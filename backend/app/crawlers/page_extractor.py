"""
Extract novel links from any source-site page.

Supports:
    - Category listing pages (e.g. /book/lastupdate_0_6_0_0_0_0_0_1_0.html)
    - Search result pages
    - Any page containing links matching the site's novel URL pattern.

Uses rule-engine selectors when available, falls back to generic extraction.
"""

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import asyncio

from bs4 import BeautifulSoup

from app.crawlers.anti_detect import smart_fetch
from app.crawlers.rule_engine import load_rule


# ---------------------------------------------------------------------------
# Generic link extraction (no rule needed)
# ---------------------------------------------------------------------------

def _extract_generic(
    html: str,
    base_url: str,
    novel_url_pattern: str = r"/book/(\d+)",
) -> list[dict]:
    """Extract novel links from any HTML page using a URL pattern.

    Looks for all ``<a href>`` that match *novel_url_pattern* and
    deduplicates by URL.
    """
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    results: list[dict] = []

    for a_tag in soup.select(f"a[href*='/book/']"):
        href = a_tag.get("href", "").strip()
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue

        full_url = urljoin(base_url, href)
        if full_url in seen:
            continue
        seen.add(full_url)

        # Extract book_id
        m = re.search(novel_url_pattern, href)
        book_id = m.group(1) if m else ""

        # Try to get title from the link text, title attr, or nearby elements
        title = (
            a_tag.get("title", "")
            or a_tag.get_text(strip=True)
            or ""
        )

        # Skip links that look like category/tag navigation
        if not book_id:
            # Try catalog-style URLs
            m2 = re.search(r"/book/(\d+)/", full_url)
            if m2:
                book_id = m2.group(1)

        if not book_id or len(book_id) > 10:
            continue

        # Skip category/list pages (they have more path segments)
        if re.search(r"/book/lastupdate|/tag/|/author/|/login|/search|/catalog$|\.html$", href) and not href.endswith(".html"):
            # Allow .html chapter URLs
            pass

        # Heuristic: skip links with very short text (usually images)
        if not title and not a_tag.find("img"):
            parent_text = a_tag.parent.get_text(strip=True) if a_tag.parent else ""
            title = parent_text[:80] if parent_text else ""

        # Try to find cover image near the link
        cover_url = ""
        parent = a_tag.parent
        for _ in range(3):
            if parent is None:
                break
            img = parent.select_one("img")
            if img:
                src = img.get("data-src") or img.get("src") or ""
                if src and not src.endswith("loading.gif"):
                    cover_url = urljoin(base_url, src)
                break
            parent = parent.parent

        results.append({
            "title": title[:120] if title else f"Book-{book_id}",
            "url": full_url,
            "book_id": book_id,
            "cover_url": cover_url,
            "is_chapter": bool(re.search(r"/\d+\.html$", full_url)),
        })

    return results


# ---------------------------------------------------------------------------
# Rule-based extraction
# ---------------------------------------------------------------------------

def _extract_with_rule(
    html: str,
    base_url: str,
    rule: dict,
) -> list[dict]:
    """Use a rule's catalog/search selectors to extract novel links."""
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []

    # Try catalog selectors first
    catalog_rule = rule.get("selectors", {}).get("catalog", {})
    container = catalog_rule.get("container", "")
    fields = catalog_rule.get("fields", {})

    if container:
        items = soup.select(container)
        for item in items:
            url_el = item.select_one(fields.get("url", {}).get("selector", "a"))
            title_el = item.select_one(fields.get("title", {}).get("selector", ".module-row-title span"))

            href = url_el.get("href", "") if url_el else ""
            title = (
                url_el.get("title", "")
                or (title_el.get_text(strip=True) if title_el else "")
                or url_el.get_text(strip=True) if url_el else ""
            )

            if href:
                full_url = urljoin(base_url, href)
                book_id_match = re.search(r"/book/(\d+)", full_url)
                book_id = book_id_match.group(1) if book_id_match else ""
                results.append({
                    "title": title[:120] or f"Chapter-{book_id}",
                    "url": full_url,
                    "book_id": book_id,
                    "is_chapter": True,
                })

    # Also try search selectors
    search_rule = rule.get("selectors", {}).get("search", {})
    s_container = search_rule.get("container", "")
    s_fields = search_rule.get("fields", {})

    if s_container and not results:
        items = soup.select(s_container)
        for item in items:
            url_sel = s_fields.get("url", {}).get("selector", "a")
            title_sel = s_fields.get("title", {}).get("selector", "a")

            url_el = item.select_one(url_sel) if url_sel else None
            title_el = item.select_one(title_sel) if title_sel else None

            href = url_el.get("href", "") if url_el else ""
            title = (
                url_el.get("title", "")
                or (title_el.get_text(strip=True) if title_el else "")
            )
            if href:
                full_url = urljoin(base_url, href)
                book_id_match = re.search(r"/book/(\d+)", full_url)
                book_id = book_id_match.group(1) if book_id_match else ""
                results.append({
                    "title": title[:120] or f"Novel-{book_id}",
                    "url": full_url,
                    "book_id": book_id,
                    "is_chapter": False,
                })

    return results


# ---------------------------------------------------------------------------
# URL pagination helper
# ---------------------------------------------------------------------------

