from __future__ import annotations

import asyncio

from openai import AsyncOpenAI
from bullmq import Job, Queue, Worker

from app.config import (
    CLAIM_AUDIT_QUEUE_NAME,
    OPENAI_TIMEOUT_SECONDS,
    SOURCE_SEARCH_QUEUE_NAME,
    bullmq_options,
    claim_audit_model,
    claim_audit_review_model,
    openai_api_key,
    openai_base_url,
)
from app.database.session import get_session_factory
from app.repositories.citation_audits import CitationAuditRepository
from app.repositories.papers import PaperDocumentRepository
from app.repositories.pipeline import PaperPipelineRepository
from app.services.citation_audit import (
    AuditBatch,
    CitationAuditAnalyzer,
    build_audit_batches,
    find_sentence,
    finding_from_decision,
)
from app.workers.source_search import enqueue_pending_source_searches


async def run() -> None:
    client = AsyncOpenAI(api_key=openai_api_key(), base_url=openai_base_url(), timeout=OPENAI_TIMEOUT_SECONDS)
    try:
        analyzer = CitationAuditAnalyzer(
            client,
            api_key=openai_api_key(),
            model=claim_audit_model(),
        )
        reviewer = CitationAuditAnalyzer(
            client,
            api_key=openai_api_key(),
            model=claim_audit_review_model(),
        )
        source_queue = Queue(SOURCE_SEARCH_QUEUE_NAME, bullmq_options())

        async def process(job: Job, _token: str) -> dict[str, int]:
            paper_id = str(job.data.get("paperId") or "")
            audit_id = str(job.data.get("auditId") or "")
            section_ids = [
                str(value) for value in (job.data.get("sectionIds") or []) if value
            ]
            if not paper_id or not audit_id:
                raise ValueError("The citation-audit job is missing paperId or auditId.")
            try:
                async with get_session_factory()() as session:
                    await PaperPipelineRepository(session).begin(
                        paper_id, "missing-citation-review"
                    )
                result = await audit_document(
                    job,
                    paper_id,
                    audit_id,
                    analyzer,
                    reviewer,
                    source_queue,
                    section_ids=section_ids,
                )
                async with get_session_factory()() as session:
                    await PaperPipelineRepository(session).complete(
                        paper_id, "missing-citation-review", progress=result
                    )
                return result
            except Exception as exc:
                async with get_session_factory()() as session:
                    await CitationAuditRepository(session).record_error(audit_id, str(exc))
                    await PaperPipelineRepository(session).fail(
                        paper_id, "missing-citation-review", str(exc)
                    )
                raise

        worker = Worker(
            CLAIM_AUDIT_QUEUE_NAME,
            process,
            {
                **bullmq_options(),
                "autorun": False,
                "concurrency": 1,
            },
        )
        await worker.run()
    finally:
        await client.close()


async def audit_document(
    job: Job,
    paper_id: str,
    audit_id: str,
    analyzer: CitationAuditAnalyzer,
    reviewer: CitationAuditAnalyzer,
    source_queue: Queue,
    *,
    section_ids: list[str] | None = None,
) -> dict[str, int]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        paper = (await PaperDocumentRepository(session).get(paper_id)).paper
    if section_ids:
        allowed = set(section_ids)
        paper = paper.model_copy(
            update={"sections": [section for section in paper.sections if section.id in allowed]}
        )

    sentences, priority_batches, discovery_batches = build_audit_batches(paper)
    async with session_factory() as session:
        audits = CitationAuditRepository(session)
        record = await audits.prepare(
            audit_id,
            total_sentences=len(sentences),
            heuristic_candidates=sum(sentence.heuristic_candidate for sentence in sentences),
            priority_total=len(priority_batches),
            discovery_total=len(discovery_batches),
        )
        completed = await audits.completed_batch_keys(audit_id)
        await job.updateProgress(audits.progress(record).model_dump())

    async def process_lane(batches: list[AuditBatch]) -> None:
        for batch in batches:
            if (batch.lane, batch.key) in completed:
                continue
            findings = []
            decisions = []
            if batch.lane == "priority":
                primary_decisions = await analyzer.verify(batch)
                accepted_sentence_ids: set[str] = set()
                for decision in primary_decisions:
                    finding = finding_from_decision(
                        decision,
                        find_sentence(batch.sentences, decision.sentence_id),
                    )
                    accepted = finding is not None
                    decisions.append((decision, analyzer.model, accepted))
                    if finding is not None:
                        findings.append((finding, analyzer.model))
                        accepted_sentence_ids.add(finding.sentence_id)

                unresolved_ids = [
                    sentence_id
                    for sentence_id in batch.eligible_sentence_ids
                    if sentence_id not in accepted_sentence_ids
                ]
                if unresolved_ids:
                    review_batch = batch.model_copy(
                        update={"eligible_sentence_ids": unresolved_ids}
                    )
                    review_decisions = await reviewer.verify(review_batch)
                    for decision in review_decisions:
                        finding = finding_from_decision(
                            decision,
                            find_sentence(batch.sentences, decision.sentence_id),
                        )
                        accepted = finding is not None
                        decisions.append((decision, reviewer.model, accepted))
                        if finding is not None:
                            findings.append((finding, reviewer.model))
            else:
                findings = [
                    (finding, analyzer.model)
                    for finding in await analyzer.discover(batch)
                ]
            async with session_factory() as session:
                audits = CitationAuditRepository(session)
                record = await audits.complete_batch(
                    audit_id,
                    lane=batch.lane,
                    batch_key=batch.key,
                    findings=findings,
                    decisions=decisions,
                    sentences=batch.sentences,
                )
                await job.updateProgress(audits.progress(record).model_dump())

    await asyncio.gather(
        process_lane(priority_batches),
        process_lane(discovery_batches),
    )

    async with session_factory() as session:
        audits = CitationAuditRepository(session)
        record = await audits.mark_completed(audit_id)
        progress = audits.progress(record)
        finding_count = len(await audits.list_findings(audit_id))
        await job.updateProgress(progress.model_dump())
    await enqueue_pending_source_searches(source_queue, audit_id=audit_id)
    return {
        "findings": finding_count,
        "priorityBatches": progress.priority_completed,
        "discoveryBatches": progress.discovery_completed,
    }


if __name__ == "__main__":
    asyncio.run(run())
