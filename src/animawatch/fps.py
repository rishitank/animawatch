"""Frame timing measured inside the page: dropped frames and jank.

Why not the video: Playwright records video at a fixed 25 fps, so the gaps
between recorded frames say nothing about how often the page painted. A
perfectly smooth animation measured from the recording scored 98.8% "jank".
The recording is kept for the vision pass only.

What is measured instead, in the page under test:

- ``requestAnimationFrame`` timestamps. Each callback receives the start time
  of the frame the main thread produced. The gaps between them, compared with
  the display's refresh interval, give the frames the main thread dropped.
- Long Animation Frames (``PerformanceObserver`` type ``long-animation-frame``,
  Chromium 123+), which name the scripts that held a frame up.
- Optionally, Chromium's own compositor frame reports from a CDP trace
  (``PipelineReporter`` events), which show whether the frames the user saw
  were presented in full, presented without the main thread's update, or
  dropped. A transform or opacity animation runs on the compositor and can stay
  smooth while the main thread is blocked; the trace shows that difference.

The refresh interval is measured, not assumed: before the page loads, the
blank tab is sampled for a few dozen ``requestAnimationFrame`` callbacks and
the median gap is taken as the display's refresh interval.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

# --------------------------------------------------------------------------
# Scripts injected into the page
# --------------------------------------------------------------------------

#: Defines ``window.__animawatchFrames`` in a document (once). It does nothing
#: until ``start()`` is called: the rAF loop only runs while measuring, so the
#: page is not kept painting outside the window. ``restart()`` starts measuring
#: in a document that replaced the measured one; the browser module calls it
#: once that page has loaded and its network has gone quiet, so the new page's
#: load work is not counted.
_COLLECTOR_BODY = r"""
  if (!window.__animawatchFrames) {
    const MAX_FRAMES = 20000;
    const MAX_LOAF = 500;
    const state = {
      running: false,
      timestamps: [],
      loaf: [],
      loafSupported: false,
      startedAt: null,
      armedAfterNavigation: false,
      overflow: false,
    };
    let observer = null;
    const tick = (ts) => {
      if (!state.running) { return; }
      if (state.timestamps.length < MAX_FRAMES) { state.timestamps.push(ts); }
      else { state.overflow = true; }
      requestAnimationFrame(tick);
    };
    const record = (entries) => {
      for (const e of entries) {
        if (state.loaf.length >= MAX_LOAF) { state.overflow = true; continue; }
        state.loaf.push({
          startTime: e.startTime,
          duration: e.duration,
          blockingDuration: e.blockingDuration || 0,
          scripts: (e.scripts || []).slice(0, 5).map((s) => ({
            invoker: String(s.invoker || ''),
            sourceURL: String(s.sourceURL || ''),
            sourceFunctionName: String(s.sourceFunctionName || ''),
            duration: s.duration || 0,
          })),
        });
      }
    };
    try {
      const types = (window.PerformanceObserver && PerformanceObserver.supportedEntryTypes) || [];
      if (types.includes('long-animation-frame')) {
        state.loafSupported = true;
        observer = new PerformanceObserver((list) => record(list.getEntries()));
        observer.observe({ type: 'long-animation-frame', buffered: true });
      }
    } catch (e) {
      state.loafSupported = false;
    }
    const start = () => {
      if (state.running) { return; }
      state.timestamps = [];
      state.overflow = false;
      state.startedAt = performance.now();
      state.running = true;
      requestAnimationFrame(tick);
    };
    Object.defineProperty(window, '__animawatchFrames', {
      configurable: false,
      enumerable: false,
      value: Object.freeze({
        start,
        restart() {
          // A same-document navigation (pushState, #hash) leaves this running.
          if (state.running) { return false; }
          state.armedAfterNavigation = true;
          start();
          return true;
        },
        stop() {
          state.running = false;
          // Entries the observer has not delivered yet would otherwise be lost.
          if (observer) { record(observer.takeRecords()); }
          const from = state.startedAt === null ? 0 : state.startedAt;
          return {
            timestamps: state.timestamps.slice(),
            loaf: state.loaf.filter((e) => e.startTime + e.duration >= from),
            loafSupported: state.loafSupported,
            startedAt: state.startedAt,
            stoppedAt: performance.now(),
            timeOrigin: performance.timeOrigin,
            armedAfterNavigation: state.armedAfterNavigation,
            overflow: state.overflow,
            visibility: document.visibilityState,
          };
        },
      }),
    });
  }
