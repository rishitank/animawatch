"""Tests for AnimaWatch MCP server module."""

from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.utilities.types import Image

from animawatch import billing
from animawatch.browser import InteractionResult
from animawatch.fps import analyze_frame_timestamps
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

SMOOTH = analyze_frame_timestamps(
    [i * 1000 / 60 for i in range(181)], 1000 / 60, refresh_source="calibrated"
)


class RecordingMeter:
    """A meter that records charges and can be set to refuse."""

    def __init__(self, remaining: int | None = None) -> None:
        self._remaining = remaining
        self.charges: list[tuple[str, int]] = []

    async def remaining(self, event: str) -> int | None:
        return self._remaining

    async def charge(self, event: str, count: int) -> None:
        self.charges.append((event, count))


@pytest.fixture
def meter() -> Iterator[RecordingMeter]:
    recording = RecordingMeter()
    billing.set_meter(recording)
    try:
        yield recording
    finally:
        billing.set_meter(billing.NoopMeter())


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
            mock_settings.vision_model = "gemini-3.8-flash"
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
    def recording(self, tmp_path: Path) -> Path:
        """A recording file owned by the test, for tools that delete unsaved videos."""
        path = tmp_path / "video.webm"
        path.write_bytes(b"video")
        return path

    @pytest.fixture
    def mock_app_context(self, recording: Path, tmp_path: Path) -> AppContext:
        """Create a mock AppContext for testing tools."""
        mock_browser = AsyncMock()
        mock_browser.record_interaction = AsyncMock(return_value=recording)
        mock_browser.measure_interaction = AsyncMock(
            return_value=InteractionResult(video_path=recording, timing=SMOOTH)
        )
        mock_browser.take_screenshot = AsyncMock(return_value=tmp_path / "screenshot.png")

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
        self, mock_ctx: MagicMock, mock_app_context: AppContext, recording: Path
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
            assert "### Frame timing" in result
            assert "Dropped frames**: 0 of 180" in result
            assert "### Vision analysis" in result
            assert "Video analysis result" in result
            measure = cast(AsyncMock, mock_app_context.browser.measure_interaction)
            measure.assert_called_once()
            assert measure.call_args.kwargs["record_video"] is True
            cast(AsyncMock, mock_app_context.vision.analyze_video).assert_called_once()
            # The recording is deleted when not saved
            assert mock_app_context.recordings == {}
            assert not recording.exists()

    @pytest.mark.asyncio
    async def test_watch_without_context_raises(self) -> None:
        """Test watch raises when context is None."""
        from animawatch.server import watch

        with pytest.raises(RuntimeError, match="Context is required"):
            await watch(url="https://example.com", ctx=None)

    @pytest.mark.asyncio
    async def test_watch_saves_recording_when_requested(
        self, mock_ctx: MagicMock, mock_app_context: AppContext, recording: Path
    ) -> None:
        """Test watch saves recording when save_recording=True."""
        from animawatch.server import watch

        await watch(
            url="https://example.com",
            save_recording=True,
            ctx=mock_ctx,
        )

        # Recording should be stored, and kept on disk
        assert list(mock_app_context.recordings.values()) == [recording]
        assert recording.exists()

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


