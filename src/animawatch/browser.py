"""Browser automation, frame timing and video recording using Playwright.

Features:
- Frame timing measured inside the page (see ``animawatch.fps``)
- Video recording of browser interactions, for the vision pass only
- Mobile device emulation with predefined profiles
- Connection pooling for browser context reuse
- Screenshot capture with full-page support
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import tempfile
import time
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import (
    Browser,
    BrowserContext,
    CDPSession,
    Frame,
    Page,
    Playwright,
    Request,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError

from .actions import (
    Action,
    ClickAction,
    HoverAction,
    ScrollAction,
    TypeAction,
    WaitAction,
    parse_actions,
)
from .config import settings
from .devices import DeviceProfile, get_device
from .fps import (
    CALIBRATION_JS,
    DEFAULT_REFRESH_INTERVAL_MS,
    FRAME_BUFFER_LIMIT,
    FRAME_COLLECTOR_JS,
    LOAF_BUFFER_LIMIT,
    TRACE_CATEGORIES,
    CompositorFrameStats,
    FrameTimingResult,
    RefreshSource,
    analyze_frame_timestamps,
    estimate_refresh_interval,
    estimate_refresh_interval_from_busy,
    parse_compositor_trace,
    parse_long_animation_frames,
)
from .logging import log_extra

#: Number of rAF gaps sampled on a blank page to measure the refresh interval.
CALIBRATION_FRAMES = 30
#: How long to wait for Chromium to hand over a finished trace.
TRACE_TIMEOUT_SECONDS = 10.0
#: After a navigation, measurement restarts once no request has been in flight
#: for this long: the rule Playwright's "networkidle" uses.
NETWORK_QUIET_SECONDS = 0.5


class URLNotAllowedError(ValueError):
    """Raised for a URL AnimaWatch will not open."""


def validate_url(url: str) -> str:
    """Allow only http(s) URLs, plus file:// when ``settings.allow_file_urls`` is on.

    Rejects ``javascript:``, ``data:``, ``chrome:`` and every other scheme, so a
    tool call cannot run script in the browser or read browser-internal pages.
    """
    scheme = urlsplit(url).scheme.lower()
    if scheme in ("http", "https"):
        return url
    if scheme == "file" and settings.allow_file_urls:
        return url
    allowed = "http, https" + (", file" if settings.allow_file_urls else "")
    raise URLNotAllowedError(
        f"URL scheme '{scheme or '(none)'}' is not allowed (allowed: {allowed})"
    )


def clamp_seconds(value: Any) -> float:
    """A wait in seconds, bounded to [0, settings.max_recording_duration]."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(seconds):
        return 0.0
    return min(max(0.0, seconds), float(settings.max_recording_duration))


@dataclass(frozen=True)
class InteractionResult:
    """What one measured interaction produced."""

    video_path: Path | None
    timing: FrameTimingResult | None


class _CompositorTrace:
    """A Chromium trace limited to the per-frame ``PipelineReporter`` events."""

    def __init__(self, session: CDPSession) -> None:
        self._session = session
        self._events: list[dict[str, Any]] = []
        self._done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        session.on("Tracing.dataCollected", self._collect)
        session.on("Tracing.tracingComplete", self._complete)

    def _collect(self, params: dict[str, Any]) -> None:
        self._events.extend(params.get("value", []))

    def _complete(self, _params: dict[str, Any]) -> None:
        if not self._done.done():
            self._done.set_result(None)

    async def start(self) -> None:
        await self._session.send(
            "Tracing.start",
            {
                "traceConfig": {"includedCategories": TRACE_CATEGORIES},
                "transferMode": "ReportEvents",
            },
        )

    async def stop(self) -> CompositorFrameStats | None:
        await self._session.send("Tracing.end")
        await asyncio.wait_for(self._done, timeout=TRACE_TIMEOUT_SECONDS)
        with contextlib.suppress(Exception):
            await self._session.detach()
        return parse_compositor_trace(self._events)


