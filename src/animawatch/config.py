"""Configuration settings for AnimaWatch MCP Server."""

from pathlib import Path
from typing import Literal, TypedDict

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Current stable Gemini Flash model. Checked on 13 Nov 2026 against
#: https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash (stable; accepts
#: video) and the deprecations page, which retired gemini-2.0-flash on 1 Jun 2026.
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


class ViewportSize(TypedDict):
    """Viewport size type compatible with Playwright."""

    width: int
    height: int


class Settings(BaseSettings):
    """Server configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Vision AI Provider
    vision_provider: Literal["gemini", "ollama", "none"] = Field(
        default="gemini",
        description=(
            "Vision AI provider: 'gemini' (your own API key), 'ollama' (local), or "
            "'none' (frame timing and metrics only). Gemini without a key turns vision off."
        ),
    )
    gemini_api_key: str = Field(
        default="",
        description=(
            "Your own Google Gemini API key. Users in the UK, EEA or Switzerland "
            "need a paid (billing-enabled) key under the Gemini API terms."
        ),
    )
    vision_model: str = Field(
        default=DEFAULT_GEMINI_MODEL,
        description="Gemini model used for the vision pass",
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
    browser_executable_path: str | None = Field(
        default=None,
        description=(
            "Chromium executable to launch instead of Playwright's bundled one "
            "(for a browser installed outside Playwright's cache)"
        ),
    )
    allow_file_urls: bool = Field(
        default=True,
        description="Allow file:// URLs (turned off when hosted, e.g. on Apify)",
    )
    hosted: bool = Field(
        default=False,
        description=(
            "Running as a hosted service (set by the Apify Actor): no local files are "
            "written for the client"
        ),
    )
    refresh_rate_hz: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Display refresh rate to judge frame timing against. Default: measured "
            "in the browser before each page loads"
        ),
    )
    video_width: int = Field(default=1280, description="Video recording width")
    video_height: int = Field(default=720, description="Video recording height")
    max_recording_duration: int = Field(
        default=30,
        gt=0,
        description=(
            "Upper bound, in seconds, on each wait (wait_time, duration and 'wait' actions)"
        ),
    )

    # Server settings
    server_host: str = Field(default="127.0.0.1", description="Server bind address")
    server_port: int = Field(default=8765, description="Server port for HTTP transport")
    allowed_hosts: str = Field(
        default="",
        description=(
            "Comma-separated extra host names the HTTP transport accepts in Host and "
            "Origin headers (for example a reverse proxy's domain). Localhost is always allowed"
        ),
    )
    recordings_dir: Path | None = Field(
        default=None,
        description="Directory to store recordings (default: temp)",
    )

    @property
    def allowed_hosts_list(self) -> list[str]:
        """``allowed_hosts`` split into names."""
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def video_size(self) -> ViewportSize:
        """Return video size as TypedDict for Playwright compatibility."""
        return ViewportSize(width=self.video_width, height=self.video_height)


# Global settings instance
settings = Settings()
