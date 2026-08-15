from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ManuscriptRevisionRecord, PaperRecord, ReferenceEnrichmentRecord
from app.exceptions import PaperDocumentNotFoundError, PaperDocumentNotReadyError
from app.schemas.documents import (
    EnrichmentProgress,
    PaperDocument,
    PaperLifecycle,
    ReferenceEnrichmentUpdate,
)
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

    async def list_enrichments(
        self,
        paper_id: str,
        *,
        provider: str = "openalex",
    ) -> list[ReferenceEnrichmentRecord]:
        result = await self._session.execute(
            select(ReferenceEnrichmentRecord)
            .where(
                ReferenceEnrichmentRecord.paper_id == paper_id,
                ReferenceEnrichmentRecord.provider == provider,
            )
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
                ReferenceEnrichmentRecord.provider == "openalex",
                ReferenceEnrichmentRecord.revision > after_revision,
            )
            .order_by(ReferenceEnrichmentRecord.revision)
        )
        return [self._update_from_record(record) for record in result.scalars()]

    async def hydrate_cached_reference_enrichments(self, paper_id: str) -> int:
        """Reuse stable provider decisions for the same scholarly reference."""
        target = await self._get_record_for_update(paper_id)
        if target.paper_json is None:
            await self._session.rollback()
            return 0

        target_paper = Paper.model_validate(target.paper_json)
        target_references = _unique_reference_keys(target_paper)
        if not target_references:
            await self._session.rollback()
            return 0

        existing = {
            (reference_id, provider)
            for reference_id, provider in (
                await self._session.execute(
                    select(
                        ReferenceEnrichmentRecord.reference_id,
                        ReferenceEnrichmentRecord.provider,
                    ).where(ReferenceEnrichmentRecord.paper_id == paper_id)
                )
            ).tuples()
        }
        missing_keys = {
            (reference_id, provider)
            for reference_id in target_references.values()
            for provider in ("openalex", "semantic-scholar")
            if (reference_id, provider) not in existing
        }
        if not missing_keys:
            await self._session.rollback()
            return 0

        result = await self._session.execute(
            select(
                PaperRecord.id,
                PaperRecord.paper_json,
                ReferenceEnrichmentRecord,
            )
            .join(
                ReferenceEnrichmentRecord,
                ReferenceEnrichmentRecord.paper_id == PaperRecord.id,
            )
            .where(
                PaperRecord.id != paper_id,
                PaperRecord.status == "ready",
                PaperRecord.paper_json.is_not(None),
            )
            .order_by(
                case((PaperRecord.content_sha256 == target.content_sha256, 0), else_=1),
                ReferenceEnrichmentRecord.updated_at.desc(),
            )
        )

        source_reference_keys: dict[str, dict[str, str]] = {}
        cached: dict[tuple[str, str], ReferenceEnrichmentRecord] = {}
        for source_paper_id, source_payload, enrichment in result.tuples():
            if enrichment.status == "error":
                continue
            if source_paper_id not in source_reference_keys:
                try:
                    source_paper = Paper.model_validate(source_payload)
                except (TypeError, ValueError):
                    source_reference_keys[source_paper_id] = {}
                else:
                    source_reference_keys[source_paper_id] = {
                        reference_id: key
                        for key, reference_id in _unique_reference_keys(
                            source_paper
                        ).items()
                    }
            identity_key = source_reference_keys[source_paper_id].get(
                enrichment.reference_id
            )
            target_reference_id = target_references.get(identity_key or "")
            target_key = (target_reference_id or "", enrichment.provider)
            if not target_reference_id or target_key not in missing_keys:
                continue
            cached.setdefault(target_key, enrichment)

        for (reference_id, provider), source in cached.items():
            target.revision += 1
            self._session.add(
                ReferenceEnrichmentRecord(
                    paper_id=paper_id,
                    reference_id=reference_id,
                    provider=provider,
                    work_id=source.work_id,
                    status=source.status,
                    work_json=source.work_json,
                    match_method=source.match_method,
                    confidence=source.confidence,
                    error=source.error,
                    revision=target.revision,
                )
            )
        if not cached:
            await self._session.rollback()
            return 0
        await self._session.commit()
        return len(cached)

    async def reference_enrichment_progress(
        self,
        paper_id: str,
        *,
        total: int,
    ) -> EnrichmentProgress:
        records = list(
            await self._session.scalars(
                select(ReferenceEnrichmentRecord).where(
                    ReferenceEnrichmentRecord.paper_id == paper_id
                )
            )
        )
        grouped: dict[str, list[ReferenceEnrichmentRecord]] = {}
        for record in records:
            grouped.setdefault(record.reference_id, []).append(record)
        complete = [
            group
            for group in grouped.values()
            if {record.provider for record in group}
            >= {"openalex", "semantic-scholar"}
        ]
        outcomes = [_enrichment_outcome(group) for group in complete]
        return EnrichmentProgress(
            total=total,
            completed=len(complete),
            matched=outcomes.count("matched"),
            unmatched=outcomes.count("unmatched"),
            failed=outcomes.count("failed"),
            skipped=outcomes.count("skipped"),
        )

    async def save_reference_enrichment(
        self,
        paper_id: str,
        reference: Reference,
        *,
        provider: str = "openalex",
        work_id: str | None = None,
    ) -> int:
        return await self.save_provider_enrichment(
            paper_id,
            reference.id,
            provider=provider,
            work_id=work_id,
            status=reference.openalex_status or "error",
            work_json=(
                reference.openalex.model_dump(mode="json", by_alias=True)
                if reference.openalex
                else None
            ),
            match_method=(reference.openalex.match_method if reference.openalex else None),
            confidence=(reference.openalex.confidence if reference.openalex else None),
            error=reference.openalex_error,
        )

    async def save_provider_enrichment(
        self,
        paper_id: str,
        reference_id: str,
        *,
        provider: str,
        work_id: str | None,
        status: str,
        work_json: dict | None,
        match_method: str | None,
        confidence: str | None,
        error: str | None,
    ) -> int:
        paper_record = await self._session.scalar(
            select(PaperRecord).where(PaperRecord.id == paper_id).with_for_update()
        )
        if paper_record is None:
            raise PaperDocumentNotFoundError("The parsed paper was not found.")

        paper_record.revision += 1
        key = {
            "paper_id": paper_id,
            "reference_id": reference_id,
            "provider": provider,
        }
        record = await self._session.get(ReferenceEnrichmentRecord, key)
        if record is None:
            record = ReferenceEnrichmentRecord(**key, status=status)
            self._session.add(record)

        record.status = status
        record.work_id = work_id
        record.work_json = work_json
        record.match_method = match_method
        record.confidence = confidence
        record.error = error
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


