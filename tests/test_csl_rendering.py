import unittest
import zipfile
from io import BytesIO

from app.schemas.paper import (
    CSLDate,
    CSLItem,
    CSLName,
    CitationItem,
    CitationNode,
    Paper,
    Paragraph,
    Reference,
    Section,
    TextNode,
)
from app.services.csl_rendering import PandocCSLRenderer
from app.services.paper_exports import CSLPaperExporter


def sample_paper(*, form: str = "parenthetical", locator: str | None = None) -> Paper:
    citation = CitationNode(
        id="cite-1",
        raw_text="legacy marker",
        items=[
            CitationItem(
                source_id="ref-1",
                locator=locator,
                label="page" if locator else None,
                resolution_method="manual",
                confidence="high",
            )
        ],
        form=form,
    )
    return Paper(
        title="A Citation Test",
        abstract="A compact abstract.",
        authors=[CSLName(given="Ada", family="Researcher")],
        citation_style="author-year",
        sections=[
            Section(
                id="s1",
                title="Introduction",
                paragraphs=[
                    Paragraph(
                        id="p1",
                        nodes=[TextNode(text="Prior work shows this "), citation],
                    )
                ],
            )
        ],
        references=[
            Reference(
                id="ref-1",
                raw_text="Alice Smith. Evidence Paper. 2020.",
                status="parsed",
                csl=CSLItem(
                    id="ref-1",
                    type="article-journal",
                    title="Evidence Paper",
                    author=[CSLName(given="Alice", family="Smith")],
                    issued=CSLDate(date_parts=[[2020]]),
                ),
            ),
            Reference(
                id="ref-2",
                raw_text="Grace Lee. Uncited Background. 2019.",
                status="parsed",
                csl=CSLItem(
                    id="ref-2",
                    type="article-journal",
                    title="Uncited Background",
                    author=[CSLName(given="Grace", family="Lee")],
                    issued=CSLDate(date_parts=[[2019]]),
                ),
            ),
        ],
    )


class PandocCSLRendererTest(unittest.TestCase):
    def setUp(self) -> None:
        self.renderer = PandocCSLRenderer()

    def test_apa_and_ieee_markers_come_from_csl(self) -> None:
        paper = sample_paper()
        citation = next(
            node
            for node in paper.sections[0].paragraphs[0].nodes
            if isinstance(node, CitationNode)
        )
        self.assertEqual(self.renderer.render_marker(paper, citation, "apa"), "(Smith, 2020)")
        self.assertEqual(self.renderer.render_marker(paper, citation, "ieee"), "[1]")

    def test_locator_and_narrative_form_are_preserved(self) -> None:
        located = sample_paper(locator="7")
        located_citation = next(
            node
            for node in located.sections[0].paragraphs[0].nodes
            if isinstance(node, CitationNode)
        )
        self.assertIn("7", self.renderer.render_marker(located, located_citation, "apa"))

        narrative = sample_paper(form="narrative")
        narrative_citation = next(
            node
            for node in narrative.sections[0].paragraphs[0].nodes
            if isinstance(node, CitationNode)
        )
        marker = self.renderer.render_marker(narrative, narrative_citation, "apa")
        self.assertTrue(marker.startswith("Smith"), marker)
        self.assertIn("2020", marker)

    def test_document_uses_csl_bibliography_layout_not_enumerate(self) -> None:
        rendered = self.renderer.render_document(sample_paper(), "apa")
        self.assertIn("Smith", rendered.latex)
        self.assertIn("Evidence Paper", rendered.latex)
        self.assertIn("Uncited Background", rendered.latex)
        self.assertNotIn("\\begin{enumerate}", rendered.latex)
        self.assertIn(b'"id": "ref-1"', rendered.references_json)

    def test_revision_export_compiles_pdf_and_editable_bundle(self) -> None:
        generated = CSLPaperExporter(self.renderer).generate(sample_paper(), "apa")
        self.assertTrue(generated.pdf.startswith(b"%PDF-"))
        with zipfile.ZipFile(BytesIO(generated.latex_bundle)) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"main.tex", "references.json", "styles/apa.csl", "README.txt"},
            )
            self.assertNotIn(b"\\begin{enumerate}", archive.read("main.tex"))


if __name__ == "__main__":
    unittest.main()
