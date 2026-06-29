"""Link wheel (链轮) management API."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.database import get_db
from app.models.link_ring import LinkRing, LinkRingTarget
from app.models.user import User
from app.services.link_wheel_service import create_ring, update_ring, delete_ring

router = APIRouter(prefix="/link-rings", tags=["Link Rings"])


@router.get("")
async def list_rings(
    site_id: str = Query(None, description="Filter by site ID, 'global' for global rings"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(LinkRing)
    if site_id == "global":
        q = q.where(LinkRing.site_id == None)
    elif site_id:
        q = q.where((LinkRing.site_id == site_id) | (LinkRing.site_id == None))

    q = q.order_by(LinkRing.created_at.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{ring_id}")
async def get_ring(
    ring_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ring = await db.get(LinkRing, ring_id)
    if not ring:
        raise HTTPException(status_code=404, detail="Link ring not found")
    return ring


@router.post("", status_code=201)
async def create_link_ring(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if "name" not in data:
        raise HTTPException(status_code=400, detail="Missing required field: name")
    # Normalize: empty string site_id → None (global ring)
    if data.get("site_id") == "":
        data["site_id"] = None
    ring = await create_ring(db, data)
    await db.commit()
    await db.refresh(ring)
    return ring


@router.put("/{ring_id}")
async def update_link_ring(
    ring_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ring = await db.get(LinkRing, ring_id)
    if not ring:
        raise HTTPException(status_code=404, detail="Link ring not found")
    ring = await update_ring(db, ring, data)
    await db.commit()
    return ring


@router.delete("/{ring_id}", status_code=204)
async def delete_link_ring(
    ring_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ring = await db.get(LinkRing, ring_id)
    if not ring:
        raise HTTPException(status_code=404, detail="Link ring not found")
    await delete_ring(db, ring)
    await db.commit()


# ---- Target management within a ring ----

@router.get("/{ring_id}/targets")
async def list_targets(
    ring_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(LinkRingTarget).where(
        LinkRingTarget.ring_id == ring_id
    ).order_by(LinkRingTarget.sort_order)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/{ring_id}/targets", status_code=201)
async def add_target(
    ring_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ring = await db.get(LinkRing, ring_id)
    if not ring:
        raise HTTPException(status_code=404, detail="Link ring not found")

    max_sort = (await db.execute(
        select(func.max(LinkRingTarget.sort_order)).where(LinkRingTarget.ring_id == ring_id)
    )).scalar() or 0

    target = LinkRingTarget(
        ring_id=ring_id,
        source_site_id=data.get("source_site_id"),
        source_novel_id=data.get("source_novel_id"),
        target_site_id=data.get("target_site_id"),
        target_novel_id=data.get("target_novel_id"),
        target_url=data.get("target_url"),
        anchor_text=data.get("anchor_text", "{title}"),
        sort_order=data.get("sort_order", max_sort + 1),
        is_active=data.get("is_active", True),
    )
    db.add(target)
    await db.flush()
    await db.refresh(target)
    return target


@router.put("/{ring_id}/targets/{target_id}")
async def update_target(
    ring_id: str,
    target_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = await db.get(LinkRingTarget, target_id)
    if not target or target.ring_id != ring_id:
        raise HTTPException(status_code=404, detail="Target not found")
    for k in ("source_site_id", "source_novel_id", "target_site_id",
              "target_novel_id", "target_url", "anchor_text", "sort_order", "is_active"):
        if k in data:
            setattr(target, k, data[k])
    await db.flush()
    await db.refresh(target)
    return target


@router.delete("/{ring_id}/targets/{target_id}", status_code=204)
async def delete_target(
    ring_id: str,
    target_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = await db.get(LinkRingTarget, target_id)
    if not target or target.ring_id != ring_id:
        raise HTTPException(status_code=404, detail="Target not found")
    await db.delete(target)
    await db.flush()
