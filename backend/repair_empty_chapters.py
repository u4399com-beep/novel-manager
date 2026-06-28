#!/usr/bin/env python3
"""Repair empty chapters — re-fetch content from source site."""
import asyncio, sys, os, logging, re
from urllib.parse import urljoin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger("repair")

async def fix_novel(db, novel_id: str, concurrency: int = 20):
    """Re-fetch empty chapters for one novel."""
    from app.models.chapter import Chapter
    from app.models.novel import Novel
    from app.services.chapter_service import get_chapter_content
    from sqlalchemy import select, and_
    import httpx
    from bs4 import BeautifulSoup

    novel = await db.get(Novel, novel_id)
    if not novel or not novel.source_url:
        return 0

    # Find empty chapters with source_url
    result = await db.execute(
        select(Chapter).where(
            and_(Chapter.novel_id == novel_id, Chapter.content == None, Chapter.content_file == None, Chapter.source_url != None)
        ).limit(500)
    )
    chapters = result.scalars().all()
    if not chapters:
        return 0

    log.info(f"  {novel.title[:30]}: {len(chapters)} empty chapters")
    
    sem = asyncio.Semaphore(concurrency)
    fixed = 0

    async def fetch_one(ch):
        nonlocal fixed
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
                    resp = await c.get(ch.source_url)
                    soup = BeautifulSoup(resp.text, "lxml")
                    cd = soup.select_one(".view-heading .article-content") or soup.select_one("div.article-content")
                    if cd:
                        for j in cd.select("script, ins, .adsbygoogle"): j.decompose()
                        text = cd.get_text(strip=True)
                        if text and len(text) > 50:
                            ch.content = text
                            fixed += 1
            except Exception:
                pass

    await asyncio.gather(*[fetch_one(ch) for ch in chapters])
    
    if fixed > 0:
        await db.commit()
        log.info(f"    ✅ fixed {fixed}/{len(chapters)}")
    
    return fixed

async def main():
    from app.database import async_session_factory
    from app.models.chapter import Chapter
    from app.models.novel import Novel
    from sqlalchemy import select, func, and_

    async with async_session_factory() as db:
        # Get novels with most empty chapters
        result = await db.execute(
            select(Chapter.novel_id, func.count())
            .where(and_(Chapter.content == None, Chapter.content_file == None, Chapter.source_url != None))
            .group_by(Chapter.novel_id)
            .order_by(func.count().desc())
            .limit(50)
        )
        novel_counts = result.all()
        
        log.info(f"Repairing {len(novel_counts)} novels with empty chapters")
        
        total_fixed = 0
        for nid, cnt in novel_counts:
            fixed = await fix_novel(db, nid)
            total_fixed += fixed
            await asyncio.sleep(0.5)
        
        log.info(f"Total fixed: {total_fixed}")

if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    asyncio.run(main())
