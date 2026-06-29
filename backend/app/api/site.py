"""Public-facing SEO-friendly site routes (Jinja2 SSR).

Features:
    - Pseudo-static URL patterns per site
    - Chapter content pagination (by word count or page count)
    - Link wheel (链轮) rendering
"""

import asyncio
import math
import os
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.category import Category
from app.models.chapter import Chapter
from app.models.novel import Novel
from app.models.site import Site
from app.services.chapter_service import get_chapter_content
from app.services.link_wheel_service import resolve_links_for_page
from app.i18n import t as i18n_t, load_translations, get_language_list
from app.services.translator import translate_text as tr_content

# ---------------------------------------------------------------------------
# Template resolution — site-specific templates override defaults
# ---------------------------------------------------------------------------

_tpl_cache: dict[str, Jinja2Templates] = {}
TEMPLATES_BASE = os.path.join(os.path.dirname(__file__), "..", "templates")


async def _check_page_cache(page_type: str, site, path: str, query: str) -> Optional[str]:
    """Two-level cache check: Redis (L1, cross-worker) → Memory LRU (L2).

    Returns cached HTML or None.  Must be called BEFORE DB queries.
    """
    from app.services.redis_cache import get as redis_get
    from app.services.page_cache import page_cache

    lang = site.language if site else "zh"

    # L1: Redis (shared across all workers — fixes 0% hit rate under load)
    cached = await redis_get("page", page_type, path, query, lang)
    if cached:
        # Promote to L2 for even faster subsequent hits
        await page_cache.set(page_type, path, query, lang, cached)
        return cached

    # L2: In-memory LRU (process-local, microsecond latency)
    return await page_cache.get(page_type, path, query, lang)


async def _render_page(
    page_type: str,
    tpl: Jinja2Templates,
    template_name: str,
    context: dict,
    site,
    path: str,
    query: str,
) -> HTMLResponse:
    """Render + cache (L1 Redis + L2 Memory) + return HTMLResponse."""
    from app.services.redis_cache import set as redis_set
    from app.services.page_cache import page_cache

    lang = site.language if site else "zh"
    html = await asyncio.to_thread(tpl.env.get_template(template_name).render, context)

    # L2: In-memory (microsecond)
    await page_cache.set(page_type, path, query, lang, html)
    # L1: Redis (awaited — must complete before response so other workers see it)
    await redis_set("page", html, page_type, path, query, lang)

    return HTMLResponse(html)


def _get_templates(site_template: str = "default") -> Jinja2Templates:
    """Return a Jinja2Templates that searches the site directory first."""
    site_template = site_template or "default"
    if site_template not in _tpl_cache:
        paths = [
            os.path.join(TEMPLATES_BASE, site_template),
            TEMPLATES_BASE,
        ]
        existing = [p for p in paths if os.path.isdir(p)]
        loader = FileSystemLoader(existing)
        env = Environment(loader=loader, autoescape=True)

        # Add translation filter
        _t_cache = {}
        def _translate_filter(text, target_lang):
            if not text or target_lang == "zh":
                return text
            cache_key = f"{hash(text)}:{target_lang}"
            if cache_key in _t_cache:
                return _t_cache[cache_key]
            try:
                import httpx
                resp = httpx.post("http://localhost:5001/translate", json={
                    "q": text, "source": "auto", "target": target_lang, "format": "text"
                }, timeout=10)
                if resp.status_code == 200:
                    result = resp.json()["translatedText"]
                    if result:
                        _t_cache[cache_key] = result
                        return result
            except:
                pass
            return text
        env.filters["translate"] = _translate_filter
        _tpl_cache[site_template] = Jinja2Templates(env=env)
    return _tpl_cache[site_template]


# Site context helper
# ── In-process TTL cache for ORM objects (avoids Redis serialization) ──
_orm_cache: dict[str, tuple[float, object]] = {}


