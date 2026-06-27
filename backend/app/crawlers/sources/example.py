"""
Example crawler implementation.

This is a template showing how to implement a novel source crawler.
Replace with actual implementations for real sources like Qidian, Zongheng, etc.

NOTE: Web scraping may be subject to the target site's terms of service.
Always respect robots.txt and rate-limit your requests.
"""

import asyncio

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import register_crawler


@register_crawler
class ExampleCrawler(BaseCrawler):
    """Example crawler that fetches from a novel listing site."""

    source_name = "example"
    base_url = "https://example-novels.com"
    description = "Example novel source (template)"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=settings.CRAWLER_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        )

    async def _fetch(self, url: str) -> str:
        """Fetch a URL and return the HTML text."""
        await asyncio.sleep(settings.CRAWLER_REQUEST_DELAY)
        response = await self.client.get(url)
        response.raise_for_status()
        return response.text

    async def get_novel_info(self, novel_url: str) -> dict:
        """Fetch novel metadata.

        Override this with actual parsing logic for your target site.
        """
        html = await self._fetch(novel_url)
        soup = BeautifulSoup(html, "lxml")

        # TODO: Replace with actual selectors
        return {
            "title": "",
            "author": "",
            "description": "",
            "cover_url": "",
        }

    async def get_chapters(self, novel_url: str) -> list[dict]:
        """Fetch chapter list and content.

        Override this with actual parsing logic for your target site.
        """
        html = await self._fetch(novel_url)
        soup = BeautifulSoup(html, "lxml")

        chapters: list[dict] = []

        # TODO: Replace with actual parsing logic
        # 1. Find the chapter list on the page
        # 2. For each chapter link:
        #    a. Fetch chapter page
        #    b. Parse title + content
        #    c. Append to chapters list

        return chapters

    async def search(self, keyword: str) -> list[dict]:
        """Search for novels by keyword.

        Override this with actual search logic for your target site.
        """
        search_url = f"{self.base_url}/search?q={keyword}"
        html = await self._fetch(search_url)
        soup = BeautifulSoup(html, "lxml")

        results: list[dict] = []

        # TODO: Replace with actual parsing logic

        return results

    async def close(self):
        """Clean up the HTTP client."""
        await self.client.aclose()
