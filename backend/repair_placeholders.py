#!/usr/bin/env python3
"""Repair novels with placeholder titles (Book-XXXX → real title).

High-concurrency version — fetches 30 titles in parallel for fast bulk repair.

Usage:
    python3 repair_placeholders.py                    # dry run (show count only)
    python3 repair_placeholders.py --fix              # fix ALL (30 concurrent)
    python3 repair_placeholders.py --fix --limit 100  # fix first 100 only
    python3 repair_placeholders.py --fix --novel-id <uuid>  # fix one
"""
import asyncio
import os
import re
import sys
import logging
import time
from argparse import ArgumentParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("repair")

# ---------------------------------------------------------------------------
# Title extraction (uses httpx pool, no SmartClient needed for bulk)
# ---------------------------------------------------------------------------

TITLE_EXTRACT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# Titles that indicate an error/404 page rather than a real book
BAD_TITLE_MARKERS = [
    "出现错误", "错误页面", "404", "页面不存在", "Not Found",
    "找不到", "已删除", "已下架", "不存在",
]
BAD_TITLE_EXACT = {
    "铅笔小说", "23qb", "23qb.net", "笔趣阁", "小说大全",
    "全本小说网", "趣读小说", "提子小说网", "香书中文",
    "铅笔小说-免费网络小说阅读网",
}