def _cached_orm(key: str, ttl: int, compute):
    """Simple in-process TTL cache for ORM objects."""
    import time
    now = time.monotonic()
    if key in _orm_cache:
        expiry, val = _orm_cache[key]
        if now < expiry:
            return val
    return None  # miss — caller must compute and store


def _set_orm_cache(key: str, val: object, ttl: int):
    import time
    _orm_cache[key] = (time.monotonic() + ttl, val)


async def _get_site(request, db) -> Optional[Site]:
    """Resolve the current Site from the request Host header (cached 1h)."""
    host = request.headers.get("host", "").split(":")[0]
    cache_key = f"site:{host}"

    cached = _cached_orm(cache_key, ttl=3600, compute=None)
    if cached is not None:
        return cached

    result = await db.execute(
        select(Site).where(Site.domain == host, Site.is_active == True)
    )
    site = result.scalars().first()
    _set_orm_cache(cache_key, site, ttl=3600)
    return site


async def _get_categories(db) -> list:
    """Fetch all categories (cached 5min — changes rarely)."""
    cache_key = "all_categories"

    cached = _cached_orm(cache_key, ttl=300, compute=None)
    if cached is not None:
        return cached

    cats = (await db.execute(
        select(Category).order_by(Category.sort_order)
    )).scalars().all()
    _set_orm_cache(cache_key, cats, ttl=300)
    return cats


router = APIRouter(tags=["Site"])

# Default templates (used when no site matches)
templates = Jinja2Templates(directory="app/templates")


def _now():
    return datetime.now(timezone.utc)


def _tr(site: Optional[Site], key: str, **kwargs) -> str:
    """Translate *key* to the site's language."""
    lang = site.language if site and site.language else "zh"
    return i18n_t(lang, key, **kwargs)


def _site_context(site: Optional[Site], **extra) -> dict:
    """Build common template context with language support."""
    lang = site.language if site and site.language else "zh"
    return {
        "lang": lang,
        "T": lambda key, **kw: i18n_t(lang, key, **kw),
        "lang_name": {"zh":"中文","en":"English","ja":"日本語","ko":"한국어","fr":"Français","de":"Deutsch","es":"Español","pt":"Português","ru":"Русский","ar":"العربية","th":"ภาษาไทย","vi":"Tiếng Việt","id":"Bahasa Indonesia","it":"Italiano","tr":"Türkçe","hi":"हिन्दी","fa":"فارسی","cs":"Čeština","da":"Dansk","nl":"Nederlands","fi":"Suomi","el":"Ελληνικά","he":"עברית","hu":"Magyar","ga":"Gaeilge","pl":"Polski","sk":"Slovenčina","sv":"Svenska","uk":"Українська","az":"Azərbaycan"}.get(lang, "中文"),
        "target_lang": lang,
        **extra,
    }


async def _tr_content(db, novel, chapter, cats, lang: str):
    """Translate content. Disabled: Google Translate blocked by firewall."""
    return  # no-op stub — re-enable when firewall allows


# ---------------------------------------------------------------------------
# Recommend module helper — check if a module is enabled for this page
# ---------------------------------------------------------------------------





def _module_enabled(site: Optional[Site], page: str, module: str) -> bool:
    """Check if a recommend module is enabled for the given page type.

    Returns True if the module config is missing (default=enabled) or
    if the module's ``enabled`` field is truthy.
    """
    if not site or not site.recommend_modules:
        return True  # no config = all enabled
    page_cfg = site.recommend_modules.get(page, {})
    mod_cfg = page_cfg.get(module, {})
    if not mod_cfg:
        return True  # module not configured = enabled by default
    return mod_cfg.get("enabled", True)


def _build_modules(site: Optional[Site], page: str, *modules: str) -> dict:
    """Build a {module: bool} dict for template conditional rendering."""
    return {m: _module_enabled(site, page, m) for m in modules}


