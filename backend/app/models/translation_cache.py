"""Translation cache model — stores translated texts to avoid repeated API calls."""
from sqlalchemy import Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class TranslationCache(Base, TimestampMixin):
    __tablename__ = "translation_cache"

    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="SHA256 of source text")
    source_lang: Mapped[str] = mapped_column(String(10), nullable=False, default="zh")
    target_lang: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_translation_lookup", "source_hash", "target_lang", unique=True),
    )
