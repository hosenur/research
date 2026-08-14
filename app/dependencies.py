from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends

from app.cache.jsonl import JsonlCache
from app.config import (
    GROBID_TIMEOUT_SECONDS,
    OPENALEX_TIMEOUT_SECONDS,
    grobid_url,
    openalex_api_key,
    openalex_cache_path,
    openalex_mailto,
    openalex_proxy,
    openalex_url,
)
from app.repositories.grobid import GrobidRepository
from app.repositories.openalex import OpenAlexRepository
from app.services.missing_works import MissingWorkFinder
from app.services.openalex import OpenAlexEnricher
from app.services.papers import PaperService


async def get_grobid_client() -> AsyncIterator[httpx.AsyncClient]:
    """Create a client pointed at the configured GROBID service."""
    async with httpx.AsyncClient(
        base_url=grobid_url(),
        timeout=GROBID_TIMEOUT_SECONDS,
    ) as client:
        yield client


def get_grobid_repository(
    client: Annotated[httpx.AsyncClient, Depends(get_grobid_client)],
) -> GrobidRepository:
    return GrobidRepository(client)


def get_paper_service(
    grobid: Annotated[GrobidRepository, Depends(get_grobid_repository)],
) -> PaperService:
    return PaperService(grobid)


@lru_cache(maxsize=1)
def get_openalex_cache() -> JsonlCache:
    return JsonlCache(Path(openalex_cache_path()))


async def get_openalex_client() -> AsyncIterator[httpx.AsyncClient]:
    mailto = openalex_mailto()
    user_agent = (
        f"folio-paper-parser (mailto:{mailto})"
        if mailto
        else "folio-paper-parser/0.1"
    )
    headers = {"User-Agent": user_agent}
    proxy = openalex_proxy()
    async with httpx.AsyncClient(
        base_url=openalex_url(),
        timeout=OPENALEX_TIMEOUT_SECONDS,
        headers=headers,
        proxy=proxy,
    ) as client:
        yield client


def get_openalex_repository(
    client: Annotated[httpx.AsyncClient, Depends(get_openalex_client)],
    cache: Annotated[JsonlCache, Depends(get_openalex_cache)],
) -> OpenAlexRepository:
    return OpenAlexRepository(
        client,
        mailto=openalex_mailto(),
        api_key=openalex_api_key(),
        cache=cache,
    )


def get_openalex_enricher(
    repository: Annotated[OpenAlexRepository, Depends(get_openalex_repository)],
) -> OpenAlexEnricher:
    return OpenAlexEnricher(repository)


def get_missing_work_finder(
    repository: Annotated[OpenAlexRepository, Depends(get_openalex_repository)],
) -> MissingWorkFinder:
    return MissingWorkFinder(repository)
