#!/usr/bin/env python3
"""Repair empty cover images — fetch from source site."""
import asyncio, sys, os, logging, re
from urllib.parse import urljoin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger("covers")

async def fix_covers(batch_size=100, concurrency=30):
    from app.database import async_session_factory
    from app.models.novel import Novel
    from app.services.novel_service import save_cover_image
    from sqlalchemy import select
    import httpx
    from bs4 import BeautifulSoup

    async with async_session_factory() as db:
        novels = (await db.execute(
            select(Novel).where(
                ((Novel.cover_image_url == None) | (Novel.cover_image_url == '')),
                Novel.source_url != None, Novel.source_url != ''
            ).limit(batch_size)
        )).scalars().all()

        if not novels:
            log.info("No novels need covers!")
            return

        log.info(f"Fixing covers for {len(novels)} novels ({concurrency} concurrent)")
        sem = asyncio.Semaphore(concurrency)
        fixed = 0

        async def fetch_one(novel):
            nonlocal fixed
            async with sem:
                try:
                    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
                        resp = await c.get(novel.source_url)
                        soup = BeautifulSoup(resp.text, "lxml")
                        
                        # Try meta og:image first
                        cover_url = ""
                        meta = soup.select_one('meta[property="og:image"]')
                        if meta:
                            cover_url = meta.get("content", "")
                        
                        # Try img inside novel cover area
                        if not cover_url:
                            for sel in [".module-item-pic img", ".novel-cover img", ".book-cover img", "img[src*='cover']", "img[src*='image']"]:
                                img = soup.select_one(sel)
                                if img:
                                    src = img.get("src") or img.get("data-src") or ""
                                    if src and not src.endswith("loading.gif"):
                                        cover_url = urljoin(novel.source_url, src)
                                        break

                        if cover_url:
                            resp2 = await c.get(cover_url)
                            if resp2.status_code == 200 and len(resp2.content) > 100:
                                filename = cover_url.rsplit("/", 1)[-1] or "cover.jpg"
                                novel.cover_image_url = await save_cover_image(novel, resp2.content, filename)
                                fixed += 1
                except Exception:
                    pass

        await asyncio.gather(*[fetch_one(n) for n in novels])

        if fixed > 0:
            await db.commit()
            log.info(f"✅ Fixed {fixed}/{len(novels)} covers")

        # Count remaining
        remaining = (await db.execute(
            select(func.count()).where(
                ((Novel.cover_image_url == None) | (Novel.cover_image_url == ''))
            )
        )).scalar()
        log.info(f"Remaining: {remaining}")

from sqlalchemy import func

if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    asyncio.run(fix_covers(batch_size=500, concurrency=30))
