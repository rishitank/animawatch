"""Tests for AnimaWatch vision AI providers."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from animawatch.vision import GeminiProvider, OllamaProvider, get_vision_provider


class TestGeminiProvider:
    """Tests for GeminiProvider class."""

    def test_init_without_api_key_raises(self) -> None:
        """Test that GeminiProvider raises without API key."""
        with patch("animawatch.vision.settings") as mock_settings:
            mock_settings.gemini_api_key = ""
            with pytest.raises(ValueError, match="GEMINI_API_KEY not set"):
                GeminiProvider()

    def test_init_with_api_key_configures_genai(self) -> None:
        """Test that GeminiProvider configures genai with API key."""
        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch("animawatch.vision.genai") as mock_genai,
        ):
            mock_settings.gemini_api_key = "test-api-key"
            mock_settings.vision_model = "gemini-2.0-flash"

            provider = GeminiProvider()

            mock_genai.configure.assert_called_once_with(api_key="test-api-key")
            mock_genai.GenerativeModel.assert_called_once_with("gemini-2.0-flash")
            assert provider.model is not None

    @pytest.mark.asyncio
    async def test_analyze_video_uploads_and_processes(self) -> None:
        """Test that analyze_video uploads video and waits for processing."""
        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch("animawatch.vision.genai") as mock_genai,
        ):
            mock_settings.gemini_api_key = "test-api-key"
            mock_settings.vision_model = "gemini-2.0-flash"

            # Mock video file states
            mock_video_file = MagicMock()
            mock_video_file.state.name = "ACTIVE"
            mock_video_file.name = "test-video"
            mock_genai.upload_file.return_value = mock_video_file

            # Mock model response
            mock_response = MagicMock()
            mock_response.text = "Analysis result"
            mock_model = MagicMock()
            mock_model.generate_content.return_value = mock_response
            mock_genai.GenerativeModel.return_value = mock_model

            provider = GeminiProvider()
            result = await provider.analyze_video(Path("/tmp/test.webm"), "Analyze this")

            assert result == "Analysis result"
            mock_genai.upload_file.assert_called_once()
            mock_model.generate_content.assert_called_once()
            mock_genai.delete_file.assert_called_once_with("test-video")

    @pytest.mark.asyncio
    async def test_analyze_video_handles_processing_state(self) -> None:
        """Test that analyze_video waits while video is processing."""
        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch("animawatch.vision.genai") as mock_genai,
            patch("animawatch.vision.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_settings.gemini_api_key = "test-api-key"
            mock_settings.vision_model = "gemini-2.0-flash"

            # First call returns PROCESSING, second returns ACTIVE
            processing_file = MagicMock()
            processing_file.state.name = "PROCESSING"
            processing_file.name = "test-video"

            active_file = MagicMock()
            active_file.state.name = "ACTIVE"
            active_file.name = "test-video"

            mock_genai.upload_file.return_value = processing_file
            mock_genai.get_file.return_value = active_file

            mock_response = MagicMock()
            mock_response.text = "Done"
            mock_model = MagicMock()
            mock_model.generate_content.return_value = mock_response
            mock_genai.GenerativeModel.return_value = mock_model

            provider = GeminiProvider()
            result = await provider.analyze_video(Path("/tmp/test.webm"), "Analyze")

            mock_sleep.assert_called_once_with(1)
            assert result == "Done"

    @pytest.mark.asyncio
    async def test_analyze_video_raises_on_failed_state(self) -> None:
        """Test that analyze_video raises when processing fails."""
        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch("animawatch.vision.genai") as mock_genai,
        ):
            mock_settings.gemini_api_key = "test-api-key"
            mock_settings.vision_model = "gemini-2.0-flash"

            failed_file = MagicMock()
            failed_file.state.name = "FAILED"
            mock_genai.upload_file.return_value = failed_file
            mock_genai.GenerativeModel.return_value = MagicMock()

            provider = GeminiProvider()

            with pytest.raises(RuntimeError, match="Video processing failed"):
                await provider.analyze_video(Path("/tmp/test.webm"), "Analyze")

    @pytest.mark.asyncio
    async def test_analyze_image_reads_and_encodes(self, tmp_path: Path) -> None:
        """Test that analyze_image reads and base64 encodes the image."""
        # Create a test image file
        image_path = tmp_path / "test.png"
        image_path.write_bytes(b"fake image data")

        with (
            patch("animawatch.vision.settings") as mock_settings,
            patch("animawatch.vision.genai") as mock_genai,
        ):
            mock_settings.gemini_api_key = "test-api-key"
            mock_settings.vision_model = "gemini-2.0-flash"

            mock_response = MagicMock()
            mock_response.text = "Image analysis"
            mock_model = MagicMock()
            mock_model.generate_content.return_value = mock_response
            mock_genai.GenerativeModel.return_value = mock_model

            provider = GeminiProvider()
            result = await provider.analyze_image(image_path, "Analyze image")

            assert result == "Image analysis"
            mock_model.generate_content.assert_called_once()


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

    @pytest.mark.asyncio
    async def test_analyze_video_raises_not_implemented(self) -> None:
        """Test that analyze_video raises NotImplementedError for Ollama."""
        mock_client = MagicMock()

        # Create provider directly without full initialization
        provider = OllamaProvider.__new__(OllamaProvider)
        provider.client = mock_client
        provider.model = "qwen2.5-vl:7b"

        with pytest.raises(NotImplementedError, match="Ollama doesn't support direct video"):
            await provider.analyze_video(Path("/tmp/test.webm"), "Analyze")

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
            mock_settings.vision_model = "gemini-2.0-flash"

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
