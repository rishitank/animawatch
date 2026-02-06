"""Vision AI providers for analyzing videos and screenshots.

Includes:
- GeminiProvider: Google Gemini vision with video and image support
- OllamaProvider: Local Ollama for image analysis
- Retry logic with exponential backoff
- Structured logging and observability
"""

import asyncio
import base64
import contextlib
import mimetypes
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypedDict

import aiofiles
from google import genai
from google.genai import types

from .config import settings
from .logging import log_extra, timed_operation
from .retry import RetryConfig, vision_circuit, with_retry

# Maximum time to wait for video processing (5 minutes)
MAX_PROCESSING_SECONDS = 300

# Retry configuration for vision API calls
VISION_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0,
    retry_exceptions=(ConnectionError, TimeoutError, OSError),
)


# TypedDict for Ollama API response to avoid Any type leaks
class OllamaMessage(TypedDict):
    """Ollama message structure in chat response."""

    content: str


class OllamaResponse(TypedDict):
    """Ollama chat response structure."""

    message: OllamaMessage


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
    """Google Gemini vision provider (FREE tier available).

    Features:
    - Video and image analysis with Gemini's multimodal models
    - Automatic retry with exponential backoff
    - Structured logging for observability
    - Circuit breaker to prevent cascading failures
    """

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/"
            )
        self.client: genai.Client = genai.Client(api_key=settings.gemini_api_key)
        self.model_name: str = settings.vision_model
        log_extra(
            "GeminiProvider initialized",
            model=self.model_name,
            provider="gemini",
        )

    @with_retry(VISION_RETRY_CONFIG, vision_circuit)
    async def analyze_video(self, video_path: Path, prompt: str) -> str:
        """Analyze video using Gemini's video understanding."""
        async with timed_operation(
            "analyze_video",
            provider="gemini",
            video_path=str(video_path),
            prompt_length=len(prompt),
        ):
            # Upload the video file using async API
            video_file = await self.client.aio.files.upload(file=str(video_path))

            # Validate file name is present
            if not video_file.name:
                raise RuntimeError("Uploaded video file name not available")
            file_name = video_file.name

            # Wait for processing with timeout
            start_time = time.monotonic()
            while video_file.state and video_file.state.name == "PROCESSING":
                elapsed = time.monotonic() - start_time
                if elapsed > MAX_PROCESSING_SECONDS:
                    raise TimeoutError(
                        f"Video processing timed out after {MAX_PROCESSING_SECONDS}s "
                        f"for file: {file_name}"
                    )
                await asyncio.sleep(1)
                video_file = await self.client.aio.files.get(name=file_name)

            if video_file.state and video_file.state.name == "FAILED":
                raise RuntimeError(f"Video processing failed: {video_file.state.name}")

            # Validate video URI before creating Part
            if not video_file.uri:
                raise RuntimeError(f"Video file URI not available for: {file_name}")

            # Generate analysis
            video_part = types.Part.from_uri(
                file_uri=video_file.uri,
                mime_type="video/webm",
            )
            prompt_part = types.Part.from_text(text=prompt)
            contents: list[types.Part] = [video_part, prompt_part]
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,  # type: ignore[arg-type]
            )

            # Clean up uploaded file (file may already be deleted or not accessible)
            # Suppress only expected errors: file not found or permission denied
            with contextlib.suppress(FileNotFoundError, PermissionError, OSError):
                await self.client.aio.files.delete(name=file_name)

            result = str(response.text) if response.text else ""
            return result

    @with_retry(VISION_RETRY_CONFIG, vision_circuit)
    async def analyze_image(self, image_path: Path, prompt: str) -> str:
        """Analyze image using Gemini's vision capabilities."""
        async with timed_operation(
            "analyze_image",
            provider="gemini",
            image_path=str(image_path),
            prompt_length=len(prompt),
        ):
            # Use async file I/O to avoid blocking the event loop
            async with aiofiles.open(image_path, "rb") as f:
                image_data = await f.read()

            # Detect MIME type from file extension
            mime_type, _ = mimetypes.guess_type(str(image_path))
            if mime_type is None:
                mime_type = "image/png"  # fallback

            # Use Part.from_bytes for image data
            image_part = types.Part.from_bytes(
                data=image_data,
                mime_type=mime_type,
            )
            prompt_part = types.Part.from_text(text=prompt)
            contents: list[types.Part] = [image_part, prompt_part]

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,  # type: ignore[arg-type]
            )
            return str(response.text) if response.text else ""


class OllamaProvider(VisionProvider):
    """Ollama local vision provider (100% FREE, runs locally).

    Features:
    - Image analysis with local vision models
    - No external API calls - fully private
    - Automatic retry with exponential backoff
    """

    def __init__(self) -> None:
        try:
            import ollama

            # NOTE: Using Any type for ollama client because the ollama package
            # lacks proper type stubs. TODO: Add proper typing when ollama publishes stubs
            # or create a Protocol interface for the methods we use.
            self.client: Any = ollama.AsyncClient(host=settings.ollama_host)
            self.model = settings.ollama_model
            log_extra(
                "OllamaProvider initialized",
                model=self.model,
                host=settings.ollama_host,
                provider="ollama",
            )
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

    @with_retry(VISION_RETRY_CONFIG)
    async def analyze_image(self, image_path: Path, prompt: str) -> str:
        """Analyze image using Ollama's vision model."""
        async with timed_operation(
            "analyze_image",
            provider="ollama",
            image_path=str(image_path),
            prompt_length=len(prompt),
        ):
            # Use async file I/O to avoid blocking the event loop
            async with aiofiles.open(image_path, "rb") as f:
                image_data = base64.b64encode(await f.read()).decode("utf-8")

            response: OllamaResponse = await self.client.chat(
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
