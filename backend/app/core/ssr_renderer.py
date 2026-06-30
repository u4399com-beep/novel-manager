"""SSR page renderer — caching, translation, and Jinja2 template helpers."""

import asyncio
import hashlib
import re
from typing import Optional

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

# Precompiled regex
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def nl2br(text) -> str:
    """Convert <br> tags to newlines, strip all other HTML."""
    if not text: return ""
    text = _BR_RE.sub("\n", str(text))
    return _TAG_RE.sub("", text)


def striptags(text) -> str:
    """Strip ALL HTML tags, return plain text."""
    if not text: return ""
    return _TAG_RE.sub("", str(text))


# ── Page cache (in-memory LRU) ────────────────────────────────────

async def check_cache(page_type: str, site, path: str, query: str) -> Optional[str]:
    """Check in-memory page cache before DB queries."""
    from app.services.page_cache import page_cache
    lang = site.language if site else "zh"
    return await page_cache.get(page_type, path, query, lang)


async def render_and_cache(
    page_type: str, tpl: Jinja2Templates, template_name: str,
    context: dict, site, path: str, query: str,
) -> HTMLResponse:
    """Render Jinja2 template via thread pool + cache in memory."""
    from app.services.page_cache import page_cache
    lang = site.language if site else "zh"
    html = await asyncio.to_thread(tpl.env.get_template(template_name).render, context)
    await page_cache.set(page_type, path, query, lang, html)
    return HTMLResponse(html)


# ── Template loader ───────────────────────────────────────────────

_tpl_cache: dict[str, Jinja2Templates] = {}


def get_templates(site_template: str = "default", templates_base: str = "") -> Jinja2Templates:
    """Return Jinja2Templates for a site, with caching."""
    site_template = site_template or "default"
    if site_template not in _tpl_cache:
        paths = [f"{templates_base}/{site_template}", templates_base]
        existing = [p for p in paths if __import__("os").path.isdir(p)]
        env = Environment(loader=FileSystemLoader(existing), autoescape=True)
        _tpl_cache[site_template] = Jinja2Templates(env=env)
    return _tpl_cache[site_template]


# ── Jinja2 filter registration ────────────────────────────────────

def register_filters(env: Environment):
    """Register all custom Jinja2 filters."""
    env.filters["nl2br"] = nl2br
    env.filters["striptags"] = striptags
