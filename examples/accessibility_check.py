#!/usr/bin/env python3
"""Example: Accessibility Check with AnimaWatch.

This example demonstrates how to use AnimaWatch to check
a webpage for visual accessibility issues like color contrast,
readability, and touch target sizes.
"""

import asyncio

from animawatch.browser import BrowserRecorder
from animawatch.config import settings
from animawatch.vision import get_vision_provider


async def check_accessibility(url: str) -> str:
    """Check a webpage for visual accessibility issues.

    Args:
        url: The webpage URL to check

    Returns:
        The accessibility analysis result
    """
    from pathlib import Path

    browser = BrowserRecorder()
    vision = get_vision_provider()
    screenshot_path: Path | None = None

    try:
        await browser.start()

        # Take full-page screenshot
        print(f"📸 Capturing {url}...")
        screenshot_path = await browser.take_screenshot(url, full_page=True)

        # Analyze for accessibility
        print("♿ Checking accessibility...")
        prompt = """You are an accessibility expert reviewing a webpage.

Check for these visual accessibility issues:

1. **Color Contrast**
   - Text/background contrast ratios
   - Low contrast UI elements

2. **Text Readability**
   - Font sizes (minimum 16px for body)
   - Line height and spacing
   - Font weight and clarity

3. **Touch Targets**
   - Button/link sizes (minimum 44x44px)
   - Spacing between interactive elements

4. **Focus Indicators**
   - Visible focus states
   - Skip links

5. **Visual Hierarchy**
   - Heading structure clarity
   - Information organization

6. **Motion Concerns**
   - Animations that could cause vestibular issues
   - Flashing content

Rate overall accessibility (A, AA, AAA, or Failing) and provide specific recommendations.
"""

        analysis = await vision.analyze_image(screenshot_path, prompt)

        return str(analysis)

    finally:
        # Clean up temp screenshot
        if screenshot_path is not None and screenshot_path.exists():
            screenshot_path.unlink()
        await browser.stop()


async def main() -> None:
    """Run the example."""
    url = "https://example.com"

    print("=" * 60)
    print("♿ AnimaWatch - Accessibility Check Example")
    print("=" * 60)
    print()
    print(f"URL: {url}")
    print(f"Vision Provider: {settings.vision_provider}")
    print()

    try:
        result = await check_accessibility(url)
        print()
        print("=" * 60)
        print("📊 ACCESSIBILITY REPORT")
        print("=" * 60)
        print(result)
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
