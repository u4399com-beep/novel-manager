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
from app.crawlers.content_cleaner import clean_chapter_title
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
        """
        search_url = f"{self.base_url}/search.html?searchkey={keyword}"
        html = await self._fetch(search_url)
        soup = self._soup(html)

        results: list[dict] = []

        for item in soup.select(".module-search-item"):
            links = item.select("a")
            if len(links) < 3:
                continue

            title_link = links[2]
            href = urljoin(self.base_url, title_link.get("href", ""))
            title = _clean_text(title_link.get_text()) or ""

            full_text = item.get_text(" ", strip=True)
            author = ""
            parts = full_text.split(".")
            if len(parts) >= 3:
                author = parts[2].strip()

            if title:
                desc_parts = full_text.split(title, 1)
                description = desc_parts[1].strip() if len(desc_parts) > 1 else ""
            else:
                description = ""
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

        if not title:
            h1 = soup.select_one("h1.page-title")
            title = _clean_text(h1.get_text()) if h1 else ""

        if not author:
            author_link = soup.select_one(".novel-info-aux a[title]")
            if author_link:
                author_text = author_link.get("title", "")
                if author_text.startswith("作者："):
                    author = author_text[3:]

        category_name = ""
        cat_link = soup.select_one(".novel-info-aux a[href*='/book/lastupdate']")
        if cat_link:
            category_name = cat_link.get_text(strip=True)

        word_count = 0
        word_span = soup.find("span", class_="tag-link", string=re.compile(r"万字"))
        if word_span:
            wm = re.search(r"([\d.]+)\s*万", word_span.get_text())
            if wm:
                word_count = int(float(wm.group(1)) * 10000)

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

    # ------------------------------------------------------------------
    # Chapter fetching (concurrent)
    # ------------------------------------------------------------------

    _CHAPTER_CONTENT_SELECTORS = [
        ".view-heading .article-content",
        "div.article-content",
    ]
    _JUNK_SELECTORS = ["script", "ins", ".adsbygoogle"]

    async def get_chapters(
        self, novel_url: str, max_chapters: Optional[int] = None
    ) -> list[dict]:
        """Fetch ALL chapters (with content) for a novel — **concurrently**.

        Fetches up to ``CRAWLER_CONCURRENCY`` (default 10) chapter pages
        in parallel via :class:`asyncio.Semaphore`.

        Returns:
            list[dict]: Each dict has keys *title*, *content*,
                        *source_url*, *sort_order* (catalog order).
        """
        book_id = _extract_book_id(novel_url)
        if not book_id:
            raise ValueError(f"Cannot extract book_id from URL: {novel_url}")

        catalog_url = f"{self.base_url}/book/{book_id}/catalog"
        html = await self._fetch(catalog_url)
        soup = self._soup(html)

        chapter_items = soup.select(".module-row-info a.module-row-text")
        if max_chapters:
            chapter_items = chapter_items[:max_chapters]

        concurrency = getattr(settings, "CRAWLER_CONCURRENCY", 10)
        sem = asyncio.Semaphore(concurrency)

        async def _fetch_one(idx: int, a_tag) -> dict:
            async with sem:
                href = a_tag.get("href", "")
                title = a_tag.get("title", "")
                if not title:
                    span = a_tag.select_one(".module-row-title span")
                    title = _clean_text(span.get_text()) if span else ""

                chapter_url = urljoin(self.base_url, href)

                content = ""
                try:
                    ch_html = await self._fetch(chapter_url)
                    ch_soup = self._soup(ch_html)
                    content_div = None
                    for sel in self._CHAPTER_CONTENT_SELECTORS:
                        content_div = ch_soup.select_one(sel)
                        if content_div:
                            break
                    if content_div:
                        for junk in content_div.select(", ".join(self._JUNK_SELECTORS)):
                            junk.decompose()
                        text = _clean_text(content_div.get_text())
                        if text:
                            content = text
                except Exception:
                    pass  # skip chapters that fail to fetch

                ch_title = clean_chapter_title(_clean_text(title) or "")
                if not ch_title:
                    ch_title = f"第{idx+1}章"
                return {
                    "title": ch_title,
                    "content": content,
                    "source_url": chapter_url,
                    "sort_order": idx + 1,
                }

        results = await asyncio.gather(
            *[_fetch_one(i, a) for i, a in enumerate(chapter_items)]
        )
        return list(results)

    async def get_new_chapters(
        self, novel_url: str, last_source_url: Optional[str] = None
    ) -> list[dict]:
        """Fetch only NEW chapters (since *last_source_url*) — **concurrently**."""
        book_id = _extract_book_id(novel_url)
        if not book_id:
            raise ValueError(f"Cannot extract book_id from URL: {novel_url}")

        catalog_url = f"{self.base_url}/book/{book_id}/catalog"
        html = await self._fetch(catalog_url)
        soup = self._soup(html)

        chapter_items = soup.select(".module-row-info a.module-row-text")

        # Find cutoff: first already-known chapter
        cutoff = len(chapter_items)
        if last_source_url:
            for i, a_tag in enumerate(chapter_items):
                href = a_tag.get("href", "")
                chapter_url = urljoin(self.base_url, href)
                if chapter_url == last_source_url:
                    cutoff = i
                    break
        new_items = chapter_items[:cutoff]

        concurrency = getattr(settings, "CRAWLER_CONCURRENCY", 10)
        sem = asyncio.Semaphore(concurrency)

        async def _fetch_one(idx: int, a_tag) -> dict:
            async with sem:
                href = a_tag.get("href", "")
                title = a_tag.get("title", "")
                if not title:
                    span = a_tag.select_one(".module-row-title span")
                    title = _clean_text(span.get_text()) if span else ""

                chapter_url = urljoin(self.base_url, href)

                content = ""
                try:
                    ch_html = await self._fetch(chapter_url)
                    ch_soup = self._soup(ch_html)
                    content_div = None
                    for sel in self._CHAPTER_CONTENT_SELECTORS:
                        content_div = ch_soup.select_one(sel)
                        if content_div:
                            break
                    if content_div:
                        for junk in content_div.select(", ".join(self._JUNK_SELECTORS)):
                            junk.decompose()
                        text = _clean_text(content_div.get_text())
                        if text:
                            content = text
                except Exception:
                    pass

                ch_title = clean_chapter_title(_clean_text(title) or "")
                if not ch_title:
                    ch_title = f"第{idx+1}章"
                return {
                    "title": ch_title,
                    "content": content,
                    "source_url": chapter_url,
                    "sort_order": idx + 1,
                }

        results = await asyncio.gather(
            *[_fetch_one(i, a) for i, a in enumerate(new_items)]
        )
        return list(results)

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
