#!/usr/bin/env python3
"""Example: CI/CD Integration with AnimaWatch.

This example demonstrates how to use AnimaWatch in CI/CD pipelines
with structured output and exit codes for automated testing.

Usage in GitHub Actions:
    - name: Run Visual Tests
      env:
        GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
      run: |
        uv run python examples/ci_integration.py \\
          --url https://your-site.com \\
          --threshold 0.8 \\
          --output results.json
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from animawatch.browser import BrowserRecorder
from animawatch.config import settings
from animawatch.vision import get_vision_provider


@dataclass
class TestResult:
    """Structured test result for CI/CD integration."""

    url: str
    passed: bool
    score: float  # 0.0 to 1.0
    issues_found: int
    critical_issues: int
    summary: str
    details: str


async def run_visual_test(url: str, threshold: float = 0.8) -> TestResult:
    """Run a visual test and return structured results.

    Args:
        url: URL to test
        threshold: Pass/fail threshold (0.0-1.0)

    Returns:
        Structured test result

    Raises:
        ValueError: If threshold is not between 0.0 and 1.0
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")

    browser = BrowserRecorder()
    vision = get_vision_provider()
    screenshot_path: Path | None = None

    try:
        await browser.start()

        # Capture screenshot
        screenshot_path = await browser.take_screenshot(url, full_page=True)

        # Analyze with structured prompt for CI-friendly output
        prompt = """You are a visual QA system. Analyze this screenshot and provide a JSON response.

Return ONLY valid JSON with this structure:
{
    "score": 0.95,
    "issues": [
        {
            "type": "layout|style|content|accessibility",
            "severity": "critical|major|minor",
            "description": "Brief description",
            "location": "Where on the page"
        }
    ],
    "summary": "One sentence summary"
}

Score guidelines:
- 1.0: Perfect, no issues
- 0.9+: Minor cosmetic issues only
- 0.7-0.9: Some issues but usable
- 0.5-0.7: Significant issues
- <0.5: Major problems, unusable

Check for: layout problems, broken styling, accessibility issues, visual artifacts."""

        analysis = await vision.analyze_image(screenshot_path, prompt)

        # Parse the AI response
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_str = analysis
            if "```json" in analysis:
                json_str = analysis.split("```json")[1].split("```")[0]
            elif "```" in analysis:
                json_str = analysis.split("```")[1].split("```")[0]

            result_data = json.loads(json_str.strip())
            score = float(result_data.get("score", 0.5))
            issues = result_data.get("issues", [])
            summary = result_data.get("summary", "Analysis complete")

            critical_count = sum(1 for i in issues if i.get("severity") == "critical")

            return TestResult(
                url=url,
                passed=score >= threshold and critical_count == 0,
                score=score,
                issues_found=len(issues),
                critical_issues=critical_count,
                summary=summary,
                details=analysis,
            )

        except (json.JSONDecodeError, KeyError, ValueError):
            # If parsing fails, return a conservative result
            return TestResult(
                url=url,
                passed=False,
                score=0.5,
                issues_found=-1,
                critical_issues=-1,
                summary="Could not parse AI response",
                details=analysis,
            )

    finally:
        if screenshot_path is not None and screenshot_path.exists():
            screenshot_path.unlink()
        await browser.stop()


async def main() -> int:
    """Run CI visual test and return exit code."""
    parser = argparse.ArgumentParser(description="AnimaWatch CI Integration")
    parser.add_argument("--url", default="https://example.com", help="URL to test")
    parser.add_argument("--threshold", type=float, default=0.8, help="Pass threshold")
    parser.add_argument("--output", help="JSON output file path")
    args = parser.parse_args()

    print(f"🔍 Testing: {args.url}")
    print(f"📊 Threshold: {args.threshold}")
    print(f"🤖 Provider: {settings.vision_provider}")
    print()

    result = await run_visual_test(args.url, args.threshold)

    # Output results
    result_dict = asdict(result)
    if args.output:
        with open(args.output, "w") as f:
            json.dump(result_dict, f, indent=2)
        print(f"📁 Results saved to: {args.output}")

    # Print summary
    status = "✅ PASSED" if result.passed else "❌ FAILED"
    print(f"\n{status} - Score: {result.score:.2f}")
    print(f"Issues: {result.issues_found} total, {result.critical_issues} critical")
    print(f"Summary: {result.summary}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
