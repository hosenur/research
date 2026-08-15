from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.paper import ApiModel, ExtractionPointer, OpenAlexWork, Paper


class PaperDocument(ApiModel):
    id: str
    revision: int = Field(ge=1)
    paper: Paper


class PaperLifecycle(ApiModel):
    id: str
    filename: str
    status: Literal["uploaded", "parsing", "ready", "failed"]
    revision: int = Field(ge=1)
    manuscript_revision: int = Field(default=1, ge=1)
    paper: Paper | None = None
    error: str | None = None
    source_url: str
    retrieval_mode: Literal["unavailable", "provisional", "authoritative"] = "unavailable"


class PaperPipelineStage(ApiModel):
    name: str
    status: Literal["not_started", "queued", "running", "completed", "failed", "skipped"]
    attempt: int = Field(default=0, ge=0)
    revision: int = Field(default=1, ge=1)
    progress: dict[str, object] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class PaperPipeline(ApiModel):
    paper_id: str
    stages: list[PaperPipelineStage] = Field(default_factory=list)


class ClaimCitationFinding(ApiModel):
    id: str
    sentence_id: str
    section_id: str
    section_title: str
    paragraph_id: str
    citation_id: str | None = None
    reference_id: str
    claim_text: str
    citation_text: str
    work_title: str | None = None
    source_url: str | None = None
    providers: list[str] = Field(default_factory=list)
    priority_score: float | None = None
    classification: Literal["supported", "weak", "contradicted", "unverifiable"]
    confidence: float = Field(ge=0, le=1)
    explanation: str
    evidence_text: str | None = None


class ClaimCitationReviewStatus(ApiModel):
    paper_id: str
    status: Literal["not_started", "queued", "running", "completed", "failed"]
    findings: list[ClaimCitationFinding] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    completed: int = Field(default=0, ge=0)
    error: str | None = None


class EditCommandRequest(ApiModel):
    command: str = Field(min_length=3, max_length=4_000)
    base_revision: int = Field(ge=1)


class BibliographyChange(ApiModel):
    action: Literal["add", "reuse", "remove", "retain", "update"]
    reference_id: str
    citation_marker: str | None = None
    before_text: str | None = None
    after_text: str | None = None


class EditOperation(ApiModel):
    id: str
    position: int = Field(ge=0)
    operation_type: Literal[
        "replace_text",
        "insert_citation",
        "remove_citation",
        "restore_revision",
        "citation_change",
    ]
    node_ids: list[str] = Field(default_factory=list)
    before_text: str
    after_text: str
    rationale: str
    validation_status: Literal["valid", "invalid"]
    validation_error: str | None = None
    approved: bool = False
    bibliography_change: BibliographyChange | None = None
    bibliography_changes: list[BibliographyChange] = Field(default_factory=list)


class EditProposal(ApiModel):
    id: str
    paper_id: str
    base_revision: int = Field(ge=1)
    command: str
    status: Literal["planned", "approved", "rejected", "conflict", "invalid"]
    summary: str
    warnings: list[str] = Field(default_factory=list)
    operations: list[EditOperation] = Field(default_factory=list)
    approved_revision: int | None = None


class EditApprovalRequest(ApiModel):
    operation_ids: list[str] | None = None


class RevisionRevertRequest(ApiModel):
    operation_ids: list[str]


class ManuscriptRevisionSummary(ApiModel):
    revision: int = Field(ge=1)
    parent_revision: int | None = None
    source: Literal["parse", "edit", "restore", "revert"]
    summary: str | None = None
    proposal_id: str | None = None
    created_at: datetime
    operations: list[EditOperation] = Field(default_factory=list)


class ManuscriptRevisionDetail(ManuscriptRevisionSummary):
    paper: Paper


class ManuscriptRevisionList(ApiModel):
    paper_id: str
    current_revision: int = Field(ge=1)
    revisions: list[ManuscriptRevisionSummary] = Field(default_factory=list)


class CitationStyleRequest(ApiModel):
    style_id: str = Field(min_length=1, max_length=255)


class CitationStyleStatus(ApiModel):
    paper_id: str
    style_id: str | None = None
    confirmed: bool = False
    detected_family: str | None = None
    candidates: list[dict[str, str]] = Field(default_factory=list)


class PaperExportRequest(ApiModel):
    revision: int = Field(ge=1)


class PaperExport(ApiModel):
    id: str
    paper_id: str
    revision: int = Field(ge=1)
    style_id: str
    status: Literal["queued", "running", "completed", "failed"]
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    latex_url: str | None = None
    pdf_url: str | None = None


class SectionReviewRequest(ApiModel):
    section_ids: list[str] = Field(min_length=1, max_length=5)


class ReferenceEnrichmentUpdate(ApiModel):
    reference_id: str
    provider: Literal["openalex"] = "openalex"
    status: Literal["matched", "unmatched", "error", "skipped"]
    openalex: OpenAlexWork | None = None
    error: str | None = None
    revision: int = Field(ge=1)