"""

#: Installed with ``BrowserContext.add_init_script`` before the page loads, so
#: every document in the context, including one reached by navigating, has it.
FRAME_COLLECTOR_JS = "(() => {" + _COLLECTOR_BODY + "})();"

#: Samples ``count`` + 1 rAF timestamps on an idle page (resolves early after
#: two seconds if the page is throttled).
CALIBRATION_JS = r"""
(count) => new Promise((resolve) => {
  const ts = [];
  const done = () => resolve(ts);
  const tick = (t) => {
    ts.push(t);
    if (ts.length > count) { done(); } else { requestAnimationFrame(tick); }
  };
  requestAnimationFrame(tick);
  setTimeout(done, 2000);
})
"""

#: Trace categories that carry Chromium's per-frame ``PipelineReporter`` events.
TRACE_CATEGORIES = ["cc", "benchmark", "disabled-by-default-devtools.timeline.frame"]

DEFAULT_REFRESH_INTERVAL_MS = 1000.0 / 60.0
MIN_CALIBRATION_DELTAS = 5

RefreshSource = Literal["configured", "calibrated", "estimated", "assumed"]
Severity = Literal["minor", "major", "severe"]


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class JankEvent:
    """A gap between two main-thread frames longer than one refresh interval."""

    timestamp_ms: float  # since the start of measurement
    frame_delta_ms: float
    dropped_frames: int
    severity: Severity


@dataclass(frozen=True)
class LongAnimationFrameScript:
    """A script attributed to a long animation frame."""

    invoker: str
    source_url: str
    function_name: str
    duration_ms: float


@dataclass(frozen=True)
class LongAnimationFrame:
    """A Long Animation Frames API entry (a frame that took over 50 ms)."""

    start_ms: float  # since the start of measurement
    duration_ms: float
    blocking_duration_ms: float
    scripts: tuple[LongAnimationFrameScript, ...] = ()


@dataclass(frozen=True)
class CompositorFrameStats:
    """Chromium's own verdict on each compositor frame, from a CDP trace."""

    presented_all: int
    presented_partial: int
    dropped: int
    no_update: int

    @property
    def frames(self) -> int:
        """Frames the compositor had something to show for."""
        return self.presented_all + self.presented_partial + self.dropped

    @property
    def dropped_percentage(self) -> float:
        """Share of compositor frames that were dropped."""
        return 100.0 * self.dropped / self.frames if self.frames else 0.0

    @property
    def partial_percentage(self) -> float:
        """Share presented without the main thread's update."""
        return 100.0 * self.presented_partial / self.frames if self.frames else 0.0


@dataclass(frozen=True)
class FrameTimingResult:
    """Main-thread frame timing over one measurement window."""

    refresh_interval_ms: float
    refresh_source: RefreshSource
    duration_ms: float
    frames_presented: int
    frames_expected: int
    dropped_frames: int
    jank_percentage: float  # dropped / expected * 100
    average_fps: float
    p50_frame_ms: float
    p95_frame_ms: float
    p99_frame_ms: float
    max_frame_ms: float
    jank_events: tuple[JankEvent, ...] = ()
    long_animation_frames: tuple[LongAnimationFrame, ...] = ()
    loaf_supported: bool = False
    compositor: CompositorFrameStats | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def refresh_rate_hz(self) -> float:
        """The refresh rate the measurement was judged against."""
        return 1000.0 / self.refresh_interval_ms

    @property
    def verdict(self) -> str:
        """AnimaWatch's own bands for the dropped-frame percentage."""
        if self.frames_presented == 0:
            return "no frames measured"
        if self.jank_percentage < 2.0:
            return "smooth"
        if self.jank_percentage < 10.0:
            return "occasional jank"
        if self.jank_percentage < 30.0:
            return "noticeable jank"
        return "severe jank"


# --------------------------------------------------------------------------
# Analysis (pure functions, unit tested without a browser)
# --------------------------------------------------------------------------


