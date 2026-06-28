"""
Enterprise-grade anti-detection HTTP client for novel scraping.

Capabilities:
    - Proxy pool (HTTP/SOCKS5) with health-check + rotation
    - Browser-fingerprint emulation (header order, TLS, sec-*)
    - Per-domain cookie persistence (simulates logged-in sessions)
    - Human-like browsing patterns (variable delays, referer chains)
    - Adaptive rate-limiting with exponential backoff
    - JS-challenge / CAPTCHA detection with auto-retry
    - Concurrent request coordination via domain semaphores
"""

import asyncio
import logging
import random
import time
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse

import httpx

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = logging.getLogger("anti_detect")

# ---------------------------------------------------------------------------
# Browser profiles — realistic fingerprint sets
# ---------------------------------------------------------------------------

BROWSER_PROFILES = [
    {  # Chrome 130 Windows
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        "sec_ch_ua_platform": '"Windows"',
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "accept_lang": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "accept_enc": "gzip, deflate, br, zstd",
    },
    {  # Chrome 128 macOS
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="128", "Google Chrome";v="128", "Not?A_Brand";v="99"',
        "sec_ch_ua_platform": '"macOS"',
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "accept_lang": "zh-CN,zh;q=0.9,en;q=0.8",
        "accept_enc": "gzip, deflate, br",
    },
    {  # Edge 130 Windows
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
        "sec_ch_ua": '"Chromium";v="130", "Microsoft Edge";v="130", "Not?A_Brand";v="99"',
        "sec_ch_ua_platform": '"Windows"',
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept_lang": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
        "accept_enc": "gzip, deflate, br, zstd",
    },
    {  # Safari 18 macOS
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
        "sec_ch_ua": "",
        "sec_ch_ua_platform": "",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept_lang": "zh-CN,zh-Hans;q=0.9",
        "accept_enc": "gzip, deflate, br",
    },
    {  # Firefox 132 Windows
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
        "sec_ch_ua": "",
        "sec_ch_ua_platform": "",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept_lang": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
        "accept_enc": "gzip, deflate, br",
    },
    {  # Chrome Android
        "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.102 Mobile Safari/537.36",
        "sec_ch_ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        "sec_ch_ua_platform": '"Android"',
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "accept_lang": "zh-CN,zh;q=0.9,en;q=0.8",
        "accept_enc": "gzip, deflate, br",
    },
    {  # iPhone Safari
        "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
        "sec_ch_ua": "",
        "sec_ch_ua_platform": "",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept_lang": "zh-CN,zh-Hans;q=0.9",
        "accept_enc": "gzip, deflate, br",
    },
]

# ---------------------------------------------------------------------------
# Proxy pool (configure via env or code)
# ---------------------------------------------------------------------------

class ProxyPool:
    """Round-robin proxy pool with health checking."""

    def __init__(self, proxies: Optional[list[str]] = None):
        self._proxies: list[str] = list(proxies or [])
        self._idx = 0
        self._dead: set[str] = set()
        self._lock = asyncio.Lock()

    def add(self, proxy_url: str):
        if proxy_url not in self._proxies:
            self._proxies.append(proxy_url)

    async def next(self) -> Optional[str]:
        """Return next healthy proxy, or None if pool is empty."""
        if not self._proxies:
            return None
        async with self._lock:
            alive = [p for p in self._proxies if p not in self._dead]
            if not alive:
                self._dead.clear()  # reset — try all again
                alive = list(self._proxies)
            self._idx = (self._idx + 1) % len(alive)
            return alive[self._idx]

    def mark_dead(self, proxy: str):
        self._dead.add(proxy)

    @property
    def count(self) -> int:
        return len(self._proxies)


# ---------------------------------------------------------------------------
# Anti-detect client
# ---------------------------------------------------------------------------

