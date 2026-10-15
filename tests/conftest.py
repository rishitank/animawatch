"""Shared pytest fixtures for AnimaWatch tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from animawatch.server import AppContext


@pytest.fixture
def mock_page() -> MagicMock:
    """A Playwright ``Page`` stand-in with awaitable navigation and evaluation."""
    page = MagicMock()
    page.goto = AsyncMock()
    page.evaluate = AsyncMock(return_value={})
    return page


@pytest.fixture
def mock_app_context(mock_page: MagicMock, tmp_path: Path) -> AppContext:
    """An AppContext whose browser and vision provider are mocks.

    ``browser.pooled_context`` behaves like the real async context manager: calling
    it returns an object usable in ``async with`` that yields ``(context, page)``.
    It is wrapped in a ``MagicMock`` so tests can assert how it was called.
    """
    mock_browser = AsyncMock()
    # Paths live under tmp_path so tools that unlink them can't touch real files.
    mock_browser.record_interaction = AsyncMock(return_value=tmp_path / "video.webm")
    mock_browser.take_screenshot = AsyncMock(return_value=tmp_path / "screenshot.png")

    @asynccontextmanager
    async def pooled_context(*_args: Any, **_kwargs: Any) -> AsyncIterator[tuple[Any, Any]]:
        """Yield a ``(context, page)`` pair like ``BrowserRecorder.pooled_context``."""
        yield (MagicMock(), mock_page)

    mock_browser.pooled_context = MagicMock(side_effect=pooled_context)

    mock_vision = AsyncMock()
    mock_vision.analyze_video = AsyncMock(return_value="Video analysis result")
    mock_vision.analyze_image = AsyncMock(return_value="Image analysis result")

    return AppContext(
        browser=mock_browser,
        vision=mock_vision,
        recordings={},
        analyses={},
    )


@pytest.fixture
def mock_ctx(mock_app_context: AppContext) -> MagicMock:
    """A tool ``Context`` whose lifespan context is ``mock_app_context``."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = mock_app_context
    return ctx
