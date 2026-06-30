"""Search API — ILIKE search (works on MySQL, PostgreSQL, SQLite)."""
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
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
    """Search novels or chapters using ILIKE (cross-database compatible)."""
    if len(q.strip()) < 2:
        return {"items": [], "total": 0, "page": 1, "size": size, "pages": 0}

    qs = f"%{q.strip()}%"

    if type == "novel":
        query = select(Novel).where(
            Novel.title.ilike(qs) | Novel.author.ilike(qs) | Novel.description.ilike(qs)
        )
    else:
        query = select(Chapter).where(Chapter.title.ilike(qs))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Novel.updated_at.desc() if type == "novel" else Chapter.updated_at.desc())
    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)

    if type == "novel":
        items = [NovelRead.model_validate(n) for n in result.unique().scalars().all()]
    else:
        items = [ChapterRead.model_validate(c) for c in result.scalars().all()]

    return {"items": items, "total": total, "page": page, "size": size,
            "pages": max(1, math.ceil(total / max(size, 1)))}
