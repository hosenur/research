import hashlib
import unittest
import uuid
from pathlib import Path

from sqlalchemy import delete, select

from app.database.models import (
    CitationAuditFindingRecord,
    CitationAuditRecord,
    CitationSourceCandidateRecord,
    ManuscriptRevisionRecord,
    PaperCSLStyleRecord,
    PaperRecord,
    ProviderCacheRecord,
    ScholarlyWorkRecord,
)
from app.database.session import get_session_factory
from app.repositories.scholarly_works import ScholarlyWorkRepository
from app.schemas.paper import CitationNode, Paper, TextNode
from app.services.manuscript_revisions import (
    ManuscriptRevisionService,
    citation_identity,
    content_hash,
    structure_identity,
)
from app.services.paper_exports import CSLPaperExporter
from app.services.reference_evidence import choose_semantic_scholar_match
from app.services.source_search import SourceSupportVerifier
from app.services.tei_parser import parse_tei


FIXTURES = Path(__file__).parent / "fixtures"


class _UnusedPlanner:
    model = "architecture-integration"


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

        paper_id = str(uuid.uuid4())
        audit_id = str(uuid.uuid4())
        finding_id = str(uuid.uuid4())
        candidate_id = str(uuid.uuid4())
        provider_id = str(uuid.uuid4())
        cache_key = f"architecture-flow:{provider_id}"
        source_title = f"Verified Architecture Evidence {provider_id}"
        provider_payload = {
            "data": [
                {
                    "paperId": provider_id,
                    "title": source_title,
                    "abstract": "The controlled evidence supports the anchored architecture claim.",
                    "year": 2024,
                    "authors": [{"name": "Ada Evidence"}],
                    "externalIds": {"DOI": f"10.9999/{provider_id}"},
                    "url": f"https://www.semanticscholar.org/paper/{provider_id}",
                    "citationCount": 3,
                }
            ]
        }
        work_id = None
        session_factory = get_session_factory()
        try:
            works = ScholarlyWorkRepository(session_factory)
            await works.store_response(
                "semantic-scholar",
                cache_key,
                provider_payload,
                request={"query": source_title},
            )
            work_id = await works.find_by_provider_id("semantic-scholar", provider_id)
            self.assertIsNotNone(work_id)

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
                await session.flush()
                session.add(
                    CitationSourceCandidateRecord(
                        id=candidate_id,
                        finding_id=finding_id,
                        work_id=work_id,
                        rank=1,
                        score=0.99,
                        reason="Provider-backed integration evidence",
                        support_status="verified",
                        supports_claim=True,
                        support_confidence=0.99,
                        support_explanation="The provider abstract supports the exact claim.",
                        support_evidence="supports the anchored architecture claim",
                    )
                )
                await session.commit()

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
                await session.execute(
                    delete(ProviderCacheRecord).where(
                        ProviderCacheRecord.provider == "semantic-scholar",
                        ProviderCacheRecord.cache_key == cache_key,
                    )
                )
                if work_id:
                    await session.execute(
                        delete(ScholarlyWorkRecord).where(ScholarlyWorkRecord.id == work_id)
                    )
                await session.commit()


class VerificationFailureTest(unittest.IsolatedAsyncioTestCase):
    async def test_missing_verifier_key_is_unverifiable_and_not_actionable(self) -> None:
        decision = await SourceSupportVerifier(
            client=None,  # type: ignore[arg-type]
            api_key=None,
            model="unused",
        ).verify("A claim", "A provider source", "A provider abstract")
        self.assertTrue(decision.unverifiable)
        self.assertFalse(decision.supports_claim)


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