def frame_slots(delta_ms: float, refresh_interval_ms: float) -> int:
    """How many refresh intervals a frame gap spans, rounded half up, at least 1."""
    if refresh_interval_ms <= 0:
        raise ValueError("refresh_interval_ms must be positive")
    return max(1, math.floor(delta_ms / refresh_interval_ms + 0.5))


def classify_severity(dropped_frames: int) -> Severity:
    """Severity of one long gap, by the frames it dropped."""
    if dropped_frames >= 4:
        return "severe"
    if dropped_frames >= 2:
        return "major"
    return "minor"


def _deltas(timestamps: Sequence[float]) -> list[float]:
    ordered = sorted(timestamps)
    return [b - a for a, b in zip(ordered, ordered[1:], strict=False) if b - a > 0]


def estimate_refresh_interval(timestamps: Sequence[float]) -> float | None:
    """The median gap between consecutive rAF timestamps of an idle page.

    Returns None when fewer than ``MIN_CALIBRATION_DELTAS`` gaps were seen or the
    median is implausible (under 2 ms or over 100 ms, i.e. outside 10-500 Hz).
    """
    deltas = _deltas(timestamps)
    if len(deltas) < MIN_CALIBRATION_DELTAS:
        return None
    median = statistics.median(deltas)
    if not 2.0 <= median <= 100.0:
        return None
    return float(median)


def estimate_refresh_interval_from_busy(timestamps: Sequence[float]) -> float | None:
    """Estimate the refresh interval from a page that may itself be janky.

    Takes the 10th-percentile gap as an anchor and returns the median of the gaps
    within 20% of it, so long gaps (jank) do not pull the estimate up. Used only
    when calibration on a blank page failed.
    """
    deltas = sorted(_deltas(timestamps))
    if len(deltas) < MIN_CALIBRATION_DELTAS:
        return None
    anchor = deltas[len(deltas) // 10]
    cluster = [d for d in deltas if 0.8 * anchor <= d <= 1.2 * anchor]
    estimate = statistics.median(cluster) if cluster else anchor
    if not 2.0 <= estimate <= 100.0:
        return None
    return float(estimate)


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, math.ceil(pct / 100.0 * len(sorted_values)) - 1))
    return float(sorted_values[index])


def parse_long_animation_frames(
    entries: Iterable[dict[str, Any]], started_at_ms: float
) -> tuple[LongAnimationFrame, ...]:
    """Convert raw LoAF entries from the page into results, times relative to start."""
    frames: list[LongAnimationFrame] = []
    for entry in entries:
        scripts = tuple(
            LongAnimationFrameScript(
                invoker=str(s.get("invoker", "")),
                source_url=str(s.get("sourceURL", "")),
                function_name=str(s.get("sourceFunctionName", "")),
                duration_ms=float(s.get("duration", 0.0)),
            )
            for s in entry.get("scripts", [])
        )
        frames.append(
            LongAnimationFrame(
                start_ms=float(entry.get("startTime", 0.0)) - started_at_ms,
                duration_ms=float(entry.get("duration", 0.0)),
                blocking_duration_ms=float(entry.get("blockingDuration", 0.0)),
                scripts=scripts,
            )
        )
    return tuple(frames)


def parse_compositor_trace(events: Iterable[dict[str, Any]]) -> CompositorFrameStats | None:
    """Count Chromium ``PipelineReporter`` frames by their final state.

    Each compositor frame produces one async ``PipelineReporter`` begin event
    whose ``args.frame_reporter.state`` is one of ``STATE_PRESENTED_ALL``,
    ``STATE_PRESENTED_PARTIAL``, ``STATE_DROPPED`` or ``STATE_NO_UPDATE_DESIRED``.
    Returns None when the trace holds no such events (another browser, or a
    Chromium that renamed them).
    """
    counts = {"all": 0, "partial": 0, "dropped": 0, "none": 0}
    seen = False
    for event in events:
        if event.get("name") != "PipelineReporter" or event.get("ph") != "b":
            continue
        reporter = (event.get("args") or {}).get("frame_reporter") or {}
        state = reporter.get("state")
        if state == "STATE_PRESENTED_ALL":
            counts["all"] += 1
        elif state == "STATE_PRESENTED_PARTIAL":
            counts["partial"] += 1
        elif state == "STATE_DROPPED":
            counts["dropped"] += 1
        elif state == "STATE_NO_UPDATE_DESIRED":
            counts["none"] += 1
        else:
            continue
        seen = True
    if not seen:
        return None
    return CompositorFrameStats(
        presented_all=counts["all"],
        presented_partial=counts["partial"],
        dropped=counts["dropped"],
        no_update=counts["none"],
    )


