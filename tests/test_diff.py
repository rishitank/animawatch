"""Tests for visual diff detection in animawatch.diff."""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from animawatch.diff import (
    DiffRegion,
    compare_images,
    compare_screenshots_batch,
)


@pytest.fixture
def identical_images() -> tuple[Path, Path]:
    """Create two identical test images."""
    img = Image.new("RGB", (100, 100), color="red")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1:
        img.save(f1.name)
        path1 = Path(f1.name)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
        img.save(f2.name)
        path2 = Path(f2.name)
    yield path1, path2
    path1.unlink(missing_ok=True)
    path2.unlink(missing_ok=True)


@pytest.fixture
def different_images() -> tuple[Path, Path]:
    """Create two different test images."""
    img1 = Image.new("RGB", (100, 100), color="red")
    img2 = Image.new("RGB", (100, 100), color="blue")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1:
        img1.save(f1.name)
        path1 = Path(f1.name)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
        img2.save(f2.name)
        path2 = Path(f2.name)
    yield path1, path2
    path1.unlink(missing_ok=True)
    path2.unlink(missing_ok=True)


@pytest.fixture
def partially_different_images() -> tuple[Path, Path]:
    """Create images with partial differences."""
    img1 = Image.new("RGB", (100, 100), color="white")
    img2 = Image.new("RGB", (100, 100), color="white")
    # Add a red square to img2
    for x in range(20, 40):
        for y in range(20, 40):
            img2.putpixel((x, y), (255, 0, 0))
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1:
        img1.save(f1.name)
        path1 = Path(f1.name)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
        img2.save(f2.name)
        path2 = Path(f2.name)
    yield path1, path2
    path1.unlink(missing_ok=True)
    path2.unlink(missing_ok=True)


class TestDiffRegion:
    """Tests for DiffRegion dataclass."""

    def test_diff_region_creation(self) -> None:
        """Test creating a diff region."""
        region = DiffRegion(x=10, y=20, width=50, height=30, difference_score=75.0)
        assert region.x == 10
        assert region.y == 20
        assert region.width == 50
        assert region.height == 30
        assert region.difference_score == 75.0


class TestCompareImages:
    """Tests for compare_images function."""

    def test_identical_images(self, identical_images: tuple[Path, Path]) -> None:
        """Test comparing identical images."""
        before, after = identical_images
        result = compare_images(before, after, output_diff=False)
        assert result.has_differences is False
        assert result.overall_similarity == 100.0
        assert result.diff_percentage == 0.0
        assert len(result.diff_regions) == 0

    def test_completely_different_images(self, different_images: tuple[Path, Path]) -> None:
        """Test comparing completely different images."""
        before, after = different_images
        result = compare_images(before, after, output_diff=False)
        assert result.has_differences is True
        assert result.overall_similarity < 100.0  # Should be less than identical
        assert result.diff_percentage > 0.0  # Should have differences

    def test_partial_differences(self, partially_different_images: tuple[Path, Path]) -> None:
        """Test comparing partially different images."""
        before, after = partially_different_images
        result = compare_images(before, after, output_diff=False)
        assert result.has_differences is True
        assert result.overall_similarity > 90.0  # Most is same
        assert result.diff_percentage < 10.0  # Small region differs

    def test_diff_image_generation(self, different_images: tuple[Path, Path]) -> None:
        """Test that diff image is generated."""
        before, after = different_images
        result = compare_images(before, after, output_diff=True)
        assert result.diff_image_path is not None
        assert result.diff_image_path.exists()
        result.diff_image_path.unlink(missing_ok=True)

    def test_result_paths(self, identical_images: tuple[Path, Path]) -> None:
        """Test that result contains correct paths."""
        before, after = identical_images
        result = compare_images(before, after, output_diff=False)
        assert result.before_path == before
        assert result.after_path == after


class TestCompareScreenshotsBatch:
    """Tests for compare_screenshots_batch function."""

    def test_batch_comparison(
        self, identical_images: tuple[Path, Path], different_images: tuple[Path, Path]
    ) -> None:
        """Test comparing multiple pairs."""
        pairs = [identical_images, different_images]
        results = compare_screenshots_batch(pairs, threshold=10)
        assert len(results) == 2
        assert results[0].has_differences is False
        assert results[1].has_differences is True

    def test_empty_batch(self) -> None:
        """Test with empty batch."""
        results = compare_screenshots_batch([])
        assert results == []
