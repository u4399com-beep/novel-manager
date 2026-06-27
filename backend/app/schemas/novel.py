from typing import Optional

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.category import CategoryRead


class NovelCreate(BaseModel):
    """Schema for creating a novel."""

    title: str = Field(min_length=1, max_length=255)
    author: str = Field(min_length=1, max_length=128)
    description: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    status: str = Field(default="ongoing", pattern="^(ongoing|completed|hiatus)$")
    category_ids: list[int] = Field(default_factory=list)


class NovelUpdate(BaseModel):
    """Schema for updating a novel."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    author: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(ongoing|completed|hiatus)$")
    category_ids: Optional[list[int]] = None


class NovelRead(BaseModel):
    """Schema for novel response (list view, without full chapters)."""

    id: str
    title: str
    author: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    status: str
    total_chapters: int
    categories: list[CategoryRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NovelList(BaseModel):
    """Paginated novel list response."""

    items: list[NovelRead]
    total: int
    page: int
    size: int
    pages: int


class NovelStatistics(BaseModel):
    """Novel statistics."""

    novel_id: str
    total_chapters: int
    total_words: int
    published_chapters: int
    last_updated: Optional[datetime]
