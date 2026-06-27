import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models.base import Base

# Import all models so Base.metadata knows about them
from app.models import Category, Chapter, CrawlerTask, Novel, User  # noqa: F401

config = context.config

# Override sqlalchemy.url from our settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL script.

    Uses ``literal_binds`` for SQLite; for MySQL, the URL is embedded
    directly without literal binds to avoid parameter-rendering issues
    with MySQL-specific syntax.
    """
    url = config.get_main_option("sqlalchemy.url")
    is_mysql = "mysql" in url.lower() if url else False

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=not is_mysql,  # MySQL doesn't work well with literal_binds
        dialect_opts={"paramstyle": "named"} if not is_mysql else {},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
