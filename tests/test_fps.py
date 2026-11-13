"""Unit tests for the frame timing analysis in animawatch.fps (no browser)."""

from __future__ import annotations

import pytest

from animawatch.fps import (
    CompositorFrameStats,
    FrameTimingResult,
    LongAnimationFrame,
    LongAnimationFrameScript,
    analyze_frame_timestamps,
    classify_severity,
    estimate_refresh_interval,
    estimate_refresh_interval_from_busy,
    frame_slots,
    generate_fps_report,
    parse_compositor_trace,
    parse_long_animation_frames,
)

HZ60 = 1000.0 / 60.0


def frames(count: int, interval: float = HZ60, start: float = 1000.0) -> list[float]:
    """Evenly spaced frame start times."""
    return [start + i * interval for i in range(count)]


class TestFrameSlots:
    def test_one_interval_is_one_slot(self) -> None:
        assert frame_slots(HZ60, HZ60) == 1

    def test_jitter_below_half_an_interval_is_not_a_drop(self) -> None:
        assert frame_slots(HZ60 * 1.49, HZ60) == 1

    def test_half_rounds_up(self) -> None:
        # Python's round() would give 2 for 1.5 but also 2 for 2.5: rounding is half up here.
        assert frame_slots(HZ60 * 1.5, HZ60) == 2
        assert frame_slots(HZ60 * 2.5, HZ60) == 3

    def test_short_gap_counts_as_one_slot(self) -> None:
        assert frame_slots(1.0, HZ60) == 1

    def test_rejects_non_positive_interval(self) -> None:
        with pytest.raises(ValueError):
            frame_slots(10.0, 0.0)


class TestSeverity:
    @pytest.mark.parametrize(
        ("dropped", "expected"),
        [(1, "minor"), (2, "major"), (3, "major"), (4, "severe"), (10, "severe")],
    )
    def test_by_dropped_frames(self, dropped: int, expected: str) -> None:
        assert classify_severity(dropped) == expected


class TestRefreshEstimates:
    def test_idle_page_median(self) -> None:
        assert estimate_refresh_interval(frames(31)) == pytest.approx(HZ60)

    def test_120hz(self) -> None:
        assert estimate_refresh_interval(frames(31, 1000 / 120)) == pytest.approx(1000 / 120)

    def test_too_few_samples(self) -> None:
        assert estimate_refresh_interval(frames(5)) is None

    def test_implausible_rates_rejected(self) -> None:
        assert estimate_refresh_interval(frames(31, 1.0)) is None
        assert estimate_refresh_interval(frames(31, 250.0)) is None

    def test_busy_page_estimate_ignores_long_gaps(self) -> None:
        # Half of all gaps are 100 ms stalls; the median alone would be wrong.
        stamps = [0.0]
        for i in range(60):
            stamps.append(stamps[-1] + (100.0 if i % 2 else HZ60))
        assert estimate_refresh_interval_from_busy(stamps) == pytest.approx(HZ60)

    def test_busy_page_estimate_needs_samples(self) -> None:
        assert estimate_refresh_interval_from_busy([0.0, 16.7]) is None


class TestAnalyzeFrameTimestamps:
    def test_perfectly_smooth(self) -> None:
        result = analyze_frame_timestamps(frames(181), HZ60, refresh_source="calibrated")

        assert result.frames_presented == 180
        assert result.dropped_frames == 0
        assert result.jank_percentage == 0.0
        assert result.verdict == "smooth"
        assert result.average_fps == pytest.approx(60.0)
        assert result.refresh_rate_hz == pytest.approx(60.0)
        assert result.jank_events == ()

    def test_regression_25fps_is_not_jank_at_25hz(self) -> None:
        # The bug: 40 ms gaps (a 25 fps recording) were judged against 60 fps.
        # Judged against the interval they were produced at, they are smooth.
        result = analyze_frame_timestamps(frames(86, 40.0), 40.0)
        assert result.jank_percentage == 0.0

    def test_single_long_frame(self) -> None:
        stamps = frames(10)
        stamps.append(stamps[-1] + 100.0)  # six intervals: five dropped
        result = analyze_frame_timestamps(stamps, HZ60, started_at_ms=stamps[0])

        assert result.dropped_frames == 5
        assert result.frames_expected == result.frames_presented + 5
        assert len(result.jank_events) == 1
        event = result.jank_events[0]
        assert event.dropped_frames == 5
        assert event.severity == "severe"
        assert event.timestamp_ms == pytest.approx(9 * HZ60)
        assert event.frame_delta_ms == pytest.approx(100.0)

    def test_jank_percentage_is_share_of_refreshes_without_a_frame(self) -> None:
        # Every third refresh is missed: 2 frames over 3 refreshes.
        stamps = [0.0]
        for i in range(90):
            stamps.append(stamps[-1] + (2 * HZ60 if i % 2 else HZ60))
        result = analyze_frame_timestamps(stamps, HZ60)

        assert result.jank_percentage == pytest.approx(100.0 / 3, abs=0.5)
        assert result.verdict == "severe jank"

    @pytest.mark.parametrize(
        ("missed_every", "verdict"),
        [(200, "smooth"), (20, "occasional jank"), (5, "noticeable jank")],
    )
    def test_verdict_bands(self, missed_every: int, verdict: str) -> None:
        stamps = [0.0]
        for i in range(1, 1000):
            stamps.append(stamps[-1] + (2 * HZ60 if i % missed_every == 0 else HZ60))
        assert analyze_frame_timestamps(stamps, HZ60).verdict == verdict

    def test_unsorted_and_duplicate_timestamps(self) -> None:
        stamps = frames(20)
        shuffled = list(reversed(stamps)) + [stamps[3]]
        result = analyze_frame_timestamps(shuffled, HZ60)
        assert result.frames_presented == 19
        assert result.dropped_frames == 0

    def test_no_frames(self) -> None:
        result = analyze_frame_timestamps([], HZ60)
        assert result.frames_presented == 0
        assert result.jank_percentage == 0.0
        assert result.verdict == "no frames measured"
        assert any("No frames" in note for note in result.notes)

    def test_percentiles(self) -> None:
        stamps = frames(100)
        stamps.append(stamps[-1] + 50.0)
        result = analyze_frame_timestamps(stamps, HZ60)
        assert result.p50_frame_ms == pytest.approx(HZ60)
        assert result.max_frame_ms == pytest.approx(50.0)
        assert result.p99_frame_ms <= result.max_frame_ms

    def test_rejects_non_positive_interval(self) -> None:
        with pytest.raises(ValueError):
            analyze_frame_timestamps(frames(3), -1.0)


