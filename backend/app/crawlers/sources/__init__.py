"""Crawler source implementations.

To add a new source, create a new file in this directory and decorate
your crawler class with @register_crawler. It will be auto-discovered
when imported.
"""

# Import sources to trigger registration
from app.crawlers.sources import example  # noqa: F401
from app.crawlers.sources import twenty_three_qb  # noqa: F401
