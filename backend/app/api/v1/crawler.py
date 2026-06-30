"""Crawler API — trigger, batch, search-match, monitor, manage."""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.crawlers.registry import list_sources
from app.database import get_db, async_session_factory
from app.models.user import User
from app.schemas.crawler import CrawlerSourceInfo, CrawlerTaskRead, CrawlerTrigger
from app.crawlers.page_extractor import extract_page_links, test_all_novels
from app.services import crawler_service
from app.models.crawler_task import CrawlerTask as CrawlerTaskModel
from app.services.crawl_session import stream_events
from app.services.novel_service import get_novel, create_novel
from app.schemas.novel import NovelCreate

router = APIRouter()

# Keep references to running background tasks so the GC doesn't cancel them
_running_tasks: set[asyncio.Task] = set()


# ---------------------------------------------------------------------------
# Extended schemas
# ---------------------------------------------------------------------------

class BatchTriggerRequest(BaseModel):
    novel_ids: list[str] = Field(min_length=1, max_length=50)
    source_name: Optional[str] = None
    mode: str = Field(default="direct", pattern="^(direct|search)$")


class SingleTriggerRequest(BaseModel):
    novel_id: str
    source_name: Optional[str] = None
    mode: str = Field(default="direct", pattern="^(direct|search)$")


class SearchPreviewRequest(BaseModel):
    novel_id: str
    source_name: str


class PagePreviewRequest(BaseModel):
    page_url: str
    source_name: Optional[str] = None
    page_from: int = Field(default=1, ge=1)
    page_to: int = Field(default=1, ge=1)
    selected_book_ids: Optional[list[str]] = None  # 只测试指定的小说


class PageTriggerRequest(BaseModel):
    page_url: str
    source_name: str
    selected_book_ids: Optional[list[str]] = Field(
        default=None,
        description="特定 book_id 列表；留空则全部导入并采集",
    )
    page_from: int = Field(default=1, ge=1)
    page_to: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

@router.get("/sources", response_model=list[CrawlerSourceInfo])
async def get_sources():
    return [
        CrawlerSourceInfo(
            source_name=s["source_name"],
            base_url=s["base_url"],
            description=s["description"],
        )
        for s in list_sources()
    ]


# ---------------------------------------------------------------------------
# Search-preview (no side-effects)
# ---------------------------------------------------------------------------

