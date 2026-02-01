"""Vision AI providers for analyzing videos and screenshots."""

import base64
import contextlib
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import google.generativeai as genai

from .config import settings


class VisionProvider(ABC):
    """Abstract base class for vision AI providers."""

    @abstractmethod
    async def analyze_video(self, video_path: Path, prompt: str) -> str:
        """Analyze a video file and return the analysis."""
        pass

    @abstractmethod
    async def analyze_image(self, image_path: Path, prompt: str) -> str:
        """Analyze an image file and return the analysis."""
        pass


class GeminiProvider(VisionProvider):
    """Google Gemini vision provider (FREE tier available)."""

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/"
            )
        genai.configure(api_key=settings.gemini_api_key)  # type: ignore[attr-defined]
        self.model: Any = genai.GenerativeModel(settings.vision_model)  # type: ignore[attr-defined]

    async def analyze_video(self, video_path: Path, prompt: str) -> str:
        """Analyze video using Gemini's video understanding."""
        # Upload the video file
        video_file: Any = genai.upload_file(str(video_path))  # type: ignore[attr-defined]

        # Wait for processing
        while video_file.state.name == "PROCESSING":
            time.sleep(1)
            video_file = genai.get_file(video_file.name)  # type: ignore[attr-defined]

        if video_file.state.name == "FAILED":
            raise RuntimeError(f"Video processing failed: {video_file.state.name}")

        # Generate analysis
        response: Any = self.model.generate_content([video_file, prompt])

        # Clean up uploaded file
        with contextlib.suppress(Exception):
            genai.delete_file(video_file.name)  # type: ignore[attr-defined]

        return str(response.text)

    async def analyze_image(self, image_path: Path, prompt: str) -> str:
        """Analyze image using Gemini's vision capabilities."""
        with open(image_path, "rb") as f:
            image_data = f.read()

        image_part = {
            "mime_type": "image/png",
            "data": base64.b64encode(image_data).decode("utf-8"),
        }

        response: Any = self.model.generate_content([image_part, prompt])
        return str(response.text)


class OllamaProvider(VisionProvider):
    """Ollama local vision provider (100% FREE, runs locally)."""

    def __init__(self) -> None:
        try:
            import ollama

            self.client: Any = ollama.AsyncClient(host=settings.ollama_host)
            self.model = settings.ollama_model
        except ImportError as err:
            raise ImportError(
                "Ollama package not installed. Run: pip install ollama"
            ) from err

    async def analyze_video(self, video_path: Path, prompt: str) -> str:
        """Analyze video by extracting key frames (Ollama doesn't support video directly)."""
        # For Ollama, we'll extract frames and analyze them
        # This is a simplified implementation - could be enhanced with ffmpeg
        raise NotImplementedError(
            "Ollama doesn't support direct video analysis. "
            "Use analyze_image with extracted frames or switch to Gemini."
        )

    async def analyze_image(self, image_path: Path, prompt: str) -> str:
        """Analyze image using Ollama's vision model."""
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        response: dict[str, Any] = await self.client.chat(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_data],
                }
            ],
        )
        return str(response["message"]["content"])


def get_vision_provider() -> VisionProvider:
    """Factory function to get the configured vision provider."""
    if settings.vision_provider == "ollama":
        return OllamaProvider()
    return GeminiProvider()

