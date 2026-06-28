from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.categories import router as categories_router
from app.api.v1.novels import router as novels_router
from app.api.v1.chapters import router as chapters_router
from app.api.v1.search import router as search_router
from app.api.v1.crawler import router as crawler_router
from app.api.v1.rules import router as rules_router
from app.api.v1.sites import router as sites_mgr_router
from app.api.v1.link_rings import router as link_rings_router
from app.api.v1.cache_admin import router as cache_admin_router
from app.api.v1.watchdog_api import router as watchdog_router
from app.api.v1.repair_api import router as repair_router
from app.api.site import router as site_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(categories_router, prefix="/categories", tags=["Categories"])
api_router.include_router(novels_router, prefix="/novels", tags=["Novels"])
api_router.include_router(chapters_router, tags=["Chapters"])
api_router.include_router(search_router, prefix="/search", tags=["Search"])
api_router.include_router(crawler_router, prefix="/crawler", tags=["Crawler"])
api_router.include_router(rules_router, prefix="", tags=["Rules"])
api_router.include_router(sites_mgr_router, tags=["Sites"])
api_router.include_router(link_rings_router, tags=["Link Rings"])
api_router.include_router(cache_admin_router, tags=["Cache"])
api_router.include_router(watchdog_router, tags=["Watchdog"])
api_router.include_router(repair_router, tags=["Repair"])
