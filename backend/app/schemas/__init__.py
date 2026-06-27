from app.schemas.common import (
    ErrorResponse,
    MessageResponse,
    PaginatedResponse,
    PaginationParams,
)
from app.schemas.user import TokenResponse, UserCreate, UserLogin, UserRead, UserUpdate
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.schemas.novel import NovelCreate, NovelList, NovelRead, NovelStatistics, NovelUpdate
from app.schemas.chapter import (
    ChapterBatchCreate,
    ChapterBatchDelete,
    ChapterCreate,
    ChapterDetail,
    ChapterRead,
    ChapterReorder,
    ChapterUpdate,
)
from app.schemas.crawler import CrawlerSourceInfo, CrawlerTaskRead, CrawlerTrigger

__all__ = [
    # Common
    "PaginatedResponse",
    "MessageResponse",
    "ErrorResponse",
    "PaginationParams",
    # User
    "UserCreate",
    "UserLogin",
    "UserRead",
    "UserUpdate",
    "TokenResponse",
    # Category
    "CategoryCreate",
    "CategoryRead",
    "CategoryUpdate",
    # Novel
    "NovelCreate",
    "NovelRead",
    "NovelUpdate",
    "NovelList",
    "NovelStatistics",
    # Chapter
    "ChapterCreate",
    "ChapterRead",
    "ChapterDetail",
    "ChapterUpdate",
    "ChapterBatchCreate",
    "ChapterReorder",
    "ChapterBatchDelete",
    # Crawler
    "CrawlerTrigger",
    "CrawlerTaskRead",
    "CrawlerSourceInfo",
]
