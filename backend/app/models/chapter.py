from typing import Optional

from sqlalchemy import Index, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Chapter(Base, TimestampMixin):
    __tablename__ = "chapters"

    novel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_file: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True,
        comment="Path to compressed content file (e.g. data/content/ab/abc.../xyz.gz)"
    )
    volume: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="Volume/section name (e.g. 第一卷 七玄门风云)"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, index=True
    )
    word_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    source_url: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    # Relationships
    novel = relationship("Novel", back_populates="chapters")

    __table_args__ = (
        Index("ix_chapters_novel_sort", "novel_id", "sort_order"),
        Index("ix_chapters_novel_source_url", "novel_id", "source_url"),
        Index("ix_chapters_novel_published", "novel_id", "is_published"),
    )

    def __repr__(self) -> str:
        return f"<Chapter {self.title}>"
