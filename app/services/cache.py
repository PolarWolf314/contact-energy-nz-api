"""TTL cache implementation for API responses."""

from typing import Any

from cachetools import TTLCache

from app.config import get_settings


class Cache:
    """Simple TTL cache wrapper."""

    def __init__(self, maxsize: int = 100, ttl_minutes: int | None = None):
        """Initialize cache with optional custom TTL.

        Args:
            maxsize: Maximum number of items in the cache.
            ttl_minutes: Time-to-live in minutes. Defaults to config value.
        """
        if ttl_minutes is None:
            ttl_minutes = get_settings().cache_ttl_minutes

        ttl_seconds = ttl_minutes * 60
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=maxsize, ttl=ttl_seconds)

    def get(self, key: str) -> Any | None:
        """Get a value from cache."""
        return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        """Set a value in cache."""
        self._cache[key] = value

    def delete(self, key: str) -> None:
        """Delete a value from cache."""
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()

    def has(self, key: str) -> bool:
        """Check if a key exists in cache."""
        return key in self._cache


# Global cache instance
_cache: Cache | None = None


def get_cache() -> Cache:
    """Get the global cache instance."""
    global _cache
    if _cache is None:
        _cache = Cache()
    return _cache


def clear_cache() -> None:
    """Clear the global cache."""
    global _cache
    if _cache is not None:
        _cache.clear()
