"""Redis caching layer — pluggable, falls back to in-memory if Redis unavailable.

Strategies:
    - Page cache: full HTML responses (TTL 10-60s per page type)
    - Query cache: DB query results (TTL 60-300s)
    - Fragment cache: rendered template blocks (TTL 30-120s)
    - Session cache: crawl session state (TTL 1h)

Keys are namespaced: nvm:{type}:{hash}
"""
import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Optional, Any

log = logging.getLogger("redis_cache")

# ── Redis client (lazy init) ──────────────────────────────────
_redis: Any = None
_redis_available: bool = False  # set to True after first successful ping

from app.config import settings
REDIS_URL = settings.REDIS_URL

# ── TTL defaults (seconds) ────────────────────────────────────
TTL = {
    "page:home": 10,
    "page:book_library": 10,
    "page:search": 10,
    "page:novel_detail": 60,
    "page:chapter_list": 30,
    "page:chapter_read": 5,
    "query:category_novels": 120,
    "query:latest_chapters": 60,
    "query:ranking": 120,
    "fragment:link_wheel": 60,
    "fragment:random_recommend": 30,
    "session:crawl": 3600,
    "default": 60,
}


async def _get_redis():
    """Lazy-init Redis connection pool (async)."""
    global _redis, _redis_available
    if _redis is not None:
        return _redis

    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            max_connections=50,
        )
        await _redis.ping()
        _redis_available = True
        log.info("Redis connected: %s", REDIS_URL)
    except Exception as e:
        log.warning("Redis unavailable (%s), using in-memory fallback", e)
        _redis = None
        _redis_available = False

    return _redis


def is_available() -> bool:
    return _redis_available


# ── Core API ──────────────────────────────────────────────────

def _key(namespace: str, *parts: str) -> str:
    """Build a namespaced cache key."""
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.md5(raw.encode()).hexdigest()[:16]
    return f"nvm:{namespace}:{digest}"


async def get(namespace: str, *parts: str) -> Optional[str]:
    """Get a cached value. Returns None on miss or Redis down."""
    r = await _get_redis()
    if not r:
        return None
    try:
        key = _key(namespace, *parts)
        return await r.get(key)
    except asyncio.CancelledError:
        raise
    except Exception:
        return None


async def set(
    namespace: str,
    value: str,
    *parts: str,
    ttl: Optional[int] = None,
):
    """Set a cached value with TTL."""
    r = await _get_redis()
    if not r:
        return
    try:
        key = _key(namespace, *parts)
        ttl_seconds = ttl or TTL.get(f"{namespace}:{parts[0] if parts else ''}", TTL["default"])
        await r.setex(key, ttl_seconds, value)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.debug("Redis set failed: %s", e)


async def delete(namespace: str, *parts: str):
    """Delete a cached key."""
    r = await _get_redis()
    if not r:
        return
    try:
        key = _key(namespace, *parts)
        await r.delete(key)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.debug("Redis delete failed: %s", e)


async def delete_pattern(namespace: str, pattern: str = "*"):
    """Delete all keys matching namespace:pattern."""
    r = await _get_redis()
    if not r:
        return
    try:
        match = f"nvm:{namespace}:{pattern}"
        cursor = 0
        while True:
            cursor, keys = await r.scan(cursor, match=match, count=100)
            if keys:
                await r.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        pass


async def flush_namespace(namespace: str):
    """Flush all keys in a namespace."""
    await delete_pattern(namespace, "*")


# ── High-level helpers ────────────────────────────────────────

async def get_or_compute(
    namespace: str,
    *parts: str,
    ttl: Optional[int] = None,
    compute=None,
):
    """Get from cache, or compute and store if miss."""
    cached = await get(namespace, *parts)
    if cached is not None:
        return cached

    if compute is None:
        return None

    result = await compute()
    # Cache all truthy results plus explicitly non-None falsy values (0, "", [])
    if result is not None and result != "":
        await set(namespace, str(result) if not isinstance(result, str) else result, *parts, ttl=ttl)
    return result


async def cache_page(
    page_type: str,
    path: str,
    query: str,
    lang: str,
    content: str,
):
    """Cache a rendered page."""
    ttl = TTL.get(f"page:{page_type}", TTL["default"])
    if ttl <= 0:
        return
    await set("page", content, page_type, path, query, lang, ttl=ttl)


async def get_cached_page(
    page_type: str,
    path: str,
    query: str,
    lang: str,
) -> Optional[str]:
    """Retrieve a cached page."""
    ttl = TTL.get(f"page:{page_type}", 0)
    if ttl <= 0:
        return None
    return await get("page", page_type, path, query, lang)


async def invalidate_novel(novel_id: str):
    """Invalidate caches for a specific novel (targeted, not global)."""
    await delete_pattern("page", f"*{novel_id}*")
    await delete_pattern("query", f"*{novel_id}*")
    await delete_pattern("fragment", f"*{novel_id}*")


async def invalidate_site(site_id: str):
    """Invalidate all page caches for a site."""
    await flush_namespace("page")


# ── Health / stats ────────────────────────────────────────────

async def health_check() -> dict:
    """Return Redis health status."""
    r = await _get_redis()
    if not r:
        return {"redis": "unavailable", "fallback": "in-memory"}

    try:
        info = await r.info("memory")
        dbsize = await r.dbsize()
        return {
            "redis": "connected",
            "url": REDIS_URL,
            "keys": dbsize,
            "used_memory_human": info.get("used_memory_human", "?"),
            "fallback": None,
        }
    except Exception as e:
        return {"redis": "error", "error": str(e), "fallback": "in-memory"}
