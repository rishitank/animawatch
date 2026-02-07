"""Visual diff detection for comparing before/after screenshots.

This module provides utilities to compare screenshots pixel-by-pixel
and highlight visual differences for regression detection.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


@dataclass
class DiffRegion:
    """A region where visual differences were detected."""

    x: int
    y: int
    width: int
    height: int
    difference_score: float  # 0-100, how different this region is


@dataclass
class VisualDiffResult:
    """Result of visual diff comparison."""

    has_differences: bool
    overall_similarity: float  # 0-100, 100 = identical
    diff_percentage: float  # Percentage of pixels that differ
    diff_regions: list[DiffRegion]
    diff_image_path: Path | None  # Path to generated diff image
    before_path: Path
    after_path: Path


def compare_images(
    before_path: Path,
    after_path: Path,
    threshold: int = 10,
    output_diff: bool = True,
    highlight_color: tuple[int, int, int, int] = (255, 0, 0, 128),
) -> VisualDiffResult:
    """Compare two images and detect visual differences.

    Args:
        before_path: Path to the "before" image
        after_path: Path to the "after" image
        threshold: Pixel difference threshold (0-255). Higher = more tolerant
        output_diff: If True, generate a diff image highlighting changes
        highlight_color: RGBA color for highlighting differences

    Returns:
        VisualDiffResult with comparison metrics and diff image
    """
    # Load images
    before = Image.open(before_path).convert("RGBA")
    after = Image.open(after_path).convert("RGBA")

    # Resize if dimensions don't match (use "before" as reference)
    if before.size != after.size:
        after = after.resize(before.size, Image.Resampling.LANCZOS)

    # Calculate pixel-by-pixel difference
    diff = ImageChops.difference(before, after)

    # Convert to grayscale for analysis
    diff_gray = diff.convert("L")

    # Count different pixels (above threshold)
    total_pixels = before.size[0] * before.size[1]
    diff_pixels = 0
    diff_sum = 0

    # Get pixel data as a flat list for grayscale image
    pixel_data = diff_gray.tobytes()
    for pixel_value in pixel_data:
        # For grayscale ("L" mode), pixels are single int values
        pixel_diff = int(pixel_value)
        diff_sum += pixel_diff
        if pixel_diff > threshold:
            diff_pixels += 1

    diff_percentage = (diff_pixels / total_pixels) * 100
    overall_similarity = 100.0 - (diff_sum / (total_pixels * 255) * 100)

    # Find diff regions using bounding boxes
    diff_regions = _find_diff_regions(diff_gray, threshold)

    # Generate diff image if requested
    diff_image_path: Path | None = None
    if output_diff and diff_pixels > 0:
        diff_image_path = _generate_diff_image(before, after, diff_gray, threshold, highlight_color)

    return VisualDiffResult(
        has_differences=diff_pixels > 0,
        overall_similarity=overall_similarity,
        diff_percentage=diff_percentage,
        diff_regions=diff_regions,
        diff_image_path=diff_image_path,
        before_path=before_path,
        after_path=after_path,
    )


def _find_diff_regions(
    diff_gray: Image.Image,
    threshold: int,
    min_region_size: int = 10,
) -> list[DiffRegion]:
    """Find contiguous regions of difference."""
    # Convert to binary (above/below threshold)
    binary = diff_gray.point(lambda p: 255 if p > threshold else 0)

    # Get bounding box of all differences
    bbox = binary.getbbox()
    if bbox is None:
        return []

    # For simplicity, return one region covering all differences
    # More sophisticated implementations could use connected component analysis
    x, y, x2, y2 = bbox
    width = x2 - x
    height = y2 - y

    if width < min_region_size and height < min_region_size:
        return []

    # Calculate region difference score
    region = diff_gray.crop(bbox)
    pixels = region.tobytes()
    avg_diff = sum(pixels) / len(pixels) if pixels else 0
    difference_score = (avg_diff / 255) * 100

    return [
        DiffRegion(
            x=x,
            y=y,
            width=width,
            height=height,
            difference_score=difference_score,
        )
    ]


def _generate_diff_image(
    before: Image.Image,
    after: Image.Image,
    diff_gray: Image.Image,
    threshold: int,
    highlight_color: tuple[int, int, int, int],
) -> Path:
    """Generate a diff image with highlighted changes."""
    # Create a copy of the "after" image
    result = after.copy()

    # Create an overlay for highlighting
    overlay = Image.new("RGBA", result.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Highlight differing pixels using getpixel for type safety
    for x in range(diff_gray.width):
        for y in range(diff_gray.height):
            pixel_value = diff_gray.getpixel((x, y))
            if isinstance(pixel_value, int) and pixel_value > threshold:
                draw.point((x, y), fill=highlight_color)

    # Composite the overlay onto the result
    result = Image.alpha_composite(result.convert("RGBA"), overlay)

    # Save to temp file
    fd, tmp_path = tempfile.mkstemp(suffix="_diff.png")
    import os

    os.close(fd)
    result.save(tmp_path)

    return Path(tmp_path)


def compare_screenshots_batch(
    pairs: list[tuple[Path, Path]],
    threshold: int = 10,
) -> list[VisualDiffResult]:
    """Compare multiple pairs of screenshots.

    Args:
        pairs: List of (before_path, after_path) tuples
        threshold: Pixel difference threshold

    Returns:
        List of VisualDiffResult for each pair
    """
    results = []
    for before_path, after_path in pairs:
        result = compare_images(before_path, after_path, threshold=threshold)
        results.append(result)
    return results
