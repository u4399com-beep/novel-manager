#!/usr/bin/env python3
"""High-performance queue runner — parallel crawl tasks with shared connection pool.

Usage:
    python3 queue_runner.py                  # default: 5 concurrent
    python3 queue_runner.py --concurrent 10  # 10 concurrent tasks

Uses DB-backed distributed lock (queue_lock.py) to prevent duplicate runners
across gunicorn workers — no Redis required.
"""
import asyncio
import logging
import os
import signal
import sys
import time
from argparse import ArgumentParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
)
log = logging.getLogger("queue")

TASK_TIMEOUT = 300
DEFAULT_CONCURRENCY = 5


async def fetch_pending_batch(db, limit: int):
    from app.models.crawler_task import CrawlerTask
    from sqlalchemy import select
    result = await db.execute(
        select(CrawlerTask)
        .where(CrawlerTask.status == "pending")
        .order_by(CrawlerTask.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    tasks = result.scalars().all()
    for t in tasks:
        t.status = "running"
    await db.flush()
    return tasks


async def count_pending(db_or_factory) -> int:
    from app.models.crawler_task import CrawlerTask
    from sqlalchemy import select, func
    from sqlalchemy.ext.asyncio import AsyncSession
    if isinstance(db_or_factory, AsyncSession):
        return (await db_or_factory.execute(select(func.count()).where(CrawlerTask.status == "pending"))).scalar() or 0
    else:
        async with db_or_factory() as db:
            return (await db.execute(select(func.count()).where(CrawlerTask.status == "pending"))).scalar() or 0


async def process_one(task_id: str, novel_title: str, remaining: int) -> bool:
    from app.database import async_session_factory
    from app.services.crawler_service import run_crawl
    tid_short = task_id[:12]
    log.info(f"[{remaining:>5}] {tid_short}  {novel_title[:30]}")
    try:
        async with async_session_factory() as db:
            await asyncio.wait_for(run_crawl(db, task_id, mode="direct"), timeout=TASK_TIMEOUT)
            await db.commit()
        log.info(f"  ✅ {tid_short}")
        return True
    except asyncio.TimeoutError:
        log.warning(f"  ⏱ {tid_short} timeout — resetting to pending")
        from app.models.crawler_task import CrawlerTask as CT
        try:
            async with async_session_factory() as db:
                task = await db.get(CT, task_id)
                if task and task.status == "running":
                    task.status = "pending"
                    task.error_message = f"Timeout after {TASK_TIMEOUT}s"
                    await db.commit()
        except Exception:
            pass
        return False
    except Exception as e:
        log.warning(f"  ❌ {tid_short}: {str(e)[:80]}")
        return False


async def main():
    ap = ArgumentParser()
    ap.add_argument("--concurrent", type=int, default=DEFAULT_CONCURRENCY)
    ap.add_argument("--batch", type=int, default=0, help="Stop after N tasks (0=all)")
    args = ap.parse_args()

    from app.database import async_session_factory
    from app.models.novel import Novel
    from sqlalchemy import select
    from app.services.queue_lock import acquire_queue_lock, release_queue_lock

    # Acquire DB-backed distributed lock
    lock_held = await acquire_queue_lock()
    if not lock_held:
        log.warning("Another queue processor holds the lock — exiting")
        return

    sem = asyncio.Semaphore(args.concurrent)
    completed = 0; failed = 0; total_processed = 0
    start_time = time.monotonic()
    batch_limit = args.batch

    log.info(f"Queue runner started (concurrent={args.concurrent}, lock=acquired)")

    try:
        while True:
            async with async_session_factory() as db:
                remaining = await count_pending(db)
                if remaining == 0:
                    log.info("All tasks completed!")
                    break

                batch_size = min(args.concurrent * 2, remaining)
                tasks = await fetch_pending_batch(db, batch_size)
                if not tasks:
                    await asyncio.sleep(0.5)
                    continue

                novel_ids = [t.novel_id for t in tasks]
                novel_rows = (await db.execute(select(Novel.id, Novel.title).where(Novel.id.in_(novel_ids)))).all()
                title_map = {r[0]: r[1] for r in novel_rows}

            async def worker(task):
                nonlocal completed, failed, total_processed
                async with sem:
                    tid = str(task.id)
                    title = title_map.get(task.novel_id, "?")[:30]
                    ok = await process_one(tid, title, remaining)
                    if ok: completed += 1
                    else: failed += 1
                    total_processed += 1

            await asyncio.gather(*[worker(t) for t in tasks])

            elapsed = time.monotonic() - start_time
            rate = total_processed / elapsed if elapsed > 0 else 0
            now_remaining = await count_pending(async_session_factory)
            eta_min = (now_remaining / rate) / 60 if rate > 0 and now_remaining > 0 else 0
            log.info(f"  📊 {completed} ok + {failed} fail = {total_processed} total "
                     f"| {rate:.1f}/s | pending={now_remaining} | ETA={eta_min:.0f}min")

            if batch_limit and total_processed >= batch_limit:
                log.info(f"Batch limit {batch_limit} reached")
                break
            await asyncio.sleep(0.1)

        total_time = time.monotonic() - start_time
        log.info(f"Queue runner stopped. {completed} ok, {failed} fail in {total_time:.0f}s")
    finally:
        await release_queue_lock()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    asyncio.run(main())
