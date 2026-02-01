"""Visual Diagnosis MCP Server - Main server implementation."""

import asyncio
import tempfile
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .browser import BrowserRecorder
from .config import settings
from .vision import get_vision_provider

# Create server instance
server = Server("visual-diagnosis-mcp")

# Global browser recorder instance
_browser: BrowserRecorder | None = None


async def get_browser() -> BrowserRecorder:
    """Get or create the browser recorder instance."""
    global _browser
    if _browser is None:
        _browser = BrowserRecorder()
        await _browser.start()
    return _browser


# Animation diagnosis prompt template
ANIMATION_DIAGNOSIS_PROMPT = """You are an expert UI/UX tester analyzing a video recording of a web page interaction.

Watch this recording carefully and identify ANY visual issues, including:

1. **Animation Issues**:
   - Jank or stuttering (frames dropping, not smooth 60fps)
   - Incorrect timing (too fast, too slow, abrupt starts/stops)
   - Missing easing (linear when should be ease-in-out)
   - Interrupted or incomplete animations
   - Animation loops that shouldn't loop

2. **Visual Artifacts**:
   - Flickering elements
   - Z-index issues (elements appearing above/below incorrectly)
   - Clipping or overflow problems
   - Rendering glitches

3. **Layout Issues**:
   - Elements jumping or shifting unexpectedly
   - Content reflow during animations
   - Overlapping elements

4. **Timing & Synchronization**:
   - Animations not synchronized with each other
   - Delayed responses to interactions
   - Race conditions visible in UI

For EACH issue found, report:
- **Timestamp**: When it occurs (e.g., "at 1.2 seconds")
- **Element**: Which UI element is affected
- **Issue**: Clear description of the problem
- **Severity**: Critical / Major / Minor
- **Suggestion**: How to fix it

If no issues are found, confirm the animations are smooth and well-implemented.

Be thorough - watch the entire recording multiple times if needed."""


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="diagnose_animation",
            description=(
                "Record a web page interaction and analyze it for animation issues, "
                "visual artifacts, and UI problems. Uses AI vision to watch the recording "
                "like a human tester would."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page to diagnose",
                    },
                    "actions": {
                        "type": "array",
                        "description": "Optional actions to perform (click, hover, scroll, etc.)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["click", "hover", "scroll", "type", "wait"]},
                                "selector": {"type": "string"},
                                "text": {"type": "string"},
                                "y": {"type": "number"},
                                "duration": {"type": "number"},
                            },
                        },
                    },
                    "wait_time": {
                        "type": "number",
                        "description": "Seconds to wait after actions for animations (default: 3)",
                        "default": 3.0,
                    },
                    "custom_prompt": {
                        "type": "string",
                        "description": "Optional custom prompt for specific analysis",
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="diagnose_page",
            description=(
                "Take a screenshot of a page and analyze it for visual issues. "
                "Faster than video analysis but doesn't capture animations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to screenshot"},
                    "full_page": {"type": "boolean", "default": True},
                    "prompt": {"type": "string", "description": "What to look for"},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="analyze_video",
            description="Analyze an existing video file for visual/animation issues.",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "Path to video file"},
                    "prompt": {"type": "string", "description": "Analysis prompt"},
                },
                "required": ["video_path"],
            },
        ),
        Tool(
            name="record_interaction",
            description="Record a browser interaction without analysis. Returns video path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "actions": {"type": "array"},
                    "wait_time": {"type": "number", "default": 3.0},
                    "output_dir": {"type": "string"},
                },
                "required": ["url"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "diagnose_animation":
            return await _diagnose_animation(arguments)
        elif name == "diagnose_page":
            return await _diagnose_page(arguments)
        elif name == "analyze_video":
            return await _analyze_video(arguments)
        elif name == "record_interaction":
            return await _record_interaction(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def _diagnose_animation(args: dict) -> list[TextContent]:
    """Record and diagnose animations on a page."""
    url = args["url"]
    actions = args.get("actions")
    wait_time = args.get("wait_time", 3.0)
    custom_prompt = args.get("custom_prompt")

    browser = await get_browser()
    vision = get_vision_provider()

    # Record the interaction
    video_path = await browser.record_interaction(
        url=url,
        actions=actions,
        wait_time=wait_time,
    )

    # Analyze with vision AI
    prompt = custom_prompt or ANIMATION_DIAGNOSIS_PROMPT
    analysis = await vision.analyze_video(video_path, prompt)

    # Clean up video file
    try:
        video_path.unlink()
    except Exception:
        pass

    return [TextContent(
        type="text",
        text=f"## Animation Diagnosis for {url}\n\n{analysis}",
    )]


async def _diagnose_page(args: dict) -> list[TextContent]:
    """Screenshot and diagnose a page."""
    url = args["url"]
    full_page = args.get("full_page", True)
    prompt = args.get("prompt", "Analyze this webpage for any visual issues, layout problems, or UI inconsistencies.")

    browser = await get_browser()
    vision = get_vision_provider()

    screenshot_path = await browser.take_screenshot(url, full_page)
    analysis = await vision.analyze_image(screenshot_path, prompt)

    try:
        screenshot_path.unlink()
    except Exception:
        pass

    return [TextContent(type="text", text=f"## Page Analysis for {url}\n\n{analysis}")]


async def _analyze_video(args: dict) -> list[TextContent]:
    """Analyze an existing video file."""
    video_path = Path(args["video_path"])
    prompt = args.get("prompt", ANIMATION_DIAGNOSIS_PROMPT)

    if not video_path.exists():
        return [TextContent(type="text", text=f"Video not found: {video_path}")]

    vision = get_vision_provider()
    analysis = await vision.analyze_video(video_path, prompt)

    return [TextContent(type="text", text=f"## Video Analysis\n\n{analysis}")]


async def _record_interaction(args: dict) -> list[TextContent]:
    """Record a browser interaction without analysis."""
    url = args["url"]
    actions = args.get("actions")
    wait_time = args.get("wait_time", 3.0)
    output_dir = args.get("output_dir")

    browser = await get_browser()
    video_dir = Path(output_dir) if output_dir else None

    video_path = await browser.record_interaction(
        url=url,
        actions=actions,
        wait_time=wait_time,
        video_dir=video_dir,
    )

    return [TextContent(
        type="text",
        text=f"Recording saved to: {video_path}",
    )]


def main():
    """Run the MCP server."""
    import asyncio

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()

