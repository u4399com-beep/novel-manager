"""Public-facing SEO-friendly site routes (Jinja2 SSR)."""

import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.category import Category
from app.models.chapter import Chapter
from app.models.novel import Novel
from app.services.chapter_service import get_chapter_content

router = APIRouter(tags=["Site"])

templates = Jinja2Templates(directory="app/templates")


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def site_home(
    request: Request,
    page: int = 1,
    category: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    size = 24
    query = select(Novel).options(selectinload(Novel.categories))

    if category:
        query = query.where(Novel.categories.any(Category.id == category))

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(Novel.updated_at.desc()).offset((page - 1) * size).limit(size)
    novels = (await db.execute(query)).unique().scalars().all()

    cats = (await db.execute(select(Category).order_by(Category.sort_order))).scalars().all()

    return templates.TemplateResponse("pages/home.html", {
        "request": request,
        "novels": novels,
        "categories": cats,
        "page": page,
        "pages": max(1, math.ceil(total / size)),
        "now": _now(),
        "canonical_url": str(request.url).split("?")[0],
    })


# ---------------------------------------------------------------------------
# Novel detail
# ---------------------------------------------------------------------------

@router.get("/novel/{novel_id}", response_class=HTMLResponse)
async def site_novel(
    request: Request,
    novel_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Novel)
        .options(selectinload(Novel.categories))
        .where(Novel.id == novel_id)
    )
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404)

    # Fetch recent chapters
    chapters = (await db.execute(
        select(Chapter)
        .where(Chapter.novel_id == novel_id)
        .order_by(Chapter.sort_order.desc()).limit(15)
    )).scalars().all()

    cats = (await db.execute(select(Category).order_by(Category.sort_order))).scalars().all()

    return templates.TemplateResponse("pages/novel.html", {
        "request": request,
        "novel": novel,
        "chapters": list(chapters),
        "categories": cats,
        "now": _now(),
    })


# ---------------------------------------------------------------------------
# Chapter list
# ---------------------------------------------------------------------------

@router.get("/novel/{novel_id}/chapters", response_class=HTMLResponse)
async def site_chapter_list(
    request: Request,
    novel_id: str,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    novel = (await db.execute(
        select(Novel).where(Novel.id == novel_id)
    )).scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404)

    # Fetch all chapters
    all_chapters = (await db.execute(
        select(Chapter)
        .where(Chapter.novel_id == novel_id)
        .order_by(Chapter.sort_order)
    )).scalars().all()

    # Group by actual volume field from DB
    grouped: list[dict] = []
    if all_chapters:
        current_vol = {"title": "正文", "chapters": []}
        for ch in all_chapters:
            vol = (ch.volume or "").strip()
            if vol and current_vol["title"] != vol:
                if current_vol["chapters"]:
                    grouped.append(current_vol)
                current_vol = {"title": vol, "chapters": []}
            current_vol["chapters"].append(ch)
        grouped.append(current_vol)

    cats = (await db.execute(select(Category).order_by(Category.sort_order))).scalars().all()
    return templates.TemplateResponse("pages/chapter_list.html", {
        "request": request,
        "novel": novel,
        "grouped": grouped if len(grouped) > 1 else [],
        "all_chapters": all_chapters,
        "total": len(all_chapters),
        "categories": cats,
        "now": _now(),
    })


# ---------------------------------------------------------------------------
# Chapter reader
# ---------------------------------------------------------------------------

@router.get("/chapter/{chapter_id}", response_class=HTMLResponse)
async def site_chapter(
    request: Request,
    chapter_id: str,
    db: AsyncSession = Depends(get_db),
):
    chapter = (await db.execute(
        select(Chapter).where(Chapter.id == chapter_id)
    )).scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404)

    novel = (await db.execute(
        select(Novel).where(Novel.id == chapter.novel_id)
    )).scalar_one_or_none()

    # Prev / Next
    prev_ch = (await db.execute(
        select(Chapter)
        .where(Chapter.novel_id == chapter.novel_id, Chapter.sort_order < chapter.sort_order)
        .order_by(Chapter.sort_order.desc()).limit(1)
    )).scalar_one_or_none()

    next_ch = (await db.execute(
        select(Chapter)
        .where(Chapter.novel_id == chapter.novel_id, Chapter.sort_order > chapter.sort_order)
        .order_by(Chapter.sort_order).limit(1)
    )).scalar_one_or_none()

    # Read content from file store (or DB fallback)
    chapter_content = await get_chapter_content(chapter)
    chapter.content = chapter_content  # inject for template

    cats = (await db.execute(select(Category).order_by(Category.sort_order))).scalars().all()
    return templates.TemplateResponse("pages/chapter.html", {
        "request": request,
        "novel": novel,
        "chapter": chapter,
        "categories": cats,
        "prev_id": str(prev_ch.id) if prev_ch else "",
        "prev_title": prev_ch.title if prev_ch else "",
        "next_id": str(next_ch.id) if next_ch else "",
        "next_title": next_ch.title if next_ch else "",
        "now": _now(),
    })


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.get("/search", response_class=HTMLResponse)
async def site_search(
    request: Request,
    q: str = "",
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    results = []
    total = 0
    if q:
        size = 20
        query = select(Novel).options(selectinload(Novel.categories)).where(
            Novel.title.ilike(f"%{q}%") | Novel.author.ilike(f"%{q}%")
        )
        count_q = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_q)).scalar() or 0
        query = query.order_by(Novel.updated_at.desc()).offset((page - 1) * size).limit(size)
        results = (await db.execute(query)).unique().scalars().all()

    cats = (await db.execute(select(Category).order_by(Category.sort_order))).scalars().all()
    return templates.TemplateResponse("pages/search.html", {
        "request": request,
        "query": q,
        "results": results,
        "categories": cats,
        "page": page,
        "pages": max(1, math.ceil(total / 20)) if total else 0,
        "total": total,
        "now": _now(),
    })


# ---------------------------------------------------------------------------
# Book library page
# ---------------------------------------------------------------------------

@router.get("/novels", response_class=HTMLResponse)
async def site_novels(
    request: Request,
    page: int = 1,
    category: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    size = 30
    query = select(Novel).options(selectinload(Novel.categories))

    if category:
        query = query.where(Novel.categories.any(Category.id == category))
    if status:
        query = query.where(Novel.status == status)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(Novel.updated_at.desc()).offset((page - 1) * size).limit(size)
    novels = (await db.execute(query)).unique().scalars().all()
    cats = (await db.execute(select(Category).order_by(Category.sort_order))).scalars().all()

    return templates.TemplateResponse("pages/home.html", {
        "request": request,
        "novels": novels,
        "categories": cats,
        "page": page,
        "pages": max(1, math.ceil(total / size)),
        "now": _now(),
    })
