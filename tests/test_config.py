"""Tests for AnimaWatch configuration."""

import pytest

from animawatch.config import Settings


class TestSettings:
    """Tests for Settings configuration."""

    def test_default_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that default settings are created correctly."""
        for name in (
            "VISION_PROVIDER",
            "VISION_MODEL",
            "BROWSER_EXECUTABLE_PATH",
            "ALLOW_FILE_URLS",
            "REFRESH_RATE_HZ",
            "MAX_RECORDING_DURATION",
        ):
            monkeypatch.delenv(name, raising=False)
        settings = Settings(_env_file=None)
        assert settings.vision_provider == "gemini"
        assert settings.vision_model == "gemini-3.8-flash"
        assert settings.browser_headless is True
        assert settings.video_size == {"width": 1280, "height": 720}
        assert settings.max_recording_duration == 30
        assert settings.allow_file_urls is True
        assert settings.refresh_rate_hz is None
        assert settings.browser_executable_path is None

    def test_video_size_dimensions(self) -> None:
        """Test that video size returns correct dimensions."""
        settings = Settings()
        video_size = settings.video_size
        assert "width" in video_size
        assert "height" in video_size
        assert video_size["width"] == 1280
        assert video_size["height"] == 720

    def test_settings_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that environment variables override defaults."""
        monkeypatch.setenv("BROWSER_HEADLESS", "false")
        monkeypatch.setenv("MAX_RECORDING_DURATION", "60")

        settings = Settings()
        assert settings.browser_headless is False
        assert settings.max_recording_duration == 60

    def test_default_model_is_not_a_retired_one(self) -> None:
        """gemini-2.0-flash was shut down on 1 Jun 2026; the default must not regress."""
        from animawatch.config import DEFAULT_GEMINI_MODEL

        assert DEFAULT_GEMINI_MODEL == "gemini-3.8-flash"
        assert "2.0" not in Settings().vision_model

    def test_vision_can_be_turned_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VISION_PROVIDER", "none")
        assert Settings().vision_provider == "none"

    def test_rejects_unknown_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pydantic import ValidationError

        monkeypatch.setenv("VISION_PROVIDER", "openai")
        with pytest.raises(ValidationError):
            Settings()

    def test_rejects_non_positive_limits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pydantic import ValidationError

        monkeypatch.setenv("MAX_RECORDING_DURATION", "0")
        with pytest.raises(ValidationError):
            Settings()
        monkeypatch.setenv("MAX_RECORDING_DURATION", "30")
        monkeypatch.setenv("REFRESH_RATE_HZ", "0")
        with pytest.raises(ValidationError):
            Settings()

    def test_browser_and_refresh_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BROWSER_EXECUTABLE_PATH", "/opt/chrome")
        monkeypatch.setenv("REFRESH_RATE_HZ", "120")
        monkeypatch.setenv("ALLOW_FILE_URLS", "false")
        settings = Settings()
        assert settings.browser_executable_path == "/opt/chrome"
        assert settings.refresh_rate_hz == 120.0
        assert settings.allow_file_urls is False
