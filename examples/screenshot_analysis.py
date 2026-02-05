#!/usr/bin/env python3
"""Example: Screenshot Analysis with AnimaWatch.

This example demonstrates how to take screenshots and analyze them
for visual issues like layout problems, color contrast, and typography.
"""

import asyncio

from animawatch.browser import BrowserRecorder
from animawatch.config import settings
from animawatch.vision import get_vision_provider


async def analyze_screenshot(
    url: str,
    full_page: bool = True,
    focus: str = "layout, colors, typography",
) -> str:
    """Take a screenshot and analyze it for visual issues.

    Args:
        url: The webpage URL to analyze
        full_page: Whether to capture the full scrollable page
        focus: Aspects to focus the analysis on

    Returns:
        The analysis result from the vision AI
    """
    browser = BrowserRecorder()
    vision = get_vision_provider()

    try:
        await browser.start()

        # Take screenshot
        print(f"📸 Taking screenshot of {url}...")
        screenshot_path = await browser.take_screenshot(url, full_page)
        print(f"✅ Screenshot saved: {screenshot_path}")

        # Analyze with vision AI
        print("🔍 Analyzing screenshot...")
        prompt = f"""You are a UI/UX expert. Analyze this screenshot focusing on:

{focus}

For each issue:
- Location on the page
- Description of the issue
- Impact on user experience
- Recommended fix

Also note what's done well."""

        analysis = await vision.analyze_image(screenshot_path, prompt)

        # Clean up
        if screenshot_path.exists():
            screenshot_path.unlink()

        return str(analysis)

    finally:
        await browser.stop()


async def main() -> None:
    """Run the example."""
    url = "https://example.com"

    print("=" * 60)
    print("📸 AnimaWatch - Screenshot Analysis Example")
    print("=" * 60)
    print()
    print(f"URL: {url}")
    print(f"Vision Provider: {settings.vision_provider}")
    print()

    try:
        result = await analyze_screenshot(url)
        print()
        print("=" * 60)
        print("📊 ANALYSIS RESULT")
        print("=" * 60)
        print(result)
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
