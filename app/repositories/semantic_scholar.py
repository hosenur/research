from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from typing import Any

import httpx

from app.config import (
    SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS,
    SEMANTIC_SCHOLAR_RETRY_ATTEMPTS,
)
from app.repositories.openalex import Cache


class SemanticScholarError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class SemanticScholarRepository:
    """Search Semantic Scholar's Graph API with a durable exact-request cache."""

    _fields = (
        "paperId,title,abstract,year,authors,externalIds,url,"
        "citationCount,openAccessPdf"
    )

    def __init__(self, client: httpx.AsyncClient, cache: Cache) -> None:
        self._client = client
        self._cache = cache
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def search(self, query: str, *, limit: int = 5) -> dict[str, Any] | None:
        cleaned = sanitize_query(query)[:500]
        if not cleaned:
            return None
        params: dict[str, str] = {
            "query": cleaned,
            "limit": str(limit),
            "fields": self._fields,
        }
        cache_key = self._cache_key("/paper/search", params)
        cached = await self._cache.get_cached("semantic-scholar", cache_key)
        if cached.found:
            return cached.value

        last_error: SemanticScholarError | None = None
        for attempt in range(SEMANTIC_SCHOLAR_RETRY_ATTEMPTS):
            await self._throttle()
            try:
                response = await self._client.get("/paper/search", params=params)
            except httpx.RequestError as exc:
                raise SemanticScholarError("Semantic Scholar is unavailable.") from exc
            if response.status_code == 429:
                last_error = SemanticScholarError("Semantic Scholar rate-limited the request.")
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
                await asyncio.sleep(min(delay, 20))
                continue
            if response.status_code >= 400:
                raise SemanticScholarError(
                    f"Semantic Scholar returned HTTP {response.status_code}."
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise SemanticScholarError("Semantic Scholar returned a non-JSON body.") from exc
            await self._cache.store_response(
                "semantic-scholar",
                cache_key,
                payload,
                request={"path": "/paper/search", "params": params},
            )
            return payload
        raise last_error or SemanticScholarError("Semantic Scholar rate-limited the request.")

    async def _throttle(self) -> None:
        async with self._lock:
            delay = self._next_allowed - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_allowed = time.monotonic() + SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS

    @staticmethod
    def _cache_key(path: str, params: dict[str, str]) -> str:
        encoded = json.dumps({"path": path, "params": params}, sort_keys=True)
        return "semantic-scholar:" + hashlib.sha256(encoded.encode()).hexdigest()


def sanitize_query(value: str) -> str:
    # Semantic Scholar plain-text search treats hyphens as operators poorly.
    return re.sub(r"\s+", " ", re.sub(r"[-–—]", " ", value)).strip()