def analyze_frame_timestamps(
    timestamps: Sequence[float],
    refresh_interval_ms: float,
    *,
    refresh_source: RefreshSource = "configured",
    started_at_ms: float | None = None,
    stopped_at_ms: float | None = None,
    long_animation_frames: Sequence[LongAnimationFrame] = (),
    loaf_supported: bool = False,
    compositor: CompositorFrameStats | None = None,
    notes: Sequence[str] = (),
) -> FrameTimingResult:
    """Judge rAF timestamps against the display's refresh interval.

    Each gap between consecutive frames spans ``n`` refresh intervals (rounded);
    ``n - 1`` of those intervals produced no main-thread frame and count as
    dropped. The jank percentage is dropped / (presented + dropped): the share
    of the display's refreshes in the window that got no new frame.

    ``started_at_ms`` and ``stopped_at_ms`` are the edges of the measurement
    window. A stall between the start and the first frame, or between the last
    frame and the stop, counts as dropped frames too; the edges themselves are
    not presented frames.
    """
    if refresh_interval_ms <= 0:
        raise ValueError("refresh_interval_ms must be positive")

    ordered = sorted(timestamps)
    deltas = _deltas(ordered)
    origin = started_at_ms if started_at_ms is not None else (ordered[0] if ordered else 0.0)

    events: list[JankEvent] = []
    dropped_total = 0
    previous = ordered[0] if ordered else 0.0
    for current in ordered[1:]:
        delta = current - previous
        if delta > 0:
            dropped = frame_slots(delta, refresh_interval_ms) - 1
            if dropped > 0:
                dropped_total += dropped
                events.append(
                    JankEvent(
                        timestamp_ms=previous - origin,
                        frame_delta_ms=delta,
                        dropped_frames=dropped,
                        severity=classify_severity(dropped),
                    )
                )
        previous = current

    if ordered:
        edges: list[tuple[float, float]] = []
        if started_at_ms is not None and ordered[0] > started_at_ms:
            edges.append((started_at_ms, ordered[0]))
        if stopped_at_ms is not None and stopped_at_ms > ordered[-1]:
            edges.append((ordered[-1], stopped_at_ms))
        for begin, end in edges:
            dropped = frame_slots(end - begin, refresh_interval_ms) - 1
            if dropped > 0:
                dropped_total += dropped
                events.append(
                    JankEvent(
                        timestamp_ms=begin - origin,
                        frame_delta_ms=end - begin,
                        dropped_frames=dropped,
                        severity=classify_severity(dropped),
                    )
                )
        events.sort(key=lambda e: e.timestamp_ms)

    presented = len(deltas)
    expected = presented + dropped_total
    first = started_at_ms if started_at_ms is not None and ordered else None
    last = stopped_at_ms if stopped_at_ms is not None and ordered else None
    window_start = min(first, ordered[0]) if first is not None else (ordered[0] if ordered else 0.0)
    window_end = max(last, ordered[-1]) if last is not None else (ordered[-1] if ordered else 0.0)
    duration = window_end - window_start if len(ordered) > 1 else 0.0
    sorted_deltas = sorted(deltas)

    all_notes = list(notes)
    if presented == 0:
        all_notes.append(
            "No frames were measured: the page may be hidden, throttled, or closed "
            "before the measurement window ended."
        )

    return FrameTimingResult(
        refresh_interval_ms=refresh_interval_ms,
        refresh_source=refresh_source,
        duration_ms=duration,
        frames_presented=presented,
        frames_expected=expected,
        dropped_frames=dropped_total,
        jank_percentage=(100.0 * dropped_total / expected) if expected else 0.0,
        average_fps=(1000.0 * presented / duration) if duration > 0 else 0.0,
        p50_frame_ms=_percentile(sorted_deltas, 50),
        p95_frame_ms=_percentile(sorted_deltas, 95),
        p99_frame_ms=_percentile(sorted_deltas, 99),
        max_frame_ms=float(sorted_deltas[-1]) if sorted_deltas else 0.0,
        jank_events=tuple(events),
        long_animation_frames=tuple(long_animation_frames),
        loaf_supported=loaf_supported,
        compositor=compositor,
        notes=tuple(all_notes),
    )


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

