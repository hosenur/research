from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PaperRecord, ReferenceEnrichmentRecord
from app.exceptions import PaperDocumentNotFoundError
from app.schemas.documents import PaperDocument, ReferenceEnrichmentUpdate
from app.schemas.paper import OpenAlexWork, Paper, Reference


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
            revision=1,
        )
        self._session.add(record)
        await self._session.commit()
        return PaperDocument(id=record.id, revision=record.revision, paper=paper)

    async def get(self, paper_id: str) -> PaperDocument:
        record = await self._get_record(paper_id)
        enrichments = await self.list_enrichments(paper_id)
        paper = self._merge(Paper.model_validate(record.paper_json), enrichments)
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
