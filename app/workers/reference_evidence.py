from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from bullmq import Job, Queue, Worker

from app.cache.jsonl import JsonlCache
from app.config import (
    OPENALEX_CONCURRENCY,
    REFERENCE_EVIDENCE_QUEUE_NAME,
    CLAIM_CITATION_REVIEW_QUEUE_NAME,
    OPENALEX_TIMEOUT_SECONDS,
    SEMANTIC_SCHOLAR_TIMEOUT_SECONDS,
    bullmq_options,
    openalex_api_key,
    openalex_cache_path,
    openalex_mailto,
    openalex_proxy,
    openalex_url,
    semantic_scholar_api_key,
    semantic_scholar_url,
)
from app.database.session import get_session_factory
from app.repositories.openalex import OpenAlexRepository
from app.repositories.papers import PaperDocumentRepository
from app.repositories.pipeline import PaperPipelineRepository
from app.repositories.scholarly_works import ScholarlyWorkRepository
from app.repositories.semantic_scholar import SemanticScholarRepository
from app.schemas.documents import EnrichmentProgress
from app.schemas.paper import Reference
from app.services.openalex import OpenAlexEnricher
from app.services.paper_pipeline import claim_citation_review_job_id
from app.services.reference_evidence import BibliographyEvidenceResolver


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
    semantic_headers = {}
    if semantic_scholar_api_key():
        semantic_headers["x-api-key"] = semantic_scholar_api_key()
    async with (
        httpx.AsyncClient(
            base_url=openalex_url(),
            timeout=OPENALEX_TIMEOUT_SECONDS,
            headers=headers,
            proxy=openalex_proxy(),
        ) as client,
        httpx.AsyncClient(
            base_url=semantic_scholar_url(),
            timeout=SEMANTIC_SCHOLAR_TIMEOUT_SECONDS,
            headers=semantic_headers,
        ) as semantic_client,
    ):
        provider = OpenAlexRepository(
            client,
            mailto=mailto,
            api_key=openalex_api_key(),
            cache=scholarly_works,
        )
        resolver = BibliographyEvidenceResolver(
            OpenAlexEnricher(provider),
            SemanticScholarRepository(semantic_client, scholarly_works),
            scholarly_works,
        )
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
                result = await enrich_document(job, paper_id, resolver)
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
            REFERENCE_EVIDENCE_QUEUE_NAME,
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
    resolver: BibliographyEvidenceResolver,
) -> dict[str, int]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        documents = PaperDocumentRepository(session)
        document = await documents.get(paper_id)
        existing = await documents.list_enrichments(paper_id, provider="openalex")
        semantic_existing = await documents.list_enrichments(
            paper_id, provider="semantic-scholar"
        )
        completed_ids = {record.reference_id for record in existing}
        semantic_completed_ids = {record.reference_id for record in semantic_existing}
        counters = counters_from_existing(
            [*existing, *semantic_existing], len(document.paper.references)
        )
        await job.updateProgress(counters.model_dump())

        semaphore = asyncio.Semaphore(OPENALEX_CONCURRENCY)

        pending = [
            asyncio.create_task(resolver.resolve(reference, semaphore))
            for reference in document.paper.references
            if reference.id not in completed_ids
            or reference.id not in semantic_completed_ids
        ]
        for result in asyncio.as_completed(pending):
            resolved = await result
            for evidence in resolved.providers:
                await documents.save_provider_enrichment(
                    paper_id,
                    resolved.reference.id,
                    provider=evidence.provider,
                    work_id=evidence.work_id,
                    status=evidence.status,
                    work_json=evidence.work_json,
                    match_method=evidence.match_method,
                    confidence=evidence.confidence,
                    error=evidence.error,
                )
            if resolved.reference.id in completed_ids:
                continue
            counters.completed += 1
            if resolved.reconciliation.status in {"agreed", "single-provider"}:
                counters.matched += 1
            elif resolved.reconciliation.status == "ambiguous":
                counters.failed += 1
            elif any(item.status == "unmatched" for item in resolved.providers):
                counters.unmatched += 1
            elif all(item.status == "skipped" for item in resolved.providers):
                counters.skipped += 1
            else:
                counters.failed += 1
            await job.updateProgress(counters.model_dump())

        return counters.model_dump()


def counters_from_existing(records: list, total: int) -> EnrichmentProgress:
    grouped: dict[str, list] = {}
    for record in records:
        grouped.setdefault(record.reference_id, []).append(record)
    return EnrichmentProgress(
        total=total,
        completed=len(grouped),
        matched=sum(
            any(record.status == "matched" for record in group)
            and not any(record.status == "ambiguous" for record in group)
            for group in grouped.values()
        ),
        unmatched=sum(
            all(record.status == "unmatched" for record in group)
            for group in grouped.values()
        ),
        failed=sum(
            any(record.status in {"ambiguous", "error"} for record in group)
            for group in grouped.values()
        ),
        skipped=sum(
            all(record.status == "skipped" for record in group)
            for group in grouped.values()
        ),
    )


if __name__ == "__main__":
    asyncio.run(run())