def _detect_page_param(url: str) -> tuple[str, int, int]:
    """Detect the page-number position in a 23qb-style URL.

    23qb URLs look like:
        .../postdate_0_0_0_0_0_0_0_{page}_0.html

    Returns ``(template, position, current_page)`` where *template* is
    the URL with ``{page}`` in place of the page number.
    """
    import re
    parts = url.rsplit("/", 1)
    base = parts[0] + "/" if len(parts) > 1 else ""
    filename = parts[-1] if len(parts) > 1 else url
    # Split on underscore and find the numeric position that looks like a page
    segments = filename.replace(".html", "").split("_")
    # Last numeric segment before the trailing "_0" is usually the page
    best_pos = -2  # default: second-last
    best_val = 1
    for i in range(len(segments) - 1, -1, -1):
        if segments[i].isdigit() and int(segments[i]) > 0:
            best_pos = i
            best_val = int(segments[i])
            break
    template_segs = list(segments)
    template_segs[best_pos] = "{page}"
    template = base + "_".join(template_segs) + ".html"
    return template, best_pos, best_val


def _url_for_page(template: str, page: int) -> str:
    """Fill ``{page}`` placeholder in *template*."""
    return template.replace("{page}", str(page))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def extract_page_links(
    page_url: str,
    source_name: Optional[str] = None,
    pattern: str = r"/book/(\d+)",
    page_from: int = 1,
    page_to: int = 1,
) -> dict:
    """Fetch *page_url* and extract all novel/chapter links.

    Returns:
        {"page_url": ..., "total": ..., "novels": [...], "chapters": [...]}
    """
    # Detect page template
    template, _, current_page = _detect_page_param(page_url)
    if page_to < page_from:
        page_to = page_from

    base_url = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    rule = load_rule(source_name) if source_name else None

    all_items: list[dict] = []
    pages_fetched = 0

    for pg in range(page_from, page_to + 1):
        url = _url_for_page(template, pg)
        try:
            html = await smart_fetch(url)
            pages_fetched += 1
        except Exception:
            continue  # skip failed pages

        if rule:
            items = _extract_with_rule(html, base_url, rule)
            if not items:
                items = _extract_generic(html, base_url, pattern)
        else:
            items = _extract_generic(html, base_url, pattern)

        all_items.extend(items)

        # Early exit: if a page returns no items, stop pagination
        if not items and pg > page_from:
            break

    # Separate novels vs chapters + deduplicate
    novels: list[dict] = []
    chapters: list[dict] = []
    seen_novel: set[str] = set()

    for item in all_items:
        if item.get("is_chapter"):
            chapters.append(item)
        else:
            bid = item.get("book_id", "")
            if bid and bid not in seen_novel:
                seen_novel.add(bid)
                novels.append(item)

    return {
        "page_url": page_url,
        "page_from": page_from,
        "page_to": page_to,
        "pages_fetched": pages_fetched,
        "total": len(all_items),
        "novel_count": len(novels),
        "chapter_count": len(chapters),
        "novels": novels,
        "chapters": chapters[:50],
    }


# ---------------------------------------------------------------------------
# Per-novel catalog + chapter content test
# ---------------------------------------------------------------------------

async def test_novel_extraction(
    novel_url: str,
    source_name: str,
) -> dict:
    """Quick-test whether a novel's catalog and chapters can be extracted.

    Returns:
        { "passed": bool, "catalog_ok": bool, "chapter_ok": bool,
          "chapter_count": int, "chapter_title": str, "content_len": int,
          "error": str }
    """
    result = {"passed": False, "catalog_ok": False, "chapter_ok": False,
              "chapter_count": 0, "chapter_title": "", "content_len": 0, "error": ""}

    rule = load_rule(source_name)
    base_url = rule.get("base_url", "") if rule else ""

    try:
        # 1. Test catalog extraction
        book_id = re.search(r"/book/(\d+)", novel_url)
        if not book_id:
            result["error"] = "无法提取 book_id"
            return result
        bid = book_id.group(1)

        catalog_url = f"{base_url}/book/{bid}/catalog"
        html = await smart_fetch(catalog_url)
        soup = BeautifulSoup(html, "lxml")

        chapter_items = soup.select(".module-row-info a.module-row-text")
        if not chapter_items:
            result["error"] = "目录提取失败：未找到章节链接"
            return result

        result["catalog_ok"] = True
        result["chapter_count"] = len(chapter_items)

        # 2. Test chapter content extraction (fetch first chapter)
        first = chapter_items[0]
        href = first.get("href", "")
        if not href:
            result["error"] = "目录提取成功，但章节链接为空"
            return result

        chapter_url = urljoin(base_url, href)
        title = first.get("title", "") or first.get_text(strip=True)

        ch_html = await smart_fetch(chapter_url)
        ch_soup = BeautifulSoup(ch_html, "lxml")

        content_div = (
            ch_soup.select_one(".view-heading .article-content")
            or ch_soup.select_one("div.article-content")
        )
        if content_div:
            for junk in content_div.select("script, ins, .adsbygoogle"):
                junk.decompose()
            content = content_div.get_text(strip=True)
        else:
            content = ""

        if len(content) < 50:
            result["error"] = f"章节内容提取失败：仅 {len(content)} 字符"
            return result

        result["chapter_ok"] = True
        result["chapter_title"] = title
        result["content_len"] = len(content)
        result["passed"] = True

    except Exception as exc:
        result["error"] = str(exc)[:200]

    return result


async def test_all_novels(
    novels: list[dict],
    source_name: str,
    concurrency: int = 3,
) -> list[dict]:
    """Test catalog + chapter extraction for all novels concurrently.

    Each novel dict gets ``_test`` field with test results.
    Only novels that pass both catalog AND chapter tests are marked ``_test.passed=True``.
    """
    sem = asyncio.Semaphore(concurrency)

    async def test_one(n: dict):
        async with sem:
            n["_test"] = await test_novel_extraction(n["url"], source_name)
            n["_testing"] = False

    # Run all tests concurrently
    for n in novels:
        n["_testing"] = True
        n["_test"] = None
    await asyncio.gather(*[test_one(n) for n in novels])

    return novels