async def _safe_link_wheel(site, db, novel_id, page_type):
    """Fetch link wheel links with error handling."""
    if not site:
        return []
    try:
        return await resolve_links_for_page(
            db, site.id, novel_id, page_type=page_type,
            max_total=site.link_wheel.get("max_links_per_page", 8) if site.link_wheel else 8,
        )
    except Exception as exc:
        import logging; logging.getLogger("site").warning(
            "Link wheel failed for site=%s page=%s: %s", site.id, page_type, exc)
        return []




# ---------------------------------------------------------------------------
# Pseudo-static URL builder
# ---------------------------------------------------------------------------

def _build_url(site: Optional[Site], pattern_key: str, **kwargs) -> str:
    """Build a URL using the site's pseudo-static pattern.

    Args:
        site: Site model (or None for defaults)
        pattern_key: e.g. "novel_detail", "chapter_read", "chapter_list"
        **kwargs: values to substitute into the pattern (e.g. id="...")
    """
    defaults = {
        "novel_detail": "/novel/{id}/",
        "chapter_list": "/novel/{id}/chapters/",
        "chapter_read": "/chapter/{id}/",
        "category_list": "/novels?category={id}",
        "search": "/search?q={keyword}",
    }
    if site and site.url_patterns:
        pattern = site.url_patterns.get(pattern_key, defaults.get(pattern_key, ""))
    else:
        pattern = defaults.get(pattern_key, "")

    # Simple {key} substitution
    for k, v in kwargs.items():
        pattern = pattern.replace(f"{{{k}}}", str(v))
    return pattern


# ---------------------------------------------------------------------------
# Chapter content pagination
# ---------------------------------------------------------------------------

def _paginate_chapter(content: str, site: Optional[Site]) -> list[str]:
    """Split chapter content into pages based on site config.

    Returns list of page contents. Single element = no pagination.
    """
    if not content or not site or not site.chapter_pagination:
        return [content]

    cfg = site.chapter_pagination
    if not cfg.get("enabled"):
        return [content]

    method = cfg.get("method", "word_count")

    if method == "word_count":
        words_per_page = cfg.get("words_per_page", 3000)
        return _split_by_words(content, words_per_page)
    elif method == "page_count":
        pages_count = cfg.get("pages_per_chapter", 2)
        return _split_by_pages(content, pages_count)
    else:
        return [content]


def _split_by_words(text: str, words_per_page: int) -> list[str]:
    """Split text into chunks of approximately *words_per_page* Chinese characters."""
    if not text or words_per_page <= 0:
        return [text]

    # Count chars (Chinese + English words)
    pages = []
    remaining = text
    while remaining:
        # Find a good break point near words_per_page characters
        chunk = remaining[:words_per_page]
        if len(remaining) <= words_per_page:
            pages.append(remaining)
            break

        # Try to break at paragraph boundary
        rest = remaining[words_per_page:]
        para_break = rest.find("\n\n")
        if para_break != -1 and para_break < 500:
            chunk = remaining[: words_per_page + para_break]
            remaining = remaining[words_per_page + para_break + 2:]
        else:
            # Try to break at sentence end
            for sep in ("。", "！", "？", "」", "\n"):
                last = chunk.rfind(sep)
                if last > words_per_page * 0.6:
                    chunk = chunk[: last + 1]
                    remaining = remaining[last + 1:]
                    break
            else:
                remaining = remaining[words_per_page:]

        pages.append(chunk)

    return pages if pages else [text]


