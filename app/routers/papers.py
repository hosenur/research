from typing import Annotated

from bullmq import Job, Queue
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status, HTTPException

from app.config import MAX_PDF_SIZE, MAX_TEI_SIZE, claim_audit_model
from app.dependencies import (
    get_citation_audit_queue,
    get_citation_audit_repository,
    get_extraction_artifact_store,
    get_missing_work_finder,
    get_openalex_enricher,
    get_openalex_queue,
    get_paper_index_queue,
    get_paper_document_repository,
    get_paper_service,
    get_source_search_queue,
)
from app.repositories.artifacts import ExtractionArtifactStore
from app.repositories.citation_audits import CitationAuditRepository
from app.repositories.papers import PaperDocumentRepository
from app.schemas.documents import (
    CitationAuditJob,
    CitationAuditStatus,
    CitationFeedbackRequest,
    CitationFeedbackSummary,
    EnrichmentProgress,
    OpenAlexEnrichmentJob,
    OpenAlexEnrichmentStatus,
    PaperDocument,
    PaperJobStatus,
    PaperJobsStatus,
    CitationSourceDecisionRequest,
)
from app.schemas.paper import MissingWorkReport, Paper
from app.services.missing_works import MissingWorkFinder
from app.services.openalex import OpenAlexEnricher
from app.services.papers import PaperService, normalize_tei
from app.workers.source_search import enqueue_pending_source_searches
from app.config import PAPER_INDEX_QUEUE_NAME, bullmq_options

router = APIRouter(prefix="/papers", tags=["papers"])

PdfUpload = Annotated[UploadFile, File(description="Academic paper in PDF format")]
TeiUpload = Annotated[UploadFile, File(description="GROBID TEI XML document")]
PaperParser = Annotated[PaperService, Depends(get_paper_service)]
ReferenceEnricher = Annotated[OpenAlexEnricher, Depends(get_openalex_enricher)]
MissingWorks = Annotated[MissingWorkFinder, Depends(get_missing_work_finder)]
ArtifactStore = Annotated[ExtractionArtifactStore, Depends(get_extraction_artifact_store)]
PaperDocuments = Annotated[PaperDocumentRepository, Depends(get_paper_document_repository)]
OpenAlexQueue = Annotated[Queue, Depends(get_openalex_queue)]
CitationAudits = Annotated[CitationAuditRepository, Depends(get_citation_audit_repository)]
CitationAuditQueue = Annotated[Queue, Depends(get_citation_audit_queue)]
SourceSearchQueue = Annotated[Queue, Depends(get_source_search_queue)]


@router.post("/{paper_id}/citation-audit/findings/{finding_id}/candidates/{candidate_id}/decision")
async def decide_citation_candidate(
    paper_id: str,
    finding_id: str,
    candidate_id: str,
    payload: CitationSourceDecisionRequest,
    documents: PaperDocuments,
    audits: CitationAudits,
) -> dict[str, str]:
    await documents.get(paper_id)
    try:
        candidate = await audits.decide_candidate(paper_id, finding_id, candidate_id, payload.decision)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"candidateId": candidate.id, "decision": candidate.decision}


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
    """Record review feedback without changing the current candidate state."""
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
    return {"feedbackId": record.id, "feedback": record.feedback, "candidateId": record.candidate_id}


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
    await index_queue.add("index-paper", {"paperId": document.id}, {"jobId": f"paper-index-{document.id}", "attempts": 3, "removeOnComplete": False, "removeOnFail": False})
    return document


@router.post("/{paper_id}/index", status_code=status.HTTP_202_ACCEPTED)
async def index_existing_paper(
    paper_id: str,
    documents: PaperDocuments,
    index_queue: Annotated[Queue, Depends(get_paper_index_queue)],
) -> dict[str, str]:
    await documents.get(paper_id)
    job_id = f"paper-index-{paper_id}"
    job = await Job.fromId(index_queue, job_id)
    if job is None:
        await index_queue.add("index-paper", {"paperId": paper_id}, {"jobId": job_id, "attempts": 3, "removeOnComplete": False, "removeOnFail": False})
    return {"paperId": paper_id, "status": "queued"}


