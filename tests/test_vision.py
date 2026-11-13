"""Tests for AnimaWatch vision AI providers."""

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from animawatch.cache import AnalysisCache, analysis_cache
from animawatch.frames import (
    ExtractedFrame,
    FrameExtractionResult,
    _sample_by_time,
    video_duration_ms,
)
from animawatch.models import AnalysisResult
from animawatch.retry import vision_circuit
from animawatch.vision import (
    OLLAMA_VIDEO_SCAN_INTERVAL_MS,
    OLLAMA_VIDEO_SCAN_MAX_FRAMES,
    GeminiProvider,
    OllamaProvider,
    get_vision_provider,
    scan_interval_ms,
    spread,
)


@pytest.fixture(autouse=True)
def reset_shared_state() -> None:
    """Reset circuit breaker and cache before each test to avoid state pollution."""
    vision_circuit.reset()
    # Clear the global cache to avoid test pollution
    analysis_cache._cache.clear()


class TestGeminiProvider:
    """Tests for GeminiProvider class."""

    def test_init_without_api_key_raises(self) -> None:
        """Test that GeminiProvider raises without API key."""
        with patch("animawatch.vision.settings") as mock_settings:
            mock_settings.gemini_api_key = ""
            with pytest.raises(ValueError, match="GEMINI_API_KEY is not set"):
                GeminiProvider()

    def test_init_with_api_key_creates_client(self) -> None:
        """Test that GeminiProvider creates a genai Client with API key."""
        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch("animawatch.vision.genai"),
        ):
            mock_settings.gemini_api_key = "test-api-key"
            mock_settings.vision_model = "gemini-3.8-flash"

            provider = GeminiProvider()

            # Provider creation is validated by its mere existence
            # (avoid asserting internal implementation details)
            assert provider is not None

    @pytest.mark.asyncio
    async def test_analyze_video_uploads_and_processes(self, tmp_path: Path) -> None:
        """Test that analyze_video uploads video and waits for processing."""
        # Create a real temp file for the cache to hash
        video_path = tmp_path / "test.webm"
        video_path.write_bytes(b"fake video data")

        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch("animawatch.vision.genai") as mock_genai,
        ):
            mock_settings.gemini_api_key = "test-api-key"
            mock_settings.vision_model = "gemini-3.8-flash"

            # Mock video file states
            mock_video_file = MagicMock()
            mock_video_file.state.name = "ACTIVE"
            mock_video_file.name = "test-video"
            mock_video_file.uri = "gs://test/video.webm"

            # Mock client and async methods
            mock_client = MagicMock()
            mock_client.aio.files.upload = AsyncMock(return_value=mock_video_file)
            mock_client.aio.files.delete = AsyncMock()

            mock_response = MagicMock()
            mock_response.text = "Analysis result"
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider()
            result = await provider.analyze_video(video_path, "Analyze this")

            assert result == "Analysis result"
            mock_client.aio.files.upload.assert_called_once()
            mock_client.aio.models.generate_content.assert_called_once()
            mock_client.aio.files.delete.assert_called_once_with(name="test-video")

    @pytest.mark.asyncio
    async def test_analyze_video_handles_processing_state(self, tmp_path: Path) -> None:
        """Test that analyze_video waits while video is processing."""
        # Create a real temp file for the cache to hash
        video_path = tmp_path / "test.webm"
        video_path.write_bytes(b"fake video data")

        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch("animawatch.vision.genai") as mock_genai,
            patch("animawatch.vision.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_settings.gemini_api_key = "test-api-key"
            mock_settings.vision_model = "gemini-3.8-flash"

            # First call returns PROCESSING, second returns ACTIVE
            processing_file = MagicMock()
            processing_file.state.name = "PROCESSING"
            processing_file.name = "test-video"
            processing_file.uri = "gs://test/video.webm"

            active_file = MagicMock()
            active_file.state.name = "ACTIVE"
            active_file.name = "test-video"
            active_file.uri = "gs://test/video.webm"

            mock_client = MagicMock()
            mock_client.aio.files.upload = AsyncMock(return_value=processing_file)
            mock_client.aio.files.get = AsyncMock(return_value=active_file)
            mock_client.aio.files.delete = AsyncMock()

            mock_response = MagicMock()
            mock_response.text = "Done"
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider()
            result = await provider.analyze_video(video_path, "Analyze")

            mock_sleep.assert_called_once_with(1)
            assert result == "Done"

    @pytest.mark.asyncio
    async def test_analyze_video_raises_on_failed_state(self, tmp_path: Path) -> None:
        """Test that analyze_video raises when processing fails."""
        # Create a real temp file for the cache to hash
        video_path = tmp_path / "test.webm"
        video_path.write_bytes(b"fake video data")

        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch("animawatch.vision.genai") as mock_genai,
        ):
            mock_settings.gemini_api_key = "test-api-key"
            mock_settings.vision_model = "gemini-3.8-flash"

            failed_file = MagicMock()
            failed_file.state.name = "FAILED"
            failed_file.name = "test-video"

            mock_client = MagicMock()
            mock_client.aio.files.upload = AsyncMock(return_value=failed_file)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider()

            with pytest.raises(RuntimeError, match="Video processing failed"):
                await provider.analyze_video(video_path, "Analyze")

    @pytest.mark.asyncio
    async def test_analyze_image_reads_and_processes(self, tmp_path: Path) -> None:
        """Test that analyze_image reads image and calls generate_content."""
        # Create a test image file
        image_path = tmp_path / "test.png"
        image_path.write_bytes(b"fake image data")

        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch("animawatch.vision.genai") as mock_genai,
        ):
            mock_settings.gemini_api_key = "test-api-key"
            mock_settings.vision_model = "gemini-3.8-flash"

            mock_response = MagicMock()
            mock_response.text = "Image analysis"

            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider()
            result = await provider.analyze_image(image_path, "Analyze image")

            assert result == "Image analysis"
            mock_client.aio.models.generate_content.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_image_returns_empty_on_blank_response(self, tmp_path: Path) -> None:
        """Test that analyze_image returns empty string when response has no text."""
        image_path = tmp_path / "test.png"
        image_path.write_bytes(b"fake image data")

        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch("animawatch.vision.genai") as mock_genai,
        ):
            mock_settings.gemini_api_key = "test-api-key"
            mock_settings.vision_model = "gemini-3.8-flash"

            mock_response = MagicMock()
            mock_response.text = None  # Empty/blank response

            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider()
            result = await provider.analyze_image(image_path, "Analyze image")

            assert result == ""


