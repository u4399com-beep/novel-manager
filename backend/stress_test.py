#!/usr/bin/env python3
"""
Stress test: 1000 sites × 10 concurrent crawls × simulated traffic.

Scenario:
  - 1000 domains (24 languages, ~42 sites per language)
  - 10 concurrent crawl tasks
  - Simulated traffic: up to 3500 concurrent requests
  - Measures: response time (avg/P50/P99), error rate, throughput (req/s), DB perf

Usage:
  python3 stress_test.py                    # Quick test (50 sites, 500 req)
  python3 stress_test.py --full             # Full test (1000 sites, 10k req)
  python3 stress_test.py --sites 100 --req 2000 --concurrent 100
"""
import asyncio
import json
import os
import random
import sys
import time
from argparse import ArgumentParser
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx
from sqlalchemy import select, func, text

from app.database import async_session_factory
from app.models.site import Site
from app.models.novel import Novel
from app.models.crawler_task import CrawlerTask
from app.models.chapter import Chapter

# ── Config ──────────────────────────────────────────────────
LANGUAGES = [
    "zh","zh-TW","en","ja","ko","fr","de","es","pt","ru",
    "ar","th","vi","id","it","tr","hi","ms","tl","sw","fa","ur","bn","my",
]

PAGES = [
    ("/", "home"),
    ("/novels", "library"),
    ("/novels?category=1", "category"),
    ("/search?q=test", "search"),
]

# ── Color helpers ───────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def banner(title: str):
    print(f"\n{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{CYAN}{'='*60}{RESET}")


# ── Phase 1: Create test sites ──────────────────────────────
async def create_test_sites(count: int, base_url: str):
    """Create *count* test sites with randomized configs, return list of domains."""
    banner(f"Phase 1: Creating {count} test sites...")

    async with async_session_factory() as db:
        # Count existing
        existing = (await db.execute(select(func.count()).select_from(Site))).scalar()
        to_create = max(0, count - existing)

        if to_create == 0:
            result = await db.execute(select(Site.domain, Site.id, Site.language))
            sites = [(r[0], r[1], r[2]) for r in result.fetchall()]
            print(f"  {GREEN}✓{RESET} {count} sites already exist, skipping creation")
            return sites[:count]

        sites_data = []
        for i in range(to_create):
            lang = LANGUAGES[i % len(LANGUAGES)]
            domain = f"site{i + existing:04d}.{base_url}"
            sites_data.append({
                "domain": domain,
                "name": f"测试站{i + existing:04d}",
                "template": random.choice(["default","biquge","daquan","teezi","quanben5"]),
                "language": lang,
                "is_active": True,
                "description": f"Stress test site {i}",
                "offset": random.randint(0, 1000),
            })

        # Batch insert
        for data in sites_data:
            db.add(Site(**data))
        await db.commit()

        result = await db.execute(select(Site.domain, Site.id, Site.language))
        sites = [(r[0], r[1], r[2]) for r in result.fetchall()[:count]]

        print(f"  {GREEN}✓{RESET} Created {to_create} sites ({len(sites)} total)")
        return sites


# ── Phase 2: Concurrent crawl simulation ────────────────────
async def submit_crawl_tasks(count: int):
    """Submit *count* crawl tasks and start processing."""
    banner(f"Phase 2: Starting {count} concurrent crawl tasks...")

    async with async_session_factory() as db:
        novels = (await db.execute(select(Novel.id).limit(count))).scalars().all()
        if len(novels) < count:
            novels = list(novels) + [novels[0]] * (count - len(novels))

        tasks_created = 0
        for nid in novels[:count]:
            task = CrawlerTask(novel_id=nid, status="pending")
            db.add(task)
            tasks_created += 1
        await db.commit()

    print(f"  {GREEN}✓{RESET} Submitted {tasks_created} crawl tasks")

    # Start processing
    from app.services.crawler_service import run_crawl

    stats = {"completed": 0, "failed": 0, "total": tasks_created, "times": []}

    async def process_one(nid):
        async with async_session_factory() as db:
            task = CrawlerTask(novel_id=nid, status="pending")
            db.add(task)
            await db.flush()
            await db.refresh(task)

            t0 = time.monotonic()
            try:
                await asyncio.wait_for(
                    run_crawl(db, str(task.id), mode="direct"),
                    timeout=120,
                )
                stats["completed"] += 1
            except Exception:
                stats["failed"] += 1
            stats["times"].append(time.monotonic() - t0)

    # Run up to 10 concurrently
    sem = asyncio.Semaphore(10)
    async def limited(nid):
        async with sem:
            await process_one(nid)

    t0 = time.monotonic()
    await asyncio.gather(*[limited(nid) for nid in novels[:count]])
    elapsed = time.monotonic() - t0

    print(f"  Completed: {stats['completed']}, Failed: {stats['failed']}")
    print(f"  Time: {elapsed:.1f}s, Avg/task: {elapsed/count:.1f}s")
    return stats


