"""Fetching for the live data sources: timeout, one retry, a short-lived cache, and
serve-stale-on-error, so a slow or broken upstream never stalls a live phone call."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from stormdesk import chaos
from stormdesk.config import settings

RETRY_DELAY_S = 0.25


class SourceUnavailable(Exception):
    """The upstream failed and there is no earlier copy to fall back on."""


@dataclass
class Fetched:
    data: Any
    fetched_at: float
    stale: bool = False
    error: str | None = None

    @property
    def age_s(self) -> int:
        return int(time.time() - self.fetched_at)


class CachedFetcher:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client
        self._cache: dict[str, Fetched] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=settings.http_timeout_s,
                follow_redirects=True,
                headers={"User-Agent": "StormDesk/0.1 (IT service desk demo)"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        # Locks belong to the event loop that is shutting down.
        self._locks.clear()

    def prime(self, url: str, data: Any) -> None:
        """Put a known answer in the cache (tests and offline demos)."""
        self._cache[url] = Fetched(data, time.time())

    def clear(self) -> None:
        self._cache.clear()

    async def get_json(self, url: str, ttl_s: int) -> Fetched:
        if chaos.is_on("feeds_down"):  # drill: as if every upstream had been down long enough to have no copy
            raise SourceUnavailable(f"{url}: feeds_down drill")
        cached = self._cache.get(url)
        if cached and cached.age_s < ttl_s:
            return cached
        # One fetch per URL at a time: five Google services asking at once share one request.
        async with self._locks.setdefault(url, asyncio.Lock()):
            cached = self._cache.get(url)
            if cached and cached.age_s < ttl_s:
                return cached
            try:
                data = await self._fetch_with_retry(url)
            except (httpx.HTTPError, ValueError) as exc:
                reason = str(exc) or type(exc).__name__
                if cached:
                    return Fetched(cached.data, cached.fetched_at, stale=True, error=reason)
                raise SourceUnavailable(f"{url}: {reason}") from exc
            fresh = Fetched(data, time.time())
            self._cache[url] = fresh
            return fresh

    async def _fetch_with_retry(self, url: str) -> Any:
        try:
            return await self._fetch(url)
        except (httpx.HTTPError, ValueError):
            await asyncio.sleep(RETRY_DELAY_S)
            return await self._fetch(url)

    async def _fetch(self, url: str) -> Any:
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json()


fetcher = CachedFetcher()