_SOURCE_LABEL: dict[str, str] = {
    "configured": "configured",
    "calibrated": "measured on a blank page in the same browser",
    "estimated": "estimated from the page's own frames",
    "assumed": "assumed (60 Hz); measurement failed",
}


def generate_fps_report(result: FrameTimingResult, max_events: int = 10) -> str:
    """Render a frame timing result as Markdown."""
    lines = [
        "# Frame Timing Report",
        "",
        (
            "Measured inside the page (requestAnimationFrame and Long Animation Frames), "
            "not from the video recording."
        ),
        "",
        "## Summary",
        f"- **Verdict**: {result.verdict}",
        f"- **Dropped frames**: {result.dropped_frames} of {result.frames_expected} "
        f"({result.jank_percentage:.1f}%)",
        f"- **Refresh rate**: {result.refresh_rate_hz:.1f} Hz "
        f"({result.refresh_interval_ms:.2f} ms, {_SOURCE_LABEL[result.refresh_source]})",
        f"- **Main-thread frames**: {result.frames_presented} in "
        f"{result.duration_ms / 1000:.2f}s (average {result.average_fps:.1f} fps)",
        f"- **Frame time**: p50 {result.p50_frame_ms:.1f} ms, p95 {result.p95_frame_ms:.1f} ms, "
        f"p99 {result.p99_frame_ms:.1f} ms, max {result.max_frame_ms:.1f} ms",
    ]

    if result.compositor is None and result.dropped_frames > 0:
        lines.append(
            "- **Note**: these are main-thread frames. A CSS transform or opacity "
            "animation runs on the compositor and may still look smooth; measure with "
            "`trace_compositor=True` to see the frames users saw."
        )

    if result.compositor is not None:
        c = result.compositor
        lines.extend(
            [
                "",
                "## Compositor frames (Chromium trace)",
                f"- **Presented in full**: {c.presented_all}",
                f"- **Presented without the main thread's update**: {c.presented_partial} "
                f"({c.partial_percentage:.1f}%)",
                f"- **Dropped**: {c.dropped} ({c.dropped_percentage:.1f}%)",
                (
                    "- A transform or opacity animation runs on the compositor and can stay "
                    "smooth while the main thread drops frames."
                ),
            ]
        )

    lines.extend(["", "## Long animation frames"])
    if not result.loaf_supported:
        lines.append("- Not available in this browser (needs Chromium 123 or later).")
    elif not result.long_animation_frames:
        lines.append("- None over 50 ms.")
    else:
        worst = sorted(result.long_animation_frames, key=lambda f: f.duration_ms, reverse=True)
        for frame in worst[:max_events]:
            culprit = ""
            if frame.scripts:
                top = max(frame.scripts, key=lambda s: s.duration_ms)
                where = top.source_url or "inline script"
                name = f" {top.function_name}" if top.function_name else ""
                culprit = f" - {top.invoker}{name} ({where}, {top.duration_ms:.0f} ms)"
            lines.append(
                f"- @ {frame.start_ms:.0f} ms: {frame.duration_ms:.0f} ms "
                f"(blocking {frame.blocking_duration_ms:.0f} ms){culprit}"
            )
        if len(worst) > max_events:
            lines.append(f"- ... and {len(worst) - max_events} more")

    lines.extend(["", "## Jank events"])
    if not result.jank_events:
        lines.append("- None.")
    else:
        worst_events = sorted(result.jank_events, key=lambda e: e.frame_delta_ms, reverse=True)
        for event in worst_events[:max_events]:
            lines.append(
                f"- @ {event.timestamp_ms:.0f} ms: {event.frame_delta_ms:.1f} ms frame, "
                f"{event.dropped_frames} dropped [{event.severity}]"
            )
        if len(worst_events) > max_events:
            lines.append(f"- ... and {len(worst_events) - max_events} more")

    if result.notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in result.notes)

    return "\n".join(lines)
