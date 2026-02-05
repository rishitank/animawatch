#!/usr/bin/env python3
"""Example: Basic Animation Check with AnimaWatch.

This example demonstrates how to use AnimaWatch programmatically
to check animations on a webpage without running as an MCP server.
"""

import asyncio
from pathlib import Path

from animawatch.browser import BrowserRecorder
from animawatch.config import settings
from animawatch.vision import get_vision_provider


async def check_animations(url: str, output_dir: Path | None = None) -> str:
    """Record and analyze animations on a webpage.

    Args:
        url: The webpage URL to analyze
        output_dir: Optional directory to save the recording

    Returns:
        The analysis result from the vision AI
    """
    # Initialize browser recorder and vision provider
    browser = BrowserRecorder()
    vision = get_vision_provider()
    video_path: Path | None = None

    try:
        # Start the browser
        await browser.start()

        # Record the page (waits 3 seconds for animations)
        print(f"🎬 Recording {url}...")
        video_path = await browser.record_interaction(
            url=url,
            actions=None,  # No specific actions, just watch
            wait_time=3.0,
            video_dir=output_dir,
        )
        print(f"✅ Recording saved: {video_path}")

        # Analyze with vision AI
        print("🔍 Analyzing with vision AI...")
        prompt = """Analyze this video for animation issues:
- Jank or stuttering
- Timing problems
- Visual artifacts
- Layout shifts

Report any issues with timestamps and severity."""

        analysis = await vision.analyze_video(video_path, prompt)

        return str(analysis)

    finally:
        # Clean up temp video if no output dir specified
        if output_dir is None and video_path is not None and video_path.exists():
            video_path.unlink()
        # Always clean up browser
        await browser.stop()


async def main() -> None:
    """Run the example."""
    # Example URL - replace with your own
    url = "https://example.com"

    print("=" * 60)
    print("🎬 AnimaWatch - Basic Animation Check Example")
    print("=" * 60)
    print()
    print(f"URL: {url}")
    print(f"Vision Provider: {settings.vision_provider}")
    print(f"Vision Model: {settings.vision_model}")
    print()

    try:
        result = await check_animations(url)
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
