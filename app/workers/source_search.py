from __future__ import annotations

import asyncio
import logging

import httpx
from openai import AsyncOpenAI
from bullmq import Job, Queue, Worker
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
from app.database.models import CitationAuditFindingRecord
from app.database.session import get_session_factory
from app.repositories.citation_audits import CitationAuditRepository
from app.repositories.openalex import OpenAlexRepository
from app.repositories.scholarly_works import ScholarlyWorkRepository
from app.repositories.semantic_scholar import SemanticScholarRepository
from app.services.source_search import build_citation_source_fulfillment


logger = logging.getLogger(__name__)


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
        AsyncOpenAI(
            api_key=openai_api_key(),
            base_url=openai_base_url(),
            timeout=OPENAI_TIMEOUT_SECONDS,
        ) as openai_client,
    ):
        fulfillment = build_citation_source_fulfillment(
            session_factory,
            works,
            OpenAlexRepository(
                openalex_client,
                mailto=mailto,
                api_key=openalex_api_key(),
                cache=works,
            ),
            SemanticScholarRepository(semantic_client, works),
            openai_client,
            api_key=openai_api_key(),
            model=source_verification_model(),
        )

        async def process(job: Job, _token: str) -> dict[str, int]:
            finding_id = str(job.data.get("findingId") or "")
            if not finding_id:
                raise ValueError("The source-search job is missing findingId.")
            result = await fulfillment.fulfill(finding_id)
            return {"candidates": result.candidate_count}

        queue = Queue(SOURCE_SEARCH_QUEUE_NAME, bullmq_options())
        worker = Worker(
            SOURCE_SEARCH_QUEUE_NAME,
            process,
            {
                **bullmq_options(),
                "autorun": False,
                "concurrency": 2,
            },
        )
        backfill = asyncio.create_task(enqueue_pending_source_searches(queue))
        backfill.add_done_callback(report_backfill_failure)
        await worker.run()


async def enqueue_pending_source_searches(
    queue: Queue,
    *,
    audit_id: str | None = None,
) -> int:
    session_factory = get_session_factory()
    # A worker restart should recover durable queued work, but it must not turn
    # a search-version bump into a full historical reprocessing job. New audit
    # findings are scoped by audit_id and may still start from not_started.
    eligible_statuses = ["not_started", "queued"] if audit_id else ["queued"]
    async with session_factory() as session:
        statement = select(CitationAuditFindingRecord.id).where(
            CitationAuditFindingRecord.source_search_status.in_(eligible_statuses)
        )
        if audit_id:
            statement = statement.where(CitationAuditFindingRecord.audit_id == audit_id)
        statement = statement.order_by(CitationAuditFindingRecord.created_at.desc())
        finding_ids = list(await session.scalars(statement))

    enqueued = 0
    for finding_id in finding_ids:
        async with session_factory() as session:
            finding = await session.get(CitationAuditFindingRecord, finding_id)
            if finding and finding.source_search_status in eligible_statuses:
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
        elif await job.getState() == "failed":
            # A deployment may fix the cause of an exhausted job while the durable
            # finding still correctly says its search is pending. Reprocess that
            # same idempotency key instead of leaving the finding queued forever.
            await job.retry(
                "failed",
                {
                    "resetAttemptsMade": True,
                    "resetAttemptsStarted": True,
                },
            )
            enqueued += 1
    return enqueued


def source_search_job_id(finding_id: str) -> str:
    return f"citation-source-v{SOURCE_SEARCH_VERSION}-{finding_id}"


def report_backfill_failure(task: asyncio.Task[int]) -> None:
    try:
        task.result()
    except Exception:
        logger.exception("Citation source-search backfill failed.")


if __name__ == "__main__":
    asyncio.run(run())
