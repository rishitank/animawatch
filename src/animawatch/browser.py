"""Browser automation and video recording using Playwright for AnimaWatch.

Features:
- Video recording of browser interactions
- Mobile device emulation with predefined profiles
- Connection pooling for browser context reuse
- Screenshot capture with full-page support
"""

import asyncio
import os
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
from .devices import DeviceProfile, get_device
from .logging import log_extra


class BrowserRecorder:
    """Manages browser automation and video recording for AnimaWatch.

    Features:
    - Video recording with configurable viewport
    - Mobile device emulation
    - Connection pooling for reusing browser contexts
    - Structured logging for observability
    """

    def __init__(self, pool_size: int = 3) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._pool_size = pool_size
        self._context_pool: list[BrowserContext] = []
        self._pool_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the Playwright browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.browser_headless,
        )
        log_extra("Browser started", headless=settings.browser_headless)

    async def stop(self) -> None:
        """Stop the browser and cleanup."""
        # Close all pooled contexts
        async with self._pool_lock:
            for ctx in self._context_pool:
                await ctx.close()
            self._context_pool.clear()

        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        log_extra("Browser stopped")

    @asynccontextmanager
    async def recording_context(
        self,
        video_dir: Path | None = None,
        device: str | DeviceProfile | None = None,
    ) -> AsyncGenerator[tuple[BrowserContext, Page, Path], None]:
        """Create a browser context with video recording enabled.

        Args:
            video_dir: Directory to save video (default: temp)
            device: Device profile name or DeviceProfile for emulation
        """
        if not self._browser:
            await self.start()

        # Use temp directory if not specified
        if video_dir is None:
            video_dir = Path(tempfile.mkdtemp(prefix="animawatch-"))

        video_dir.mkdir(parents=True, exist_ok=True)

        if self._browser is None:
            raise RuntimeError("Browser not initialized")

        # Resolve device profile
        profile = self._resolve_device(device)
        viewport = profile.viewport if profile else settings.video_size
        video_size = profile.viewport if profile else settings.video_size

        # Build context options
        context_options: dict[str, Any] = {
            "viewport": viewport,
            "record_video_dir": str(video_dir),
            "record_video_size": video_size,
        }

        # Add device-specific options
        if profile:
            context_options["user_agent"] = profile.user_agent
            context_options["device_scale_factor"] = profile.device_scale_factor
            context_options["is_mobile"] = profile.is_mobile
            context_options["has_touch"] = profile.has_touch
            log_extra("Device emulation", device=profile.name, viewport=viewport)

        context = await self._browser.new_context(**context_options)
        page = await context.new_page()

        try:
            yield context, page, video_dir
        finally:
            # Ensure video is saved before closing
            video = page.video
            if video:
                await video.path()  # Wait for video to be saved

            await context.close()

    def _resolve_device(self, device: str | DeviceProfile | None) -> DeviceProfile | None:
        """Resolve device name to DeviceProfile."""
        if device is None:
            return None
        if isinstance(device, DeviceProfile):
            return device
        return get_device(device)

    @asynccontextmanager
    async def pooled_context(
        self,
        device: str | DeviceProfile | None = None,
    ) -> AsyncGenerator[tuple[BrowserContext, Page], None]:
        """Get a browser context from the pool (without video recording).

        This is more efficient for screenshots and navigation tasks where
        video recording is not needed. Contexts are reused when possible.

        Args:
            device: Device profile name or DeviceProfile for emulation

        Note: Pooled contexts don't support video recording.
        For video recording, use recording_context() instead.
        """
        if not self._browser:
            await self.start()

        if self._browser is None:
            raise RuntimeError("Browser not initialized")

        # Resolve device profile
        profile = self._resolve_device(device)
        viewport = profile.viewport if profile else settings.video_size

        # Build context options
        context_options: dict[str, Any] = {"viewport": viewport}
        if profile:
            context_options["user_agent"] = profile.user_agent
            context_options["device_scale_factor"] = profile.device_scale_factor
            context_options["is_mobile"] = profile.is_mobile
            context_options["has_touch"] = profile.has_touch
            log_extra("Device emulation (pooled)", device=profile.name, viewport=viewport)

        # Try to get a context from the pool
        context: BrowserContext | None = None
        async with self._pool_lock:
            if self._context_pool:
                context = self._context_pool.pop()
                log_extra("Reusing pooled context", pool_remaining=len(self._context_pool))

        # Create new context if pool was empty
        if context is None:
            context = await self._browser.new_context(**context_options)
            log_extra("Created new context", pool_size=len(self._context_pool))

        page = await context.new_page()

        try:
            yield context, page
        finally:
            # Close the page but return context to pool if room
            await page.close()
            async with self._pool_lock:
                if len(self._context_pool) < self._pool_size:
                    self._context_pool.append(context)
                    log_extra("Returned context to pool", pool_size=len(self._context_pool))
                else:
                    await context.close()
                    log_extra("Pool full, closed context")

    async def record_interaction(
        self,
        url: str,
        actions: list[dict[str, Any]] | None = None,
        wait_time: float = 3.0,
        video_dir: Path | None = None,
        device: str | None = None,
    ) -> Path:
        """
        Record a browser interaction and return the video path.

        Args:
            url: URL to navigate to
            actions: Optional list of actions to perform (click, type, scroll, etc.)
            wait_time: Time to wait after actions for animations to complete
            video_dir: Directory to save video (default: temp)
            device: Device profile name for mobile emulation (e.g., "iphone_15_pro")

        Returns:
            Path to the recorded video file
        """
        async with self.recording_context(video_dir, device) as (context, page, vid_dir):
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

    async def take_screenshot(
        self,
        url: str,
        full_page: bool = True,
        device: str | None = None,
        use_pool: bool = False,
    ) -> Path:
        """Take a screenshot of a page.

        Args:
            url: URL to screenshot
            full_page: Capture full scrollable page or just viewport
            device: Device profile name for mobile emulation
            use_pool: Use connection pooling for better performance (default: False)
                Note: Pooling ignores device-specific settings for reuse efficiency
        """
        if use_pool and device is None:
            # Use pooled context for better performance (no device emulation)
            async with self.pooled_context() as (_, page):
                await page.goto(url, wait_until="networkidle")

                fd, tmp_path = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                screenshot_path = Path(tmp_path)
                await page.screenshot(path=str(screenshot_path), full_page=full_page)

                log_extra(
                    "Screenshot captured (pooled)",
                    url=url,
                    full_page=full_page,
                )
                return screenshot_path

        # Non-pooled path (original behavior with device support)
        if not self._browser:
            await self.start()

        if self._browser is None:
            raise RuntimeError("Browser not initialized")

        # Resolve device profile
        profile = self._resolve_device(device)
        viewport = profile.viewport if profile else settings.video_size

        # Build context options
        context_options: dict[str, Any] = {"viewport": viewport}
        if profile:
            context_options["user_agent"] = profile.user_agent
            context_options["device_scale_factor"] = profile.device_scale_factor
            context_options["is_mobile"] = profile.is_mobile
            context_options["has_touch"] = profile.has_touch

        context = await self._browser.new_context(**context_options)
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle")

            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            screenshot_path = Path(tmp_path)
            await page.screenshot(path=str(screenshot_path), full_page=full_page)

            log_extra(
                "Screenshot captured",
                url=url,
                device=profile.name if profile else "default",
                full_page=full_page,
            )
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
