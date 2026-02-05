"""Vision AI providers for analyzing videos and screenshots."""

import asyncio
import base64
import contextlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

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
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model_name = settings.vision_model

    async def analyze_video(self, video_path: Path, prompt: str) -> str:
        """Analyze video using Gemini's video understanding."""
        # Upload the video file using async API
        video_file = await self.client.aio.files.upload(file=str(video_path))
        file_name = video_file.name or ""

        # Wait for processing (check file state)
        while video_file.state and video_file.state.name == "PROCESSING":
            await asyncio.sleep(1)
            video_file = await self.client.aio.files.get(name=file_name)

        if video_file.state and video_file.state.name == "FAILED":
            raise RuntimeError(f"Video processing failed: {video_file.state.name}")

        # Generate analysis
        video_part = types.Part.from_uri(
            file_uri=video_file.uri or "",
            mime_type="video/webm",
        )
        prompt_part = types.Part.from_text(text=prompt)
        contents: list[types.Part] = [video_part, prompt_part]
        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=contents,  # type: ignore[arg-type]
        )

        # Clean up uploaded file
        with contextlib.suppress(Exception):
            await self.client.aio.files.delete(name=file_name)

        return str(response.text) if response.text else ""

    async def analyze_image(self, image_path: Path, prompt: str) -> str:
        """Analyze image using Gemini's vision capabilities."""
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Use Part.from_bytes for image data
        image_part = types.Part.from_bytes(
            data=image_data,
            mime_type="image/png",
        )
        prompt_part = types.Part.from_text(text=prompt)
        contents: list[types.Part] = [image_part, prompt_part]

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=contents,  # type: ignore[arg-type]
        )
        return str(response.text) if response.text else ""


class OllamaProvider(VisionProvider):
    """Ollama local vision provider (100% FREE, runs locally)."""

    def __init__(self) -> None:
        try:
            import ollama

            self.client: Any = ollama.AsyncClient(host=settings.ollama_host)
            self.model = settings.ollama_model
        except ImportError as err:
            raise ImportError("Ollama package not installed. Run: pip install ollama") from err

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
