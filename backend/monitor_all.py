#!/usr/bin/env python3
"""Combined monitor: crawl queue + chapter repair status."""
import asyncio, sys, os, time, signal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

C = {"R":"\033[91m","G":"\033[92m","Y":"\033[93m","B":"\033[94m","C":"\033[96m","W":"\033[0m","D":"\033[90m","X":"\033[1m"}

async def fetch_stats():
    from app.database import async_session_factory
    from app.models.crawler_task import CrawlerTask
    from app.models.chapter import Chapter
    from sqlalchemy import select, func, and_
    
    async with async_session_factory() as db:
        # Crawl queue
        q = {}
        for st in ("pending","running","completed","failed"):
            q[st] = (await db.execute(
                select(func.count()).where(CrawlerTask.status == st)
            )).scalar() or 0
        
        # Empty chapters
        empty = (await db.execute(
            select(func.count()).where(
                and_(Chapter.content == None, Chapter.content_file == None)
            )
        )).scalar() or 0
        
        total_ch = (await db.execute(select(func.count()).select_from(Chapter))).scalar() or 1
        
        return q, empty, total_ch

async def run():
    prev_completed = 0
    start = time.monotonic()
    
    while True:
        q, empty, total_ch = await fetch_stats()
        total_tasks = sum(q.values())
        done = q["completed"] + q["failed"]
        pct = done / total_tasks * 100 if total_tasks > 0 else 0
        
        # Speed
        speed = (q["completed"] - prev_completed) / 2 if prev_completed else 0
        prev_completed = q["completed"]
        eta = (q["pending"] / speed / 3600) if speed > 0 else 0
        
        sys.stdout.write("\033[2J\033[H")
        elapsed = int(time.monotonic() - start)
        print(f"{C['X']}{C['C']}╔{'═'*52}╗{C['W']}")
        print(f"{C['C']}║{C['X']}  📊  NOVEL MANAGER MONITOR{' '*30}{C['C']}║")
        print(f"{C['C']}╠{'═'*52}╣{C['W']}")
        
        # Crawl
        bar = "█" * int(pct/100*30) + "░" * (30-int(pct/100*30))
        print(f"{C['C']}║{C['W']}  🕷 采集队列 [{C['B']}{bar}{C['W']}] {pct:.1f}%{' '*12}{C['C']}║")
        print(f"{C['C']}║{C['W']}     {C['Y']}⏳{q['pending']:>6}{C['W']}  {C['B']}🔄{q['running']:>6}{C['W']}  {C['G']}✅{q['completed']:>6}{C['W']}  {C['R']}❌{q['failed']:>6}{C['W']}     {C['C']}║")
        
        speed_str = f"{speed:.1f}/s" if speed > 0 else "—"
        eta_str = f"{eta:.1f}h" if eta < 100 else "—"
        print(f"{C['C']}║{C['W']}     ⚡{speed_str:>8}  ⏱ETA {eta_str:>8}{C['W']}           {C['C']}║")
        
        # Empty chapters
        empty_pct = empty / total_ch * 100
        e_bar = "█" * int(empty_pct/100*30) + "░" * (30-int(empty_pct/100*30))
        print(f"{C['C']}║{' '*52}║")
        print(f"{C['C']}║{C['W']}  📝 空章节 [{C['Y']}{e_bar}{C['W']}] {empty_pct:.1f}%{' '*11}{C['C']}║")
        print(f"{C['C']}║{C['W']}     空: {C['Y']}{empty:>6}{C['W']} / {total_ch:>6} ({100-empty_pct:.1f}% 完成){C['W']}     {C['C']}║")
        
        # Repair log tail
        try:
            with open("/tmp/repair.log") as f:
                lines = f.readlines()
                last_fixed = [l for l in lines[-20:] if "fixed" in l]
                if last_fixed:
                    print(f"{C['C']}║{' '*52}║")
                    print(f"{C['C']}║{C['W']}  🔧 最近修复:{C['W']}{' '*34}{C['C']}║")
                    for lf in last_fixed[-3:]:
                        short = lf.strip()[-48:]
                        print(f"{C['C']}║{C['W']}     {C['G']}{short}{C['W']}{C['C']}║")
        except: pass
        
        print(f"{C['C']}╚{'═'*52}╝{C['W']}")
        print(f"  {C['D']}{time.strftime('%H:%M:%S')} | 运行 {elapsed//60}m{elapsed%60}s | 刷新 2s{C['W']}")
        
        await asyncio.sleep(2)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    asyncio.run(run())
