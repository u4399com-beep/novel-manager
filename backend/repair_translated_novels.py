#!/usr/bin/env python3
"""Restore novels accidentally translated to English — fetch original Chinese data from 23qb.net."""
import asyncio, sys, os, logging, re
from urllib.parse import urljoin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger("restore")

async def main():
    from app.database import async_session_factory
    from app.models.novel import Novel
    from app.models.chapter import Chapter
    from app.models.category import Category
    from sqlalchemy import select
    import httpx
    from bs4 import BeautifulSoup

    CATS = {1:'言情',2:'都市',3:'唯美',4:'穿越',5:'青春',6:'玄幻',7:'武侠',8:'军事',9:'竞技',10:'科幻',11:'悬疑',12:'同人',13:'职场'}

    async with async_session_factory() as db:
        # Find affected novels (no Chinese chars in title)
        all_novels = (await db.execute(select(Novel))).scalars().all()
        affected = []
        for n in all_novels:
            has_cn = any('一' <= c <= '鿿' for c in (n.title or ''))
            if not has_cn and n.source_url and '23qb.net' in n.source_url:
                affected.append(n)

        log.info(f"Found {len(affected)} novels to restore")

        if not affected:
            return

        restored_titles = 0
        restored_authors = 0
        restored_descs = 0
        restored_chapters = 0
        restored_cats = 0

        for idx, novel in enumerate(affected):
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                    # Fetch novel info page
                    resp = await client.get(novel.source_url)
                    soup = BeautifulSoup(resp.text, 'lxml')

                    # Extract original Chinese metadata from meta tags
                    title = ""
                    meta = soup.select_one('meta[property="og:novel:book_name"]')
                    if meta:
                        title = meta.get('content', '').strip()
                    if not title:
                        h1 = soup.select_one('h1.page-title') or soup.select_one('h1')
                        title = h1.get_text(strip=True) if h1 else ""

                    author = ""
                    meta = soup.select_one('meta[property="og:novel:author"]')
                    if meta:
                        author = meta.get('content', '').strip()

                    desc = ""
                    meta = soup.select_one('meta[property="og:description"]')
                    if meta:
                        desc = meta.get('content', '').strip()

                    # Restore title
                    if title and any('一' <= c <= '鿿' for c in title):
                        if novel.title != title:
                            novel.title = title
                            restored_titles += 1

                    # Restore author
                    if author and any('一' <= c <= '鿿' for c in author):
                        if novel.author != author:
                            novel.author = author
                            restored_authors += 1

                    # Restore description
                    if desc and any('一' <= c <= '鿿' for c in desc):
                        novel.description = desc[:2000]
                        restored_descs += 1

                    # Restore category from nav link
                    cat_link = soup.select_one('.novel-info-aux a[href*="/book/lastupdate"]')
                    if cat_link:
                        cat_name = cat_link.get_text(strip=True)
                        for cid, cname in CATS.items():
                            if cname == cat_name:
                                novel.categories = [await db.get(Category, cid)]
                                restored_cats += 1
                                break

                    # Restore chapter titles (fetch catalog)
                    book_id = re.search(r'/book/(\d+)', novel.source_url or '')
                    if book_id:
                        bid = book_id.group(1)
                        catalog_url = f"https://www.23qb.net/book/{bid}/catalog"
                        resp2 = await client.get(catalog_url)
                        soup2 = BeautifulSoup(resp2.text, 'lxml')

                        ch_items = soup2.select('.module-row-info a.module-row-text')
                        chapter_map = {}
                        for a in ch_items:
                            href = a.get('href', '')
                            chtitle = a.get('title', '') or a.get_text(strip=True)
                            if href and chtitle:
                                full_url = urljoin('https://www.23qb.net', href)
                                chapter_map[full_url] = chtitle

                        if chapter_map:
                            # Update existing chapters
                            existing = (await db.execute(
                                select(Chapter).where(Chapter.novel_id == novel.id)
                            )).scalars().all()
                            for ch in existing:
                                if ch.source_url in chapter_map:
                                    orig_title = chapter_map[ch.source_url]
                                    if any('一' <= c <= '鿿' for c in orig_title):
                                        if ch.title != orig_title:
                                            ch.title = orig_title
                                            restored_chapters += 1

                    log.info(f"[{idx+1}/{len(affected)}] {title[:30]} — T:{restored_titles} A:{restored_authors} D:{restored_descs} C:{restored_cats} Ch:{restored_chapters}")

            except Exception as e:
                log.warning(f"[{idx+1}/{len(affected)}] Failed: {e}")

            if (idx + 1) % 10 == 0:
                await db.commit()
                log.info(f"  Committed batch ({idx+1}/{len(affected)})")

        await db.commit()

        log.info(f"\n{'='*50}")
        log.info(f"RESTORE COMPLETE")
        log.info(f"  Titles:      {restored_titles}")
        log.info(f"  Authors:     {restored_authors}")
        log.info(f"  Descriptions:{restored_descs}")
        log.info(f"  Categories:  {restored_cats}")
        log.info(f"  Chapters:    {restored_chapters}")
        log.info(f"{'='*50}")


if __name__ == '__main__':
    import signal
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    asyncio.run(main())