def _split_by_pages(text: str, num_pages: int) -> list[str]:
    """Split text into *num_pages* roughly equal parts."""
    if not text or num_pages <= 1:
        return [text]

    total = len(text)
    page_size = total // num_pages
    pages = []
    pos = 0

    for i in range(num_pages):
        if i == num_pages - 1:
            pages.append(text[pos:])
        else:
            end = pos + page_size
            # Find break point near the target position
            chunk = text[pos:end]
            for sep in ("。", "！", "？", "\n\n", "\n"):
                last = chunk.rfind(sep)
                if last > page_size * 0.6:
                    end = pos + last + 1
                    break
            pages.append(text[pos:end])
            pos = end

    return [p for p in pages if p.strip()]


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def site_home(
    request: Request,
    page: int = 1,
    category: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    size = 24
    site = await _get_site(request, db)
    tpl = _get_templates(site.template if site else "default")

    # Check page cache BEFORE any DB queries
    cached = await _check_page_cache("home", site, request.url.path, str(request.query_params))
    if cached:
        return HTMLResponse(cached)

    site_offset = site.offset if site else 0

    query = select(Novel).options(selectinload(Novel.categories))

    if category:
        query = query.where(Novel.categories.any(Category.id == category))

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Apply site offset for content differentiation
    query = query.order_by(Novel.updated_at.desc()).offset(site_offset + (page - 1) * size).limit(size)
    novels = (await db.execute(query)).unique().scalars().all()

    cats = await _get_categories(db)

    # Category novels — single query + Python grouping (replaces N queries)
    from app.models.novel import novel_categories
    from collections import defaultdict
    category_novels: dict[str, list] = {}
    if len(cats) <= 9 and cats:
        cat_ids = [c.id for c in cats]
        all_cat_result = await db.execute(
            select(Novel)
            .options(selectinload(Novel.categories))
            .join(novel_categories, Novel.id == novel_categories.c.novel_id)
            .where(novel_categories.c.category_id.in_(cat_ids))
            .order_by(Novel.updated_at.desc())
        )
        all_cat_novels = all_cat_result.unique().scalars().all()
        cat_novels_map: dict[str, list] = defaultdict(list)
        for novel in all_cat_novels:
            for cat in novel.categories:
                cid = str(cat.id)
                if cat.id in cat_ids and len(cat_novels_map[cid]) < 5:
                    cat_novels_map[cid].append(novel)
        category_novels = dict(cat_novels_map)

    # Ranking (top 15) — single query, also used for featured
    ranking = (await db.execute(
        select(Novel).options(selectinload(Novel.categories)).order_by(Novel.total_chapters.desc()).limit(15)
    )).unique().scalars().all()
    featured = ranking[:5]  # Featured = top 5 of ranking

    # Latest 25 with latest chapter info (batch query, not N+1)
    latest_rows = (await db.execute(
        select(Novel).order_by(Novel.updated_at.desc()).limit(25)
    )).unique().scalars().all()
    novel_ids = [n.id for n in latest_rows]
    # Batch fetch latest chapter for all 25 novels in ONE query
    from sqlalchemy import and_
    if novel_ids:
        lc_subq = (
            select(
                Chapter.novel_id,
                Chapter.id,
                Chapter.title,
                func.row_number().over(
                    partition_by=Chapter.novel_id,
                    order_by=Chapter.sort_order.desc()
                ).label("rn"),
            )
            .where(Chapter.novel_id.in_(novel_ids))
            .subquery()
        )
        lc_rows = (await db.execute(
            select(lc_subq.c.novel_id, lc_subq.c.id, lc_subq.c.title)
            .where(lc_subq.c.rn == 1)
        )).all()
        lc_map = {row[0]: (str(row[1]), row[2]) for row in lc_rows}
    else:
        lc_map = {}
    latest = []
    for n in latest_rows:
        if n.id in lc_map:
            n.latest_chapter_id, n.latest_title = lc_map[n.id]
        latest.append(n)

    # ---- Link wheel links ----
    link_wheel_links = await _safe_link_wheel(site, db, None, "home")

    context = {
        **_site_context(site),
        "request": request,
        "site": site,
        "novels": novels,
        "categories": cats,
        "category_novels": category_novels,
        "featured": featured,
        "latest_novels": latest,
        "ranking": ranking,
        "breadcrumb_links": [],
        "friend_links": [],
        "page": page,
        "pages": max(1, math.ceil(total / size)),
        "now": _now(),
        "canonical_url": str(request.url).split("?")[0],
        "link_wheel_links": link_wheel_links,
        "modules": _build_modules(site, "home",
            "hero_carousel", "category_sections", "latest_updates",
            "hot_ranking", "friend_links", "link_wheel"),
    }
    return await _render_page(
        "home", tpl, "pages/home.html", context, site,
        request.url.path, str(request.query_params),
    )


# ---------------------------------------------------------------------------
# Novel detail
# ---------------------------------------------------------------------------

@router.get("/novel/{novel_id}", response_class=HTMLResponse)
async def site_novel(
    request: Request,
    novel_id: str,
    db: AsyncSession = Depends(get_db),
):
    site = await _get_site(request, db)
    tpl = _get_templates(site.template if site else "default")

    cached = await _check_page_cache("novel_detail", site, request.url.path, str(request.query_params))
    if cached:
        return HTMLResponse(cached)

    result = await db.execute(
        select(Novel)
        .options(selectinload(Novel.categories))
        .where(Novel.id == novel_id)
    )
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404)

    # Fetch recent chapters
    chapters = (await db.execute(
        select(Chapter)
        .where(Chapter.novel_id == novel_id)
        .order_by(Chapter.sort_order.desc()).limit(15)
    )).scalars().all()

    cats = await _get_categories(db)
    lang = site.language if site and site.language else "zh"
    await _tr_content(db, novel, None, cats, lang)

    # ---- Link wheel links ----
    link_wheel_links = await _safe_link_wheel(site, db, novel.id, "novel_detail")

    context = {
        **_site_context(site),
        "request": request,
        "site": site,
        "novel": novel,
        "chapters": list(chapters),
        "categories": cats,
        "now": _now(),
        "link_wheel_links": link_wheel_links,
        "modules": _build_modules(site, "novel_detail", "friend_links", "link_wheel"),
    }
    return await _render_page(
        "novel_detail", tpl, "pages/novel.html", context, site,
        request.url.path, str(request.query_params),
    )


