"""Search API — FULLTEXT for chapters; ILIKE for novels."""
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.chapter import Chapter
from app.models.novel import Novel
from app.schemas.chapter import ChapterRead
from app.schemas.novel import NovelRead

router = APIRouter()


def _match_clause(column, query: str):
    """Return MATCH AGAINST for FULLTEXT; ILIKE fallback for short queries."""
    # For 1-char queries, FULLTEXT ngram may not match well — use ILIKE
    if len(query.strip()) <= 1:
        return column.ilike(f"%{query}%")
    # Escape special FULLTEXT operators and use BOOLEAN MODE
    safe_q = query.replace("'", "''").replace('"', '""')
    return column.match(safe_q)


@router.get("")
async def search(
    q: str = Query(min_length=1, description="Search query"),
    type: str = Query(default="novel", pattern="^(novel|chapter)$"),
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Search across novels or chapters."""
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

    else:  # chapter — use FULLTEXT index for fast search
        match_filter = _match_clause(Chapter.title, q)
        query = select(Chapter).where(match_filter)

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
