"""Tests for AnimaWatch configuration."""

import pytest

from animawatch.config import Settings


class TestSettings:
    """Tests for Settings configuration."""

    def test_default_settings(self) -> None:
        """Test that default settings are created correctly."""
        settings = Settings()
        assert settings.vision_provider == "gemini"
        assert settings.vision_model == "gemini-2.0-flash"
        assert settings.browser_headless is True
        assert settings.video_size == {"width": 1280, "height": 720}
        assert settings.max_recording_duration == 30

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

