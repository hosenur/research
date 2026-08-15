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
from app.repositories.scholarly_works import ScholarlyWorkData, works_from_response
from app.services.reference_evidence import (
    ProviderReferenceEvidence,
    ReferenceEvidenceReconciliation,
    reconcile_provider_matches,
)


@dataclass(frozen=True)
class ReferenceEvidence:
    reference_id: str
    work_id: str | None
    title: str | None
    abstract: str | None
    source_url: str | None
    providers: list[str]
    payloads: dict[str, Any]
    reconciliation_status: str
    reconciliation_reason: str
    abstract_provider: str | None
    identifier_providers: dict[str, dict[str, Any]]


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
        grouped: dict[str, list[tuple[ReferenceEnrichmentRecord, ScholarlyWorkRecord | None]]] = {}
        for enrichment, work in rows.tuples():
            grouped.setdefault(enrichment.reference_id, []).append((enrichment, work))

        evidence: dict[str, ReferenceEvidence] = {}
        for reference_id, candidates in grouped.items():
            payloads: dict[str, Any] = {}
            matches: list[ProviderReferenceEvidence] = []
            for enrichment, work in candidates:
                match = provider_match(enrichment, work)
                matches.append(match)
                payloads[enrichment.provider] = provider_evidence_payload(match)
            reconciliation = (
                ReferenceEvidenceReconciliation(
                    status="ambiguous",
                    providers=tuple(item.provider for item in matches),
                    reason=next(
                        (
                            item.error
                            for item in matches
                            if item.status == "ambiguous" and item.error
                        ),
                        "Provider matches conflict and cannot be combined.",
                    ),
                )
                if any(item.status == "ambiguous" for item in matches)
                else reconcile_provider_matches(tuple(matches))
            )
            if reconciliation.status in {"ambiguous", "unavailable"}:
                evidence[reference_id] = ReferenceEvidence(
                    reference_id=reference_id,
                    work_id=None,
                    title=None,
                    abstract=None,
                    source_url=None,
                    providers=list(reconciliation.providers),
                    payloads=payloads,
                    reconciliation_status=reconciliation.status,
                    reconciliation_reason=reconciliation.reason,
                    abstract_provider=None,
                    identifier_providers=identifier_provenance(matches),
                )
                continue
            usable = [item for item in matches if item.status == "matched"]
            selected = max(
                usable,
                key=lambda item: (
                    bool(item.abstract),
                    len(item.abstract or ""),
                    item.confidence == "high",
                ),
            )
            evidence[reference_id] = ReferenceEvidence(
                reference_id=reference_id,
                work_id=selected.work_id,
                title=selected.title,
                abstract=selected.abstract,
                source_url=selected.source_url,
                providers=list(reconciliation.providers),
                payloads=payloads,
                reconciliation_status=reconciliation.status,
                reconciliation_reason=reconciliation.reason,
                abstract_provider=selected.provider if selected.abstract else None,
                identifier_providers=identifier_provenance(usable),
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


def provider_match(
    enrichment: ReferenceEnrichmentRecord,
    work: ScholarlyWorkRecord | None,
) -> ProviderReferenceEvidence:
    provider = enrichment.provider
    raw = (
        work.provider_payloads.get(provider)
        if work and isinstance(work.provider_payloads, dict)
        else enrichment.work_json
    )
    provider_id = work.provider_ids.get(provider) if work else None
    parsed = next(
        (
            item
            for item in works_from_response(provider, raw)
            if provider_id is None or item.provider_id == provider_id
        ),
        None,
    )
    return ProviderReferenceEvidence(
        provider=provider,
        status=enrichment.status,
        work_id=enrichment.work_id,
        work_json=raw if isinstance(raw, dict) else enrichment.work_json,
        match_method=enrichment.match_method,
        confidence=enrichment.confidence,
        error=enrichment.error,
        **provider_data_projection(parsed, enrichment.work_json),
    )


def provider_data_projection(
    parsed: ScholarlyWorkData | None,
    fallback: dict[str, Any] | None,
) -> dict[str, Any]:
    if parsed:
        return {
            "provider_id": parsed.provider_id,
            "title": parsed.title,
            "abstract": parsed.abstract,
            "doi": parsed.doi,
            "arxiv_id": parsed.arxiv_id,
            "year": parsed.year,
            "authors": tuple(
                str(author.get("name") or "").strip()
                for author in parsed.authors
                if str(author.get("name") or "").strip()
            ),
            "source_url": parsed.landing_page_url,
        }
    payload = fallback or {}
    return {
        "provider_id": payload.get("id") or payload.get("paperId"),
        "title": payload.get("title"),
        "abstract": payload.get("abstract"),
        "doi": payload.get("doi") or payload.get("DOI"),
        "arxiv_id": payload.get("arxivId"),
        "year": payload.get("year"),
        "authors": tuple(
            str(author.get("name") or "").strip()
            for author in payload.get("authors") or []
            if isinstance(author, dict) and str(author.get("name") or "").strip()
        ),
        "source_url": payload.get("landingPageUrl") or payload.get("url"),
    }


def provider_evidence_payload(match: ProviderReferenceEvidence) -> dict[str, Any]:
    return {
        "providerId": match.provider_id,
        "title": match.title,
        "abstract": match.abstract,
        "abstractProvider": match.provider if match.abstract else None,
        "identifiers": {
            "doi": match.doi,
            "arxiv": match.arxiv_id,
        },
        "sourceUrl": match.source_url,
        "status": match.status,
        "matchMethod": match.match_method,
        "confidence": match.confidence,
        "raw": match.work_json,
    }


def identifier_provenance(
    matches: list[ProviderReferenceEvidence],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for field, attribute in (("doi", "doi"), ("arxiv", "arxiv_id")):
        values: dict[str, list[str]] = {}
        for match in matches:
            value = getattr(match, attribute)
            if value:
                values.setdefault(str(value), []).append(match.provider)
        if values:
            value, providers = sorted(
                values.items(), key=lambda item: (-len(item[1]), item[0])
            )[0]
            output[field] = {"value": value, "providers": sorted(providers)}
    return output
