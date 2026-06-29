"""Unified API response schemas and helpers."""

from typing import Optional, Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response envelope."""

    items: list[T] = Field(default_factory=list)
    total: int = Field(default=0)
    page: int = Field(default=1)
    size: int = Field(default=20)
    pages: int = Field(default=0)


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


class ErrorResponse(BaseModel):
    """Error response envelope."""

    detail: str
    error_code: Optional[str] = None


class PaginationParams(BaseModel):
    """Common pagination query parameters."""

    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


# ── Unified API response helpers ──────────────────────────────────


def ok(data: Any = None, **kwargs) -> dict:
    """Unified success response."""
    result = {"data": data} if data is not None else {}
    result.update(kwargs)
    return result


def paginated(items: list, total: int, page: int, size: int) -> dict:
    """Unified paginated response."""
    import math
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / max(size, 1))),
    }


def err(detail: str, error_code: Optional[str] = None) -> ErrorResponse:
    """Unified error response."""
    return ErrorResponse(detail=detail, error_code=error_code)