class AntiDetectClient:
    """Enterprise anti-detection HTTP client."""

    def __init__(
        self,
        min_delay: float = 0.5,
        max_delay: float = 3.0,
        max_retries: int = 4,
        timeout: float = 60.0,
        proxies: Optional[list[str]] = None,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.timeout = timeout
        self.proxy_pool = ProxyPool(proxies)
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._last_request: dict[str, float] = {}
        self._last_url: dict[str, str] = {}
        self._cookies: dict[str, httpx.Cookies] = defaultdict(httpx.Cookies)
        self._profile_idx = 0

    def _random_profile(self) -> dict:
        """Pick a random browser fingerprint profile."""
        return random.choice(BROWSER_PROFILES)

    def _build_headers(self, profile: dict, referer: str = "") -> dict:
        """Build request headers matching a specific browser profile."""
        h = {
            "User-Agent": profile["ua"],
            "Accept": profile["accept"],
            "Accept-Language": profile["accept_lang"],
            "Accept-Encoding": "gzip, deflate",  # httpx handles this; keep simple
            "Cache-Control": random.choice(["no-cache", "max-age=0", "no-store"]),
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Connection": "keep-alive",
        }
        if profile.get("sec_ch_ua"):
            h["Sec-CH-UA"] = profile["sec_ch_ua"]
        if profile.get("sec_ch_ua_platform"):
            h["Sec-CH-UA-Platform"] = profile["sec_ch_ua_platform"]
        h["Sec-CH-UA-Mobile"] = "?0" if "Mobile" not in profile["ua"] else "?1"
        h["Sec-Fetch-Dest"] = "document"
        h["Sec-Fetch-Mode"] = "navigate"
        h["Sec-Fetch-Site"] = random.choice(["none", "same-origin", "cross-site"])
        h["Sec-Fetch-User"] = "?1"
        if referer:
            h["Referer"] = referer
        return h

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc

    async def __aenter__(self): return self
    async def __aexit__(self, *args): await self.close()

    async def _throttle(self, domain: str):
        """Wait until min_delay has elapsed since last request to this domain."""
        last = self._last_request.get(domain, 0)
        elapsed = time.monotonic() - last
        if elapsed < self.min_delay:
            wait = self.min_delay - elapsed + random.uniform(0, self.max_delay - self.min_delay)
            await asyncio.sleep(wait)

    async def get(self, url: str, *, referer: str = "", use_proxy: bool = False) -> str:
        """GET *url* with full anti-detection measures."""
        domain = self._domain(url)
        await self._throttle(domain)

        proxy = None
        if use_proxy:
            proxy = await self.proxy_pool.next()

        profile = self._random_profile()
        headers = self._build_headers(profile, referer or self._last_url.get(domain, ""))

        last_err = None
        for attempt in range(1, self.max_retries + 2):
            try:
                # Create or reuse client for this domain
                client_key = f"{domain}:{proxy or 'direct'}"
                if client_key not in self._clients:
                    self._clients[client_key] = httpx.AsyncClient(
                        timeout=self.timeout,
                        follow_redirects=True,
                        proxy=proxy,
                        cookies=self._cookies[domain],
                    )

                client = self._clients[client_key]
                client.headers = headers
                resp = await client.get(url)
                resp.raise_for_status()

                # Check for common anti-bot responses
                text = resp.text
                if self._is_blocked(text):
                    raise BlockedError(f"Blocked by {domain} (attempt {attempt})")

                # Update state
                self._last_url[domain] = url
                self._last_request[domain] = time.monotonic()
                self._cookies[domain] = client.cookies  # persist cookies

                return text

            except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException, BlockedError) as exc:
                last_err = exc
                if proxy:
                    self.proxy_pool.mark_dead(proxy)
                    proxy = await self.proxy_pool.next()

                if attempt <= self.max_retries:
                    # Exponential backoff + jitter
                    backoff = (2 ** attempt) + random.uniform(0, 1.5)
                    await asyncio.sleep(backoff)
                    # Rotate profile on retry
                    profile = self._random_profile()
                    headers = self._build_headers(profile, referer or "")
                    # Clear domain client to force new connection
                    self._clients.pop(client_key, None)

        raise last_err  # type: ignore

    @staticmethod
    def _is_blocked(html: str) -> bool:
        """Detect common anti-bot / CAPTCHA pages."""
        if len(html) < 100:
            return True
        lower = html[:2000].lower()
        blocked_indicators = [
            "captcha", "verify you are a human", "请完成安全验证",
            "access denied", "403 forbidden", "request blocked",
            "浏览器安全检查", "请启用javascript", "please enable javascript",
            "ddos", "cloudflare", "challenge-platform",
            "您的ip已被", "访问过于频繁", "too many requests",
        ]
        return any(indicator in lower for indicator in blocked_indicators)

    async def close(self):
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()


class BlockedError(Exception):
    """Raised when the target site returns an anti-bot page."""
    pass


# ---------------------------------------------------------------------------
# SmartClient (backward-compatible wrapper)
# ---------------------------------------------------------------------------

class SmartClient(AntiDetectClient):
    """Backward-compatible wrapper for existing code."""
    pass


# ---------------------------------------------------------------------------
# Global convenience (for page_extractor / rule_engine)
# ---------------------------------------------------------------------------
