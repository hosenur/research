from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from typing import Any, Protocol

import httpx

from app.config import (
    OPENALEX_MAX_RETRY_AFTER_SECONDS,
    OPENALEX_MIN_INTERVAL_SECONDS,
    OPENALEX_RETRY_ATTEMPTS,
)


class CacheLookup(Protocol):
    found: bool
    value: Any | None


class Cache(Protocol):
    async def get_cached(self, provider: str, cache_key: str) -> CacheLookup: ...

    async def store_response(
        self,
        provider: str,
        cache_key: str,
        response: Any | None,
        *,
        request: dict[str, Any] | None = None,
    ) -> int: ...


class OpenAlexError(Exception):
    """Raised when OpenAlex cannot be reached or returns an unexpected error."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class OpenAlexRepository:
    """Looks up works on OpenAlex. Never invents a match."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        mailto: str | None = None,
        api_key: str | None = None,
        cache: Cache | None = None,
    ) -> None:
        self._client = client
        self._mailto = mailto
        self._api_key = api_key
        self._cache = cache
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    def _params(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        params = {
            "select": (
                "id,doi,display_name,title,publication_year,ids,"
                "abstract_inverted_index,primary_location,cited_by_count,authorships"
            )
        }
        if extra:
            params.update(extra)
        if self._mailto:
            params.setdefault("mailto", self._mailto)
        if self._api_key:
            params.setdefault("api_key", self._api_key)
        return params

    def _cache_key(self, path: str, params: dict[str, str] | None) -> str:
        payload = json.dumps({"path": path, "params": self._params(params)}, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return f"openalex:{digest}"

    async def _throttle(self) -> None:
        async with self._lock:
            wait = self._next_allowed - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_allowed = time.monotonic() + OPENALEX_MIN_INTERVAL_SECONDS

    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any | None:
        cache_key = self._cache_key(path, params)
        if self._cache is not None:
            cached = await self._cache.get_cached("openalex", cache_key)
            if cached.found:
                return cached.value

        last_error: OpenAlexError | None = None
        for attempt in range(OPENALEX_RETRY_ATTEMPTS):
            await self._throttle()
            try:
                response = await self._client.get(path, params=self._params(params))
            except httpx.RequestError as exc:
                raise OpenAlexError("OpenAlex is unavailable.") from exc

            if response.status_code == 404:
                if self._cache is not None:
                    await self._cache.store_response(
                        "openalex",
                        cache_key,
                        None,
                        request=self._cache_request(path, params),
                    )
                return None
            if response.status_code == 429:
                last_error = OpenAlexError("OpenAlex rate-limited the request.")
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.replace(".", "", 1).isdigit()
                    else 1.5 * (attempt + 1)
                )
                delay = min(delay, OPENALEX_MAX_RETRY_AFTER_SECONDS)
                await asyncio.sleep(delay)
                continue
            if response.status_code >= 400:
                raise OpenAlexError(f"OpenAlex returned HTTP {response.status_code}.")
            try:
                payload = response.json()
            except ValueError as exc:
                raise OpenAlexError("OpenAlex returned a non-JSON body.") from exc
            if self._cache is not None:
                await self._cache.store_response(
                    "openalex",
                    cache_key,
                    payload,
                    request=self._cache_request(path, params),
                )
            return payload

        raise last_error or OpenAlexError("OpenAlex rate-limited the request.")

    def _cache_request(
        self,
        path: str,
        params: dict[str, str] | None,
    ) -> dict[str, Any]:
        safe_params = {
            key: value
            for key, value in self._params(params).items()
            if key not in {"api_key", "mailto"}
        }
        return {"path": path, "params": safe_params}

    async def _first_work(self, payload: Any | None) -> dict[str, Any] | None:
        if not payload:
            return None
        if isinstance(payload, dict) and "results" in payload:
            results = payload.get("results") or []
            return results[0] if results else None
        return payload if isinstance(payload, dict) else None

    async def get_by_doi(self, doi: str) -> dict[str, Any] | None:
        payload = await self._get("/works", {"filter": f"doi:{doi}", "per-page": "1"})
        return await self._first_work(payload)

    async def get_by_arxiv(self, arxiv_id: str) -> dict[str, Any] | None:
        return await self.get_by_doi(f"10.48550/arxiv.{arxiv_id}")

    async def search_by_title(
        self,
        title: str,
        year: int | None = None,
        author: str | None = None,
    ) -> dict[str, Any] | None:
        filters = [f"title.search:{sanitize_filter(title)}"]
        if author:
            filters.append(f"raw_author_name.search:{sanitize_filter(author)}")
        return await self._get(
            "/works",
            {
                "filter": ",".join(filters),
                "per-page": "5",
            },
        )

    async def search_related(self, query: str, per_page: int = 5) -> tuple[dict[str, Any] | None, str]:
        cleaned = sanitize_filter(query)[:400]
        if not cleaned:
            return None, "search"
        last_error: OpenAlexError | None = None
        for method, params in (
            ("search", {"search": cleaned, "per-page": str(per_page)}),
            (
                "keyword",
                {
                    "filter": f"title_and_abstract.search:{cleaned}",
                    "per-page": str(per_page),
                },
            ),
        ):
            try:
                return await self._get("/works", params), method
            except OpenAlexError as exc:
                last_error = exc
                if "rate-limited" in exc.detail or "unavailable" in exc.detail:
                    raise
        if last_error is not None:
            raise last_error
        return None, "search"


def sanitize_filter(value: str) -> str:
    return re.sub(r"[,:|]", " ", value).strip()
