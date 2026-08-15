import asyncio
import hashlib
import json
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
from sqlalchemy import delete, select

from app.database.models import (
    CitationAuditFindingRecord,
    CitationAuditRecord,
    CitationSourceCandidateRecord,
    ManuscriptRevisionRecord,
    PaperCSLStyleRecord,
    PaperRecord,
    ProviderCacheRecord,
    ReferenceEnrichmentRecord,
    ScholarlyWorkRecord,
)
from app.database.session import get_session_factory
from app.repositories.citation_audits import CitationAuditRepository
from app.repositories.claim_citations import ClaimCitationReviewRepository
from app.repositories.openalex import OpenAlexRepository
from app.repositories.papers import PaperDocumentRepository
from app.repositories.semantic_scholar import SemanticScholarRepository
from app.repositories.scholarly_works import ScholarlyWorkRepository
from app.schemas.paper import CitationNode, Paper, TextNode
from app.services.manuscript_revisions import (
    ManuscriptRevisionService,
    citation_identity,
    content_hash,
    structure_identity,
)
from app.services.paper_exports import CSLPaperExporter
from app.services.openalex import OpenAlexEnricher
from app.services.reference_evidence import (
    BibliographyEvidenceResolver,
    ProviderReferenceEvidence,
    choose_semantic_scholar_match,
    reconcile_provider_matches,
)
from app.services.source_search import SourceSupportVerifier
from app.services.tei_parser import parse_tei


FIXTURES = Path(__file__).parent / "fixtures"


class _UnusedPlanner:
    model = "architecture-integration"


