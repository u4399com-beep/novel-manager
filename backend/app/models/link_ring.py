"""Link wheel (链轮) models — inter-site and inter-book link networks."""
from typing import Optional
from sqlalchemy import Boolean, Index, Integer, String, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship, foreign
from app.models.base import Base, TimestampMixin


class LinkRing(Base, TimestampMixin):
    """A link wheel / link ring configuration."""
    __tablename__ = "link_rings"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    ring_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="cross_site_books",
        comment="cross_site | same_site_books | cross_site_books | custom"
    )
    site_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True,
        comment="NULL = applies to all sites"
    )
    max_links: Mapped[int] = mapped_column(Integer, default=5)
    display_mode: Mapped[str] = mapped_column(String(20), default="sidebar")
    link_format: Mapped[str] = mapped_column(String(500), default="{title}")
    open_new_tab: Mapped[bool] = mapped_column(default=True)
    nofollow: Mapped[bool] = mapped_column(default=False)
    selection_rules: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    # Use primaryjoin to avoid MySQL charset issues with FK
    targets: Mapped[list["LinkRingTarget"]] = relationship(
        "LinkRingTarget",
        primaryjoin="foreign(LinkRingTarget.ring_id) == LinkRing.id",
        cascade="all, delete-orphan", lazy="selectin",
    )

    __table_args__ = (
        Index("ix_link_rings_active_site", "is_active", "site_id"),
    )


class LinkRingTarget(Base, TimestampMixin):
    """A specific link target within a link ring."""
    __tablename__ = "link_ring_targets"

    ring_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_site_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    source_novel_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    target_site_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    target_novel_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    target_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    anchor_text: Mapped[str] = mapped_column(String(200), default="{title}")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)

    ring: Mapped["LinkRing"] = relationship(
        "LinkRing",
        primaryjoin="foreign(LinkRingTarget.ring_id) == LinkRing.id",
        back_populates="targets",
    )
