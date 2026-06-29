from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.category import Category
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter()


# ── In-process TTL cache for ORM objects ──
_orm_cache: dict[str, tuple[float, object]] = {}


@router.get("", response_model=list[CategoryRead])
async def list_categories(db: AsyncSession = Depends(get_db)):
    """List all categories, ordered by sort_order (cached 5 min)."""
    import time
    cache_key = "all_categories_api"
    now = time.monotonic()
    if cache_key in _orm_cache:
        expiry, val = _orm_cache[cache_key]
        if now < expiry:
            return val

    result = await db.execute(
        select(Category).order_by(Category.sort_order.asc())
    )
    cats = result.scalars().all()
    _orm_cache[cache_key] = (now + 300, cats)
    return cats


async def _invalidate_category_cache():
    """Invalidate cached category queries after mutation."""
    _orm_cache.pop("all_categories_api", None)
    from app.services.redis_cache import delete_pattern
    await delete_pattern("query", "*categories*")


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new category."""
    category = Category(**data.model_dump())
    db.add(category)
    await db.flush()
    await db.refresh(category)
    await _invalidate_category_cache()
    return category


@router.get("/{category_id}", response_model=CategoryRead)
async def get_category(category_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single category by ID."""
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.put("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a category."""
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    await db.flush()
    await db.refresh(category)
    await _invalidate_category_cache()
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a category."""
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    await db.delete(category)
    await db.flush()
    await _invalidate_category_cache()
