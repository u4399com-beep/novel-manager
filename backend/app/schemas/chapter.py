from typing import Optional

from datetime import datetime

from pydantic import BaseModel, Field


class ChapterCreate(BaseModel):
    """Schema for creating a single chapter."""

    title: str = Field(min_length=1, max_length=255)
    content: Optional[str] = None
    source_url: Optional[str] = None
    is_published: bool = True
    sort_order: Optional[int] = None  # Auto-assigned if not provided


class ChapterUpdate(BaseModel):
    """Schema for updating a chapter."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = None
    source_url: Optional[str] = None
    is_published: Optional[bool] = None
    sort_order: Optional[int] = None


class ChapterRead(BaseModel):
    """Schema for chapter in list view (no content body)."""

    id: str
    novel_id: str
    title: str
    sort_order: int
    word_count: int
    source_url: Optional[str] = None
    is_published: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChapterDetail(ChapterRead):
    """Schema for chapter detail view (includes full content)."""

    content: Optional[str] = None


class ChapterBatchCreate(BaseModel):
    """Schema for batch-creating chapters."""

    chapters: list[ChapterCreate] = Field(min_length=1, max_length=500)


class ChapterBatchDelete(BaseModel):
    """Schema for batch-deleting chapters."""

    ids: list[str] = Field(min_length=1)


class ChapterReorder(BaseModel):
    """Schema for reordering chapters."""

    orders: list[dict[str, int]] = Field(
        min_length=1,
        description='List of {"id": "chapter-uuid", "sort_order": 0} objects',
    )
