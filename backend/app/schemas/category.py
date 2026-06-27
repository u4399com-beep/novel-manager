from typing import Optional

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    """Schema for creating a category."""

    name: str = Field(min_length=1, max_length=64)
    slug: str = Field(min_length=1, max_length=64)
    description: Optional[str] = None
    sort_order: int = Field(default=0)


class CategoryUpdate(BaseModel):
    """Schema for updating a category."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = None
    sort_order: Optional[int] = None


class CategoryRead(BaseModel):
    """Schema for category response."""

    id: int
    name: str
    slug: str
    description: Optional[str] = None
    sort_order: int

    model_config = {"from_attributes": True}
