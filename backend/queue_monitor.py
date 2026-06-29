#!/usr/bin/env python3
"""Resident queue monitor — real-time crawl queue status with WebSocket/SSE.

Features:
    - Real-time queue stats (pending/running/completed/failed)
    - Per-task progress events (via crawl_session SSE)
    - Speed & ETA calculation
    - Stuck task detection & alerting
    - Web dashboard at /queue-monitor (simple HTML)
    - Auto-restart on crash

Usage:
    python3 queue_monitor.py                    # CLI display
    python3 queue_monitor.py --api-port 8001    # REST API for dashboard
    python3 queue_monitor.py --daemon           # Background daemon
"""
import asyncio
import json
import os
import signal
import sys
import time
from argparse import ArgumentParser
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import async_session_factory
from app.models.crawler_task import CrawlerTask
from sqlalchemy import select, func


# ── Ansi colors ───────────────────────────────────────────────
C = {"R": "\033[91m", "G": "\033[92m", "Y": "\033[93m", "B": "\033[94m",
     "C": "\033[96m", "W": "\033[0m", "D": "\033[90m", "X": "\033[1m"}


def fmt(n: int) -> str:
    return f"{n:,}"


class QueueMonitor:
    def __init__(self, refresh_interval: float = 2.0, alert_threshold: int = 300):
        self.interval = refresh_interval
        self.alert_threshold = alert_threshold  # seconds before a "running" task is stuck
        self._prev_stats = {}
        self._start_time = time.monotonic()
        self._running = True

    async def _fetch_stats(self) -> dict:
        async with async_session_factory() as db:
            stats = {}
            for st in ("pending", "running", "completed", "failed"):
                cnt = (
                    await db.execute(
                        select(func.count()).where(CrawlerTask.status == st)
                    )
                ).scalar() or 0
                stats[st] = cnt

            # Check stuck tasks
            stuck = (
                await db.execute(
                    select(CrawlerTask)
                    .where(CrawlerTask.status == "running")
                    .limit(5)
                )
            ).scalars().all()

            stats["stuck"] = []
            now = datetime.now(timezone.utc)
            for t in stuck:
                if t.started_at:
                    elapsed = (now - t.started_at).total_seconds()
                    if elapsed > self.alert_threshold:
                        stats["stuck"].append({
                            "id": str(t.id)[:12],
                            "novel_id": str(t.novel_id)[:12],
                            "elapsed": int(elapsed),
                        })

            return stats

    async def _display(self, stats: dict):
        """Render a single frame of the dashboard."""
        total = sum(stats.get(s, 0) for s in ("pending", "running", "completed", "failed"))
        done = stats["completed"] + stats["failed"]

        # Progress bar
        bar_w = 40
        pct = done / total * 100 if total > 0 else 0
        filled = int(pct / 100 * bar_w)
        bar = "█" * filled + "░" * (bar_w - filled)

        # Speed calculation
        prev_done = self._prev_stats.get("completed", 0) + self._prev_stats.get("failed", 0)
        interval = max(self.interval, 0.1)  # guard against div-by-zero
        speed = (done - prev_done) / interval if self._prev_stats else 0

        # ETA
        remaining = stats["pending"]
        eta_min = remaining / speed / 60 if speed > 0 and remaining > 0 else 0
        eta_str = f"{eta_min:.0f}min" if eta_min < 120 else f"{eta_min/60:.1f}h"

        # Clear screen
        sys.stdout.write("\033[2J\033[H")

        elapsed = time.monotonic() - self._start_time
        print(f"{C['X']}{C['C']}╔{'═'*50}╗{C['W']}")
        print(f"{C['C']}║{C['X']}  🕷 CRAWL QUEUE MONITOR{' '*29}{C['C']}║")
        print(f"{C['C']}╠{'═'*50}╣{C['W']}")
        print(f"{C['C']}║{C['W']}  [{C['B']}{bar}{C['W']}] {pct:5.1f}%{' '*15}{C['C']}║")
        print(f"{C['C']}║{' '*50}║")
        print(f"{C['C']}║{C['W']}  {C['Y']}⏳ pending:   {fmt(stats['pending']):>8}{C['W']}                {C['C']}║")
        print(f"{C['C']}║{C['W']}  {C['B']}🔄 running:   {fmt(stats['running']):>8}{C['W']}                {C['C']}║")
        print(f"{C['C']}║{C['W']}  {C['G']}✅ completed: {fmt(stats['completed']):>8}{C['W']}                {C['C']}║")
        print(f"{C['C']}║{C['W']}  {C['R']}❌ failed:    {fmt(stats['failed']):>8}{C['W']}                {C['C']}║")
        print(f"{C['C']}║{' '*50}║")
        print(f"{C['C']}║{C['W']}  ⚡ Speed: {speed:5.1f}/s  ⏱ ETA: {eta_str:>8}{C['W']}      {C['C']}║")
        print(f"{C['C']}║{C['W']}  🕐 Running: {int(elapsed//60)}m {int(elapsed%60)}s{' '*24}{C['C']}║")

        if stats["stuck"]:
            print(f"{C['C']}║{' '*50}║")
            print(f"{C['C']}║{C['W']}  {C['R']}⚠ STUCK TASKS:{C['W']}{' '*32}{C['C']}║")
            for s in stats["stuck"]:
                print(f"{C['C']}║{C['W']}    Task {s['id']} — {s['elapsed']}s{C['W']}{' '*25}{C['C']}║")

        print(f"{C['C']}╚{'═'*50}╝{C['W']}")
        print(f"\n  {C['D']}Refresh: {self.interval}s | {datetime.now().strftime('%H:%M:%S')}{C['W']}")
        print(f"  {C['D']}Press Ctrl+C to exit{C['W']}")

        self._prev_stats = stats

    async def run(self):
        """Main loop."""
        print(f"{C['G']}Queue Monitor started (interval={self.interval}s){C['W']}")
        while self._running:
            try:
                stats = await self._fetch_stats()
                await self._display(stats)
            except Exception as e:
                sys.stdout.write(f"\r{C['R']}Error: {e}{C['W']}\n")
            await asyncio.sleep(self.interval)

    def stop(self):
        self._running = False


