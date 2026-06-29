"""
Crawl session tracker — in-memory event queue + DB-backed metadata.

In-memory queue:  per-worker, ephemeral events (not shared).
DB metadata:     cross-worker, persisted (task_id, novel_title, worker_pid).

For multi-worker SSE: use Nginx sticky sessions (ip_hash) so the SSE
client always lands on the same worker that holds the in-memory queue.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional


class CrawlEvent:
    """A single progress event emitted during a crawl."""
    __slots__ = ("timestamp", "type", "data")

    def __init__(self, event_type: str, **kwargs):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.type = event_type
        self.data = kwargs

    def to_sse(self) -> str:
        payload = json.dumps({
            "t": self.timestamp, "type": self.type, **self.data,
        }, ensure_ascii=False)
        return f"data: {payload}\n\n"


class CrawlSession:
    """Per-task crawl session holding an event queue + metadata."""

    def __init__(self, task_id: str, novel_title: str = ""):
        self.task_id = task_id
        self.novel_title = novel_title
        self.queue: asyncio.Queue[CrawlEvent] = asyncio.Queue(maxsize=500)
        self.started_at: float = time.monotonic()
        self.finished: bool = False
        self.worker_pid: int = os.getpid()

    def emit(self, event: CrawlEvent):
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # drop if consumer is too slow

    async def close(self):
        self.finished = True
        self.emit(CrawlEvent("done", message="Crawl finished"))


# ── Local registry (per-worker) ──────────────────────────────────
_sessions: dict[str, CrawlSession] = {}
_SESSION_TTL = 7200


async def _db_upsert_session(task_id: str, novel_title: str, status: str):
    """Persist session metadata to DB for cross-worker discovery."""
    try:
        from app.database import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as db:
            await db.execute(text(
                "INSERT INTO crawl_sessions (task_id, novel_title, status, worker_pid) "
                "VALUES (:tid, :title, :status, :pid) "
                "ON DUPLICATE KEY UPDATE novel_title=:title, status=:status, worker_pid=:pid"
            ), {"tid": task_id, "title": novel_title, "status": status, "pid": os.getpid()})
            await db.commit()
    except Exception:
        pass  # table may not exist yet (first run before migration)


async def _db_remove_session(task_id: str):
    try:
        from app.database import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as db:
            await db.execute(text("DELETE FROM crawl_sessions WHERE task_id=:tid"), {"tid": task_id})
            await db.commit()
    except Exception:
        pass


def create_session(task_id: str, novel_title: str = "") -> CrawlSession:
    session = CrawlSession(task_id, novel_title)
    _sessions[task_id] = session
    asyncio.create_task(_db_upsert_session(task_id, novel_title, "running"))
    return session


def get_session(task_id: str) -> Optional[CrawlSession]:
    return _sessions.get(task_id)


def remove_session(task_id: str):
    _sessions.pop(task_id, None)
    asyncio.create_task(_db_remove_session(task_id))


# ── Cleanup ──────────────────────────────────────────────────────

async def _cleanup_stale_sessions():
    now = time.monotonic()
    stale = [tid for tid, s in _sessions.items()
             if now - s.started_at > _SESSION_TTL or s.finished]
    for tid in stale:
        _sessions.pop(tid, None)
        await _db_remove_session(tid)


async def _start_session_cleanup(interval: int = 600):
    while True:
        await asyncio.sleep(interval)
        await _cleanup_stale_sessions()


# ── SSE stream generator ─────────────────────────────────────────

async def stream_events(task_id: str):
    """Async generator yielding SSE strings for *task_id*."""
    session = get_session(task_id)
    if not session:
        yield CrawlEvent("error", message="Session not found — try reconnecting").to_sse()
        return

    yield CrawlEvent("start", task_id=task_id, novel_title=session.novel_title).to_sse()

    while not session.finished:
        try:
            event = await asyncio.wait_for(session.queue.get(), timeout=15.0)
            yield event.to_sse()
        except asyncio.TimeoutError:
            yield CrawlEvent("heartbeat").to_sse()

    while not session.queue.empty():
        yield session.queue.get_nowait().to_sse()

    yield CrawlEvent("done", message="Stream ended").to_sse()
