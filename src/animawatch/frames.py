"""Video frame extraction and sampling for efficient analysis.

This module provides utilities to extract key frames from videos,
enabling efficient analysis by skipping redundant frames.
"""

import asyncio
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass
class ExtractedFrame:
    """A single extracted frame from a video."""

    path: Path
    timestamp_ms: int
    frame_number: int
    content_hash: str


@dataclass
class FrameExtractionResult:
    """Result of frame extraction from a video."""

    frames: list[ExtractedFrame]
    total_frames: int
    duration_ms: int
    fps: float


async def extract_frames(
    video_path: Path,
    interval_ms: int = 1000,
    max_frames: int = 10,
    output_dir: Path | None = None,
    skip_similar: bool = True,
    similarity_threshold: float = 0.95,
) -> FrameExtractionResult:
    """Extract frames from a video at specified intervals.

    Args:
        video_path: Path to the video file
        interval_ms: Extract one frame every N milliseconds (default 1000ms = 1fps)
        max_frames: Maximum number of frames to extract (default 10)
        output_dir: Directory to save frames (default: temp directory)
        skip_similar: Skip frames that are too similar to the previous (default True)
        similarity_threshold: Threshold for similarity detection 0-1 (default 0.95)

    Returns:
        FrameExtractionResult containing extracted frames and metadata
    """
    # Use temp directory if not specified
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="animawatch_frames_"))
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Try to use ffmpeg for frame extraction
    frames = await _extract_with_ffmpeg(video_path, output_dir, interval_ms, max_frames)

    # If ffmpeg is not available, fall back to imageio
    if not frames:
        frames = await _extract_with_imageio(video_path, output_dir, interval_ms, max_frames)

    # Filter similar frames if requested
    if skip_similar and len(frames) > 1:
        frames = _filter_similar_frames(frames, similarity_threshold)

    # Calculate video metadata
    total_duration_ms = frames[-1].timestamp_ms if frames else 0
    fps = 1000.0 / interval_ms if interval_ms > 0 else 1.0

    return FrameExtractionResult(
        frames=frames,
        total_frames=len(frames),
        duration_ms=total_duration_ms,
        fps=fps,
    )


async def _extract_with_ffmpeg(
    video_path: Path,
    output_dir: Path,
    interval_ms: int,
    max_frames: int,
) -> list[ExtractedFrame]:
    """Extract frames using ffmpeg (preferred, faster)."""
    try:
        # Calculate fps from interval
        fps = 1000.0 / interval_ms if interval_ms > 0 else 1.0

        # Build ffmpeg command
        output_pattern = output_dir / "frame_%04d.png"
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vf",
            f"fps={fps}",
            "-frames:v",
            str(max_frames),
            "-y",  # Overwrite output files
            str(output_pattern),
        ]

        # Run ffmpeg
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        if proc.returncode != 0:
            return []

        # Collect extracted frames
        frames = []
        for i, frame_path in enumerate(sorted(output_dir.glob("frame_*.png"))):
            timestamp_ms = i * interval_ms
            content_hash = _hash_image(frame_path)
            frames.append(
                ExtractedFrame(
                    path=frame_path,
                    timestamp_ms=timestamp_ms,
                    frame_number=i,
                    content_hash=content_hash,
                )
            )
            if len(frames) >= max_frames:
                break

        return frames

    except FileNotFoundError:
        # ffmpeg not installed
        return []


async def _extract_with_imageio(
    video_path: Path,
    output_dir: Path,
    interval_ms: int,
    max_frames: int,
) -> list[ExtractedFrame]:
    """Extract frames using imageio (fallback, pure Python)."""
    try:
        import imageio.v3 as iio

        frames = []
        # Read video metadata
        props = iio.improps(video_path, plugin="pyav")
        fps = props.fps if hasattr(props, "fps") else 30.0
        frame_interval = max(1, int(fps * interval_ms / 1000))

        frame_count = 0
        for i, frame_data in enumerate(iio.imiter(video_path, plugin="pyav")):
            if i % frame_interval != 0:
                continue

            # Save frame as PNG
            frame_path = output_dir / f"frame_{frame_count:04d}.png"
            img = Image.fromarray(frame_data)
            img.save(frame_path)

            timestamp_ms = int(i * 1000 / fps)
            content_hash = _hash_image(frame_path)

            frames.append(
                ExtractedFrame(
                    path=frame_path,
                    timestamp_ms=timestamp_ms,
                    frame_number=frame_count,
                    content_hash=content_hash,
                )
            )

            frame_count += 1
            if frame_count >= max_frames:
                break

        return frames

    except ImportError:
        # imageio not installed, return empty
        return []


def _hash_image(image_path: Path) -> str:
    """Compute a content hash for an image."""
    with open(image_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()  # noqa: S324


def _filter_similar_frames(
    frames: list[ExtractedFrame],
    threshold: float = 0.95,
) -> list[ExtractedFrame]:
    """Filter out frames that are too similar to the previous frame.

    Uses perceptual hashing for similarity detection.
    """
    if not frames:
        return frames

    try:
        import imagehash

        result = [frames[0]]  # Always keep first frame
        prev_hash = imagehash.average_hash(Image.open(frames[0].path))

        for frame in frames[1:]:
            curr_hash = imagehash.average_hash(Image.open(frame.path))
            # Calculate similarity (0 = identical, higher = more different)
            diff = curr_hash - prev_hash
            similarity = 1.0 - (diff / 64.0)  # Normalize to 0-1

            if similarity < threshold:
                result.append(frame)
                prev_hash = curr_hash

        return result

    except ImportError:
        # imagehash not installed, use content hash comparison
        result = [frames[0]]
        prev_hash = frames[0].content_hash

        for frame in frames[1:]:
            if frame.content_hash != prev_hash:
                result.append(frame)
                prev_hash = frame.content_hash

        return result


async def cleanup_frames(extraction_result: FrameExtractionResult) -> None:
    """Clean up extracted frame files."""
    import contextlib

    for frame in extraction_result.frames:
        with contextlib.suppress(OSError):
            frame.path.unlink()

    # Try to remove the parent directory if empty
    if extraction_result.frames:
        parent = extraction_result.frames[0].path.parent
        with contextlib.suppress(OSError):
            parent.rmdir()