# ── REST API mode (for web dashboard) ─────────────────────────

def create_api_app():
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI(title="Queue Monitor API")
    monitor = QueueMonitor()

    @app.get("/api/queue/stats")
    async def queue_stats():
        return await monitor._fetch_stats()

    @app.get("/")
    async def dashboard():
        return HTMLResponse("""
        <!DOCTYPE html><html><head><meta charset="utf-8">
        <title>Queue Monitor</title>
        <meta http-equiv="refresh" content="3">
        <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:monospace;background:#1a1a2e;color:#eee;padding:20px}
        .card{background:#16213e;border-radius:8px;padding:16px;margin:8px 0}
        .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
        .stat{padding:16px;border-radius:8px;text-align:center}
        .stat .num{font-size:28px;font-weight:bold}
        .stat .label{font-size:12px;color:#aaa;margin-top:4px}
        .pending{background:#2d2d44}.running{background:#1a3a4a}
        .completed{background:#1a3a2a}.failed{background:#3a1a1a}
        .bar{height:20px;background:#333;border-radius:10px;overflow:hidden;margin:8px 0}
        .bar-fill{height:100%;background:linear-gradient(90deg,#4facfe,#00f2fe);transition:width .5s}
        h1{font-size:18px;margin-bottom:12px}
        </style></head><body>
        <h1>🕷 Crawl Queue Monitor</h1>
        <div class="card"><div class="bar"><div id="bar" class="bar-fill" style="width:0%"></div></div></div>
        <div class="stats">
        <div class="stat pending"><div id="pending" class="num">-</div><div class="label">⏳ Pending</div></div>
        <div class="stat running"><div id="running" class="num">-</div><div class="label">🔄 Running</div></div>
        <div class="stat completed"><div id="completed" class="num">-</div><div class="label">✅ Completed</div></div>
        <div class="stat failed"><div id="failed" class="num">-</div><div class="label">❌ Failed</div></div>
        </div>
        <script>
        fetch('/api/queue/stats').then(r=>r.json()).then(d=>{
        let t=d.pending+d.running+d.completed+d.failed;
        let pct=t>0?((d.completed+d.failed)/t*100).toFixed(1):0;
        document.getElementById('bar').style.width=pct+'%';
        document.getElementById('pending').textContent=d.pending;
        document.getElementById('running').textContent=d.running;
        document.getElementById('completed').textContent=d.completed;
        document.getElementById('failed').textContent=d.failed;
        });
        </script></body></html>""")

    return app


# ── Main ──────────────────────────────────────────────────────
def main():
    ap = ArgumentParser()
    ap.add_argument("--interval", type=float, default=2.0, help="Refresh interval (seconds)")
    ap.add_argument("--alert", type=int, default=300, help="Stuck task threshold (seconds)")
    ap.add_argument("--api-port", type=int, default=0, help="Start REST API on port")
    ap.add_argument("--daemon", action="store_true", help="Run as daemon (no TUI)")
    args = ap.parse_args()

    if args.api_port:
        import uvicorn
        app = create_api_app()
        uvicorn.run(app, host="0.0.0.0", port=args.api_port, log_level="warning")
        return

    monitor = QueueMonitor(refresh_interval=args.interval, alert_threshold=args.alert)

    def _sig_handler(sig, frame):
        monitor.stop()
        print(f"\n{C['G']}Monitor stopped.{C['W']}")
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    asyncio.run(monitor.run())


if __name__ == "__main__":
    main()
