"""
In-memory crawl session tracker for real-time progress streaming.

Each running crawl task publishes events to a per-task asyncio queue.
The SSE endpoint consumes the queue and pushes events to the frontend.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class CrawlEvent:
    """A single progress event emitted during a crawl."""

    def __init__(self, event_type: str, **kwargs):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.type = event_type
        self.data = kwargs

    def to_sse(self) -> str:
        payload = json.dumps({
            "t": self.timestamp,
            "type": self.type,
            **self.data,
        }, ensure_ascii=False)
        return f"data: {payload}\n\n"


# ---------------------------------------------------------------------------
# Session manager
# ---------------------------------------------------------------------------

class CrawlSession:
    """Per-task crawl session holding an event queue."""

    def __init__(self, task_id: str, novel_title: str = ""):
        self.task_id = task_id
        self.novel_title = novel_title
        self.queue: asyncio.Queue[CrawlEvent] = asyncio.Queue(maxsize=500)
        self.started_at: float = time.monotonic()
        self.chapter_index: int = 0
        self.chapter_total: int = 0
        self.current_title: str = ""
        self.current_content_preview: str = ""
        self.finished: bool = False

    def emit(self, event: CrawlEvent):
        """Push an event into the queue (non-blocking)."""
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # drop if consumer is too slow

    async def close(self):
        """Signal end of stream."""
        self.finished = True
        self.emit(CrawlEvent("done", message="Crawl finished"))


# Global registry: task_id -> CrawlSession
_sessions: dict[str, CrawlSession] = {}
_SESSION_TTL = 7200  # 2 hours max session lifetime


async def _cleanup_stale_sessions():
    """Remove sessions older than _SESSION_TTL."""
    now = time.monotonic()
    stale = [
        tid for tid, s in _sessions.items()
        if now - s.started_at > _SESSION_TTL or s.finished
    ]
    for tid in stale:
        _sessions.pop(tid, None)


def create_session(task_id: str, novel_title: str = "") -> CrawlSession:
    session = CrawlSession(task_id, novel_title)
    _sessions[task_id] = session
    return session


def get_session(task_id: str) -> Optional[CrawlSession]:
    return _sessions.get(task_id)


def remove_session(task_id: str):
    _sessions.pop(task_id, None)


async def stream_events(task_id: str):
    """Async generator yielding SSE strings for *task_id*."""
    session = get_session(task_id)
    if not session:
        yield CrawlEvent("error", message="Session not found").to_sse()
        return

    # Send initial state
    yield CrawlEvent("start", task_id=task_id, novel_title=session.novel_title).to_sse()

    while not session.finished:
        try:
            event = await asyncio.wait_for(session.queue.get(), timeout=15.0)
            yield event.to_sse()
        except asyncio.TimeoutError:
            # Send heartbeat to keep connection alive
            yield CrawlEvent("heartbeat").to_sse()

    # Drain remaining events
    while not session.queue.empty():
        event = session.queue.get_nowait()
        yield event.to_sse()

    yield CrawlEvent("done", message="Stream ended").to_sse()
