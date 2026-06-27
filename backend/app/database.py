"""Async SQLAlchemy engine with auto-optimisation per dialect."""
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import event
from app.config import settings

_is_sqlite = "sqlite" in settings.DATABASE_URL
_is_mysql = "mysql" in settings.DATABASE_URL or "asyncmy" in settings.DATABASE_URL

_kwargs: dict = {"echo": False, "future": True}
if _is_mysql:
    _kwargs.update(pool_size=settings.DB_POOL_SIZE, max_overflow=settings.DB_MAX_OVERFLOW,
                   pool_recycle=settings.DB_POOL_RECYCLE, pool_pre_ping=True)
elif _is_sqlite:
    _kwargs["connect_args"] = {"timeout": 30}

engine = create_async_engine(settings.DATABASE_URL, **_kwargs)

if _is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragma(conn, _):
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=30000")
        c.close()

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
