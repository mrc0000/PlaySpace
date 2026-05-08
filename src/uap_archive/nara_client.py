"""Rate-limited async HTTP client. Etiquette is baked in here, not the callers."""

from __future__ import annotations

import asyncio
import logging
import urllib.robotparser
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

import httpx
from aiolimiter import AsyncLimiter
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from uap_archive.config import (
    DEFAULT_RPS,
    MAX_RETRIES,
    NARA_API_BASE,
    PER_HOST_CONCURRENCY,
    RETRY_BASE,
    user_agent,
)

log = logging.getLogger(__name__)


class RateLimitedClient:
    """
    Wraps httpx.AsyncClient with:
      - global rate limit (rps)
      - per-host concurrency cap
      - tenacity retries on 429/5xx with exponential backoff
      - one-time robots.txt check per host
      - 429 throttle-down: 3 in a row halves rps
    """

    def __init__(
        self,
        rps: float = DEFAULT_RPS,
        per_host_concurrency: int = PER_HOST_CONCURRENCY,
        timeout: float = 60.0,
    ):
        self._rps = rps
        # AsyncLimiter takes (max_rate, time_period). 1 token per (1/rps) seconds.
        self._limiter = AsyncLimiter(max_rate=1, time_period=max(0.001, 1.0 / rps))
        self._sem: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(per_host_concurrency)
        )
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent()},
            timeout=timeout,
            follow_redirects=True,
            http2=True,
        )
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._consecutive_429 = 0

    async def __aenter__(self) -> RateLimitedClient:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def rps(self) -> float:
        return self._rps

    async def _ensure_robots(self, host: str) -> None:
        if host in self._robots:
            return
        url = f"https://{host}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = await self._client.get(url)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
                self._robots[host] = rp
                return
        except httpx.HTTPError as e:
            log.warning("robots.txt fetch failed for %s: %s", host, e)
        # On 404/error, leave unset — treat as permissive but log it.
        self._robots[host] = None

    def _allowed(self, url: str) -> bool:
        host = urlparse(url).netloc
        rp = self._robots.get(host)
        if rp is None:
            return True
        return rp.can_fetch(user_agent().split()[0], url)

    async def _throttle_down(self) -> None:
        self._consecutive_429 += 1
        if self._consecutive_429 >= 3:
            new_rps = max(self._rps / 2, 0.1)
            log.warning("Three consecutive 429s — sleeping 5 min and lowering rps %.2f → %.2f",
                        self._rps, new_rps)
            await asyncio.sleep(300)
            self._rps = new_rps
            self._limiter = AsyncLimiter(max_rate=1, time_period=1.0 / self._rps)
            self._consecutive_429 = 0

    async def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        host = urlparse(url).netloc
        await self._ensure_robots(host)
        if not self._allowed(url):
            log.info("robots.txt disallows %s — skipping", url)
            raise PermissionError(f"robots.txt disallows {url}")

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(MAX_RETRIES),
            wait=wait_exponential(multiplier=RETRY_BASE, min=RETRY_BASE, max=16),
            retry=retry_if_exception_type((httpx.TransportError, _RetryableStatus)),
            reraise=True,
        ):
            with attempt:
                async with self._sem[host], self._limiter:
                    r = await self._client.request(method, url, **kwargs)
                if r.status_code == 429:
                    retry_after = float(r.headers.get("retry-after", "0") or 0)
                    if retry_after > 0:
                        await asyncio.sleep(min(retry_after, 60))
                    await self._throttle_down()
                    raise _RetryableStatus(429, url)
                if 500 <= r.status_code < 600:
                    raise _RetryableStatus(r.status_code, url)
                if r.status_code == 200:
                    self._consecutive_429 = 0
                return r
        raise RuntimeError("unreachable")

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def head(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("HEAD", url, **kwargs)

    @asynccontextmanager
    async def stream(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> AsyncIterator[httpx.Response]:
        """Streaming request that still respects robots.txt and rate limits.

        No automatic retry mid-stream; callers handle status codes themselves.
        """
        host = urlparse(url).netloc
        await self._ensure_robots(host)
        if not self._allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        async with self._sem[host], self._limiter:
            async with self._client.stream(method, url, **kwargs) as r:
                yield r

    # ----- NARA Catalog API helpers -----

    async def nara_record(self, naid: int) -> dict:
        """Fetch a single NARA catalog record by NAID."""
        r = await self.get(f"{NARA_API_BASE}/records/{naid}")
        r.raise_for_status()
        return r.json()

    async def nara_children(self, parent_naid: int, limit: int = 200):
        """Yield child records page by page."""
        offset = 0
        while True:
            r = await self.get(
                f"{NARA_API_BASE}/records/parentNaId/{parent_naid}",
                params={"limit": limit, "offset": offset},
            )
            r.raise_for_status()
            payload = r.json()
            # The API shape (post-2023 v2) wraps results in {"body": {"hits": {"hits": [...]}}}.
            # Defend against shape variation across endpoints by trying common keys.
            records = _extract_record_list(payload)
            if not records:
                return
            for rec in records:
                yield rec
            if len(records) < limit:
                return
            offset += len(records)


class _RetryableStatus(Exception):
    def __init__(self, status: int, url: str):
        self.status = status
        super().__init__(f"retryable HTTP {status} for {url}")


def _extract_record_list(payload: dict) -> list[dict]:
    """NARA's v2 API has shifted shapes; try the common ones in order."""
    # Most common modern shape
    body = payload.get("body") if isinstance(payload, dict) else None
    if isinstance(body, dict):
        hits = body.get("hits")
        if isinstance(hits, dict) and isinstance(hits.get("hits"), list):
            return [h.get("_source", h) for h in hits["hits"]]
    # Older flat shape
    if isinstance(payload, dict):
        for key in ("results", "records", "items"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
    return []


def extract_digital_objects(record: dict) -> list[dict]:
    """Pull digital objects from a NARA record. Returns list of dicts with stable keys."""
    src = record.get("_source", record) if isinstance(record, dict) else {}
    dos: list[dict] = []
    candidates = src.get("digitalObjects") or src.get("digital_objects") or []
    for d in candidates:
        url = d.get("objectUrl") or d.get("object_url") or d.get("url")
        if not url:
            continue
        dos.append({
            "url": url,
            "filename": d.get("objectFilename") or d.get("filename") or url.rsplit("/", 1)[-1],
            "media_type": d.get("mediaType") or d.get("media_type") or d.get("contentType"),
            "size_bytes": d.get("size") or d.get("sizeBytes"),
        })
    return dos