class _NavigationRearm:
    """Restarts measurement in a document that replaced the measured one.

    A click or a script can navigate during the measurement window. The new
    document gets the collector from the context's init script, but it is not
    measuring. Playwright reports every request the page makes, so the requests
    in flight are known exactly. After a main-frame navigation, this waits for
    the ``load`` event and then for ``NETWORK_QUIET_SECONDS`` with no request in
    flight, and only then starts measuring. The new page's load work is
    therefore excluded, as it is for the first page.
    """

    def __init__(self, page: Page) -> None:
        self._page = page
        self._in_flight: set[Request] = set()
        self._last_activity = time.monotonic()
        self._task: asyncio.Task[None] | None = None
        self._closed = False
        page.on("request", self._on_request)
        page.on("requestfinished", self._on_request_done)
        page.on("requestfailed", self._on_request_done)
        page.on("framenavigated", self._on_navigated)

    def _on_request(self, request: Request) -> None:
        self._in_flight.add(request)
        self._last_activity = time.monotonic()

    def _on_request_done(self, request: Request) -> None:
        self._in_flight.discard(request)
        self._last_activity = time.monotonic()

    def _on_navigated(self, frame: Frame) -> None:
        # Also fires for same-document navigations (pushState, #hash); restart()
        # is then a no-op, because the collector is still running.
        if frame != self._page.main_frame:
            return
        if self._task is not None:
            self._task.cancel()
        self._task = asyncio.get_running_loop().create_task(self._restart_when_idle())

    def _network_quiet(self) -> bool:
        return (
            not self._in_flight and time.monotonic() - self._last_activity >= NETWORK_QUIET_SECONDS
        )

    async def _restart_when_idle(self) -> None:
        try:
            await self._page.wait_for_load_state("load")
            while not self._network_quiet():
                await asyncio.sleep(0.05)
            await self._page.evaluate(
                "() => window.__animawatchFrames && window.__animawatchFrames.restart()"
            )
        except PlaywrightError as err:
            # Another navigation replaced this document; its own task takes over.
            log_extra("Measurement restart skipped", error=str(err))

    async def close(self) -> None:
        """Stop waiting for a restart; the window has ended. Safe to call twice."""
        if self._closed:
            return
        self._closed = True
        self._page.remove_listener("request", self._on_request)
        self._page.remove_listener("requestfinished", self._on_request_done)
        self._page.remove_listener("requestfailed", self._on_request_done)
        self._page.remove_listener("framenavigated", self._on_navigated)
        if self._task is not None and not self._task.done():
            # Still waiting: the new page never went quiet within the window.
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task


