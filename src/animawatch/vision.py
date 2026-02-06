"""Vision AI providers for analyzing videos and screenshots.

Includes:
- GeminiProvider: Google Gemini vision with video and image support
- OllamaProvider: Local Ollama for image analysis
- Retry logic with exponential backoff
- Response caching for identical requests
- Structured JSON output with confidence scoring
- Structured logging and observability
"""

import asyncio
import base64
import contextlib
import json
import mimetypes
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, TypedDict

import aiofiles
from google import genai
from google.genai import types

from .cache import AnalysisCache, analysis_cache
from .config import settings
from .logging import log_extra, timed_operation
from .models import AnalysisMetadata, AnalysisResult, Finding, IssueCategory, Severity
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

# JSON output instruction to append to prompts
JSON_OUTPUT_INSTRUCTION = """

IMPORTANT: Respond with a valid JSON object following this exact structure:
{
  "findings": [
    {
      "id": "unique-id",
      "category": "animation|visual_artifact|layout|timing|accessibility|performance",
      "severity": "critical|major|minor|info",
      "confidence": 0-100,
      "timestamp": null or seconds (for video),
      "element": "description of affected element",
      "description": "what is wrong",
      "suggestion": "how to fix it",
      "bounding_box": null or {"x": 0, "y": 0, "width": 100, "height": 100},
      "evidence": "visual evidence supporting this finding"
    }
  ],
  "summary": "brief overall summary",
  "overall_score": 0-100 (100 = no issues)
}

Only return the JSON object, no markdown formatting or additional text."""


# TypedDict for Ollama API response to avoid Any type leaks
class OllamaMessage(TypedDict):
    """Ollama message structure in chat response."""

    content: str


class OllamaResponse(TypedDict):
    """Ollama chat response structure."""

    message: OllamaMessage