@router.get("/{paper_id}", response_model=PaperDocument)
async def get_paper(paper_id: str, documents: PaperDocuments) -> PaperDocument:
    """Return the latest paper projection with persisted provider enrichments."""
    return await documents.get(paper_id)


@router.get("/{paper_id}/jobs", response_model=PaperJobsStatus)
async def get_paper_jobs(
    paper_id: str,
    documents: PaperDocuments,
    openalex_queue: OpenAlexQueue,
    audit_queue: CitationAuditQueue,
    index_queue: Annotated[Queue, Depends(get_paper_index_queue)],
) -> PaperJobsStatus:
    """Expose a single operational view of the long-running paper pipeline."""
    await documents.get(paper_id)
    jobs = [
        ("index", f"paper-index-{paper_id}", index_queue),
        ("openalex", openalex_job_id(paper_id), openalex_queue),
        ("citation-audit", citation_audit_job_id(paper_id), audit_queue),
    ]
    statuses: list[PaperJobStatus] = []
    for name, job_id, queue in jobs:
        job = await Job.fromId(queue, job_id)
        if job is None:
            statuses.append(PaperJobStatus(name=name, job_id=job_id, status="not_started"))
            continue
        progress = job.progress if isinstance(job.progress, dict) else {}
        statuses.append(
            PaperJobStatus(
                name=name,
                job_id=job_id,
                status=map_job_status(await job.getState()),
                progress=progress,
                error=job.failedReason,
            )
        )
    return PaperJobsStatus(paper_id=paper_id, jobs=statuses)


@router.post("/normalize", response_model=Paper)
async def normalize_paper(file: TeiUpload) -> Paper:
    """Normalize an existing GROBID TEI XML document into the internal Paper model."""
    xml = await file.read(MAX_TEI_SIZE + 1)
    return normalize_tei(xml)


@router.get("/artifacts/{artifact_id}/tei")
def get_tei_artifact(artifact_id: str, artifacts: ArtifactStore) -> Response:
    """Download the immutable raw TEI used to create a Paper response."""
    return Response(
        content=artifacts.read_tei(artifact_id),
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
    "/{paper_id}/enrichments/openalex",
    response_model=OpenAlexEnrichmentJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_openalex_enrichment(
    paper_id: str,
    documents: PaperDocuments,
    queue: OpenAlexQueue,
) -> OpenAlexEnrichmentJob:
    """Idempotently enqueue OpenAlex matching after the parse response has returned."""
    await documents.get(paper_id)
    job_id = openalex_job_id(paper_id)
    job = await Job.fromId(queue, job_id)
    if job is None:
        job = await queue.add(
            "enrich-openalex",
            {"paperId": paper_id},
            {
                "jobId": job_id,
                "attempts": 4,
                "backoff": {"type": "exponential", "delay": 2_000},
                "removeOnComplete": False,
                "removeOnFail": False,
            },
        )
    return OpenAlexEnrichmentJob(
        job_id=job_id,
        paper_id=paper_id,
        status=map_job_status(await job.getState()),
    )


@router.get(
    "/{paper_id}/enrichments/openalex",
    response_model=OpenAlexEnrichmentStatus,
)
async def get_openalex_enrichment(
    paper_id: str,
    documents: PaperDocuments,
    queue: OpenAlexQueue,
    after_revision: Annotated[int, Query(alias="afterRevision", ge=0)] = 0,
) -> OpenAlexEnrichmentStatus:
    """Poll BullMQ state and receive only reference updates after a document revision."""
    document = await documents.get(paper_id)
    job_id = openalex_job_id(paper_id)
    job = await Job.fromId(queue, job_id)
    updates = await documents.list_updates(paper_id, after_revision=after_revision)
    if job is None:
        return OpenAlexEnrichmentStatus(
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
    return OpenAlexEnrichmentStatus(
        job_id=job_id,
        paper_id=paper_id,
        status=map_job_status(await job.getState()),
        revision=document.revision,
        reference_updates=updates,
        progress=progress,
        error=job.failedReason,
    )


def openalex_job_id(paper_id: str) -> str:
    return f"openalex-{paper_id}"


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
        source_search_pending=await audits.source_search_pending_count(audit.id),
        error=(job.failedReason if job else audit.error) if job_status == "failed" else None,
    )


def citation_audit_job_id(paper_id: str) -> str:
    return f"citation-audit-{paper_id}"