# ---------------------------------------------------------------------------
# Chapter list
# ---------------------------------------------------------------------------

@router.get("/novel/{novel_id}/chapters", response_class=HTMLResponse)
async def site_chapter_list(
    request: Request,
    novel_id: str,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    site = await _get_site(request, db)
    tpl = _get_templates(site.template if site else "default")

    cached = await _check_page_cache("chapter_list", site, request.url.path, str(request.query_params))
    if cached:
        return HTMLResponse(cached)

    novel = (await db.execute(
        select(Novel).where(Novel.id == novel_id)
    )).scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404)

    # Fetch all chapters
    all_chapters = (await db.execute(
        select(Chapter)
        .where(Chapter.novel_id == novel_id)
        .order_by(Chapter.sort_order)
    )).scalars().all()

    # Group by actual volume field from DB
    grouped: list[dict] = []
    if all_chapters:
        current_vol = {"title": "正文", "chapters": []}
        for ch in all_chapters:
            vol = (ch.volume or "").strip()
            if vol and current_vol["title"] != vol:
                if current_vol["chapters"]:
                    grouped.append(current_vol)
                current_vol = {"title": vol, "chapters": []}
            current_vol["chapters"].append(ch)
        grouped.append(current_vol)

    cats = await _get_categories(db)

    # ---- Link wheel links ----
    link_wheel_links = await _safe_link_wheel(site, db, novel.id, "chapter_list")

    context = {
        **_site_context(site),
        "request": request,
        "site": site,
        "novel": novel,
        "grouped": grouped if len(grouped) > 1 else [],
        "all_chapters": all_chapters,
        "total": len(all_chapters),
        "categories": cats,
        "now": _now(),
        "link_wheel_links": link_wheel_links,
        "modules": _build_modules(site, "chapter_list", "link_wheel"),
    }
    return await _render_page(
        "chapter_list", tpl, "pages/chapter_list.html", context, site,
        request.url.path, str(request.query_params),
    )


# ---------------------------------------------------------------------------
# Chapter reader
# ---------------------------------------------------------------------------