class TestFrameTimingAndVisionOff:
    """Tools after the switch to in-page timing, with and without vision."""

    @pytest.fixture
    def app_ctx(self) -> AppContext:
        browser = AsyncMock()
        browser.measure_interaction = AsyncMock(
            return_value=InteractionResult(video_path=None, timing=SMOOTH)
        )
        browser.take_screenshot = AsyncMock()
        return AppContext(
            browser=browser,
            vision=None,
            vision_unavailable_reason="Vision is off: GEMINI_API_KEY is not set.",
        )

    @pytest.fixture
    def ctx(self, app_ctx: AppContext) -> MagicMock:
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context = app_ctx
        return mock_ctx

    @pytest.mark.asyncio
    async def test_analyze_fps_measures_in_page_and_charges_once(
        self, ctx: MagicMock, app_ctx: AppContext, meter: RecordingMeter
    ) -> None:
        from animawatch.server import analyze_fps

        result = await analyze_fps(
            url="https://example.com",
            duration=2.0,
            refresh_rate_hz=120.0,
            trace_compositor=True,
            ctx=ctx,
        )

        assert "Frame Timing for https://example.com" in result
        assert "Verdict**: smooth" in result
        kwargs = cast(AsyncMock, app_ctx.browser.measure_interaction).call_args.kwargs
        assert kwargs["refresh_rate_hz"] == 120.0
        assert kwargs["trace_compositor"] is True
        assert "record_video" not in kwargs  # no video for timing
        assert meter.charges == [(billing.PAGE_ANALYSED, 1)]

    @pytest.mark.asyncio
    async def test_analyze_fps_rejects_bad_input_without_charging(
        self, ctx: MagicMock, meter: RecordingMeter
    ) -> None:
        from animawatch.server import analyze_fps

        with pytest.raises(ToolError, match="not allowed"):
            await analyze_fps(url="javascript:alert(1)", ctx=ctx)
        with pytest.raises(ToolError, match="refresh_rate_hz"):
            await analyze_fps(url="https://example.com", refresh_rate_hz=5000, ctx=ctx)
        assert "not found" in await analyze_fps(url="https://example.com", device="nope", ctx=ctx)
        assert meter.charges == []

    @pytest.mark.asyncio
    async def test_spending_limit_refuses_before_loading(
        self, ctx: MagicMock, app_ctx: AppContext
    ) -> None:
        from animawatch.server import analyze_fps, compare_screenshots

        billing.set_meter(RecordingMeter(remaining=1))
        try:
            with pytest.raises(ToolError, match="spending limit"):
                await compare_screenshots(
                    url1="https://a.example", url2="https://b.example", ctx=ctx
                )
            billing.set_meter(RecordingMeter(remaining=0))
            with pytest.raises(ToolError, match="spending limit"):
                await analyze_fps(url="https://example.com", ctx=ctx)
        finally:
            billing.set_meter(billing.NoopMeter())
        cast(AsyncMock, app_ctx.browser.measure_interaction).assert_not_called()
        cast(AsyncMock, app_ctx.browser.take_screenshot).assert_not_called()

    @pytest.mark.asyncio
    async def test_watch_without_vision_returns_timing_only(
        self, ctx: MagicMock, app_ctx: AppContext, meter: RecordingMeter
    ) -> None:
        from animawatch.server import watch

        result = await watch(url="https://example.com", ctx=ctx)

        assert "### Frame timing" in result
        assert "GEMINI_API_KEY is not set" in result
        assert "Frame timing only" in result
        kwargs = cast(AsyncMock, app_ctx.browser.measure_interaction).call_args.kwargs
        assert kwargs["record_video"] is False  # no vision, no recording needed
        assert meter.charges == [(billing.PAGE_ANALYSED, 1)]

    @pytest.mark.asyncio
    async def test_watch_with_device_measures_with_device(
        self, ctx: MagicMock, app_ctx: AppContext, meter: RecordingMeter
    ) -> None:
        from animawatch.server import watch_with_device

        result = await watch_with_device(url="https://example.com", device="iphone_15_pro", ctx=ctx)

        assert "Device Animation Analysis" in result
        assert "### Frame timing" in result
        kwargs = cast(AsyncMock, app_ctx.browser.measure_interaction).call_args.kwargs
        assert kwargs["device"] == "iphone_15_pro"
        assert meter.charges == [(billing.PAGE_ANALYSED, 1)]

    @pytest.mark.asyncio
    async def test_vision_tools_explain_how_to_turn_vision_on(
        self, ctx: MagicMock, app_ctx: AppContext, tmp_path: Path, meter: RecordingMeter
    ) -> None:
        from animawatch.server import analyze_video, check_accessibility

        with pytest.raises(ToolError, match="paid key"):
            await check_accessibility(url="https://example.com", ctx=ctx)
        with pytest.raises(ToolError, match="VISION_PROVIDER=ollama"):
            await analyze_video(video_path=str(tmp_path / "v.webm"), ctx=ctx)
        cast(AsyncMock, app_ctx.browser.take_screenshot).assert_not_called()
        assert meter.charges == []

    @pytest.mark.asyncio
    async def test_screenshot_without_vision_still_returns_image(
        self, ctx: MagicMock, app_ctx: AppContext, tmp_path: Path, meter: RecordingMeter
    ) -> None:
        from animawatch.server import screenshot

        shot = tmp_path / "shot.png"
        shot.write_bytes(b"\x89PNG fake")
        cast(AsyncMock, app_ctx.browser.take_screenshot).return_value = shot

        image = await screenshot(url="https://example.com", ctx=ctx)

        assert isinstance(image, Image)
        assert not shot.exists()  # temp file removed
        assert any("GEMINI_API_KEY" in a for a in app_ctx.analyses.values())
        assert meter.charges == [(billing.PAGE_ANALYSED, 1)]

    @pytest.mark.asyncio
    async def test_compare_screenshots_charges_two_pages(
        self, ctx: MagicMock, app_ctx: AppContext, tmp_path: Path, meter: RecordingMeter
    ) -> None:
        from PIL import Image as PILImage

        from animawatch.server import compare_screenshots

        shots = []
        for name in ("a.png", "b.png"):
            path = tmp_path / name
            PILImage.new("RGB", (20, 20), "white").save(path)
            shots.append(path)
        cast(AsyncMock, app_ctx.browser.take_screenshot).side_effect = shots

        result = await compare_screenshots(
            url1="https://a.example", url2="https://b.example", ctx=ctx
        )

        assert "No visual differences" in result
        assert meter.charges == [(billing.PAGE_ANALYSED, 2)]
        assert not any(p.exists() for p in shots)

    @pytest.mark.asyncio
    async def test_failed_work_is_not_charged(
        self, ctx: MagicMock, app_ctx: AppContext, meter: RecordingMeter
    ) -> None:
        from animawatch.server import analyze_fps

        cast(AsyncMock, app_ctx.browser.measure_interaction).side_effect = TimeoutError("slow")
        with pytest.raises(TimeoutError):
            await analyze_fps(url="https://example.com", ctx=ctx)
        assert meter.charges == []


