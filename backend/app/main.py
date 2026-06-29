import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.api.site import router as site_router
from app.config import settings
from app.middleware.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    try:
        os.makedirs(os.path.join(settings.STATIC_DIR, "covers"), exist_ok=True)
    except OSError:
        pass
    # Warm up Redis connection pool + start write-behind worker
    try:
        from app.services.redis_cache import _get_redis
        await _get_redis()
    except Exception:
        pass
    try:
        from app.services.write_behind_cache import start_write_behind_worker
        asyncio.create_task(start_write_behind_worker(interval=30))
    except Exception:
        pass
    try:
        from app.services.crawl_session import _start_session_cleanup
        asyncio.create_task(_start_session_cleanup(interval=600))
    except Exception:
        pass
    yield
    from app.database import engine
    await engine.dispose()


async def _db_health() -> bool:
    try:
        from app.database import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as s:
            await s.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _redis_health() -> dict:
    try:
        from app.services.redis_cache import _get_redis
        r = await _get_redis()
        if r:
            info = await r.info("memory")
            return {
                "connected": True,
                "used_memory": info.get("used_memory_human", "?"),
                "keys": await r.dbsize(),
            }
        return {"connected": False, "reason": "not_configured"}
    except Exception as e:
        return {"connected": False, "reason": str(e)[:100]}


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Rate limiting (100 req/60s per IP on API routes)
    app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

    # Security headers
    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Static files
    static_dir = os.path.abspath(settings.STATIC_DIR)
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Routers
    app.include_router(site_router)
    app.include_router(api_router, prefix=settings.API_PREFIX)

    # Health check (DB + Redis aware)
    @app.get("/health")
    async def health_check():
        db_ok = await _db_health()
        redis = await _redis_health()
        overall = "ok" if db_ok else "degraded"
        return {
            "status": overall,
            "version": settings.APP_VERSION,
            "database": "ok" if db_ok else "unreachable",
            "redis": redis,
        }

    @app.get("/metrics")
    async def metrics():
        from app.services.page_cache import page_cache
        from app.services.write_behind_cache import get_stats as wb_stats
        from app.services.content_store import stats as cs_stats
        from app.database import engine

        return {
            "cache": {
                "page": page_cache.stats,
                "write_behind": wb_stats(),
            },
            "content_store": cs_stats(),
            "db_pool": {
                "size": engine.pool.size(),
                "checked_in": engine.pool.checkedin(),
                "overflow": engine.pool.overflow(),
            },
        }

    return app


app = create_app()
