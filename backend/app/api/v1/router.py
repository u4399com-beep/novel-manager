from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.categories import router as categories_router
from app.api.v1.novels import router as novels_router
from app.api.v1.chapters import router as chapters_router
from app.api.v1.search import router as search_router
from app.api.v1.crawler import router as crawler_router
from app.api.v1.rules import router as rules_router
from app.api.site import router as site_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(categories_router, prefix="/categories", tags=["Categories"])
api_router.include_router(novels_router, prefix="/novels", tags=["Novels"])
api_router.include_router(chapters_router, tags=["Chapters"])
api_router.include_router(search_router, prefix="/search", tags=["Search"])
api_router.include_router(crawler_router, prefix="/crawler", tags=["Crawler"])
api_router.include_router(rules_router, prefix="", tags=["Rules"])
