from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # Database — default to MySQL; set DATABASE_URL to override
    # MySQL: mysql+asyncmy://user:password@host:3306/dbname
    # SQLite: sqlite+aiosqlite:///./novel_manager.db
    DATABASE_URL: str = "mysql+asyncmy://root:password@localhost:3306/novel_manager"

    # Database pool settings (MySQL-specific)
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 3600  # Recycle connections every hour

    # Auth
    SECRET_KEY: str = "change-me-in-production-use-a-strong-random-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours

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
    CRAWLER_REQUEST_DELAY: float = 1.0  # seconds between requests
    CRAWLER_TIMEOUT: int = 60  # seconds

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
