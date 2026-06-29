"""Crawler service — single/batch crawl with incremental update."""
import asyncio, re, time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawlers.anti_detect import SmartClient
from app.crawlers.content_cleaner import clean_chapter_title, clean_content as clean_chapter
from app.crawlers.registry import get_crawler
from app.crawlers.rule_engine import load_rule
from app.models.chapter import Chapter
from app.models.crawler_task import CrawlerTask
from app.models.novel import Novel
from app.services.chapter_service import batch_create_chapters, count_words
from app.services.crawl_session import CrawlEvent, create_session, get_session, remove_session
from app.services.novel_service import save_cover_image as save_cover

# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------
async def create_crawler_task(db: AsyncSession, novel_id: str, source_name: Optional[str] = None) -> CrawlerTask:
    t = CrawlerTask(novel_id=novel_id, status="pending")
    db.add(t)
    await db.flush()
    await db.refresh(t)
    return t

async def get_crawler_task(db: AsyncSession, task_id: str) -> Optional[CrawlerTask]:
    return (await db.execute(select(CrawlerTask).where(CrawlerTask.id == task_id))).scalar_one_or_none()

async def list_crawler_tasks(db: AsyncSession, *, novel_id: Optional[str] = None, status: Optional[str] = None, page: int = 1, size: int = 20) -> tuple[list[CrawlerTask], int]:
    q = select(CrawlerTask)
    if novel_id: q = q.where(CrawlerTask.novel_id == novel_id)
    if status: q = q.where(CrawlerTask.status == status)
    q = q.order_by(CrawlerTask.created_at.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(q.offset((page - 1) * size).limit(size))).scalars().all()
    return list(items), total

# ---------------------------------------------------------------------------
# Auto-match: search source site by novel title
# ---------------------------------------------------------------------------
async def auto_match_novel(novel: Novel, source_name: str) -> Optional[str]:
    c = get_crawler(source_name)
    if not c: return None
    try:
        results = await c.search(novel.title)
    except Exception:
        return None
    best_url, best_score = "", 0
    for r in results:
        score = 0
        if r.get("title") == novel.title: score += 50
        elif novel.title in r.get("title", "") or r.get("title", "") in novel.title: score += 30
        if novel.author and r.get("author"):
            if novel.author == r.get("author"): score += 40
            elif novel.author in r.get("author") or r.get("author") in novel.author: score += 20
        if score > best_score: best_score, best_url = score, r.get("url", "")
    return best_url if best_score >= 30 else None

# ---------------------------------------------------------------------------
# Parse catalog: extract volume + chapter list
# ---------------------------------------------------------------------------
def _parse_catalog(html: str) -> tuple[list[str], list[dict]]:
    """Return (volume_titles, chapter_list) from catalog HTML."""
    soup = BeautifulSoup(html, "lxml")
    # Volume headers: h2.module-title.type, excluding #shuqian (阅读进度)
    volumes = [el.get_text(strip=True) for el in soup.select("h2.module-title.type") if el.find_parent(id="shuqian") is None]
    ch_items = soup.select(".module-row-info a.module-row-text")
    # Build volume map
    vol_map, cur_vol = [], volumes[0] if volumes else ""
    vi = 0
    for el in soup.select(".module-title, .module-row-info"):
        if "module-title" in el.get("class", []):
            txt = el.get_text(strip=True)
            if txt and "阅读进度" not in txt and vi < len(volumes): cur_vol = volumes[vi]; vi += 1
        elif "module-row-info" in el.get("class", []):
            vol_map.append(cur_vol)
    # Build chapter list
    chapters = []
    for idx, a in enumerate(ch_items):
        href = a.get("href", "")
        if href:
            chapters.append({
                "idx": idx, "title": a.get("title", "") or a.get_text(strip=True),
                "url": urljoin("https://www.23qb.net", href),
                "volume": vol_map[idx] if idx < len(vol_map) else "",
            })
    return volumes, chapters

