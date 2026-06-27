from typing import Optional

from datetime import datetime

from pydantic import BaseModel, Field


class CrawlerTrigger(BaseModel):
    """Schema for triggering a crawl task."""

    novel_id: str
    source_name: Optional[str] = None  # Uses novel's source_name if not provided


class CrawlerTaskRead(BaseModel):
    """Schema for crawler task response."""

    id: str
    novel_id: str
    status: str
    chapters_found: int
    chapters_added: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CrawlerSourceInfo(BaseModel):
    """Info about an available crawler source."""

    source_name: str
    base_url: str
    description: str
