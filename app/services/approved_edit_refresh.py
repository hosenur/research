from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from bullmq import Job, Queue

from app.repositories.citation_audits import CitationAuditRepository
from app.repositories.papers import PaperDocumentRepository
from app.repositories.pipeline import PaperPipelineRepository
from app.schemas.documents import EditProposal


class JobQueuePort(Protocol):
    async def add_once(
        self,
        name: str,
        data: dict[str, Any],
        *,
        job_id: str,
        attempts: int,
    ) -> None: ...


@dataclass(frozen=True)
class BullMQJobQueue:
    """Production adapter for idempotent BullMQ job submission."""

    queue: Queue

    async def add_once(
        self,
        name: str,
        data: dict[str, Any],
        *,
        job_id: str,
        attempts: int,
    ) -> None:
        if await Job.fromId(self.queue, job_id) is not None:
            return
        await self.queue.add(
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


class ApprovedEditRefresher:
    """Schedule derived indexes and reviews without changing approval outcome."""

    def __init__(
        self,
        *,
        documents: PaperDocumentRepository,
        audits: CitationAuditRepository,
        pipeline: PaperPipelineRepository,
        index_jobs: JobQueuePort,
        missing_review_jobs: JobQueuePort,
        existing_review_jobs: JobQueuePort,
        audit_model: str,
    ) -> None:
        self._documents = documents
        self._audits = audits
        self._pipeline = pipeline
        self._index_jobs = index_jobs
        self._missing_review_jobs = missing_review_jobs
        self._existing_review_jobs = existing_review_jobs
        self._audit_model = audit_model

    async def schedule(self, paper_id: str, approved: EditProposal) -> list[str]:
        revision = approved.approved_revision
        if revision is None:
            return []

        warnings: list[str] = []
        await self._schedule_index(paper_id, revision, warnings)

        approved_operations = [
            operation for operation in approved.operations if operation.approved
        ]
        if not approved_operations:
            return warnings

        try:
            document = await self._documents.get(paper_id)
            restore_all = any(
                operation.operation_type == "restore_revision"
                for operation in approved_operations
            )
            paragraph_ids = {
                node_id
                for operation in approved_operations
                for node_id in operation.node_ids
            }
            section_ids = [
                section.id
                for section in document.paper.sections
                if restore_all
                or any(
                    paragraph.id in paragraph_ids for paragraph in section.paragraphs
                )
            ]
        except Exception as exc:
            warnings.append(
                "The revision was approved, but affected sections could not be loaded "
                f"for citation review: {safe_error(exc)}"
            )
            return warnings

        if not section_ids:
            return warnings

        try:
            audit = await self._audits.create_or_get(paper_id, self._audit_model)
        except Exception as exc:
            warnings.append(
                "The revision was approved, but citation review could not be prepared: "
                f"{safe_error(exc)}"
            )
            return warnings

        jobs = (
            (
                self._missing_review_jobs,
                "audit-missing-citations",
                {
                    "paperId": paper_id,
                    "auditId": audit.id,
                    "sectionIds": section_ids,
                },
                f"citation-audit-{paper_id}-revision-{revision}",
                "missing-citation-review",
            ),
            (
                self._existing_review_jobs,
                "review-existing-citations",
                {"paperId": paper_id, "sectionIds": section_ids},
                f"claim-citation-review-{paper_id}-revision-{revision}",
                "existing-citation-review",
            ),
        )
        for queue, name, data, job_id, stage in jobs:
            try:
                await queue.add_once(
                    name,
                    data,
                    job_id=job_id,
                    attempts=4,
                )
                await self._pipeline.queued(
                    paper_id,
                    stage,
                    revision=revision,
                    progress={
                        "sectionIds": section_ids,
                        "scope": "approved-edit",
                        "manuscriptRevision": revision,
                    },
                )
            except Exception as exc:
                await self._record_failure(paper_id, stage, exc)
                warnings.append(
                    f"The revision was approved, but {stage} is awaiting retry: "
                    f"{safe_error(exc)}"
                )
        return warnings

    async def _schedule_index(
        self,
        paper_id: str,
        revision: int,
        warnings: list[str],
    ) -> None:
        try:
            await self._index_jobs.add_once(
                "index-paper",
                {"paperId": paper_id},
                job_id=f"paper-index-{paper_id}-revision-{revision}",
                attempts=3,
            )
            await self._pipeline.queued(
                paper_id,
                "authoritative-index",
                revision=revision,
                progress={"manuscriptRevision": revision},
            )
        except Exception as exc:
            await self._record_failure(paper_id, "authoritative-index", exc)
            warnings.append(
                "The revision was approved, but manuscript reindexing is awaiting "
                f"retry: {safe_error(exc)}"
            )

    async def _record_failure(self, paper_id: str, stage: str, exc: Exception) -> None:
        try:
            await self._pipeline.fail(paper_id, stage, safe_error(exc))
        except Exception:
            pass


def safe_error(exc: Exception) -> str:
    message = str(exc).strip()
    return (message[:240] if message else type(exc).__name__)
