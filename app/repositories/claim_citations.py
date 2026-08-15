from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    ClaimCitationReviewRecord,
    PaperRecord,
    ReferenceEnrichmentRecord,
    ScholarlyWorkRecord,
)
from app.schemas.documents import ClaimCitationFinding


@dataclass(frozen=True)
class ReferenceEvidence:
    reference_id: str
    work_id: str | None
    title: str | None
    abstract: str | None
    source_url: str | None
    providers: list[str]
    payloads: dict[str, Any]


class ClaimCitationReviewRepository:
    """Persist claim/source pairs and expose only review-ready projections."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reference_evidence(self, paper_id: str) -> dict[str, ReferenceEvidence]:
        rows = await self._session.execute(
            select(ReferenceEnrichmentRecord, ScholarlyWorkRecord)
            .outerjoin(
                ScholarlyWorkRecord,
                ScholarlyWorkRecord.id == ReferenceEnrichmentRecord.work_id,
            )
            .where(ReferenceEnrichmentRecord.paper_id == paper_id)
        )
        evidence: dict[str, ReferenceEvidence] = {}
        for enrichment, work in rows.tuples():
            payload = enrichment.work_json or {}
            providers = list((work.provider_ids if work else {}).keys())
            evidence[enrichment.reference_id] = ReferenceEvidence(
                reference_id=enrichment.reference_id,
                work_id=work.id if work else enrichment.work_id,
                title=(work.title if work else payload.get("title")),
                abstract=(work.abstract if work else payload.get("abstract")),
                source_url=(work.landing_page_url if work else payload.get("landingPageUrl")),
                providers=providers or ([enrichment.provider] if enrichment.status == "matched" else []),
                payloads=work.provider_payloads if work else {enrichment.provider: payload},
            )
        return evidence

    async def save(self, values: dict[str, Any]) -> None:
        statement = insert(ClaimCitationReviewRecord).values(**values)
        excluded = statement.excluded
        await self._session.execute(
            statement.on_conflict_do_update(
                constraint="uq_claim_citation_review_pair",
                set_={
                    "citation_id": excluded.citation_id,
                    "claim_text": excluded.claim_text,
                    "citation_text": excluded.citation_text,
                    "work_id": excluded.work_id,
                    "work_title": excluded.work_title,
                    "source_url": excluded.source_url,
                    "provider_evidence": excluded.provider_evidence,
                    "priority_score": excluded.priority_score,
                    "classification": excluded.classification,
                    "confidence": excluded.confidence,
                    "explanation": excluded.explanation,
                    "evidence_text": excluded.evidence_text,
                    "model": excluded.model,
                    "status": excluded.status,
                },
            )
        )
        await self._session.commit()

    async def list(self, paper_id: str) -> list[ClaimCitationFinding]:
        paper = await self._session.get(PaperRecord, paper_id)
        if paper is None:
            return []
        rows = list(
            await self._session.scalars(
                select(ClaimCitationReviewRecord)
                .where(
                    ClaimCitationReviewRecord.paper_id == paper_id,
                    ClaimCitationReviewRecord.paper_revision
                    == paper.manuscript_revision,
                )
                .order_by(
                    ClaimCitationReviewRecord.priority_score.desc().nullslast(),
                    ClaimCitationReviewRecord.section_id,
                )
            )
        )
        return [
            ClaimCitationFinding(
                id=row.id,
                sentence_id=row.sentence_id,
                section_id=row.section_id,
                section_title=row.section_title,
                paragraph_id=row.paragraph_id,
                citation_id=row.citation_id,
                reference_id=row.reference_id,
                claim_text=row.claim_text,
                citation_text=row.citation_text,
                work_title=row.work_title,
                source_url=row.source_url,
                providers=list(row.provider_evidence.get("providers", [])),
                priority_score=row.priority_score,
                classification=row.classification,  # type: ignore[arg-type]
                confidence=row.confidence,
                explanation=row.explanation,
                evidence_text=row.evidence_text,
            )
            for row in rows
        ]