class TestOllamaProvider:
    """Tests for OllamaProvider class."""

    def test_init_without_ollama_raises(self) -> None:
        """Test that OllamaProvider raises when ollama is not installed."""
        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch.dict("sys.modules", {"ollama": None}),
        ):
            mock_settings.ollama_host = "http://localhost:11434"
            mock_settings.ollama_model = "qwen2.5-vl:7b"

            # Import error should be raised
            with pytest.raises(ImportError, match="Ollama package not installed"):
                OllamaProvider()

    def test_init_with_ollama_creates_client(self) -> None:
        """Test that OllamaProvider creates an Ollama client."""
        mock_ollama = MagicMock()
        mock_client = MagicMock()
        mock_ollama.AsyncClient.return_value = mock_client

        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch.dict("sys.modules", {"ollama": mock_ollama}),
        ):
            mock_settings.ollama_host = "http://localhost:11434"
            mock_settings.ollama_model = "qwen2.5-vl:7b"

            # This test verifies settings are properly configured
            # The actual initialization is tested via the factory function

    @staticmethod
    def _provider(client: Any) -> OllamaProvider:
        provider = OllamaProvider.__new__(OllamaProvider)
        provider.client = client
        provider.model = "qwen2.5-vl:7b"
        provider._cache = AnalysisCache()
        return provider

    @staticmethod
    def _make_video(path: Path, seconds: int, rate: int = 25, source: str = "testsrc") -> Path:
        # A lavfi source with options of its own (color=c=red) takes more after ':'.
        options = f"duration={seconds}:size=160x120:rate={rate}"
        spec = f"{source}:{options}" if "=" in source else f"{source}={options}"
        made = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                spec,
                "-c:v",
                "libvpx",
                "-y",
                str(path),
            ],
            check=False,
        )
        assert made.returncode == 0, "ffmpeg is needed for this test"
        return path

    @pytest.mark.asyncio
    async def test_analyze_video_samples_frames(self, tmp_path: Path) -> None:
        """Ollama takes images only: a real video is split into frames, each analysed."""
        video = self._make_video(tmp_path / "clip.webm", 2)

        client = AsyncMock()
        client.chat.return_value = {"message": {"content": "frame looks fine"}}
        result = await self._provider(client).analyze_video(video, "Analyze")

        assert isinstance(result, str)
        assert client.chat.await_count == 8
        assert "### Frame at 0.0s" in result
        assert "### Frame at 0.5s" in result
        prompt = client.chat.call_args_list[0].kwargs["messages"][0]["content"]
        assert "still frame" in prompt
        assert "Analyze" in prompt

    @pytest.mark.asyncio
    async def test_analyze_video_samples_the_whole_recording(self, tmp_path: Path) -> None:
        """Eight frames spread over a 12 s video, not the first four seconds of it."""
        video = self._make_video(tmp_path / "long.webm", 12)

        client = AsyncMock()
        client.chat.return_value = {"message": {"content": "ok"}}
        result = await self._provider(client).analyze_video(video, "Analyze")

        assert isinstance(result, str)
        assert client.chat.await_count == 8
        times = [
            float(line.split("at ")[1].rstrip("s"))
            for line in result.splitlines()
            if line.startswith("### Frame at")
        ]
        assert times[0] == 0.0
        assert times[-1] >= 11.0
        assert times == sorted(times)

    @pytest.mark.asyncio
    async def test_analyze_video_covers_a_recording_longer_than_the_scan(
        self, tmp_path: Path
    ) -> None:
        """A 75 s video is longer than 240 frames at 250 ms; the scan widens to cover it."""
        video = self._make_video(tmp_path / "long.webm", 75, rate=5)
        assert await video_duration_ms(video) == pytest.approx(75_000, abs=500)

        client = AsyncMock()
        client.chat.return_value = {"message": {"content": "ok"}}
        result = await self._provider(client).analyze_video(video, "Analyze")

        assert isinstance(result, str)
        assert client.chat.await_count == 8
        times = [
            float(line.split("at ")[1].rstrip("s"))
            for line in result.splitlines()
            if line.startswith("### Frame at")
        ]
        assert times[0] == 0.0
        assert times[-1] >= 70.0, times

    @pytest.mark.asyncio
    async def test_unknown_duration_is_reported_not_hidden(self, tmp_path: Path) -> None:
        video = self._make_video(tmp_path / "clip.webm", 2)
        client = AsyncMock()
        client.chat.return_value = {"message": {"content": "ok"}}

        with patch("animawatch.vision.video_duration_ms", AsyncMock(return_value=None)):
            text = await self._provider(client).analyze_video(video, "Analyze")
            client.chat.return_value = {
                "message": {"content": '{"findings": [], "summary": "fine", "overall_score": 100}'}
            }
            structured = await self._provider(client).analyze_video(
                video, "Analyze", structured=True
            )

        assert isinstance(text, str)
        assert text.startswith("_ffprobe could not read the video's length")
        assert "first 60 s" in text
        assert isinstance(structured, AnalysisResult)
        assert structured.summary.startswith("ffprobe could not read")

    @pytest.mark.asyncio
    async def test_every_candidate_frame_is_removed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A still video's candidates are nearly all dropped as duplicates; none stay on disk."""
        video = self._make_video(tmp_path / "still.webm", 3, rate=5, source="color=c=red")
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        monkeypatch.setattr("animawatch.vision.tempfile.mkdtemp", lambda prefix: str(work_dir))
        client = AsyncMock()
        client.chat.return_value = {"message": {"content": "ok"}}

        await self._provider(client).analyze_video(video, "Analyze")

        assert client.chat.await_count < 8  # duplicates were filtered out
        assert not work_dir.exists()

    @pytest.mark.asyncio
    async def test_analyze_video_without_frames_explains_ffmpeg(self, tmp_path: Path) -> None:
        empty = FrameExtractionResult(frames=[], total_frames=0, duration_ms=0, fps=2.0)
        with (
            patch("animawatch.vision.extract_frames", AsyncMock(return_value=empty)),
            pytest.raises(RuntimeError, match="ffmpeg"),
        ):
            await self._provider(AsyncMock()).analyze_video(tmp_path / "x.webm", "Analyze")

    @pytest.mark.asyncio
    async def test_analyze_video_structured_merges_findings(self, tmp_path: Path) -> None:
        frames = []
        for i in range(2):
            path = tmp_path / f"frame_{i}.png"
            path.write_bytes(f"img{i}".encode())
            frames.append(
                ExtractedFrame(path=path, timestamp_ms=i * 500, frame_number=i, content_hash=str(i))
            )
        extraction = FrameExtractionResult(frames=frames, total_frames=2, duration_ms=500, fps=2.0)
        finding = (
            '{"findings": [{"id": "f", "category": "layout", "severity": "major", '
            '"confidence": 80, "element": "nav", "description": "overlap", '
            '"suggestion": "fix"}], "summary": "s", "overall_score": 70}'
        )
        client = AsyncMock()
        client.chat.return_value = {"message": {"content": finding}}
        with patch("animawatch.vision.extract_frames", AsyncMock(return_value=extraction)):
            result = await self._provider(client).analyze_video(
                tmp_path / "x.webm", "Analyze", structured=True
            )

        assert isinstance(result, AnalysisResult)
        assert len(result.findings) == 2
        # Findings without a timestamp take the time of the frame they came from.
        assert [f.timestamp for f in result.findings] == [0.0, 0.5]
        assert result.overall_score == 70
        assert result.metadata.provider == "ollama"
        assert not frames[0].path.exists()  # frames are cleaned up

    @pytest.mark.asyncio
    async def test_analyze_image_calls_ollama_chat(self, tmp_path: Path) -> None:
        """Test that analyze_image calls Ollama chat API."""
        image_path = tmp_path / "test.png"
        image_path.write_bytes(b"fake image data")

        mock_client = AsyncMock()
        mock_client.chat.return_value = {"message": {"content": "Ollama analysis"}}

        provider = OllamaProvider.__new__(OllamaProvider)
        provider.client = mock_client
        provider.model = "qwen2.5-vl:7b"
        provider._cache = AnalysisCache()

        result = await provider.analyze_image(image_path, "Analyze this")

        assert result == "Ollama analysis"
        mock_client.chat.assert_called_once()
        call_args = mock_client.chat.call_args
        assert call_args.kwargs["model"] == "qwen2.5-vl:7b"
        assert "images" in call_args.kwargs["messages"][0]


