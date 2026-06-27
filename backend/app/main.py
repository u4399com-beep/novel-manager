import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.api.site import router as site_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup: ensure static directories exist
    os.makedirs(os.path.join(settings.STATIC_DIR, "covers"), exist_ok=True)
    yield
    # Shutdown: dispose database engine
    from app.database import engine

    await engine.dispose()


def create_app() -> FastAPI:
    """Application factory — creates and configures the FastAPI app."""
    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files
    static_dir = os.path.abspath(settings.STATIC_DIR)
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # SEO-friendly public site (root level, no prefix)
    app.include_router(site_router)

    # Include API router
    app.include_router(api_router, prefix=settings.API_PREFIX)

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": settings.APP_VERSION}

    return app


app = create_app()
