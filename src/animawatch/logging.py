"""Structured logging for AnimaWatch with observability support.

Provides JSON-structured logging for production use and human-readable
logs for development. Includes timing context managers and decorators.
"""

import asyncio
import functools
import logging
import os
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

# Configure structured logger
_log_format = os.environ.get("ANIMAWATCH_LOG_FORMAT", "text")
_log_level = os.environ.get("ANIMAWATCH_LOG_LEVEL", "INFO").upper()

logger = logging.getLogger("animawatch")
logger.setLevel(getattr(logging, _log_level, logging.INFO))

# Avoid adding multiple handlers
if not logger.handlers:
    handler = logging.StreamHandler()

    if _log_format == "json":
        # JSON format for production/observability
        import json

        class JsonFormatter(logging.Formatter):
            """Format log records as JSON for structured logging."""

            def format(self, record: logging.LogRecord) -> str:
                log_data: dict[str, Any] = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                # Add extra fields if present
                if hasattr(record, "extra_data"):
                    extra_data: dict[str, Any] = getattr(record, "extra_data", {})
                    log_data.update(extra_data)
                return json.dumps(log_data)

        handler.setFormatter(JsonFormatter())
    else:
        # Human-readable format for development
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    logger.addHandler(handler)


def log_extra(message: str, level: int = logging.INFO, **extra: Any) -> None:
    """Log a message with extra structured data."""
    record = logging.LogRecord(
        name=logger.name,
        level=level,
        pathname="",
        lineno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.extra_data = extra  # noqa: B010
    logger.handle(record)


@asynccontextmanager
async def timed_operation(
    name: str,
    **context: Any,
) -> AsyncGenerator[dict[str, Any], None]:
    """Context manager that times an async operation and logs it.

    Usage:
        async with timed_operation("analyze_video", url=url) as ctx:
            result = await do_work()
            ctx["result_size"] = len(result)
    """
    start = time.perf_counter()
    ctx: dict[str, Any] = {"operation": name, **context}

    try:
        yield ctx
        elapsed = time.perf_counter() - start
        ctx["duration_ms"] = round(elapsed * 1000, 2)
        ctx["success"] = True
        log_extra(f"{name} completed", logging.INFO, **ctx)
    except Exception as e:
        elapsed = time.perf_counter() - start
        ctx["duration_ms"] = round(elapsed * 1000, 2)
        ctx["success"] = False
        ctx["error"] = str(e)
        ctx["error_type"] = type(e).__name__
        log_extra(f"{name} failed", logging.ERROR, **ctx)
        raise


F = TypeVar("F", bound=Callable[..., Any])


def timed(func: F) -> F:
    """Decorator to time and log function execution."""
    if asyncio.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                log_extra(
                    f"{func.__name__} completed",
                    logging.DEBUG,
                    operation=func.__name__,
                    duration_ms=round(elapsed * 1000, 2),
                    success=True,
                )
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start
                log_extra(
                    f"{func.__name__} failed",
                    logging.ERROR,
                    operation=func.__name__,
                    duration_ms=round(elapsed * 1000, 2),
                    success=False,
                    error=str(e),
                )
                raise

        return async_wrapper  # type: ignore[return-value]
    else:

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                log_extra(
                    f"{func.__name__} completed",
                    logging.DEBUG,
                    operation=func.__name__,
                    duration_ms=round(elapsed * 1000, 2),
                    success=True,
                )
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start
                log_extra(
                    f"{func.__name__} failed",
                    logging.ERROR,
                    operation=func.__name__,
                    duration_ms=round(elapsed * 1000, 2),
                    success=False,
                    error=str(e),
                )
                raise

        return sync_wrapper  # type: ignore[return-value]
