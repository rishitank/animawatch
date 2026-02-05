#!/usr/bin/env python3
"""Example: Multi-Page Workflow Testing with AnimaWatch.

This example demonstrates how to test user journeys across multiple pages,
analyzing animations and transitions at each step.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from animawatch.browser import BrowserRecorder
from animawatch.config import settings
from animawatch.vision import get_vision_provider


@dataclass
class WorkflowStep:
    """A single step in a multi-page workflow."""

    name: str
    url: str | None = None  # If None, stay on current page
    actions: list[dict[str, str | float]] | None = None
    wait_time: float = 2.0
    focus: str = "all"


async def test_workflow(steps: list[WorkflowStep]) -> list[dict[str, str]]:
    """Test a multi-page workflow and analyze each step.

    Args:
        steps: List of workflow steps to execute

    Returns:
        List of analysis results for each step
    """
    browser = BrowserRecorder()
    vision = get_vision_provider()
    results: list[dict[str, str]] = []
    video_paths: list[Path] = []

    try:
        await browser.start()
        current_url: str | None = None

        for i, step in enumerate(steps, 1):
            print(f"\n🔄 Step {i}/{len(steps)}: {step.name}")

            # Determine the URL for this step
            if step.url:
                current_url = step.url
            elif current_url is None:
                raise ValueError(f"Step {i} ({step.name}) has no URL and no previous URL to use")
            # If step.url is None, we keep using current_url from previous step

            # Record the interaction
            video_path = await browser.record_interaction(
                url=current_url,
                actions=step.actions,
                wait_time=step.wait_time,
            )
            video_paths.append(video_path)

            # Analyze for animation issues
            prompt = f"""Analyzing workflow step: {step.name}

Watch this recording and identify any issues:

1. **Page Load Animations**
   - Smooth loading transitions
   - No jarring content shifts
   - Progressive rendering

2. **Navigation Transitions**
   - Page transition animations
   - Loading indicators
   - Content fade-in effects

3. **Interactive Element Feedback**
   - Button click feedback
   - Form field focus states
   - Hover state transitions

4. **Layout Stability**
   - No unexpected layout shifts
   - Content stays in place
   - Proper content flow

Focus area: {step.focus}

Report any issues with severity and recommendations."""

            print("   🔍 Analyzing...")
            analysis = await vision.analyze_video(video_path, prompt)

            results.append(
                {
                    "step": step.name,
                    "url": current_url,
                    "analysis": analysis,
                }
            )

            # Clean up video
            if video_path.exists():
                video_path.unlink()

        return results

    finally:
        # Ensure all temp files are cleaned
        for path in video_paths:
            if path.exists():
                path.unlink()
        await browser.stop()


async def main() -> None:
    """Run the multi-page workflow example."""
    # Example: Simple navigation workflow
    workflow = [
        WorkflowStep(
            name="Homepage Load",
            url="https://example.com",
            wait_time=2.0,
            focus="page load animations, layout stability",
        ),
        WorkflowStep(
            name="Scroll Interaction",
            url="https://example.com",
            actions=[
                {"type": "scroll", "y": 300},
                {"type": "wait", "duration": 0.5},
                {"type": "scroll", "y": 300},
            ],
            wait_time=1.5,
            focus="scroll behavior, lazy loading, sticky elements",
        ),
        WorkflowStep(
            name="Link Hover States",
            url="https://example.com",
            actions=[
                {"type": "hover", "selector": "a"},
                {"type": "wait", "duration": 0.5},
            ],
            wait_time=1.0,
            focus="hover transitions, visual feedback",
        ),
    ]

    print("=" * 60)
    print("🔄 AnimaWatch - Multi-Page Workflow Example")
    print("=" * 60)
    print()
    print(f"Vision Provider: {settings.vision_provider}")
    print(f"Steps: {len(workflow)}")
    for i, step in enumerate(workflow, 1):
        print(f"  {i}. {step.name}")
    print()

    try:
        results = await test_workflow(workflow)

        print()
        print("=" * 60)
        print("📊 WORKFLOW ANALYSIS RESULTS")
        print("=" * 60)

        for result in results:
            print(f"\n### {result['step']}")
            print(f"URL: {result['url']}")
            print("-" * 40)
            print(result["analysis"])
            print()

    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