@router.get("/chapter/{chapter_id}", response_class=HTMLResponse)
async def site_chapter(
    request: Request,
    chapter_id: str,
    db: AsyncSession = Depends(get_db),
):
    site = await _get_site(request, db)
    tpl = _get_templates(site.template if site else "default")

    cached = await _check_page_cache("chapter_read", site, request.url.path, str(request.query_params))
    if cached:
        return HTMLResponse(cached)

    chapter = (await db.execute(
        select(Chapter).where(Chapter.id == chapter_id)
    )).scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404)

    novel = (await db.execute(
        select(Novel).where(Novel.id == chapter.novel_id)
    )).scalar_one_or_none()

    # Prev / Next
    prev_ch = (await db.execute(
        select(Chapter)
        .where(Chapter.novel_id == chapter.novel_id, Chapter.sort_order < chapter.sort_order)
        .order_by(Chapter.sort_order.desc()).limit(1)
    )).scalar_one_or_none()

    next_ch = (await db.execute(
        select(Chapter)
        .where(Chapter.novel_id == chapter.novel_id, Chapter.sort_order > chapter.sort_order)
        .order_by(Chapter.sort_order).limit(1)
    )).scalar_one_or_none()

    # Translate content for non-Chinese sites
    lang_ch = site.language if site and site.language else "zh"
    await _tr_content(db, novel, chapter, None, lang_ch)

    # Read content from file store (or DB fallback)
    chapter_content = await get_chapter_content(chapter)

    # ---- Chapter pagination ----
    all_pages = _paginate_chapter(chapter_content, site)
    page_param = site.chapter_pagination.get("page_param", "page") if site and site.chapter_pagination else "page"
    current_page = int(request.query_params.get(page_param, 1))
    total_pages = len(all_pages)
    if current_page < 1:
        current_page = 1
    if current_page > total_pages:
        current_page = total_pages

    page_content = all_pages[current_page - 1]
    chapter.content = page_content  # inject current page for template

    # ---- Link wheel links ----
    link_wheel_links = await _safe_link_wheel(site, db, novel.id, "chapter_read")

    # ---- Random 5 book recommendations (exclude current novel, only with covers) ----
    rand_novels = []
    if novel:
        rand_result = await db.execute(
            select(Novel)
            .options(selectinload(Novel.categories))
            .where(
                Novel.id != novel.id,
                Novel.cover_image_url.isnot(None),
                Novel.cover_image_url != "",
            )
            .order_by(func.rand())
            .limit(5)
        )
        rand_novels = rand_result.unique().scalars().all()
        # Attach latest chapter (batch query, not N+1)
        rn_ids = [rn.id for rn in rand_novels]
        if rn_ids:
            lc_rn_subq = (
                select(
                    Chapter.novel_id, Chapter.id, Chapter.title,
                    func.row_number().over(
                        partition_by=Chapter.novel_id, order_by=Chapter.sort_order.desc()
                    ).label("rn"),
                )
                .where(Chapter.novel_id.in_(rn_ids))
                .subquery()
            )
            lc_rn_rows = (await db.execute(
                select(lc_rn_subq.c.novel_id, lc_rn_subq.c.id, lc_rn_subq.c.title)
                .where(lc_rn_subq.c.rn == 1)
            )).all()
            lc_rn_map = {row[0]: (str(row[1]), row[2]) for row in lc_rn_rows}
            for rn in rand_novels:
                if rn.id in lc_rn_map:
                    rn.latest_chapter_id, rn.latest_title = lc_rn_map[rn.id]

    # ---- Pseudo-static page URLs ----
    page_urls = {}
    if total_pages > 1:
        for p in range(1, total_pages + 1):
            base = _build_url(site, "chapter_read", id=chapter_id)
            if p == 1 and site and site.chapter_pagination and site.chapter_pagination.get("canonical_first_page", True):
                page_urls[p] = base
            else:
                page_urls[p] = f"{base}?{page_param}={p}"

    cats = await _get_categories(db)
    context = {
        **_site_context(site),
        "request": request,
        "site": site,
        "novel": novel,
        "chapter": chapter,
        "categories": cats,
        "prev_id": str(prev_ch.id) if prev_ch else "",
        "prev_title": prev_ch.title if prev_ch else "",
        "next_id": str(next_ch.id) if next_ch else "",
        "next_title": next_ch.title if next_ch else "",
        "now": _now(),
        "total_pages": total_pages,
        "current_page": current_page,
        "page_param": page_param,
        "page_urls": page_urls,
        "has_pagination": total_pages > 1,
        "link_wheel_links": link_wheel_links,
        "rand_novels": rand_novels,
        "modules": _build_modules(site, "chapter_read",
            "random_recommend", "reader_toolbar", "link_wheel"),
    }
    return await _render_page(
        "chapter_read", tpl, "pages/chapter.html", context, site,
        request.url.path, str(request.query_params),
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.get("/search", response_class=HTMLResponse)
async def site_search(
    request: Request,
    q: str = "",
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    site = await _get_site(request, db)
    tpl = _get_templates(site.template if site else "default")

    cached = await _check_page_cache("search", site, request.url.path, str(request.query_params))
    if cached:
        return HTMLResponse(cached)

    results = []
    total = 0
    if q:
        size = 20
        query = select(Novel).options(selectinload(Novel.categories)).where(
            Novel.title.ilike(f"%{q}%") | Novel.author.ilike(f"%{q}%")
        )
        count_q = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_q)).scalar() or 0
        query = query.order_by(Novel.updated_at.desc()).offset((page - 1) * size).limit(size)
        results = (await db.execute(query)).unique().scalars().all()

    cats = await _get_categories(db)

    # ---- Link wheel links ----
    link_wheel_links = await _safe_link_wheel(site, db, None, "home")

    context = {
        **_site_context(site),
        "request": request,
        "site": site,
        "query": q,
        "results": results,
        "categories": cats,
        "page": page,
        "pages": max(1, math.ceil(total / 20)) if total else 0,
        "total": total,
        "now": _now(),
        "link_wheel_links": link_wheel_links,
        "modules": _build_modules(site, "search", "link_wheel"),
    }
    return await _render_page(
        "search", tpl, "pages/search.html", context, site,
        request.url.path, str(request.query_params),
    )


