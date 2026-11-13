"""Tests for AnimaWatch browser automation module."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from animawatch.browser import (
    BrowserRecorder,
    InteractionResult,
    URLNotAllowedError,
    _build_timing,
    clamp_seconds,
    validate_url,
)
from animawatch.config import settings


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

        mock_page.evaluate.assert_called_once_with("(y) => window.scrollBy(0, y)", 300.0)

    @pytest.mark.asyncio
    async def test_scroll_never_formats_input_into_script(self, recorder: BrowserRecorder) -> None:
        """A non-numeric y is not interpolated into JavaScript (it was before)."""
        mock_page = AsyncMock()

        await recorder._perform_action(mock_page, {"type": "scroll", "y": "0); alert(1"})
        await recorder._perform_action(mock_page, {"type": "scroll", "y": float("inf")})

        for call in mock_page.evaluate.call_args_list:
            assert call.args == ("(y) => window.scrollBy(0, y)", 500.0)

    @pytest.mark.asyncio
    async def test_wait_is_capped_by_max_recording_duration(
        self, recorder: BrowserRecorder, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "max_recording_duration", 2)
        with patch("animawatch.browser.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await recorder._perform_action(AsyncMock(), {"type": "wait", "duration": 3600})
            mock_sleep.assert_called_once_with(2.0)

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
    async def test_perform_action_click_without_selector(self, recorder: BrowserRecorder) -> None:
        """Test click action without selector does nothing."""
        mock_page = AsyncMock()
        action = {"type": "click"}

        await recorder._perform_action(mock_page, action)

        mock_page.click.assert_not_called()


class TestValidateUrl:
    """Only http(s), and file:// when allowed, may be opened."""

    @pytest.mark.parametrize("url", ["https://example.com", "http://127.0.0.1:8000/x"])
    def test_http_allowed(self, url: str) -> None:
        assert validate_url(url) == url

    @pytest.mark.parametrize(
        "url",
        ["javascript:alert(1)", "data:text/html,<p>x", "chrome://settings", "about:blank", "x"],
    )
    def test_other_schemes_refused(self, url: str) -> None:
        with pytest.raises(URLNotAllowedError):
            validate_url(url)

    def test_file_urls_follow_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "allow_file_urls", True)
        assert validate_url("file:///tmp/page.html") == "file:///tmp/page.html"
        monkeypatch.setattr(settings, "allow_file_urls", False)
        with pytest.raises(URLNotAllowedError, match="not allowed"):
            validate_url("file:///tmp/page.html")


class TestClampSeconds:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1.5, 1.5),
            (-3, 0.0),
            (10_000, 30.0),
            ("2", 2.0),
            ("abc", 0.0),
            (None, 0.0),
            (float("nan"), 0.0),
        ],
    )
    def test_bounds(self, value: object, expected: float, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "max_recording_duration", 30)
        assert clamp_seconds(value) == expected


class TestLaunchAndRecord:
    @pytest.mark.asyncio
    async def test_start_uses_configured_executable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "browser_executable_path", "/opt/chrome/chrome")
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=AsyncMock())
        with patch("animawatch.browser.async_playwright") as mock_async_pw:
            mock_async_pw.return_value.start = AsyncMock(return_value=mock_playwright)
            await BrowserRecorder().start()
        kwargs = mock_playwright.chromium.launch.call_args.kwargs
        assert kwargs["executable_path"] == "/opt/chrome/chrome"

    @pytest.mark.asyncio
    async def test_record_interaction_returns_video_without_measuring(self) -> None:
        recorder = BrowserRecorder()
        result = InteractionResult(video_path=Path("/tmp/v.webm"), timing=None)
        with patch.object(recorder, "measure_interaction", AsyncMock(return_value=result)) as m:
            assert await recorder.record_interaction("https://example.com") == Path("/tmp/v.webm")
        assert m.call_args.kwargs["record_video"] is True
        assert m.call_args.kwargs["measure_frames"] is False

    @pytest.mark.asyncio
    async def test_record_interaction_raises_without_video(self) -> None:
        recorder = BrowserRecorder()
        result = InteractionResult(video_path=None, timing=None)
        with (
            patch.object(recorder, "measure_interaction", AsyncMock(return_value=result)),
            pytest.raises(RuntimeError, match="Failed to record video"),
        ):
            await recorder.record_interaction("https://example.com")

    @pytest.mark.asyncio
    async def test_refresh_interval_configured_and_cached(self) -> None:
        recorder = BrowserRecorder()
        page = AsyncMock()
        assert await recorder._refresh_interval(page, 50.0) == (20.0, "configured")
        page.evaluate.assert_not_called()

        page.evaluate = AsyncMock(return_value=[i * 10.0 for i in range(31)])
        assert await recorder._refresh_interval(page, None) == (10.0, "calibrated")
        assert await recorder._refresh_interval(page, None) == (10.0, "calibrated")
        page.evaluate.assert_awaited_once()  # cached for the browser's lifetime

    @pytest.mark.asyncio
    async def test_refresh_interval_calibration_failure(self) -> None:
        recorder = BrowserRecorder()
        page = AsyncMock()
        page.evaluate = AsyncMock(side_effect=RuntimeError("closed"))
        assert await recorder._refresh_interval(page, None) == (None, "estimated")


class TestBuildTiming:
    def _raw(self, **overrides: object) -> dict[str, object]:
        raw: dict[str, object] = {
            "timestamps": [100.0 + i * 16.7 for i in range(60)],
            "loaf": [],
            "loafSupported": True,
            "startedAt": 90.0,
            "timeOrigin": 1000.0,
            "overflow": False,
            "visibility": "visible",
        }
        raw.update(overrides)
        return raw

    def test_clean_window(self) -> None:
        result = _build_timing(self._raw(), 16.7, "calibrated", 1000.0, None, [])
        assert result.notes == ()
        assert result.jank_percentage == 0.0

    def test_navigation_overflow_and_hidden_are_noted(self) -> None:
        raw = self._raw(timeOrigin=2000.0, overflow=True, visibility="hidden")
        notes = " ".join(_build_timing(raw, 16.7, "calibrated", 1000.0, None, []).notes)
        assert "navigated" in notes
        assert "buffer filled" in notes
        assert "hidden" in notes

    def test_missing_collector(self) -> None:
        result = _build_timing(None, 16.7, "calibrated", 1000.0, None, [])
        assert result.frames_presented == 0
        assert any("collector was not present" in n for n in result.notes)

    def test_estimates_interval_when_calibration_failed(self) -> None:
        result = _build_timing(self._raw(), None, "estimated", 1000.0, None, [])
        assert result.refresh_source == "estimated"
        assert result.refresh_interval_ms == pytest.approx(16.7)

    def test_assumes_60hz_when_nothing_to_estimate_from(self) -> None:
        result = _build_timing(self._raw(timestamps=[]), None, "estimated", 1000.0, None, [])
        assert result.refresh_source == "assumed"
        assert result.refresh_interval_ms == pytest.approx(1000 / 60)