class TestParsers:
    def test_long_animation_frames(self) -> None:
        raw = [
            {
                "startTime": 1500.0,
                "duration": 104.0,
                "blockingDuration": 50.0,
                "scripts": [
                    {
                        "invoker": "TimerHandler:setInterval",
                        "sourceURL": "http://x/blocker.js",
                        "sourceFunctionName": "blockMainThread",
                        "duration": 100.0,
                    }
                ],
            }
        ]
        (frame,) = parse_long_animation_frames(raw, started_at_ms=1000.0)
        assert frame.start_ms == pytest.approx(500.0)
        assert frame.duration_ms == 104.0
        assert frame.blocking_duration_ms == 50.0
        assert frame.scripts[0].function_name == "blockMainThread"

    def test_compositor_trace_counts_states(self) -> None:
        def reporter(state: str, ph: str = "b") -> dict[str, object]:
            return {
                "name": "PipelineReporter",
                "ph": ph,
                "args": {"frame_reporter": {"state": state}},
            }

        events = [
            reporter("STATE_PRESENTED_ALL"),
            reporter("STATE_PRESENTED_ALL"),
            reporter("STATE_PRESENTED_PARTIAL"),
            reporter("STATE_DROPPED"),
            reporter("STATE_NO_UPDATE_DESIRED"),
            reporter("STATE_DROPPED", ph="e"),  # end events are not frames
            {"name": "BeginFrame", "ph": "X"},
        ]
        stats = parse_compositor_trace(events)
        assert stats == CompositorFrameStats(
            presented_all=2, presented_partial=1, dropped=1, no_update=1
        )
        assert stats.frames == 4
        assert stats.dropped_percentage == pytest.approx(25.0)
        assert stats.partial_percentage == pytest.approx(25.0)

    def test_compositor_trace_without_frames(self) -> None:
        assert parse_compositor_trace([{"name": "Other", "ph": "b"}]) is None


class TestReport:
    def _result(self, **overrides: object) -> FrameTimingResult:
        stamps = frames(60)
        stamps.append(stamps[-1] + 100.0)
        base = analyze_frame_timestamps(stamps, HZ60, refresh_source="calibrated")
        values = {**base.__dict__, **overrides}
        return FrameTimingResult(**values)  # type: ignore[arg-type]

    def test_summary_lines(self) -> None:
        report = generate_fps_report(self._result())
        assert "# Frame Timing Report" in report
        assert "not from the video recording" in report
        assert "Dropped frames**: 5 of 65" in report
        assert "60.0 Hz" in report
        assert "measured on a blank page" in report
        assert "[severe]" in report

    def test_loaf_section(self) -> None:
        loaf = LongAnimationFrame(
            start_ms=200.0,
            duration_ms=104.0,
            blocking_duration_ms=50.0,
            scripts=(
                LongAnimationFrameScript(
                    invoker="TimerHandler:setInterval",
                    source_url="http://x/blocker.js",
                    function_name="blockMainThread",
                    duration_ms=100.0,
                ),
            ),
        )
        report = generate_fps_report(
            self._result(loaf_supported=True, long_animation_frames=(loaf,))
        )
        assert "blockMainThread" in report
        assert "104 ms" in report

    def test_loaf_unsupported_and_none(self) -> None:
        assert "Not available" in generate_fps_report(self._result(loaf_supported=False))
        assert "None over 50 ms" in generate_fps_report(self._result(loaf_supported=True))

    def test_compositor_section_and_notes(self) -> None:
        stats = CompositorFrameStats(presented_all=90, presented_partial=5, dropped=5, no_update=0)
        report = generate_fps_report(self._result(compositor=stats, notes=("a note",)))
        assert "Compositor frames" in report
        assert "Dropped**: 5 (5.0%)" in report
        assert "- a note" in report

    def test_event_list_is_truncated(self) -> None:
        stamps = [0.0]
        for _ in range(15):
            stamps.extend([stamps[-1] + HZ60, stamps[-1] + HZ60 + 50.0])
        result = analyze_frame_timestamps(stamps, HZ60)
        report = generate_fps_report(result, max_events=10)
        assert "... and 5 more" in report