# ── Phase 3: Traffic simulation ─────────────────────────────
async def traffic_simulation(
    sites: list, total_requests: int, concurrency: int, server_url: str
):
    """Simulate high-traffic load across all sites."""
    banner(
        f"Phase 3: Traffic simulation — {total_requests} requests @ {concurrency} concurrent"
    )

    # Pre-build request list
    requests = []
    novel_pool = None

    async with async_session_factory() as db:
        novel_rows = (await db.execute(select(Novel.id).limit(500))).scalars().all()
        novel_pool = list(novel_rows)

    for i in range(total_requests):
        site_domain, site_id, lang = random.choice(sites)
        page_path, page_type = random.choice(PAGES)

        if page_type in ("home", "category", "library", "search"):
            url = f"{server_url}{page_path}"
        else:
            nid = random.choice(novel_pool) if novel_pool else "n1"
            url = f"{server_url}/novel/{nid}"

        requests.append((url, site_domain, site_id, page_type, i))

    # Run with controlled concurrency
    sem = asyncio.Semaphore(concurrency)
    results = {
        "total": total_requests,
        "success": 0,
        "error": 0,
        "times": [],
        "status_codes": defaultdict(int),
        "errors_by_type": defaultdict(int),
        "by_page": defaultdict(lambda: {"count": 0, "times": [], "errors": 0}),
    }

    t0 = time.monotonic()
    progress_interval = max(1, total_requests // 20)  # 20 progress updates

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        async def do_request(req_data, idx):
            url, domain, site_id, page_type, req_id = req_data
            async with sem:
                t_req = time.monotonic()
                try:
                    resp = await client.get(
                        url,
                        headers={
                            "Host": domain,
                            "User-Agent": random.choice([
                                "Mozilla/5.0 (Windows NT 10.0) Chrome/130.0.0.0",
                                "Mozilla/5.0 (Macintosh) Safari/605.1.15",
                                "Mozilla/5.0 (X11; Linux) Firefox/132.0",
                                "Mozilla/5.0 (iPhone) Mobile/15E148",
                            ]),
                            "Accept-Language": random.choice([
                                "zh-CN,zh;q=0.9", "en-US,en;q=0.9", "ja;q=0.9",
                            ]),
                        },
                    )
                    elapsed_req = time.monotonic() - t_req
                    results["success"] += 1
                    results["times"].append(elapsed_req)
                    results["status_codes"][resp.status_code] += 1
                    results["by_page"][page_type]["count"] += 1
                    results["by_page"][page_type]["times"].append(elapsed_req)
                except Exception as e:
                    elapsed_req = time.monotonic() - t_req
                    results["error"] += 1
                    results["times"].append(elapsed_req)
                    results["errors_by_type"][type(e).__name__] += 1
                    results["by_page"][page_type]["errors"] += 1

                if idx % progress_interval == 0:
                    pct = idx / total_requests * 100
                    elapsed = time.monotonic() - t0
                    rps = idx / elapsed if elapsed > 0 else 0
                    print(
                        f"  [{pct:5.1f}%] {idx}/{total_requests} "
                        f"| {rps:.0f} req/s | err={results['error']}"
                    )

        tasks = [do_request(req, i) for i, req in enumerate(requests)]
        await asyncio.gather(*tasks)

    total_time = time.monotonic() - t0
    return results, total_time


# ── Report ──────────────────────────────────────────────────
def print_report(results: dict, total_time: float, crawl_stats=None):
    banner("RESULTS")

    r = results
    t = results["times"]
    t_sorted = sorted(t)
    n = len(t_sorted)
    total = r["total"]

    print(f"\n{BOLD}📊 Throughput{RESET}")
    print(f"  Total requests:  {total:,}")
    print(f"  Success:         {GREEN}{r['success']:,}{RESET}")
    print(f"  Errors:          {RED}{r['error']:,}{RESET}")
    print(f"  Time:            {total_time:.1f}s")
    print(f"  Throughput:      {CYAN}{total / total_time:.0f} req/s{RESET}")

    print(f"\n{BOLD}⏱  Latency{RESET}")
    if t_sorted:
        print(f"  Min:     {t_sorted[0]*1000:.1f}ms")
        print(f"  Avg:     {sum(t)/n*1000:.1f}ms")
        print(f"  P50:     {t_sorted[n//2]*1000:.1f}ms")
        print(f"  P90:     {t_sorted[int(n*0.9)]*1000:.1f}ms")
        print(f"  P99:     {t_sorted[int(n*0.99)]*1000:.1f}ms")
        print(f"  Max:     {t_sorted[-1]*1000:.1f}ms")

    print(f"\n{BOLD}📄 By Page Type{RESET}")
    for pt, data in sorted(r["by_page"].items()):
        cnt = data["count"]
        t_pt = data["times"]
        avg = sum(t_pt) / len(t_pt) * 1000 if t_pt else 0
        err_rate = data["errors"] / cnt * 100 if cnt > 0 else 0
        print(
            f"  {pt:12s}  {cnt:6d} req  avg={avg:6.0f}ms  "
            f"err={err_rate:.1f}%"
        )

    print(f"\n{BOLD}📊 Scale Projection{RESET}")
    rps = total / total_time
    sites_count = 1000
    pv_per_site = 30_000_000  # 30M PV/day = 30× IP
    seconds_per_day = 86400
    needed_rps = (sites_count * pv_per_site) / seconds_per_day
    print(f"  1000 sites @ 30M PV/day each: {needed_rps:,.0f} req/s needed")
    print(f"  Test achieved:                 {rps:,.0f} req/s")
    ratio = rps / needed_rps * 100 if needed_rps > 0 else 0
    color = GREEN if ratio >= 10 else YELLOW if ratio >= 1 else RED
    print(f"  Coverage:                      {color}{ratio:.1f}%{RESET}")

    if crawl_stats:
        print(f"\n{BOLD}🕷 Crawl Tasks{RESET}")
        print(f"  Completed: {crawl_stats['completed']}")
        print(f"  Failed:    {crawl_stats['failed']}")
        print(f"  Avg time:  {sum(crawl_stats['times'])/len(crawl_stats['times']):.1f}s")


# ── Main ────────────────────────────────────────────────────
async def main():
    ap = ArgumentParser()
    ap.add_argument("--full", action="store_true", help="Full scale (1000 sites, 10k req, 100 concurrent)")
    ap.add_argument("--sites", type=int, default=100, help="Number of sites")
    ap.add_argument("--req", type=int, default=2000, help="Total HTTP requests")
    ap.add_argument("--concurrent", type=int, default=50, help="Concurrent requests")
    ap.add_argument("--crawl", type=int, default=5, help="Concurrent crawl tasks")
    ap.add_argument("--server", type=str, default="http://localhost:8000", help="Target server URL")
    ap.add_argument("--base-domain", type=str, default="test.local", help="Base domain for test sites")
    args = ap.parse_args()

    if args.full:
        args.sites = 1000
        args.req = 10000
        args.concurrent = 200
        args.crawl = 10

    print(f"{BOLD}{CYAN}")
    print("╔══════════════════════════════════════════════════╗")
    print("║       Novel Manager — STRESS TEST                ║")
    print("╠══════════════════════════════════════════════════╣")
    print(f"║  Sites:      {args.sites:>6}                              ║")
    print(f"║  Requests:   {args.req:>6}                              ║")
    print(f"║  Concurrent: {args.concurrent:>6}                              ║")
    print(f"║  Crawl tasks:{args.crawl:>6}                              ║")
    print(f"║  Server:     {args.server:<30s} ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"{RESET}")

    t0 = time.monotonic()

    # Phase 1: Sites
    sites = await create_test_sites(args.sites, args.base_domain)

    # Phase 2: Crawl
    crawl_stats = await submit_crawl_tasks(args.crawl)

    # Phase 3: Traffic
    results, traffic_time = await traffic_simulation(
        sites, args.req, args.concurrent, args.server
    )

    # Report
    print_report(results, traffic_time, crawl_stats)

    total_elapsed = time.monotonic() - t0
    print(f"\n{CYAN}Total test duration: {total_elapsed:.0f}s{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
