from __future__ import annotations

import asyncio

import httpx
from openai import AsyncOpenAI
from bullmq import Job, Queue, Worker
import hashlib
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select

from app.config import (
    OPENALEX_TIMEOUT_SECONDS,
    SEMANTIC_SCHOLAR_TIMEOUT_SECONDS,
    SOURCE_SEARCH_QUEUE_NAME,
    SOURCE_SEARCH_VERSION,
    bullmq_options,
    openalex_api_key,
    openalex_mailto,
    openalex_proxy,
    openalex_url,
    source_verification_model,
    semantic_scholar_api_key,
    semantic_scholar_url,
    OPENAI_TIMEOUT_SECONDS,
    openai_api_key,
    openai_base_url,
)
from app.database.models import CitationAuditFindingRecord, CitationAuditRecord, CitationSourceCandidateRecord, ScholarlyWorkRecord, CitationClaimSearchRecord, CitationClaimSearchResultRecord
from app.database.session import get_session_factory
from app.repositories.citation_audits import CitationAuditRepository
from app.repositories.openalex import OpenAlexRepository
from app.repositories.papers import PaperDocumentRepository
from app.repositories.scholarly_works import ScholarlyWorkRepository
from app.repositories.semantic_scholar import SemanticScholarRepository
from app.services.source_search import CitationSourceSearcher, source_query
from app.services.source_verification import SourceSupportVerifier


async def run() -> None:
    session_factory = get_session_factory()
    works = ScholarlyWorkRepository(session_factory)
    mailto = openalex_mailto()
    openalex_headers = {
        "User-Agent": (
            f"folio-paper-parser (mailto:{mailto})" if mailto else "folio-paper-parser/0.1"
        )
    }
    semantic_headers = {}
    if semantic_scholar_api_key():
        semantic_headers["x-api-key"] = semantic_scholar_api_key()

    async with (
        httpx.AsyncClient(
            base_url=openalex_url(),
            timeout=OPENALEX_TIMEOUT_SECONDS,
            headers=openalex_headers,
            proxy=openalex_proxy(),
        ) as openalex_client,
        httpx.AsyncClient(
            base_url=semantic_scholar_url(),
            timeout=SEMANTIC_SCHOLAR_TIMEOUT_SECONDS,
            headers=semantic_headers,
        ) as semantic_client,
        AsyncOpenAI(api_key=openai_api_key(), base_url=openai_base_url(), timeout=OPENAI_TIMEOUT_SECONDS) as openai_client,
    ):
        searcher = CitationSourceSearcher(
            works,
            OpenAlexRepository(
                openalex_client,
                mailto=mailto,
                api_key=openalex_api_key(),
                cache=works,
            ),
            SemanticScholarRepository(semantic_client, works),
        )
        verifier = SourceSupportVerifier(openai_client, api_key=openai_api_key(), model=source_verification_model())

        async def process(job: Job, _token: str) -> dict[str, int]:
            finding_id = str(job.data.get("findingId") or "")
            if not finding_id:
                raise ValueError("The source-search job is missing findingId.")
            return await search_for_finding(finding_id, searcher, verifier)

        queue = Queue(SOURCE_SEARCH_QUEUE_NAME, bullmq_options())
        await enqueue_pending_source_searches(queue)
        worker = Worker(
            SOURCE_SEARCH_QUEUE_NAME,
            process,
            {
                **bullmq_options(),
                "autorun": False,
                "concurrency": 2,
            },
        )
        await worker.run()


