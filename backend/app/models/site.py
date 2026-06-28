"""Site model for multi-site (站群) support with pseudo-static URLs and pagination."""
from typing import Optional, Any
from sqlalchemy import Boolean, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Site(Base, TimestampMixin):
    __tablename__ = "sites"

    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    template: Mapped[str] = mapped_column(String(50), default="default")
    offset: Mapped[int] = mapped_column("offset_val", Integer, default=0, comment="Novel offset for content differentiation")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    language: Mapped[str] = mapped_column(String(10), default="zh", comment="Site language code: zh,en,ja,ko,fr,de,es,pt,ru,ar,th,vi,id,it,tr,hi,ms")

    # ---- Pseudo-static URL patterns ----
    url_patterns: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="""
    URL rewrite patterns for this site. Example:
    {
        "novel_detail": "/novel/{id}.html",
        "chapter_list": "/novel/{id}/chapters/",
        "chapter_read": "/chapter/{id}.html",
        "category_list": "/category/{id}/",
        "search": "/search/{keyword}/"
    }
    Leave null to use default patterns (/novel/{id}, /chapter/{id}, etc.)
    """)

    # ---- Chapter content pagination ----
    chapter_pagination: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="""
    Chapter pagination config for this site. Example:
    {
        "enabled": true,
        "method": "word_count",      // "word_count" | "page_count" | "none"
        "words_per_page": 3000,       // split every N words
        "pages_per_chapter": null,    // or split into N fixed pages
        "show_page_nav": true,        // show "Page 1/5" navigation
        "page_param": "page",         // query param name: ?page=2
        "canonical_first_page": true  // page 1 uses canonical URL without ?page=
    }
    """)

    # ---- Link wheel (链轮) config ----
    link_wheel: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="""
    Per-site link wheel defaults. Global link rings can override these.
    {
        "enabled": true,
        "max_links_per_page": 8,
        "link_section": "sidebar",   // "sidebar" | "footer" | "inline" | "popup"
        "open_new_tab": true,
        "nofollow": false
    }
    """)

    # ---- Recommend modules (推荐模块) config ----
    recommend_modules: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="""
    Per-page module toggles and settings. null = all defaults (enabled).
    {
        "home": {
            "hero_carousel": {"enabled": true},
            "category_sections": {"enabled": true, "max_categories": 9},
            "latest_updates": {"enabled": true, "count": 25},
            "hot_ranking": {"enabled": true, "count": 15},
            "friend_links": {"enabled": true},
            "link_wheel": {"enabled": true}
        },
        "novel_detail": {
            "friend_links": {"enabled": true},
            "link_wheel": {"enabled": true}
        },
        "chapter_read": {
            "random_recommend": {"enabled": true, "count": 5},
            "reader_toolbar": {"enabled": true},
            "link_wheel": {"enabled": true}
        },
        "chapter_list": {
            "link_wheel": {"enabled": true}
        },
        "search": {
            "link_wheel": {"enabled": true}
        },
        "book_library": {
            "link_wheel": {"enabled": true}
        }
    }
    """)
