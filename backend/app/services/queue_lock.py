"""DB-backed distributed lock for queue coordination (no Redis needed).

Uses the ``system_state`` table with atomic INSERT ON CONFLICT semantics.
A worker acquires a lock by atomically inserting/updating a key with its PID
and a TTL. Other workers see the lock held and back off.

Compatible with PostgreSQL and MySQL.
"""

import os
from datetime import datetime, timezone

from app.config import settings


def _is_pg() -> bool:
    return "postgresql" in settings.DATABASE_URL or "asyncpg" in settings.DATABASE_URL


async def acquire_queue_lock(lock_key: str = "queue_processor", ttl: int = 120) -> bool:
    """Try to acquire a distributed lock. Returns True if acquired."""
    from app.database import async_session_factory
    from sqlalchemy import text

    pid = os.getpid()
    now = datetime.now(timezone.utc)

    try:
        async with async_session_factory() as db:
            if _is_pg():
                await db.execute(text("""
                    INSERT INTO system_state (key, value, worker_pid, locked_at, lock_ttl)
                    VALUES (:key, 'locked', :pid, :now, :ttl)
                    ON CONFLICT (key) DO UPDATE SET
                        value = CASE WHEN system_state.value IS NULL OR system_state.locked_at IS NULL
                            OR EXTRACT(EPOCH FROM (:now - system_state.locked_at)) > system_state.lock_ttl
                            THEN 'locked' ELSE system_state.value END,
                        worker_pid = CASE WHEN system_state.value IS NULL OR system_state.locked_at IS NULL
                            OR (system_state.value = 'locked' AND
                                EXTRACT(EPOCH FROM (:now - system_state.locked_at)) > system_state.lock_ttl)
                            THEN :pid ELSE system_state.worker_pid END,
                        locked_at = CASE WHEN system_state.value IS NULL OR system_state.locked_at IS NULL
                            OR (system_state.value = 'locked' AND
                                EXTRACT(EPOCH FROM (:now - system_state.locked_at)) > system_state.lock_ttl)
                            THEN :now ELSE system_state.locked_at END
                """), {"key": lock_key, "pid": pid, "now": now, "ttl": ttl})
            else:
                await db.execute(text("""
                    INSERT INTO system_state (`key`, `value`, `worker_pid`, `locked_at`, `lock_ttl`)
                    VALUES (:key, 'locked', :pid, :now, :ttl)
                    ON DUPLICATE KEY UPDATE
                        `value` = IF(`value` IS NULL OR `locked_at` IS NULL OR
                            TIMESTAMPDIFF(SECOND, `locked_at`, :now) > `lock_ttl`,
                            'locked', `value`),
                        `worker_pid` = IF(`value` IS NULL OR `locked_at` IS NULL OR
                            (`value` = 'locked' AND
                             TIMESTAMPDIFF(SECOND, `locked_at`, :now) > `lock_ttl`),
                            :pid, `worker_pid`),
                        `locked_at` = IF(`value` IS NULL OR `locked_at` IS NULL OR
                            (`value` = 'locked' AND
                             TIMESTAMPDIFF(SECOND, `locked_at`, :now) > `lock_ttl`),
                            :now, `locked_at`)
                """), {"key": lock_key, "pid": pid, "now": now, "ttl": ttl})
            await db.commit()

            q = 'SELECT worker_pid FROM system_state WHERE "key"=:key' if _is_pg() \
                else 'SELECT worker_pid FROM system_state WHERE `key`=:key'
            result = await db.execute(text(q), {"key": lock_key})
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
            q = ('UPDATE system_state SET value=NULL, locked_at=NULL '
                 'WHERE "key"=:key AND worker_pid=:pid') if _is_pg() else \
                ('UPDATE system_state SET `value`=NULL, `locked_at`=NULL '
                 'WHERE `key`=:key AND worker_pid=:pid')
            await db.execute(text(q), {"key": lock_key, "pid": os.getpid()})
            await db.commit()
    except Exception:
        pass
