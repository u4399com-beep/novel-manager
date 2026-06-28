"""Watchdog + Queue monitoring API endpoints."""
import subprocess, os, sys
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/watchdog", tags=["Watchdog"])

QUEUE_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "queue_runner.py")


@router.get("/status")
async def watchdog_status(current_user: User = Depends(get_current_user)):
    """Get queue + watchdog status."""
    from app.database import async_session_factory
    from app.models.crawler_task import CrawlerTask
    from app.models.chapter import Chapter
    from sqlalchemy import select, func, and_
    from datetime import datetime, timezone, timedelta

    async with async_session_factory() as db:
        # Queue stats
        stats = {}
        for st in ("pending", "running", "completed", "failed"):
            stats[st] = int((await db.execute(
                select(func.count()).where(CrawlerTask.status == st)
            )).scalar() or 0)

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=600)
        stuck = int((await db.execute(
            select(func.count()).where(CrawlerTask.status == "running", CrawlerTask.started_at < cutoff)
        )).scalar() or 0)

        empty = int((await db.execute(
            select(func.count()).where(and_(Chapter.content == None, Chapter.content_file == None))
        )).scalar() or 0)

        # Runner alive
        try:
            r = subprocess.run(["pgrep", "-f", "queue_runner.py"], capture_output=True, text=True, timeout=3)
            runner_alive = bool(r.stdout.strip())
        except:
            runner_alive = False

        # Watchdog alive
        try:
            r = subprocess.run(["pgrep", "-f", "queue_watchdog.py"], capture_output=True, text=True, timeout=3)
            watchdog_alive = bool(r.stdout.strip())
        except:
            watchdog_alive = False

        total = sum(stats.values())
        done = stats["completed"] + stats["failed"]
        pct = done / total * 100 if total > 0 else 0

        return {
            "queue": {
                "pending": stats["pending"],
                "running": stats["running"],
                "completed": stats["completed"],
                "failed": stats["failed"],
                "total": total,
                "progress": round(pct, 1),
                "stuck": stuck,
            },
            "empty_chapters": empty,
            "runner_alive": runner_alive,
            "watchdog_alive": watchdog_alive,
        }


@router.post("/restart")
async def restart_queue(current_user: User = Depends(get_current_user)):
    """Force restart the queue runner."""
    try:
        subprocess.run(["pkill", "-9", "-f", "queue_runner.py"], capture_output=True)
        subprocess.Popen(
            [sys.executable, QUEUE_SCRIPT, "--concurrent", "8"],
            stdout=open("/tmp/queue_runner.log", "a"),
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(QUEUE_SCRIPT),
        )
        return {"message": "Queue runner restarted", "success": True}
    except Exception as e:
        return {"message": str(e), "success": False}


@router.post("/restart-watchdog")
async def restart_watchdog(current_user: User = Depends(get_current_user)):
    """Force restart the watchdog."""
    import signal
    try:
        subprocess.run(["pkill", "-9", "-f", "queue_watchdog.py"], capture_output=True)
        watchdog_script = os.path.join(os.path.dirname(QUEUE_SCRIPT), "queue_watchdog.py")
        subprocess.Popen(
            [sys.executable, watchdog_script],
            stdout=open("/tmp/watchdog.log", "a"),
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(QUEUE_SCRIPT),
        )
        return {"message": "Watchdog restarted", "success": True}
    except Exception as e:
        return {"message": str(e), "success": False}


@router.get("/logs/queue")
async def queue_logs(lines: int = 20, current_user: User = Depends(get_current_user)):
    """Get recent queue runner logs."""
    try:
        with open("/tmp/queue_runner.log") as f:
            all_lines = f.readlines()
            return {"lines": [l.strip() for l in all_lines[-lines:]]}
    except:
        return {"lines": []}


@router.get("/logs/watchdog")
async def watchdog_logs(lines: int = 20, current_user: User = Depends(get_current_user)):
    """Get recent watchdog logs."""
    try:
        with open("/tmp/watchdog.log") as f:
            all_lines = f.readlines()
            return {"lines": [l.strip() for l in all_lines[-lines:]]}
    except:
        return {"lines": []}
