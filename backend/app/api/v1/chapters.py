import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.chapter import (
    ChapterBatchCreate,
    ChapterBatchDelete,
    ChapterCreate,
    ChapterDetail,
    ChapterRead,
    ChapterReorder,
    ChapterUpdate,
)
from app.services import chapter_service
from app.services.novel_service import get_novel

router = APIRouter()


@router.get("/novels/{novel_id}/chapters", response_model=dict)
async def list_chapters(
    novel_id: str,
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List chapters for a novel."""
    # Verify novel exists
    novel = await get_novel(db, novel_id)
    if not novel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    chapters, total = await chapter_service.get_chapters(db, novel_id, page=page, size=size)
    return {
        "items": [ChapterRead.model_validate(c) for c in chapters],
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)),
    }


@router.post(
    "/novels/{novel_id}/chapters",
    response_model=ChapterRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_chapter(
    novel_id: str,
    data: ChapterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new chapter."""
    novel = await get_novel(db, novel_id)
    if not novel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    return await chapter_service.create_chapter(
        db,
        novel_id=novel_id,
        title=data.title,
        content=data.content,
        source_url=data.source_url,
        is_published=data.is_published,
        sort_order=data.sort_order,
    )


@router.get("/novels/{novel_id}/chapters/{chapter_id}", response_model=ChapterDetail)
async def get_chapter(
    novel_id: str,
    chapter_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single chapter with full content."""
    chapter = await chapter_service.get_chapter(db, chapter_id)
    if not chapter or chapter.novel_id != novel_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")
    return chapter


@router.put("/novels/{novel_id}/chapters/{chapter_id}", response_model=ChapterRead)
async def update_chapter(
    novel_id: str,
    chapter_id: str,
    data: ChapterUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a chapter."""
    chapter = await chapter_service.get_chapter(db, chapter_id)
    if not chapter or chapter.novel_id != novel_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")

    update_data = data.model_dump(exclude_unset=True)
    return await chapter_service.update_chapter(db, chapter, update_data)


@router.delete("/novels/{novel_id}/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chapter(
    novel_id: str,
    chapter_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a chapter."""
    chapter = await chapter_service.get_chapter(db, chapter_id)
    if not chapter or chapter.novel_id != novel_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")
    await chapter_service.delete_chapter(db, chapter)


@router.post(
    "/novels/{novel_id}/chapters/batch",
    response_model=list[ChapterRead],
    status_code=status.HTTP_201_CREATED,
)
async def batch_create_chapters(
    novel_id: str,
    data: ChapterBatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch create chapters."""
    novel = await get_novel(db, novel_id)
    if not novel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    chapters_dicts = [c.model_dump() for c in data.chapters]
    return await chapter_service.batch_create_chapters(db, novel_id, chapters_dicts)


@router.put("/novels/{novel_id}/chapters/reorder")
async def reorder_chapters(
    novel_id: str,
    data: ChapterReorder,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reorder chapters."""
    novel = await get_novel(db, novel_id)
    if not novel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    await chapter_service.reorder_chapters(db, novel_id, data.orders)
    return {"message": "Chapters reordered successfully"}


@router.delete("/novels/{novel_id}/chapters/batch")
async def batch_delete_chapters(
    novel_id: str,
    data: ChapterBatchDelete,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch delete chapters."""
    novel = await get_novel(db, novel_id)
    if not novel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    deleted = await chapter_service.batch_delete_chapters(db, novel_id, data.ids)
    return {"message": f"Deleted {deleted} chapters"}