# ---------------------------------------------------------------------------
# Single crawl (the main function)
# ---------------------------------------------------------------------------
async def run_crawl(db: AsyncSession, task_id: str, *, mode: str = "direct") -> CrawlerTask:
    task = await get_crawler_task(db, task_id)
    if not task: raise ValueError(f"Task {task_id} not found")
    novel = (await db.execute(select(Novel).where(Novel.id == task.novel_id))).scalar_one_or_none()
    if not novel: task.status = "failed"; task.error_message = "Novel not found"; await db.flush(); return task
    source_name = novel.source_name
    if not source_name: task.status = "failed"; task.error_message = "No source_name"; await db.flush(); return task

    session = get_session(task_id) or create_session(task_id, novel.title)
    start_time = time.monotonic()

    try:
        task.status = "running"; task.started_at = datetime.now(timezone.utc); await db.flush()
        session.emit(CrawlEvent("status", status="running", message="开始采集..."))

        # --- Search mode ---
        if mode == "search" or not novel.source_url:
            session.emit(CrawlEvent("status", status="searching", message=f"搜索 '{novel.title}'..."))
            match_url = await auto_match_novel(novel, source_name)
            if not match_url:
                task.status = "failed"; task.error_message = f"未找到 '{novel.title}'"; task.finished_at = datetime.now(timezone.utc)
                await db.flush(); await session.close(); remove_session(task_id); return task
            novel.source_url = match_url; await db.flush()
            session.emit(CrawlEvent("status", status="matched", message=f"匹配: {match_url}"))

        crawler = get_crawler(source_name)
        if not crawler: raise ValueError(f"No crawler for '{source_name}'")

        async with SmartClient() as client:
            # Patch crawler to use anti-detect client
            orig_fetch = crawler._fetch
            async def _fetch(url: str) -> str: return await client.get(url, referer=novel.source_url or crawler.base_url)
            crawler._fetch = _fetch  # type: ignore

            try:
                # --- Novel metadata (cover + description) ---
                # Skip if already complete (has cover, author, description)
                has_full_info = (
                    novel.cover_image_url and novel.author and novel.description
                    and not novel.author.startswith("Book-")
                )
                if novel.source_url and not has_full_info:
                    try:
                        info = await crawler.get_novel_info(novel.source_url)
                        # Update title if it's a placeholder (Book-XXXX / Chapter-XXXX)
                        if info.get("title") and (not novel.title or novel.title.startswith("Book-") or novel.title.startswith("Chapter-")):
                            novel.title = info["title"]; await db.flush()
                        # Save missing fields
                        if info.get("author") and (not novel.author or novel.author == "未知"):
                            novel.author = info["author"]; await db.flush()
                        desc = info.get("description", "")
                        if desc and not novel.description: novel.description = desc[:2000]; await db.flush()
                        # Smart category mapping: match 23qb name to local by keyword overlap
                        cat_name = info.get("category_name", "")
                        if cat_name and not novel.categories:
                            from app.models.category import Category as CatModel
                            all_cats = (await db.execute(select(CatModel))).scalars().all()
                            best, best_score = None, 0
                            for lc in all_cats:
                                score = 0
                                if lc.name in cat_name: score += 10
                                if cat_name in lc.name: score += 5
                                for kw in ['言情','都市','唯美','耽美','百合','穿越','青春','玄幻','武侠','军事','竞技','科幻','悬疑','同人','职场','修真','历史','游戏','空间','惊悚','官场','魔法']:
                                    if kw in lc.name and kw in cat_name: score += 3
                                if score > best_score: best_score, best = score, lc
                            # Edge case: 耽美百合 → 唯美
                            if not best and '耽美' in cat_name:
                                best = next((c for c in all_cats if c.name == '唯美'), None)
                            if best and (best_score >= 3 or '耽美' in cat_name):
                                novel.categories = [best]
                                await db.flush(); await db.refresh(novel)
                                session.emit(CrawlEvent("status", status="category", message=f"分类: {best.name}"))
                        cover_url = info.get("cover_url", "")
                        if cover_url and not novel.cover_image_url:
                            session.emit(CrawlEvent("status", status="cover", message="下载封面..."))
                            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
                                resp = await http.get(cover_url)
                                if resp.status_code == 200:
                                    fn = cover_url.rsplit("/", 1)[-1] or "cover.jpg"
                                    novel.cover_image_url = await save_cover(novel, resp.content, fn)
                                    await db.flush()
                    except Exception as exc:
                        session.emit(CrawlEvent("status", status="cover", message=f"封面/简介失败: {exc}"))

                # --- Phase 1: Catalog ---
                m = re.search(r"/book/(\d+)", novel.source_url or "")
                book_id = m.group(1) if m else ""
                catalog_url = f"{crawler.base_url}/book/{book_id}/catalog"
                session.emit(CrawlEvent("status", status="catalog", message="获取章节目录..."))
                catalog_html = await _fetch(catalog_url)
                volumes, all_chapters = _parse_catalog(catalog_html)
                session.emit(CrawlEvent("progress", phase="catalog", total=len(all_chapters),
                                        message=f"发现 {len(all_chapters)} 章 ({len(volumes)} 卷)"))

                # --- Incremental filter ---
                # Only fetch columns needed for dedup (not full TEXT content)
                existing_rows = (await db.execute(
                    select(Chapter.source_url, Chapter.title, Chapter.sort_order)
                    .where(Chapter.novel_id == novel.id)
                )).all()
                exist_urls = {row[0] for row in existing_rows if row[0]}
                exist_keys = {(row[1], row[2]) for row in existing_rows}
                new_chapters = [c for c in all_chapters if c["url"] not in exist_urls and (c["title"], c["idx"] + 1) not in exist_keys]
                # Re-index so idx matches position in filtered list
                for i, c in enumerate(new_chapters): c["idx"] = i
                skipped = len(all_chapters) - len(new_chapters)
                if skipped > 0:
                    session.emit(CrawlEvent("status", status="incremental", message=f"增量: {len(new_chapters)} 新章, 跳过 {skipped} 已有"))

                task.chapters_found = len(new_chapters)
                if len(new_chapters) == 0:
                    task.status = "completed"; task.finished_at = datetime.now(timezone.utc); task.error_message = None
                    await db.flush(); await db.commit(); remove_session(task_id); return task

                # --- Phase 2: Concurrent chapter fetch ---
                sem = asyncio.Semaphore(settings.CRAWLER_CONCURRENCY)
                data = [{} for _ in range(len(new_chapters))]; done = 0; lock = asyncio.Lock()
                rule = load_rule(source_name); cleaner_cfg = rule.get("cleaner", {}) if rule else {}
                session.emit(CrawlEvent("progress", phase="fetch", total=len(new_chapters),
                                        message=f"并发采集 {len(new_chapters)} 章 ({CONCURRENCY}线程)"))

                async with httpx.AsyncClient(
                    timeout=30, follow_redirects=True,
                    limits=httpx.Limits(max_connections=30, max_keepalive_connections=15),
                    headers={"User-Agent": "Mozilla/5.0 Chrome/130.0.0.0", "Accept": "text/html;q=0.9,*/*;q=0.8", "Accept-Language": "zh-CN"},
                ) as pool:
                    async def _fetch_one(ch: dict):
                        nonlocal done
                        async with sem:
                            content = ""
                            try:
                                resp = await pool.get(ch["url"]); resp.raise_for_status()
                                ch_soup = BeautifulSoup(resp.text, "lxml")
                                cd = ch_soup.select_one(".view-heading .article-content") or ch_soup.select_one("div.article-content")
                                if cd:
                                    for j in cd.select("script, ins, .adsbygoogle"): j.decompose()
                                    from app.crawlers.sources.twenty_three_qb import _clean_text
                                    paras = [_clean_text(p.get_text()) for p in cd.select("p") if len(_clean_text(p.get_text())) > 5]
                                    if not paras: paras = [_clean_text(d.get_text()) for d in cd.select(":scope > div") if len(_clean_text(d.get_text())) > 15]
                                    if not paras:
                                        raw = _clean_text(cd.get_text())
                                        if raw: paras = [raw]
                                    content = "\n\n".join(paras)
                            except Exception:
                                pass  # individual chapter fetch failure is non-fatal
                            # Clean chapter title — reject garbage
                            chapter_title = clean_chapter_title(ch["title"])
                            if not chapter_title:
                                chapter_title = f"第{ch['idx'] + 1}章"  # fallback
                            data[ch["idx"]] = {"title": chapter_title, "content": content, "source_url": ch["url"], "sort_order": ch["idx"] + 1, "volume": ch.get("volume", "")}
                            async with lock:
                                nonlocal done; done += 1
                                if cleaner_cfg.get("enabled") and content:
                                    content = clean_chapter(content, remove_lines=cleaner_cfg.get("remove_lines"), inline_remove=cleaner_cfg.get("inline_remove"))
                                    data[ch["idx"]]["content"] = content  # persist cleaned content
                                elapsed = time.monotonic() - start_time
                                spd = done / elapsed if elapsed > 0 else 0
                                if done % max(1, len(new_chapters) // 20) == 0 or done <= 3:
                                    session.emit(CrawlEvent("chapter", index=done, total=len(new_chapters), title=chapter_title,
                                        speed=round(spd, 1), eta=round((len(new_chapters) - done) / spd, 0) if spd > 0 else 0,
                                        content_preview=content[:120] if content else "(空)",
                                        message=f"[{done}/{len(new_chapters)}] {ch['title']}"))
                    await asyncio.gather(*[_fetch_one(c) for c in new_chapters])

                # --- Batch insert ---
                valid = [c for c in data if c.get("title")]
                if valid:
                    created = await batch_create_chapters(db, novel.id, valid)
                    task.chapters_added = len(created)
                else:
                    task.chapters_added = 0

                task.status = "completed"; task.finished_at = datetime.now(timezone.utc); task.error_message = None
                total_time = time.monotonic() - start_time
                session.emit(CrawlEvent("status", status="completed",
                    message=f"采集完成! {done} 章, {total_time:.0f}s", total_chapters=done, total_time=round(total_time, 1)))

            finally:
                crawler._fetch = orig_fetch  # type: ignore

    except Exception as exc:
        task.status = "failed"; task.error_message = str(exc)[:500]; task.finished_at = datetime.now(timezone.utc)
        session.emit(CrawlEvent("error", message=str(exc)[:300]))
        await db.rollback()  # discard partial inserts from failed crawl
    finally:
        await session.close()

    await db.flush(); await db.commit(); await db.refresh(task); remove_session(task_id)
    return task

# ---------------------------------------------------------------------------
# Batch crawl
# ---------------------------------------------------------------------------
async def run_batch_crawl(db: AsyncSession, novel_ids: list[str], source_name: Optional[str] = None, mode: str = "direct") -> list[CrawlerTask]:
    tasks = []
    for nid in novel_ids:
        n = (await db.execute(select(Novel).where(Novel.id == nid))).scalar_one_or_none()
        if not n: continue
        t = CrawlerTask(novel_id=nid, status="pending"); db.add(t); tasks.append(t)
    await db.flush(); [await db.refresh(t) for t in tasks]
    for t in tasks:
        try: await run_crawl(db, str(t.id), mode=mode)
        except Exception as exc:
            import logging; logging.getLogger("crawler").error("Batch task %s failed: %s", t.id, exc)
            t.status = "failed"
            t.error_message = str(exc)[:500]
    return tasks

# ---------------------------------------------------------------------------
# Search preview (no side effects)
# ---------------------------------------------------------------------------
async def preview_search_match(db: AsyncSession, novel_id: str, source_name: str) -> dict:
    novel = (await db.execute(select(Novel).where(Novel.id == novel_id))).scalar_one_or_none()
    if not novel: return {"error": "Novel not found"}
    c = get_crawler(source_name)
    if not c: return {"error": f"No crawler for '{source_name}'"}
    try: results = await c.search(novel.title)
    except Exception as exc: return {"error": f"Search failed: {exc}"}
    scored = []
    for r in results:
        score = 0
        if r.get("title") == novel.title: score += 50
        elif novel.title in r.get("title", "") or r.get("title", "") in novel.title: score += 30
        if novel.author and r.get("author"):
            if novel.author == r.get("author"): score += 40
            elif novel.author in r.get("author") or r.get("author") in novel.author: score += 20
        r["_score"] = score; scored.append(r)
    scored.sort(key=lambda x: x["_score"], reverse=True)
    return {"novel_title": novel.title, "novel_author": novel.author, "source_name": source_name,
            "total_results": len(scored), "candidates": scored[:10],
            "best_match": scored[0] if scored and scored[0]["_score"] >= 30 else None}
