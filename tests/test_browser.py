"""Tests for AnimaWatch browser automation module."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from animawatch.browser import BrowserRecorder


class TestBrowserRecorder:
    """Tests for BrowserRecorder class."""

    @pytest.fixture
    def recorder(self) -> BrowserRecorder:
        """Create a BrowserRecorder instance."""
        return BrowserRecorder()

    def test_init(self, recorder: BrowserRecorder) -> None:
        """Test BrowserRecorder initialization."""
        assert recorder._playwright is None
        assert recorder._browser is None

    @pytest.mark.asyncio
    async def test_start_initializes_browser(self, recorder: BrowserRecorder) -> None:
        """Test that start() initializes Playwright and browser."""
        mock_playwright = MagicMock()
        mock_browser = AsyncMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("animawatch.browser.async_playwright") as mock_async_pw:
            mock_async_pw.return_value.start = AsyncMock(return_value=mock_playwright)
            await recorder.start()

            assert recorder._playwright is mock_playwright
            assert recorder._browser is mock_browser
            mock_playwright.chromium.launch.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_cleans_up_resources(self, recorder: BrowserRecorder) -> None:
        """Test that stop() cleans up browser and playwright."""
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()
        recorder._browser = mock_browser
        recorder._playwright = mock_playwright

        await recorder.stop()

        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()
        assert recorder._browser is None
        assert recorder._playwright is None

    @pytest.mark.asyncio
    async def test_stop_handles_none_browser(self, recorder: BrowserRecorder) -> None:
        """Test that stop() handles None browser gracefully."""
        recorder._browser = None
        recorder._playwright = None

        # Should not raise
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_recording_context_creates_context_with_video(
        self, recorder: BrowserRecorder
    ) -> None:
        """Test that recording_context creates a browser context with video recording."""
        mock_page = AsyncMock()
        mock_video = AsyncMock()
        mock_video.path = AsyncMock(return_value="/tmp/video.webm")
        mock_page.video = mock_video

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        recorder._browser = mock_browser

        async with recorder.recording_context() as (context, page, video_dir):
            assert context is mock_context
            assert page is mock_page
            assert isinstance(video_dir, Path)

        mock_browser.new_context.assert_called_once()
        mock_context.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_recording_context_starts_browser_if_not_started(
        self, recorder: BrowserRecorder
    ) -> None:
        """Test that recording_context starts browser if not already started."""
        mock_page = AsyncMock()
        mock_video = AsyncMock()
        mock_video.path = AsyncMock(return_value="/tmp/video.webm")
        mock_page.video = mock_video

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("animawatch.browser.async_playwright") as mock_async_pw:
            mock_async_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            async with recorder.recording_context() as (context, page, video_dir):
                assert recorder._browser is mock_browser

    @pytest.mark.asyncio
    async def test_take_screenshot_returns_path(self, recorder: BrowserRecorder) -> None:
        """Test that take_screenshot returns a Path to the screenshot."""
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        recorder._browser = mock_browser

        result = await recorder.take_screenshot("https://example.com")

        assert isinstance(result, Path)
        assert result.suffix == ".png"
        mock_page.goto.assert_called_once()
        mock_page.screenshot.assert_called_once()
        mock_context.close.assert_called_once()


class TestBrowserRecorderActions:
    """Tests for BrowserRecorder action handling."""

    @pytest.fixture
    def recorder(self) -> BrowserRecorder:
        """Create a BrowserRecorder instance."""
        return BrowserRecorder()

    @pytest.mark.asyncio
    async def test_perform_action_click(self, recorder: BrowserRecorder) -> None:
        """Test click action."""
        mock_page = AsyncMock()
        action = {"type": "click", "selector": "#button"}

        await recorder._perform_action(mock_page, action)

        mock_page.click.assert_called_once_with("#button")

    @pytest.mark.asyncio
    async def test_perform_action_type(self, recorder: BrowserRecorder) -> None:
        """Test type action."""
        mock_page = AsyncMock()
        action = {"type": "type", "selector": "#input", "text": "hello"}

        await recorder._perform_action(mock_page, action)

        mock_page.fill.assert_called_once_with("#input", "hello")

    @pytest.mark.asyncio
    async def test_perform_action_scroll(self, recorder: BrowserRecorder) -> None:
        """Test scroll action."""
        mock_page = AsyncMock()
        action = {"type": "scroll", "y": 300}

        await recorder._perform_action(mock_page, action)

        mock_page.evaluate.assert_called_once_with("window.scrollBy(0, 300)")

    @pytest.mark.asyncio
    async def test_perform_action_hover(self, recorder: BrowserRecorder) -> None:
        """Test hover action."""
        mock_page = AsyncMock()
        action = {"type": "hover", "selector": "#menu"}

        await recorder._perform_action(mock_page, action)

        mock_page.hover.assert_called_once_with("#menu")

    @pytest.mark.asyncio
    async def test_perform_action_wait(self, recorder: BrowserRecorder) -> None:
        """Test wait action."""
        mock_page = AsyncMock()
        action = {"type": "wait", "duration": 0.1}

        with patch("animawatch.browser.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await recorder._perform_action(mock_page, action)
            mock_sleep.assert_called_once_with(0.1)

    @pytest.mark.asyncio
    async def test_perform_action_unknown_type(self, recorder: BrowserRecorder) -> None:
        """Test that unknown action types are ignored."""
        mock_page = AsyncMock()
        action = {"type": "unknown_action"}

        # Should not raise
        await recorder._perform_action(mock_page, action)

    @pytest.mark.asyncio
    async def test_perform_action_click_without_selector(
        self, recorder: BrowserRecorder
    ) -> None:
        """Test click action without selector does nothing."""
        mock_page = AsyncMock()
        action = {"type": "click"}

        await recorder._perform_action(mock_page, action)

        mock_page.click.assert_not_called()