class _FakeResponses:
    def __init__(self, payload: dict | None = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    async def create(self, **_kwargs):
        if self.error:
            raise self.error
        return SimpleNamespace(output_text=json.dumps(self.payload))


class _FakeOpenAI:
    def __init__(self, payload: dict | None = None, error: Exception | None = None) -> None:
        self.responses = _FakeResponses(payload, error)


def inverted_abstract(value: str) -> dict[str, list[int]]:
    output: dict[str, list[int]] = {}
    for index, word in enumerate(value.split()):
        output.setdefault(word, []).append(index)
    return output


class ArchitectureFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_parse_provider_proposal_approval_export_preserves_manuscript(self) -> None:
        paper = parse_tei((FIXTURES / "bert.tei.xml").read_bytes())
        selected_sections = []
        has_citation = False
        target = None
        for section in paper.sections:
            selected_sections.append(section)
            for paragraph in section.paragraphs:
                has_citation = has_citation or any(
                    isinstance(node, CitationNode) for node in paragraph.nodes
                )
                if target is None:
                    target = next(
                        (
                            (paragraph, node)
                            for node in paragraph.nodes
                            if isinstance(node, TextNode) and len(node.text.strip()) >= 80
                        ),
                        None,
                    )
            if has_citation and target is not None:
                break
        self.assertTrue(has_citation)
        self.assertIsNotNone(target)
        paper.sections = selected_sections
        cited_ids = {
            source_id
            for section in paper.sections
            for paragraph in section.paragraphs
            for node in paragraph.nodes
            if isinstance(node, CitationNode)
            for source_id in node.source_ids
        }
        paper.references = [
            reference
            for reference in paper.references
            if reference.id in cited_ids and reference.csl is not None
        ]
        evidence_reference = paper.references[0].model_copy(deep=True)

        paper_id = str(uuid.uuid4())
        audit_id = str(uuid.uuid4())
        finding_id = str(uuid.uuid4())
        provider_token = str(uuid.uuid4())
        openalex_id = f"https://openalex.org/W{provider_token}"
        semantic_id = f"semantic-{provider_token}"
        source_title = f"Verified Architecture Evidence {provider_token}"
        source_abstract = (
            "The controlled evidence supports the anchored architecture claim."
        )
        source_doi = f"10.9999/{provider_token}"
        evidence_reference.csl.title = source_title
        evidence_reference.csl.doi = source_doi
        evidence_reference.csl.issued = None
        openalex_payload = {
            "id": openalex_id,
            "doi": f"https://doi.org/{source_doi}",
            "display_name": source_title,
            "publication_year": 2024,
            "ids": {"openalex": openalex_id, "doi": f"https://doi.org/{source_doi}"},
            "abstract_inverted_index": inverted_abstract(source_abstract),
            "primary_location": {"landing_page_url": openalex_id},
            "cited_by_count": 3,
            "authorships": [
                {"author": {"display_name": "Ada Evidence"}}
            ],
        }
        semantic_payload = {
            "data": [
                {
                    "paperId": semantic_id,
                    "title": source_title,
                    "abstract": source_abstract,
                    "year": 2024,
                    "authors": [{"name": "Ada Evidence"}],
                    "externalIds": {"DOI": source_doi},
                    "url": f"https://www.semanticscholar.org/paper/{semantic_id}",
                    "citationCount": 3,
                }
            ]
        }
        work_id = None
        cache_keys: list[tuple[str, str]] = []
        session_factory = get_session_factory()
        try:
            paragraph, text_node = target
            find_text = text_node.text.strip()[:80].rstrip()
            start_offset = text_node.text.index(find_text)
            original_citations = citation_identity(paper)
            original_structure = structure_identity(paper)
            payload = paper.model_dump(mode="json", by_alias=True)

            async with session_factory() as session:
                session.add(
                    PaperRecord(
                        id=paper_id,
                        filename="bert.pdf",
                        content_sha256=hashlib.sha256(paper_id.encode()).hexdigest(),
                        paper_json=payload,
                        status="ready",
                        revision=1,
                        manuscript_revision=1,
                    )
                )
                await session.flush()
                session.add(
                    ManuscriptRevisionRecord(
                        id=str(uuid.uuid4()),
                        paper_id=paper_id,
                        revision=1,
                        parent_revision=None,
                        paper_json=payload,
                        content_hash=content_hash(payload),
                        source="parse",
                        summary="Authoritative parse",
                    )
                )
                session.add(
                    PaperCSLStyleRecord(
                        paper_id=paper_id,
                        style_id="apa",
                        confirmed=True,
                        detected_family="author-year",
                    )
                )
                session.add(
                    CitationAuditRecord(
                        id=audit_id,
                        paper_id=paper_id,
                        status="completed",
                        model="architecture-integration",
                        revision=1,
                    )
                )
                await session.flush()
                session.add(
                    CitationAuditFindingRecord(
                        id=finding_id,
                        audit_id=audit_id,
                        sentence_id=f"{paragraph.id}:integration",
                        section_id=next(
                            section.id
                            for section in paper.sections
                            if paragraph in section.paragraphs
                        ),
                        section_title=next(
                            section.title
                            for section in paper.sections
                            if paragraph in section.paragraphs
                        ),
                        paragraph_id=paragraph.id,
                        sentence_text=find_text,
                        source_text=find_text,
                        claim_text=find_text,
                        claim_hash=hashlib.sha256(find_text.encode()).hexdigest(),
                        claim_type="empirical",
                        confidence=0.95,
                        explanation="Architecture integration fixture",
                        detected_by=["ai"],
                        heuristic_reasons=[],
                        start_offset=start_offset,
                        end_offset=start_offset + len(find_text),
                        source_search_status="completed",
                        source_search_version=1,
                        model="architecture-integration",
                        revision=1,
                    )
                )
                await session.commit()

            works = ScholarlyWorkRepository(session_factory)
            openalex_client = httpx.AsyncClient(
                base_url="https://openalex.test",
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200, json=openalex_payload, request=request
                    )
                ),
            )
            semantic_client = httpx.AsyncClient(
                base_url="https://semantic.test",
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200, json=semantic_payload, request=request
                    )
                ),
            )
            try:
                openalex_repository = OpenAlexRepository(
                    openalex_client, cache=works
                )
                semantic_repository = SemanticScholarRepository(
                    semantic_client, works
                )
                cache_keys.extend(
                    [
                        (
                            "openalex",
                            openalex_repository._cache_key(  # noqa: SLF001
                                "/works",
                                {
                                    "filter": f"doi:{source_doi}",
                                    "per-page": "1",
                                },
                            ),
                        ),
                        (
                            "semantic-scholar",
                            semantic_repository._cache_key(  # noqa: SLF001
                                "/paper/search",
                                {
                                    "query": source_doi,
                                    "limit": "5",
                                    "fields": semantic_repository._fields,  # noqa: SLF001
                                },
                            ),
                        ),
                    ]
                )
                resolution = await BibliographyEvidenceResolver(
                    OpenAlexEnricher(openalex_repository),
                    semantic_repository,
                    works,
                ).resolve(evidence_reference, asyncio.Semaphore(2))
            finally:
                await openalex_client.aclose()
                await semantic_client.aclose()

            self.assertEqual(resolution.reconciliation.status, "agreed")
            self.assertEqual(
                {item.provider for item in resolution.providers if item.status == "matched"},
                {"openalex", "semantic-scholar"},
            )
            self.assertEqual(
                len(
                    {
                        item.work_id
                        for item in resolution.providers
                        if item.status == "matched"
                    }
                ),
                1,
            )
            async with session_factory() as session:
                documents = PaperDocumentRepository(session)
                for provider in resolution.providers:
                    await documents.save_provider_enrichment(
                        paper_id,
                        evidence_reference.id,
                        provider=provider.provider,
                        work_id=provider.work_id,
                        status=provider.status,
                        work_json=provider.work_json,
                        match_method=provider.match_method,
                        confidence=provider.confidence,
                        error=provider.error,
                    )
                stored_matches = list(
                    await session.scalars(
                        select(ReferenceEnrichmentRecord).where(
                            ReferenceEnrichmentRecord.paper_id == paper_id,
                            ReferenceEnrichmentRecord.reference_id
                            == evidence_reference.id,
                        )
                    )
                )
                self.assertEqual(
                    {item.provider for item in stored_matches},
                    {"openalex", "semantic-scholar"},
                )
                reconciled = (
                    await ClaimCitationReviewRepository(session).reference_evidence(
                        paper_id
                    )
                )[evidence_reference.id]
            self.assertEqual(reconciled.reconciliation_status, "agreed")
            self.assertIn(reconciled.abstract_provider, {"openalex", "semantic-scholar"})
            self.assertEqual(
                reconciled.payloads[reconciled.abstract_provider]["abstractProvider"],
                reconciled.abstract_provider,
            )
            self.assertEqual(
                set(reconciled.identifier_providers["doi"]["providers"]),
                {"openalex", "semantic-scholar"},
            )
            work_id = reconciled.work_id
            self.assertIsNotNone(work_id)

            verifier = SourceSupportVerifier(
                _FakeOpenAI(
                    {
                        "status": "verified",
                        "confidence": 0.99,
                        "explanation": "The abstract supports the exact claim.",
                        "evidence": "supports the anchored architecture claim",
                    }
                ),
                api_key="test-key",
                model="fake-verifier",
            )
            decision = await verifier.verify(find_text, source_title, reconciled.abstract)
            self.assertEqual(decision.status, "verified")

            async with session_factory() as session:
                audits = CitationAuditRepository(session)
                await audits.replace_source_candidates(
                    finding_id,
                    [(work_id, 0.99, "Dual-provider reconciled evidence")],
                )
                candidate_id = await session.scalar(
                    select(CitationSourceCandidateRecord.id).where(
                        CitationSourceCandidateRecord.finding_id == finding_id,
                        CitationSourceCandidateRecord.work_id == work_id,
                    )
                )
                self.assertIsNotNone(candidate_id)
                await audits.update_candidate_supports([(candidate_id, decision)])
                candidate = await session.get(
                    CitationSourceCandidateRecord, candidate_id
                )
                self.assertEqual(candidate.support_status, "verified")
                self.assertTrue(candidate.supports_claim)

            async with session_factory() as session:
                revisions = ManuscriptRevisionService(session, _UnusedPlanner())
                proposal = await revisions.propose_verified_source(
                    paper_id, finding_id, candidate_id
                )
                approved = await revisions.approve(
                    paper_id,
                    proposal.id,
                    [operation.id for operation in proposal.operations],
                )
                self.assertEqual(approved.approved_revision, 2)
                record = await session.scalar(
                    select(ManuscriptRevisionRecord).where(
                        ManuscriptRevisionRecord.paper_id == paper_id,
                        ManuscriptRevisionRecord.revision == 2,
                    )
                )
                self.assertIsNotNone(record)
                revised = Paper.model_validate(record.paper_json)

            self.assertEqual(structure_identity(revised), original_structure)
            self.assertTrue(original_citations <= citation_identity(revised))
            self.assertTrue(
                any(reference.raw_text.startswith("Ada Evidence") for reference in revised.references)
            )
            inserted = next(
                node
                for section in revised.sections
                for paragraph in section.paragraphs
                for node in paragraph.nodes
                if isinstance(node, CitationNode)
                and any(
                    reference.raw_text.startswith("Ada Evidence")
                    and reference.id in node.source_ids
                    for reference in revised.references
                )
            )
            self.assertIsNotNone(inserted.anchor)
            self.assertGreater(inserted.anchor.end_offset, inserted.anchor.start_offset)
            generated = CSLPaperExporter().generate(revised, "apa")
            self.assertTrue(generated.pdf.startswith(b"%PDF-"))
            self.assertIn(b"main.tex", generated.latex_bundle)
        finally:
            async with session_factory() as session:
                await session.execute(delete(PaperRecord).where(PaperRecord.id == paper_id))
                for provider, cache_key in cache_keys:
                    await session.execute(
                        delete(ProviderCacheRecord).where(
                            ProviderCacheRecord.provider == provider,
                            ProviderCacheRecord.cache_key == cache_key,
                        )
                    )
                if work_id:
                    await session.execute(
                        delete(ScholarlyWorkRecord).where(ScholarlyWorkRecord.id == work_id)
                    )
                await session.commit()


