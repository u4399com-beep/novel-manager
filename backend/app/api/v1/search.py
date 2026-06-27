import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.chapter import Chapter
from app.models.novel import Novel
from app.schemas.chapter import ChapterRead
from app.schemas.novel import NovelRead

router = APIRouter()


@router.get("")
async def search(
    q: str = Query(min_length=1, description="Search query"),
    type: str = Query(default="novel", pattern="^(novel|chapter)$"),
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Search across novels or chapters using LIKE matching."""
    if type == "novel":
        query = (
            select(Novel)
            .where(
                Novel.title.ilike(f"%{q}%")
                | Novel.author.ilike(f"%{q}%")
                | Novel.description.ilike(f"%{q}%")
            )
        )
        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        query = query.order_by(Novel.updated_at.desc()).offset((page - 1) * size).limit(size)
        result = await db.execute(query)
        items = [NovelRead.model_validate(n) for n in result.unique().scalars().all()]

    else:  # chapter
        query = (
            select(Chapter)
            .where(
                Chapter.title.ilike(f"%{q}%")
                | Chapter.content.ilike(f"%{q}%")
            )
        )
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Chapter.updated_at.desc()).offset((page - 1) * size).limit(size)
        result = await db.execute(query)
        items = [ChapterRead.model_validate(c) for c in result.scalars().all()]

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)),
    }
