from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PaperPipelineStageRecord
from app.schemas.documents import PaperPipelineStage


PIPELINE_STAGE_ORDER = (
    "upload",
    "quick-extraction",
    "quick-index",
    "authoritative-parse",
    "authoritative-index",
    "reference-resolution",
    "missing-citation-review",
    "existing-citation-review",
    "export",
)


class PaperPipelineRepository:
    """Own durable, independently retryable stage transitions for one paper DAG."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def initialize(self, paper_id: str) -> None:
        now = datetime.now(UTC)
        states = {
            "upload": ("completed", now),
            "quick-extraction": ("queued", None),
            "quick-index": ("not_started", None),
            "authoritative-parse": ("queued", None),
        }
        for stage in PIPELINE_STAGE_ORDER:
            status, completed_at = states.get(stage, ("not_started", None))
            await self._session.execute(
                insert(PaperPipelineStageRecord)
                .values(
                    paper_id=paper_id,
                    stage=stage,
                    status=status,
                    completed_at=completed_at,
                )
                .on_conflict_do_nothing(index_elements=["paper_id", "stage"])
            )
        await self._session.commit()

    async def queued(
        self,
        paper_id: str,
        stage: str,
        *,
        revision: int = 1,
        progress: dict[str, Any] | None = None,
    ) -> None:
        await self._upsert(
            paper_id,
            stage,
            status="queued",
            revision=revision,
            progress=progress or {},
            error=None,
            completed_at=None,
        )

    async def begin(
        self,
        paper_id: str,
        stage: str,
        *,
        revision: int = 1,
        progress: dict[str, Any] | None = None,
    ) -> None:
        current = await self._session.get(
            PaperPipelineStageRecord, {"paper_id": paper_id, "stage": stage}
        )
        attempt = (current.attempt if current else 0) + 1
        await self._upsert(
            paper_id,
            stage,
            status="running",
            attempt=attempt,
            revision=revision,
            progress=progress or {},
            error=None,
            started_at=datetime.now(UTC),
            completed_at=None,
        )

    async def update_progress(
        self,
        paper_id: str,
        stage: str,
        progress: dict[str, Any],
    ) -> None:
        record = await self._record(paper_id, stage)
        record.progress = progress
        await self._session.commit()

    async def complete(
        self,
        paper_id: str,
        stage: str,
        *,
        revision: int = 1,
        progress: dict[str, Any] | None = None,
    ) -> None:
        await self._upsert(
            paper_id,
            stage,
            status="completed",
            revision=revision,
            progress=progress or {},
            error=None,
            completed_at=datetime.now(UTC),
        )

    async def fail(self, paper_id: str, stage: str, error: str) -> None:
        record = await self._record(paper_id, stage)
        record.status = "failed"
        record.error = error[:4_000]
        record.completed_at = datetime.now(UTC)
        await self._session.commit()

    async def skip(
        self,
        paper_id: str,
        stage: str,
        reason: str,
        *,
        progress: dict[str, Any] | None = None,
    ) -> None:
        await self._upsert(
            paper_id,
            stage,
            status="skipped",
            progress={"reason": reason, **(progress or {})},
            error=None,
            completed_at=datetime.now(UTC),
        )

    async def list(self, paper_id: str) -> list[PaperPipelineStage]:
        rows = list(
            await self._session.scalars(
                select(PaperPipelineStageRecord).where(
                    PaperPipelineStageRecord.paper_id == paper_id
                )
            )
        )
        by_name = {row.stage: row for row in rows}
        ordered = [by_name[name] for name in PIPELINE_STAGE_ORDER if name in by_name]
        ordered.extend(row for row in rows if row.stage not in PIPELINE_STAGE_ORDER)
        return [self._projection(row) for row in ordered]

    async def _record(self, paper_id: str, stage: str) -> PaperPipelineStageRecord:
        record = await self._session.get(
            PaperPipelineStageRecord, {"paper_id": paper_id, "stage": stage}
        )
        if record is None:
            record = PaperPipelineStageRecord(paper_id=paper_id, stage=stage)
            self._session.add(record)
            await self._session.flush()
        return record

    async def _upsert(
        self,
        paper_id: str,
        stage: str,
        **values: Any,
    ) -> None:
        await self._session.execute(
            insert(PaperPipelineStageRecord)
            .values(paper_id=paper_id, stage=stage, **values)
            .on_conflict_do_update(
                index_elements=["paper_id", "stage"],
                set_=values,
            )
        )
        await self._session.commit()

    @staticmethod
    def _projection(record: PaperPipelineStageRecord) -> PaperPipelineStage:
        duration_ms = None
        if record.started_at and record.completed_at:
            duration_ms = max(
                0, int((record.completed_at - record.started_at).total_seconds() * 1_000)
            )
        return PaperPipelineStage(
            name=record.stage,
            status=record.status,  # type: ignore[arg-type]
            attempt=record.attempt,
            revision=record.revision,
            progress=record.progress,
            error=record.error,
            started_at=record.started_at,
            completed_at=record.completed_at,
            duration_ms=duration_ms,
        )