class SourceSupportVerificationTest(unittest.IsolatedAsyncioTestCase):
    async def test_missing_verifier_key_is_unverifiable_and_not_actionable(self) -> None:
        decision = await SourceSupportVerifier(
            client=None,  # type: ignore[arg-type]
            api_key=None,
            model="unused",
        ).verify("A claim", "A provider source", "A provider abstract")
        self.assertEqual(decision.status, "unverifiable")

    async def test_missing_abstract_is_unverifiable(self) -> None:
        decision = await self.verifier(
            status="verified", evidence="real evidence"
        ).verify("A claim", "A source", None)
        self.assertEqual(decision.status, "unverifiable")

    async def test_empty_evidence_cannot_be_verified(self) -> None:
        decision = await self.verifier(status="verified", evidence="").verify(
            "A claim", "A source", "The provider abstract contains real evidence."
        )
        self.assertEqual(decision.status, "unverifiable")

    async def test_fabricated_evidence_cannot_be_verified(self) -> None:
        decision = await self.verifier(
            status="verified", evidence="words that are not in the abstract"
        ).verify("A claim", "A source", "The provider abstract contains real evidence.")
        self.assertEqual(decision.status, "unverifiable")

    async def test_api_failure_is_unverifiable(self) -> None:
        decision = await SourceSupportVerifier(
            _FakeOpenAI(error=RuntimeError("offline")),
            api_key="test-key",
            model="fake",
        ).verify("A claim", "A source", "The provider abstract contains real evidence.")
        self.assertEqual(decision.status, "unverifiable")

    async def test_valid_abstract_evidence_is_verified(self) -> None:
        decision = await self.verifier(
            status="verified", evidence="contains real evidence"
        ).verify("A claim", "A source", "The provider abstract contains real evidence.")
        self.assertEqual(decision.status, "verified")
        self.assertEqual(decision.evidence, "contains real evidence")

    @staticmethod
    def verifier(*, status: str, evidence: str) -> SourceSupportVerifier:
        return SourceSupportVerifier(
            _FakeOpenAI(
                {
                    "status": status,
                    "confidence": 0.9,
                    "explanation": "Deterministic verification fixture.",
                    "evidence": evidence,
                }
            ),
            api_key="test-key",
            model="fake",
        )


