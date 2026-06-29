from typing import Optional

import re

import asyncio

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.novel import Novel
from app.services import content_store


async def _invalidate_cache(novel_id: str):
    """Fire-and-forget cache invalidation after chapter mutations."""
    try:
        from app.services.write_behind_cache import invalidate_novel
        await invalidate_novel(novel_id)
    except Exception:
        pass


def count_words(text: Optional[str]) -> int:
    """Count words in chapter content (Chinese-aware).

    Strips HTML tags, then counts Chinese characters + English words.
    """
    if not text:
        return 0
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", "", text)
    # Count Chinese characters
    chinese_chars = len(re.findall(r"[一-鿿]", clean))
    # Count English words
    english_words = len(re.findall(r"[a-zA-Z]+", clean))
    return chinese_chars + english_words


async def get_chapters(
    db: AsyncSession,
    novel_id: str,
    *,
    page: int = 1,
    size: int = 50,
    include_content: bool = False,
) -> tuple[list[Chapter], int]:
    """Get paginated chapters for a novel, ordered by sort_order."""
    query = select(Chapter).where(Chapter.novel_id == novel_id)

    # Count
    count_query = select(func.count(Chapter.id)).where(
        Chapter.novel_id == novel_id
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Order and paginate
    query = query.order_by(Chapter.sort_order.asc())
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    chapters = result.scalars().all()

    return list(chapters), total


async def get_chapter(db: AsyncSession, chapter_id: str) -> Optional[Chapter]:
    """Get a single chapter by ID."""
    result = await db.execute(
        select(Chapter).where(Chapter.id == chapter_id)
    )
    return result.scalar_one_or_none()


async def get_chapter_content(chapter: Chapter) -> str:
    """Read chapter content from file store (with cache), falling back to DB."""
    if chapter.content_file:
        text = await content_store.aread_content(
            chapter.novel_id, str(chapter.id), chapter.content_file
        )
        if text:
            return text
    # Fallback: old DB-stored content
    return chapter.content or ""


async def create_chapter(
    db: AsyncSession, novel_id: str, title: str, content: Optional[str] = None,
    source_url: Optional[str] = None, is_published: bool = True,
    sort_order: Optional[int] = None,
) -> Chapter:
    """Create a single chapter, auto-assigning sort_order if not provided."""
    if sort_order is None:
        # Auto-assign: max existing + 1
        max_result = await db.execute(
            select(func.max(Chapter.sort_order)).where(
                Chapter.novel_id == novel_id
            )
        )
        max_order = max_result.scalar() or 0
        sort_order = max_order + 1

    chapter = Chapter(
        novel_id=novel_id,
        title=title,
        source_url=source_url,
        is_published=is_published,
        sort_order=sort_order,
        word_count=count_words(content),
    )
    # volume is passed via **kwargs or set after
    db.add(chapter)
    await db.flush()
    # Write content to compressed file
    if content:
        chapter.content_file = await content_store.awrite_content(novel_id, str(chapter.id), content)

    # Update novel's total_chapters (atomic +1)
    await _recount_novel_chapters(db, novel_id, delta=1)

    await db.refresh(chapter)
    asyncio.create_task(_invalidate_cache(novel_id))
    return chapter


async def update_chapter(
    db: AsyncSession, chapter: Chapter, update_data: dict
) -> Chapter:
    """Update a chapter's fields."""
    for field, value in update_data.items():
        if value is not None:
            setattr(chapter, field, value)

    # Recompute word count if content changed
    if "content" in update_data:
        chapter.word_count = count_words(chapter.content)

    await db.flush()
    await db.refresh(chapter)
    return chapter


async def delete_chapter(db: AsyncSession, chapter: Chapter) -> None:
    """Delete a chapter and update novel's chapter count."""
    novel_id = chapter.novel_id
    await db.delete(chapter)
    await db.flush()
    await _recount_novel_chapters(db, novel_id, delta=-1)
    asyncio.create_task(_invalidate_cache(novel_id))


async def batch_create_chapters(
    db: AsyncSession, novel_id: str, chapters_data: list[dict]
) -> list[Chapter]:
    """Batch create chapters in a single transaction.

    Chapters with empty or invalid titles are silently skipped.
    """
    from app.crawlers.content_cleaner import is_valid_chapter_title

    # Get current max sort_order
    max_result = await db.execute(
        select(func.max(Chapter.sort_order)).where(Chapter.novel_id == novel_id)
    )
    max_order = max_result.scalar() or 0

    chapters = []
    accepted = 0
    for data in chapters_data:
        # Skip chapters with garbage titles
        raw_title = data.get("title", "")
        if not is_valid_chapter_title(raw_title):
            continue
        accepted += 1

        sort_order = data.get("sort_order")
        if sort_order is None:
            sort_order = max_order + accepted

        text = data.get("content", "")
        chapter = Chapter(
            novel_id=novel_id,
            title=raw_title,
            source_url=data.get("source_url"),
            is_published=data.get("is_published", True),
            sort_order=sort_order,
            word_count=count_words(text),
            volume=data.get("volume", ""),
        )
        db.add(chapter)
        chapters.append(chapter)
        # Flush to get chapter.id, then write content file
        if text:
            await db.flush()
            chapter.content_file = await content_store.awrite_content(novel_id, str(chapter.id), text)

    await db.flush()
    await _recount_novel_chapters(db, novel_id, delta=len(chapters))

    for ch in chapters:
        await db.refresh(ch)
    asyncio.create_task(_invalidate_cache(novel_id))
    return chapters


async def reorder_chapters(
    db: AsyncSession, novel_id: str, orders: list[dict[str, int]]
) -> None:
    """Reorder chapters with a single bulk CASE UPDATE."""
    if not orders:
        return
    # Build CASE expression: WHEN id=X THEN Y WHEN id=Z THEN W ... ELSE sort_order
    sort_map = {item["id"]: item["sort_order"] for item in orders}
    id_list = list(sort_map.keys())
    sort_case = case(sort_map, value=Chapter.id, else_=Chapter.sort_order)
    await db.execute(
        update(Chapter)
        .where(Chapter.id.in_(id_list), Chapter.novel_id == novel_id)
        .values(sort_order=sort_case)
    )
    await db.flush()


async def batch_delete_chapters(
    db: AsyncSession, novel_id: str, chapter_ids: list[str]
) -> int:
    """Batch delete chapters with a single DELETE statement."""
    if not chapter_ids:
        return 0
    result = await db.execute(
        delete(Chapter).where(
            Chapter.id.in_(chapter_ids),
            Chapter.novel_id == novel_id,
        )
    )
    deleted = result.rowcount
    await db.flush()
    await _recount_novel_chapters(db, novel_id, delta=-deleted)
    asyncio.create_task(_invalidate_cache(novel_id))
    return deleted


async def _recount_novel_chapters(
    db: AsyncSession, novel_id: str, delta: Optional[int] = None
) -> None:
    """Update the novel's total_chapters denormalized count.

    When *delta* is provided, uses an atomic ``total_chapters + delta``
    increment (no COUNT scan).  When *delta* is None, falls back to a
    full ``SELECT COUNT(*)`` for correctness (e.g. repair / migration).
    """
    if delta is not None and delta != 0:
        await db.execute(
            update(Novel)
            .where(Novel.id == novel_id)
            .values(total_chapters=Novel.total_chapters + delta)
        )
    else:
        count_result = await db.execute(
            select(func.count(Chapter.id)).where(Chapter.novel_id == novel_id)
        )
        count = count_result.scalar() or 0
        await db.execute(
            update(Novel).where(Novel.id == novel_id).values(total_chapters=count)
        )
