from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    CitationAuditBatchRecord,
    CitationAuditDecisionRecord,
    CitationAuditFindingRecord,
    CitationAuditRecord,
    CitationFeedbackRecord,
    CitationSourceCandidateRecord,
    ScholarlyWorkRecord,
)
from app.schemas.documents import (
    CitationAuditFinding,
    CitationAuditProgress,
    CitationSourceCandidate,
    CitationSourceWork,
)
from app.schemas.paper import ExtractionPointer
from app.services.citation_audit import (
    AuditSentence,
    ModelDecision,
    ModelFinding,
    exact_claim_span,
    normalized_claim_hash,
)


class _CandidateSupportDecision(Protocol):
    status: str
    confidence: float
    explanation: str
    evidence: str


class CitationAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_or_get(self, paper_id: str, model: str) -> CitationAuditRecord:
        audit_id = str(uuid.uuid4())
        statement = (
            insert(CitationAuditRecord)
            .values(id=audit_id, paper_id=paper_id, model=model, status="queued")
            .on_conflict_do_nothing(index_elements=["paper_id"])
            .returning(CitationAuditRecord.id)
        )
        created_id = await self._session.scalar(statement)
        await self._session.commit()
        record = await self.get_for_paper(paper_id)
        if record is None:
            raise RuntimeError(f"Could not create citation audit {created_id or audit_id}.")
        return record

    async def get_for_paper(self, paper_id: str) -> CitationAuditRecord | None:
        return await self._session.scalar(
            select(CitationAuditRecord).where(CitationAuditRecord.paper_id == paper_id)
        )

    async def get(self, audit_id: str) -> CitationAuditRecord:
        record = await self._session.get(CitationAuditRecord, audit_id)
        if record is None:
            raise RuntimeError("The citation audit was not found.")
        return record

    async def prepare(
        self,
        audit_id: str,
        *,
        total_sentences: int,
        heuristic_candidates: int,
        priority_total: int,
        discovery_total: int,
    ) -> CitationAuditRecord:
        record = await self._locked(audit_id)
        record.status = "running"
        record.error = None
        record.total_sentences = total_sentences
        record.heuristic_candidates = heuristic_candidates
        record.priority_total = priority_total
        record.discovery_total = discovery_total
        await self._session.commit()
        return record

    async def reset(self, audit_id: str) -> CitationAuditRecord:
        audit = await self._locked(audit_id)
        await self._session.execute(delete(CitationAuditFindingRecord).where(CitationAuditFindingRecord.audit_id == audit_id))
        await self._session.execute(delete(CitationAuditDecisionRecord).where(CitationAuditDecisionRecord.audit_id == audit_id))
        await self._session.execute(delete(CitationAuditBatchRecord).where(CitationAuditBatchRecord.audit_id == audit_id))
        audit.status = "queued"
        audit.error = None
        audit.total_sentences = 0
        audit.heuristic_candidates = 0
        audit.priority_total = 0
        audit.priority_completed = 0
        audit.discovery_total = 0
        audit.discovery_completed = 0
        audit.revision += 1
        await self._session.commit()
        return audit

    async def completed_batch_keys(self, audit_id: str) -> set[tuple[str, str]]:
        result = await self._session.execute(
            select(CitationAuditBatchRecord.lane, CitationAuditBatchRecord.batch_key).where(
                CitationAuditBatchRecord.audit_id == audit_id,
                CitationAuditBatchRecord.status == "completed",
            )
        )
        return set(result.tuples())

    async def complete_batch(
        self,
        audit_id: str,
        *,
        lane: str,
        batch_key: str,
        findings: list[tuple[ModelFinding, str]],
        decisions: list[tuple[ModelDecision, str, bool]],
        sentences: list[AuditSentence],
    ) -> CitationAuditRecord:
        audit = await self._locked(audit_id)
        batch_identity = {
            "audit_id": audit_id,
            "lane": lane,
            "batch_key": batch_key,
        }
        existing_batch = await self._session.get(CitationAuditBatchRecord, batch_identity)
        if existing_batch and existing_batch.status == "completed":
            return audit

        by_id = {sentence.id: sentence for sentence in sentences}
        sentence_ids = {finding.sentence_id for finding, _model in findings}
        existing_records = list(
            await self._session.scalars(
                select(CitationAuditFindingRecord)
                .where(
                    CitationAuditFindingRecord.audit_id == audit_id,
                    CitationAuditFindingRecord.sentence_id.in_(sentence_ids),
                )
                .with_for_update()
            )
        ) if sentence_ids else []
        existing_hashes = {record.claim_hash for record in existing_records}

        inserted = 0
        for finding, model in findings:
            sentence = by_id.get(finding.sentence_id)
            relative_span = exact_claim_span(sentence.text, finding.source_text) if sentence else None
            if sentence is None or relative_span is None:
                continue
            claim_hash = normalized_claim_hash(finding.sentence_id, finding.claim_text)
            absolute_start = sentence.start_offset + relative_span[0]
            absolute_end = sentence.start_offset + relative_span[1]
            overlap = next(
                (
                    record
                    for record in existing_records
                    if record.sentence_id == sentence.id
                    and absolute_start < record.end_offset
                    and record.start_offset < absolute_end
                ),
                None,
            )
            if overlap is not None:
                changed = False
                detected_by = list(overlap.detected_by)
                if sentence.heuristic_candidate and "verbal-heuristic" not in detected_by:
                    detected_by.insert(0, "verbal-heuristic")
                    overlap.detected_by = detected_by
                    changed = True
                current_length = overlap.end_offset - overlap.start_offset
                new_length = absolute_end - absolute_start
                if new_length < current_length and (
                    claim_hash not in existing_hashes or claim_hash == overlap.claim_hash
                ):
                    existing_hashes.discard(overlap.claim_hash)
                    overlap.source_text = finding.source_text.strip()
                    overlap.claim_text = finding.claim_text.strip()
                    overlap.claim_hash = claim_hash
                    overlap.claim_type = finding.claim_type
                    overlap.confidence = finding.confidence
                    overlap.explanation = finding.explanation[:500]
                    overlap.heuristic_reasons = sentence.heuristic_reasons
                    overlap.start_offset = absolute_start
                    overlap.end_offset = absolute_end
                    overlap.source_json = sentence.source
                    overlap.model = model
                    existing_hashes.add(claim_hash)
                    changed = True
                if changed:
                    audit.revision += 1
                    overlap.revision = audit.revision
                continue
            if claim_hash in existing_hashes:
                continue
            audit.revision += 1
            detected_by = ["ai"]
            if sentence.heuristic_candidate:
                detected_by.insert(0, "verbal-heuristic")
            record = CitationAuditFindingRecord(
                    id=str(uuid.uuid4()),
                    audit_id=audit_id,
                    sentence_id=sentence.id,
                    section_id=sentence.section_id,
                    section_title=sentence.section_title,
                    paragraph_id=sentence.paragraph_id,
                    sentence_text=sentence.text,
                    source_text=finding.source_text.strip(),
                    claim_text=finding.claim_text.strip(),
                    claim_hash=claim_hash,
                    claim_type=finding.claim_type,
                    confidence=finding.confidence,
                    explanation=finding.explanation[:500],
                    detected_by=detected_by,
                    heuristic_reasons=sentence.heuristic_reasons,
                    start_offset=absolute_start,
                    end_offset=absolute_end,
                    source_json=sentence.source,
                    source_search_status="not_started",
                    model=model,
                    revision=audit.revision,
                )
            self._session.add(record)
            existing_records.append(record)
            existing_hashes.add(claim_hash)
            inserted += 1

        for decision, model, accepted in decisions:
            if decision.sentence_id not in by_id:
                continue
            self._session.add(
                CitationAuditDecisionRecord(
                    audit_id=audit_id,
                    lane=lane,
                    batch_key=batch_key,
                    sentence_id=decision.sentence_id,
                    model=model,
                    is_verifiable_claim=decision.is_verifiable_claim,
                    requires_citation=decision.requires_citation,
                    source_text=decision.source_text.strip(),
                    claim_text=decision.claim_text.strip(),
                    claim_type=decision.claim_type,
                    confidence=decision.confidence,
                    explanation=decision.explanation[:500],
                    accepted=accepted,
                )
            )

        if existing_batch is None:
            existing_batch = CitationAuditBatchRecord(
                **batch_identity,
                status="completed",
                item_count=inserted,
            )
            self._session.add(existing_batch)
        else:
            existing_batch.status = "completed"
            existing_batch.item_count = inserted
            existing_batch.error = None

        if lane == "priority":
            audit.priority_completed = min(audit.priority_total, audit.priority_completed + 1)
        else:
            audit.discovery_completed = min(
                audit.discovery_total,
                audit.discovery_completed + 1,
            )
        await self._session.commit()
        return audit

    async def mark_completed(self, audit_id: str) -> CitationAuditRecord:
        record = await self._locked(audit_id)
        record.status = "completed"
        record.error = None
        await self._session.commit()
        return record

    async def record_error(self, audit_id: str, error: str) -> None:
        record = await self._locked(audit_id)
        record.error = error[:1_000]
        await self._session.commit()

    async def list_findings(
        self,
        audit_id: str,
        *,
        after_revision: int = 0,
    ) -> list[CitationAuditFinding]:
        return await self._findings_by_review_state(
            audit_id,
            after_revision=after_revision,
            dismissed=False,
        )

    async def list_dismissed_findings(
        self,
        audit_id: str,
    ) -> list[CitationAuditFinding]:
        return await self._findings_by_review_state(
            audit_id,
            after_revision=0,
            dismissed=True,
        )

    async def _findings_by_review_state(
        self,
        audit_id: str,
        *,
        after_revision: int,
        dismissed: bool,
    ) -> list[CitationAuditFinding]:
        records = list(await self._session.scalars(
            select(CitationAuditFindingRecord)
            .where(
                CitationAuditFindingRecord.audit_id == audit_id,
                CitationAuditFindingRecord.revision > after_revision,
            )
            .order_by(CitationAuditFindingRecord.revision)
        ))
        if not records:
            return []
        feedback_records = list(
            await self._session.scalars(
                select(CitationFeedbackRecord)
                .where(
                    CitationFeedbackRecord.finding_id.in_(
                        [record.id for record in records]
                    )
                )
                .order_by(
                    CitationFeedbackRecord.created_at,
                    CitationFeedbackRecord.id,
                )
            )
        )
        latest_feedback = {
            feedback.finding_id: feedback.feedback for feedback in feedback_records
        }
        records = [
            record
            for record in records
            if (latest_feedback.get(record.id) == "false_positive") == dismissed
        ]
        if not records:
            return []
        return await self._project_findings(records)

    async def _project_findings(
        self,
        records: list[CitationAuditFindingRecord],
    ) -> list[CitationAuditFinding]:
        candidate_rows = await self._session.execute(
            select(CitationSourceCandidateRecord, ScholarlyWorkRecord)
            .join(
                ScholarlyWorkRecord,
                ScholarlyWorkRecord.id == CitationSourceCandidateRecord.work_id,
            )
            .where(
                CitationSourceCandidateRecord.finding_id.in_(
                    [record.id for record in records]
                ),
                (CitationSourceCandidateRecord.support_status == "verified") | (CitationSourceCandidateRecord.decision == "accepted"),
            )
            .order_by(
                CitationSourceCandidateRecord.finding_id,
                CitationSourceCandidateRecord.rank,
            )
        )
        candidates: dict[str, list[tuple[CitationSourceCandidateRecord, ScholarlyWorkRecord]]] = {}
        for candidate, work in candidate_rows.tuples():
            candidates.setdefault(candidate.finding_id, []).append((candidate, work))
        return [
            self._finding_from_record(record, candidates.get(record.id, []))
            for record in records
        ]

    async def pending_source_finding_ids(self, audit_id: str) -> list[str]:
        result = await self._session.scalars(
            select(CitationAuditFindingRecord.id).where(
                CitationAuditFindingRecord.audit_id == audit_id,
                CitationAuditFindingRecord.source_search_status == "not_started",
            )
        )
        return list(result)

    async def source_search_pending_count(self, audit_id: str) -> int:
        count = await self._session.scalar(
            select(func.count()).select_from(CitationAuditFindingRecord).where(
                CitationAuditFindingRecord.audit_id == audit_id,
                CitationAuditFindingRecord.source_search_status.in_(
                    ["not_started", "queued", "running"]
                ),
            )
        )
        return int(count or 0)

    async def mark_source_search(
        self,
        finding_id: str,
        status: str,
        *,
        error: str | None = None,
        source_search_version: int | None = None,
    ) -> CitationAuditFindingRecord:
        finding = await self._session.scalar(
            select(CitationAuditFindingRecord)
            .where(CitationAuditFindingRecord.id == finding_id)
            .with_for_update()
        )
        if finding is None:
            raise RuntimeError("The citation finding was not found.")
        audit = await self._locked(finding.audit_id)
        version_changed = (
            source_search_version is not None
            and finding.source_search_version != source_search_version
        )
        if (
            finding.source_search_status != status
            or finding.source_search_error != error
            or version_changed
        ):
            audit.revision += 1
            finding.revision = audit.revision
            finding.source_search_status = status
            finding.source_search_error = error[:1_000] if error else None
            if source_search_version is not None:
                finding.source_search_version = source_search_version
        await self._session.commit()
        return finding

    async def update_candidate_supports(
        self,
        decisions: list[tuple[str, _CandidateSupportDecision]],
    ) -> None:
        if not decisions:
            return
        records = list(
            await self._session.scalars(
                select(CitationSourceCandidateRecord).where(
                    CitationSourceCandidateRecord.id.in_(
                        [candidate_id for candidate_id, _decision in decisions]
                    )
                )
            )
        )
        records_by_id = {record.id: record for record in records}
        for candidate_id, decision in decisions:
            record = records_by_id.get(candidate_id)
            if record is None:
                continue
            record.support_status = decision.status
            record.supports_claim = (
                True
                if decision.status == "verified"
                else False if decision.status == "rejected" else None
            )
            record.support_confidence = decision.confidence
            record.support_explanation = decision.explanation[:500]
            record.support_evidence = decision.evidence[:300]
        await self._session.commit()

    async def decide_candidate(self, paper_id: str, finding_id: str, candidate_id: str, decision: str) -> CitationSourceCandidateRecord:
        from app.database.models import ConfirmedCitationRecord
        finding = await self._session.scalar(select(CitationAuditFindingRecord).where(CitationAuditFindingRecord.id == finding_id))
        candidate = await self._session.scalar(select(CitationSourceCandidateRecord).where(CitationSourceCandidateRecord.id == candidate_id, CitationSourceCandidateRecord.finding_id == finding_id).with_for_update())
        if finding is None or candidate is None:
            raise RuntimeError("The citation source candidate was not found.")
        if decision == "accepted" and (
            candidate.support_status != "verified" or candidate.supports_claim is not True
        ):
            raise RuntimeError(
                "Only a provider source verified to support this claim can be accepted."
            )
        audit = await self._locked(finding.audit_id)
        candidate.decision = decision
        candidate.decided_at = func.now()
        if decision == "accepted":
            await self._session.execute(insert(ConfirmedCitationRecord).values(id=str(uuid.uuid4()), paper_id=paper_id, finding_id=finding_id, work_id=candidate.work_id, status="accepted").on_conflict_do_update(index_elements=["finding_id", "work_id"], set_={"status": "accepted"}))
        else:
            await self._session.execute(delete(ConfirmedCitationRecord).where(ConfirmedCitationRecord.finding_id == finding_id, ConfirmedCitationRecord.work_id == candidate.work_id))
        self._session.add(
            CitationFeedbackRecord(
                id=str(uuid.uuid4()),
                paper_id=paper_id,
                finding_id=finding_id,
                candidate_id=candidate_id,
                feedback="accepted_source" if decision == "accepted" else "rejected_source",
            )
        )
        audit.revision += 1
        finding.revision = audit.revision
        await self._session.commit()
        return candidate

    async def record_feedback(
        self,
        paper_id: str,
        finding_id: str,
        *,
        feedback: str,
        candidate_id: str | None = None,
        actor_id: str = "anonymous",
        note: str | None = None,
    ) -> CitationFeedbackRecord:
        finding = await self._session.scalar(
            select(CitationAuditFindingRecord).where(
                CitationAuditFindingRecord.id == finding_id,
                CitationAuditFindingRecord.audit_id.in_(
                    select(CitationAuditRecord.id).where(CitationAuditRecord.paper_id == paper_id)
                ),
            )
        )
        if finding is None:
            raise RuntimeError("The citation finding was not found for this paper.")
        if candidate_id is not None:
            candidate = await self._session.scalar(
                select(CitationSourceCandidateRecord).where(
                    CitationSourceCandidateRecord.id == candidate_id,
                    CitationSourceCandidateRecord.finding_id == finding_id,
                )
            )
            if candidate is None:
                raise RuntimeError("The citation source candidate was not found for this finding.")
        record = CitationFeedbackRecord(
            id=str(uuid.uuid4()),
            paper_id=paper_id,
            finding_id=finding_id,
            candidate_id=candidate_id,
            feedback=feedback,
            actor_id=actor_id,
            note=note,
        )
        audit = await self._locked(finding.audit_id)
        audit.revision += 1
        finding.revision = audit.revision
        self._session.add(record)
        await self._session.commit()
        return record

    async def feedback_summary(self, paper_id: str) -> dict[str, int]:
        result = await self._session.execute(
            select(CitationFeedbackRecord.feedback, func.count())
            .where(CitationFeedbackRecord.paper_id == paper_id)
            .group_by(CitationFeedbackRecord.feedback)
        )
        return {feedback: int(count) for feedback, count in result.tuples()}

    async def feedback_metrics(self, paper_id: str) -> tuple[dict[str, int], float | None, dict[str, int]]:
        summary = await self.feedback_summary(paper_id)
        accepted = summary.get("accepted_source", 0)
        rejected = summary.get("rejected_source", 0)
        denominator = accepted + rejected
        rate = accepted / denominator if denominator else None
        rank_result = await self._session.execute(
            select(CitationSourceCandidateRecord.rank, func.count())
            .join(CitationFeedbackRecord, CitationFeedbackRecord.candidate_id == CitationSourceCandidateRecord.id)
            .where(
                CitationFeedbackRecord.paper_id == paper_id,
                CitationFeedbackRecord.feedback == "accepted_source",
            )
            .group_by(CitationSourceCandidateRecord.rank)
            .order_by(CitationSourceCandidateRecord.rank)
        )
        return summary, rate, {str(rank): int(count) for rank, count in rank_result.tuples()}

    async def replace_source_candidates(
        self,
        finding_id: str,
        candidates: list[tuple[str, float, str]],
    ) -> CitationAuditFindingRecord:
        finding = await self._session.scalar(
            select(CitationAuditFindingRecord)
            .where(CitationAuditFindingRecord.id == finding_id)
            .with_for_update()
        )
        if finding is None:
            raise RuntimeError("The citation finding was not found.")
        await self._session.execute(
            delete(CitationSourceCandidateRecord).where(
                CitationSourceCandidateRecord.finding_id == finding_id
            )
        )
        for rank, (work_id, score, reason) in enumerate(candidates, start=1):
            self._session.add(
                CitationSourceCandidateRecord(
                    id=str(uuid.uuid4()),
                    finding_id=finding_id,
                    work_id=work_id,
                    rank=rank,
                    score=score,
                    reason=reason,
                )
            )
        await self._session.commit()
        return finding

    async def complete_source_search(
        self,
        finding_id: str,
        *,
        source_search_version: int,
    ) -> CitationAuditFindingRecord:
        finding = await self._session.scalar(
            select(CitationAuditFindingRecord)
            .where(CitationAuditFindingRecord.id == finding_id)
            .with_for_update()
        )
        if finding is None:
            raise RuntimeError("The citation finding was not found.")
        audit = await self._locked(finding.audit_id)
        audit.revision += 1
        finding.revision = audit.revision
        finding.source_search_status = "completed"
        finding.source_search_error = None
        finding.source_search_version = source_search_version
        await self._session.commit()
        return finding

    @staticmethod
    def progress(record: CitationAuditRecord) -> CitationAuditProgress:
        return CitationAuditProgress(
            total_sentences=record.total_sentences,
            heuristic_candidates=record.heuristic_candidates,
            priority_total=record.priority_total,
            priority_completed=record.priority_completed,
            discovery_total=record.discovery_total,
            discovery_completed=record.discovery_completed,
        )

    async def _locked(self, audit_id: str) -> CitationAuditRecord:
        record = await self._session.scalar(
            select(CitationAuditRecord)
            .where(CitationAuditRecord.id == audit_id)
            .with_for_update()
        )
        if record is None:
            raise RuntimeError("The citation audit was not found.")
        return record

    @staticmethod
    def _finding_from_record(
        record: CitationAuditFindingRecord,
        candidates: list[tuple[CitationSourceCandidateRecord, ScholarlyWorkRecord]],
    ) -> CitationAuditFinding:
        return CitationAuditFinding(
            id=record.id,
            sentence_id=record.sentence_id,
            section_id=record.section_id,
            section_title=record.section_title,
            paragraph_id=record.paragraph_id,
            sentence_text=record.sentence_text,
            source_text=record.source_text,
            claim_text=record.claim_text,
            claim_type=record.claim_type,  # type: ignore[arg-type]
            confidence=record.confidence,
            explanation=record.explanation,
            detected_by=record.detected_by,
            heuristic_reasons=record.heuristic_reasons,
            start_offset=record.start_offset,
            end_offset=record.end_offset,
            source=(
                ExtractionPointer.model_validate(record.source_json)
                if record.source_json
                else None
            ),
            source_search_status=record.source_search_status,  # type: ignore[arg-type]
            source_search_error=record.source_search_error,
            source_candidates=[
                CitationSourceCandidate(
                    id=candidate.id,
                    rank=candidate.rank,
                    score=candidate.score,
                    reason=candidate.reason,
                    support_status=candidate.support_status,
                    supports_claim=candidate.supports_claim,
                    support_confidence=candidate.support_confidence,
                    support_explanation=candidate.support_explanation,
                    support_evidence=candidate.support_evidence,
                    decision=candidate.decision,
                    work=CitationSourceWork(
                        id=work.id,
                        title=work.title,
                        year=work.year,
                        abstract=work.abstract,
                        doi=work.doi,
                        arxiv_id=work.arxiv_id,
                        authors=work.authors,
                        landing_page_url=work.landing_page_url,
                        cited_by_count=work.cited_by_count,
                        providers=list(work.provider_ids),  # type: ignore[arg-type]
                        provider_ids=work.provider_ids,
                    ),
                )
                for candidate, work in candidates
            ],
            revision=record.revision,
        )
