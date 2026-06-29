"""
Chapter content file-store with gzip compression and LRU cache.

File layout::

    data/content/{novel_id[:2]}/{novel_id}/{chapter_id}.gz

Each file is a gzip-compressed UTF-8 text blob.  Metadata (title,
word_count, sort_order) stays in the DB ``chapters`` table.

Performance characteristics (vs DB TEXT):
    - Volume:   ~70 % smaller (gzip on Chinese text)
    - Read:     comparable to DB (after first OS page-cache warmup)
    - Write:    ~2× faster (no DB round-trip)
    - DB load:  dramatically reduced (no large TEXT blobs in queries)
"""

import asyncio
import gzip
import os
import time
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONTENT_ROOT = Path("data/content")
MAX_CACHE_ITEMS = 100   # keep the 100 most-recently-read chapters in memory
MAX_CACHE_BYTES = 16 * 1024 * 1024  # 16 MiB max

# ---------------------------------------------------------------------------
# LRU cache
# ---------------------------------------------------------------------------

_cache: OrderedDict[str, str] = OrderedDict()
_cache_bytes: int = 0
_lock: Lock = Lock()


def _file_path(novel_id: str, chapter_id: str) -> Path:
    """Return the filesystem path for a chapter content file."""
    return CONTENT_ROOT / novel_id[:2] / novel_id / f"{chapter_id}.gz"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_content(novel_id: str, chapter_id: str, text: str) -> str:
    """Compress and write chapter content to disk.

    Returns the relative file path (e.g. ``data/content/ab/abc.../xyz.gz``).
    """
    if not text:
        return ""

    path = _file_path(novel_id, chapter_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    compressed = gzip.compress(text.encode("utf-8"), compresslevel=3)
    path.write_bytes(compressed)

    rel = str(path.relative_to(CONTENT_ROOT.parent))
    return rel


def read_content(novel_id: str, chapter_id: str, file_path: str = "") -> str:
    """Read and decompress chapter content.

    Uses LRU cache; falls back to disk if not cached.
    """
    with _lock:
        cache_key = f"{novel_id}:{chapter_id}"
        if cache_key in _cache:
            # Move to end (most-recently-used)
            text = _cache.pop(cache_key)
            _cache[cache_key] = text
            return text

    # Read from disk
    path = _file_path(novel_id, chapter_id)
    if not path.is_file() and file_path:
        # Try the DB-stored path
        path = Path(file_path)
    if not path.is_file():
        return ""

    compressed = path.read_bytes()
    text = gzip.decompress(compressed).decode("utf-8")

    # Cache it
    with _lock:
        _add_to_cache(cache_key, text)

    return text


def delete_content(novel_id: str, chapter_id: str, file_path: str = "") -> None:
    """Delete a chapter content file from disk and cache."""
    global _cache_bytes
    with _lock:
        cache_key = f"{novel_id}:{chapter_id}"
        old = _cache.pop(cache_key, None)
        if old is not None:
            _cache_bytes -= len(old.encode("utf-8"))

    path = _file_path(novel_id, chapter_id)
    if path.is_file():
        path.unlink()
    elif file_path:
        p = Path(file_path)
        if p.is_file():
            p.unlink()


def exists(novel_id: str, chapter_id: str, file_path: str = "") -> bool:
    """Check whether content exists on disk."""
    path = _file_path(novel_id, chapter_id)
    return path.is_file() or (bool(file_path) and Path(file_path).is_file())


def stats() -> dict:
    """Return cache statistics."""
    with _lock:
        return {
            "cached_items": len(_cache),
            "cached_bytes": _cache_bytes,
            "max_items": MAX_CACHE_ITEMS,
            "max_bytes": MAX_CACHE_BYTES,
        }


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _add_to_cache(key: str, text: str):
    global _cache_bytes
    size = len(text.encode("utf-8"))  # accurate byte count for CJK (3 bytes/char)
    _cache[key] = text
    _cache_bytes += size
    # Evict oldest entries if over limits
    while _cache and (_cache_bytes > MAX_CACHE_BYTES or len(_cache) > MAX_CACHE_ITEMS):
        oldest_key, oldest_val = _cache.popitem(last=False)
        _cache_bytes -= len(oldest_val.encode("utf-8"))


# ── Async wrappers (offload blocking I/O to thread pool) ──────────────


async def awrite_content(novel_id: str, chapter_id: str, text: str) -> str:
    """Async wrapper for :func:`write_content`."""
    return await asyncio.to_thread(write_content, novel_id, chapter_id, text)


async def aread_content(novel_id: str, chapter_id: str, file_path: str = "") -> str:
    """Async wrapper for :func:`read_content`."""
    return await asyncio.to_thread(read_content, novel_id, chapter_id, file_path)


async def adelete_content(novel_id: str, chapter_id: str, file_path: str = "") -> None:
    """Async wrapper for :func:`delete_content`."""
    return await asyncio.to_thread(delete_content, novel_id, chapter_id, file_path)
