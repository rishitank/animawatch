"""Regression tests for frame timing, against a real headless Chromium.

The old metric compared the gaps between frames of Playwright's 25 fps video
with a 60 fps target, so a perfectly smooth animation scored 98.8% jank. These
tests pin the in-page measurement that replaced it.
"""

from __future__ import annotations

import pytest

from animawatch.browser import BrowserRecorder, URLNotAllowedError
from animawatch.config import settings

pytestmark = pytest.mark.browser

MEASURE_SECONDS = 3.0


async def test_smooth_css_animation_scores_under_two_percent(
    chromium: BrowserRecorder, page_server: str
) -> None:
    result = await chromium.measure_interaction(
        f"{page_server}/smooth.html", wait_time=MEASURE_SECONDS
    )

    timing = result.timing
    assert timing is not None
    assert timing.jank_percentage < 2.0, timing
    assert timing.verdict == "smooth"
    # About one frame per refresh for the whole window.
    assert timing.frames_presented >= 0.9 * MEASURE_SECONDS * timing.refresh_rate_hz
    assert timing.refresh_source == "calibrated"
    assert 2.0 <= timing.refresh_interval_ms <= 100.0
    assert timing.loaf_supported
    assert timing.long_animation_frames == ()
    assert result.video_path is None


async def test_main_thread_blocked_for_100ms_scores_over_thirty_percent(
    chromium: BrowserRecorder, page_server: str
) -> None:
    result = await chromium.measure_interaction(
        f"{page_server}/blocked.html", wait_time=MEASURE_SECONDS
    )

    timing = result.timing
    assert timing is not None
    assert timing.jank_percentage > 30.0, timing
    assert timing.verdict == "severe jank"
    # rAF timestamps are frame start times, so a 100 ms block shows as a gap of
    # at least five refresh intervals (four dropped frames, "severe").
    assert timing.max_frame_ms >= 4.5 * timing.refresh_interval_ms
    assert any(e.severity == "severe" for e in timing.jank_events)
    # The Long Animation Frames API sees the 100 ms blocks and names the timer.
    long_frames = [f for f in timing.long_animation_frames if f.duration_ms >= 95.0]
    assert len(long_frames) >= 5
    invokers = {s.invoker for f in timing.long_animation_frames for s in f.scripts}
    assert any("setInterval" in invoker for invoker in invokers), invokers
    functions = {s.function_name for f in timing.long_animation_frames for s in f.scripts}
    assert "blockMainThread" in functions, functions


async def test_recording_video_does_not_add_jank(
    chromium: BrowserRecorder, page_server: str
) -> None:
    result = await chromium.measure_interaction(
        f"{page_server}/smooth.html", wait_time=MEASURE_SECONDS, record_video=True
    )

    assert result.timing is not None
    assert result.timing.jank_percentage < 2.0, result.timing
    assert result.video_path is not None
    assert result.video_path.exists()
    assert result.video_path.stat().st_size > 0
    result.video_path.unlink()


async def test_compositor_trace_tells_main_thread_jank_from_dropped_frames(
    chromium: BrowserRecorder, page_server: str
) -> None:
    # CSS transform animation: the compositor keeps presenting frames even while
    # the main thread is blocked, so users see a smooth animation.
    css = await chromium.measure_interaction(
        f"{page_server}/blocked-css.html", wait_time=MEASURE_SECONDS, trace_compositor=True
    )
    # rAF-driven animation: blocking the main thread drops visible frames.
    js = await chromium.measure_interaction(
        f"{page_server}/blocked.html", wait_time=MEASURE_SECONDS, trace_compositor=True
    )

    assert css.timing is not None and css.timing.compositor is not None, css.timing
    assert js.timing is not None and js.timing.compositor is not None, js.timing
    assert css.timing.jank_percentage > 30.0
    assert css.timing.compositor.dropped_percentage < 2.0, css.timing.compositor
    assert js.timing.compositor.dropped_percentage > 10.0, js.timing.compositor


async def test_navigation_during_measurement_is_reported(
    chromium: BrowserRecorder, page_server: str
) -> None:
    result = await chromium.measure_interaction(
        f"{page_server}/navigates.html",
        actions=[{"type": "click", "selector": "#go"}],
        wait_time=2.0,
    )

    assert result.timing is not None
    assert any("navigated" in note for note in result.timing.notes), result.timing.notes
    # Measurement re-armed itself in the new document, after that page loaded.
    assert any("restarted once the new page" in n for n in result.timing.notes)
    assert result.timing.frames_presented > 30
    assert result.timing.jank_percentage < 2.0, result.timing


async def test_configured_refresh_rate_is_used(chromium: BrowserRecorder, page_server: str) -> None:
    result = await chromium.measure_interaction(
        f"{page_server}/smooth.html", wait_time=1.0, refresh_rate_hz=30.0
    )

    assert result.timing is not None
    assert result.timing.refresh_source == "configured"
    assert result.timing.refresh_interval_ms == pytest.approx(1000.0 / 30.0)


async def test_file_urls_refused_when_hosted(
    chromium: BrowserRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "allow_file_urls", False)

    with pytest.raises(URLNotAllowedError):
        await chromium.measure_interaction("file:///etc/hostname", wait_time=0.1)
    with pytest.raises(URLNotAllowedError):
        await chromium.take_screenshot("file:///etc/hostname")


async def test_core_web_vitals_reads_lcp_and_cls(
    chromium: BrowserRecorder, page_server: str
) -> None:
    """LCP and layout shifts are only visible to a buffered PerformanceObserver.

    The previous code read them with getEntriesByType, which returns nothing for
    these types, so LCP was always missing and CLS always 0.
    """
    from animawatch.metrics import extract_performance_metrics

    async with chromium.pooled_context() as (_, page):
        await page.goto(f"{page_server}/shift.html", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        metrics = await extract_performance_metrics(page, f"{page_server}/shift.html")

    vitals = metrics.core_web_vitals
    assert vitals.lcp_ms is not None and vitals.lcp_ms > 0
    assert vitals.fcp_ms is not None and vitals.fcp_ms > 0
    assert vitals.cls_score is not None and vitals.cls_score > 0.01
    assert vitals.ttfb_ms is not None and vitals.ttfb_ms >= 0
