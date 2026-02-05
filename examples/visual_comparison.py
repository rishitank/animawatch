#!/usr/bin/env python3
"""Example: Visual Comparison / Regression Testing with AnimaWatch.

This example demonstrates how to compare screenshots between two URLs
or before/after states to detect visual regressions.
"""

import asyncio
from pathlib import Path

from animawatch.browser import BrowserRecorder
from animawatch.config import settings


async def compare_pages(
    url1: str,
    url2: str,
    *,
    names: tuple[str, str] = ("Page 1", "Page 2"),
) -> str:
    """Compare two URLs for visual differences.

    Args:
        url1: First URL (baseline)
        url2: Second URL (comparison)
        names: Display names for the pages

    Returns:
        The comparison analysis result
    """
    browser = BrowserRecorder()
    # Note: We use the genai client directly for multi-image comparison
    # since the standard VisionProvider.analyze_image only handles single images
    screenshot1: Path | None = None
    screenshot2: Path | None = None

    try:
        await browser.start()

        # Capture both screenshots
        print(f"📸 Capturing {names[0]}: {url1}")
        screenshot1 = await browser.take_screenshot(url1, full_page=True)

        print(f"📸 Capturing {names[1]}: {url2}")
        screenshot2 = await browser.take_screenshot(url2, full_page=True)

        # Read both images and send to vision AI for comparison
        with open(screenshot1, "rb") as f:
            img1_data = f.read()
        with open(screenshot2, "rb") as f:
            img2_data = f.read()

        # Use the vision provider to compare (Gemini supports multi-image)
        prompt = f"""You are a visual regression testing expert. Compare these two screenshots:

**{names[0]}** (First image) - The baseline/expected state
**{names[1]}** (Second image) - The current/comparison state

Identify ANY visual differences:

1. **Layout Changes**
   - Element positions moved
   - Size differences
   - Missing or new elements

2. **Style Changes**
   - Color differences
   - Font changes
   - Border/shadow differences

3. **Content Changes**
   - Text differences
   - Image changes
   - Data changes

4. **Responsiveness Issues**
   - Alignment problems
   - Overflow issues
   - Spacing inconsistencies

For each difference found:
- **Location**: Where on the page
- **Type**: Category of change
- **Severity**: Breaking / Major / Minor / Cosmetic
- **Description**: What changed

If the pages are identical, confirm that no visual regressions were detected."""

        # For Gemini, we can analyze both images together
        from google import genai
        from google.genai import types

        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY required for comparison")

        client = genai.Client(api_key=settings.gemini_api_key)

        contents: list[types.Part] = [
            types.Part.from_bytes(data=img1_data, mime_type="image/png"),
            types.Part.from_bytes(data=img2_data, mime_type="image/png"),
            types.Part.from_text(text=prompt),
        ]

        response = await client.aio.models.generate_content(
            model=settings.vision_model,
            contents=contents,  # type: ignore[arg-type]
        )

        return str(response.text) if response.text else ""

    finally:
        # Clean up screenshots
        if screenshot1 is not None and screenshot1.exists():
            screenshot1.unlink()
        if screenshot2 is not None and screenshot2.exists():
            screenshot2.unlink()
        await browser.stop()


async def main() -> None:
    """Run the visual comparison example."""
    # Example: Compare production vs staging
    url_baseline = "https://example.com"
    url_comparison = "https://example.org"

    print("=" * 60)
    print("🔍 AnimaWatch - Visual Comparison Example")
    print("=" * 60)
    print()
    print(f"Baseline: {url_baseline}")
    print(f"Comparison: {url_comparison}")
    print(f"Vision Provider: {settings.vision_provider}")
    print()

    try:
        result = await compare_pages(
            url_baseline,
            url_comparison,
            names=("Baseline", "Comparison"),
        )
        print()
        print("=" * 60)
        print("📊 COMPARISON RESULT")
        print("=" * 60)
        print(result)
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
