import asyncio
import hashlib
from typing import Annotated
from urllib.parse import quote

from bullmq import Job, Queue
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status, HTTPException

from app.config import MAX_PDF_SIZE, MAX_TEI_SIZE, claim_audit_model
from app.dependencies import (
    get_citation_audit_queue,
    get_citation_audit_repository,
    get_claim_citation_review_repository,
    get_claim_citation_review_queue,
    get_paper_export_repository,
    get_paper_export_queue,
    get_extraction_artifact_store,
    get_missing_work_finder,
    get_manuscript_revision_service,
    get_openalex_enricher,
    get_reference_evidence_queue,
    get_paper_document_repository,
    get_paper_index_queue,
    get_paper_ingestion_service,
    get_paper_parse_queue,
    get_paper_pipeline_repository,
    get_paper_quick_read_queue,
    get_paper_service,
    get_source_search_queue,
)
from app.repositories.artifacts import PaperArtifactStore
from app.repositories.citation_audits import CitationAuditRepository
from app.repositories.claim_citations import ClaimCitationReviewRepository
from app.repositories.exports import PaperExportRepository, project_export
from app.repositories.papers import PaperDocumentRepository
from app.repositories.pipeline import PaperPipelineRepository
from app.schemas.documents import (
    CitationAuditJob,
    CitationAuditStatus,
    CitationFeedbackRequest,
    CitationFeedbackSummary,
    EnrichmentProgress,
    ReferenceEvidenceJob,
    ReferenceEvidenceStatus,
    PaperDocument,
    PaperLifecycle,
    PaperPipeline,
    PaperJobStatus,
    PaperJobsStatus,
    CitationSourceDecisionRequest,
    ClaimCitationReviewStatus,
    EditApprovalRequest,
    EditCommandRequest,
    EditProposal,
    ManuscriptRevisionDetail,
    ManuscriptRevisionList,
    RevisionRevertRequest,
    CitationStyleRequest,
    CitationStyleStatus,
    PaperExport,
    PaperExportRequest,
    SectionReviewRequest,
)
from app.schemas.paper import MissingWorkReport, Paper
from app.services.missing_works import MissingWorkFinder
from app.services.openalex import OpenAlexEnricher
from app.services.paper_ingestion import PaperIngestionService, parse_job_id
from app.services.paper_ingestion import quick_read_job_id
from app.services.paper_pipeline import (
    citation_audit_job_id,
    claim_citation_review_job_id,
    reference_evidence_job_id,
    paper_index_job_id,
)
from app.services.papers import PaperService, normalize_tei
from app.services.manuscript_revisions import ManuscriptRevisionService, RevisionConflictError
from app.services.approved_edit_refresh import ApprovedEditRefresher, BullMQJobQueue
from app.workers.source_search import enqueue_pending_source_searches

router = APIRouter(prefix="/papers", tags=["papers"])

PdfUpload = Annotated[UploadFile, File(description="Academic paper in PDF format")]
TeiUpload = Annotated[UploadFile, File(description="GROBID TEI XML document")]
PaperParser = Annotated[PaperService, Depends(get_paper_service)]
ReferenceEnricher = Annotated[OpenAlexEnricher, Depends(get_openalex_enricher)]
MissingWorks = Annotated[MissingWorkFinder, Depends(get_missing_work_finder)]
ArtifactStore = Annotated[PaperArtifactStore, Depends(get_extraction_artifact_store)]
PaperDocuments = Annotated[PaperDocumentRepository, Depends(get_paper_document_repository)]
PaperIngestion = Annotated[PaperIngestionService, Depends(get_paper_ingestion_service)]
PaperPipelineRepositoryDependency = Annotated[
    PaperPipelineRepository, Depends(get_paper_pipeline_repository)
]
ClaimCitationReviews = Annotated[
    ClaimCitationReviewRepository, Depends(get_claim_citation_review_repository)
]
ManuscriptRevisions = Annotated[
    ManuscriptRevisionService, Depends(get_manuscript_revision_service)
]
ReferenceEvidenceQueue = Annotated[Queue, Depends(get_reference_evidence_queue)]
CitationAudits = Annotated[CitationAuditRepository, Depends(get_citation_audit_repository)]
CitationAuditQueue = Annotated[Queue, Depends(get_citation_audit_queue)]
SourceSearchQueue = Annotated[Queue, Depends(get_source_search_queue)]
PaperExports = Annotated[PaperExportRepository, Depends(get_paper_export_repository)]
PaperExportQueue = Annotated[Queue, Depends(get_paper_export_queue)]
ClaimCitationReviewQueue = Annotated[Queue, Depends(get_claim_citation_review_queue)]
PaperIndexQueue = Annotated[Queue, Depends(get_paper_index_queue)]


