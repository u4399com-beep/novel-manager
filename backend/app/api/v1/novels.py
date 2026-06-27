from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.novel import NovelCreate, NovelList, NovelRead, NovelStatistics, NovelUpdate
from app.services import novel_service

router = APIRouter()


@router.get("", response_model=NovelList)
async def list_novels(
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    status: Optional[str] = None,
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
    db: AsyncSession = Depends(get_db),
):
    """List novels with filtering and pagination."""
    return await novel_service.list_novels(
        db,
        page=page,
        size=size,
        search=search,
        category_id=category_id,
        status=status,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.post("", response_model=NovelRead, status_code=status.HTTP_201_CREATED)
async def create_novel(
    data: NovelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new novel."""
    return await novel_service.create_novel(db, data)


@router.get("/{novel_id}", response_model=NovelRead)
async def get_novel(novel_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single novel by ID."""
    novel = await novel_service.get_novel(db, novel_id)
    if not novel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    return novel


@router.put("/{novel_id}", response_model=NovelRead)
async def update_novel(
    novel_id: str,
    data: NovelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a novel."""
    novel = await novel_service.get_novel(db, novel_id)
    if not novel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    return await novel_service.update_novel(db, novel, data)


@router.delete("/{novel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_novel(
    novel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a novel and all its chapters."""
    novel = await novel_service.get_novel(db, novel_id)
    if not novel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    await novel_service.delete_novel(db, novel)


@router.post("/{novel_id}/cover")
async def upload_cover(
    novel_id: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a cover image for a novel."""
    novel = await novel_service.get_novel(db, novel_id)
    if not novel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    content = await file.read()
    url = await novel_service.save_cover_image(novel, content, file.filename or "cover.jpg")
    novel.cover_image_url = url
    await db.flush()

    return {"cover_image_url": url}


@router.get("/{novel_id}/statistics", response_model=NovelStatistics)
async def get_novel_statistics(novel_id: str, db: AsyncSession = Depends(get_db)):
    """Get statistics for a novel."""
    stats = await novel_service.get_novel_statistics(db, novel_id)
    return NovelStatistics(**stats)