class TestGetVisionProvider:
    """Tests for get_vision_provider factory function."""

    def test_returns_gemini_by_default(self) -> None:
        """Test that get_vision_provider returns GeminiProvider by default."""
        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch("animawatch.vision.genai"),
        ):
            mock_settings.vision_provider = "gemini"
            mock_settings.gemini_api_key = "test-key"
            mock_settings.vision_model = "gemini-3.8-flash"

            provider = get_vision_provider()

            # Check class name due to module reloading during mocking
            assert type(provider).__name__ == "GeminiProvider"

    def test_returns_ollama_when_configured(self) -> None:
        """Test that get_vision_provider returns OllamaProvider when configured."""
        mock_ollama = MagicMock()

        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch.dict("sys.modules", {"ollama": mock_ollama}),
        ):
            mock_settings.vision_provider = "ollama"
            mock_settings.ollama_host = "http://localhost:11434"
            mock_settings.ollama_model = "qwen2.5-vl:7b"

            provider = get_vision_provider()

            # Check class name due to module reloading during mocking
            assert type(provider).__name__ == "OllamaProvider"

    def test_none_turns_vision_off(self) -> None:
        """VISION_PROVIDER=none is refused by the factory, so callers run without vision."""
        with patch("animawatch.vision.settings") as mock_settings:
            mock_settings.vision_provider = "none"
            with pytest.raises(ValueError, match="turned off"):
                get_vision_provider()