class BrowserRecorder:
    """Manages browser automation, frame timing and video recording.

    Features:
    - In-page frame timing with a measured refresh interval
    - Video recording with configurable viewport (for the vision pass)
    - Mobile device emulation
    - Connection pooling for reusing browser contexts
    - Structured logging for observability
    """

    def __init__(self, pool_size: int = 3) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._pool_size = pool_size
        self._context_pool: list[BrowserContext] = []
        self._pool_lock = asyncio.Lock()
        self._calibrated_interval_ms: float | None = None

    async def start(self) -> None:
        """Start the Playwright browser."""
        self._playwright = await async_playwright().start()
        launch_options: dict[str, Any] = {"headless": settings.browser_headless}
        if settings.browser_executable_path:
            launch_options["executable_path"] = settings.browser_executable_path
        self._browser = await self._playwright.chromium.launch(**launch_options)
        log_extra("Browser started", headless=settings.browser_headless)

    async def stop(self) -> None:
        """Stop the browser and cleanup."""
        # Close all pooled contexts
        async with self._pool_lock:
            for ctx in self._context_pool:
                await ctx.close()
            self._context_pool.clear()

        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        log_extra("Browser stopped")

    async def _ensure_browser(self) -> Browser:
        if not self._browser:
            await self.start()
        if self._browser is None:
            raise RuntimeError("Browser not initialized")
        return self._browser

    def _context_options(self, profile: DeviceProfile | None) -> dict[str, Any]:
        """Viewport and device-emulation options for a new context."""
        options: dict[str, Any] = {
            "viewport": profile.viewport if profile else settings.video_size,
        }
        if profile:
            options["user_agent"] = profile.user_agent
            options["device_scale_factor"] = profile.device_scale_factor
            options["is_mobile"] = profile.is_mobile
            options["has_touch"] = profile.has_touch
            log_extra("Device emulation", device=profile.name, viewport=options["viewport"])
        return options

    @asynccontextmanager
    async def recording_context(
        self,
        video_dir: Path | None = None,
        device: str | DeviceProfile | None = None,
    ) -> AsyncGenerator[tuple[BrowserContext, Page, Path], None]:
        """Create a browser context with video recording enabled.

        Args:
            video_dir: Directory to save video (default: temp)
            device: Device profile name or DeviceProfile for emulation
        """
        browser = await self._ensure_browser()

        # Use temp directory if not specified
        if video_dir is None:
            video_dir = Path(tempfile.mkdtemp(prefix="animawatch-"))
        video_dir.mkdir(parents=True, exist_ok=True)

        profile = self._resolve_device(device)
        context_options = self._context_options(profile)
        context_options["record_video_dir"] = str(video_dir)
        context_options["record_video_size"] = context_options["viewport"]

        context = await browser.new_context(**context_options)
        page = await context.new_page()

        try:
            yield context, page, video_dir
        finally:
            # Ensure video is saved before closing
            video = page.video
            if video:
                await video.path()  # Wait for video to be saved

            await context.close()

    def _resolve_device(self, device: str | DeviceProfile | None) -> DeviceProfile | None:
        """Resolve device name to DeviceProfile."""
        if device is None:
            return None
        if isinstance(device, DeviceProfile):
            return device
        return get_device(device)

    @asynccontextmanager
    async def pooled_context(
        self,
        device: str | DeviceProfile | None = None,
    ) -> AsyncGenerator[tuple[BrowserContext, Page], None]:
        """Get a browser context from the pool (without video recording).

        This is more efficient for screenshots and navigation tasks where
        video recording is not needed. Contexts are reused when possible.

        Args:
            device: Device profile name or DeviceProfile for emulation

        Note: Pooled contexts don't support video recording.
        For video recording, use recording_context() instead.
        """
        browser = await self._ensure_browser()
        context_options = self._context_options(self._resolve_device(device))

        # Try to get a context from the pool
        context: BrowserContext | None = None
        async with self._pool_lock:
            if self._context_pool:
                context = self._context_pool.pop()
                log_extra("Reusing pooled context", pool_remaining=len(self._context_pool))

        # Create new context if pool was empty
        if context is None:
            context = await browser.new_context(**context_options)
            log_extra("Created new context", pool_size=len(self._context_pool))

        page = await context.new_page()

        try:
            yield context, page
        finally:
            # Close the page but return context to pool if room
            await page.close()
            async with self._pool_lock:
                if len(self._context_pool) < self._pool_size:
                    self._context_pool.append(context)
                    log_extra("Returned context to pool", pool_size=len(self._context_pool))
                else:
                    await context.close()
                    log_extra("Pool full, closed context")

    async def _refresh_interval(
        self, page: Page, refresh_rate_hz: float | None
    ) -> tuple[float | None, RefreshSource]:
        """The refresh interval to judge frames against, and where it came from.

        A rate passed in (or set in ``settings.refresh_rate_hz``) wins. Otherwise
        the blank page is sampled once per browser and the result cached; None
        means the sampling failed and the caller should estimate from the page.
        """
        rate = refresh_rate_hz or settings.refresh_rate_hz
        if rate:
            return 1000.0 / rate, "configured"
        if self._calibrated_interval_ms is None:
            try:
                samples = await page.evaluate(CALIBRATION_JS, CALIBRATION_FRAMES)
                self._calibrated_interval_ms = estimate_refresh_interval(
                    [float(t) for t in samples]
                )
            except Exception as err:  # the page may be closed or not scriptable
                log_extra("Refresh-rate calibration failed", error=str(err))
                return None, "estimated"
            log_extra("Refresh interval calibrated", interval_ms=self._calibrated_interval_ms)
        if self._calibrated_interval_ms is None:
            return None, "estimated"
        return self._calibrated_interval_ms, "calibrated"

    async def measure_interaction(
        self,
        url: str,
        actions: Sequence[Action | Mapping[str, Any]] | None = None,
        wait_time: float = 3.0,
        *,
        device: str | DeviceProfile | None = None,
        record_video: bool = False,
        video_dir: Path | None = None,
        measure_frames: bool = True,
        trace_compositor: bool = False,
        refresh_rate_hz: float | None = None,
    ) -> InteractionResult:
        """Load a page, run actions, wait, and measure frame timing in the page.

        The measurement window starts once the page has loaded (network idle) and
        ends ``wait_time`` seconds after the last action, so page-load work is not
        counted as animation jank.

        Args:
            url: http(s) URL to open (file:// only when allowed in settings)
            actions: Actions to perform (click, type, scroll, hover, wait)
            wait_time: Seconds to keep measuring after the actions
            device: Device profile name or DeviceProfile for emulation
            record_video: Also record a video (for the vision pass)
            video_dir: Directory for the video (default: a temp directory)
            measure_frames: Measure frame timing (requestAnimationFrame + LoAF)
            trace_compositor: Also record Chromium's compositor frame states (CDP)
            refresh_rate_hz: Judge against this refresh rate instead of measuring it
        """
        validate_url(url)
        steps = parse_actions(actions)
        wait = clamp_seconds(wait_time)
        browser = await self._ensure_browser()

        options = self._context_options(self._resolve_device(device))
        if record_video:
            if video_dir is None:
                video_dir = Path(tempfile.mkdtemp(prefix="animawatch-"))
            video_dir.mkdir(parents=True, exist_ok=True)
            options["record_video_dir"] = str(video_dir)
            options["record_video_size"] = options["viewport"]

        context = await browser.new_context(**options)
        video_path: Path | None = None
        timing: FrameTimingResult | None = None
        rearm: _NavigationRearm | None = None
        try:
            if measure_frames:
                await context.add_init_script(FRAME_COLLECTOR_JS)
            page = await context.new_page()

            interval: float | None = None
            source: RefreshSource = "estimated"
            if measure_frames:
                interval, source = await self._refresh_interval(page, refresh_rate_hz)

            await page.goto(url, wait_until="networkidle")

            trace: _CompositorTrace | None = None
            notes: list[str] = []
            started_origin: float | None = None
            if measure_frames:
                if trace_compositor:
                    try:
                        trace = _CompositorTrace(await context.new_cdp_session(page))
                        await trace.start()
                    except Exception as err:  # not Chromium, or tracing refused
                        trace = None
                        notes.append(f"Compositor trace unavailable: {err}")
                started_origin = await page.evaluate(
                    "() => { window.__animawatchFrames.start(); return performance.timeOrigin; }"
                )
                # A navigation during the window restarts measurement in the new document.
                rearm = _NavigationRearm(page)

            for step in steps:
                await self._perform_action(page, step)

            await asyncio.sleep(wait)

            if measure_frames:
                if rearm is not None:
                    await rearm.close()
                raw = await page.evaluate(
                    "() => window.__animawatchFrames ? window.__animawatchFrames.stop() : null"
                )
                compositor: CompositorFrameStats | None = None
                if trace is not None:
                    try:
                        compositor = await trace.stop()
                        if compositor is None:
                            notes.append("The trace held no compositor frame events.")
                    except Exception as err:
                        notes.append(f"Compositor trace failed: {err}")
                timing = _build_timing(raw, interval, source, started_origin, compositor, notes)

            if record_video and page.video:
                video_path = Path(await page.video.path())
        finally:
            if rearm is not None:
                await rearm.close()
            # Closing the context finalises the video file.
            await context.close()

        return InteractionResult(video_path=video_path, timing=timing)

    async def record_interaction(
        self,
        url: str,
        actions: Sequence[Action | Mapping[str, Any]] | None = None,
        wait_time: float = 3.0,
        video_dir: Path | None = None,
        device: str | None = None,
    ) -> Path:
        """
        Record a browser interaction and return the video path.

        Args:
            url: URL to navigate to
            actions: Optional list of actions to perform (click, type, scroll, etc.)
            wait_time: Time to wait after actions for animations to complete
            video_dir: Directory to save video (default: temp)
            device: Device profile name for mobile emulation (e.g., "iphone_15_pro")

        Returns:
            Path to the recorded video file
        """
        result = await self.measure_interaction(
            url,
            actions,
            wait_time,
            device=device,
            record_video=True,
            video_dir=video_dir,
            measure_frames=False,
        )
        if result.video_path is None:
            raise RuntimeError("Failed to record video")
        return result.video_path

    async def take_screenshot(
        self,
        url: str,
        full_page: bool = True,
        device: str | None = None,
        use_pool: bool = False,
    ) -> Path:
        """Take a screenshot of a page.

        Args:
            url: URL to screenshot
            full_page: Capture full scrollable page or just viewport
            device: Device profile name for mobile emulation
            use_pool: Use connection pooling for better performance (default: False)
                Note: Pooling ignores device-specific settings for reuse efficiency
        """
        validate_url(url)
        if use_pool and device is None:
            # Use pooled context for better performance (no device emulation)
            async with self.pooled_context() as (_, page):
                await page.goto(url, wait_until="networkidle")

                fd, tmp_path = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                screenshot_path = Path(tmp_path)
                await page.screenshot(path=str(screenshot_path), full_page=full_page)

                log_extra(
                    "Screenshot captured (pooled)",
                    url=url,
                    full_page=full_page,
                )
                return screenshot_path

        # Non-pooled path (original behavior with device support)
        browser = await self._ensure_browser()
        profile = self._resolve_device(device)
        context = await browser.new_context(**self._context_options(profile))
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle")

            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            screenshot_path = Path(tmp_path)
            await page.screenshot(path=str(screenshot_path), full_page=full_page)

            log_extra(
                "Screenshot captured",
                url=url,
                device=profile.name if profile else "default",
                full_page=full_page,
            )
            return screenshot_path
        finally:
            await context.close()

    async def _perform_action(self, page: Page, action: Action | Mapping[str, Any]) -> None:
        """Perform a single browser action (validated first)."""
        (parsed,) = parse_actions([action])

        if isinstance(parsed, ClickAction):
            await page.click(parsed.selector)
        elif isinstance(parsed, TypeAction):
            await page.fill(parsed.selector, parsed.text)
        elif isinstance(parsed, ScrollAction):
            # Passed as an argument, never formatted into the script.
            await page.evaluate("(y) => window.scrollBy(0, y)", parsed.y)
        elif isinstance(parsed, WaitAction):
            await asyncio.sleep(clamp_seconds(parsed.duration))
        elif isinstance(parsed, HoverAction):
            await page.hover(parsed.selector)


