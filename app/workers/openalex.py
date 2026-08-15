from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from bullmq import Job, Queue, Worker

from app.cache.jsonl import JsonlCache
from app.config import (
    OPENALEX_CONCURRENCY,
    OPENALEX_QUEUE_NAME,
    CLAIM_CITATION_REVIEW_QUEUE_NAME,
    OPENALEX_TIMEOUT_SECONDS,
    bullmq_options,
    openalex_api_key,
    openalex_cache_path,
    openalex_mailto,
    openalex_proxy,
    openalex_url,
)
from app.database.session import get_session_factory
from app.repositories.openalex import OpenAlexRepository
from app.repositories.papers import PaperDocumentRepository
from app.repositories.pipeline import PaperPipelineRepository
from app.repositories.scholarly_works import ScholarlyWorkRepository
from app.schemas.documents import EnrichmentProgress
from app.schemas.paper import Reference
from app.services.openalex import OpenAlexEnricher
from app.services.paper_pipeline import claim_citation_review_job_id


async def run() -> None:
    scholarly_works = ScholarlyWorkRepository(get_session_factory())
    await scholarly_works.backfill_openalex_jsonl(
        JsonlCache(Path(openalex_cache_path()))
    )
    mailto = openalex_mailto()
    headers = {
        "User-Agent": (
            f"folio-paper-parser (mailto:{mailto})" if mailto else "folio-paper-parser/0.1"
        )
    }
    async with httpx.AsyncClient(
        base_url=openalex_url(),
        timeout=OPENALEX_TIMEOUT_SECONDS,
        headers=headers,
        proxy=openalex_proxy(),
    ) as client:
        provider = OpenAlexRepository(
            client,
            mailto=mailto,
            api_key=openalex_api_key(),
            cache=scholarly_works,
        )
        enricher = OpenAlexEnricher(provider)
        existing_citation_queue = Queue(
            CLAIM_CITATION_REVIEW_QUEUE_NAME, bullmq_options()
        )

        async def process(job: Job, _token: str) -> dict[str, int]:
            paper_id = str(job.data.get("paperId") or "")
            if not paper_id:
                raise ValueError("The enrichment job is missing paperId.")
            try:
                async with get_session_factory()() as session:
                    await PaperPipelineRepository(session).begin(
                        paper_id, "reference-resolution"
                    )
                result = await enrich_document(job, paper_id, enricher)
                async with get_session_factory()() as session:
                    pipeline = PaperPipelineRepository(session)
                    document = await PaperDocumentRepository(session).get(paper_id)
                    page_count = (
                        document.paper.extraction.preflight.page_count
                        if document.paper.extraction else None
                    )
                    await pipeline.complete(
                        paper_id, "reference-resolution", progress=result
                    )
                    if page_count and page_count > 80:
                        await pipeline.skip(
                            paper_id,
                            "existing-citation-review",
                            "Whole-document automatic review is limited to 80 pages. Choose up to five sections to review.",
                            progress={"pageCount": page_count},
                        )
                    else:
                        await pipeline.queued(paper_id, "existing-citation-review")
                if not page_count or page_count <= 80:
                    review_job_id = claim_citation_review_job_id(paper_id)
                    if await Job.fromId(existing_citation_queue, review_job_id) is None:
                        await existing_citation_queue.add(
                            "review-existing-citations",
                            {"paperId": paper_id},
                            {
                                "jobId": review_job_id,
                                "attempts": 4,
                                "backoff": {"type": "exponential", "delay": 2_000},
                                "removeOnComplete": False,
                                "removeOnFail": False,
                            },
                        )
                return result
            except Exception as exc:
                async with get_session_factory()() as session:
                    await PaperPipelineRepository(session).fail(
                        paper_id, "reference-resolution", str(exc)
                    )
                raise

        worker = Worker(
            OPENALEX_QUEUE_NAME,
            process,
            {
                **bullmq_options(),
                "autorun": False,
                "concurrency": 1,
            },
        )
        await worker.run()


async def enrich_document(
    job: Job,
    paper_id: str,
    enricher: OpenAlexEnricher,
) -> dict[str, int]:
    session_factory = get_session_factory()
    scholarly_works = ScholarlyWorkRepository(session_factory)
    async with session_factory() as session:
        documents = PaperDocumentRepository(session)
        document = await documents.get(paper_id)
        existing = await documents.list_enrichments(paper_id)
        completed_ids = {record.reference_id for record in existing}
        counters = counters_from_existing(existing, len(document.paper.references))
        await job.updateProgress(counters.model_dump())

        semaphore = asyncio.Semaphore(OPENALEX_CONCURRENCY)

        async def enrich(reference: Reference) -> Reference:
            await enricher.enrich_reference(reference, semaphore)
            return reference

        pending = [
            asyncio.create_task(enrich(reference))
            for reference in document.paper.references
            if reference.id not in completed_ids
        ]
        for result in asyncio.as_completed(pending):
            reference = await result
            work_id = None
            if reference.openalex is not None:
                work_id = await scholarly_works.find_by_provider_id(
                    "openalex",
                    reference.openalex.id,
                )
            await documents.save_reference_enrichment(
                paper_id,
                reference,
                work_id=work_id,
            )
            counters.completed += 1
            if reference.openalex_status == "matched":
                counters.matched += 1
            elif reference.openalex_status == "unmatched":
                counters.unmatched += 1
            elif reference.openalex_status == "skipped":
                counters.skipped += 1
            else:
                counters.failed += 1
            await job.updateProgress(counters.model_dump())

        return counters.model_dump()


def counters_from_existing(records: list, total: int) -> EnrichmentProgress:
    return EnrichmentProgress(
        total=total,
        completed=len(records),
        matched=sum(record.status == "matched" for record in records),
        unmatched=sum(record.status == "unmatched" for record in records),
        failed=sum(record.status == "error" for record in records),
        skipped=sum(record.status == "skipped" for record in records),
    )


if __name__ == "__main__":
    asyncio.run(run())
