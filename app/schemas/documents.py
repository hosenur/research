from typing import Literal

from pydantic import Field

from app.schemas.paper import ApiModel, ExtractionPointer, OpenAlexWork, Paper


class PaperDocument(ApiModel):
    id: str
    revision: int = Field(ge=1)
    paper: Paper


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
