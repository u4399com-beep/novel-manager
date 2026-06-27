from abc import ABC, abstractmethod


class BaseCrawler(ABC):
    """Abstract base class for novel crawlers.

    Each crawler implementation corresponds to a specific novel source website
    (e.g., Qidian, Zongheng) and knows how to fetch novel info and chapter
    content from that source.
    """

    source_name: str = ""
    base_url: str = ""
    description: str = ""

    @abstractmethod
    async def get_novel_info(self, novel_url: str) -> dict:
        """Fetch novel metadata from the source.

        Returns:
            dict with keys: title, author, description, cover_url
        """
        ...

    @abstractmethod
    async def get_chapters(self, novel_url: str) -> list[dict]:
        """Fetch all chapter data from the source.

        Returns:
            List of dicts, each with keys: title, content, source_url, sort_order (optional)
        """
        ...

    @abstractmethod
    async def search(self, keyword: str) -> list[dict]:
        """Search for novels on the source site.

        Returns:
            List of dicts, each with keys: title, author, url, description
        """
        ...
