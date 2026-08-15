from __future__ import annotations

from bullmq import Job, Queue

from app.config import claim_audit_model
from app.repositories.citation_audits import CitationAuditRepository
from app.repositories.pipeline import PaperPipelineRepository


async def enqueue_parsed_paper_pipeline(
    paper_id: str,
    *,
    audits: CitationAuditRepository,
    index_queue: Queue,
    reference_evidence_queue: Queue,
    citation_audit_queue: Queue,
    pipeline: PaperPipelineRepository,
    page_count: int | None = None,
) -> None:
    """Idempotently fan a parsed paper out to every currently implemented stage."""
    audit = await audits.create_or_get(paper_id, claim_audit_model())
    await _add_once(
        index_queue,
        "index-paper",
        {"paperId": paper_id},
        paper_index_job_id(paper_id),
        attempts=3,
    )
    await pipeline.queued(paper_id, "authoritative-index")
    await _add_once(
        reference_evidence_queue,
        "resolve-reference-evidence",
        {"paperId": paper_id},
        reference_evidence_job_id(paper_id),
        attempts=4,
    )
    await pipeline.queued(paper_id, "reference-resolution")
    if page_count and page_count > 80:
        reason = "Whole-document automatic review is limited to 80 pages. Choose up to five sections to review."
        await pipeline.skip(
            paper_id, "missing-citation-review", reason, progress={"pageCount": page_count}
        )
        await pipeline.skip(
            paper_id, "existing-citation-review", reason, progress={"pageCount": page_count}
        )
    else:
        await _add_once(
            citation_audit_queue,
            "audit-missing-citations",
            {"paperId": paper_id, "auditId": audit.id},
            citation_audit_job_id(paper_id),
            attempts=4,
        )
        await pipeline.queued(paper_id, "missing-citation-review")


async def _add_once(
    queue: Queue,
    name: str,
    data: dict[str, str],
    job_id: str,
    *,
    attempts: int,
) -> None:
    if await Job.fromId(queue, job_id) is not None:
        return
    await queue.add(
        name,
        data,
        {
            "jobId": job_id,
            "attempts": attempts,
            "backoff": {"type": "exponential", "delay": 2_000},
            "removeOnComplete": False,
            "removeOnFail": False,
        },
    )


def paper_index_job_id(paper_id: str) -> str:
    return f"paper-index-{paper_id}"


def reference_evidence_job_id(paper_id: str) -> str:
    return f"reference-evidence-v3-{paper_id}"


def citation_audit_job_id(paper_id: str) -> str:
    return f"citation-audit-{paper_id}"


def claim_citation_review_job_id(paper_id: str) -> str:
    return f"claim-citation-review-v2-{paper_id}"
