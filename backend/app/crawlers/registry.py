from typing import Optional

from app.crawlers.base import BaseCrawler

_crawlers: dict[str, type[BaseCrawler]] = {}
_sources_loaded: bool = False


def _ensure_sources():
    """Lazy-import crawler source modules to trigger @register_crawler.

    Called automatically on first access to get_crawler / list_sources,
    avoiding circular imports at module load time.
    """
    global _sources_loaded
    if not _sources_loaded:
        import app.crawlers.sources  # noqa: F401
        _sources_loaded = True


def register_crawler(cls: type[BaseCrawler]) -> type[BaseCrawler]:
    """Decorator to register a crawler class."""
    _crawlers[cls.source_name] = cls
    return cls


def get_crawler(source_name: str) -> Optional[BaseCrawler]:
    """Get a crawler instance by source name."""
    _ensure_sources()
    cls = _crawlers.get(source_name)
    if cls is None:
        return None
    return cls()


def list_sources() -> list[dict]:
    """List all registered crawler sources."""
    _ensure_sources()
    return [
        {
            "source_name": cls.source_name,
            "base_url": cls.base_url,
            "description": cls.description,
        }
        for cls in _crawlers.values()
    ]