# ---------------------------------------------------------------------------
# Book library page
# ---------------------------------------------------------------------------

@router.get("/novels", response_class=HTMLResponse)
async def site_novels(
    request: Request,
    page: int = 1,
    category: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    site = await _get_site(request, db)
    tpl = _get_templates(site.template if site else "default")

    cached = await _check_page_cache("book_library", site, request.url.path, str(request.query_params))
    if cached:
        return HTMLResponse(cached)

    size = 30
    query = select(Novel).options(selectinload(Novel.categories))

    if category:
        query = query.where(Novel.categories.any(Category.id == category))
    if status:
        query = query.where(Novel.status == status)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(Novel.updated_at.desc()).offset((page - 1) * size).limit(size)
    novels = (await db.execute(query)).unique().scalars().all()
    cats = await _get_categories(db)
    lang = site.language if site and site.language else "zh"
    await _tr_content(db, None, None, cats, lang)

    # ---- Link wheel links ----
    link_wheel_links = await _safe_link_wheel(site, db, None, "home")

    context = {
        **_site_context(site),
        "request": request,
        "site": site,
        "novels": novels,
        "categories": cats,
        "category_novels": {},
        "featured": novels[:5] if novels else [],
        "latest_novels": novels[:25] if novels else [],
        "ranking": novels[:15] if novels else [],
        "breadcrumb_links": [],
        "friend_links": [],
        "page": page,
        "pages": max(1, math.ceil(total / size)),
        "now": _now(),
        "canonical_url": str(request.url).split("?")[0],
        "link_wheel_links": link_wheel_links,
        "modules": _build_modules(site, "book_library",
            "hero_carousel", "category_sections", "latest_updates",
            "hot_ranking", "friend_links", "link_wheel"),
    }
    return await _render_page(
        "book_library", tpl, "pages/home.html", context, site,
        request.url.path, str(request.query_params),
    )
