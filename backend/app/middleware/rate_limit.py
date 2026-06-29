"""Simple in-memory rate limiter for API protection."""

import asyncio
import time
from collections import defaultdict
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket-style rate limiter per client IP.

    Default: 100 requests per 60-second window per IP.
    API endpoints share the bucket; SSR endpoints are exempt.
    """

    def __init__(
        self,
        app,
        max_requests: int = 100,
        window_seconds: int = 60,
        exempt_paths: tuple[str, ...] = ("/health", "/static", "/docs", "/redoc"),
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window_seconds
        self.exempt_paths = exempt_paths
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        # Skip exempt paths
        path = request.url.path
        if any(path.startswith(p) for p in self.exempt_paths):
            return await call_next(request)

        # Only rate-limit API calls; SSR pages are cached and cheap
        if not path.startswith("/api/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()

        async with self._lock:
            bucket = self._buckets[client_ip]
            # Evict expired timestamps
            cutoff = now - self.window
            bucket[:] = [t for t in bucket if t > cutoff]

            if len(bucket) >= self.max_requests:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many requests. Please slow down.",
                        "retry_after": int(self.window - (now - bucket[0])),
                    },
                )

            bucket.append(now)

            # Periodic cleanup: remove empty buckets to prevent memory leak
            if len(self._buckets) > 10000:
                empty = [ip for ip, b in self._buckets.items() if not b]
                for ip in empty:
                    del self._buckets[ip]

        return await call_next(request)