def _build_timing(
    raw: dict[str, Any] | None,
    interval: float | None,
    source: RefreshSource,
    started_origin: float | None,
    compositor: CompositorFrameStats | None,
    notes: list[str],
) -> FrameTimingResult:
    """Turn the collector's snapshot into a FrameTimingResult."""
    if not raw:
        notes.append("The frame collector was not present in the final document.")
        raw = {}
    timestamps = [float(t) for t in raw.get("timestamps", [])]

    origin = raw.get("timeOrigin")
    navigated = (
        origin is not None
        and started_origin is not None
        and abs(float(origin) - float(started_origin)) > 0.5
    )
    if navigated:
        notes.append(
            "The page navigated during measurement: only frames of the last document are counted."
        )
        if raw.get("startedAt") is None:
            notes.append(
                "The new page's network did not go quiet "
                f"({NETWORK_QUIET_SECONDS * 1000:.0f} ms with no request in flight) before the "
                "window ended, so it was not measured. Measure that URL directly."
            )
        if compositor is not None:
            # The trace covers the whole window: the first page, the navigation and
            # the new page's load. It cannot be cut to the last document's window.
            compositor = None
            notes.append(
                "The compositor trace was left out because it spans the navigation and "
                "the new page's load, so it does not match the window measured above."
            )
    frames_overflow = bool(raw.get("framesOverflow")) and bool(timestamps)
    loaf_entries: list[dict[str, Any]] = list(raw.get("loaf", []))
    if frames_overflow:
        notes.append(
            f"The frame buffer filled ({FRAME_BUFFER_LIMIT} frames), so the window ends at "
            "the last recorded frame; the rest of the wait was not measured."
        )
        # Everything reported must cover the same window as the frame timing.
        window_end = max(timestamps)
        loaf_entries = [e for e in loaf_entries if float(e.get("startTime", 0.0)) <= window_end]
        if compositor is not None:
            # The trace ran until stop(), past the last recorded frame.
            compositor = None
            notes.append(
                "The compositor trace was left out because it runs past the last "
                "recorded frame, so it does not match the window measured above."
            )
    if raw.get("loafOverflow"):
        notes.append(
            f"Only the first {LOAF_BUFFER_LIMIT} long animation frames were kept; there were more."
        )
    if raw.get("visibility") == "hidden":
        notes.append("The page was hidden, so the browser throttled its frames.")
    if raw.get("armedAfterNavigation"):
        notes.append(
            "After the navigation, measurement restarted once the new page had loaded and "
            f"no request had been in flight for {NETWORK_QUIET_SECONDS * 1000:.0f} ms, "
            "so its load work is not counted."
        )

    if interval is None:
        estimated = estimate_refresh_interval_from_busy(timestamps)
        if estimated is None:
            interval, source = DEFAULT_REFRESH_INTERVAL_MS, "assumed"
        else:
            interval, source = estimated, "estimated"

    started_at = raw.get("startedAt")
    # Past a full buffer nothing was recorded, so that time is not a stall.
    stopped_at = None if frames_overflow else raw.get("stoppedAt")
    return analyze_frame_timestamps(
        timestamps,
        interval,
        refresh_source=source,
        started_at_ms=float(started_at) if started_at is not None else None,
        stopped_at_ms=float(stopped_at) if stopped_at is not None else None,
        long_animation_frames=parse_long_animation_frames(
            loaf_entries, float(started_at) if started_at is not None else 0.0
        ),
        loaf_supported=bool(raw.get("loafSupported", False)),
        compositor=compositor,
        notes=notes,
    )
