import unittest
from pathlib import Path

from app.schemas.paper import CitationNode
from app.services.tei_parser import parse_tei

FIXTURES = Path(__file__).parent / "fixtures"


def load_paper(stem: str):
    return parse_tei((FIXTURES / f"{stem}.tei.xml").read_bytes())


def citations(paper):
    return [
        node
        for section in paper.sections
        for paragraph in section.paragraphs
        for node in paragraph.nodes
        if isinstance(node, CitationNode)
    ]


class SamplePaperSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        missing = [
            name
            for name in (
                "attention-is-all-you-need",
                "bert",
                "language-models-are-few-shot-learners",
            )
            if not (FIXTURES / f"{name}.tei.xml").exists()
        ]
        if missing:
            raise unittest.SkipTest(f"Missing TEI fixtures: {', '.join(missing)}")
        cls.attention = load_paper("attention-is-all-you-need")
        cls.bert = load_paper("bert")
        cls.gpt3 = load_paper("language-models-are-few-shot-learners")

    def test_attention_structure_and_numeric_cites(self) -> None:
        paper = self.attention
        self.assertEqual(paper.title, "Attention Is All You Need")
        self.assertTrue(paper.abstract)
        titles = {section.title for section in paper.sections}
        self.assertTrue({"Introduction", "Background", "Model Architecture", "Conclusion"} <= titles)
        self.assertNotIn("Input-Input Layer5", titles)
        self.assertGreaterEqual(len(paper.references), 38)
        self.assertLessEqual(len(paper.sections), 22)
        self.assertEqual(paper.citation_style, "numeric")
        self.assertEqual(paper.identifiers.get("arxiv"), "1706.03762")
        self.assertEqual(paper.year, 2017)

        by_id = {reference.id: reference for reference in paper.references}
        self.assertEqual(by_id["b0"].status, "parsed")
        self.assertIn("Layer normalization", by_id["b0"].csl.title)
        self.assertEqual(by_id["b29"].status, "parsed")
        self.assertTrue(by_id["b29"].csl.author)

        first_cite = next(
            node for node in citations(paper) if node.raw_text.strip() in {"[13]", "[13]."}
        )
        self.assertEqual(first_cite.reference_ids, ["b12"])
        self.assertFalse(paper.unresolved_reference_ids)
        parsed = sum(1 for reference in paper.references if reference.status == "parsed")
        self.assertGreaterEqual(parsed, 39)

    def test_bert_author_year_resolution(self) -> None:
        paper = self.bert
        self.assertTrue(paper.title.startswith("BERT"))
        self.assertTrue(paper.abstract)
        self.assertEqual(paper.citation_style, "author-year")
        self.assertNotIn(
            "Input-Input Layer5",
            {section.title for section in paper.sections},
        )
        self.assertIn("QNLI", {section.title for section in paper.sections})

        cite_nodes = citations(paper)
        self.assertFalse(
            any("CLS" in node.raw_text or "SEP" in node.raw_text for node in cite_nodes)
        )

        peters = [
            node
            for node in cite_nodes
            if "Peters" in node.raw_text and "2018a" in node.raw_text
        ]
        self.assertTrue(peters)
        self.assertTrue(all("b34" in node.reference_ids for node in peters))
        self.assertTrue(all("Peters" not in " ".join(node.unresolved_fragments) for node in peters))

        wang = [
            node
            for node in cite_nodes
            if "Wang" in node.raw_text and "2018a" in node.raw_text
        ]
        self.assertTrue(wang)
        self.assertTrue(all("b46" in node.reference_ids for node in wang))

        mnih = [
            node
            for node in cite_nodes
            if "Mnih" in node.raw_text
        ]
        self.assertTrue(mnih)
        self.assertTrue(all(node.unresolved_fragments for node in mnih))

        leftover = [
            fragment
            for node in cite_nodes
            for fragment in node.unresolved_fragments
        ]
        self.assertTrue(leftover)
        self.assertIn("Mnih and Hinton, 2009", leftover)
        self.assertIn("Clark and Gardner, 2018", leftover)

        by_id = {reference.id: reference for reference in paper.references}
        self.assertEqual(by_id["b9"].status, "parsed")
        self.assertIn("Quora", by_id["b9"].csl.title or "")
        self.assertEqual(by_id["b34"].status, "parsed")
        self.assertTrue(
            (by_id["b34"].csl.title or "").startswith("Deep contextualized")
        )
        self.assertEqual(by_id["b34"].csl.issued.date_parts[0][0], 2018)

    def test_gpt3_filters_false_bibliography(self) -> None:
        paper = self.gpt3
        self.assertEqual(paper.title, "Language Models are Few-Shot Learners")
        self.assertTrue(paper.abstract)
        titles = {section.title for section in paper.sections}
        self.assertTrue({"Introduction", "Conclusion"} <= titles)
        self.assertNotIn("Context → Article:", titles)
        self.assertNotIn("Setting CL A1 A2 RI RW", titles)
        self.assertEqual(paper.citation_style, "harvard-key")

        raw = [reference.raw_text for reference in paper.references]
        self.assertFalse(any(text.startswith("Poor English") for text in raw))
        self.assertFalse(any("designed and led the research" in text for text in raw))
        self.assertLessEqual(len(paper.references), 140)
        self.assertGreaterEqual(len(paper.references), 120)

        titles_joined = " ".join(
            (reference.csl.title or "") for reference in paper.references if reference.csl
        )
        self.assertIn("Learning to learn by gradient descent", titles_joined)

        mccd = [
            node
            for node in citations(paper)
            if "MCCD13" in node.raw_text
        ]
        self.assertTrue(mccd)
        self.assertTrue(all(node.reference_ids for node in mccd))

        parsed = sum(1 for reference in paper.references if reference.status == "parsed")
        self.assertGreaterEqual(parsed / len(paper.references), 0.85)


if __name__ == "__main__":
    unittest.main()
