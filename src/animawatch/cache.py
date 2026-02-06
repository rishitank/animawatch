"""Response caching for vision AI analysis.

Provides TTL-based caching to avoid redundant API calls for identical requests.
Cache keys are generated from content hashes and prompts.
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, TypeVar

from .logging import log_extra

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """A cached value with expiration time."""

    value: T
    expires_at: float
    created_at: float = field(default_factory=time.monotonic)

    @property
    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        return time.monotonic() > self.expires_at


class AnalysisCache:
    """Thread-safe TTL cache for vision analysis results.

    Features:
    - Content-based hashing for cache keys
    - Configurable TTL (time-to-live)
    - Automatic expiration cleanup
    - Thread-safe with asyncio.Lock
    - Memory-efficient with size limits
    """

    def __init__(
        self,
        default_ttl: float = 3600.0,  # 1 hour default
        max_size: int = 100,
        cleanup_interval: float = 300.0,  # 5 minutes
    ) -> None:
        self._cache: dict[str, CacheEntry[str]] = {}
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._cleanup_interval = cleanup_interval
        self._lock = asyncio.Lock()
        self._last_cleanup = time.monotonic()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _hash_content(content: bytes, prompt: str) -> str:
        """Generate a cache key from content and prompt."""
        hasher = hashlib.sha256()
        hasher.update(content)
        hasher.update(prompt.encode("utf-8"))
        return hasher.hexdigest()[:32]

    @staticmethod
    def hash_file(file_path: Path, prompt: str) -> str:
        """Generate a cache key from a file and prompt."""
        with open(file_path, "rb") as f:
            content = f.read()
        return AnalysisCache._hash_content(content, prompt)

    async def get(self, key: str) -> str | None:
        """Get a cached value if it exists and hasn't expired."""
        async with self._lock:
            await self._maybe_cleanup()

            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired:
                del self._cache[key]
                self._misses += 1
                log_extra("Cache entry expired", key=key[:8])
                return None

            self._hits += 1
            log_extra("Cache hit", key=key[:8], age_s=time.monotonic() - entry.created_at)
            return entry.value

    async def set(self, key: str, value: str, ttl: float | None = None) -> None:
        """Store a value in the cache with optional custom TTL."""
        async with self._lock:
            # Evict oldest entries if at capacity
            while len(self._cache) >= self._max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k].created_at)
                del self._cache[oldest_key]
                log_extra("Cache eviction", evicted_key=oldest_key[:8])

            effective_ttl = ttl if ttl is not None else self._default_ttl
            self._cache[key] = CacheEntry(
                value=value,
                expires_at=time.monotonic() + effective_ttl,
            )
            log_extra("Cache set", key=key[:8], ttl_s=effective_ttl)

    async def invalidate(self, key: str) -> bool:
        """Remove a specific entry from the cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> int:
        """Clear all cache entries. Returns number of entries cleared."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            log_extra("Cache cleared", entries_cleared=count)
            return count

    async def _maybe_cleanup(self) -> None:
        """Periodically clean up expired entries."""
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        expired_keys = [k for k, v in self._cache.items() if v.is_expired]
        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            log_extra("Cache cleanup", expired_count=len(expired_keys))
        self._last_cleanup = now

    @property
    def stats(self) -> dict[str, int | float]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 2),
        }


# Global cache instance
analysis_cache = AnalysisCache()
