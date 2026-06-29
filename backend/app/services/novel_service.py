from typing import Optional

import math
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.category import Category
from app.models.chapter import Chapter
from app.models.novel import Novel
from app.schemas.common import PaginatedResponse
from app.schemas.novel import NovelCreate, NovelUpdate


async def list_novels(
    db: AsyncSession,
    *,
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    status: Optional[str] = None,
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
) -> PaginatedResponse:
    """List novels with filtering, sorting, and pagination."""
    query = select(Novel).options(selectinload(Novel.categories))

    # Filters
    if search:
        query = query.where(
            Novel.title.ilike(f"%{search}%")
            | Novel.author.ilike(f"%{search}%")
        )
    if status:
        query = query.where(Novel.status == status)
    if category_id is not None:
        query = query.where(Novel.categories.any(Category.id == category_id))

    # Sort
    sort_col = getattr(Novel, sort_by, Novel.updated_at)
    if sort_dir == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    novels = result.unique().scalars().all()

    return PaginatedResponse(
        items=list(novels),
        total=total,
        page=page,
        size=size,
        pages=max(1, math.ceil(total / size)),
    )


async def get_novel(db: AsyncSession, novel_id: str) -> Optional[Novel]:
    """Get a single novel by ID with categories loaded."""
    result = await db.execute(
        select(Novel)
        .options(selectinload(Novel.categories))
        .where(Novel.id == novel_id)
    )
    return result.scalar_one_or_none()


async def create_novel(db: AsyncSession, data: NovelCreate) -> Novel:
    """Create a new novel."""
    novel = Novel(
        title=data.title,
        author=data.author,
        description=data.description,
        source_url=data.source_url,
        source_name=data.source_name,
        status=data.status,
    )
    # Assign categories
    if data.category_ids:
        cat_result = await db.execute(
            select(Category).where(Category.id.in_(data.category_ids))
        )
        novel.categories = cat_result.scalars().all()

    db.add(novel)
    await db.flush()
    await db.refresh(novel)
    return novel


async def update_novel(
    db: AsyncSession, novel: Novel, data: NovelUpdate
) -> Novel:
    """Update an existing novel."""
    update_data = data.model_dump(exclude_unset=True, exclude={"category_ids"})

    for field, value in update_data.items():
        setattr(novel, field, value)

    # Update categories if provided
    if data.category_ids is not None:
        cat_result = await db.execute(
            select(Category).where(Category.id.in_(data.category_ids))
        )
        novel.categories = cat_result.scalars().all()

    await db.flush()
    await db.refresh(novel)
    return novel


async def delete_novel(db: AsyncSession, novel: Novel) -> None:
    """Delete a novel and its chapter content files."""
    # Clean up chapter content files before cascade delete
    from app.services.content_store import adelete_content
    from app.models.chapter import Chapter
    from sqlalchemy import select as sa_select
    chapters = (await db.execute(
        sa_select(Chapter.id, Chapter.content_file).where(Chapter.novel_id == novel.id)
    )).all()
    for ch_id, ch_file in chapters:
        if ch_file:
            await adelete_content(novel.id, str(ch_id), ch_file)
    await db.delete(novel)
    await db.flush()


async def get_novel_statistics(db: AsyncSession, novel_id: str) -> dict:
    """Get statistics for a novel."""
    # Total chapters
    count_result = await db.execute(
        select(func.count(Chapter.id)).where(Chapter.novel_id == novel_id)
    )
    total_chapters = count_result.scalar() or 0

    # Published chapters
    pub_result = await db.execute(
        select(func.count(Chapter.id)).where(
            Chapter.novel_id == novel_id, Chapter.is_published == True
        )
    )
    published_chapters = pub_result.scalar() or 0

    # Total words
    words_result = await db.execute(
        select(func.sum(Chapter.word_count)).where(Chapter.novel_id == novel_id)
    )
    total_words = words_result.scalar() or 0

    # Last updated
    last_result = await db.execute(
        select(func.max(Chapter.updated_at)).where(Chapter.novel_id == novel_id)
    )
    last_updated = last_result.scalar()

    return {
        "novel_id": novel_id,
        "total_chapters": total_chapters,
        "published_chapters": published_chapters,
        "total_words": total_words,
        "last_updated": last_updated,
    }


async def save_cover_image(novel: Novel, file_content: bytes, filename: str) -> str:
    """Save a cover image to static directory and return the URL."""
    import asyncio as _asyncio
    covers_dir = os.path.join(settings.STATIC_DIR, "covers")
    os.makedirs(covers_dir, exist_ok=True)
    ext = os.path.splitext(filename)[1] or ".jpg"
    stored_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(covers_dir, stored_name)

    def _write():
        with open(file_path, "wb") as f:
            f.write(file_content)

    await _asyncio.to_thread(_write)
    return f"/static/covers/{stored_name}"
