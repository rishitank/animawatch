"""Tests for frame extraction in animawatch.frames."""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from animawatch.frames import (
    ExtractedFrame,
    FrameExtractionResult,
    cleanup_frames,
)


class TestExtractedFrame:
    """Tests for ExtractedFrame dataclass."""

    def test_extracted_frame_creation(self) -> None:
        """Test creating an extracted frame."""
        frame = ExtractedFrame(
            path=Path("/tmp/frame_001.png"),
            timestamp_ms=1000,
            frame_number=1,
            content_hash="abc123",
        )
        assert frame.path == Path("/tmp/frame_001.png")
        assert frame.timestamp_ms == 1000
        assert frame.frame_number == 1
        assert frame.content_hash == "abc123"


class TestFrameExtractionResult:
    """Tests for FrameExtractionResult dataclass."""

    def test_result_creation(self) -> None:
        """Test creating a frame extraction result."""
        frames = [
            ExtractedFrame(Path("/tmp/f1.png"), 0, 0, "hash1"),
            ExtractedFrame(Path("/tmp/f2.png"), 1000, 1, "hash2"),
        ]
        result = FrameExtractionResult(
            frames=frames,
            total_frames=2,
            duration_ms=1000,
            fps=1.0,
        )
        assert len(result.frames) == 2
        assert result.total_frames == 2
        assert result.duration_ms == 1000
        assert result.fps == 1.0

    def test_empty_result(self) -> None:
        """Test empty frame extraction result."""
        result = FrameExtractionResult(
            frames=[],
            total_frames=0,
            duration_ms=0,
            fps=1.0,
        )
        assert len(result.frames) == 0


class TestCleanupFrames:
    """Tests for cleanup_frames function."""

    @pytest.mark.asyncio
    async def test_cleanup_deletes_frames(self) -> None:
        """Test that cleanup removes frame files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create test frame files
            frame_paths = []
            for i in range(3):
                frame_path = tmppath / f"frame_{i:04d}.png"
                img = Image.new("RGB", (100, 100), color="red")
                img.save(frame_path)
                frame_paths.append(frame_path)

            frames = [
                ExtractedFrame(path, i * 1000, i, f"hash{i}") for i, path in enumerate(frame_paths)
            ]
            result = FrameExtractionResult(
                frames=frames,
                total_frames=3,
                duration_ms=2000,
                fps=1.0,
            )

            # Verify files exist
            for path in frame_paths:
                assert path.exists()

            # Cleanup
            await cleanup_frames(result)

            # Verify files are deleted
            for path in frame_paths:
                assert not path.exists()

    @pytest.mark.asyncio
    async def test_cleanup_empty_result(self) -> None:
        """Test cleanup with empty result doesn't fail."""
        result = FrameExtractionResult(frames=[], total_frames=0, duration_ms=0, fps=1.0)
        await cleanup_frames(result)  # Should not raise