class VisionProvider(ABC):
    """Abstract base class for vision AI providers."""

    def __init__(self) -> None:
        self._cache: AnalysisCache = analysis_cache

    @abstractmethod
    async def analyze_video(
        self, video_path: Path, prompt: str, structured: bool = False
    ) -> str | AnalysisResult:
        """Analyze a video file and return the analysis."""
        pass

    @abstractmethod
    async def analyze_image(
        self, image_path: Path, prompt: str, structured: bool = False
    ) -> str | AnalysisResult:
        """Analyze an image file and return the analysis."""
        pass

    async def analyze_images_parallel(
        self,
        image_paths: list[Path],
        prompts: list[str] | str,
        structured: bool = False,
        max_concurrent: int = 5,
    ) -> list[str | AnalysisResult]:
        """Analyze multiple images concurrently for improved performance.

        Args:
            image_paths: List of paths to images to analyze
            prompts: Either a single prompt for all images, or a list of prompts
            structured: If True, return AnalysisResult with confidence scores
            max_concurrent: Maximum number of concurrent API calls (default 5)

        Returns:
            List of analysis results in the same order as input images

        Raises:
            ValueError: If prompts is a list with different length than image_paths
        """
        if isinstance(prompts, str):
            prompt_list = [prompts] * len(image_paths)
        else:
            if len(prompts) != len(image_paths):
                raise ValueError(
                    f"Number of prompts ({len(prompts)}) must match "
                    f"number of images ({len(image_paths)})"
                )
            prompt_list = prompts

        # Use semaphore to limit concurrent API calls
        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_with_limit(path: Path, prompt: str) -> str | AnalysisResult:
            async with semaphore:
                return await self.analyze_image(path, prompt, structured)

        # Run all analyses concurrently with rate limiting
        tasks = [
            analyze_with_limit(path, prompt)
            for path, prompt in zip(image_paths, prompt_list, strict=True)
        ]
        return await asyncio.gather(*tasks)

    async def analyze_image_streaming(
        self,
        image_path: Path,
        prompt: str,
    ) -> AsyncGenerator[str, None]:
        """Analyze an image and stream results as they are generated.

        This is useful for providing real-time feedback during analysis.
        Default implementation calls analyze_image and yields the result.

        Args:
            image_path: Path to the image to analyze
            prompt: Analysis prompt

        Yields:
            Chunks of the analysis text as they are generated
        """
        # Default implementation: non-streaming fallback
        result = await self.analyze_image(image_path, prompt, structured=False)
        if isinstance(result, str):
            yield result
        else:
            yield result.to_markdown()

    def _parse_structured_response(
        self,
        response: str,
        provider: str,
        model: str,
        duration_ms: int,
        url: str | None = None,
    ) -> AnalysisResult:
        """Parse JSON response into AnalysisResult model."""
        try:
            # Try to extract JSON from markdown code blocks if present
            clean_response = response.strip()
            if clean_response.startswith("```"):
                # Extract content between code blocks
                lines = clean_response.split("\n")
                json_lines = []
                in_block = False
                for line in lines:
                    if line.startswith("```"):
                        in_block = not in_block
                        continue
                    if in_block:
                        json_lines.append(line)
                clean_response = "\n".join(json_lines)

            data = json.loads(clean_response)

            findings = []
            for f in data.get("findings", []):
                finding = Finding(
                    id=f.get("id", str(uuid.uuid4())[:8]),
                    category=IssueCategory(f.get("category", "visual_artifact")),
                    severity=Severity(f.get("severity", "minor")),
                    confidence=f.get("confidence", 50),
                    timestamp=f.get("timestamp"),
                    element=f.get("element", "Unknown element"),
                    description=f.get("description", ""),
                    suggestion=f.get("suggestion", ""),
                    evidence=f.get("evidence"),
                )
                findings.append(finding)

            return AnalysisResult(
                id=str(uuid.uuid4())[:8],
                url=url,
                success=True,
                findings=findings,
                summary=data.get("summary", "Analysis complete"),
                overall_score=data.get("overall_score", 100 - len(findings) * 10),
                metadata=AnalysisMetadata(
                    provider=provider,
                    model=model,
                    analysis_duration_ms=duration_ms,
                ),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            log_extra("Failed to parse structured response", error=str(e))
            # Return a basic result with the raw response as summary
            return AnalysisResult(
                id=str(uuid.uuid4())[:8],
                url=url,
                success=True,
                findings=[],
                summary=response[:500] if len(response) > 500 else response,
                overall_score=100,
                metadata=AnalysisMetadata(
                    provider=provider,
                    model=model,
                    analysis_duration_ms=duration_ms,
                ),
            )


class GeminiProvider(VisionProvider):
    """Google Gemini vision provider (FREE tier available).

    Features:
    - Video and image analysis with Gemini's multimodal models
    - Automatic retry with exponential backoff
    - Response caching for identical requests
    - Structured JSON output with confidence scoring
    - Structured logging for observability
    - Circuit breaker to prevent cascading failures
    """

    def __init__(self) -> None:
        super().__init__()
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
    async def analyze_video(
        self, video_path: Path, prompt: str, structured: bool = False
    ) -> str | AnalysisResult:
        """Analyze video using Gemini's video understanding.

        Args:
            video_path: Path to the video file
            prompt: Analysis prompt
            structured: If True, return AnalysisResult with confidence scores

        Returns:
            Raw string response or structured AnalysisResult
        """
        start_time = time.monotonic()

        # Check cache first
        cache_key = self._cache.hash_file(video_path, prompt + str(structured))
        cached = await self._cache.get(cache_key)
        if cached:
            log_extra("Cache hit for video analysis", video_path=str(video_path))
            if structured:
                return self._parse_structured_response(cached, "gemini", self.model_name, 0)
            return cached

        # Build prompt with JSON instruction if structured
        effective_prompt = prompt + JSON_OUTPUT_INSTRUCTION if structured else prompt

        async with timed_operation(
            "analyze_video",
            provider="gemini",
            video_path=str(video_path),
            prompt_length=len(effective_prompt),
            structured=structured,
        ):
            # Upload the video file using async API
            video_file = await self.client.aio.files.upload(file=str(video_path))

            # Validate file name is present
            if not video_file.name:
                raise RuntimeError("Uploaded video file name not available")
            file_name = video_file.name

            # Wait for processing with timeout
            upload_start = time.monotonic()
            while video_file.state and video_file.state.name == "PROCESSING":
                elapsed = time.monotonic() - upload_start
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
            prompt_part = types.Part.from_text(text=effective_prompt)
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

            # Cache the result
            await self._cache.set(cache_key, result)

            duration_ms = int((time.monotonic() - start_time) * 1000)

            if structured:
                return self._parse_structured_response(
                    result, "gemini", self.model_name, duration_ms
                )
            return result

    @with_retry(VISION_RETRY_CONFIG, vision_circuit)
    async def analyze_image(
        self, image_path: Path, prompt: str, structured: bool = False
    ) -> str | AnalysisResult:
        """Analyze image using Gemini's vision capabilities.

        Args:
            image_path: Path to the image file
            prompt: Analysis prompt
            structured: If True, return AnalysisResult with confidence scores

        Returns:
            Raw string response or structured AnalysisResult
        """
        start_time = time.monotonic()

        # Check cache first
        cache_key = self._cache.hash_file(image_path, prompt + str(structured))
        cached = await self._cache.get(cache_key)
        if cached:
            log_extra("Cache hit for image analysis", image_path=str(image_path))
            if structured:
                return self._parse_structured_response(cached, "gemini", self.model_name, 0)
            return cached

        # Build prompt with JSON instruction if structured
        effective_prompt = prompt + JSON_OUTPUT_INSTRUCTION if structured else prompt

        async with timed_operation(
            "analyze_image",
            provider="gemini",
            image_path=str(image_path),
            prompt_length=len(effective_prompt),
            structured=structured,
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
            prompt_part = types.Part.from_text(text=effective_prompt)
            contents: list[types.Part] = [image_part, prompt_part]

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,  # type: ignore[arg-type]
            )
            result = str(response.text) if response.text else ""

            # Cache the result
            await self._cache.set(cache_key, result)

            duration_ms = int((time.monotonic() - start_time) * 1000)

            if structured:
                return self._parse_structured_response(
                    result, "gemini", self.model_name, duration_ms
                )
            return result

    async def analyze_image_streaming(
        self,
        image_path: Path,
        prompt: str,
    ) -> AsyncGenerator[str, None]:
        """Analyze an image and stream results as they are generated.

        Uses Gemini's streaming API to yield text chunks as they arrive.

        Args:
            image_path: Path to the image to analyze
            prompt: Analysis prompt

        Yields:
            Chunks of the analysis text as they are generated
        """
        async with timed_operation(
            "analyze_image_streaming",
            provider="gemini",
            image_path=str(image_path),
            prompt_length=len(prompt),
        ):
            # Use async file I/O
            async with aiofiles.open(image_path, "rb") as f:
                image_data = await f.read()

            # Detect MIME type
            mime_type, _ = mimetypes.guess_type(str(image_path))
            if mime_type is None:
                mime_type = "image/png"

            # Build contents
            image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)
            prompt_part = types.Part.from_text(text=prompt)
            contents: list[types.Part] = [image_part, prompt_part]

            # Use streaming API
            async for chunk in await self.client.aio.models.generate_content_stream(
                model=self.model_name,
                contents=contents,  # type: ignore[arg-type]
            ):
                if chunk.text:
                    yield chunk.text


