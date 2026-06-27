from typing import Optional

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CrawlerTask(Base, TimestampMixin):
    __tablename__ = "crawler_tasks"

    novel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    chapters_found: Mapped[int] = mapped_column(
        Integer, default=0
    )
    chapters_added: Mapped[int] = mapped_column(
        Integer, default=0
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<CrawlerTask {self.id} [{self.status}]>"
