"""
Crawler for 铅笔小说 (www.23qb.net).

Site structure:
    - Book detail:   /book/{book_id}/
    - Catalog:       /book/{book_id}/catalog
    - Chapter:       /book/{book_id}/{chapter_id}.html
    - Search:        /search.html?searchkey={keyword}
    - Category list: /book/lastupdate_0_{cat_id}_0_0_0_0_0_1_0.html
    - Cover image:   /files/article/image/{sub}/{book_id}/{book_id}s.jpg

Uses meta tags (og:novel:*) extensively for structured data extraction.
"""

import asyncio
import re
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from app.config import settings
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import register_crawler

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# Category mapping: category_id -> (slug, name)
CATEGORY_MAP = {
    1: ("yanqing", "言情"),
    2: ("dushi", "都市"),
    3: ("weimei", "唯美"),
    4: ("chuanyue", "穿越"),
    5: ("qingchun", "青春"),
    6: ("xuanhuan", "玄幻"),
    7: ("wuxia", "武侠"),
    8: ("junshi", "军事"),
    9: ("jingji", "竞技"),
    10: ("kehuan", "科幻"),
    11: ("xuanyi", "悬疑"),
    12: ("tongren", "同人"),
    13: ("zhichang", "职场"),
}

STATUS_MAP = {
    "完结": "completed",
    "连载": "ongoing",
    "连载中": "ongoing",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _meta(soup: BeautifulSoup, prop: str) -> Optional[str]:
    """Extract content from a <meta property="..."> tag."""
    tag = soup.find("meta", attrs={"property": prop})
    if tag and isinstance(tag, Tag):
        return tag.get("content", "").strip() or None
    return None


def _clean_text(text: Optional[str]) -> Optional[str]:
    """Collapse whitespace and strip."""
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).strip() or None


