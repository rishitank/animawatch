"""AnimaWatch MCP Server - Watch web animations like a human tester.

Built with FastMCP leveraging the latest MCP spec (2025-11-25):
- Lifespan management for browser/vision resources
- Resources for accessing recordings and analysis results
- Prompts for different analysis templates
- Image content type for screenshots
- Sampling for server-side LLM requests
"""

import contextlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.utilities.types import Image
from mcp.server.session import ServerSession

from .browser import BrowserRecorder
from .config import settings
from .vision import VisionProvider, get_vision_provider  # noqa: F401

# =============================================================================
# Application Context (Lifespan Management)
# =============================================================================


@dataclass
class AppContext:
    """Type-safe application context for dependency injection."""

    browser: BrowserRecorder
    vision: VisionProvider
    recordings: dict[str, Path] = field(default_factory=dict)
    analyses: dict[str, str] = field(default_factory=dict)


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage application lifecycle with proper resource cleanup."""
    # Startup: Initialize browser and vision provider
    browser = BrowserRecorder()
    await browser.start()
    vision = get_vision_provider()

    try:
        yield AppContext(browser=browser, vision=vision)
    finally:
        # Shutdown: Clean up browser
        await browser.stop()


# =============================================================================
# FastMCP Server Instance
# =============================================================================

mcp = FastMCP(
    "AnimaWatch",
    lifespan=app_lifespan,
    instructions="""AnimaWatch is an MCP server that watches web animations like a human tester.

It can:
- Record browser interactions and analyze them for animation issues
- Detect jank, stuttering, visual artifacts, timing problems
- Take screenshots and analyze static pages
- Store recordings and analysis results as accessible resources

Use the `watch` tool to record and analyze animations.
Use the `screenshot` tool for static page analysis.
Access previous recordings and analyses via resources.""",
)


# =============================================================================
# Prompt Templates (MCP Prompts Feature)
# =============================================================================

ANIMATION_PROMPT = """You are an expert UI/UX tester analyzing a video recording of a web page.

Watch this recording carefully and identify ANY visual issues:

## Animation Issues
- Jank or stuttering (frames dropping, not smooth 60fps)
- Incorrect timing (too fast, too slow, abrupt starts/stops)
- Missing easing (linear when should be ease-in-out)
- Interrupted or incomplete animations
- Animation loops that shouldn't loop

## Visual Artifacts
- Flickering elements
- Z-index issues (elements appearing above/below incorrectly)
- Clipping or overflow problems
- Rendering glitches

## Layout Issues
- Elements jumping or shifting unexpectedly
- Content reflow during animations
- Overlapping elements

## Timing & Synchronization
- Animations not synchronized with each other
- Delayed responses to interactions
- Race conditions visible in UI

For EACH issue found, report:
- **Timestamp**: When it occurs (e.g., "at 1.2 seconds")
- **Element**: Which UI element is affected
- **Issue**: Clear description of the problem
- **Severity**: Critical / Major / Minor
- **Suggestion**: How to fix it

If no issues are found, confirm the animations are smooth and well-implemented."""


@mcp.prompt()
def animation_diagnosis(focus_area: str = "all") -> str:
    """Generate prompt for animation analysis with optional focus area."""
    base = ANIMATION_PROMPT
    if focus_area != "all":
        return f"{base}\n\n**FOCUS SPECIFICALLY ON**: {focus_area}"
    return base


@mcp.prompt()
def page_analysis(aspects: str = "layout, colors, typography, spacing") -> str:
    """Generate prompt for static page visual analysis."""
    return f"""You are an expert UI/UX designer reviewing a webpage screenshot.

Analyze the following aspects: {aspects}

For each issue found:
- **Location**: Where on the page
- **Issue**: What's wrong
- **Impact**: How it affects user experience
- **Recommendation**: How to fix it

Also note what's done well."""


@mcp.prompt()
def accessibility_check() -> str:
    """Generate prompt for accessibility-focused analysis."""
    return """You are an accessibility expert reviewing a webpage.

Check for:
- Color contrast issues
- Text readability
- Touch target sizes
- Focus indicators visibility
- Animation that could cause vestibular issues
- Missing visual hierarchy

Rate overall accessibility and provide specific recommendations."""


