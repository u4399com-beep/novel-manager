"""Gunicorn config for multi-worker production deployment.

Usage:
    gunicorn -k uvicorn.workers.UvicornWorker -c gunicorn.conf.py app.main:app

Recommended workers: 2-4 × (CPU cores) for I/O bound workloads.
"""
import os
import multiprocessing

# ---- Workers ----
workers = int(os.getenv("GUNICORN_WORKERS", min(8, max(4, multiprocessing.cpu_count()))))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 2000
timeout = 300
keepalive = 5

# ---- Binding ----
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
backlog = 2048

# ---- Process naming ----
proc_name = "novel-manager"

# ---- Logging ----
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# ---- Memory management ----
max_requests = 5000       # Restart worker after 5k requests (prevent leaks)
max_requests_jitter = 500  # Randomize restart timing

# ---- Preload ----
preload_app = True  # Share module memory across workers (post_fork warms per-worker pools)


def post_fork(server, worker):
    """Called after each worker forks — warm up this worker's DB pool."""
    import asyncio
    loop = asyncio.new_event_loop()

    async def warmup():
        from app.database import warmup_pool
        await warmup_pool()
        server.log.info(f"Worker {worker.pid} DB pool warmed up")

    loop.run_until_complete(warmup())


def worker_exit(server, worker):
    """Clean up on worker exit."""
    server.log.info(f"Worker {worker.pid} exiting")
