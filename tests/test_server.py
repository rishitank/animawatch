"""Tests for AnimaWatch MCP server module."""

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from animawatch.consensus import ConsensusResult
from animawatch.fps import FPSAnalysisResult, JankEvent
from animawatch.metrics import CoreWebVitals, PerformanceMetrics
from animawatch.models import Finding, IssueCategory, Severity
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
    """Tests for MCP tools (fixtures ``mock_app_context``/``mock_ctx`` live in conftest)."""

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
            cast(AsyncMock, mock_app_context.browser.record_interaction).assert_called_once()
            cast(AsyncMock, mock_app_context.vision.analyze_video).assert_called_once()

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
        cast(AsyncMock, mock_app_context.vision.analyze_video).assert_called_once()

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
        cast(AsyncMock, mock_app_context.browser.record_interaction).assert_called_once()
        # Vision should NOT be called for record-only
        cast(AsyncMock, mock_app_context.vision.analyze_video).assert_not_called()

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
        cast(AsyncMock, mock_app_context.browser.take_screenshot).assert_called_once()
        cast(AsyncMock, mock_app_context.vision.analyze_image).assert_called_once()


class TestNewTools:
    """Tests for new MCP tools (devices, diff, fps, metrics, consensus)."""

    @pytest.mark.asyncio
    async def test_list_devices_all(self) -> None:
        """Test list_devices returns all devices."""
        from animawatch.server import list_devices

        result = await list_devices()

        assert "Available Device Profiles" in result
        assert "iphone" in result.lower() or "pixel" in result.lower()

    @pytest.mark.asyncio
    async def test_list_devices_by_category(self) -> None:
        """Test list_devices filters by category."""
        from animawatch.server import list_devices

        result = await list_devices(category="mobile")

        assert "Available Device Profiles" in result
        assert "**Category**: mobile" in result
        # Mobile profiles are listed; tablet and desktop profiles are filtered out.
        assert "**iphone_15_pro**" in result
        assert "**pixel_8**" in result
        assert "**ipad_pro_12**" not in result
        assert "**desktop_1080p**" not in result

    @pytest.mark.asyncio
    async def test_list_devices_invalid_category(self) -> None:
        """Test list_devices with invalid category."""
        from animawatch.server import list_devices

        result = await list_devices(category="invalid")

        assert "Invalid category" in result

    @pytest.mark.asyncio
    async def test_watch_with_device_valid(
        self, mock_ctx: MagicMock, mock_app_context: AppContext
    ) -> None:
        """Test watch_with_device with valid device."""
        from animawatch.server import watch_with_device

        with patch("animawatch.server.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = MagicMock()
            mock_uuid.return_value.__str__ = lambda self: "abc12345-6789"

            result = await watch_with_device(
                url="https://example.com",
                device="iphone_15_pro",
                ctx=mock_ctx,
            )

            assert "Device Animation Analysis" in result
            assert "iPhone 15 Pro" in result
            # The selected device is forwarded to the recorder.
            record = cast(AsyncMock, mock_app_context.browser.record_interaction)
            record.assert_called_once()
            assert record.call_args.kwargs["device"] == "iphone_15_pro"
            assert record.call_args.kwargs["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_watch_with_device_invalid(
        self, mock_ctx: MagicMock, mock_app_context: AppContext
    ) -> None:
        """Test watch_with_device with invalid device."""
        from animawatch.server import watch_with_device

        result = await watch_with_device(
            url="https://example.com",
            device="invalid_device",
            ctx=mock_ctx,
        )

        assert "not found" in result
        assert "Available devices" in result

    @pytest.mark.asyncio
    async def test_watch_with_device_without_context(self) -> None:
        """Test watch_with_device raises without context."""
        from animawatch.server import watch_with_device

        with pytest.raises(RuntimeError, match="Context is required"):
            await watch_with_device(
                url="https://example.com",
                device="iphone_15_pro",
                ctx=None,
            )

    @pytest.mark.asyncio
    async def test_analyze_fps_file_not_found(self) -> None:
        """Test analyze_fps with non-existent file."""
        from animawatch.server import analyze_fps

        result = await analyze_fps(video_path="/nonexistent/video.mp4")

        assert "Video not found" in result

    @pytest.mark.asyncio
    async def test_get_performance_metrics_without_context(self) -> None:
        """Test get_performance_metrics raises without context."""
        from animawatch.server import get_performance_metrics

        with pytest.raises(RuntimeError, match="Context is required"):
            await get_performance_metrics(url="https://example.com", ctx=None)

    @pytest.mark.asyncio
    async def test_analyze_with_consensus_without_context(self) -> None:
        """Test analyze_with_consensus_tool raises without context."""
        from animawatch.server import analyze_with_consensus_tool

        with pytest.raises(RuntimeError, match="Context is required"):
            await analyze_with_consensus_tool(url="https://example.com", ctx=None)

    @pytest.mark.asyncio
    async def test_compare_screenshots_without_context(self) -> None:
        """Test compare_screenshots raises without context."""
        from animawatch.server import compare_screenshots

        with pytest.raises(RuntimeError, match="Context is required"):
            await compare_screenshots(
                url1="https://example.com",
                url2="https://example.org",
                ctx=None,
            )

    # ------------------------------------------------------------------
    # Happy paths for the new tools
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_analyze_fps_reports_results(self, tmp_path: Path) -> None:
        """analyze_fps passes its arguments through and renders the FPS report."""
        from animawatch.server import analyze_fps

        video = tmp_path / "recording.webm"
        video.write_bytes(b"fake video")
        fps_result = FPSAnalysisResult(
            average_fps=58.5,
            target_fps=30.0,
            min_fps=40.0,
            max_fps=60.0,
            total_frames=117,
            jank_events=[
                JankEvent(
                    frame_number=42,
                    timestamp_ms=700.0,
                    expected_delta_ms=33.3,
                    actual_delta_ms=50.0,
                    severity="minor",
                    dropped_frames=1,
                )
            ],
            jank_percentage=0.85,
            frame_time_consistency=92.0,
            duration_ms=2000.0,
        )

        with patch(
            "animawatch.server.analyze_video_fps", AsyncMock(return_value=fps_result)
        ) as mock_analyze:
            result = await analyze_fps(
                video_path=str(video), target_fps=30.0, jank_threshold_ms=8.0
            )

        mock_analyze.assert_awaited_once_with(video, 30.0, 8.0)
        assert result.startswith("## 🎯 FPS Analysis")
        assert "**Average FPS**: 58.5 (target: 30.0)" in result
        assert "**Jank Events**: 1" in result
        assert "Frame 42 @ 700ms" in result

    @pytest.mark.asyncio
    async def test_get_performance_metrics_reports_and_stores(
        self, mock_ctx: MagicMock, mock_app_context: AppContext, mock_page: MagicMock
    ) -> None:
        """get_performance_metrics navigates a pooled page and stores the report."""
        from animawatch.server import get_performance_metrics

        metrics = PerformanceMetrics(
            url="https://example.com",
            core_web_vitals=CoreWebVitals(lcp_ms=1800.0, fcp_ms=900.0, cls_score=0.02),
            load_time_ms=2100.0,
            dom_content_loaded_ms=1200.0,
            resource_count=12,
            total_transfer_size_kb=340.0,
        )

        with patch(
            "animawatch.server.extract_performance_metrics", AsyncMock(return_value=metrics)
        ) as mock_extract:
            result = await get_performance_metrics(url="https://example.com", ctx=mock_ctx)

        cast(MagicMock, mock_app_context.browser.pooled_context).assert_called_once_with()
        mock_page.goto.assert_awaited_once_with("https://example.com", wait_until="networkidle")
        mock_extract.assert_awaited_once_with(mock_page, "https://example.com")
        assert result.startswith("**Analysis ID**: `")
        assert "Performance Metrics Report" in result
        assert "LCP" in result
        assert len(mock_app_context.analyses) == 1
        (stored,) = mock_app_context.analyses.values()
        assert result.endswith(stored)

    @pytest.mark.asyncio
    async def test_analyze_with_consensus_reports_findings(
        self, mock_ctx: MagicMock, mock_app_context: AppContext, tmp_path: Path
    ) -> None:
        """analyze_with_consensus_tool renders agreed and single-model findings."""
        from animawatch.server import analyze_with_consensus_tool

        screenshot = tmp_path / "consensus.png"
        screenshot.write_bytes(b"fake png")
        mock_app_context.browser.take_screenshot = AsyncMock(return_value=screenshot)

        agreed = Finding(
            id="f1",
            category=IssueCategory.ANIMATION,
            severity=Severity.MAJOR,
            confidence=90,
            element="hero banner",
            description="Banner stutters while sliding in",
            suggestion="Animate transform instead of left",
        )
        gemini_only = Finding(
            id="f2",
            category=IssueCategory.LAYOUT,
            severity=Severity.MINOR,
            confidence=60,
            element="footer",
            description="Footer shifts after fonts load",
            suggestion="Reserve space for the footer",
        )
        consensus = ConsensusResult(
            merged_findings=[agreed, gemini_only],
            gemini_only=[gemini_only],
            ollama_only=[],
            agreed_findings=[agreed],
            gemini_result=None,
            ollama_result=None,
            consensus_score=50.0,
        )

        with patch(
            "animawatch.server.run_consensus_analysis", AsyncMock(return_value=consensus)
        ) as mock_consensus:
            result = await analyze_with_consensus_tool(
                url="https://example.com", focus="timing", ctx=mock_ctx
            )

        mock_consensus.assert_awaited_once()
        assert mock_consensus.await_args is not None
        assert mock_consensus.await_args.args[0] == screenshot
        assert "**Consensus Score**: 50%" in result
        assert "**major** [animation]: Banner stutters while sliding in" in result
        assert "Animate transform instead of left" in result
        assert "Gemini-Only Findings" in result
        assert "Ollama-Only Findings" not in result
        assert not screenshot.exists()  # temporary screenshot is cleaned up
        assert list(mock_app_context.analyses.values()) == [result]

    @staticmethod
    def _write_png(path: Path, square: bool) -> Path:
        """Write a 40x40 white PNG, optionally with a 20x20 black square at (10, 10)."""
        image = Image.new("RGB", (40, 40), "white")
        if square:
            image.paste((0, 0, 0), (10, 10, 30, 30))
        image.save(path)
        return path

    @pytest.mark.asyncio
    async def test_compare_screenshots_detects_differences(
        self, mock_ctx: MagicMock, mock_app_context: AppContext, tmp_path: Path
    ) -> None:
        """compare_screenshots reports the differing region and cleans up screenshots."""
        from animawatch.server import compare_screenshots

        before = self._write_png(tmp_path / "before.png", square=False)
        after = self._write_png(tmp_path / "after.png", square=True)
        mock_app_context.browser.take_screenshot = AsyncMock(side_effect=[before, after])

        result = await compare_screenshots(
            url1="https://example.com", url2="https://example.org", ctx=mock_ctx
        )

        # Locate the generated diff image first so it is removed even if an assertion fails.
        marker = "Diff image saved: `"
        diff_image = Path(result.rsplit(marker, 1)[1].rstrip("`")) if marker in result else None
        try:
            assert "Differences detected!" in result
            assert "**Diff Percentage**: 25.00%" in result  # 400 of 1600 pixels
            assert "**Region 1**: (10, 10) 20x20" in result
            assert not before.exists()
            assert not after.exists()
            assert diff_image is not None
            assert diff_image.exists()
        finally:
            if diff_image is not None:
                diff_image.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_compare_screenshots_identical(
        self, mock_ctx: MagicMock, mock_app_context: AppContext, tmp_path: Path
    ) -> None:
        """compare_screenshots reports no differences for identical pages."""
        from animawatch.server import compare_screenshots

        before = self._write_png(tmp_path / "before.png", square=True)
        after = self._write_png(tmp_path / "after.png", square=True)
        mock_app_context.browser.take_screenshot = AsyncMock(side_effect=[before, after])

        result = await compare_screenshots(
            url1="https://example.com", url2="https://example.com", ctx=mock_ctx
        )

        assert "No visual differences detected!" in result
        assert "Similarity: 100.0%" in result
