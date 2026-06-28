import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models.

    Compatible with MySQL, SQLite, and PostgreSQL.
    """
    pass


class TimestampMixin:
    """Mixin that adds id, created_at, and updated_at columns.

    Uses String(36) for UUID primary keys, which maps to:
    - MySQL:    VARCHAR(36) / CHAR(36)
    - SQLite:   TEXT
    - Postgres: VARCHAR(36)

    DateTime columns use Python-side defaults for portability across
    all database backends. An event listener on ``before_update``
    automatically bumps ``updated_at`` on every flush.
    """

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ---- Auto-update updated_at on every ORM flush ----
@event.listens_for(Base, "before_update", propagate=True)
def _touch_updated_at(mapper, connection, target):
    """Bump updated_at to now() before every UPDATE.

    Using a mapper event is the most portable way to auto-update
    timestamps — it works identically on MySQL, SQLite, and Postgres
    without relying on database-specific ON UPDATE triggers.
    """
    target.updated_at = datetime.now(timezone.utc)
