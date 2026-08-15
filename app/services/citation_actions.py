from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import SOURCE_SEARCH_VERSION
from app.database.models import (
    CitationAuditFindingRecord,
    CitationAuditRecord,
    CitationFeedbackRecord,
    CitationImprovementCandidateRecord,
    CitationSourceCandidateRecord,
    ClaimCitationReviewRecord,
    ConfirmedCitationRecord,
    PaperRecord,
    ScholarlyWorkRecord,
)
from app.repositories.citation_audits import CitationAuditRepository
from app.repositories.papers import PaperDocumentRepository
from app.schemas.documents import EditProposal
from app.schemas.paper import Paper
from app.services.manuscript_revisions import (
    ManuscriptEditPlanner,
    ManuscriptRevisionService,
)
from app.services.source_search import (
    CitationSourceSearcher,
    SourceClaim,
    SourceSupportVerifier,
)


CitationTarget = Literal["missing", "existing"]
CitationAction = Literal["add", "supplement", "replace", "remove", "update_metadata"]


class CitationActionService:
    """Inspect, discover, and propose citation changes through one safe interface."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        searcher: CitationSourceSearcher,
        verifier: SourceSupportVerifier,
        planner: ManuscriptEditPlanner,
    ) -> None:
        self._session_factory = session_factory
        self._searcher = searcher
        self._verifier = verifier
        self._planner = planner

    async def authoritative_paper(self, paper_id: str) -> Paper:
        async with self._session_factory() as session:
            return (await PaperDocumentRepository(session).get(paper_id)).paper

    async def existing_review(
        self,
        paper_id: str,
        *,
        classification: str | None = None,
        finding_id: str | None = None,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            paper_record = await session.get(PaperRecord, paper_id)
            if paper_record is None:
                return {"error": "The paper was not found."}
            statement = select(ClaimCitationReviewRecord).where(
                ClaimCitationReviewRecord.paper_id == paper_id,
                ClaimCitationReviewRecord.paper_revision
                == paper_record.manuscript_revision,
            )
            if finding_id:
                statement = statement.where(ClaimCitationReviewRecord.id == finding_id)
            if classification:
                statement = statement.where(
                    ClaimCitationReviewRecord.classification == classification
                )
            rows = list(
                await session.scalars(
                    statement.order_by(
                        ClaimCitationReviewRecord.priority_score.desc().nullslast(),
                        ClaimCitationReviewRecord.section_id,
                    )
                )
            )
        findings = [
            {
                "id": row.id,
                "section": row.section_title,
                "paragraphId": row.paragraph_id,
                "sentenceId": row.sentence_id,
                "citationId": row.citation_id,
                "referenceId": row.reference_id,
                "claim": row.claim_text,
                "citationText": row.citation_text,
                "workTitle": row.work_title,
                "sourceUrl": row.source_url,
                "classification": row.classification,
                "confidence": row.confidence,
                "explanation": row.explanation,
                "evidence": row.evidence_text,
            }
            for row in rows
        ]
        counts = {
            key: sum(item["classification"] == key for item in findings)
            for key in ("supported", "weak", "contradicted", "unverifiable")
        }
        return {"count": len(findings), "counts": counts, "findings": findings}

    async def candidates(
        self,
        paper_id: str,
        *,
        target: CitationTarget,
        finding_id: str,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            if target == "missing":
                finding = await self._missing_finding(session, paper_id, finding_id)
                if finding is None:
                    return {"error": "The missing-citation finding was not found."}
                rows = list(
                    (
                        await session.execute(
                            select(CitationSourceCandidateRecord, ScholarlyWorkRecord)
                            .join(
                                ScholarlyWorkRecord,
                                ScholarlyWorkRecord.id
                                == CitationSourceCandidateRecord.work_id,
                            )
                            .where(
                                CitationSourceCandidateRecord.finding_id == finding_id
                            )
                            .order_by(CitationSourceCandidateRecord.rank)
                        )
                    ).tuples()
                )
                status = finding.source_search_status
            else:
                review = await self._existing_finding(session, paper_id, finding_id)
                if review is None:
                    return {"error": "The existing-citation finding was not found."}
                rows = list(
                    (
                        await session.execute(
                            select(
                                CitationImprovementCandidateRecord,
                                ScholarlyWorkRecord,
                            )
                            .join(
                                ScholarlyWorkRecord,
                                ScholarlyWorkRecord.id
                                == CitationImprovementCandidateRecord.work_id,
                            )
                            .where(
                                CitationImprovementCandidateRecord.review_finding_id
                                == finding_id
                            )
                            .order_by(CitationImprovementCandidateRecord.rank)
                        )
                    ).tuples()
                )
                status = "completed" if rows else "not_started"
        return {
            "target": target,
            "findingId": finding_id,
            "status": status,
            "candidates": [self._candidate_payload(candidate, work) for candidate, work in rows],
        }

    async def opportunities(
        self,
        paper_id: str,
        *,
        section: str | None = None,
        topic: str | None = None,
        limit: int = 3,
    ) -> dict[str, Any]:
        """Resolve broad section/topic requests to exact audited claim anchors."""

        bounded_limit = max(1, min(limit, 5))
        async with self._session_factory() as session:
            rows = list(
                await session.scalars(
                    select(CitationAuditFindingRecord)
                    .join(
                        CitationAuditRecord,
                        CitationAuditRecord.id == CitationAuditFindingRecord.audit_id,
                    )
                    .where(CitationAuditRecord.paper_id == paper_id)
                    .order_by(
                        CitationAuditFindingRecord.confidence.desc(),
                        CitationAuditFindingRecord.revision,
                    )
                )
            )
            finding_ids = [row.id for row in rows]
            confirmed = set(
                await session.scalars(
                    select(ConfirmedCitationRecord.finding_id).where(
                        ConfirmedCitationRecord.paper_id == paper_id,
                        ConfirmedCitationRecord.status == "accepted",
                    )
                )
            )
            feedback = (
                list(
                    await session.scalars(
                        select(CitationFeedbackRecord)
                        .where(CitationFeedbackRecord.finding_id.in_(finding_ids))
                        .order_by(
                            CitationFeedbackRecord.created_at,
                            CitationFeedbackRecord.id,
                        )
                    )
                )
                if finding_ids
                else []
            )
        latest_feedback = {item.finding_id: item.feedback for item in feedback}
        ranked = rank_opportunities(
            [
                row
                for row in rows
                if row.id not in confirmed
                and latest_feedback.get(row.id) != "false_positive"
            ],
            section=section,
            topic=topic,
        )[:bounded_limit]
        results: list[dict[str, Any]] = []
        for finding in ranked:
            candidate_result = await self.candidates(
                paper_id,
                target="missing",
                finding_id=finding.id,
            )
            candidates = candidate_result.get("candidates", [])
            if not any(
                item.get("supportStatus") == "verified"
                and item.get("supportsClaim") is True
                for item in candidates
            ):
                candidate_result = await self.search(
                    paper_id,
                    target="missing",
                    finding_id=finding.id,
                )
                candidates = candidate_result.get("candidates", [])
            results.append(
                {
                    "findingId": finding.id,
                    "sectionId": finding.section_id,
                    "section": finding.section_title,
                    "paragraphId": finding.paragraph_id,
                    "claim": finding.claim_text,
                    "confidence": finding.confidence,
                    "candidates": candidates,
                }
            )
        return {
            "status": "ready" if results else "no_findings",
            "section": section,
            "topic": topic,
            "count": len(results),
            "opportunities": results,
            "instruction": (
                "Use an exact findingId and verified candidateId to propose one citation at a time."
                if results
                else "No open audited claim matched this scope; do not invent a citation."
            ),
        }

    async def search(
        self,
        paper_id: str,
        *,
        target: CitationTarget,
        finding_id: str,
    ) -> dict[str, Any]:
        paper = await self.authoritative_paper(paper_id)
        async with self._session_factory() as session:
            if target == "missing":
                finding = await self._missing_finding(session, paper_id, finding_id)
                if finding is None:
                    return {"error": "The missing-citation finding was not found."}
                claim = SourceClaim(
                    claim_text=finding.claim_text,
                    section_title=finding.section_title,
                    paragraph_id=finding.paragraph_id,
                )
            else:
                review = await self._existing_finding(session, paper_id, finding_id)
                if review is None:
                    return {"error": "The existing-citation finding was not found."}
                claim = SourceClaim(
                    claim_text=review.claim_text,
                    section_title=review.section_title,
                    paragraph_id=review.paragraph_id,
                )

        results = await self._searcher.search(paper, claim)
        async with self._session_factory() as session:
            if target == "missing":
                repository = CitationAuditRepository(session)
                await repository.replace_source_candidates(
                    finding_id,
                    [(item.work_id, item.score, item.reason) for item in results],
                )
                rows = list(
                    (
                        await session.execute(
                            select(CitationSourceCandidateRecord, ScholarlyWorkRecord)
                            .join(
                                ScholarlyWorkRecord,
                                ScholarlyWorkRecord.id
                                == CitationSourceCandidateRecord.work_id,
                            )
                            .where(
                                CitationSourceCandidateRecord.finding_id == finding_id
                            )
                            .order_by(CitationSourceCandidateRecord.rank)
                        )
                    ).tuples()
                )
                decisions = [
                    (
                        candidate.id,
                        await self._verifier.verify(
                            claim.claim_text, work.title, work.abstract
                        ),
                    )
                    for candidate, work in rows
                ]
                await repository.update_candidate_supports(decisions)
                await repository.complete_source_search(
                    finding_id, source_search_version=SOURCE_SEARCH_VERSION
                )
            else:
                await session.execute(
                    delete(CitationImprovementCandidateRecord).where(
                        CitationImprovementCandidateRecord.review_finding_id
                        == finding_id
                    )
                )
                works = {
                    work.id: work
                    for work in await session.scalars(
                        select(ScholarlyWorkRecord).where(
                            ScholarlyWorkRecord.id.in_(
                                [item.work_id for item in results]
                            )
                        )
                    )
                }
                for rank, result in enumerate(results, start=1):
                    work = works.get(result.work_id)
                    if work is None:
                        continue
                    decision = await self._verifier.verify(
                        claim.claim_text, work.title, work.abstract
                    )
                    session.add(
                        CitationImprovementCandidateRecord(
                            id=str(uuid.uuid4()),
                            review_finding_id=finding_id,
                            work_id=work.id,
                            rank=rank,
                            score=result.score,
                            reason=result.reason,
                            support_status=(
                                "verified" if decision.supports_claim else "rejected"
                            ),
                            supports_claim=decision.supports_claim,
                            support_confidence=decision.confidence,
                            support_explanation=decision.explanation[:500],
                            support_evidence=decision.evidence[:300],
                        )
                    )
                await session.commit()
        return await self.candidates(
            paper_id, target=target, finding_id=finding_id
        )

    async def propose(
        self,
        paper_id: str,
        *,
        action: CitationAction,
        target: CitationTarget,
        finding_id: str,
        candidate_id: str | None = None,
    ) -> EditProposal | dict[str, str]:
        async with self._session_factory() as session:
            revisions = ManuscriptRevisionService(session, self._planner)
            if target == "missing":
                if action == "add" and candidate_id:
                    return await revisions.propose_verified_source(
                        paper_id, finding_id, candidate_id
                    )
                if action == "remove" and candidate_id:
                    return await revisions.propose_verified_source_removal(
                        paper_id, finding_id, candidate_id
                    )
                return {
                    "error": "Missing citations support add or remove with a candidate_id."
                }
            return await revisions.propose_citation_improvement(
                paper_id,
                finding_id,
                action=action,
                candidate_id=candidate_id,
            )

    async def active_proposal(self, paper_id: str) -> EditProposal | None:
        async with self._session_factory() as session:
            proposal = await ManuscriptRevisionService(
                session, self._planner
            ).latest_proposal(paper_id)
            return proposal if proposal and proposal.status == "planned" else None

    @staticmethod
    async def _missing_finding(
        session: AsyncSession, paper_id: str, finding_id: str
    ) -> CitationAuditFindingRecord | None:
        return await session.scalar(
            select(CitationAuditFindingRecord)
            .join(
                CitationAuditRecord,
                CitationAuditRecord.id == CitationAuditFindingRecord.audit_id,
            )
            .where(
                CitationAuditFindingRecord.id == finding_id,
                CitationAuditRecord.paper_id == paper_id,
            )
        )

    @staticmethod
    async def _existing_finding(
        session: AsyncSession, paper_id: str, finding_id: str
    ) -> ClaimCitationReviewRecord | None:
        paper = await session.get(PaperRecord, paper_id)
        if paper is None:
            return None
        return await session.scalar(
            select(ClaimCitationReviewRecord).where(
                ClaimCitationReviewRecord.id == finding_id,
                ClaimCitationReviewRecord.paper_id == paper_id,
                ClaimCitationReviewRecord.paper_revision == paper.manuscript_revision,
            )
        )

    @staticmethod
    def _candidate_payload(candidate: Any, work: ScholarlyWorkRecord) -> dict[str, Any]:
        return {
            "candidateId": candidate.id,
            "workId": work.id,
            "title": work.title,
            "year": work.year,
            "url": work.landing_page_url,
            "doi": work.doi,
            "arxivId": work.arxiv_id,
            "providers": sorted(work.provider_ids),
            "rank": candidate.rank,
            "score": candidate.score,
            "reason": candidate.reason,
            "supportStatus": candidate.support_status,
            "supportsClaim": candidate.supports_claim,
            "supportConfidence": candidate.support_confidence,
            "supportExplanation": candidate.support_explanation,
            "supportEvidence": candidate.support_evidence,
            "decision": candidate.decision,
        }


def rank_opportunities(
    findings: list[CitationAuditFindingRecord],
    *,
    section: str | None,
    topic: str | None,
) -> list[CitationAuditFindingRecord]:
    section_query = (section or "").casefold().strip()
    topic_tokens = {
        token
        for token in (topic or "").casefold().replace("-", " ").split()
        if len(token) > 2
    }
    scored: list[tuple[float, CitationAuditFindingRecord]] = []
    for finding in findings:
        section_text = f"{finding.section_id} {finding.section_title}".casefold()
        if section_query and section_query not in section_text:
            continue
        haystack = f"{finding.section_title} {finding.claim_text}".casefold()
        overlap = sum(token in haystack for token in topic_tokens)
        if topic_tokens and overlap == 0:
            continue
        score = float(finding.confidence) + overlap
        if section_query and section_query == finding.section_title.casefold():
            score += 2
        scored.append((score, finding))
    return [
        finding
        for _score, finding in sorted(
            scored,
            key=lambda item: (-item[0], item[1].revision, item[1].id),
        )
    ]
