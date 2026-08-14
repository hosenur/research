from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends
from bullmq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session, get_session_factory
from app.repositories.citation_audits import CitationAuditRepository
from app.repositories.artifacts import ExtractionArtifactStore
from app.config import (
    GROBID_TIMEOUT_SECONDS,
    OPENALEX_TIMEOUT_SECONDS,
    extraction_artifact_path,
    grobid_fallback_flavor,
    grobid_url,
    ocr_enabled,
    openalex_api_key,
    openalex_mailto,
    openalex_proxy,
    openalex_url,
    bullmq_options,
    CLAIM_AUDIT_QUEUE_NAME,
    OPENALEX_QUEUE_NAME,
    SOURCE_SEARCH_QUEUE_NAME,
    PAPER_INDEX_QUEUE_NAME,
)
from app.repositories.grobid import GrobidRepository
from app.repositories.openalex import OpenAlexRepository
from app.repositories.papers import PaperDocumentRepository
from app.repositories.scholarly_works import ScholarlyWorkRepository
from app.services.missing_works import MissingWorkFinder
from app.services.openalex import OpenAlexEnricher
from app.services.papers import PaperService
from app.services.pdf_preflight import PdfPreflightService


def get_paper_document_repository(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> PaperDocumentRepository:
    return PaperDocumentRepository(session)


def get_citation_audit_repository(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> CitationAuditRepository:
    return CitationAuditRepository(session)


@lru_cache(maxsize=1)
def get_openalex_queue() -> Queue:
    return Queue(OPENALEX_QUEUE_NAME, bullmq_options())


@lru_cache(maxsize=1)
def get_citation_audit_queue() -> Queue:
    return Queue(CLAIM_AUDIT_QUEUE_NAME, bullmq_options())


@lru_cache(maxsize=1)
def get_source_search_queue() -> Queue:
    return Queue(SOURCE_SEARCH_QUEUE_NAME, bullmq_options())

@lru_cache(maxsize=1)
def get_paper_index_queue() -> Queue:
    return Queue(PAPER_INDEX_QUEUE_NAME, bullmq_options())


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


def get_pdf_preflight_service() -> PdfPreflightService:
    return PdfPreflightService()


@lru_cache(maxsize=1)
def get_extraction_artifact_store() -> ExtractionArtifactStore:
    return ExtractionArtifactStore(Path(extraction_artifact_path()))


def get_paper_service(
    grobid: Annotated[GrobidRepository, Depends(get_grobid_repository)],
    preflight: Annotated[PdfPreflightService, Depends(get_pdf_preflight_service)],
    artifacts: Annotated[ExtractionArtifactStore, Depends(get_extraction_artifact_store)],
) -> PaperService:
    return PaperService(
        grobid,
        preflight,
        artifacts,
        ocr_enabled=ocr_enabled(),
        fallback_flavor=grobid_fallback_flavor(),
    )


@lru_cache(maxsize=1)
def get_scholarly_work_repository() -> ScholarlyWorkRepository:
    return ScholarlyWorkRepository(get_session_factory())


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
    cache: Annotated[ScholarlyWorkRepository, Depends(get_scholarly_work_repository)],
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
