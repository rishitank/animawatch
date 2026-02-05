"""Retry logic with exponential backoff and circuit breaker pattern.

Provides robust retry mechanisms for API calls with:
- Exponential backoff with jitter
- Circuit breaker to prevent cascading failures
- Configurable retry conditions
"""

import asyncio
import functools
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from .logging import log_extra, logger

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0  # Initial delay in seconds
    max_delay: float = 30.0  # Maximum delay in seconds
    exponential_base: float = 2.0  # Exponential backoff multiplier
    jitter: float = 0.5  # Random jitter factor (0-1)
    retry_exceptions: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    )


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit is open, requests fail immediately
    - HALF_OPEN: Testing if service recovered

    Thread-safe for use in async contexts.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        name: str = "default",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name
        self._failures = 0
        self._last_failure_time: float = 0
        self._state = "CLOSED"
        self._lock = asyncio.Lock()

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests).

        Note: This is a synchronous check for use in non-async contexts.
        For async contexts, use async_is_open().
        """
        if self._state == "OPEN":
            # Check if recovery timeout has passed (using monotonic clock)
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = "HALF_OPEN"
                return False
            return True
        return False

    async def async_is_open(self) -> bool:
        """Thread-safe check if circuit is open (for async contexts)."""
        async with self._lock:
            return self.is_open

    def record_success(self) -> None:
        """Record a successful request."""
        self._failures = 0
        self._state = "CLOSED"

    async def async_record_success(self) -> None:
        """Thread-safe record of successful request."""
        async with self._lock:
            self.record_success()

    def record_failure(self) -> None:
        """Record a failed request."""
        self._failures += 1
        self._last_failure_time = time.monotonic()

        if self._failures >= self.failure_threshold:
            self._state = "OPEN"
            log_extra(
                f"Circuit breaker {self.name} opened",
                failures=self._failures,
                threshold=self.failure_threshold,
            )

    async def async_record_failure(self) -> None:
        """Thread-safe record of failed request."""
        async with self._lock:
            self.record_failure()

    def reset(self) -> None:
        """Reset the circuit breaker to initial state.

        Useful for testing to clear shared state between tests.
        """
        self._failures = 0
        self._last_failure_time = 0
        self._state = "CLOSED"


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


def calculate_delay(
    attempt: int,
    config: RetryConfig,
) -> float:
    """Calculate delay with exponential backoff and jitter."""
    delay = config.base_delay * (config.exponential_base**attempt)
    delay = min(delay, config.max_delay)

    # Add jitter to prevent thundering herd
    jitter_range = delay * config.jitter
    delay += random.uniform(-jitter_range, jitter_range)

    return max(0, delay)


def with_retry(
    config: RetryConfig | None = None,
    circuit_breaker: CircuitBreaker | None = None,
) -> Callable[[F], F]:
    """Decorator that adds retry logic with optional circuit breaker.

    Usage:
        @with_retry(RetryConfig(max_retries=3))
        async def call_api():
            ...
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check circuit breaker using async-safe method
            if circuit_breaker and await circuit_breaker.async_is_open():
                raise CircuitOpenError(f"Circuit breaker {circuit_breaker.name} is open")

            last_exception: Exception | None = None

            for attempt in range(config.max_retries + 1):
                try:
                    result = await func(*args, **kwargs)
                    if circuit_breaker:
                        await circuit_breaker.async_record_success()
                    return result

                except config.retry_exceptions as e:
                    last_exception = e

                    if circuit_breaker:
                        await circuit_breaker.async_record_failure()

                    if attempt < config.max_retries:
                        delay = calculate_delay(attempt, config)
                        logger.warning(
                            f"Retry {attempt + 1}/{config.max_retries} for "
                            f"{func.__name__}: {e}. Waiting {delay:.1f}s"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"All {config.max_retries} retries exhausted for {func.__name__}: {e}"
                        )

            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")

        return async_wrapper  # type: ignore[return-value]

    return decorator


# Shared circuit breaker for vision API calls
vision_circuit = CircuitBreaker(
    failure_threshold=3,
    recovery_timeout=60.0,
    name="vision_api",
)
