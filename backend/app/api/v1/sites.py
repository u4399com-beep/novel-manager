"""Site management API for multi-site (站群) system."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.database import get_db
from app.models.site import Site
from app.models.user import User

router = APIRouter(prefix="/sites", tags=["Sites"])

@router.get("")
async def list_sites(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Site).order_by(Site.created_at.desc()))
    return result.scalars().all()

@router.post("", status_code=201)
async def create_site(data: dict, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    site = Site(
        domain=data["domain"], name=data["name"],
        template=data.get("template", "default"),
        offset=data.get("offset", 0),
        description=data.get("description", ""),
        is_active=data.get("is_active", True),
        url_patterns=data.get("url_patterns"),
        chapter_pagination=data.get("chapter_pagination"),
        link_wheel=data.get("link_wheel"),
        recommend_modules=data.get("recommend_modules"),
        language=data.get("language", "zh"),
    )
    db.add(site); await db.flush(); await db.refresh(site)
    return site

@router.put("/{site_id}")
async def update_site(site_id: str, data: dict, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    site = await db.get(Site, site_id)
    if not site: raise HTTPException(404, "Site not found")
    for k in ("domain","name","template","offset","description","is_active",
              "url_patterns","chapter_pagination","link_wheel","recommend_modules","language"):
        if k in data: setattr(site, k, data[k])
    await db.flush(); await db.refresh(site)
    return site

@router.post("/batch-delete", status_code=200)
async def batch_delete_sites(data: dict, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Batch delete sites by IDs. Body: {"ids": ["id1","id2",...]}"""
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(400, "No site IDs provided")
    result = await db.execute(delete(Site).where(Site.id.in_(ids)))
    await db.commit()
    return {"deleted": result.rowcount, "message": f"Deleted {result.rowcount} sites"}


@router.delete("/{site_id}", status_code=204)
async def delete_site(site_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    site = await db.get(Site, site_id)
    if not site: raise HTTPException(404, "Site not found")
    await db.delete(site); await db.flush(); await db.commit()
