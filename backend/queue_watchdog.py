#!/usr/bin/env python3
"""Queue watchdog — monitors and auto-restarts the crawl queue every 5 min.

- Checks if queue_runner process is alive
- Checks if tasks are stuck in "running" state > 10 min
- Auto-restarts queue_runner if dead or stuck
- Resets stuck tasks to "pending"
"""
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("watchdog")

CHECK_INTERVAL = 300  # 5 minutes
STUCK_THRESHOLD = 600  # 10 minutes stuck → restart
QUEUE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "queue_runner.py")


async def get_queue_stats():
    from app.database import async_session_factory
    from app.models.crawler_task import CrawlerTask
    from sqlalchemy import select, func

    async with async_session_factory() as db:
        stats = {}
        for st in ("pending", "running", "completed", "failed"):
            stats[st] = (
                await db.execute(select(func.count()).where(CrawlerTask.status == st))
            ).scalar() or 0

        # Check stuck tasks (running > threshold)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=STUCK_THRESHOLD)
        stuck = (
            await db.execute(
                select(func.count()).where(
                    CrawlerTask.status == "running",
                    CrawlerTask.started_at < cutoff,
                )
            )
        ).scalar() or 0
        stats["stuck"] = stuck
        return stats


def is_runner_alive():
    """Check if queue_runner.py process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "queue_runner.py"],
            capture_output=True, text=True, timeout=5,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def start_runner():
    """Start queue_runner.py as a background process."""
    log.info("Starting queue_runner...")
    try:
        proc = subprocess.Popen(
            [sys.executable, QUEUE_SCRIPT, "--concurrent", "8"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        # Detach — let it run independently
        return True
    except Exception as e:
        log.error(f"Failed to start queue_runner: {e}")
        return False


async def reset_stuck_tasks():
    """Reset tasks stuck in 'running' state for too long."""
    from app.database import async_session_factory
    from app.models.crawler_task import CrawlerTask
    from sqlalchemy import update

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STUCK_THRESHOLD)
    async with async_session_factory() as db:
        result = await db.execute(
            update(CrawlerTask)
            .where(CrawlerTask.status == "running", CrawlerTask.started_at < cutoff)
            .values(status="pending", error_message="Watchdog: reset stuck task", started_at=None)
        )
        await db.commit()
        if result.rowcount > 0:
            log.info(f"Reset {result.rowcount} stuck tasks → pending")


async def repair_empty_chapters():
    """Auto-create crawl tasks for novels with empty chapters."""
    from app.database import async_session_factory
    from app.models.chapter import Chapter
    from app.models.crawler_task import CrawlerTask
    from sqlalchemy import select, func, and_

    async with async_session_factory() as db:
        # Find novels with empty chapters but with source URLs
        result = await db.execute(
            select(Chapter.novel_id, func.count())
            .where(and_(Chapter.content == None, Chapter.content_file == None, Chapter.source_url != None))
            .group_by(Chapter.novel_id)
            .limit(20)
        )
        novel_counts = result.all()
        
        created = 0
        for nid, cnt in novel_counts:
            # Check if already has a pending task
            existing = (await db.execute(
                select(func.count()).where(
                    CrawlerTask.novel_id == nid, CrawlerTask.status == 'pending'
                )
            )).scalar() or 0
            if existing == 0:
                db.add(CrawlerTask(novel_id=nid, status='pending'))
                created += 1
        
        if created:
            await db.commit()
            log.info(f"Auto-repair: created {created} tasks for {len(novel_counts)} novels with empty chapters")
        return created

async def watchdog_cycle():
    """One watchdog check cycle."""
    # Auto-repair empty chapters
    await repair_empty_chapters()
    stats = await get_queue_stats()
    alive = is_runner_alive()

    total = sum(stats[s] for s in ("pending", "running", "completed", "failed"))
    pct = (stats["completed"] + stats["failed"]) / total * 100 if total > 0 else 0

    log.info(
        f"Queue: pending={stats['pending']} running={stats['running']} "
        f"completed={stats['completed']} failed={stats['failed']} "
        f"stuck={stats['stuck']} | {pct:.1f}% | runner={'✅' if alive else '❌'}"
    )

    needs_restart = False

    # Track progress across cycles (prevent false restart)
    if not hasattr(watchdog_cycle, "_last_pending"):
        watchdog_cycle._last_pending = stats["pending"]
        watchdog_cycle._last_completed = stats["completed"]

    making_progress = (
        stats["pending"] < watchdog_cycle._last_pending or
        stats["completed"] > watchdog_cycle._last_completed
    )
    watchdog_cycle._last_pending = stats["pending"]
    watchdog_cycle._last_completed = stats["completed"]

    # Condition 1: runner process dead
    if not alive:
        log.warning("Queue runner is DEAD — restarting")
        needs_restart = True

    # Condition 2: tasks stuck > 10 min
    if stats["stuck"] > 0:
        log.warning(f"{stats['stuck']} tasks stuck > {STUCK_THRESHOLD}s — resetting")
        await reset_stuck_tasks()
        needs_restart = True

    # Condition 3: runner alive but stuck (no progress across cycles)
    if alive and stats["pending"] > 0 and stats["running"] == 0 and not making_progress:
        log.warning("Queue has pending tasks but no progress — restarting")
        needs_restart = True

    if needs_restart:
        # Kill existing runner first
        subprocess.run(["pkill", "-9", "-f", "queue_runner.py"], capture_output=True)
        time.sleep(1)
        start_runner()


async def main():
    log.info(f"Watchdog started (interval={CHECK_INTERVAL}s, stuck_threshold={STUCK_THRESHOLD}s)")

    while True:
        try:
            await watchdog_cycle()
        except Exception as e:
            log.error(f"Watchdog cycle failed: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    asyncio.run(main())
