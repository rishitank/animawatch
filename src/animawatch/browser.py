"""Browser automation and video recording using Playwright for AnimaWatch."""

import asyncio
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from .config import settings


class BrowserRecorder:
    """Manages browser automation and video recording for AnimaWatch."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        """Start the Playwright browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.browser_headless,
        )

    async def stop(self) -> None:
        """Stop the browser and cleanup."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    @asynccontextmanager
    async def recording_context(
        self,
        video_dir: Path | None = None,
    ) -> AsyncGenerator[tuple[BrowserContext, Page, Path], None]:
        """Create a browser context with video recording enabled."""
        if not self._browser:
            await self.start()

        # Use temp directory if not specified
        if video_dir is None:
            video_dir = Path(tempfile.mkdtemp(prefix="animawatch-"))

        video_dir.mkdir(parents=True, exist_ok=True)

        if self._browser is None:
            raise RuntimeError("Browser not initialized")

        context = await self._browser.new_context(
            viewport={"width": settings.video_width, "height": settings.video_height},
            record_video_dir=str(video_dir),
            record_video_size={"width": settings.video_width, "height": settings.video_height},
        )

        page = await context.new_page()

        try:
            yield context, page, video_dir
        finally:
            # Ensure video is saved before closing
            video = page.video
            if video:
                await video.path()  # Wait for video to be saved

            await context.close()

    async def record_interaction(
        self,
        url: str,
        actions: list[dict[str, Any]] | None = None,
        wait_time: float = 3.0,
        video_dir: Path | None = None,
    ) -> Path:
        """
        Record a browser interaction and return the video path.

        Args:
            url: URL to navigate to
            actions: Optional list of actions to perform (click, type, scroll, etc.)
            wait_time: Time to wait after actions for animations to complete
            video_dir: Directory to save video (default: temp)

        Returns:
            Path to the recorded video file
        """
        async with self.recording_context(video_dir) as (context, page, vid_dir):
            # Navigate to URL
            await page.goto(url, wait_until="networkidle")

            # Perform any specified actions
            if actions:
                for action in actions:
                    await self._perform_action(page, action)

            # Wait for animations to complete
            await asyncio.sleep(wait_time)

            # Get video path
            video = page.video
            if video:
                video_path = await video.path()
                return Path(video_path)

        raise RuntimeError("Failed to record video")

    async def take_screenshot(self, url: str, full_page: bool = True) -> Path:
        """Take a screenshot of a page."""
        if not self._browser:
            await self.start()

        if self._browser is None:
            raise RuntimeError("Browser not initialized")

        context = await self._browser.new_context(
            viewport={"width": settings.video_width, "height": settings.video_height}
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle")

            screenshot_path = Path(tempfile.mktemp(suffix=".png"))
            await page.screenshot(path=str(screenshot_path), full_page=full_page)

            return screenshot_path
        finally:
            await context.close()

    async def _perform_action(self, page: Page, action: dict[str, Any]) -> None:
        """Perform a single browser action."""
        action_type = action.get("type", "")

        if action_type == "click":
            selector = action.get("selector")
            if selector:
                await page.click(selector)

        elif action_type == "type":
            selector = action.get("selector")
            text = action.get("text", "")
            if selector:
                await page.fill(selector, text)

        elif action_type == "scroll":
            y = action.get("y", 500)
            await page.evaluate(f"window.scrollBy(0, {y})")

        elif action_type == "wait":
            duration = action.get("duration", 1.0)
            await asyncio.sleep(duration)

        elif action_type == "hover":
            selector = action.get("selector")
            if selector:
                await page.hover(selector)
