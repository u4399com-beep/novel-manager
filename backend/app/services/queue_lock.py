"""DB-backed distributed lock for queue coordination (no Redis needed).

Uses the ``system_state`` table with MySQL ``GET_LOCK()``-style semantics.
A worker acquires a lock by atomically inserting/updating a key with its PID
and a TTL. Other workers see the lock held and back off.

Usage:
    lock = await acquire_queue_lock()
    if lock:
        try: ...   # process queue
        finally: await release_queue_lock()
"""

import asyncio
import os
from datetime import datetime, timezone


async def acquire_queue_lock(lock_key: str = "queue_processor", ttl: int = 120) -> bool:
    """Try to acquire a distributed lock. Returns True if acquired."""
    from app.database import async_session_factory
    from sqlalchemy import text

    pid = os.getpid()
    now = datetime.now(timezone.utc)

    try:
        async with async_session_factory() as db:
            # Atomically: insert if not exists, or update if expired
            result = await db.execute(text("""
                INSERT INTO system_state (`key`, `value`, `worker_pid`, `locked_at`, `lock_ttl`)
                VALUES (:key, 'locked', :pid, :now, :ttl)
                ON DUPLICATE KEY UPDATE
                    `value` = IF(`locked_at` IS NULL OR
                        TIMESTAMPDIFF(SECOND, `locked_at`, :now) > `lock_ttl`,
                        'locked', `value`),
                    `worker_pid` = IF(`value` = 'locked' AND
                        TIMESTAMPDIFF(SECOND, `locked_at`, :now) > `lock_ttl`,
                        :pid, `worker_pid`),
                    `locked_at` = IF(`value` = 'locked' AND
                        TIMESTAMPDIFF(SECOND, `locked_at`, :now) > `lock_ttl`,
                        :now, `locked_at`)
            """), {"key": lock_key, "pid": pid, "now": now, "ttl": ttl})
            await db.commit()

            # Check if we got the lock
            result = await db.execute(
                text("SELECT worker_pid FROM system_state WHERE `key`=:key"),
                {"key": lock_key}
            )
            row = result.fetchone()
            return row is not None and row[0] == pid
    except Exception:
        return False


async def release_queue_lock(lock_key: str = "queue_processor"):
    """Release a previously acquired distributed lock."""
    from app.database import async_session_factory
    from sqlalchemy import text

    try:
        async with async_session_factory() as db:
            await db.execute(
                text("UPDATE system_state SET `value`=NULL, `locked_at`=NULL "
                     "WHERE `key`=:key AND worker_pid=:pid"),
                {"key": lock_key, "pid": os.getpid()}
            )
            await db.commit()
    except Exception:
        pass