class EnrichmentProgress(ApiModel):
    total: int = Field(default=0, ge=0)
    completed: int = Field(default=0, ge=0)
    matched: int = Field(default=0, ge=0)
    unmatched: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)


EnrichmentJobStatus = Literal[
    "not_started",
    "queued",
    "running",
    "completed",
    "failed",
]


class OpenAlexEnrichmentJob(ApiModel):
    job_id: str
    paper_id: str
    status: EnrichmentJobStatus


class OpenAlexEnrichmentStatus(OpenAlexEnrichmentJob):
    progress: EnrichmentProgress = Field(default_factory=EnrichmentProgress)
    revision: int = Field(ge=1)
    reference_updates: list[ReferenceEnrichmentUpdate] = Field(default_factory=list)
    error: str | None = None


CitationAuditJobStatus = Literal[
    "not_started",
    "queued",
    "running",
    "completed",
    "failed",
]


class CitationSourceWork(ApiModel):
    id: str
    title: str
    year: int | None = None
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    authors: list[dict[str, str]] = Field(default_factory=list)
    landing_page_url: str | None = None
    cited_by_count: int | None = None
    providers: list[Literal["openalex", "semantic-scholar"]] = Field(default_factory=list)
    provider_ids: dict[str, str] = Field(default_factory=dict)


class CitationSourceCandidate(ApiModel):
    id: str
    rank: int = Field(ge=1)
    score: float = Field(ge=0, le=1)
    reason: str
    support_status: Literal["not_started", "running", "verified", "rejected", "failed"] = "not_started"
    supports_claim: bool | None = None
    support_confidence: float | None = None
    support_explanation: str | None = None
    support_evidence: str | None = None
    decision: Literal["pending", "accepted", "rejected"] = "pending"
    work: CitationSourceWork


class CitationAuditFinding(ApiModel):
    id: str
    sentence_id: str
    section_id: str
    section_title: str
    paragraph_id: str
    sentence_text: str
    source_text: str
    claim_text: str
    claim_type: Literal[
        "quantitative",
        "comparative",
        "causal",
        "empirical",
        "background",
        "association",
        "generalization",
        "other",
    ]
    confidence: float = Field(ge=0, le=1)
    explanation: str
    detected_by: list[Literal["verbal-heuristic", "ai"]]
    heuristic_reasons: list[str] = Field(default_factory=list)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    source: ExtractionPointer | None = None
    source_search_status: Literal["not_started", "queued", "running", "completed", "failed"]
    source_search_error: str | None = None
    source_candidates: list[CitationSourceCandidate] = Field(default_factory=list)
    revision: int = Field(ge=1)


class CitationAuditProgress(ApiModel):
    total_sentences: int = Field(default=0, ge=0)
    heuristic_candidates: int = Field(default=0, ge=0)
    priority_total: int = Field(default=0, ge=0)
    priority_completed: int = Field(default=0, ge=0)
    discovery_total: int = Field(default=0, ge=0)
    discovery_completed: int = Field(default=0, ge=0)


class CitationAuditJob(ApiModel):
    audit_id: str
    job_id: str
    paper_id: str
    status: CitationAuditJobStatus
    revision: int = Field(ge=1)


class CitationAuditStatus(CitationAuditJob):
    model: str
    progress: CitationAuditProgress = Field(default_factory=CitationAuditProgress)
    findings: list[CitationAuditFinding] = Field(default_factory=list)
    dismissed_findings: list[CitationAuditFinding] = Field(default_factory=list)
    source_search_pending: int = Field(default=0, ge=0)
    error: str | None = None


class CitationSourceDecisionRequest(ApiModel):
    decision: Literal["accepted", "rejected"]


class CitationFeedbackRequest(ApiModel):
    feedback: Literal[
        "accepted_source",
        "rejected_source",
        "false_positive",
        "needs_review",
    ]
    candidate_id: str | None = None
    note: str | None = Field(default=None, max_length=2_000)
    actor_id: str = Field(default="anonymous", min_length=1, max_length=128)


class CitationFeedbackSummary(ApiModel):
    paper_id: str
    total: int = Field(ge=0)
    by_feedback: dict[str, int] = Field(default_factory=dict)
    accepted_source_rate: float | None = Field(default=None, ge=0, le=1)
    accepted_by_rank: dict[str, int] = Field(default_factory=dict)


class PaperJobStatus(ApiModel):
    name: str
    job_id: str
    status: Literal["not_started", "queued", "running", "completed", "failed"]
    progress: dict[str, object] = Field(default_factory=dict)
    error: str | None = None


class PaperJobsStatus(ApiModel):
    paper_id: str
    jobs: list[PaperJobStatus] = Field(default_factory=list)