def _unique_reference_keys(paper: Paper) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for reference in paper.references:
        key = _reference_cache_key(reference)
        if key:
            grouped.setdefault(key, []).append(reference.id)
    return {
        key: reference_ids[0]
        for key, reference_ids in grouped.items()
        if len(reference_ids) == 1
    }


def _enrichment_outcome(records: list[ReferenceEnrichmentRecord]) -> str:
    statuses = {record.status for record in records}
    if "ambiguous" in statuses:
        return "failed"
    if "matched" in statuses:
        return "matched"
    if "unmatched" in statuses:
        return "unmatched"
    if statuses == {"skipped"}:
        return "skipped"
    return "failed"


def _reference_cache_key(reference: Reference) -> str:
    identifiers = reference.raw_fields.get("identifiers")
    identifiers = identifiers if isinstance(identifiers, dict) else {}
    doi = (reference.csl.doi if reference.csl else None) or identifiers.get("doi")
    if isinstance(doi, str) and doi.strip():
        normalized = re.sub(
            r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)",
            "",
            doi.strip(),
            flags=re.I,
        ).rstrip(".").lower()
        if normalized:
            return f"doi:{normalized}"

    arxiv = (
        (reference.csl.archive_location if reference.csl else None)
        or identifiers.get("arxiv")
    )
    if isinstance(arxiv, str) and arxiv.strip():
        normalized = re.sub(
            r"^(?:https?://arxiv\.org/(?:abs|pdf)/|arxiv:\s*)",
            "",
            arxiv.strip(),
            flags=re.I,
        )
        normalized = re.sub(r"(?:\.pdf|v\d+)$", "", normalized, flags=re.I)
        if normalized:
            return f"arxiv:{normalized.lower()}"

    title = (reference.csl.title if reference.csl else None) or reference.raw_fields.get(
        "title"
    )
    year = None
    if reference.csl and reference.csl.issued and reference.csl.issued.date_parts:
        year = reference.csl.issued.date_parts[0][0]
    authors = reference.csl.author if reference.csl else []
    author = (
        (authors[0].family or authors[0].literal)
        if authors
        else None
    )
    if isinstance(title, str) and title.strip() and year and author:
        normalized_title = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        normalized_author = re.sub(r"[^a-z0-9]+", " ", author.lower()).strip()
        if normalized_title and normalized_author:
            return f"title:{normalized_title}|{year}|{normalized_author}"

    normalized_raw = re.sub(r"\s+", " ", reference.raw_text).strip().lower()
    return (
        "raw:" + hashlib.sha256(normalized_raw.encode()).hexdigest()
        if normalized_raw
        else ""
    )
