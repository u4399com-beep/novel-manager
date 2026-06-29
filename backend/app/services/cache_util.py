"""Unified in-process TTL cache — used by site.py and categories API for ORM objects."""

import asyncio
import time
from typing import Optional


class TTLCache:
    """Async-safe, bounded, TTL-based in-process cache."""

    def __init__(self, max_size: int = 1000, name: str = "cache"):
        self._cache: dict[str, tuple[float, object]] = {}
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._name = name
        self._miss = object()  # sentinel for cache miss

    async def get(self, key: str) -> object:
        """Return cached value or sentinel _miss on miss/expiry."""
        now = time.monotonic()
        async with self._lock:
            if key in self._cache:
                expiry, val = self._cache[key]
                if now < expiry:
                    return val
                del self._cache[key]
        return self._miss

    async def set(self, key: str, val: object, ttl: int):
        """Store value with TTL (seconds). Evicts oldest if at capacity."""
        async with self._lock:
            if len(self._cache) >= self._max_size:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (time.monotonic() + ttl, val)

    async def invalidate(self, pattern: str = ""):
        """Remove keys containing pattern (empty = all)."""
        async with self._lock:
            if not pattern:
                self._cache.clear()
            else:
                keys = [k for k in self._cache if pattern in k]
                for k in keys:
                    del self._cache[k]

    @property
    def size(self) -> int:
        return len(self._cache)


# Global singleton instances
site_cache = TTLCache(max_size=500, name="site")
categories_cache = TTLCache(max_size=10, name="categories")
