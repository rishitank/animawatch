#!/usr/bin/env python3
"""Example: Form Interaction Testing with AnimaWatch.

This example demonstrates how to test form interactions,
analyzing input animations, validation feedback, and submit behaviors.
"""

import asyncio
from pathlib import Path

from animawatch.browser import BrowserRecorder
from animawatch.config import settings
from animawatch.vision import get_vision_provider


async def test_form_interactions(
    url: str,
    form_selector: str = "form",
    inputs: list[dict[str, str]] | None = None,
) -> str:
    """Test form interactions and analyze visual feedback.

    Args:
        url: URL containing the form
        form_selector: CSS selector for the form
        inputs: List of input actions (selector + value pairs)

    Returns:
        The analysis result
    """
    browser = BrowserRecorder()
    vision = get_vision_provider()
    video_path: Path | None = None

    # Default test inputs if none provided
    if inputs is None:
        inputs = [
            {"selector": "input[type='text'], input[type='email']", "value": "test@example.com"},
            {"selector": "input[type='password']", "value": "testpassword123"},
        ]

    # Build actions list
    actions: list[dict[str, str | float]] = []
    for inp in inputs:
        # Focus on the field first (for focus animation)
        actions.extend(
            [
                {"type": "click", "selector": inp["selector"]},
                {"type": "wait", "duration": 0.3},
                {"type": "type", "selector": inp["selector"], "text": inp["value"]},
                {"type": "wait", "duration": 0.5},
            ]
        )

    # Click outside to trigger blur/validation
    actions.append({"type": "click", "selector": "body"})
    actions.append({"type": "wait", "duration": 0.5})

    try:
        await browser.start()

        print(f"🎬 Recording form interactions on {url}...")
        video_path = await browser.record_interaction(
            url=url,
            actions=actions,
            wait_time=2.0,
        )

        # Analyze form interactions
        prompt = """You are testing form interactions on a webpage.

Analyze this recording for form-related animation and feedback issues:

1. **Focus States**
   - Input field focus animations (border, shadow, highlight)
   - Label transitions (floating labels, color changes)
   - Smooth focus transitions between fields

2. **Typing Feedback**
   - Character input animations
   - Password field masking behavior
   - Real-time validation indicators

3. **Validation Feedback**
   - Error message appearance (fade-in, slide-down)
   - Error highlighting (red borders, icons)
   - Success indicators (checkmarks, green states)

4. **Button States**
   - Disabled state transitions
   - Hover/active state feedback
   - Loading spinners on submit

5. **Overall Form UX**
   - Smooth transitions between states
   - Clear visual hierarchy
   - Responsive layout during interaction

For each issue:
- **Element**: Which form element
- **Issue**: What's wrong with the animation/feedback
- **Severity**: Breaking / Major / Minor
- **Suggestion**: How to improve"""

        print("🔍 Analyzing form interactions...")
        analysis = await vision.analyze_video(video_path, prompt)

        return str(analysis)

    finally:
        if video_path is not None and video_path.exists():
            video_path.unlink()
        await browser.stop()


async def main() -> None:
    """Run the form interaction example."""
    # Example: Test a login form
    url = "https://example.com"  # Replace with URL containing a form

    print("=" * 60)
    print("📝 AnimaWatch - Form Interaction Testing Example")
    print("=" * 60)
    print()
    print(f"URL: {url}")
    print(f"Vision Provider: {settings.vision_provider}")
    print()
    print("Actions to perform:")
    print("  1. Click and type in text/email fields")
    print("  2. Click and type in password fields")
    print("  3. Click outside to trigger validation")
    print()

    try:
        result = await test_form_interactions(url)
        print()
        print("=" * 60)
        print("📊 FORM INTERACTION ANALYSIS")
        print("=" * 60)
        print(result)
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
