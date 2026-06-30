"""Link wheel (链轮) service — configured rules only, fallback to hot ranking."""

import re
from typing import Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.link_ring import LinkRing, LinkRingTarget
from app.models.novel import Novel
from app.models.site import Site

_PLACEHOLDER_RE = re.compile(r"\{[^}]+\}")
_CLEANUP_RE = re.compile(r"\s*[-–—|·]\s*$")


async def get_active_rings(
    db: AsyncSession, site_id: Optional[str] = None,
) -> list[LinkRing]:
    """Get all active link rings for a site (or global ones)."""
    q = select(LinkRing).where(
        LinkRing.is_active == True,
        or_(
            LinkRing.site_id == site_id,
            LinkRing.site_id == None,
            LinkRing.site_id == "",
        ),
    )
    result = await db.execute(q)
    return list(result.scalars().all())


async def _get_hot_ranking_novels(db: AsyncSession, count: int) -> list[dict]:
    """Get hot ranking novels as fallback links (when no link rings configured)."""
    result = await db.execute(
        select(Novel)
        .options(selectinload(Novel.categories))
        .order_by(Novel.total_chapters.desc())
        .limit(count)
    )
    from sqlalchemy.orm import selectinload
    novels = result.unique().scalars().all()
    return [
        {
            "anchor_text": n.title,
            "url": f"/novel/{n.id}",
            "open_new_tab": False,
            "nofollow": False,
            "ring_name": "热门推荐",
            "display_mode": "sidebar",
        }
        for n in novels
    ]


async def resolve_links_for_page(
    db: AsyncSession,
    site_id: str,
    novel_id: Optional[str] = None,
    page_type: str = "novel_detail",
    max_total: int = 8,
) -> list[dict]:
    """Resolve which links to show on a given page.

    Strategy:
    1. If ANY link ring has configured targets → use configured rules only
    2. If no configured targets exist → fallback to hot ranking novels
    """
    rings = await get_active_rings(db, site_id)

    # Check if any ring has actual configured targets
    has_configured = any(
        any(t.is_active for t in ring.targets)
        for ring in rings
    )

    # Strategy 1: No configured targets → hot ranking fallback
    if not has_configured:
        return await _get_hot_ranking_novels(db, max_total)

    # Strategy 2: Configured rules → use them
    links: list[dict] = []

    for ring in rings:
        if len(links) >= max_total:
            break

        rules = ring.selection_rules or {}
        on_pages = rules.get("on_pages", ["novel_detail", "chapter_read"])
        if page_type not in on_pages:
            continue

        targets = [t for t in ring.targets if t.is_active]
        if not targets:
            continue  # skip rings with no targets (not fallback)

        # Filter by source
        applicable = []
        for t in targets:
            if t.source_site_id and t.source_site_id != site_id:
                continue
            if t.source_novel_id and novel_id and t.source_novel_id != novel_id:
                continue
            applicable.append(t)

        selected = applicable[: ring.max_links]

        # Batch-fetch sites and novels to avoid N+1
        site_ids = {t.target_site_id for t in selected if t.target_site_id}
        novel_ids = {t.target_novel_id for t in selected if t.target_novel_id}

        site_map = {}
        if site_ids:
            sites = (await db.execute(
                select(Site).where(Site.id.in_(site_ids))
            )).scalars().all()
            site_map = {s.id: s for s in sites}

        novel_map = {}
        if novel_ids:
            novels = (await db.execute(
                select(Novel).where(Novel.id.in_(novel_ids))
            )).scalars().all()
            novel_map = {n.id: n for n in novels}

        for t in selected:
            url = _build_target_url(t, ring, site_map)
            if not url:
                continue
            anchor = _resolve_anchor(t, ring, novel_map, site_map)
            links.append({
                "anchor_text": anchor,
                "url": url,
                "open_new_tab": ring.open_new_tab,
                "nofollow": ring.nofollow,
                "ring_name": ring.name,
                "display_mode": ring.display_mode,
            })

    # Deduplicate by URL
    seen = set()
    unique = []
    for link in links:
        if link["url"] not in seen:
            seen.add(link["url"])
            unique.append(link)
    return unique[:max_total]


def _build_target_url(
    target: LinkRingTarget, ring: LinkRing,
    site_map: dict,
) -> str:
    """Build the actual URL for a link target (no DB call — uses pre-fetched map)."""
    if target.target_url:
        return target.target_url

    if target.target_novel_id:
        target_site = site_map.get(target.target_site_id) if target.target_site_id else None
        base = f"http://{target_site.domain}" if (target_site and target_site.domain) else ""
        pattern = "/novel/{id}/"
        if target_site and target_site.url_patterns:
            pattern = target_site.url_patterns.get("novel_detail", pattern)
        return f"{base}{pattern.replace('{id}', target.target_novel_id)}"

    return ""


def _resolve_anchor(
    target: LinkRingTarget, ring: LinkRing,
    novel_map: dict, site_map: dict,
) -> str:
    """Resolve anchor text with pre-fetched maps (no DB calls)."""
    text = target.anchor_text or ring.link_format or "{title}"

    if target.target_novel_id:
        novel = novel_map.get(target.target_novel_id)
        if novel:
            text = text.replace("{title}", novel.title)
            text = text.replace("{author}", novel.author or "")
        else:
            text = text.replace("{title}", "未知书名").replace("{author}", "")

    if target.target_site_id:
        site = site_map.get(target.target_site_id)
        if site:
            text = text.replace("{site_name}", site.name)
    elif "{site_name}" in text:
        text = text.replace("{site_name}", "")

    text = _PLACEHOLDER_RE.sub("", text).strip()
    text = _CLEANUP_RE.sub("", text).strip()
    text = re.sub(r"^\s*[-–—|·]\s*", "", text).strip()
    return text or ring.name


# ── CRUD ──────────────────────────────────────────────────────────

async def create_ring(db: AsyncSession, data: dict) -> LinkRing:
    ring = LinkRing(
        name=data["name"],
        ring_type=data.get("ring_type", "cross_site_books"),
        site_id=data.get("site_id"),
        max_links=data.get("max_links", 5),
        display_mode=data.get("display_mode", "sidebar"),
        link_format=data.get("link_format", "{title}"),
        open_new_tab=data.get("open_new_tab", True),
        nofollow=data.get("nofollow", False),
        selection_rules=data.get("selection_rules"),
        is_active=data.get("is_active", True),
    )
    db.add(ring)
    await db.flush()
    await db.refresh(ring)
    for i, t_data in enumerate(data.get("targets", [])):
        target = LinkRingTarget(
            ring_id=ring.id,
            source_site_id=t_data.get("source_site_id"),
            source_novel_id=t_data.get("source_novel_id"),
            target_site_id=t_data.get("target_site_id"),
            target_novel_id=t_data.get("target_novel_id"),
            target_url=t_data.get("target_url"),
            anchor_text=t_data.get("anchor_text", "{title}"),
            sort_order=t_data.get("sort_order", i),
            is_active=t_data.get("is_active", True),
        )
        db.add(target)
    await db.flush()
    return ring


async def update_ring(db: AsyncSession, ring: LinkRing, data: dict) -> LinkRing:
    for k in ("name", "ring_type", "site_id", "max_links", "display_mode",
              "link_format", "open_new_tab", "nofollow", "selection_rules", "is_active"):
        if k in data:
            setattr(ring, k, data[k])
    await db.flush()
    await db.refresh(ring)
    return ring


async def delete_ring(db: AsyncSession, ring: LinkRing) -> None:
    await db.delete(ring)
    await db.flush()
