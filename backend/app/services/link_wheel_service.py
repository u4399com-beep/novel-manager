"""Link wheel (链轮) service — resolve and render inter-site/book links."""
import random
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.link_ring import LinkRing, LinkRingTarget
from app.models.novel import Novel
from app.models.site import Site


async def get_active_rings(
    db: AsyncSession,
    site_id: Optional[str] = None,
) -> list[LinkRing]:
    """Get all active link rings for a site (or global ones)."""
    from sqlalchemy import or_
    q = select(LinkRing).where(
        LinkRing.is_active == True,
        or_(
            LinkRing.site_id == site_id,
            LinkRing.site_id == None,
            LinkRing.site_id == "",  # empty string = global
        ),
    )
    result = await db.execute(q)
    return list(result.scalars().all())


async def resolve_links_for_page(
    db: AsyncSession,
    site_id: str,
    novel_id: Optional[str] = None,
    page_type: str = "novel_detail",
    max_total: int = 8,
) -> list[dict]:
    """Resolve which links to show on a given page.

    Args:
        site_id: current site
        novel_id: current novel (if on novel/chapter page)
        page_type: "home" | "novel_detail" | "chapter_read"
        max_total: max links across all rings

    Returns list of {anchor_text, url, open_new_tab, nofollow, ring_name}
    """
    rings = await get_active_rings(db, site_id)
    links: list[dict] = []

    for ring in rings:
        if len(links) >= max_total:
            break

        # Check if this ring applies to this page type
        rules = ring.selection_rules or {}
        on_pages = rules.get("on_pages", ["novel_detail", "chapter_read"])
        if page_type not in on_pages:
            continue

        # Get targets for this ring
        targets = [t for t in ring.targets if t.is_active]

        if not targets:
            # Auto-generate targets from selection rules
            targets = await _auto_generate_targets(db, ring, site_id, novel_id)

        # Filter by source (where the link appears)
        applicable = []
        for t in targets:
            if t.source_site_id and t.source_site_id != site_id:
                continue
            if t.source_novel_id and novel_id and t.source_novel_id != novel_id:
                continue
            applicable.append(t)

        # Pick up to ring.max_links
        selected = applicable[: ring.max_links]

        for t in selected:
            url = await _build_target_url(db, t, ring)
            if not url:
                continue
            # Resolve anchor text placeholders with actual book data
            anchor = await _resolve_anchor(db, t, ring)
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


async def _auto_generate_targets(
    db: AsyncSession, ring: LinkRing, site_id: str, novel_id: Optional[str]
) -> list[LinkRingTarget]:
    """Auto-generate link targets from selection rules."""
    rules = ring.selection_rules or {}
    target_rules = rules.get("target", {})
    source_rules = rules.get("source", {})

    match_by = target_rules.get("match_by", "random")
    target_site_ids = target_rules.get("site_ids", [])
    target_novel_ids = target_rules.get("novel_ids", [])
    target_cat_ids = target_rules.get("category_ids", [])
    exclude_ids = target_rules.get("exclude_novel_ids", [])

    # Build query
    q = select(Novel)
    if target_novel_ids:
        q = q.where(Novel.id.in_(target_novel_ids))
    elif target_cat_ids:
        from app.models.novel import novel_categories
        q = q.where(Novel.categories.any(id=target_cat_ids[0]))  # simplified
    elif match_by == "random":
        q = q.order_by(func.rand()).limit(ring.max_links)
    else:
        q = q.limit(ring.max_links)

    if exclude_ids:
        q = q.where(Novel.id.notin_(exclude_ids))

    result = await db.execute(q)
    novels = result.scalars().all()

    targets = []
    for i, n in enumerate(novels):
        t = LinkRingTarget(
            ring_id=ring.id,
            source_site_id=site_id,
            target_novel_id=n.id,
            target_site_id=target_site_ids[0] if target_site_ids else site_id,
            anchor_text="{title}",
            sort_order=i,
        )
        targets.append(t)
    return targets


async def _build_target_url(
    db: AsyncSession, target: LinkRingTarget, ring: LinkRing
) -> str:
    """Build the actual URL for a link target."""
    if target.target_url:
        return target.target_url

    if target.target_novel_id:
        # Determine which site's domain to use
        target_site = None
        if target.target_site_id:
            target_site = await db.get(Site, target.target_site_id)
        if target_site and target_site.domain:
            base = f"http://{target_site.domain}"
        else:
            base = ""

        # Build URL using site's URL patterns
        if target_site and target_site.url_patterns:
            pattern = target_site.url_patterns.get("novel_detail", "/novel/{id}/")
        else:
            pattern = "/novel/{id}/"
        return f"{base}{pattern.replace('{id}', target.target_novel_id)}"

    return ""


async def _resolve_anchor(db: AsyncSession, target: LinkRingTarget, ring: LinkRing) -> str:
    """Resolve anchor text template with actual book/site names."""
    text = target.anchor_text or ring.link_format or "{title}"

    # Fetch target novel for title/author
    if target.target_novel_id:
        novel = await db.get(Novel, target.target_novel_id)
        if novel:
            text = text.replace("{title}", novel.title)
            text = text.replace("{author}", novel.author or "")
        else:
            text = text.replace("{title}", "未知书名").replace("{author}", "")

    # Fetch target site for site_name
    if target.target_site_id:
        site = await db.get(Site, target.target_site_id)
        if site:
            text = text.replace("{site_name}", site.name)
    elif "{site_name}" in text:
        text = text.replace("{site_name}", "")

    # Clean up: remove leftover placeholders
    import re
    text = re.sub(r"\{[^}]+\}", "", text).strip()
    # Clean up separators that are now orphaned
    text = re.sub(r"\s*[-–—|·]\s*$", "", text).strip()
    text = re.sub(r"^\s*[-–—|·]\s*", "", text).strip()

    return text or ring.name


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

    # Create targets if provided
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
