"""Tests for AnimaWatch MCP server module."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from animawatch.server import (
    ANIMATION_PROMPT,
    AppContext,
    accessibility_check,
    animation_diagnosis,
    get_analysis,
    get_config,
    get_recording,
    page_analysis,
)


class TestAppContext:
    """Tests for AppContext dataclass."""

    def test_app_context_creation(self) -> None:
        """Test AppContext can be created with required fields."""
        mock_browser = MagicMock()
        mock_vision = MagicMock()

        ctx = AppContext(browser=mock_browser, vision=mock_vision)

        assert ctx.browser is mock_browser
        assert ctx.vision is mock_vision
        assert ctx.recordings == {}
        assert ctx.analyses == {}

    def test_app_context_with_data(self) -> None:
        """Test AppContext can store recordings and analyses."""
        mock_browser = MagicMock()
        mock_vision = MagicMock()

        ctx = AppContext(
            browser=mock_browser,
            vision=mock_vision,
            recordings={"abc123": Path("/tmp/video.webm")},
            analyses={"abc123": "Analysis result"},
        )

        assert "abc123" in ctx.recordings
        assert ctx.recordings["abc123"] == Path("/tmp/video.webm")
        assert ctx.analyses["abc123"] == "Analysis result"


class TestPrompts:
    """Tests for MCP prompt templates."""

    def test_animation_diagnosis_default(self) -> None:
        """Test animation_diagnosis returns base prompt by default."""
        result = animation_diagnosis()
        assert result == ANIMATION_PROMPT

    def test_animation_diagnosis_with_focus(self) -> None:
        """Test animation_diagnosis adds focus area."""
        result = animation_diagnosis(focus_area="modal animations")
        assert ANIMATION_PROMPT in result
        assert "FOCUS SPECIFICALLY ON" in result
        assert "modal animations" in result

    def test_animation_diagnosis_with_all_focus(self) -> None:
        """Test animation_diagnosis with 'all' returns base prompt."""
        result = animation_diagnosis(focus_area="all")
        assert result == ANIMATION_PROMPT
        assert "FOCUS SPECIFICALLY ON" not in result

    def test_page_analysis_default(self) -> None:
        """Test page_analysis returns prompt with default aspects."""
        result = page_analysis()
        assert "layout, colors, typography, spacing" in result
        assert "UI/UX designer" in result

    def test_page_analysis_custom_aspects(self) -> None:
        """Test page_analysis with custom aspects."""
        result = page_analysis(aspects="buttons, forms, navigation")
        assert "buttons, forms, navigation" in result

    def test_accessibility_check_prompt(self) -> None:
        """Test accessibility_check returns accessibility-focused prompt."""
        result = accessibility_check()
        assert "accessibility expert" in result
        assert "Color contrast" in result
        assert "Touch target sizes" in result


class TestResources:
    """Tests for MCP resources."""

    def test_get_recording_found(self) -> None:
        """Test get_recording returns info when recording exists."""
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context = AppContext(
            browser=MagicMock(),
            vision=MagicMock(),
            recordings={"abc123": Path("/tmp/video.webm")},
            analyses={},
        )

        result = get_recording("abc123", mock_ctx)

        assert "abc123" in result
        assert "/tmp/video.webm" in result

    def test_get_recording_not_found(self) -> None:
        """Test get_recording returns not found message."""
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context = AppContext(
            browser=MagicMock(),
            vision=MagicMock(),
            recordings={},
            analyses={},
        )

        result = get_recording("nonexistent", mock_ctx)

        assert "not found" in result
        assert "nonexistent" in result

    def test_get_analysis_found(self) -> None:
        """Test get_analysis returns analysis when it exists."""
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context = AppContext(
            browser=MagicMock(),
            vision=MagicMock(),
            recordings={},
            analyses={"abc123": "This is the analysis result"},
        )

        result = get_analysis("abc123", mock_ctx)

        assert result == "This is the analysis result"

    def test_get_analysis_not_found(self) -> None:
        """Test get_analysis returns not found message."""
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context = AppContext(
            browser=MagicMock(),
            vision=MagicMock(),
            recordings={},
            analyses={},
        )

        result = get_analysis("nonexistent", mock_ctx)

        assert "not found" in result

    def test_get_config_returns_settings(self) -> None:
        """Test get_config returns current configuration."""
        with patch("animawatch.server.settings") as mock_settings:
            mock_settings.vision_provider = "gemini"
            mock_settings.vision_model = "gemini-2.0-flash"
            mock_settings.browser_headless = True
            mock_settings.video_width = 1280
            mock_settings.video_height = 720
            mock_settings.max_recording_duration = 30

            result = get_config()

            assert "gemini" in result
            assert "1280x720" in result
            assert "30" in result


class TestTools:
    """Tests for MCP tools."""

    @pytest.fixture
    def mock_app_context(self) -> AppContext:
        """Create a mock AppContext for testing tools."""
        mock_browser = AsyncMock()
        mock_browser.record_interaction = AsyncMock(return_value=Path("/tmp/video.webm"))
        mock_browser.take_screenshot = AsyncMock(return_value=Path("/tmp/screenshot.png"))

        mock_vision = AsyncMock()
        mock_vision.analyze_video = AsyncMock(return_value="Video analysis result")
        mock_vision.analyze_image = AsyncMock(return_value="Image analysis result")

        return AppContext(
            browser=mock_browser,
            vision=mock_vision,
            recordings={},
            analyses={},
        )

    @pytest.fixture
    def mock_ctx(self, mock_app_context: AppContext) -> MagicMock:
        """Create a mock Context for testing tools."""
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context = mock_app_context
        return mock_ctx

    @pytest.mark.asyncio
    async def test_watch_records_and_analyzes(
        self, mock_ctx: MagicMock, mock_app_context: AppContext
    ) -> None:
        """Test watch tool records and analyzes video."""
        from animawatch.server import watch

        with patch("animawatch.server.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = MagicMock(hex="abc12345")
            mock_uuid.return_value.__str__ = lambda self: "abc12345-6789-0123-4567-890123456789"

            result = await watch(
                url="https://example.com",
                ctx=mock_ctx,
            )

            # Verify the result contains expected structural elements
            assert result.startswith("## 🎬 Animation Analysis")
            assert "Analysis ID" in result
            assert "abc12345" in result  # Check the mocked UUID is present
            mock_app_context.browser.record_interaction.assert_called_once()  # type: ignore[attr-defined]
            mock_app_context.vision.analyze_video.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_watch_without_context_raises(self) -> None:
        """Test watch raises when context is None."""
        from animawatch.server import watch

        with pytest.raises(RuntimeError, match="Context is required"):
            await watch(url="https://example.com", ctx=None)

    @pytest.mark.asyncio
    async def test_watch_saves_recording_when_requested(
        self, mock_ctx: MagicMock, mock_app_context: AppContext
    ) -> None:
        """Test watch saves recording when save_recording=True."""
        from animawatch.server import watch

        await watch(
            url="https://example.com",
            save_recording=True,
            ctx=mock_ctx,
        )

        # Recording should be stored
        assert len(mock_app_context.recordings) == 1

    @pytest.mark.asyncio
    async def test_analyze_video_tool(
        self, mock_ctx: MagicMock, mock_app_context: AppContext, tmp_path: Path
    ) -> None:
        """Test analyze_video tool analyzes existing video."""
        from animawatch.server import analyze_video

        video_path = tmp_path / "test.webm"
        video_path.write_bytes(b"fake video")

        result = await analyze_video(
            video_path=str(video_path),
            ctx=mock_ctx,
        )

        assert "Video Analysis" in result
        mock_app_context.vision.analyze_video.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_analyze_video_not_found(self, mock_ctx: MagicMock) -> None:
        """Test analyze_video returns error for missing file."""
        from animawatch.server import analyze_video

        result = await analyze_video(
            video_path="/nonexistent/video.webm",
            ctx=mock_ctx,
        )

        assert "not found" in result

    @pytest.mark.asyncio
    async def test_record_tool(self, mock_ctx: MagicMock, mock_app_context: AppContext) -> None:
        """Test record tool records without analysis."""
        from animawatch.server import record

        result = await record(
            url="https://example.com",
            ctx=mock_ctx,
        )

        assert "Recording Complete" in result
        mock_app_context.browser.record_interaction.assert_called_once()  # type: ignore[attr-defined]
        # Vision should NOT be called for record-only
        mock_app_context.vision.analyze_video.assert_not_called()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_check_accessibility_tool(
        self, mock_ctx: MagicMock, mock_app_context: AppContext
    ) -> None:
        """Test check_accessibility tool."""
        from animawatch.server import check_accessibility

        result = await check_accessibility(
            url="https://example.com",
            ctx=mock_ctx,
        )

        assert "Accessibility Analysis" in result
        mock_app_context.browser.take_screenshot.assert_called_once()  # type: ignore[attr-defined]
        mock_app_context.vision.analyze_image.assert_called_once()  # type: ignore[attr-defined]
