"""Simple in-memory page cache with TTL for high-traffic routes.

Caches full HTML responses keyed by (path, query_string, site_lang).
TTL: 10s for home/search, 30s for novel detail, 5s for chapter list.
"""
import asyncio
import hashlib
import time
from collections import OrderedDict
from typing import Optional


class PageCache:
    """LRU-ish TTL cache for rendered HTML pages."""

    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

        # TTL per page type (seconds)
        self._ttl = {
            "home": 10,
            "book_library": 10,
            "search": 10,
            "novel_detail": 30,
            "chapter_list": 5,
            "chapter_read": 5,  # cached per-chapter — heavy I/O path
        }

    def _key(self, path: str, query: str, lang: str) -> str:
        raw = f"{path}|{query}|{lang}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def get(self, page_type: str, path: str, query: str, lang: str) -> Optional[str]:
        ttl = self._ttl.get(page_type, 0)
        if ttl <= 0:
            self._misses += 1
            return None

        key = self._key(path, query, lang)
        async with self._lock:
            if key in self._cache:
                expiry, content = self._cache[key]
                if time.monotonic() < expiry:
                    self._hits += 1
                    # Move to end (LRU)
                    self._cache.move_to_end(key)
                    return content
                else:
                    del self._cache[key]
        self._misses += 1
        return None

    async def set(self, page_type: str, path: str, query: str, lang: str, content: str):
        ttl = self._ttl.get(page_type, 0)
        if ttl <= 0:
            return

        key = self._key(path, query, lang)
        async with self._lock:
            # Evict oldest if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = (time.monotonic() + ttl, content)

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total * 100, 1) if total > 0 else 0,
        }

    def clear(self):
        self._cache.clear()
        self._hits = 0
        self._misses = 0


# Global singleton
page_cache = PageCache(max_size=500)
