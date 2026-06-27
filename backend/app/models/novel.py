from typing import Optional

from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Novel(Base, TimestampMixin):
    __tablename__ = "novels"

    title: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    author: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cover_image_url: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    source_url: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    source_name: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ongoing"
    )
    total_chapters: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # Relationships
    categories = relationship(
        "Category",
        secondary="novel_categories",
        lazy="selectin",
        backref="novels",
    )
    chapters = relationship(
        "Chapter",
        back_populates="novel",
        cascade="all, delete-orphan",
        order_by="Chapter.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Novel {self.title}>"


# Many-to-many association table for novels <-> categories
# Defined AFTER the Novel class so all referenced tables are in metadata
novel_categories = Table(
    "novel_categories",
    Base.metadata,
    Column("novel_id", String(36), ForeignKey("novels.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)
