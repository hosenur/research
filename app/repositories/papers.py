from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ManuscriptRevisionRecord, PaperRecord, ReferenceEnrichmentRecord
from app.exceptions import PaperDocumentNotFoundError, PaperDocumentNotReadyError
from app.schemas.documents import PaperDocument, PaperLifecycle, ReferenceEnrichmentUpdate
from app.schemas.paper import OpenAlexWork, Paper, Reference
from app.services.paper_index import current_index_kind


class PaperDocumentRepository:
    """Persist immutable parse output and merge provider enrichments by reference ID."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, filename: str, paper: Paper) -> PaperDocument:
        payload = paper.model_dump(mode="json", by_alias=True)
        extraction_hash = paper.extraction.pdf_sha256 if paper.extraction else None
        content_hash = extraction_hash or hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        record = PaperRecord(
            id=str(uuid.uuid4()),
            filename=filename,
            content_sha256=content_hash,
            paper_json=payload,
            status="ready",
            parse_completed_at=datetime.now(UTC),
            revision=1,
        )
        self._session.add(record)
        # The revision references the newly-created paper. Flush the parent first;
        # these models intentionally have no ORM relationship for SQLAlchemy to
        # infer insert ordering from.
        await self._session.flush()
        self._session.add(
            ManuscriptRevisionRecord(
                id=str(uuid.uuid4()),
                paper_id=record.id,
                revision=1,
                parent_revision=None,
                paper_json=payload,
                content_hash=content_hash,
                source="parse",
                summary="Authoritative parse",
            )
        )
        await self._session.commit()
        return PaperDocument(id=record.id, revision=record.revision, paper=paper)

    async def create_pending(
        self,
        *,
        paper_id: str,
        filename: str,
        content_sha256: str,
        source_object_key: str,
    ) -> PaperLifecycle:
        record = PaperRecord(
            id=paper_id,
            filename=filename,
            content_sha256=content_sha256,
            paper_json=None,
            status="uploaded",
            source_object_key=source_object_key,
            revision=1,
        )
        self._session.add(record)
        await self._session.commit()
        return self._lifecycle(record)

    async def get_lifecycle(self, paper_id: str) -> PaperLifecycle:
        record = await self._get_record(paper_id)
        paper: Paper | None = None
        if record.paper_json is not None:
            enrichments = await self.list_enrichments(paper_id)
            paper = self._merge(await self._current_paper(record), enrichments)
        retrieval_mode = await current_index_kind(self._session, paper_id)
        return self._lifecycle(record, paper=paper, retrieval_mode=retrieval_mode)

    async def begin_parse(self, paper_id: str) -> PaperLifecycle:
        record = await self._get_record_for_update(paper_id)
        if record.status != "ready":
            record.status = "parsing"
            record.parse_error = None
            record.parse_started_at = datetime.now(UTC)
            await self._session.commit()
        return self._lifecycle(record)

    async def complete_parse(self, paper_id: str, paper: Paper) -> PaperDocument:
        record = await self._get_record_for_update(paper_id)
        record.paper_json = paper.model_dump(mode="json", by_alias=True)
        record.status = "ready"
        record.parse_error = None
        record.parse_completed_at = datetime.now(UTC)
        record.page_count = (
            paper.extraction.preflight.page_count if paper.extraction else None
        )
        existing_revision = await self._session.scalar(
            select(ManuscriptRevisionRecord).where(
                ManuscriptRevisionRecord.paper_id == paper_id,
                ManuscriptRevisionRecord.revision == 1,
            )
        )
        if existing_revision is None:
            payload = paper.model_dump(mode="json", by_alias=True)
            self._session.add(
                ManuscriptRevisionRecord(
                    id=str(uuid.uuid4()),
                    paper_id=paper_id,
                    revision=1,
                    parent_revision=None,
                    paper_json=payload,
                    content_hash=hashlib.sha256(
                        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                    source="parse",
                    summary="Authoritative parse",
                )
            )
        await self._session.commit()
        return PaperDocument(id=record.id, revision=record.revision, paper=paper)

    async def fail_parse(self, paper_id: str, error: str) -> None:
        record = await self._get_record_for_update(paper_id)
        if record.status != "ready":
            record.status = "failed"
            record.parse_error = error[:4_000]
            await self._session.commit()

    async def source(self, paper_id: str) -> tuple[str, str]:
        record = await self._get_record(paper_id)
        if not record.source_object_key:
            raise PaperDocumentNotFoundError("The source PDF was not persisted.")
        return record.filename, record.source_object_key

    async def get(self, paper_id: str) -> PaperDocument:
        record = await self._get_record(paper_id)
        if record.paper_json is None or record.status != "ready":
            raise PaperDocumentNotReadyError(
                "The paper is still being parsed. Retry when its lifecycle is ready."
            )
        enrichments = await self.list_enrichments(paper_id)
        paper = self._merge(await self._current_paper(record), enrichments)
        return PaperDocument(id=record.id, revision=record.revision, paper=paper)

    async def list_enrichments(self, paper_id: str) -> list[ReferenceEnrichmentRecord]:
        result = await self._session.execute(
            select(ReferenceEnrichmentRecord)
            .where(ReferenceEnrichmentRecord.paper_id == paper_id)
            .order_by(ReferenceEnrichmentRecord.revision)
        )
        return list(result.scalars())

    async def list_updates(
        self,
        paper_id: str,
        *,
        after_revision: int = 0,
    ) -> list[ReferenceEnrichmentUpdate]:
        await self._get_record(paper_id)
        result = await self._session.execute(
            select(ReferenceEnrichmentRecord)
            .where(
                ReferenceEnrichmentRecord.paper_id == paper_id,
                ReferenceEnrichmentRecord.revision > after_revision,
            )
            .order_by(ReferenceEnrichmentRecord.revision)
        )
        return [self._update_from_record(record) for record in result.scalars()]

    async def save_reference_enrichment(
        self,
        paper_id: str,
        reference: Reference,
        *,
        provider: str = "openalex",
        work_id: str | None = None,
    ) -> int:
        paper_record = await self._session.scalar(
            select(PaperRecord).where(PaperRecord.id == paper_id).with_for_update()
        )
        if paper_record is None:
            raise PaperDocumentNotFoundError("The parsed paper was not found.")

        paper_record.revision += 1
        key = {
            "paper_id": paper_id,
            "reference_id": reference.id,
            "provider": provider,
        }
        record = await self._session.get(ReferenceEnrichmentRecord, key)
        if record is None:
            record = ReferenceEnrichmentRecord(**key, status=reference.openalex_status or "error")
            self._session.add(record)

        record.status = reference.openalex_status or "error"
        record.work_id = work_id
        record.work_json = (
            reference.openalex.model_dump(mode="json", by_alias=True)
            if reference.openalex
            else None
        )
        record.match_method = reference.openalex.match_method if reference.openalex else None
        record.confidence = reference.openalex.confidence if reference.openalex else None
        record.error = reference.openalex_error
        record.revision = paper_record.revision
        await self._session.commit()
        return paper_record.revision

    async def _get_record(self, paper_id: str) -> PaperRecord:
        record = await self._session.get(PaperRecord, paper_id)
        if record is None:
            raise PaperDocumentNotFoundError("The parsed paper was not found.")
        return record

    async def _get_record_for_update(self, paper_id: str) -> PaperRecord:
        record = await self._session.scalar(
            select(PaperRecord).where(PaperRecord.id == paper_id).with_for_update()
        )
        if record is None:
            raise PaperDocumentNotFoundError("The parsed paper was not found.")
        return record

    async def _current_paper(self, record: PaperRecord) -> Paper:
        if record.manuscript_revision <= 1:
            return Paper.model_validate(record.paper_json)
        revision = await self._session.scalar(
            select(ManuscriptRevisionRecord).where(
                ManuscriptRevisionRecord.paper_id == record.id,
                ManuscriptRevisionRecord.revision == record.manuscript_revision,
            )
        )
        payload = revision.paper_json if revision else record.paper_json
        return Paper.model_validate(payload)

    @staticmethod
    def _lifecycle(
        record: PaperRecord,
        *,
        paper: Paper | None = None,
        retrieval_mode: str = "unavailable",
    ) -> PaperLifecycle:
        return PaperLifecycle(
            id=record.id,
            filename=record.filename,
            status=record.status,  # type: ignore[arg-type]
            revision=record.revision,
            manuscript_revision=record.manuscript_revision,
            paper=paper,
            error=record.parse_error,
            source_url=f"/papers/{record.id}/source",
            retrieval_mode=retrieval_mode,  # type: ignore[arg-type]
        )

    @staticmethod
    def _merge(
        paper: Paper,
        enrichments: list[ReferenceEnrichmentRecord],
    ) -> Paper:
        by_reference = {record.reference_id: record for record in enrichments}
        for reference in paper.references:
            record = by_reference.get(reference.id)
            if record is None:
                continue
            reference.openalex_status = record.status  # type: ignore[assignment]
            reference.openalex_error = record.error
            reference.openalex = (
                OpenAlexWork.model_validate(record.work_json) if record.work_json else None
            )
        return paper

    @staticmethod
    def _update_from_record(record: ReferenceEnrichmentRecord) -> ReferenceEnrichmentUpdate:
        return ReferenceEnrichmentUpdate(
            reference_id=record.reference_id,
            status=record.status,  # type: ignore[arg-type]
            openalex=OpenAlexWork.model_validate(record.work_json) if record.work_json else None,
            error=record.error,
            revision=record.revision,
        )
