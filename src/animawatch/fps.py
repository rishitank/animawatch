"""Animation FPS analysis for detecting frame drops and jank.

This module provides utilities to analyze video recordings for
performance issues like frame drops, stutter, and animation jank.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FrameTimingInfo:
    """Timing information for a single frame."""

    frame_number: int
    timestamp_ms: float
    delta_ms: float  # Time since previous frame


@dataclass
class JankEvent:
    """A detected jank or frame drop event."""

    frame_number: int
    timestamp_ms: float
    expected_delta_ms: float
    actual_delta_ms: float
    severity: str  # "minor", "major", "severe"
    dropped_frames: int


@dataclass
class FPSAnalysisResult:
    """Result of FPS and jank analysis."""

    average_fps: float
    target_fps: float
    min_fps: float
    max_fps: float
    total_frames: int
    jank_events: list[JankEvent]
    jank_percentage: float  # Percentage of frames with jank
    frame_time_consistency: float  # 0-100, higher = more consistent
    duration_ms: float


async def analyze_video_fps(
    video_path: Path,
    target_fps: float = 60.0,
    jank_threshold_ms: float = 5.0,
) -> FPSAnalysisResult:
    """Analyze a video for FPS consistency and jank.

    Args:
        video_path: Path to the video file
        target_fps: Expected FPS (default 60)
        jank_threshold_ms: Frame time deviation threshold for jank detection

    Returns:
        FPSAnalysisResult with FPS metrics and jank events
    """
    # Extract frame timings using ffprobe
    frame_timings = await _extract_frame_timings(video_path)

    if len(frame_timings) < 2:
        return FPSAnalysisResult(
            average_fps=0.0,
            target_fps=target_fps,
            min_fps=0.0,
            max_fps=0.0,
            total_frames=len(frame_timings),
            jank_events=[],
            jank_percentage=0.0,
            frame_time_consistency=100.0,
            duration_ms=0.0,
        )

    # Calculate FPS metrics
    expected_delta = 1000.0 / target_fps
    deltas = [f.delta_ms for f in frame_timings if f.delta_ms > 0]

    avg_delta = expected_delta if not deltas else sum(deltas) / len(deltas)

    average_fps = 1000.0 / avg_delta if avg_delta > 0 else 0.0
    min_delta = min(deltas) if deltas else expected_delta
    max_delta = max(deltas) if deltas else expected_delta
    max_fps = 1000.0 / min_delta if min_delta > 0 else 0.0
    min_fps = 1000.0 / max_delta if max_delta > 0 else 0.0

    # Detect jank events
    jank_events = []
    for frame in frame_timings:
        if frame.delta_ms <= 0:
            continue

        deviation = abs(frame.delta_ms - expected_delta)
        if deviation > jank_threshold_ms:
            # Determine severity
            if deviation > expected_delta * 2:
                severity = "severe"
                dropped = int(frame.delta_ms / expected_delta) - 1
            elif deviation > expected_delta:
                severity = "major"
                dropped = 1
            else:
                severity = "minor"
                dropped = 0

            jank_events.append(
                JankEvent(
                    frame_number=frame.frame_number,
                    timestamp_ms=frame.timestamp_ms,
                    expected_delta_ms=expected_delta,
                    actual_delta_ms=frame.delta_ms,
                    severity=severity,
                    dropped_frames=dropped,
                )
            )

    # Calculate jank percentage
    jank_percentage = (len(jank_events) / len(frame_timings)) * 100

    # Calculate frame time consistency
    variance = sum((d - avg_delta) ** 2 for d in deltas) / len(deltas) if deltas else 0
    std_dev = variance**0.5
    consistency = max(0.0, 100.0 - (std_dev / expected_delta * 100))

    total_duration = frame_timings[-1].timestamp_ms if frame_timings else 0.0

    return FPSAnalysisResult(
        average_fps=average_fps,
        target_fps=target_fps,
        min_fps=min_fps,
        max_fps=max_fps,
        total_frames=len(frame_timings),
        jank_events=jank_events,
        jank_percentage=jank_percentage,
        frame_time_consistency=consistency,
        duration_ms=total_duration,
    )


async def _extract_frame_timings(video_path: Path) -> list[FrameTimingInfo]:
    """Extract frame timestamps from video using ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "frame=pts_time",
            "-of",
            "csv=p=0",
            str(video_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        if proc.returncode != 0:
            return []

        # Parse frame timestamps
        lines = stdout.decode().strip().split("\n")
        frame_timings = []
        prev_timestamp = 0.0

        for i, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                timestamp_sec = float(line.strip())
                timestamp_ms = timestamp_sec * 1000
                delta_ms = timestamp_ms - prev_timestamp if i > 0 else 0.0

                frame_timings.append(
                    FrameTimingInfo(
                        frame_number=i,
                        timestamp_ms=timestamp_ms,
                        delta_ms=delta_ms,
                    )
                )
                prev_timestamp = timestamp_ms
            except ValueError:
                continue

        return frame_timings

    except FileNotFoundError:
        # ffprobe not installed, return empty
        return []


def generate_fps_report(result: FPSAnalysisResult) -> str:
    """Generate a human-readable FPS analysis report."""
    lines = [
        "# FPS Analysis Report",
        "",
        "## Summary",
        f"- **Average FPS**: {result.average_fps:.1f} (target: {result.target_fps})",
        f"- **FPS Range**: {result.min_fps:.1f} - {result.max_fps:.1f}",
        f"- **Total Frames**: {result.total_frames}",
        f"- **Duration**: {result.duration_ms / 1000:.2f}s",
        f"- **Frame Time Consistency**: {result.frame_time_consistency:.1f}%",
        "",
        "## Jank Analysis",
        f"- **Jank Events**: {len(result.jank_events)}",
        f"- **Jank Percentage**: {result.jank_percentage:.2f}%",
    ]

    if result.jank_events:
        lines.extend(["", "### Jank Events"])
        for event in result.jank_events[:10]:  # Show first 10
            lines.append(
                f"- Frame {event.frame_number} @ {event.timestamp_ms:.0f}ms: "
                f"{event.actual_delta_ms:.1f}ms (expected {event.expected_delta_ms:.1f}ms) "
                f"[{event.severity}]"
            )
        if len(result.jank_events) > 10:
            lines.append(f"- ... and {len(result.jank_events) - 10} more events")

    return "\n".join(lines)
