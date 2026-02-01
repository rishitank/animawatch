"""Browser automation and video recording using Playwright for AnimaWatch."""

import asyncio
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from .config import settings


class BrowserRecorder:
    """Manages browser automation and video recording for AnimaWatch."""

    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None

    async def start(self):
        """Start the Playwright browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.browser_headless,
        )

    async def stop(self):
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

        context = await self._browser.new_context(
            viewport=settings.video_size,
            record_video_dir=str(video_dir),
            record_video_size=settings.video_size,
        )

        page = await context.new_page()

        try:
            yield context, page, video_dir
        finally:
            # Get the video path before closing
            video = page.video
            if video:
                video_path = await video.path()

            await context.close()

    async def record_interaction(
        self,
        url: str,
        actions: list[dict] | None = None,
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

        context = await self._browser.new_context(viewport=settings.video_size)
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle")

            screenshot_path = Path(tempfile.mktemp(suffix=".png"))
            await page.screenshot(path=str(screenshot_path), full_page=full_page)

            return screenshot_path
        finally:
            await context.close()

    async def _perform_action(self, page: Page, action: dict):
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