def _extract_book_id(url: str) -> Optional[str]:
    """Extract numeric book_id from a 23qb.net URL.

    Examples:
        /book/3276/          -> 3276
        /book/3276/catalog   -> 3276
        /book/3276/2343187.html -> 3276
    """
    m = re.search(r"/book/(\d+)", url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------

@register_crawler
class TwentyThreeQbCrawler(BaseCrawler):
    """Crawler for 铅笔小说 (www.23qb.net)."""

    source_name = "23qb"
    base_url = "https://www.23qb.net"
    description = "铅笔小说 - 免费网络小说阅读网"

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-init httpx client with persistent cookies."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=settings.CRAWLER_TIMEOUT,
                headers=HEADERS,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Core HTTP
    # ------------------------------------------------------------------

    async def _fetch(self, url: str) -> str:
        """GET *url* and return the response text.

        Respects ``CRAWLER_REQUEST_DELAY`` to avoid hammering the server.
        """
        await asyncio.sleep(settings.CRAWLER_REQUEST_DELAY)
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.text

    def _soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(self, keyword: str) -> list[dict]:
        """Search novels by keyword.

        Returns a list of dicts with keys:
            title, author, url, book_id, cover_url, description

        Search result items use ``.module-search-item`` (different from
        the homepage ``.module-item`` structure).
        """
        search_url = f"{self.base_url}/search.html?searchkey={keyword}"
        html = await self._fetch(search_url)
        soup = self._soup(html)

        results: list[dict] = []

        for item in soup.select(".module-search-item"):
            # All <a> tags inside the item: [cover_link, category_link, title_link, ...]
            links = item.select("a")
            if len(links) < 3:
                continue

            title_link = links[2]  # third <a> is the book title
            href = urljoin(self.base_url, title_link.get("href", ""))
            title = _clean_text(title_link.get_text()) or ""

            # Author is embedded in the full text of the item
            full_text = item.get_text(" ", strip=True)
            # Pattern: "...书名.作者名.其他..." or we fall back to extracting
            author = ""
            parts = full_text.split(".")
            if len(parts) >= 3:
                # parts[0] = category, parts[1] = title, parts[2] = author
                author = parts[2].strip()

            # Description = remaining text after the title link
            desc_parts = full_text.split(title, 1)
            description = desc_parts[1].strip() if len(desc_parts) > 1 else ""
            # Remove author from beginning of description
            if author and description.startswith(author):
                description = description[len(author):].strip(" .")

            results.append({
                "title": title,
                "author": author,
                "url": href,
                "book_id": _extract_book_id(href),
                "cover_url": "",
                "description": _clean_text(description) or "",
            })

        return results

    async def get_novel_info(self, novel_url: str) -> dict:
        """Fetch novel metadata from a book detail page.

        Returns dict with keys:
            title, author, description, cover_url, status,
            category_name, tags, word_count, book_id
        """
        html = await self._fetch(novel_url)
        soup = self._soup(html)

        # --- meta-based extraction (most reliable) ---
        title = (
            _meta(soup, "og:novel:book_name")
            or _meta(soup, "og:title")
            or ""
        )
        author = _meta(soup, "og:novel:author") or ""
        description = (
            _meta(soup, "og:description")
            or _meta(soup, "description")
            or ""
        )
        cover_url = _meta(soup, "og:image") or ""
        raw_status = _meta(soup, "og:novel:status") or "连载"
        status = STATUS_MAP.get(raw_status, "ongoing")
        tags = _meta(soup, "og:novel:tags") or ""

        # --- fallback: DOM-based extraction ---
        if not title:
            h1 = soup.select_one("h1.page-title")
            title = _clean_text(h1.get_text()) if h1 else ""

        if not author:
            author_link = soup.select_one(".novel-info-aux a[title]")
            if author_link:
                author_text = author_link.get("title", "")
                if author_text.startswith("作者："):
                    author = author_text[3:]

        # Category name from the nav link
        category_name = ""
        cat_link = soup.select_one(".novel-info-aux a[title$='小说']")
        if cat_link:
            category_name = cat_link.get("title", "").replace("小说", "")

        # Word count from text like "100.7 万字"
        word_count = 0
        word_span = soup.find("span", class_="tag-link", string=re.compile(r"万字"))
        if word_span:
            wm = re.search(r"([\d.]+)\s*万", word_span.get_text())
            if wm:
                word_count = int(float(wm.group(1)) * 10000)

        # --- description may contain HTML <br> from meta ---
        description = description.replace("<br />", "\n").replace("<br>", "\n")

        return {
            "title": _clean_text(title) or "",
            "author": _clean_text(author) or "",
            "description": _clean_text(description) or "",
            "cover_url": urljoin(self.base_url, cover_url) if cover_url else "",
            "status": status,
            "category_name": category_name,
            "tags": tags.strip(),
            "word_count": word_count,
            "book_id": _extract_book_id(novel_url) or "",
        }

    async def get_chapters(self, novel_url: str) -> list[dict]:
        """Fetch ALL chapters (with content) for a novel.

        Steps:
            1. Fetch the catalog page to get the chapter list.
            2. Fetch each chapter page for content.
            3. Return a list of {title, content, source_url, sort_order}.

        NOTE: For novels with many chapters this is slow (rate-limited).
        Consider overriding ``max_chapters`` to limit the fetch.
        """
        book_id = _extract_book_id(novel_url)
        if not book_id:
            raise ValueError(f"Cannot extract book_id from URL: {novel_url}")

        catalog_url = f"{self.base_url}/book/{book_id}/catalog"
        html = await self._fetch(catalog_url)
        soup = self._soup(html)

        # Each chapter row: div.module-row-info > a.module-row-text
        chapter_items = soup.select(".module-row-info a.module-row-text")
        chapters: list[dict] = []

        for idx, a_tag in enumerate(chapter_items):
            href = a_tag.get("href", "")
            title = a_tag.get("title", "")
            if not title:
                span = a_tag.select_one(".module-row-title span")
                title = _clean_text(span.get_text()) if span else ""

            chapter_url = urljoin(self.base_url, href)
            source_url = chapter_url

            # Fetch content
            content = ""
            try:
                ch_html = await self._fetch(chapter_url)
                ch_soup = self._soup(ch_html)

                # Chapter body is in div.article-content inside .view-heading.
                content_div = (
                    ch_soup.select_one(".view-heading .article-content")
                    or ch_soup.select_one("div.article-content")
                )
                if content_div:
                    # Remove ad blocks and scripts
                    for junk in content_div.select("script, ins, .adsbygoogle"):
                        junk.decompose()
                    text = _clean_text(content_div.get_text())
                    if text:
                        content = text
            except Exception:
                pass  # skip chapters that fail to fetch

            chapters.append({
                "title": _clean_text(title) or f"第{idx+1}章",
                "content": content,
                "source_url": source_url,
                "sort_order": idx + 1,
            })

        return chapters

    async def get_new_chapters(
        self, novel_url: str, last_source_url: Optional[str] = None
    ) -> list[dict]:
        """Fetch only NEW chapters (since *last_source_url*).

        This is more efficient than ``get_chapters`` for update checks.
        """
        book_id = _extract_book_id(novel_url)
        if not book_id:
            raise ValueError(f"Cannot extract book_id from URL: {novel_url}")

        catalog_url = f"{self.base_url}/book/{book_id}/catalog"
        html = await self._fetch(catalog_url)
        soup = self._soup(html)

        chapter_items = soup.select(".module-row-info a.module-row-text")
        new_chapters: list[dict] = []
        found_existing = False

        for idx, a_tag in enumerate(chapter_items):
            href = a_tag.get("href", "")
            chapter_url = urljoin(self.base_url, href)

            if last_source_url and chapter_url == last_source_url:
                found_existing = True
                break  # stop at the first already-known chapter

            title = a_tag.get("title", "")
            if not title:
                span = a_tag.select_one(".module-row-title span")
                title = _clean_text(span.get_text()) if span else ""

            content = ""
            try:
                ch_html = await self._fetch(chapter_url)
                ch_soup = self._soup(ch_html)
                content_div = (
                    ch_soup.select_one(".view-heading .article-content")
                    or ch_soup.select_one("div.article-content")
                )
                if content_div:
                    for junk in content_div.select("script, ins, .adsbygoogle"):
                        junk.decompose()
                    text = _clean_text(content_div.get_text())
                    if text:
                        content = text
            except Exception:
                pass

            new_chapters.append({
                "title": _clean_text(title) or f"第{idx+1}章",
                "content": content,
                "source_url": chapter_url,
                "sort_order": idx + 1,
            })

        # Return in chronological order (oldest first)
        return list(reversed(new_chapters))

    async def get_category_list(
        self, category_id: int, page: int = 1
    ) -> list[dict]:
        """Fetch the novel list for a given category.

        Args:
            category_id: 1-13 (see CATEGORY_MAP).
            page: Page number.

        Returns:
            List of {title, author, url, book_id, cover_url}.
        """
        url = (
            f"{self.base_url}/book/"
            f"lastupdate_0_{category_id}_0_0_0_0_{page}_0.html"
        )
        html = await self._fetch(url)
        soup = self._soup(html)

        results: list[dict] = []
        for item in soup.select(".module-item"):
            link = item.select_one("a[href*='/book/']")
            if not link:
                continue
            href = urljoin(self.base_url, link.get("href", ""))
            title_el = item.select_one(".module-item-title")
            author_el = item.select_one(".module-item-text")
            img_el = item.select_one("img")

            results.append({
                "title": _clean_text(title_el.get_text()) if title_el else "",
                "author": _clean_text(author_el.get_text()) if author_el else "",
                "url": href,
                "book_id": _extract_book_id(href),
                "cover_url": urljoin(self.base_url, img_el.get("data-src", ""))
                if img_el else "",
            })

        return results