# =============================================================================
# Resources (MCP Resources Feature)
# =============================================================================


@mcp.resource("animawatch://recordings/{recording_id}")
def get_recording(recording_id: str, ctx: Context[ServerSession, AppContext]) -> str:
    """Get information about a stored recording."""
    app_ctx = ctx.request_context.lifespan_context
    if recording_id in app_ctx.recordings:
        path = app_ctx.recordings[recording_id]
        return f"Recording: {recording_id}\nPath: {path}\nExists: {path.exists()}"
    return f"Recording not found: {recording_id}"


@mcp.resource("animawatch://analyses/{analysis_id}")
def get_analysis(analysis_id: str, ctx: Context[ServerSession, AppContext]) -> str:
    """Get a stored analysis result."""
    app_ctx = ctx.request_context.lifespan_context
    if analysis_id in app_ctx.analyses:
        return app_ctx.analyses[analysis_id]
    return f"Analysis not found: {analysis_id}"


@mcp.resource("animawatch://config")
def get_config() -> str:
    """Get current AnimaWatch configuration."""
    return f"""AnimaWatch Configuration:
- Vision Provider: {settings.vision_provider}
- Vision Model: {settings.vision_model}
- Browser Headless: {settings.browser_headless}
- Video Size: {settings.video_width}x{settings.video_height}
- Max Recording Duration: {settings.max_recording_duration}s"""


# =============================================================================
# Tools (MCP Tools Feature with FastMCP decorators)
# =============================================================================


@mcp.tool()
async def watch(
    url: str,
    actions: list[dict[str, Any]] | None = None,
    wait_time: float = 3.0,
    focus: str = "all",
    save_recording: bool = False,
    ctx: Context[ServerSession, AppContext] | None = None,
) -> str:
    """Watch a web page and analyze animations for issues.

    Records browser interaction and uses AI vision to detect jank, stuttering,
    visual artifacts, timing problems - just like a human tester would.

    Args:
        url: URL of the page to watch
        actions: Optional list of actions to perform (click, hover, scroll, type, wait)
        wait_time: Seconds to wait after actions for animations to complete
        focus: Focus area for analysis (e.g., "modal animations", "scroll behavior")
        save_recording: Whether to save the recording for later access via resources
    """
    if ctx is None:
        raise RuntimeError("Context is required")
    app_ctx = ctx.request_context.lifespan_context
    browser = app_ctx.browser
    vision = app_ctx.vision

    # Record the interaction
    video_path = await browser.record_interaction(
        url=url,
        actions=actions,
        wait_time=wait_time,
    )

    # Generate analysis prompt
    prompt = animation_diagnosis(focus)

    # Analyze with vision AI
    analysis = await vision.analyze_video(video_path, prompt)

    # Store results if requested
    result_id = str(uuid.uuid4())[:8]
    if save_recording:
        app_ctx.recordings[result_id] = video_path
    else:
        with contextlib.suppress(Exception):
            video_path.unlink()

    app_ctx.analyses[result_id] = analysis

    output = f"## 🎬 Animation Analysis for {url}\n\n"
    output += f"**Analysis ID**: `{result_id}` (access via `animawatch://analyses/{result_id}`)\n\n"
    if save_recording:
        output += f"**Recording ID**: `{result_id}` (access via `animawatch://recordings/{result_id}`)\n\n"
    output += analysis

    return output


