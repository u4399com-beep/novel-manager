"""Search API — FULLTEXT for chapters; ILIKE for novels."""
import math
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
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
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Search across novels or chapters.

    Chapter search requires >=2 characters (ngram FULLTEXT minimum).
    Shorter queries are rejected to avoid full-table scans on 1.9M rows.
    """
    if type == "chapter" and len(q.strip()) < 2:
        return {"items": [], "total": 0, "page": 1, "size": size, "pages": 0}

    if type == "novel":
        query = (
            select(Novel)
            .where(
                Novel.title.ilike(f"%{q}%")
                | Novel.author.ilike(f"%{q}%")
                | Novel.description.ilike(f"%{q}%")
            )
        )
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Novel.updated_at.desc()).offset((page - 1) * size).limit(size)
        result = await db.execute(query)
        items = [NovelRead.model_validate(n) for n in result.unique().scalars().all()]

    else:  # chapter — FULLTEXT for 3+ chars; ILIKE for 2-char
        qs = q.strip()
        if len(qs) >= 3:
            # Strip FULLTEXT boolean operators to prevent syntax errors
            safe_q = re.sub(r'[+\-><()~*"@]', '', qs).replace("'", "''")
            match_filter = Chapter.title.match(safe_q)
        else:
            # 2-char: ILIKE (acceptable row count for 2-char patterns)
            match_filter = Chapter.title.ilike(f"%{qs}%")

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
