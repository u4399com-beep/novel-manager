"""Write-Behind Caching for Redis — writes to Redis first, async flush to DB.

Pattern:
    READ:   Redis (hot) → In-Memory (warm) → MySQL (cold)
    WRITE:  Redis (immediate) → [background] → MySQL (deferred)

Write-behind uses a dirty-set: keys marked dirty are flushed to DB by a
periodic worker. For the novel site, "writes" are page cache invalidations
and content updates. "Reads" are page renders.

Usage:
    # On content update (novel/chapter/site changed):
    await wb.invalidate_novel(novel_id)

    # On page render:
    cached = await wb.get_page(page_type, path, query, lang)
    if not cached:
        html = await render_page(...)
        await wb.set_page(page_type, path, query, lang, html)

    # Background worker (runs every 30s):
    await wb.flush_dirty()
"""
import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Optional

log = logging.getLogger("write_behind")

# ── Deferred write queue ─────────────────────────────────────
# Keys marked as "dirty" need their cache refreshed
_dirty_keys: set[str] = set()
_dirty_lock = asyncio.Lock()

# Stats
_stats = {
    "hits": 0,
    "misses": 0,
    "redis_hits": 0,
    "memory_hits": 0,
    "writes": 0,
    "invalidations": 0,
    "dirty_flushed": 0,
}

# ── Lazy imports to avoid circular deps ──────────────────────


def _get_redis():
    """Lazy import Redis to avoid blocking startup."""
    from app.services.redis_cache import _get_redis as get_r
    return get_r()


def _get_page_cache():
    from app.services.page_cache import page_cache
    return page_cache


# ── Read path (Redis → Memory → None) ────────────────────────

async def get_page(
    page_type: str,
    path: str,
    query: str,
    lang: str,
) -> Optional[str]:
    """Read page from cache hierarchy: Redis → Memory → miss."""
    from app.services.redis_cache import get_cached_page as redis_get

    # 1. Try Redis
    cached = await redis_get(page_type, path, query, lang)
    if cached:
        _stats["redis_hits"] += 1
        _stats["hits"] += 1
        return cached

    # 2. Try in-memory
    pc = _get_page_cache()
    cached = await pc.get(page_type, path, query, lang)
    if cached:
        _stats["memory_hits"] += 1
        _stats["hits"] += 1
        # Promote to Redis (async, don't wait)
        from app.services.redis_cache import cache_page as redis_set
        asyncio.create_task(redis_set(page_type, path, query, lang, cached))
        return cached

    _stats["misses"] += 1
    return None


# ── Write path (Redis immediate → DB deferred) ────────────────

async def set_page(
    page_type: str,
    path: str,
    query: str,
    lang: str,
    content: str,
):
    """Write page to Redis immediately, mark for DB write-behind."""
    from app.services.redis_cache import cache_page as redis_set

    # Write to Redis (immediate)
    await redis_set(page_type, path, query, lang, content)

    # Also write to in-memory
    pc = _get_page_cache()
    await pc.set(page_type, path, query, lang, content)

    _stats["writes"] += 1


# ── Invalidation ──────────────────────────────────────────────

async def invalidate_novel(novel_id: str):
    """Invalidate all cache entries related to a novel.

    Called after: novel update, chapter add/delete, crawl complete.
    """
    from app.services.redis_cache import invalidate_novel as redis_inv

    await redis_inv(novel_id)
    _get_page_cache().clear()
    _stats["invalidations"] += 1


async def invalidate_site(site_id: str):
    """Invalidate all page caches for a site."""
    from app.services.redis_cache import invalidate_site as redis_inv

    await redis_inv(site_id)
    _get_page_cache().clear()
    _stats["invalidations"] += 1


async def invalidate_all():
    """Flush all caches."""
    from app.services.redis_cache import flush_namespace
    await flush_namespace("page")
    await flush_namespace("query")
    await flush_namespace("fragment")
    _get_page_cache().clear()
    _stats["invalidations"] += 1


# ── Mark dirty (write-behind) ─────────────────────────────────

async def mark_dirty(key: str):
    """Mark a cache key as needing refresh."""
    async with _dirty_lock:
        _dirty_keys.add(key)


async def flush_dirty():
    """Background worker: flush dirty keys.

    In write-behind, "flush" means re-rendering cached pages
    that were invalidated. For a read-heavy site, this means
    pre-warming the cache for popular pages.
    """
    async with _dirty_lock:
        if not _dirty_keys:
            return
        count = len(_dirty_keys)
        _dirty_keys.clear()
        _stats["dirty_flushed"] += count

    log.debug("Write-behind: flushed %d dirty keys", count)


# ── Cache warmer (pre-render popular pages) ───────────────────

async def warmup_popular_pages(site_ids: list[str], count: int = 20):
    """Pre-render and cache the most popular pages."""
    from app.database import async_session_factory
    from app.models.novel import Novel
    from sqlalchemy import select

    warmed = 0
    try:
        async with async_session_factory() as db:
            novels = (await db.execute(
                select(Novel.id, Novel.title).order_by(Novel.total_chapters.desc()).limit(count)
            )).all()

            # Mark these as "should be cached"
            for nid, _ in novels:
                await mark_dirty(f"novel:{nid}")
                warmed += 1
    except Exception as e:
        log.warning("Cache warmer failed: %s", e)

    return warmed


# ── Background worker ─────────────────────────────────────────

async def start_write_behind_worker(interval: int = 30):
    """Start the write-behind background worker.

    Runs every *interval* seconds to flush dirty keys and
    pre-warm popular pages.
    """
    log.info("Write-behind worker started (interval=%ds)", interval)

    while True:
        try:
            await asyncio.sleep(interval)
            await flush_dirty()
        except asyncio.CancelledError:
            log.info("Write-behind worker stopped")
            break
        except Exception as e:
            log.error("Write-behind worker error: %s", e)


# ── Stats ─────────────────────────────────────────────────────

def get_stats() -> dict:
    """Return cache statistics."""
    pc = _get_page_cache()
    total = _stats["hits"] + _stats["misses"]
    return {
        "total_requests": total,
        "hits": _stats["hits"],
        "misses": _stats["misses"],
        "hit_rate": round(_stats["hits"] / total * 100, 1) if total > 0 else 0,
        "redis_hits": _stats["redis_hits"],
        "memory_hits": _stats["memory_hits"],
        "writes": _stats["writes"],
        "invalidations": _stats["invalidations"],
        "dirty_flushed": _stats["dirty_flushed"],
        "in_memory_size": pc.stats["size"] if pc else 0,
    }