async def search_for_finding(
    finding_id: str,
    searcher: CitationSourceSearcher,
    verifier: SourceSupportVerifier | None = None,
) -> dict[str, int]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        audits = CitationAuditRepository(session)
        await audits.mark_source_search(finding_id, "running")

    try:
        async with session_factory() as session:
            finding = await session.get(CitationAuditFindingRecord, finding_id)
            if finding is None:
                raise RuntimeError("The citation finding was not found.")
            audit = await session.get(CitationAuditRecord, finding.audit_id)
            if audit is None:
                raise RuntimeError("The citation audit was not found.")
            paper = (await PaperDocumentRepository(session).get(audit.paper_id)).paper

        claim_hash = hashlib.sha256(finding.claim_text.strip().lower().encode()).hexdigest()
        candidates = None
        async with session_factory() as session:
            cached = await session.scalar(select(CitationClaimSearchRecord).where(CitationClaimSearchRecord.claim_hash == claim_hash, CitationClaimSearchRecord.search_version == SOURCE_SEARCH_VERSION))
            if cached:
                rows = await session.execute(select(CitationClaimSearchResultRecord).where(CitationClaimSearchResultRecord.search_id == cached.id).order_by(CitationClaimSearchResultRecord.rank))
                candidates = [type("Cached", (), {"work_id": row.work_id, "score": row.score, "reason": row.reason}) for row in rows.scalars()]
        if candidates is None:
            candidates = await searcher.search(paper, finding)
            async with session_factory() as session:
                search = CitationClaimSearchRecord(id=str(__import__('uuid').uuid4()), claim_hash=claim_hash, claim_text=finding.claim_text, query_text=source_query(paper, finding), search_version=SOURCE_SEARCH_VERSION)
                session.add(search)
                await session.flush()
                for rank, candidate in enumerate(candidates, 1):
                    session.add(CitationClaimSearchResultRecord(id=str(__import__('uuid').uuid4()), search_id=search.id, work_id=candidate.work_id, rank=rank, score=candidate.score, reason=candidate.reason))
                await session.commit()
        async with session_factory() as session:
            await CitationAuditRepository(session).save_source_candidates(
                finding_id,
                [
                    (candidate.work_id, candidate.score, candidate.reason)
                    for candidate in candidates
                ],
                source_search_version=SOURCE_SEARCH_VERSION,
            )
        if verifier:
            async with session_factory() as session:
                finding_record = await session.get(CitationAuditFindingRecord, finding_id)
                audit_record = await session.get(CitationAuditRecord, finding_record.audit_id) if finding_record else None
                works = ScholarlyWorkRepository(session)
                if finding_record and audit_record:
                    rows = list(await session.scalars(select(CitationSourceCandidateRecord).where(CitationSourceCandidateRecord.finding_id == finding_id)))
                    for row in rows:
                        work = await session.get(ScholarlyWorkRecord, row.work_id)
                        if work:
                            decision = await verifier.verify(finding_record.claim_text, work.title, work.abstract)
                            await CitationAuditRepository(session).update_candidate_support(row.id, decision)
        return {"candidates": len(candidates)}
    except Exception as exc:
        async with session_factory() as session:
            await CitationAuditRepository(session).mark_source_search(
                finding_id,
                "failed",
                error=str(exc),
            )
        raise


async def enqueue_pending_source_searches(
    queue: Queue,
    *,
    audit_id: str | None = None,
) -> int:
    session_factory = get_session_factory()
    async with session_factory() as session:
        statement = select(CitationAuditFindingRecord.id).where(
            (
                CitationAuditFindingRecord.source_search_status.in_(["not_started", "queued"])
                | (CitationAuditFindingRecord.source_search_version < SOURCE_SEARCH_VERSION)
            )
        )
        if audit_id:
            statement = statement.where(CitationAuditFindingRecord.audit_id == audit_id)
        finding_ids = list(await session.scalars(statement))

    enqueued = 0
    for finding_id in finding_ids:
        async with session_factory() as session:
            finding = await session.get(CitationAuditFindingRecord, finding_id)
            if finding and (
                finding.source_search_status == "not_started"
                or finding.source_search_version < SOURCE_SEARCH_VERSION
            ):
                await CitationAuditRepository(session).mark_source_search(finding_id, "queued")
        job_id = source_search_job_id(finding_id)
        job = await Job.fromId(queue, job_id)
        if job is None:
            await queue.add(
                "find-citation-sources",
                {"findingId": finding_id},
                {
                    "jobId": job_id,
                    "attempts": 4,
                    "backoff": {"type": "exponential", "delay": 2_000},
                    "removeOnComplete": False,
                    "removeOnFail": False,
                },
            )
            enqueued += 1
    return enqueued


def source_search_job_id(finding_id: str) -> str:
    return f"citation-source-v{SOURCE_SEARCH_VERSION}-{finding_id}"


if __name__ == "__main__":
    asyncio.run(run())