@router.post("/search-preview")
async def search_preview(
    data: SearchPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search the source site for a novel and preview match results.

    Does NOT modify any data — use this before triggering a
    ``mode=search`` crawl to see what would be matched.
    """
    result = await crawler_service.preview_search_match(
        db, data.novel_id, data.source_name
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Single trigger
# ---------------------------------------------------------------------------

@router.post("/trigger", response_model=CrawlerTaskRead, status_code=status.HTTP_202_ACCEPTED)
async def trigger_crawl(
    data: SingleTriggerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger a crawl for a single novel.

    - ``mode=direct`` — uses the novel's existing ``source_url``.
    - ``mode=search`` — searches the source site by novel title first,
      then crawls the best match.
    """
    novel = await get_novel(db, novel_id=data.novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    if data.mode == "search" and not novel.source_url:
        # Quick pre-check: can we find it?
        source = data.source_name or novel.source_name
        if not source:
            raise HTTPException(status_code=400, detail="No source_name configured")
        match = await crawler_service.auto_match_novel(novel, source)
        if not match:
            raise HTTPException(
                status_code=422,
                detail=f"在 {source} 搜索 '{novel.title}' 未找到匹配结果，请先手动设置 source_url",
            )

    task = await crawler_service.create_crawler_task(db, data.novel_id, data.source_name)
    from app.services.crawl_session import create_session
    create_session(str(task.id), novel.title)
    await db.commit()  # persist task before background execution
    # Run crawl asynchronously — don't block the HTTP response
    asyncio.create_task(_run_single_crawl(str(task.id), data.mode))
    return task


# ---------------------------------------------------------------------------
# Batch trigger
# ---------------------------------------------------------------------------

@router.post("/trigger-batch")
async def trigger_batch_crawl(
    data: BatchTriggerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue a batch crawl for multiple novels."""
    if not data.novel_ids:
        raise HTTPException(status_code=400, detail="novel_ids is empty")

    tasks: list[dict] = []
    for nid in data.novel_ids:
        novel = await get_novel(db, novel_id=nid)
        if not novel:
            continue
        task = await crawler_service.create_crawler_task(db, nid, data.source_name)
        tasks.append({"task_id": str(task.id), "novel_id": nid})

    await db.commit()
    task = asyncio.create_task(_run_batch_in_session(
        [t["task_id"] for t in tasks], data.mode,
    ))
    task.add_done_callback(lambda t: _running_tasks.discard(t))
    _running_tasks.add(task)

    return {
        "message": f"Batch queued: {len(tasks)} novels (mode={data.mode})",
        "tasks": tasks,
    }


# ---------------------------------------------------------------------------
# Page extraction & crawl
# ---------------------------------------------------------------------------

@router.post("/page-preview")
async def page_preview(
    data: PagePreviewRequest,
    current_user: User = Depends(get_current_user),
):
    """Fetch a source-site page and extract all novel/chapter links.

    Use this to preview what would be imported before calling
    ``/trigger-page``.
    """
    try:
        result = await extract_page_links(
            data.page_url, data.source_name,
            page_from=data.page_from, page_to=data.page_to,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"页面提取失败: {exc}")


@router.post("/page-test")
async def page_test(
    data: PagePreviewRequest,
    current_user: User = Depends(get_current_user),
):
    """Extract novels from a page and test catalog+chapter extraction for each.

    Returns each novel annotated with ``_test`` results. Only novels
    where ``_test.passed=True`` should be selected for import.
    """
    try:
        extracted = await extract_page_links(
            data.page_url, data.source_name,
            page_from=data.page_from, page_to=data.page_to,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"页面提取失败: {exc}")

    novels = extracted.get("novels", [])
    if not novels:
        raise HTTPException(status_code=422, detail="未找到小说链接")

    # Filter to selected books if specified
    if data.selected_book_ids:
        selected = set(data.selected_book_ids)
        novels = [n for n in novels if n.get("book_id") in selected]
    if not novels:
        raise HTTPException(status_code=422, detail="没有匹配的小说可测试")

    # Run catalog + chapter tests
    source = data.source_name or "23qb"
    await test_all_novels(novels, source)

    passed = sum(1 for n in novels if n.get("_test", {}).get("passed"))
    return {
        "page_url": data.page_url,
        "total": len(novels),
        "passed": passed,
        "failed": len(novels) - passed,
        "novels": novels,
    }


@router.post("/trigger-page")
async def trigger_page_crawl(
    data: PageTriggerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Extract novels from a page, import them, and queue crawl tasks.

    1. Fetches the page and extracts novel links.
    2. Creates ``Novel`` records for new books (skips duplicates by title).
    3. Queues crawl tasks for all imported novels.

    If ``selected_book_ids`` is provided, only those books are imported.
    """
    # 1. Extract
    try:
        extracted = await extract_page_links(
            data.page_url, data.source_name,
            page_from=data.page_from, page_to=data.page_to,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"页面提取失败: {exc}")

    novel_links = extracted.get("novels", [])
    if not novel_links:
        raise HTTPException(status_code=422, detail="页面上未找到小说链接")

    # Filter by selected IDs
    if data.selected_book_ids:
        selected_set = set(data.selected_book_ids)
        novel_links = [n for n in novel_links if n.get("book_id") in selected_set]

    # Auto-skip novels that failed pre-test (if test results exist)
    failed_ids = {n["book_id"] for n in novel_links if n.get("_test") and not n["_test"].get("passed")}
    if failed_ids:
        novel_links = [n for n in novel_links if n.get("book_id") not in failed_ids]

    if not novel_links:
        raise HTTPException(status_code=422, detail="没有通过测试的小说可导入")

    # 2. Import novels + queue tasks
    imported_count = 0
    skipped_count = 0
    task_ids: list[str] = []

    for n in novel_links:
        title = n.get("title", "").strip()
        book_id = n.get("book_id", "")
        url = n.get("url", "")

        if not title or not url:
            continue

        # Check if novel already exists by title
        from sqlalchemy import select as sa_select
        from app.models.novel import Novel as NovelModel
        existing = await db.execute(
            select(NovelModel).where(NovelModel.title == title).limit(1)
        )
        novel = existing.scalars().first()

        if novel:
            # Update missing fields
            if not novel.source_url:
                novel.source_url = url
                novel.source_name = data.source_name
            if not novel.cover_image_url and n.get("cover_url"):
                novel.cover_image_url = n["cover_url"]
            skipped_count += 1
        else:
            # Create new novel
            novel = NovelModel(
                title=title,
                author="",
                source_url=url,
                source_name=data.source_name,
                cover_image_url=n.get("cover_url", "") or "",
            )
            db.add(novel)
            imported_count += 1

            # Download cover image in background
            cover_url = n.get("cover_url", "")
            if cover_url:
                async def _download_cover(nid: str, curl: str):
                    try:
                        import httpx
                        async with httpx.AsyncClient(timeout=30) as http:
                            resp = await http.get(curl)
                            if resp.status_code == 200:
                                from app.database import async_session_factory
                                from app.services.novel_service import get_novel, save_cover_image
                                async with async_session_factory() as s:
                                    nv = await get_novel(s, nid)
                                    if nv and not nv.cover_image_url:
                                        fn = curl.rsplit("/", 1)[-1] or "cover.jpg"
                                        saved = await save_cover_image(nv, resp.content, fn)
                                        nv.cover_image_url = saved
                                        await s.flush()
                                        await s.commit()
                    except Exception as e:
                        _queue_log.debug(f"Cover download failed: {e}")
                cover_task = asyncio.create_task(_download_cover(str(novel.id), cover_url))
                cover_task.add_done_callback(lambda t: _running_tasks.discard(t))
                _running_tasks.add(cover_task)

        await db.flush()
        await db.refresh(novel)

        # Create pending crawl task
        task = await crawler_service.create_crawler_task(
            db, str(novel.id), data.source_name
        )
        task_ids.append(str(task.id))

    # 3. Commit + run sync
    await db.commit()
    for tid in task_ids:
        await crawler_service.run_crawl(db, tid, mode="direct")

    return {
        "message": f"导入 {imported_count} 本新书, 跳过 {skipped_count} 本已存在, 共 {len(task_ids)} 个采集任务",
        "imported": imported_count,
        "skipped": skipped_count,
        "task_ids": task_ids,
    }


# ---------------------------------------------------------------------------
# SSE real-time progress stream
# ---------------------------------------------------------------------------

@router.get("/stream/{task_id}")
async def stream_crawl_progress(task_id: str):
    """Server-Sent Events stream for real-time crawl progress.

    The frontend connects to this endpoint and receives live events:
    ``start``, ``status``, ``chapter`` (per-chapter progress with
    content preview), ``error``, ``done``.
    """
    return StreamingResponse(
        stream_events(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@router.get("/tasks", response_model=dict)
async def list_tasks(
    novel_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tasks, total = await crawler_service.list_crawler_tasks(
        db, novel_id=novel_id, status=status, page=page, size=size
    )
    return {
        "items": [CrawlerTaskRead.model_validate(t) for t in tasks],
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)),
    }


@router.post("/tasks/queue-range", status_code=200)
async def queue_range_start(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue crawl by book ID range on a source site.

    Body: {"source_name":"23qb", "book_from":12400, "book_to":12500}
    Creates tasks for /book/{id}/ URLs and starts queue processing.
    """
    from app.models.novel import Novel as NovelModel
    source_name = data.get("source_name", "23qb")
    book_from = int(data.get("book_from", 0))
    book_to = int(data.get("book_to", 0))
    if book_from <= 0 or book_to < book_from:
        raise HTTPException(status_code=400, detail="Invalid book range")

    base = f"https://www.23qb.net/book/"
    created = 0; skipped = 0
    for bid in range(book_from, book_to + 1):
        title = f"Book-{bid}"
        url = f"{base}{bid}/"
        # Skip if already exists
        existing = (await db.execute(
            select(NovelModel).where(NovelModel.source_url == url)
        )).scalars().first()
        if existing:
            # Create task for existing novel (update crawl)
            task = CrawlerTaskModel(novel_id=existing.id, status="pending")
            db.add(task); skipped += 1
        else:
            novel = NovelModel(title=title, author="", source_url=url, source_name=source_name)
            db.add(novel); await db.flush()
            task = CrawlerTaskModel(novel_id=novel.id, status="pending")
            db.add(task); created += 1
    await db.commit()

    # Start queue
    global _queue_running
    if not _queue_running:
        _queue_running = True
        asyncio.create_task(_queue_worker())

    return {"message": f"已创建 {created} 新书 + {skipped} 已有, 共 {created+skipped} 个任务排队", "created": created, "skipped": skipped}


@router.post("/tasks/queue-reset", status_code=200)
async def queue_reset():
    """Reset stuck queue."""
    global _queue_running
    _queue_running = False
    return {"message": "队列已重置"}


@router.post("/tasks/repair-placeholders", status_code=200)
async def repair_placeholder_titles(
    data: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Scan for novels with Book-XXXX / Chapter-XXXX placeholders and fix titles.

    Visits each novel's source_url and extracts the real title.

    Body (optional):
        limit: max books to repair (default 10, max 100)
        offset: skip first N books (default 0)
    """
    from app.models.novel import Novel as NovelModel
    from app.crawlers.anti_detect import SmartClient
    from bs4 import BeautifulSoup
    import re as _re

    limit = min(int(data.get("limit", 10)), 100)
    offset = int(data.get("offset", 0))

    # Count total
    count_q = select(func.count()).where(
        (NovelModel.title.startswith("Book-")) |
        (NovelModel.title.startswith("Chapter-"))
    )
    total = (await db.execute(count_q)).scalar() or 0

    if total == 0:
        return {"message": "No placeholder titles found", "fixed": 0, "total": 0}

    # Fetch batch
    q = select(NovelModel).where(
        (NovelModel.title.startswith("Book-")) |
        (NovelModel.title.startswith("Chapter-"))
    ).order_by(NovelModel.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    novels = result.scalars().all()

    if not novels:
        return {"message": "Empty batch", "fixed": 0, "total": total, "offset": offset}

    fixed = 0
    details: list[dict] = []

    async with SmartClient(min_delay=0.2, max_delay=0.8) as client:
        for novel in novels:
            if not novel.source_url:
                details.append({"id": str(novel.id), "old": novel.title, "new": novel.title, "error": "no source_url"})
                continue

            try:
                html = await client.get(novel.source_url)
                soup = BeautifulSoup(html, "lxml")

                # Extract title using multiple strategies (prioritize meta tags)
                title = ""
                # Strategy 1: og:novel:book_name (23qb-specific)
                meta = soup.select_one('meta[property="og:novel:book_name"]')
                if meta:
                    title = meta.get("content", "").strip()

                # Strategy 2: <title> tag
                if not title:
                    title_tag = soup.select_one("title")
                    if title_tag:
                        raw = title_tag.get_text(strip=True)
                        for sep in (" - ", " | ", " — ", "・", "·"):
                            if sep in raw:
                                raw = raw.rsplit(sep, 1)[0].strip()
                        if raw and 1 < len(raw) < 100:
                            title = raw

                # Strategy 3: h1
                if not title:
                    for sel in ["h1", ".page-title", ".novel-title", ".book-title"]:
                        el = soup.select_one(sel)
                        if el:
                            txt = el.get_text(strip=True)
                            if txt and 1 < len(txt) < 80:
                                title = txt
                                break

                # Reject obvious error/noise titles
                _bad_titles = {
                    "出现错误", "错误页面", "404", "Error", "error",
                    "页面不存在", "Not Found", "铅笔小说", "23qb",
                    "笔趣阁", "小说大全", "全本小说网", "趣读小说", "提子小说网", "香书中文",
                }
                _is_bad = any(bad in title for bad in _bad_titles) and len(title) < 20
                if title and title != novel.title and not title.startswith("Book-") and not title.startswith("Chapter-") and len(title) > 1 and not _is_bad:
                    old = novel.title
                    novel.title = title
                    fixed += 1
                    details.append({"id": str(novel.id), "old": old, "new": title})
                else:
                    details.append({"id": str(novel.id), "old": novel.title, "new": novel.title,
                                    "error": "title not found or unchanged"})

            except Exception as e:
                details.append({"id": str(novel.id), "old": novel.title, "new": novel.title, "error": str(e)[:200]})

    if fixed > 0:
        await db.commit()

    return {
        "message": f"Fixed {fixed}/{len(novels)} in batch (offset={offset}, total={total})",
        "fixed": fixed,
        "batch": len(novels),
        "total": total,
        "offset": offset,
        "has_more": offset + limit < total,
        "details": details,
    }


_queue_log = logging.getLogger("crawler.queue")


async def _run_single_crawl(task_id: str, mode: str):
    """Run a single crawl in its own DB session (background task)."""
    from app.database import async_session_factory as _asf
    from app.services import crawler_service as _cs
    try:
        async with _asf() as db:
            await _cs.run_crawl(db, task_id, mode=mode)
    except Exception:
        _queue_log.warning(f"Background crawl {task_id[:12]}... failed")


def start_queue():
    """Restart the background queue processor."""
    global _queue_running
    if not _queue_running:
        _queue_running = True
        asyncio.ensure_future(_queue_worker())


async def _queue_worker():
    """Robust queue processor with built-in watchdog."""
    global _queue_running
    fails = 0
    last_completed = 0  # track completed task count for stuck detection

    async def _completed_count():
        async with async_session_factory() as s:
            return (await s.execute(select(func.count()).where(CrawlerTaskModel.status=="completed"))).scalar() or 0

    last_completed = await _completed_count()
    stuck_checks = 0

    while _queue_running:
        tid = ""
        try:
            # FRESH session per task — prevents lock-wait cascade
            async with async_session_factory() as db:
                t = (await db.execute(
                    select(CrawlerTaskModel).where(CrawlerTaskModel.status=="pending")
                    .order_by(CrawlerTaskModel.created_at).limit(1)
                )).scalars().first()
                if not t:
                    _queue_log.info("Queue empty — stopping")
                    break
                tid = str(t.id)
                await asyncio.wait_for(
                    crawler_service.run_crawl(db, tid, mode="direct"), timeout=600)
                fails = 0; stuck_checks = 0
                await asyncio.sleep(0.3)
        except asyncio.TimeoutError:
            fails += 1; _queue_log.warning(f"Task {tid[:12]}... timeout")
        except Exception as e:
            fails += 1
            if 'Lock wait' in str(e) or 'rollback' in str(e):
                _queue_log.warning(f"DB lock — retry after backoff")
                await asyncio.sleep(5)
                continue
            _queue_log.warning(f"Task {tid[:12]}... failed: {str(e)[:100]}")

        # Watchdog: detect stuck (running but not completing)
        if fails > 0:
            stuck_checks += 1
        if stuck_checks >= 10:
            new_completed = await _completed_count()
            if new_completed == last_completed:
                _queue_log.warning("⚠️ Watchdog: 队列运行但未推进 → 重置重启")
                _queue_running = False
                await asyncio.sleep(3)
                start_queue()
                return  # new worker takes over
            last_completed = new_completed
            stuck_checks = 0; fails = 0

        if fails >= 20:
            _queue_log.error("Too many failures — stopping")
            break

    _queue_running = False
    # Reset running tasks to pending on exit
    try:
        from sqlalchemy import text as _sa_text
        async with async_session_factory() as s:
            reset = await s.execute(
                _sa_text("UPDATE crawler_tasks SET status='pending', "
                         "error_message='队列进程退出，重置为待处理', started_at=NULL "
                         "WHERE status='running'")
            )
            if reset.rowcount > 0:
                _queue_log.info(f"🧹 退出清理: {reset.rowcount} 个 running 任务已重置")
            await s.commit()
    except Exception:
        pass
    # Auto-restart if tasks remain
    await asyncio.sleep(5)
    async with async_session_factory() as s:
        remaining = (await s.execute(select(func.count()).where(CrawlerTaskModel.status=="pending"))).scalar() or 0
    if remaining > 0:
        _queue_log.info(f"Auto-restart: {remaining} tasks remain")
        start_queue()


@router.get("/stats", status_code=200)
async def system_stats(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """System-wide statistics (cached 10s for dashboard auto-refresh)."""
    from app.services.redis_cache import get_or_compute
    from app.models.novel import Novel as NovelModel
    import json, os, glob, subprocess
    from sqlalchemy import text as sa_text

    async def _compute():
        total_t = int((await db.execute(select(func.count()).select_from(CrawlerTaskModel))).scalar() or 0)
        pending_t = int((await db.execute(select(func.count()).where(CrawlerTaskModel.status=="pending"))).scalar() or 0)
        completed_t = int((await db.execute(select(func.count()).where(CrawlerTaskModel.status=="completed"))).scalar() or 0)
        failed_t = int((await db.execute(select(func.count()).where(CrawlerTaskModel.status=="failed"))).scalar() or 0)
        total_n = int((await db.execute(select(func.count()).select_from(NovelModel))).scalar() or 0)
        total_ch = int((await db.execute(sa_text("SELECT COUNT(*) FROM chapters"))).scalar() or 0)
        total_words = int((await db.execute(sa_text("SELECT COALESCE(SUM(word_count),0) FROM chapters"))).scalar() or 0)
        # Check actual queue runner status via DB lock
        running_t = int((await db.execute(select(func.count()).where(CrawlerTaskModel.status=="running"))).scalar() or 0)
        lock_row = (await db.execute(sa_text(
            "SELECT value FROM system_state WHERE key='queue_processor' AND value='locked'"
        ))).fetchone()
        queue_active = lock_row is not None
        gz = glob.glob("data/content/**/*.gz", recursive=True)
        return json.dumps({
            "tasks":{"total":total_t,"pending":pending_t,"completed":completed_t,"failed":failed_t,"running":running_t},
            "novels":total_n,"chapters":total_ch,"words":total_words,
            "content_files":len(gz),
            "queue_running":queue_active,
            "progress":round(completed_t/max(total_t,1)*100,1),
        })

    result = await get_or_compute("query", "system_stats", ttl=10, compute=_compute)
    return json.loads(result) if isinstance(result, str) else result


@router.get("/tasks/queue-status", status_code=200)
async def queue_status():
    """Check if the task queue is actually running (DB lock check)."""
    from app.database import async_session_factory as asf
    from sqlalchemy import text as _t
    async with asf() as s:
        pending = int((await s.execute(select(func.count()).where(CrawlerTaskModel.status == "pending"))).scalar() or 0)
        stuck = int((await s.execute(select(func.count()).where(CrawlerTaskModel.status == "running"))).scalar() or 0)
        # Check DB lock: queue is active if 'locked' row exists
        lock = (await s.execute(_t(
            "SELECT value, worker_pid FROM system_state WHERE key='queue_processor' AND value='locked'"
        ))).fetchone()
        active = lock is not None
    return {"running": active, "pending": pending, "stuck": stuck, "worker_pid": lock[1] if lock else None}


@router.get("/tasks/{task_id}", response_model=CrawlerTaskRead)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await crawler_service.get_crawler_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/tasks/{task_id}", response_model=CrawlerTaskRead)
async def update_task(
    task_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit a crawler task — allows changing novel_id, source_url, etc."""
    task = await crawler_service.get_crawler_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for key in ("error_message", "novel_id", "status"):
        if key in data:
            setattr(task, key, data[key])
    # Also update the novel's source_url if provided
    from app.models.novel import Novel as NovelModel
    from sqlalchemy import select as sa_select
    if "source_url" in data and data["source_url"]:
        novel = (await db.execute(
            select(NovelModel).where(NovelModel.id == task.novel_id)
        )).scalars().first()
        if novel:
            novel.source_url = data["source_url"]
            if "source_name" in data:
                novel.source_name = data["source_name"]
    await db.flush()
    await db.refresh(task)
    return task


@router.post("/tasks/batch-start", status_code=200)
async def batch_start_tasks(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch start selected pending tasks — runs them sequentially one by one."""
    ids = data.get("ids", [])
    started = 0; failed = 0
    for tid in ids:
        task = await crawler_service.get_crawler_task(db, tid)
        if not task or task.status == "running":
            failed += 1; continue
        try:
            await crawler_service.run_crawl(db, tid, mode="direct")
            started += 1
        except Exception:
            failed += 1
    return {"started": started, "failed": failed}


# Global queue state (lock-guarded for multi-worker safety)
_queue_running = False
_queue_lock = asyncio.Lock()

@router.post("/tasks/queue-start", status_code=200)
async def queue_start_tasks(
    current_user: User = Depends(get_current_user),
):
    """Start ALL pending tasks in sequence, one after another.

    Runs in the background — returns immediately with the count of queued tasks.
    Each task completes before the next one starts.
    """
    global _queue_running
    if _queue_running:
        return {"message": "队列已在运行中", "queued": 0}

    _queue_running = True

    async def _process_queue():
        global _queue_running
        try:
            while True:
                async with async_session_factory() as db:  # fresh session per iteration
                    tasks_result = await db.execute(
                        select(CrawlerTaskModel).where(CrawlerTaskModel.status == "pending")
                        .order_by(CrawlerTaskModel.created_at).limit(1)
                    )
                    task = tasks_result.scalars().first()
                    if not task:
                        break
                    try:
                        await crawler_service.run_crawl(db, str(task.id), mode="direct")
                    except Exception as e:
                        _queue_log.warning(f"Queue task failed: {e}")
        finally:
            _queue_running = False

    # Quick count
    from app.database import async_session_factory as asf
    async with asf() as s:
        c = (await s.execute(select(func.count()).where(CrawlerTaskModel.status == "pending"))).scalar()
    asyncio.create_task(_process_queue())
    return {"message": f"队列已启动: {c} 个任务排队中", "queued": c}


@router.post("/tasks/{task_id}/start", response_model=CrawlerTaskRead, status_code=202)
async def start_task(task_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Start a pending/paused task."""
    task = await crawler_service.get_crawler_task(db, task_id)
    if not task: raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "running": raise HTTPException(status_code=409, detail="Already running")
    await crawler_service.run_crawl(db, task_id, mode="direct")
    await db.refresh(task)
    return task


@router.post("/tasks/{task_id}/stop", response_model=CrawlerTaskRead, status_code=202)
async def stop_task(task_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Stop a running task."""
    task = await crawler_service.get_crawler_task(db, task_id)
    if not task: raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "running":
        task.status = "failed"; task.error_message = "手动停止"; task.finished_at = datetime.now(timezone.utc)
        await db.flush(); await db.refresh(task)
    return task


@router.post("/tasks/{task_id}/retry", response_model=CrawlerTaskRead, status_code=202)
async def retry_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-run a failed or completed task."""
    task = await crawler_service.get_crawler_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    # Reset and run sync
    task.status = "pending"
    task.error_message = None
    task.started_at = None
    task.finished_at = None
    await db.flush()
    await crawler_service.run_crawl(db, task_id, mode="direct")
    await db.refresh(task)
    return task


@router.post("/tasks/batch-delete", status_code=200)
async def batch_delete_tasks(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch delete tasks by IDs. Skips running tasks."""
    ids = data.get("ids", [])
    deleted = 0
    skipped = 0
    for tid in ids:
        task = await crawler_service.get_crawler_task(db, tid)
        if not task:
            continue
        if task.status == "running":
            skipped += 1
            continue
        await db.delete(task)
        deleted += 1
    await db.flush()
    return {"deleted": deleted, "skipped": skipped}


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await crawler_service.get_crawler_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "running":
        raise HTTPException(status_code=409, detail="Cannot delete a running task")
    await db.delete(task)
    await db.flush()


# ---------------------------------------------------------------------------
# Background runners
# ---------------------------------------------------------------------------

async def _run_batch_in_session(task_ids: list[str], mode: str = "direct"):
    from app.services.crawl_session import create_session, remove_session
    for tid in task_ids:
        create_session(tid, "")
        async with async_session_factory() as session:
            try:
                await crawler_service.run_crawl(session, tid, mode=mode)
            except Exception:
                pass
        remove_session(tid)
