"""
Generic rule-based crawler — uses JSON rule files to crawl any site without
writing Python code.

Each site requires a rule JSON file in ``app/crawlers/rules/{source_name}.json``.
The rule engine handles all extraction; this crawler just orchestrates the flow.
"""
import asyncio
import re
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import register_crawler
from app.crawlers.rule_engine import (
    load_rule, apply_rule, fetch_url, HEADERS,
)
from app.crawlers.content_cleaner import (
    clean_content as _clean_content,
    clean_title as _clean_title,
    clean_novel_title,
)


def _clean_text(text: Optional[str]) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


class RuleBasedCrawler(BaseCrawler):
    """Generic crawler driven entirely by JSON rule files.

    To add a new site:
        1. Create ``rules/{source_name}.json`` with the selectors schema.
        2. Set ``source_name`` and ``base_url`` in the rule JSON.
        3. This crawler auto-detects rules by ``source_name`` at runtime.

    The rule JSON must contain a ``selectors`` block with (at minimum):
        - ``search``
        - ``novel_info``
        - ``catalog``
        - ``chapter``
    Each section has ``url``, ``container`` (optional), and ``fields``.
    """

    # source_name, base_url, description are set dynamically from the rule
    source_name = "_rule_based"
    base_url = ""
    description = "Generic rule-based crawler"

    def __init__(self, source_name: str = "", base_url: str = "", description: str = ""):
        super().__init__()
        if source_name:
            self.source_name = source_name
            rule = load_rule(source_name)
            if rule:
                self.base_url = rule.get("base_url", "")
                self.description = rule.get("description", "")
        if base_url:
            self.base_url = base_url
        if description:
            self.description = description
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
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
    # Core helpers
    # ------------------------------------------------------------------

    def _rule(self):
        """Load the rule file for this crawler's source_name."""
        rule = load_rule(self.source_name)
        if not rule:
            raise ValueError(f"Rule '{self.source_name}' not found in rules/")
        return rule

    def _section(self, name: str):
        """Get a section's selectors from the rule."""
        rule = self._rule()
        return rule.get("selectors", {}).get(name, {})

    async def _fetch(self, url: str) -> str:
        await asyncio.sleep(settings.CRAWLER_REQUEST_DELAY)
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.text

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(self, keyword: str) -> list[dict]:
        rule = self._rule()
        ss = self._section("search")
        url_tmpl = ss.get("url", f"{self.base_url}/search?q={{keyword}}")
        url = url_tmpl.replace("{keyword}", keyword)

        html = await self._fetch(url)
        results = apply_rule(
            html,
            self.base_url,
            ss.get("fields", {}),
            container_selector=ss.get("container", ""),
            context={"url": url, "base_url": self.base_url},
        )
        # Normalize field names
        out = []
        for r in results:
            out.append({
                "title": r.get("title", ""),
                "author": r.get("author", ""),
                "url": r.get("url", ""),
                "book_id": r.get("book_id", ""),
                "cover_url": r.get("cover_url", ""),
                "description": r.get("description", ""),
            })
        return out

    async def get_novel_info(self, novel_url: str) -> dict:
        si = self._section("novel_info")
        html = await self._fetch(novel_url)
        results = apply_rule(
            html,
            self.base_url,
            si.get("fields", {}),
            container_selector=si.get("container", ""),
            context={"url": novel_url, "base_url": self.base_url},
        )
        r = results[0] if results else {}
        return {
            "title": clean_novel_title(r.get("title", "")),
            "author": r.get("author", ""),
            "description": r.get("description", ""),
            "cover_url": urljoin(self.base_url, r.get("cover_url", "")) if r.get("cover_url") else "",
            "status": r.get("status", "ongoing"),
            "category_name": r.get("category_name", ""),
            "book_id": r.get("book_id", ""),
        }

    async def get_chapters(self, novel_url: str) -> list[dict]:
        """Fetch chapter list from catalog + content from each chapter."""
        sc = self._section("catalog")
        # Build catalog URL
        book_id = re.search(r"/book/(\d+)", novel_url)
        if book_id and sc.get("url"):
            catalog_url = sc.get("url").replace("{book_id}", book_id.group(1)).replace("{base_url}", self.base_url)
        else:
            catalog_url = novel_url

        html = await self._fetch(catalog_url)
        catalog_results = apply_rule(
            html,
            self.base_url,
            sc.get("fields", {}),
            container_selector=sc.get("container", ""),
            context={"url": catalog_url, "base_url": self.base_url},
        )

        # Fetch each chapter's content
        sch = self._section("chapter")
        chapters: list[dict] = []
        for idx, cat in enumerate(catalog_results):
            ch_url = cat.get("url", "")
            if not ch_url:
                continue
            ch_url = urljoin(self.base_url, ch_url)
            content = ""
            try:
                ch_html = await self._fetch(ch_url)
                content_results = apply_rule(
                    ch_html,
                    self.base_url,
                    sch.get("fields", {}),
                    container_selector=sch.get("container", ""),
                    context={"url": ch_url, "base_url": self.base_url},
                )
                if content_results:
                    content = content_results[0].get("content", "")
            except Exception:
                pass

            chapters.append({
                "title": _clean_title(cat.get("title", f"第{idx+1}章")),
                "content": content,
                "source_url": ch_url,
                "sort_order": idx + 1,
            })

        return chapters
