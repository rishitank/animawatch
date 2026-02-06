"""Tests for caching in animawatch.cache."""

import tempfile
import time
from pathlib import Path

import pytest

from animawatch.cache import AnalysisCache, analysis_cache


class TestAnalysisCache:
    """Tests for AnalysisCache class."""

    @pytest.mark.asyncio
    async def test_set_and_get(self) -> None:
        """Test basic set and get operations."""
        cache = AnalysisCache(max_size=10, default_ttl=60)
        await cache.set("key1", "value1")
        assert await cache.get("key1") == "value1"

    @pytest.mark.asyncio
    async def test_get_missing_key(self) -> None:
        """Test getting a non-existent key returns None."""
        cache = AnalysisCache(max_size=10, default_ttl=60)
        assert await cache.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self) -> None:
        """Test that entries expire after TTL."""
        cache = AnalysisCache(max_size=10, default_ttl=0.1)
        await cache.set("key1", "value1")
        assert await cache.get("key1") == "value1"
        time.sleep(0.15)
        assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_max_size_eviction(self) -> None:
        """Test that old entries are evicted when max size is reached."""
        cache = AnalysisCache(max_size=2, default_ttl=60)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        # key1 should be evicted (oldest)
        assert await cache.get("key1") is None
        assert await cache.get("key2") == "value2"
        assert await cache.get("key3") == "value3"

    @pytest.mark.asyncio
    async def test_invalidate(self) -> None:
        """Test invalidating a specific key."""
        cache = AnalysisCache(max_size=10, default_ttl=60)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.invalidate("key1")
        assert await cache.get("key1") is None
        assert await cache.get("key2") == "value2"

    @pytest.mark.asyncio
    async def test_clear(self) -> None:
        """Test clearing all entries."""
        cache = AnalysisCache(max_size=10, default_ttl=60)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.clear()
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_stats(self) -> None:
        """Test cache statistics."""
        cache = AnalysisCache(max_size=10, default_ttl=60)
        await cache.set("key1", "value1")
        await cache.get("key1")  # hit
        await cache.get("key1")  # hit
        await cache.get("missing")  # miss
        stats = cache.stats
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_hash_file(self) -> None:
        """Test file hashing for cache keys."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"test content")
            path = Path(f.name)
        try:
            prompt = "analyze this"
            hash1 = AnalysisCache.hash_file(path, prompt)
            hash2 = AnalysisCache.hash_file(path, prompt)
            assert hash1 == hash2
            assert len(hash1) == 32  # SHA-256 hex digest truncated to 32
        finally:
            path.unlink()

    def test_hash_file_different_content(self) -> None:
        """Test that different files produce different hashes."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1:
            f1.write(b"content1")
            path1 = Path(f1.name)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
            f2.write(b"content2")
            path2 = Path(f2.name)
        try:
            prompt = "analyze"
            assert AnalysisCache.hash_file(path1, prompt) != AnalysisCache.hash_file(path2, prompt)
        finally:
            path1.unlink()
            path2.unlink()

    def test_hash_file_different_prompt(self) -> None:
        """Test that different prompts produce different hashes."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"content")
            path = Path(f.name)
        try:
            assert AnalysisCache.hash_file(path, "prompt1") != AnalysisCache.hash_file(
                path, "prompt2"
            )
        finally:
            path.unlink()


class TestGlobalCache:
    """Tests for the global analysis_cache instance."""

    def test_global_cache_exists(self) -> None:
        """Test that global cache is available."""
        assert analysis_cache is not None
        assert isinstance(analysis_cache, AnalysisCache)
