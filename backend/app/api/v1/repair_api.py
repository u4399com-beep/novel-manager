"""Repair API — fix empty chapters, missing covers, incomplete novel info."""

import asyncio, logging, os, subprocess, sys
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/repair", tags=["Repair"])

log = logging.getLogger("repair_api")
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
_repair_tasks: dict[str, subprocess.Popen] = {}


def _is_running(name: str) -> bool:
    p = _repair_tasks.get(name)
    return p is not None and p.poll() is None


@router.get("/status")
async def repair_status(current_user: User = Depends(get_current_user)):
    """Get repair statuses + counts."""
    from app.database import async_session_factory
    from app.models.novel import Novel
    from app.models.chapter import Chapter
    from sqlalchemy import select, func, and_

    async with async_session_factory() as db:
        # Empty chapters
        empty_ch = (await db.execute(
            select(func.count()).where(and_(Chapter.content == None, Chapter.content_file == None))
        )).scalar() or 0

        # No cover
        no_cover = (await db.execute(
            select(func.count()).where((Novel.cover_image_url == None) | (Novel.cover_image_url == ''))
        )).scalar() or 0

        # No description or author
        no_desc = (await db.execute(
            select(func.count()).where((Novel.description == None) | (Novel.description == ''))
        )).scalar() or 0

        no_author = (await db.execute(
            select(func.count()).where((Novel.author == None) | (Novel.author == ''))
        )).scalar() or 0

        total = (await db.execute(select(func.count()).select_from(Novel))).scalar() or 1

    return {
        "empty_chapters": empty_ch,
        "no_cover": no_cover,
        "no_description": no_desc,
        "no_author": no_author,
        "total_novels": total,
        "tasks_running": {
            "repair_chapters": _is_running("chapters"),
            "repair_covers": _is_running("covers"),
            "repair_info": _is_running("info"),
        },
    }


@router.post("/chapters")
async def start_repair_chapters(current_user: User = Depends(get_current_user)):
    """Start empty chapter repair."""
    if _is_running("chapters"):
        return {"message": "Already running", "success": False}

    script = os.path.join(BACKEND_DIR, "repair_empty_chapters.py")
    p = subprocess.Popen(
        [sys.executable, script],
        stdout=open("/tmp/repair_chapters.log", "a"), stderr=subprocess.STDOUT,
        cwd=BACKEND_DIR,
    )
    _repair_tasks["chapters"] = p
    return {"message": "Chapter repair started", "success": True, "log": "/tmp/repair_chapters.log"}


@router.post("/chapters/stop")
async def stop_repair_chapters(current_user: User = Depends(get_current_user)):
    """Stop chapter repair."""
    p = _repair_tasks.get("chapters")
    if p and p.poll() is None:
        p.terminate()
        return {"message": "Stopped", "success": True}
    return {"message": "Not running", "success": False}


@router.post("/covers")
async def start_repair_covers(current_user: User = Depends(get_current_user)):
    """Start cover image repair."""
    if _is_running("covers"):
        return {"message": "Already running", "success": False}

    script = os.path.join(BACKEND_DIR, "repair_covers.py")
    p = subprocess.Popen(
        [sys.executable, script],
        stdout=open("/tmp/repair_covers.log", "a"), stderr=subprocess.STDOUT,
        cwd=BACKEND_DIR,
    )
    _repair_tasks["covers"] = p
    return {"message": "Cover repair started", "success": True, "log": "/tmp/repair_covers.log"}


@router.post("/covers/stop")
async def stop_repair_covers(current_user: User = Depends(get_current_user)):
    """Stop cover repair."""
    p = _repair_tasks.get("covers")
    if p and p.poll() is None:
        p.terminate()
        return {"message": "Stopped", "success": True}
    return {"message": "Not running", "success": False}


@router.post("/info")
async def start_repair_info(batch_size: int = 100, current_user: User = Depends(get_current_user)):
    """Repair missing novel info (author, description) from source site."""
    if _is_running("info"):
        return {"message": "Already running", "success": False}

    async def repair():
        from app.database import async_session_factory
        from app.models.novel import Novel
        from app.crawlers.registry import get_crawler
        from sqlalchemy import select
        import httpx
        from bs4 import BeautifulSoup
        log_inner = logging.getLogger("repair_info")

        async with async_session_factory() as db:
            novels = (await db.execute(
                select(Novel).where(
                    ((Novel.author == None) | (Novel.author == '') | (Novel.description == None) | (Novel.description == '')),
                    Novel.source_url != None, Novel.source_url != ''
                ).limit(batch_size)
            )).scalars().all()

            if not novels:
                return

            crawler = get_crawler("23qb")
            fixed = 0
            for novel in novels:
                try:
                    info = await crawler.get_novel_info(novel.source_url)
                    changed = False
                    if info.get("author") and not novel.author:
                        novel.author = info["author"]; changed = True
                    if info.get("description") and not novel.description:
                        novel.description = info["description"][:2000]; changed = True
                    if changed:
                        fixed += 1
                except Exception:
                    pass
            if fixed:
                await db.commit()
            log_inner.info(f"Fixed {fixed}/{len(novels)} novel info")

    asyncio.create_task(repair())
    _repair_tasks["info"] = True  # mark as running
    return {"message": f"Novel info repair started ({batch_size} books)", "success": True}


@router.post("/info/stop")
async def stop_repair_info(current_user: User = Depends(get_current_user)):
    """Stop info repair."""
    if "info" in _repair_tasks:
        del _repair_tasks["info"]
        return {"message": "Stopped", "success": True}
    return {"message": "Not running", "success": False}


@router.get("/logs/{task}")
async def repair_logs(task: str, lines: int = 30, current_user: User = Depends(get_current_user)):
    """Get repair task logs."""
    log_files = {
        "chapters": "/tmp/repair_chapters.log",
        "covers": "/tmp/repair_covers.log",
        "info": "/tmp/repair_info.log",
    }
    path = log_files.get(task, f"/tmp/repair_{task}.log")
    try:
        with open(path) as f:
            all_lines = f.readlines()
            return {"lines": [l.strip() for l in all_lines[-lines:]]}
    except:
        return {"lines": []}
