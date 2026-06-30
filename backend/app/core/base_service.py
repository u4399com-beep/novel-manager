"""Base CRUD service — reduce boilerplate across all domain services."""

from typing import Optional, TypeVar, Generic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

T = TypeVar("T", bound=DeclarativeBase)


class BaseService(Generic[T]):
    """Generic CRUD service for any SQLAlchemy model."""

    model: type[T]

    def __init__(self, model: type[T]):
        self.model = model

    async def get_by_id(self, db: AsyncSession, id_val) -> Optional[T]:
        result = await db.execute(select(self.model).where(self.model.id == id_val))
        return result.scalar_one_or_none()

    async def list_all(self, db: AsyncSession, *, offset: int = 0, limit: int = 100) -> list[T]:
        result = await db.execute(
            select(self.model).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def count(self, db: AsyncSession, *filters) -> int:
        q = select(func.count()).select_from(self.model)
        for f in filters:
            q = q.where(f)
        return (await db.execute(q)).scalar() or 0

    async def create(self, db: AsyncSession, **kwargs) -> T:
        obj = self.model(**kwargs)
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    async def update(self, db: AsyncSession, obj: T, **kwargs) -> T:
        for field, value in kwargs.items():
            if value is not None:
                setattr(obj, field, value)
        await db.flush()
        await db.refresh(obj)
        return obj

    async def delete(self, db: AsyncSession, obj: T) -> None:
        await db.delete(obj)
        await db.flush()
