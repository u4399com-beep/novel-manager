"""Cache administration API — flush, stats, health."""
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.models.user import User
from app.services import redis_cache
from app.services.page_cache import page_cache

router = APIRouter(prefix="/cache", tags=["Cache"])


@router.get("/health")
async def cache_health(current_user: User = Depends(get_current_user)):
    """Redis + in-memory cache health and stats."""
    redis_health = await redis_cache.health_check()
    mem_stats = page_cache.stats
    return {
        "redis": redis_health,
        "in_memory": mem_stats,
    }


@router.post("/flush")
async def flush_all(current_user: User = Depends(get_current_user)):
    """Flush all caches (Redis + in-memory)."""
    await redis_cache.flush_namespace("page")
    await redis_cache.flush_namespace("query")
    await redis_cache.flush_namespace("fragment")
    page_cache.clear()
    return {"message": "All caches flushed", "in_memory_size": page_cache.stats["size"]}


@router.post("/flush/pages")
async def flush_pages(current_user: User = Depends(get_current_user)):
    """Flush page caches only."""
    await redis_cache.flush_namespace("page")
    page_cache.clear()
    return {"message": "Page caches flushed"}


@router.post("/flush/novel/{novel_id}")
async def flush_novel_cache(novel_id: str, current_user: User = Depends(get_current_user)):
    """Invalidate all caches for a specific novel."""
    await redis_cache.invalidate_novel(novel_id)
    return {"message": f"Cache invalidated for novel {novel_id}"}
