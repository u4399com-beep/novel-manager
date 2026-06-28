"""Middleware to detect current site from domain and attach to request."""
from contextvars import ContextVar
from typing import Optional
from app.models.site import Site as SiteModel

current_site: ContextVar[Optional[SiteModel]] = ContextVar("current_site", default=None)

async def get_current_site(request, db_session) -> Optional[SiteModel]:
    """Resolve the current site from request host."""
    host = request.headers.get("host", "").split(":")[0]
    from sqlalchemy import select
    result = await db_session.execute(
        select(SiteModel).where(SiteModel.domain == host, SiteModel.is_active == True)
    )
    return result.scalars().first()
