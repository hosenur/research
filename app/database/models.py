from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


class PaperRecord(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    paper_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="uploaded", server_default="uploaded"
    )
    source_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parse_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    manuscript_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatThreadRecord(Base):
    __tablename__ = "chat_threads"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    paper_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_thread_sequence", "thread_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), ForeignKey("chat_threads.id", ondelete="CASCADE"))
    paper_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaperChunkRecord(Base):
    __tablename__ = "paper_chunks"
    __table_args__ = (
        UniqueConstraint(
            "paper_id",
            "index_kind",
            "generation",
            "chunk_key",
            name="uq_paper_chunk_generation_key",
        ),
        Index(
            "ix_paper_chunks_paper_index_order",
            "paper_id",
            "index_kind",
            "generation",
            "chunk_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"))
    chunk_key: Mapped[str] = mapped_column(String(255))
    chunk_type: Mapped[str] = mapped_column(String(32))
    section_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_node_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    index_kind: Mapped[str] = mapped_column(
        String(32), default="authoritative", server_default="authoritative"
    )
    paper_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    generation: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    text: Mapped[str] = mapped_column(Text)
    chunk_order: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaperPipelineStageRecord(Base):
    __tablename__ = "paper_pipeline_stages"
    __table_args__ = (
        Index("ix_paper_pipeline_stages_status", "paper_id", "status"),
    )

    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    stage: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(
        String(32), default="not_started", server_default="not_started"
    )
    attempt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReferenceEnrichmentRecord(Base):
    __tablename__ = "reference_enrichments"
    __table_args__ = (
        Index("ix_reference_enrichments_paper_revision", "paper_id", "revision"),
    )

    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    reference_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    work_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scholarly_works.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32))
    work_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    match_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CitationAuditRecord(Base):
    __tablename__ = "citation_audits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", server_default="queued")
    model: Mapped[str] = mapped_column(String(128))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    total_sentences: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    heuristic_candidates: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    priority_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    priority_completed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    discovery_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    discovery_completed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CitationAuditBatchRecord(Base):
    __tablename__ = "citation_audit_batches"

    audit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("citation_audits.id", ondelete="CASCADE"), primary_key=True
    )
    lane: Mapped[str] = mapped_column(String(32), primary_key=True)
    batch_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    item_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CitationAuditFindingRecord(Base):
    __tablename__ = "citation_audit_findings"
    __table_args__ = (
        UniqueConstraint("audit_id", "claim_hash", name="uq_citation_audit_finding_claim"),
        Index("ix_citation_audit_findings_revision", "audit_id", "revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    audit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("citation_audits.id", ondelete="CASCADE")
    )
    sentence_id: Mapped[str] = mapped_column(String(255))
    section_id: Mapped[str] = mapped_column(String(255))
    section_title: Mapped[str] = mapped_column(String(512))
    paragraph_id: Mapped[str] = mapped_column(String(255))
    sentence_text: Mapped[str] = mapped_column(Text)
    source_text: Mapped[str] = mapped_column(Text)
    claim_text: Mapped[str] = mapped_column(Text)
    claim_hash: Mapped[str] = mapped_column(String(64))
    claim_type: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    detected_by: Mapped[list[str]] = mapped_column(JSONB)
    heuristic_reasons: Mapped[list[str]] = mapped_column(JSONB)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    source_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_search_status: Mapped[str] = mapped_column(
        String(32), default="not_started", server_default="not_started"
    )
    source_search_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_search_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    model: Mapped[str] = mapped_column(String(128))
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CitationAuditDecisionRecord(Base):
    __tablename__ = "citation_audit_decisions"
    __table_args__ = (
        Index("ix_citation_audit_decisions_audit_sentence", "audit_id", "sentence_id"),
    )

    audit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("citation_audits.id", ondelete="CASCADE"), primary_key=True
    )
    lane: Mapped[str] = mapped_column(String(32), primary_key=True)
    batch_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    sentence_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    model: Mapped[str] = mapped_column(String(128), primary_key=True)
    is_verifiable_claim: Mapped[bool]
    requires_citation: Mapped[bool]
    source_text: Mapped[str] = mapped_column(Text)
    claim_text: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    accepted: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaimCitationReviewRecord(Base):
    __tablename__ = "claim_citation_reviews"
    __table_args__ = (
        UniqueConstraint(
            "paper_id", "paper_revision", "sentence_id", "reference_id",
            name="uq_claim_citation_review_pair",
        ),
        Index(
            "ix_claim_citation_reviews_paper_classification",
            "paper_id", "classification",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"))
    paper_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    sentence_id: Mapped[str] = mapped_column(String(255))
    section_id: Mapped[str] = mapped_column(String(255))
    section_title: Mapped[str] = mapped_column(String(512))
    paragraph_id: Mapped[str] = mapped_column(String(255))
    citation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_id: Mapped[str] = mapped_column(String(255))
    claim_text: Mapped[str] = mapped_column(Text)
    citation_text: Mapped[str] = mapped_column(Text)
    work_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("scholarly_works.id", ondelete="SET NULL"), nullable=True)
    work_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification: Mapped[str] = mapped_column(String(32), default="unverifiable", server_default="unverifiable")
    confidence: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    explanation: Mapped[str] = mapped_column(Text, default="", server_default="")
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ManuscriptRevisionRecord(Base):
    __tablename__ = "manuscript_revisions"
    __table_args__ = (
        UniqueConstraint("paper_id", "revision", name="uq_manuscript_revision_number"),
        Index("ix_manuscript_revisions_paper_created", "paper_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    parent_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paper_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32), default="parse", server_default="parse")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EditProposalRecord(Base):
    __tablename__ = "edit_proposals"
    __table_args__ = (Index("ix_edit_proposals_paper_created", "paper_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"))
    base_revision: Mapped[int] = mapped_column(Integer)
    command: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="planned", server_default="planned")
    summary: Mapped[str] = mapped_column(Text)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    model: Mapped[str] = mapped_column(String(128))
    approved_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EditOperationRecord(Base):
    __tablename__ = "edit_operations"
    __table_args__ = (
        UniqueConstraint("proposal_id", "position", name="uq_edit_operation_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(36), ForeignKey("edit_proposals.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    operation_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    node_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    before_text: Mapped[str] = mapped_column(Text)
    after_text: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="", server_default="")
    validation_status: Mapped[str] = mapped_column(String(32))
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaperCSLStyleRecord(Base):
    __tablename__ = "paper_csl_styles"

    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    style_id: Mapped[str] = mapped_column(String(255))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    detected_family: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PaperExportRecord(Base):
    __tablename__ = "paper_exports"
    __table_args__ = (Index("ix_paper_exports_paper_created", "paper_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"))
    manuscript_revision: Mapped[int] = mapped_column(Integer)
    style_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="queued", server_default="queued")
    latex_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    compiler_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderCacheRecord(Base):
    __tablename__ = "provider_cache"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    response_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    is_negative: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScholarlyWorkRecord(Base):
    __tablename__ = "scholarly_works"
    __table_args__ = (
        Index("ix_scholarly_works_doi", "doi"),
        Index("ix_scholarly_works_arxiv_id", "arxiv_id"),
        Index("ix_scholarly_works_title_normalized", "title_normalized"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_key: Mapped[str] = mapped_column(String(128), unique=True)
    title: Mapped[str] = mapped_column(Text)
    title_normalized: Mapped[str] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(512), nullable=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    landing_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    cited_by_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_ids: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")
    provider_payloads: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CitationSourceCandidateRecord(Base):
    __tablename__ = "citation_source_candidates"
    __table_args__ = (
        UniqueConstraint("finding_id", "work_id", name="uq_citation_source_candidate_work"),
        Index("ix_citation_source_candidates_finding_rank", "finding_id", "rank"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    finding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("citation_audit_findings.id", ondelete="CASCADE")
    )
    work_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scholarly_works.id", ondelete="CASCADE")
    )
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    support_status: Mapped[str] = mapped_column(String(32), default="not_started", server_default="not_started")
    supports_claim: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    support_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    support_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    support_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CitationClaimSearchRecord(Base):
    __tablename__ = "citation_claim_searches"
    __table_args__ = (
        UniqueConstraint(
            "claim_hash",
            "search_version",
            name="uq_citation_claim_search_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    claim_hash: Mapped[str] = mapped_column(String(64))
    claim_text: Mapped[str] = mapped_column(Text)
    query_text: Mapped[str] = mapped_column(Text)
    search_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CitationClaimSearchResultRecord(Base):
    __tablename__ = "citation_claim_search_results"
    __table_args__ = (UniqueConstraint("search_id", "work_id", name="uq_citation_claim_search_result"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    search_id: Mapped[str] = mapped_column(String(36), ForeignKey("citation_claim_searches.id", ondelete="CASCADE"))
    work_id: Mapped[str] = mapped_column(String(36), ForeignKey("scholarly_works.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)


class ConfirmedCitationRecord(Base):
    __tablename__ = "confirmed_citations"
    __table_args__ = (UniqueConstraint("finding_id", "work_id", name="uq_confirmed_citation_finding_work"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"))
    finding_id: Mapped[str] = mapped_column(String(36), ForeignKey("citation_audit_findings.id", ondelete="CASCADE"))
    work_id: Mapped[str] = mapped_column(String(36), ForeignKey("scholarly_works.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="accepted", server_default="accepted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CitationFeedbackRecord(Base):
    """Human feedback retained separately from the current candidate state.

    Candidate decisions are mutable; this append-only-ish record preserves the
    signal needed to evaluate and improve source ranking over time.
    """

    __tablename__ = "citation_feedback"
    __table_args__ = (
        Index("ix_citation_feedback_paper_created", "paper_id", "created_at"),
        Index("ix_citation_feedback_finding", "finding_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"))
    finding_id: Mapped[str] = mapped_column(String(36), ForeignKey("citation_audit_findings.id", ondelete="CASCADE"))
    candidate_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("citation_source_candidates.id", ondelete="SET NULL"), nullable=True
    )
    feedback: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str] = mapped_column(String(128), default="anonymous", server_default="anonymous")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
