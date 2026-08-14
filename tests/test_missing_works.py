import unittest
from unittest.mock import AsyncMock

from app.repositories.openalex import OpenAlexError
from app.schemas.paper import (
    CSLItem,
    CitationNode,
    OpenAlexWork,
    Paper,
    Paragraph,
    Reference,
    Section,
    TextNode,
)
from app.services.missing_works import MissingWorkFinder, already_cited, extract_claims


def paper() -> Paper:
    return Paper(
        title="BERT: Pre-training of Deep Bidirectional Transformers",
        abstract="We introduce a new language representation model called BERT.",
        sections=[
            Section(
                id="s1",
                title="Introduction",
                paragraphs=[
                    Paragraph(
                        id="p1",
                        nodes=[
                            TextNode(
                                text=(
                                    "We propose a new language representation model called BERT. "
                                    "Unlike previous work that used unidirectional language models "
                                    "Peters et al. (2018), our model is deeply bidirectional."
                                )
                            ),
                            CitationNode(raw_text="Peters et al. (2018)", reference_ids=["b34"]),
                        ],
                    )
                ],
            ),
            Section(
                id="s2",
                title="Acknowledgements",
                paragraphs=[Paragraph(id="p2", nodes=[TextNode(text="We thank our colleagues.")])],
            ),
        ],
        references=[
            Reference(
                id="b34",
                raw_text="Peters et al. Deep contextualized word representations.",
                status="parsed",
                csl=CSLItem(id="b34", type="article", title="Deep contextualized word representations"),
                openalex=OpenAlexWork(
                    id="https://openalex.org/W1",
                    title="Deep contextualized word representations",
                    match_method="title",
                    confidence="high",
                ),
            )
        ],
    )


ELMO = {
    "id": "https://openalex.org/W1",
    "display_name": "Deep contextualized word representations",
    "doi": "https://doi.org/10.18653/v1/n18-1202",
}
ULMFiT = {
    "id": "https://openalex.org/W2",
    "display_name": "Universal Language Model Fine-tuning for Text Classification",
    "publication_year": 2018,
    "cited_by_count": 4000,
    "primary_location": {"landing_page_url": "https://openalex.org/W2"},
    "abstract_inverted_index": {"Inductive": [0], "transfer": [1], "learning": [2]},
}


class ExtractClaimsTest(unittest.TestCase):
    def test_prefers_introduction_and_skips_acks(self) -> None:
        claims = extract_claims(paper())
        self.assertTrue(claims)
        self.assertEqual(claims[0].section_title, "Introduction")
        self.assertTrue(any("BERT" in claim.text for claim in claims))
        self.assertFalse(any(claim.section_title == "Acknowledgements" for claim in claims))


class DedupeTest(unittest.TestCase):
    def test_already_cited_by_openalex_id_and_title(self) -> None:
        self.assertTrue(already_cited(ELMO, set(), set(), {"https://openalex.org/W1"}, set()))
        self.assertTrue(
            already_cited(
                ELMO,
                set(),
                set(),
                set(),
                {"deep contextualized word representations"},
            )
        )
        self.assertFalse(already_cited(ULMFiT, set(), set(), {"https://openalex.org/W1"}, set()))


class MissingWorkFinderTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_only_uncited_openalex_works(self) -> None:
        repository = AsyncMock()
        repository.search_related = AsyncMock(return_value=({"results": [ELMO, ULMFiT]}, "semantic"))
        report = await MissingWorkFinder(repository).find(paper())

        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.findings[0].work.id, "https://openalex.org/W2")
        self.assertEqual(report.findings[0].work.match_method, "search")
        self.assertIn("Universal Language Model", report.findings[0].work.title or "")
        self.assertTrue(report.queries)

    async def test_empty_and_error_are_surfaced(self) -> None:
        repository = AsyncMock()
        repository.search_related = AsyncMock(return_value=(None, "search"))
        report = await MissingWorkFinder(repository).find(paper())
        self.assertEqual(report.findings, [])
        self.assertTrue(any(query.status == "empty" for query in report.queries))

        repository.search_related = AsyncMock(side_effect=OpenAlexError("OpenAlex is unavailable."))
        report = await MissingWorkFinder(repository).find(paper())
        self.assertTrue(any(query.status == "error" for query in report.queries))
        self.assertTrue(any("failed" in warning for warning in report.warnings))


if __name__ == "__main__":
    unittest.main()
