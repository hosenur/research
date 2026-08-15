from __future__ import annotations

import asyncio
import logging

import httpx
from bullmq import Job, Queue, Worker

from app.config import (
    CLAIM_AUDIT_QUEUE_NAME,
    GROBID_TIMEOUT_SECONDS,
    REFERENCE_EVIDENCE_QUEUE_NAME,
    PAPER_INDEX_QUEUE_NAME,
    PAPER_PARSE_QUEUE_NAME,
    bullmq_options,
    grobid_fallback_flavor,
    grobid_url,
    ocr_enabled,
)
from app.database.session import get_session_factory
from app.database.models import PaperRecord
from app.repositories.artifacts import create_paper_artifact_store
from app.repositories.citation_audits import CitationAuditRepository
from app.repositories.grobid import GrobidRepository
from app.repositories.papers import PaperDocumentRepository
from app.repositories.pipeline import PaperPipelineRepository
from app.services.paper_pipeline import enqueue_parsed_paper_pipeline
from app.services.papers import PaperService
from app.services.pdf_preflight import PdfPreflightService


logger = logging.getLogger(__name__)


async def run() -> None:
    artifacts = create_paper_artifact_store()
    index_queue = Queue(PAPER_INDEX_QUEUE_NAME, bullmq_options())
    reference_evidence_queue = Queue(
        REFERENCE_EVIDENCE_QUEUE_NAME, bullmq_options()
    )
    audit_queue = Queue(CLAIM_AUDIT_QUEUE_NAME, bullmq_options())

    async with httpx.AsyncClient(
        base_url=grobid_url(),
        timeout=GROBID_TIMEOUT_SECONDS,
    ) as client:
        service = PaperService(
            GrobidRepository(client),
            PdfPreflightService(),
            artifacts,
            ocr_enabled=ocr_enabled(),
            fallback_flavor=grobid_fallback_flavor(),
        )

        async def process(job: Job, _token: str) -> dict[str, int | str]:
            paper_id = str(job.data.get("paperId") or "")
            if not paper_id:
                raise ValueError("The paper-parse job is missing paperId.")
            page_count: int | None = None
            parse_complete = False
            try:
                async with get_session_factory()() as session:
                    documents = PaperDocumentRepository(session)
                    await PaperPipelineRepository(session).begin(
                        paper_id, "authoritative-parse"
                    )
                    lifecycle = await documents.begin_parse(paper_id)
                    filename, object_key = await documents.source(paper_id)

                if lifecycle.status != "ready":
                    await job.updateProgress({"stage": "reading-source"})
                    content = await asyncio.to_thread(artifacts.read_source, object_key)
                    await job.updateProgress({"stage": "grobid"})
                    paper = await service.parse_pdf(content, filename)
                    page_count = paper.extraction.preflight.page_count if paper.extraction else None
                    async with get_session_factory()() as session:
                        await PaperDocumentRepository(session).complete_parse(paper_id, paper)
                        await PaperPipelineRepository(session).complete(
                            paper_id,
                            "authoritative-parse",
                            progress={
                                "sections": len(paper.sections),
                                "references": len(paper.references),
                            },
                        )
                else:
                    async with get_session_factory()() as session:
                        record = await session.get(PaperRecord, paper_id)
                        page_count = record.page_count if record else None
                        await PaperPipelineRepository(session).complete(
                            paper_id, "authoritative-parse"
                        )
                parse_complete = True

                await job.updateProgress({"stage": "starting-review"})
                async with get_session_factory()() as session:
                    documents = PaperDocumentRepository(session)
                    await documents.hydrate_cached_reference_enrichments(paper_id)
                    await enqueue_parsed_paper_pipeline(
                        paper_id,
                        audits=CitationAuditRepository(session),
                        index_queue=index_queue,
                        reference_evidence_queue=reference_evidence_queue,
                        citation_audit_queue=audit_queue,
                        pipeline=PaperPipelineRepository(session),
                        page_count=page_count,
                    )
                return {"paperId": paper_id, "stage": "ready"}
            except Exception as exc:
                if parse_complete:
                    logger.warning(
                        "Parsed paper %s but could not start its review pipeline: %s",
                        paper_id,
                        exc,
                    )
                    raise

                current_attempt = job.attemptsMade + 1
                max_attempts = max(int(job.attempts), 1)
                async with get_session_factory()() as session:
                    pipeline = PaperPipelineRepository(session)
                    if current_attempt < max_attempts:
                        await pipeline.queued(
                            paper_id,
                            "authoritative-parse",
                            progress={
                                "retrying": True,
                                "attempt": current_attempt,
                                "attempts": max_attempts,
                                "reason": (
                                    "A temporary processing issue occurred. "
                                    f"Retrying automatically ({current_attempt} of {max_attempts})."
                                ),
                            },
                        )
                        logger.warning(
                            "Paper parse attempt %s/%s failed for %s; retrying: %s",
                            current_attempt,
                            max_attempts,
                            paper_id,
                            exc,
                        )
                    else:
                        await PaperDocumentRepository(session).fail_parse(
                            paper_id, str(exc)
                        )
                        await pipeline.fail(
                            paper_id, "authoritative-parse", str(exc)
                        )
                        logger.exception(
                            "Paper parse exhausted %s attempts for %s",
                            max_attempts,
                            paper_id,
                        )
                raise

        worker = Worker(
            PAPER_PARSE_QUEUE_NAME,
            process,
            {
                **bullmq_options(),
                "autorun": False,
                "concurrency": 1,
            },
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(run())
