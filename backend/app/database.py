"""Async SQLAlchemy engine — with retry logic and MySQL/SQLite optimizations."""
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import event
from app.config import settings

_is_sqlite = "sqlite" in settings.DATABASE_URL
_is_mysql = "mysql" in settings.DATABASE_URL or "asyncmy" in settings.DATABASE_URL

_kwargs: dict = {"echo": False, "future": True}
if _is_mysql:
    _kwargs.update(pool_size=30, max_overflow=30, pool_recycle=3600, pool_timeout=15)
elif _is_sqlite:
    _kwargs["connect_args"] = {"timeout": 20}

# Retry on connection failure
for _ in range(3):
    try:
        engine = create_async_engine(settings.DATABASE_URL, **_kwargs)
        break
    except Exception:
        import asyncio, time; time.sleep(1)

if _is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragma(conn, _):
        c = conn.cursor(); c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA busy_timeout=20000"); c.close()

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try: yield session; await session.commit()
        except Exception: await session.rollback(); raise


async def warmup_pool():
    """Pre-warm the connection pool by opening a few connections."""
    try:
        async with async_session_factory() as db:
            from sqlalchemy import text
            await db.execute(text("SELECT 1"))
    except Exception:
        pass