@mcp.tool()
async def screenshot(
    url: str,
    full_page: bool = True,
    focus: str = "layout, colors, typography, spacing",
    ctx: Context[ServerSession, AppContext] | None = None,
) -> Image:
    """Take a screenshot and return it with analysis.

    Fast static analysis for non-animated visual issues.

    Args:
        url: URL to screenshot
        full_page: Capture full scrollable page or just viewport
        focus: Aspects to focus analysis on
    """
    if ctx is None:
        raise RuntimeError("Context is required")
    app_ctx = ctx.request_context.lifespan_context
    browser = app_ctx.browser
    vision = app_ctx.vision

    screenshot_path = await browser.take_screenshot(url, full_page)

    # Analyze with vision AI
    prompt = page_analysis(focus)
    analysis = await vision.analyze_image(screenshot_path, prompt)

    # Store analysis
    result_id = str(uuid.uuid4())[:8]
    app_ctx.analyses[result_id] = f"Screenshot analysis of {url}:\n\n{analysis}"

    # Read image data for return
    with open(screenshot_path, "rb") as f:
        image_data = f.read()

    with contextlib.suppress(Exception):
        screenshot_path.unlink()

    return Image(data=image_data, format="png")


@mcp.tool()
async def analyze_video(
    video_path: str,
    focus: str = "all",
    ctx: Context[ServerSession, AppContext] | None = None,
) -> str:
    """Analyze an existing video file for animation issues.

    Args:
        video_path: Path to the video file
        focus: Focus area for analysis
    """
    if ctx is None:
        raise RuntimeError("Context is required")
    app_ctx = ctx.request_context.lifespan_context
    vision = app_ctx.vision

    path = Path(video_path)
    if not path.exists():
        return f"❌ Video not found: {video_path}"

    prompt = animation_diagnosis(focus)
    analysis = await vision.analyze_video(path, prompt)

    result_id = str(uuid.uuid4())[:8]
    app_ctx.analyses[result_id] = analysis

    return f"## 🎥 Video Analysis\n\n**Analysis ID**: `{result_id}`\n\n{analysis}"


@mcp.tool()
async def record(
    url: str,
    actions: list[dict[str, Any]] | None = None,
    wait_time: float = 3.0,
    output_dir: str | None = None,
    ctx: Context[ServerSession, AppContext] | None = None,
) -> str:
    """Record a browser interaction without analysis.

    Use this to capture recordings for later analysis or manual review.

    Args:
        url: URL to record
        actions: Actions to perform during recording
        wait_time: Seconds to wait after actions
        output_dir: Directory to save video (default: temp directory)
    """
    if ctx is None:
        raise RuntimeError("Context is required")
    app_ctx = ctx.request_context.lifespan_context
    browser = app_ctx.browser

    video_dir = Path(output_dir) if output_dir else None
    video_path = await browser.record_interaction(
        url=url,
        actions=actions,
        wait_time=wait_time,
        video_dir=video_dir,
    )

    result_id = str(uuid.uuid4())[:8]
    app_ctx.recordings[result_id] = video_path

    return f"""## 🎥 Recording Complete

**Recording ID**: `{result_id}`
**Path**: `{video_path}`

Access via resource: `animawatch://recordings/{result_id}`
Analyze with: `analyze_video("{video_path}")`"""


@mcp.tool()
async def check_accessibility(
    url: str,
    ctx: Context[ServerSession, AppContext] | None = None,
) -> str:
    """Check a page for visual accessibility issues.

    Uses AI vision to identify contrast, readability, and other accessibility concerns.

    Args:
        url: URL to check
    """
    if ctx is None:
        raise RuntimeError("Context is required")
    app_ctx = ctx.request_context.lifespan_context
    browser = app_ctx.browser
    vision = app_ctx.vision

    screenshot_path = await browser.take_screenshot(url, full_page=True)

    prompt = accessibility_check()
    analysis = await vision.analyze_image(screenshot_path, prompt)

    with contextlib.suppress(Exception):
        screenshot_path.unlink()

    result_id = str(uuid.uuid4())[:8]
    app_ctx.analyses[result_id] = analysis

    return f"## ♿ Accessibility Analysis for {url}\n\n**Analysis ID**: `{result_id}`\n\n{analysis}"


# =============================================================================
# Server Entry Point
# =============================================================================


def main() -> None:
    """Run the AnimaWatch MCP server."""
    import sys

    # Support both stdio (default) and streamable-http transports
    transport: Literal["stdio", "streamable-http"] = "stdio"
    if "--http" in sys.argv:
        transport = "streamable-http"

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