@router.post("", response_model=PaperLifecycle, status_code=status.HTTP_202_ACCEPTED)
async def ingest_paper(file: PdfUpload, ingestion: PaperIngestion) -> PaperLifecycle:
    """Persist an uploaded PDF and return before authoritative parsing begins."""
    content = await file.read(MAX_PDF_SIZE + 1)
    return await ingestion.ingest(file.filename or "paper.pdf", content)


@router.post("/{paper_id}/citation-audit/findings/{finding_id}/candidates/{candidate_id}/decision")
async def decide_citation_candidate(
    paper_id: str,
    finding_id: str,
    candidate_id: str,
    payload: CitationSourceDecisionRequest,
    documents: PaperDocuments,
    audits: CitationAudits,
    revisions: ManuscriptRevisions,
) -> dict[str, str | EditProposal | None]:
    await documents.get(paper_id)
    proposal = None
    if payload.decision == "accepted":
        try:
            proposal = await revisions.propose_verified_source(
                paper_id, finding_id, candidate_id
            )
        except RevisionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (LookupError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        decision = "pending"
    else:
        try:
            candidate = await audits.decide_candidate(
                paper_id, finding_id, candidate_id, payload.decision
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        decision = candidate.decision
    return {
        "candidateId": candidate_id,
        "decision": decision,
        "editProposal": proposal,
    }


@router.post(
    "/{paper_id}/citation-audit/findings/{finding_id}/candidates/{candidate_id}/remove",
    response_model=EditProposal,
)
async def propose_citation_candidate_removal(
    paper_id: str,
    finding_id: str,
    candidate_id: str,
    documents: PaperDocuments,
    revisions: ManuscriptRevisions,
) -> EditProposal:
    await documents.get(paper_id)
    try:
        return await revisions.propose_verified_source_removal(
            paper_id,
            finding_id,
            candidate_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{paper_id}/citation-audit/findings/{finding_id}/feedback",
    status_code=status.HTTP_201_CREATED,
)
async def record_citation_feedback(
    paper_id: str,
    finding_id: str,
    payload: CitationFeedbackRequest,
    documents: PaperDocuments,
    audits: CitationAudits,
) -> dict[str, str | None]:
    """Record review feedback and dismiss false-positive audit findings."""
    await documents.get(paper_id)
    try:
        record = await audits.record_feedback(
            paper_id,
            finding_id,
            feedback=payload.feedback,
            candidate_id=payload.candidate_id,
            actor_id=payload.actor_id,
            note=payload.note,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "feedbackId": record.id,
        "findingId": finding_id,
        "feedback": record.feedback,
        "candidateId": record.candidate_id,
    }


@router.get("/{paper_id}/citation-audit/feedback", response_model=CitationFeedbackSummary)
async def get_citation_feedback_summary(
    paper_id: str,
    documents: PaperDocuments,
    audits: CitationAudits,
) -> CitationFeedbackSummary:
    await documents.get(paper_id)
    summary, accepted_rate, accepted_by_rank = await audits.feedback_metrics(paper_id)
    return CitationFeedbackSummary(
        paper_id=paper_id,
        total=sum(summary.values()),
        by_feedback=summary,
        accepted_source_rate=accepted_rate,
        accepted_by_rank=accepted_by_rank,
    )


@router.post("/parse", response_model=PaperDocument)
async def parse_paper(
    file: PdfUpload,
    service: PaperParser,
    documents: PaperDocuments,
    index_queue: Annotated[Queue, Depends(get_paper_index_queue)],
) -> PaperDocument:
    """Parse and persist an uploaded academic paper without waiting for enrichment."""
    content = await file.read(MAX_PDF_SIZE + 1)
    filename = file.filename or "paper.pdf"
    paper = await service.parse_pdf(content, filename)
    document = await documents.create(filename, paper)
    await index_queue.add(
        "index-paper",
        {"paperId": document.id},
        {
            "jobId": paper_index_job_id(document.id),
            "attempts": 3,
            "removeOnComplete": False,
            "removeOnFail": False,
        },
    )
    return document


@router.post("/{paper_id}/index", status_code=status.HTTP_202_ACCEPTED)
async def index_existing_paper(
    paper_id: str,
    documents: PaperDocuments,
    index_queue: Annotated[Queue, Depends(get_paper_index_queue)],
) -> dict[str, str]:
    await documents.get(paper_id)
    job_id = paper_index_job_id(paper_id)
    job = await Job.fromId(index_queue, job_id)
    if job is not None and await job.getState() == "failed":
        await job.remove()
        job = None
    if job is None:
        job = await index_queue.add(
            "index-paper",
            {"paperId": paper_id},
            {
                "jobId": job_id,
                "attempts": 3,
                "removeOnComplete": False,
                "removeOnFail": False,
            },
        )
    return {"paperId": paper_id, "status": map_job_status(await job.getState())}


@router.get("/{paper_id}", response_model=PaperLifecycle)
async def get_paper(paper_id: str, documents: PaperDocuments) -> PaperLifecycle:
    """Return durable parse state and the paper projection when it is ready."""
    return await documents.get_lifecycle(paper_id)


@router.get("/{paper_id}/pipeline", response_model=PaperPipeline)
async def get_paper_pipeline(
    paper_id: str,
    documents: PaperDocuments,
    pipeline: PaperPipelineRepositoryDependency,
) -> PaperPipeline:
    await documents.get_lifecycle(paper_id)
    return PaperPipeline(paper_id=paper_id, stages=await pipeline.list(paper_id))


@router.post("/{paper_id}/pipeline/{stage}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_paper_pipeline_stage(
    paper_id: str,
    stage: str,
    documents: PaperDocuments,
    pipeline: PaperPipelineRepositoryDependency,
    audits: CitationAudits,
    parse_queue: Annotated[Queue, Depends(get_paper_parse_queue)],
    quick_queue: Annotated[Queue, Depends(get_paper_quick_read_queue)],
    index_queue: Annotated[Queue, Depends(get_paper_index_queue)],
    reference_evidence_queue: ReferenceEvidenceQueue,
    citation_queue: CitationAuditQueue,
    existing_queue: ClaimCitationReviewQueue,
) -> dict[str, str]:
    await documents.get_lifecycle(paper_id)
    current = next((item for item in await pipeline.list(paper_id) if item.name == stage), None)
    if current is None:
        raise HTTPException(status_code=404, detail="The pipeline stage was not found.")
    if current.status == "skipped":
        raise HTTPException(
            status_code=409,
            detail="This whole-document stage was intentionally skipped. Start a section-scoped review instead.",
        )
    if current.status != "failed":
        raise HTTPException(status_code=409, detail="Only a failed stage can be retried.")
    audit = await audits.create_or_get(paper_id, claim_audit_model())
    choices = {
        "quick-extraction": (quick_queue, "quick-read-paper", {"paperId": paper_id}, quick_read_job_id(paper_id)),
        "quick-index": (quick_queue, "quick-read-paper", {"paperId": paper_id}, quick_read_job_id(paper_id)),
        "authoritative-parse": (parse_queue, "parse-paper", {"paperId": paper_id}, parse_job_id(paper_id)),
        "authoritative-index": (index_queue, "index-paper", {"paperId": paper_id}, paper_index_job_id(paper_id)),
        "reference-resolution": (
            reference_evidence_queue,
            "resolve-reference-evidence",
            {"paperId": paper_id},
            reference_evidence_job_id(paper_id),
        ),
        "missing-citation-review": (citation_queue, "audit-missing-citations", {"paperId": paper_id, "auditId": audit.id}, citation_audit_job_id(paper_id)),
        "existing-citation-review": (existing_queue, "review-existing-citations", {"paperId": paper_id}, claim_citation_review_job_id(paper_id)),
    }
    selected = choices.get(stage)
    if selected is None:
        raise HTTPException(status_code=422, detail="This stage does not support direct retry.")
    queue, name, data, job_id = selected
    existing = await Job.fromId(queue, job_id)
    if existing is not None:
        await existing.remove()
    await queue.add(
        name,
        data,
        {
            "jobId": job_id,
            "attempts": 4,
            "backoff": {"type": "exponential", "delay": 2_000},
            "removeOnComplete": False,
            "removeOnFail": False,
        },
    )
    await pipeline.queued(paper_id, stage, progress={"manualRetry": True})
    return {"paperId": paper_id, "stage": stage, "status": "queued"}


@router.get(
    "/{paper_id}/claim-citation-review",
    response_model=ClaimCitationReviewStatus,
)
async def get_claim_citation_review(
    paper_id: str,
    documents: PaperDocuments,
    pipeline: PaperPipelineRepositoryDependency,
    reviews: ClaimCitationReviews,
) -> ClaimCitationReviewStatus:
    await documents.get_lifecycle(paper_id)
    stages = await pipeline.list(paper_id)
    stage = next(
        (item for item in stages if item.name == "existing-citation-review"), None
    )
    findings = await reviews.list(paper_id)
    reported_total = (
        int(stage.progress.get("pairs", len(findings))) if stage else len(findings)
    )
    return ClaimCitationReviewStatus(
        paper_id=paper_id,
        status=(stage.status if stage and stage.status != "skipped" else "completed"),  # type: ignore[arg-type]
        findings=findings,
        total=max(reported_total, len(findings)),
        completed=len(findings),
        error=stage.error if stage else None,
    )


@router.post("/{paper_id}/section-review", status_code=status.HTTP_202_ACCEPTED)
async def start_section_scoped_review(
    paper_id: str,
    payload: SectionReviewRequest,
    documents: PaperDocuments,
    audits: CitationAudits,
    citation_queue: CitationAuditQueue,
    existing_queue: ClaimCitationReviewQueue,
    index_queue: Annotated[Queue, Depends(get_paper_index_queue)],
    pipeline: PaperPipelineRepositoryDependency,
) -> dict[str, object]:
    document = await documents.get(paper_id)
    available = {section.id for section in document.paper.sections}
    section_ids = list(dict.fromkeys(payload.section_ids))
    unknown = [section_id for section_id in section_ids if section_id not in available]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown section IDs: {', '.join(unknown)}")
    scope = hashlib.sha256("|".join(section_ids).encode()).hexdigest()[:12]
    audit = await audits.create_or_get(paper_id, claim_audit_model())
    jobs = [
        (
            citation_queue,
            "audit-missing-citations",
            {"paperId": paper_id, "auditId": audit.id, "sectionIds": section_ids},
            f"citation-audit-{paper_id}-sections-{scope}",
        ),
        (
            existing_queue,
            "review-existing-citations",
            {"paperId": paper_id, "sectionIds": section_ids},
            f"claim-citation-review-{paper_id}-sections-{scope}",
        ),
    ]
    job_statuses: list[str] = []
    for queue, name, data, job_id in jobs:
        job = await Job.fromId(queue, job_id)
        if job is not None and await job.getState() == "failed":
            await job.remove()
            job = None
        if job is None:
            job = await queue.add(
                name,
                data,
                {
                    "jobId": job_id,
                    "attempts": 4,
                    "backoff": {"type": "exponential", "delay": 2_000},
                    "removeOnComplete": False,
                    "removeOnFail": False,
                },
            )
        job_statuses.append(map_job_status(await job.getState()))
    if all(job_status == "completed" for job_status in job_statuses):
        request_status = "completed"
    elif any(job_status == "running" for job_status in job_statuses):
        request_status = "running"
    else:
        request_status = "queued"
    if request_status == "queued":
        progress = {"sectionIds": section_ids, "scope": "section"}
        await pipeline.queued(paper_id, "missing-citation-review", progress=progress)
        await pipeline.queued(paper_id, "existing-citation-review", progress=progress)
    return {
        "paperId": paper_id,
        "sectionIds": section_ids,
        "status": request_status,
    }


@router.post("/{paper_id}/edits", response_model=EditProposal)
async def plan_manuscript_edit(
    paper_id: str,
    payload: EditCommandRequest,
    documents: PaperDocuments,
    revisions: ManuscriptRevisions,
) -> EditProposal:
    await documents.get(paper_id)
    try:
        return await revisions.plan(
            paper_id,
            payload.command,
            base_revision=payload.base_revision,
        )
    except RevisionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{paper_id}/edits/latest", response_model=EditProposal | None)
async def get_latest_manuscript_edit(
    paper_id: str,
    revisions: ManuscriptRevisions,
) -> EditProposal | None:
    return await revisions.latest_proposal(paper_id)


@router.get("/{paper_id}/edits/{proposal_id}", response_model=EditProposal)
async def get_manuscript_edit(
    paper_id: str,
    proposal_id: str,
    revisions: ManuscriptRevisions,
) -> EditProposal:
    try:
        return await revisions.proposal(paper_id, proposal_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{paper_id}/edits/{proposal_id}/approve", response_model=EditProposal)
async def approve_manuscript_edit(
    paper_id: str,
    proposal_id: str,
    payload: EditApprovalRequest,
    revisions: ManuscriptRevisions,
    documents: PaperDocuments,
    audits: CitationAudits,
    citation_queue: CitationAuditQueue,
    existing_queue: ClaimCitationReviewQueue,
    index_queue: PaperIndexQueue,
    pipeline: PaperPipelineRepositoryDependency,
) -> EditProposal:
    try:
        approved = await revisions.approve(
            paper_id, proposal_id, payload.operation_ids
        )
        refresh_warnings = await ApprovedEditRefresher(
            documents=documents,
            audits=audits,
            pipeline=pipeline,
            index_jobs=BullMQJobQueue(index_queue),
            missing_review_jobs=BullMQJobQueue(citation_queue),
            existing_review_jobs=BullMQJobQueue(existing_queue),
            audit_model=claim_audit_model(),
        ).schedule(paper_id, approved)
        if not refresh_warnings:
            return approved
        return approved.model_copy(
            update={"warnings": [*approved.warnings, *refresh_warnings]}
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RevisionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{paper_id}/edits/{proposal_id}/discard", response_model=EditProposal)
async def discard_manuscript_edit(
    paper_id: str,
    proposal_id: str,
    revisions: ManuscriptRevisions,
) -> EditProposal:
    try:
        return await revisions.discard(paper_id, proposal_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RevisionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{paper_id}/revisions", response_model=ManuscriptRevisionList)
async def list_manuscript_revisions(
    paper_id: str,
    revisions: ManuscriptRevisions,
) -> ManuscriptRevisionList:
    try:
        return await revisions.revisions(paper_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{paper_id}/revisions/{revision}", response_model=ManuscriptRevisionDetail)
async def get_manuscript_revision(
    paper_id: str,
    revision: int,
    revisions: ManuscriptRevisions,
) -> ManuscriptRevisionDetail:
    try:
        return await revisions.revision(paper_id, revision)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{paper_id}/revisions/{revision}/restore", response_model=ManuscriptRevisionDetail)
async def restore_manuscript_revision(
    paper_id: str,
    revision: int,
    revisions: ManuscriptRevisions,
) -> ManuscriptRevisionDetail:
    try:
        return await revisions.restore(paper_id, revision)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{paper_id}/revisions/{revision}/revert", response_model=ManuscriptRevisionDetail)
async def selectively_revert_manuscript_revision(
    paper_id: str,
    revision: int,
    payload: RevisionRevertRequest,
    revisions: ManuscriptRevisions,
) -> ManuscriptRevisionDetail:
    try:
        return await revisions.revert_operations(
            paper_id, revision, payload.operation_ids
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{paper_id}/citation-style", response_model=CitationStyleStatus)
async def get_citation_style(
    paper_id: str,
    documents: PaperDocuments,
    exports: PaperExports,
) -> CitationStyleStatus:
    document = await documents.get(paper_id)
    detected = (
        document.paper.citation_style_detection.family
        if document.paper.citation_style_detection
        else document.paper.citation_style
    )
    return await exports.style_status(paper_id, detected)


@router.put("/{paper_id}/citation-style", response_model=CitationStyleStatus)
async def confirm_citation_style(
    paper_id: str,
    payload: CitationStyleRequest,
    documents: PaperDocuments,
    exports: PaperExports,
) -> CitationStyleStatus:
    from citeproc_styles import get_style_filepath

    document = await documents.get(paper_id)
    try:
        get_style_filepath(payload.style_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="That CSL style is unavailable.") from exc
    detected = (
        document.paper.citation_style_detection.family
        if document.paper.citation_style_detection
        else document.paper.citation_style
    )
    return await exports.confirm_style(paper_id, payload.style_id, detected)


@router.post("/{paper_id}/exports", response_model=PaperExport, status_code=status.HTTP_202_ACCEPTED)
async def create_paper_export(
    paper_id: str,
    payload: PaperExportRequest,
    revisions: ManuscriptRevisions,
    exports: PaperExports,
    queue: PaperExportQueue,
    pipeline: PaperPipelineRepositoryDependency,
) -> PaperExport:
    try:
        await revisions.revision(paper_id, payload.revision)
        record = await exports.create(paper_id, payload.revision)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await queue.add(
        "export-paper",
        {"paperId": paper_id, "exportId": record.id},
        {
            "jobId": f"paper-export-{record.id}",
            "attempts": 3,
            "backoff": {"type": "exponential", "delay": 2_000},
            "removeOnComplete": False,
            "removeOnFail": False,
        },
    )
    await pipeline.queued(paper_id, "export", revision=payload.revision)
    return project_export(record)


@router.get("/{paper_id}/exports/{export_id}", response_model=PaperExport)
async def get_paper_export(
    paper_id: str,
    export_id: str,
    exports: PaperExports,
) -> PaperExport:
    try:
        return project_export(await exports.get(paper_id, export_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{paper_id}/exports/{export_id}/download/{format}")
async def download_paper_export(
    paper_id: str,
    export_id: str,
    format: str,
    exports: PaperExports,
    artifacts: ArtifactStore,
) -> Response:
    if format not in {"latex", "pdf"}:
        raise HTTPException(status_code=404, detail="The export format was not found.")
    record = await exports.get(paper_id, export_id)
    object_key = record.latex_object_key if format == "latex" else record.pdf_object_key
    if not object_key or record.status != "completed":
        raise HTTPException(status_code=409, detail="The export is not ready for download.")
    content = await asyncio.to_thread(artifacts.read_export, object_key)
    filename = f"paper-r{record.manuscript_revision}.{'zip' if format == 'latex' else 'pdf'}"
    return Response(
        content=content,
        media_type="application/zip" if format == "latex" else "application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
@router.get("/{paper_id}/source")
async def get_paper_source(
    paper_id: str,
    documents: PaperDocuments,
    artifacts: ArtifactStore,
) -> Response:
    """Proxy the private source PDF for inline viewing without exposing MinIO."""
    filename, object_key = await documents.source(paper_id)
    content = await asyncio.to_thread(artifacts.read_source, object_key)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/{paper_id}/jobs", response_model=PaperJobsStatus)
async def get_paper_jobs(
    paper_id: str,
    documents: PaperDocuments,
    reference_evidence_queue: ReferenceEvidenceQueue,
    audit_queue: CitationAuditQueue,
    index_queue: Annotated[Queue, Depends(get_paper_index_queue)],
    parse_queue: Annotated[Queue, Depends(get_paper_parse_queue)],
    quick_read_queue: Annotated[Queue, Depends(get_paper_quick_read_queue)],
) -> PaperJobsStatus:
    """Expose a single operational view of the long-running paper pipeline."""
    await documents.get_lifecycle(paper_id)
    jobs = [
        ("quick-read", quick_read_job_id(paper_id), quick_read_queue),
        ("parse", parse_job_id(paper_id), parse_queue),
        ("index", paper_index_job_id(paper_id), index_queue),
        (
            "reference-evidence",
            reference_evidence_job_id(paper_id),
            reference_evidence_queue,
        ),
        ("citation-audit", citation_audit_job_id(paper_id), audit_queue),
    ]
    statuses: list[PaperJobStatus] = []
    for name, job_id, queue in jobs:
        job = await Job.fromId(queue, job_id)
        if job is None:
            statuses.append(PaperJobStatus(name=name, job_id=job_id, status="not_started"))
            continue
        progress = job.progress if isinstance(job.progress, dict) else {}
        job_status = map_job_status(await job.getState())
        statuses.append(
            PaperJobStatus(
                name=name,
                job_id=job_id,
                status=job_status,
                progress=progress,
                error=job.failedReason if job_status == "failed" else None,
            )
        )
    return PaperJobsStatus(paper_id=paper_id, jobs=statuses)


@router.post("/normalize", response_model=Paper)
async def normalize_paper(file: TeiUpload) -> Paper:
    """Normalize an existing GROBID TEI XML document into the internal Paper model."""
    xml = await file.read(MAX_TEI_SIZE + 1)
    return normalize_tei(xml)


@router.get("/artifacts/{artifact_id}/tei")
async def get_tei_artifact(artifact_id: str, artifacts: ArtifactStore) -> Response:
    """Download the immutable raw TEI used to create a Paper response."""
    return Response(
        content=await asyncio.to_thread(artifacts.read_tei, artifact_id),
        media_type="application/tei+xml",
        headers={
            "Content-Disposition": f'attachment; filename="{artifact_id}.tei.xml"'
        },
    )


@router.post("/enrich", response_model=Paper)
async def enrich_paper(paper: Paper, enricher: ReferenceEnricher) -> Paper:
    """Look up parsed references on OpenAlex. Misses stay unmatched."""
    return await enricher.enrich_paper(paper)


@router.post("/missing-works", response_model=MissingWorkReport)
async def find_missing_works(paper: Paper, finder: MissingWorks) -> MissingWorkReport:
    """Search OpenAlex for related work that is not already in the bibliography."""
    return await finder.find(paper)


@router.post(
    "/{paper_id}/enrichments/reference-evidence",
    response_model=ReferenceEvidenceJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_reference_evidence(
    paper_id: str,
    documents: PaperDocuments,
    queue: ReferenceEvidenceQueue,
) -> ReferenceEvidenceJob:
    """Idempotently enqueue dual-provider evidence resolution after parsing."""
    await documents.get(paper_id)
    job_id = reference_evidence_job_id(paper_id)
    job = await Job.fromId(queue, job_id)
    if job is None:
        job = await queue.add(
            "resolve-reference-evidence",
            {"paperId": paper_id},
            {
                "jobId": job_id,
                "attempts": 4,
                "backoff": {"type": "exponential", "delay": 2_000},
                "removeOnComplete": False,
                "removeOnFail": False,
            },
        )
    return ReferenceEvidenceJob(
        job_id=job_id,
        paper_id=paper_id,
        status=map_job_status(await job.getState()),
    )


@router.get(
    "/{paper_id}/enrichments/reference-evidence",
    response_model=ReferenceEvidenceStatus,
)
async def get_reference_evidence(
    paper_id: str,
    documents: PaperDocuments,
    queue: ReferenceEvidenceQueue,
    after_revision: Annotated[int, Query(alias="afterRevision", ge=0)] = 0,
) -> ReferenceEvidenceStatus:
    """Poll BullMQ state and receive only reference updates after a document revision."""
    document = await documents.get(paper_id)
    job_id = reference_evidence_job_id(paper_id)
    job = await Job.fromId(queue, job_id)
    updates = await documents.list_updates(paper_id, after_revision=after_revision)
    if job is None:
        return ReferenceEvidenceStatus(
            job_id=job_id,
            paper_id=paper_id,
            status="not_started",
            revision=document.revision,
            reference_updates=updates,
            progress=EnrichmentProgress(total=len(document.paper.references)),
        )

    progress_payload = job.progress if isinstance(job.progress, dict) else {}
    progress = EnrichmentProgress.model_validate(
        {
            "total": len(document.paper.references),
            **progress_payload,
        }
    )
    job_status = map_job_status(await job.getState())
    return ReferenceEvidenceStatus(
        job_id=job_id,
        paper_id=paper_id,
        status=job_status,
        revision=document.revision,
        reference_updates=updates,
        progress=progress,
        error=job.failedReason if job_status == "failed" else None,
    )


def map_job_status(value: str) -> str:
    if value in {"waiting", "delayed", "prioritized", "waiting-children"}:
        return "queued"
    if value == "active":
        return "running"
    if value == "completed":
        return "completed"
    if value == "failed":
        return "failed"
    return "not_started"


@router.post(
    "/{paper_id}/citation-audit",
    response_model=CitationAuditJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_citation_audit(
    paper_id: str,
    documents: PaperDocuments,
    audits: CitationAudits,
    queue: CitationAuditQueue,
    source_queue: SourceSearchQueue,
    rerun: Annotated[bool, Query()] = False,
) -> CitationAuditJob:
    """Start the two-lane heuristic verification and full-body citation audit."""
    await documents.get(paper_id)
    audit = await audits.create_or_get(paper_id, claim_audit_model())
    if rerun:
        audit = await audits.reset(audit.id)
    job_id = citation_audit_job_id(paper_id)
    job = await Job.fromId(queue, job_id)
    if rerun and job is not None:
        await job.remove()
        job = None
    if job is None:
        job = await queue.add(
            "audit-missing-citations",
            {"paperId": paper_id, "auditId": audit.id},
            {
                "jobId": job_id,
                "attempts": 4,
                "backoff": {"type": "exponential", "delay": 2_000},
                "removeOnComplete": False,
                "removeOnFail": False,
            },
        )
    if audit.status == "completed":
        await enqueue_pending_source_searches(source_queue, audit_id=audit.id)
    return CitationAuditJob(
        audit_id=audit.id,
        job_id=job_id,
        paper_id=paper_id,
        status=map_job_status(await job.getState()),
        revision=audit.revision,
    )


@router.get(
    "/{paper_id}/citation-audit",
    response_model=CitationAuditStatus,
)
async def get_citation_audit(
    paper_id: str,
    documents: PaperDocuments,
    audits: CitationAudits,
    queue: CitationAuditQueue,
    after_revision: Annotated[int, Query(alias="afterRevision", ge=0)] = 0,
) -> CitationAuditStatus:
    """Poll audit progress and receive only newly confirmed missing citations."""
    await documents.get(paper_id)
    audit = await audits.get_for_paper(paper_id)
    job_id = citation_audit_job_id(paper_id)
    if audit is None:
        return CitationAuditStatus(
            audit_id="not-started",
            job_id=job_id,
            paper_id=paper_id,
            status="not_started",
            revision=1,
            model=claim_audit_model(),
        )

    job = await Job.fromId(queue, job_id)
    job_status = audit.status if audit.status in {"queued", "running"} else (map_job_status(await job.getState()) if job else audit.status)
    return CitationAuditStatus(
        audit_id=audit.id,
        job_id=job_id,
        paper_id=paper_id,
        status=job_status,
        revision=audit.revision,
        model=audit.model,
        progress=audits.progress(audit),
        findings=await audits.list_findings(
            audit.id,
            after_revision=after_revision,
        ),
        dismissed_findings=await audits.list_dismissed_findings(audit.id),
        source_search_pending=await audits.source_search_pending_count(audit.id),
        error=(job.failedReason if job else audit.error) if job_status == "failed" else None,
    )
