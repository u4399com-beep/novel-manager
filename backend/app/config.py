"""Application settings loaded from environment variables / .env file."""

import logging
import secrets

from pydantic_settings import BaseSettings

log = logging.getLogger("config")


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    # Database
    # MySQL:   mysql+asyncmy://user:password@host:3306/dbname
    # SQLite:  sqlite+aiosqlite:///./novel_manager.db
    DATABASE_URL: str = "mysql+asyncmy://root:password@localhost:3306/novel_manager"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 3600

    # Auth
    SECRET_KEY: str = "change-me-in-production-use-a-strong-random-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Redis
    REDIS_URL: str = "redis://localhost:6380/0"

    # Static files
    STATIC_DIR: str = "static"

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # App
    APP_TITLE: str = "Novel Manager API"
    APP_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"

    # Crawler
    CRAWLER_REQUEST_DELAY: float = 1.0
    CRAWLER_TIMEOUT: int = 60
    CRAWLER_CONCURRENCY: int = 10

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# ── Startup safety checks ──────────────────────────────────────────

_DEFAULT_SECRET = "change-me-in-production-use-a-strong-random-key"
_DEFAULT_DB = "mysql+asyncmy://root:password@localhost:3306/novel_manager"

if settings.SECRET_KEY == _DEFAULT_SECRET:
    log.warning(
        "SECRET_KEY is still the default placeholder! "
        "Set SECRET_KEY env var to a strong random value. "
        "JWT tokens are forgeable with the default key."
    )

if settings.DATABASE_URL == _DEFAULT_DB:
    log.warning(
        "DATABASE_URL is using the default root:password credentials! "
        "Set DATABASE_URL env var for production."
    )

if any("localhost" in str(o) for o in settings.CORS_ORIGINS):
    log.info("CORS origins include localhost — fine for development.")