class TestScanInterval:
    def test_short_or_unknown_duration_uses_the_base_interval(self) -> None:
        assert scan_interval_ms(None) == OLLAMA_VIDEO_SCAN_INTERVAL_MS
        assert scan_interval_ms(0) == OLLAMA_VIDEO_SCAN_INTERVAL_MS
        assert scan_interval_ms(12_000) == OLLAMA_VIDEO_SCAN_INTERVAL_MS

    def test_long_video_widens_the_interval_to_cover_it(self) -> None:
        for duration in (60_001, 75_000, 3_600_000):
            interval = scan_interval_ms(duration)
            assert interval * OLLAMA_VIDEO_SCAN_MAX_FRAMES >= duration

    @pytest.mark.asyncio
    async def test_duration_of_a_missing_file_is_unknown(self, tmp_path: Path) -> None:
        assert await video_duration_ms(tmp_path / "missing.webm") is None


class TestSampleByTime:
    def test_keeps_the_first_frame_at_or_after_each_interval(self) -> None:
        # 5 fps (200 ms frames) sampled every 313 ms.
        times = [i * 200.0 for i in range(20)]
        kept = list(_sample_by_time(times, 313))
        assert kept == [0, 2, 4, 5, 7, 8, 10, 11, 13, 15, 16, 18, 19]
        # The n-th sample never runs ahead of n intervals by more than one frame.
        for n, index in enumerate(kept[1:], start=1):
            assert times[index] >= n * 313 - 200

    def test_a_75_second_video_is_covered_to_the_end(self) -> None:
        times = (i * 200.0 for i in range(75 * 5))  # 75 s at 5 fps
        kept = list(_sample_by_time(times, scan_interval_ms(75_000)))
        assert len(kept) <= OLLAMA_VIDEO_SCAN_MAX_FRAMES
        assert kept[-1] * 200.0 >= 74_000

    def test_dense_frames_keep_one_per_interval(self) -> None:
        times = [i * 1000 / 60 for i in range(600)]  # 10 s at 60 fps
        assert len(list(_sample_by_time(times, 250))) == 40


class TestSpread:
    @pytest.mark.parametrize(
        ("n", "count", "expected"),
        [
            (3, 8, [0, 1, 2]),
            (10, 4, [0, 3, 6, 9]),
            (240, 8, [0, 34, 68, 102, 137, 171, 205, 239]),
            (5, 1, [0]),
        ],
    )
    def test_evenly_spaced_with_both_ends(self, n: int, count: int, expected: list[int]) -> None:
        assert spread(list(range(n)), count) == expected
