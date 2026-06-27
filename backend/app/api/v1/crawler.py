"""Crawler API — trigger, batch, search-match, monitor, manage."""

import asyncio
import math
from datetime import datetime, timezone
from typing import Optional

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
    await db.flush()
    # Run crawl in same session — most reliable
    await crawler_service.run_crawl(db, str(task.id), mode=data.mode)
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
    _running_tasks.add(asyncio.ensure_future(_run_batch_in_session(
        [t["task_id"] for t in tasks], data.mode,
    )))

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
            sa_select(NovelModel).where(NovelModel.title == title)
        )
        novel = existing.scalar_one_or_none()

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
                    except Exception:
                        pass
                _running_tasks.add(asyncio.ensure_future(_download_cover(str(novel.id), cover_url)))
            imported_count += 1

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
    """Edit a crawler task — allows changing any field."""
    task = await crawler_service.get_crawler_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for key in ("error_message", "novel_id", "status"):
        if key in data:
            setattr(task, key, data[key])
    await db.flush()
    await db.refresh(task)
    return task


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

async def _run_in_session(task_id: str, mode: str = "direct"):
    from app.services.crawl_session import create_session, remove_session
    create_session(task_id, "")
    try:
        for retry in range(5):
            try:
                async with async_session_factory() as session:
                    await crawler_service.run_crawl(session, task_id, mode=mode)
                break  # success
            except ValueError as exc:
                if "not found" in str(exc) and retry < 4:
                    await asyncio.sleep(0.3 * (retry + 1))
                    continue
                raise
    finally:
        remove_session(task_id)


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
