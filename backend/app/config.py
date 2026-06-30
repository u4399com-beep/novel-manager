"""Application settings loaded from environment variables / .env file."""

import logging

from pydantic_settings import BaseSettings

log = logging.getLogger("config")


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    # Environment: "development" | "production"
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str = "mysql+asyncmy://root:password@localhost:3306/novel_manager"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 3600

    # Auth — must be set via env in production
    SECRET_KEY: str = ""
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
    CRAWLER_REQUEST_DELAY: float = 0.2
    CRAWLER_TIMEOUT: int = 60
    CRAWLER_CONCURRENCY: int = 10

    # Translation
    LIBRETRANSLATE_URL: str = "http://localhost:5001/translate"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# ── Startup safety checks ──────────────────────────────────────────

_DEFAULT_DB = "mysql+asyncmy://root:password@localhost:3306/novel_manager"

_is_production = settings.ENVIRONMENT == "production"

if not settings.SECRET_KEY:
    if _is_production:
        raise RuntimeError("SECRET_KEY must be set in production environment")
    import secrets as _secrets
    settings.SECRET_KEY = _secrets.token_urlsafe(32)
    log.warning("SECRET_KEY auto-generated for development session.")
elif settings.SECRET_KEY == "change-me-in-production-use-a-strong-random-key":
    if _is_production:
        raise RuntimeError("SECRET_KEY is still the default placeholder. Set to a strong random value.")

if settings.DATABASE_URL == _DEFAULT_DB and _is_production:
    raise RuntimeError("DATABASE_URL must not use default root:password in production")

_localhost_origins = [o for o in settings.CORS_ORIGINS if "://localhost" in str(o) or "://127.0.0.1" in str(o)]
if _localhost_origins:
    log.info("CORS origins include localhost — fine for development.")