class TestVisionProviderCreation:
    def test_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from animawatch.server import create_vision_provider, settings

        monkeypatch.setattr(settings, "vision_provider", "none")
        provider, reason = create_vision_provider()
        assert provider is None
        assert "turned off" in reason

    def test_missing_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from animawatch.server import create_vision_provider, settings

        monkeypatch.setattr(settings, "vision_provider", "gemini")
        monkeypatch.setattr(settings, "gemini_api_key", "")
        provider, reason = create_vision_provider()
        assert provider is None
        assert "GEMINI_API_KEY" in reason


class TestSharedLifespan:
    @pytest.mark.asyncio
    async def test_sessions_share_one_browser(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from animawatch import server

        started: list[MagicMock] = []

        def fake_recorder() -> MagicMock:
            recorder = MagicMock()
            recorder.start = AsyncMock()
            recorder.stop = AsyncMock()
            started.append(recorder)
            return recorder

        monkeypatch.setattr(server, "BrowserRecorder", fake_recorder)
        monkeypatch.setattr(server, "create_vision_provider", lambda: (None, "off"))

        async with server.app_lifespan(server.mcp) as first:
            async with server.app_lifespan(server.mcp) as second:
                assert first is second
            started[0].stop.assert_not_called()
        assert len(started) == 1
        started[0].stop.assert_awaited_once()

        async with server.app_lifespan(server.mcp) as third:
            assert third is not first  # a fresh context after the last session ended
        assert len(started) == 2


class TestHttpConfiguration:
    @staticmethod
    async def _verdict(security: object, host: str, origin: str | None = None) -> int:
        from mcp.server.transport_security import TransportSecurityMiddleware
        from starlette.requests import Request

        headers = [(b"host", host.encode())]
        if origin:
            headers.append((b"origin", origin.encode()))
        request = Request({"type": "http", "method": "GET", "headers": headers})
        response = await TransportSecurityMiddleware(security).validate_request(request)  # type: ignore[arg-type]
        return 200 if response is None else response.status_code

    @pytest.mark.asyncio
    async def test_wildcard_bind_keeps_rebinding_protection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from animawatch import server

        for name in ("host", "port", "transport_security"):
            monkeypatch.setattr(server.mcp.settings, name, getattr(server.mcp.settings, name))

        server.configure_http("0.0.0.0", 8765, ["mcp.example.com"])
        security = server.mcp.settings.transport_security
        assert security is not None and security.enable_dns_rebinding_protection
        assert server.mcp.settings.host == "0.0.0.0"

        assert await self._verdict(security, "localhost:8765") == 200
        assert await self._verdict(security, "mcp.example.com") == 200
        assert await self._verdict(security, "mcp.example.com", "https://mcp.example.com") == 200
        # A rebinding page: its own domain resolves to this machine.
        assert await self._verdict(security, "evil.example:8765") == 421
        assert await self._verdict(security, "localhost:8765", "http://evil.example") == 403

    @pytest.mark.asyncio
    async def test_specific_bind_address_is_allowed(self) -> None:
        from animawatch.server import http_security

        security = http_security("10.0.0.5", [])
        assert await self._verdict(security, "10.0.0.5:8765") == 200
        assert await self._verdict(security, "10.0.0.6:8765") == 421

    def test_allowed_hosts_setting_is_split(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from animawatch.config import Settings

        monkeypatch.setenv("ALLOWED_HOSTS", " a.example , ,b.example")
        assert Settings().allowed_hosts_list == ["a.example", "b.example"]


class TestCleanupAndConsensus:
    @pytest.mark.asyncio
    async def test_recording_deleted_when_vision_fails(
        self, tmp_path: Path, meter: RecordingMeter
    ) -> None:
        from animawatch.server import watch

        video = tmp_path / "v.webm"
        video.write_bytes(b"video")
        browser = AsyncMock()
        browser.measure_interaction = AsyncMock(
            return_value=InteractionResult(video_path=video, timing=SMOOTH)
        )
        vision = AsyncMock()
        vision.analyze_video = AsyncMock(side_effect=RuntimeError("quota"))
        ctx = MagicMock()
        ctx.request_context.lifespan_context = AppContext(browser=browser, vision=vision)

        with pytest.raises(RuntimeError, match="quota"):
            await watch(url="https://example.com", ctx=ctx)

        assert not video.exists()
        assert meter.charges == []

    @pytest.mark.asyncio
    async def test_consensus_with_no_model_is_an_error_not_a_clean_bill(
        self, tmp_path: Path, meter: RecordingMeter
    ) -> None:
        from animawatch.consensus import ConsensusResult
        from animawatch.server import analyze_with_consensus_tool

        shot = tmp_path / "s.png"
        shot.write_bytes(b"png")
        browser = AsyncMock()
        browser.take_screenshot = AsyncMock(return_value=shot)
        ctx = MagicMock()
        ctx.request_context.lifespan_context = AppContext(browser=browser, vision=None)
        empty = ConsensusResult([], [], [], [], None, None, 100.0)

        with (
            patch("animawatch.server.run_consensus_analysis", AsyncMock(return_value=empty)),
            pytest.raises(ToolError, match="Neither Gemini nor Ollama"),
        ):
            await analyze_with_consensus_tool(url="https://example.com", ctx=ctx)
        assert not shot.exists()
        assert meter.charges == []


class TestBoundedStores:
    def test_oldest_entries_are_dropped(self) -> None:
        from animawatch.server import BoundedStore

        store: BoundedStore[str] = BoundedStore(2)
        store["a"], store["b"], store["c"] = "1", "2", "3"
        assert list(store) == ["b", "c"]
        store["b"] = "updated"  # re-setting refreshes recency
        store["d"] = "4"
        assert list(store) == ["b", "d"]

    def test_evicted_recordings_are_deleted(self, tmp_path: Path) -> None:
        from animawatch import server

        ctx = AppContext(browser=MagicMock(), vision=None)
        assert isinstance(ctx.recordings, server.BoundedStore)
        files = []
        for i in range(server.MAX_STORED_RECORDINGS + 1):
            path = tmp_path / f"{i}.webm"
            path.write_bytes(b"v")
            files.append(path)
            ctx.recordings[str(i)] = path
        assert not files[0].exists()
        assert all(p.exists() for p in files[1:])
        assert len(ctx.recordings) == server.MAX_STORED_RECORDINGS

    def test_analyses_are_bounded(self) -> None:
        from animawatch import server

        ctx = AppContext(browser=MagicMock(), vision=None, analyses={"seed": "x"})
        for i in range(server.MAX_STORED_ANALYSES + 5):
            ctx.analyses[str(i)] = "report"
        assert len(ctx.analyses) == server.MAX_STORED_ANALYSES
        assert "seed" not in ctx.analyses


class TestHostedCompare:
    @pytest.mark.asyncio
    async def test_no_diff_image_when_hosted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PIL import Image as PILImage

        from animawatch import server

        shots = []
        for name, colour in (("a.png", "white"), ("b.png", "black")):
            path = tmp_path / name
            PILImage.new("RGB", (20, 20), colour).save(path)
            shots.append(path)
        browser = AsyncMock()
        browser.take_screenshot = AsyncMock(side_effect=shots)
        ctx = MagicMock()
        ctx.request_context.lifespan_context = AppContext(browser=browser, vision=None)
        monkeypatch.setattr(server.settings, "hosted", True)

        result = await server.compare_screenshots(
            url1="https://a.example", url2="https://b.example", ctx=ctx
        )

        assert "Differences detected" in result
        assert "Diff image saved" not in result


class TestConsensusReporting:
    @pytest.fixture
    def ctx(self, tmp_path: Path) -> MagicMock:
        shot = tmp_path / "s.png"
        shot.write_bytes(b"png")
        browser = AsyncMock()
        browser.take_screenshot = AsyncMock(return_value=shot)
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context = AppContext(browser=browser, vision=None)
        return mock_ctx

    @pytest.mark.asyncio
    async def test_vision_off_refuses_before_any_screenshot(
        self, ctx: MagicMock, monkeypatch: pytest.MonkeyPatch, meter: RecordingMeter
    ) -> None:
        from animawatch import server

        monkeypatch.setattr(server.settings, "vision_provider", "none")
        monkeypatch.setattr(server.settings, "gemini_api_key", "a-stored-key")
        with (
            patch("animawatch.server.run_consensus_analysis", AsyncMock()) as consensus,
            pytest.raises(ToolError, match="Vision is turned off"),
        ):
            await server.analyze_with_consensus_tool(url="https://example.com", ctx=ctx)
        consensus.assert_not_called()
        app_ctx = ctx.request_context.lifespan_context
        cast(AsyncMock, app_ctx.browser.take_screenshot).assert_not_called()
        assert meter.charges == []

    @pytest.mark.asyncio
    async def test_one_model_is_not_reported_as_agreement(
        self, ctx: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from animawatch import server
        from animawatch.consensus import ConsensusResult
        from animawatch.models import AnalysisMetadata, AnalysisResult

        monkeypatch.setattr(server.settings, "vision_provider", "gemini")
        ollama_only = AnalysisResult(
            id="o",
            success=True,
            findings=[],
            summary="clean",
            overall_score=100,
            metadata=AnalysisMetadata(provider="ollama", model="m", analysis_duration_ms=1),
        )
        result = ConsensusResult([], [], [], [], None, ollama_only, 100.0)
        with patch("animawatch.server.run_consensus_analysis", AsyncMock(return_value=result)):
            output = await server.analyze_with_consensus_tool(url="https://example.com", ctx=ctx)

        assert "Consensus Score" not in output
        assert "Gemini did not return an analysis" in output
        assert "Ollama found no issues" in output
        assert "either model" not in output


class TestToolActionValidation:
    @pytest.mark.asyncio
    async def test_bad_actions_are_refused_before_work_or_charge(
        self, meter: RecordingMeter
    ) -> None:
        from animawatch.server import analyze_fps, watch

        browser = AsyncMock()
        ctx = MagicMock()
        ctx.request_context.lifespan_context = AppContext(browser=browser, vision=None)
        bad = [{"type": "click"}]  # no selector

        with pytest.raises(ToolError, match="Invalid actions"):
            await analyze_fps(url="https://example.com", actions=bad, ctx=ctx)  # type: ignore[arg-type]
        with pytest.raises(ToolError, match="Invalid actions"):
            await watch(url="https://example.com", actions=bad, ctx=ctx)  # type: ignore[arg-type]
        cast(AsyncMock, browser.measure_interaction).assert_not_called()
        assert meter.charges == []