class OllamaProvider(VisionProvider):
    """Ollama local vision provider (100% FREE, runs locally).

    Features:
    - Image analysis with local vision models
    - No external API calls - fully private
    - Response caching for identical requests
    - Structured JSON output with confidence scoring
    - Automatic retry with exponential backoff
    """

    def __init__(self) -> None:
        super().__init__()
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

    async def analyze_video(
        self, video_path: Path, prompt: str, structured: bool = False
    ) -> str | AnalysisResult:
        """Analyze video by extracting key frames (Ollama doesn't support video directly)."""
        # For Ollama, we'll extract frames and analyze them
        # This is a simplified implementation - could be enhanced with ffmpeg
        raise NotImplementedError(
            "Ollama doesn't support direct video analysis. "
            "Use analyze_image with extracted frames or switch to Gemini."
        )

    @with_retry(VISION_RETRY_CONFIG)
    async def analyze_image(
        self, image_path: Path, prompt: str, structured: bool = False
    ) -> str | AnalysisResult:
        """Analyze image using Ollama's vision model.

        Args:
            image_path: Path to the image file
            prompt: Analysis prompt
            structured: If True, return AnalysisResult with confidence scores

        Returns:
            Raw string response or structured AnalysisResult
        """
        start_time = time.monotonic()

        # Check cache first
        cache_key = self._cache.hash_file(image_path, prompt + str(structured))
        cached = await self._cache.get(cache_key)
        if cached:
            log_extra("Cache hit for image analysis", image_path=str(image_path))
            if structured:
                return self._parse_structured_response(cached, "ollama", self.model, 0)
            return cached

        # Build prompt with JSON instruction if structured
        effective_prompt = prompt + JSON_OUTPUT_INSTRUCTION if structured else prompt

        async with timed_operation(
            "analyze_image",
            provider="ollama",
            image_path=str(image_path),
            prompt_length=len(effective_prompt),
            structured=structured,
        ):
            # Use async file I/O to avoid blocking the event loop
            async with aiofiles.open(image_path, "rb") as f:
                image_data = base64.b64encode(await f.read()).decode("utf-8")

            response: OllamaResponse = await self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": effective_prompt,
                        "images": [image_data],
                    }
                ],
            )
            result = str(response["message"]["content"])

            # Cache the result
            await self._cache.set(cache_key, result)

            duration_ms = int((time.monotonic() - start_time) * 1000)

            if structured:
                return self._parse_structured_response(result, "ollama", self.model, duration_ms)
            return result


def get_vision_provider() -> VisionProvider:
    """Factory function to get the configured vision provider."""
    if settings.vision_provider == "ollama":
        return OllamaProvider()
    return GeminiProvider()
