"""Tests for visual diff detection in animawatch.diff."""

import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageChops

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

    @pytest.mark.parametrize(
        "highlight_color", [(0, 0, 255, 255), (255, 0, 0, 128)], ids=["opaque", "translucent"]
    )
    def test_diff_image_highlights_exactly_pixels_above_threshold(
        self, tmp_path: Path, highlight_color: tuple[int, int, int, int]
    ) -> None:
        """The diff image is the "after" image with only above-threshold pixels overlaid."""
        threshold = 5
        before = Image.new("RGB", (50, 50), "white")
        after = before.copy()
        after.paste((255, 0, 0), (10, 10, 20, 20))  # strong difference
        after.paste((250, 250, 250), (30, 30, 40, 40))  # grey diff of exactly `threshold`
        before_path, after_path = tmp_path / "before.png", tmp_path / "after.png"
        before.save(before_path)
        after.save(after_path)

        result = compare_images(
            before_path, after_path, threshold=threshold, highlight_color=highlight_color
        )
        assert result.diff_image_path is not None
        try:
            actual = Image.open(result.diff_image_path).convert("RGBA")

            # Reference: overlay the highlight pixel by pixel wherever the grayscale
            # difference is strictly greater than the threshold.
            diff_gray = ImageChops.difference(before, after).convert("L")
            overlay = Image.new("RGBA", after.size, (0, 0, 0, 0))
            for x in range(after.width):
                for y in range(after.height):
                    value = diff_gray.getpixel((x, y))
                    if isinstance(value, int) and value > threshold:
                        overlay.putpixel((x, y), highlight_color)
            expected = Image.alpha_composite(after.convert("RGBA"), overlay)

            assert actual.tobytes() == expected.tobytes()
            assert actual.getpixel((35, 35)) == (250, 250, 250, 255)  # at threshold: untouched
            assert actual.getpixel((0, 0)) == (255, 255, 255, 255)  # unchanged: untouched
        finally:
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
