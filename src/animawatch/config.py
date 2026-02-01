"""Configuration settings for AnimaWatch MCP Server."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Vision AI Provider
    vision_provider: Literal["gemini", "ollama"] = Field(
        default="gemini",
        description="Vision AI provider to use",
    )
    gemini_api_key: str = Field(
        default="",
        description="Google Gemini API key (free at aistudio.google.com)",
    )
    vision_model: str = Field(
        default="gemini-2.0-flash",
        description="Vision model to use for analysis",
    )

    # Ollama settings (optional)
    ollama_host: str = Field(
        default="http://localhost:11434",
        description="Ollama server URL",
    )
    ollama_model: str = Field(
        default="qwen2.5-vl:7b",
        description="Ollama vision model to use",
    )

    # Browser settings
    browser_headless: bool = Field(
        default=True,
        description="Run browser in headless mode",
    )
    video_width: int = Field(default=1280, description="Video recording width")
    video_height: int = Field(default=720, description="Video recording height")
    max_recording_duration: int = Field(
        default=30,
        description="Maximum recording duration in seconds",
    )

    # Server settings
    server_host: str = Field(default="127.0.0.1", description="Server bind address")
    server_port: int = Field(default=8765, description="Server port for HTTP transport")
    recordings_dir: Path | None = Field(
        default=None,
        description="Directory to store recordings (default: temp)",
    )

    @property
    def video_size(self) -> dict[str, int]:
        """Return video size as dict for Playwright."""
        return {"width": self.video_width, "height": self.video_height}


# Global settings instance
settings = Settings()