class ProviderReconciliationTest(unittest.TestCase):
    def test_dual_provider_identifier_agreement(self) -> None:
        result = reconcile_provider_matches(
            (
                provider_evidence("openalex", doi="10.1000/shared"),
                provider_evidence("semantic-scholar", doi="10.1000/shared"),
            )
        )
        self.assertEqual(result.status, "agreed")

    def test_provider_identifier_disagreement_is_ambiguous(self) -> None:
        result = reconcile_provider_matches(
            (
                provider_evidence("openalex", doi="10.1000/left"),
                provider_evidence("semantic-scholar", doi="10.1000/right"),
            )
        )
        self.assertEqual(result.status, "ambiguous")

    def test_single_provider_evidence_stays_independent(self) -> None:
        result = reconcile_provider_matches(
            (
                provider_evidence("openalex", doi="10.1000/single"),
                ProviderReferenceEvidence(
                    provider="semantic-scholar", status="unmatched"
                ),
            )
        )
        self.assertEqual(result.status, "single-provider")
        self.assertEqual(result.providers, ("openalex",))


def provider_evidence(provider: str, *, doi: str) -> ProviderReferenceEvidence:
    return ProviderReferenceEvidence(
        provider=provider,
        status="matched",
        provider_id=f"{provider}-id",
        work_id=f"{provider}-work",
        title="Shared Evidence",
        abstract="The provider abstract contains real evidence.",
        doi=doi,
        year=2024,
        authors=("Ada Evidence",),
    )


class SemanticScholarMatchingTest(unittest.TestCase):
    def test_doi_match_is_exact(self) -> None:
        from app.repositories.scholarly_works import works_from_response

        candidates = works_from_response(
            "semantic-scholar",
            {
                "data": [
                    {
                        "paperId": "semantic-1",
                        "title": "Exact Evidence",
                        "year": 2020,
                        "abstract": "Evidence.",
                        "authors": [{"name": "Ada Evidence"}],
                        "externalIds": {"DOI": "10.1000/exact"},
                    }
                ]
            },
        )
        match = choose_semantic_scholar_match(
            candidates,
            doi="https://doi.org/10.1000/exact",
            arxiv=None,
            title="Exact Evidence",
            year=2020,
            author="Evidence",
        )
        self.assertIsNotNone(match)
        self.assertEqual(match[1:], ("doi", "high"))


if __name__ == "__main__":
    unittest.main()