def extract_title(html: str, url: str) -> str:
    """Extract the real novel title from a book page HTML. Returns '' if not found."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    title = ""

    # Strategy 1: og:novel:book_name meta (23qb-specific, most reliable)
    meta = soup.select_one('meta[property="og:novel:book_name"]')
    if meta:
        title = (meta.get("content") or "").strip()

    # Strategy 2: <title> tag with suffix removal
    if not title:
        tag = soup.select_one("title")
        if tag:
            raw = tag.get_text(strip=True)
            for sep in (" - ", " | ", " — ", "・", "·", "_"):
                if sep in raw:
                    raw = raw.rsplit(sep, 1)[0].strip()
            if 1 < len(raw) < 100:
                title = raw

    # Strategy 3: h1 / .page-title
    if not title:
        for sel in ("h1", ".page-title", ".novel-title", ".book-title", ".module-title"):
            el = soup.select_one(sel)
            if el:
                txt = el.get_text(strip=True)
                if 1 < len(txt) < 80:
                    title = txt
                    break

    # Strategy 4: og:title meta
    if not title:
        meta = soup.select_one('meta[property="og:title"]')
        if meta:
            title = (meta.get("content") or "").strip()

    # Validate title quality
    if not title or len(title) < 2 or len(title) > 80:
        return ""

    # Reject error/noise titles
    title_lower = title.lower()
    for marker in BAD_TITLE_MARKERS:
        if marker.lower() in title_lower:
            return ""
    if title in BAD_TITLE_EXACT:
        return ""

    # Reject titles that are just numbers / placeholder patterns
    if re.match(r"^(Book-|Chapter-)\d+$", title):
        return ""
    if re.match(r"^\d+$", title):
        return ""

    # Normalize whitespace
    title = re.sub(r"\s+", " ", title).strip()

    return title


# ---------------------------------------------------------------------------
# High-concurrency repair
# ---------------------------------------------------------------------------

async def repair_batch(
    novels: list,
    concurrency: int = 30,
    commit_every: int = 200,
    session_factory=None,
) -> dict:
    """Fetch titles for *novels* concurrently and update DB.

    Returns stats dict: {total, fixed, failed, skipped, elapsed_s}
    """
    import httpx
    from sqlalchemy import update
    from app.models.novel import Novel

    sem = asyncio.Semaphore(concurrency)
    stats = {"total": len(novels), "fixed": 0, "failed": 0, "skipped": 0}
    # Collect (novel_id, new_title) pairs
    updates: list[tuple[str, str]] = []
    start = time.monotonic()
    done = 0

    async def fetch_one(novel) -> tuple:
        nonlocal done
        async with sem:
            if not novel.source_url:
                return (novel.id, novel.title, "")

            try:
                async with httpx.AsyncClient(
                    timeout=15, follow_redirects=True, headers=TITLE_EXTRACT_HEADERS
                ) as client:
                    resp = await client.get(novel.source_url)
                    resp.raise_for_status()
                    title = extract_title(resp.text, novel.source_url)
            except Exception:
                return (novel.id, novel.title, "__FAIL__")

            return (novel.id, novel.title, title)

    # Fire all concurrently
    tasks = [fetch_one(n) for n in novels]
    results = await asyncio.gather(*tasks)

    for nid, old_title, new_title in results:
        if new_title == "__FAIL__":
            stats["failed"] += 1
        elif not new_title or new_title == old_title or new_title.startswith("Book-"):
            stats["skipped"] += 1
        else:
            updates.append((nid, new_title))
            stats["fixed"] += 1

    # Batch commit to DB
    if updates and session_factory:
        async with session_factory() as db:
            for nid, new_title in updates:
                await db.execute(
                    update(Novel).where(Novel.id == nid).values(title=new_title)
                )
            await db.commit()

    stats["elapsed_s"] = round(time.monotonic() - start, 1)
    stats["rate"] = round(stats["total"] / stats["elapsed_s"], 1) if stats["elapsed_s"] > 0 else 0
    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    ap = ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="Actually update database")
    ap.add_argument("--limit", type=int, default=0, help="Max novels to process (0=all)")
    ap.add_argument("--novel-id", type=str, help="Fix a single novel by ID")
    ap.add_argument("--concurrency", type=int, default=30, help="Concurrent fetches (default 30)")
    ap.add_argument("--batch-size", type=int, default=500, help="Commit every N fixes (default 500)")
    args = ap.parse_args()

    from app.database import async_session_factory
    from app.models.novel import Novel
    from sqlalchemy import select

    # Query
    async with async_session_factory() as db:
        q = select(Novel)
        if args.novel_id:
            q = q.where(Novel.id == args.novel_id)
        else:
            q = q.where(
                (Novel.title.startswith("Book-")) |
                (Novel.title.startswith("Chapter-"))
            )
        if args.limit > 0:
            q = q.limit(args.limit)

        result = await db.execute(q)
        novels = result.scalars().all()

        if not novels:
            log.info("No placeholder novels found!")
            return

        log.info(f"Found {len(novels)} novels with placeholder titles")

        if not args.fix:
            # Show a sample
            for n in novels[:5]:
                bid = re.search(r"/book/(\d+)", n.source_url or "")
                log.info(f"  {n.title}  →  {n.source_url or 'no url'}  (bid={bid.group(1) if bid else '?'})")
            if len(novels) > 5:
                log.info(f"  ... and {len(novels) - 5} more")
            log.info(f"\nDRY RUN — use --fix to apply changes")
            return

    # Process in batches
    total_stats = {"total": len(novels), "fixed": 0, "failed": 0, "skipped": 0}
    batch_count = 0

    for i in range(0, len(novels), args.batch_size):
        batch = novels[i : i + args.batch_size]
        batch_count += 1
        log.info(
            f"Batch {batch_count}: {i+1}-{min(i+args.batch_size, len(novels))}/{len(novels)} "
            f"({len(batch)} novels, {args.concurrency} concurrent)"
        )

        stats = await repair_batch(
            batch,
            concurrency=args.concurrency,
            session_factory=async_session_factory,
        )

        total_stats["fixed"] += stats["fixed"]
        total_stats["failed"] += stats["failed"]
        total_stats["skipped"] += stats["skipped"]

        remaining = len(novels) - (i + len(batch))
        overall_rate = (
            round(total_stats["fixed"] / (time.monotonic() - (time.monotonic() - stats["elapsed_s"] * batch_count)), 1)
            if batch_count > 0
            else stats["rate"]
        )
        eta_min = round(remaining / stats["rate"] / 60, 1) if stats["rate"] > 0 and remaining > 0 else 0

        log.info(
            f"  ✅ {stats['fixed']} fixed, ⏭ {stats['skipped']} skipped, "
            f"❌ {stats['failed']} failed  |  {stats['rate']}/s"
            + (f"  |  ETA {eta_min}min" if eta_min > 0 else "")
        )

        if remaining > 0:
            await asyncio.sleep(0.5)  # tiny breather between batches

    total_elapsed = round(time.monotonic() - (time.monotonic() - stats["elapsed_s"]), 1)
    log.info(
        f"\n{'='*60}\n"
        f"  DONE! {total_stats['fixed']} fixed, {total_stats['skipped']} skipped, "
        f"{total_stats['failed']} failed (out of {total_stats['total']})\n"
        f"  Total time: {total_elapsed:.0f}s\n"
        f"{'='*60}"
    )


if __name__ == "__main__":
    import signal

    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    asyncio.run(main())
