import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from app.repositories.openalex import OpenAlexError
from app.schemas.paper import CSLDate, CSLItem, CSLName, Paper, Reference
from app.services.openalex import (
    OpenAlexEnricher,
    choose_title_match,
    normalize_arxiv,
    normalize_doi,
    reconstruct_abstract,
    title_similarity,
    work_from_payload,
)


def paper_with(*references: Reference) -> Paper:
    return Paper(title="Tiny Paper", sections=[], references=list(references))


def reference(
    reference_id: str,
    *,
    title: str | None = None,
    doi: str | None = None,
    arxiv: str | None = None,
    year: int | None = None,
    status: str = "parsed",
) -> Reference:
    identifiers: dict[str, str] = {}
    if doi:
        identifiers["doi"] = doi
    if arxiv:
        identifiers["arxiv"] = arxiv
    issued = CSLDate(date_parts=[[year]]) if year else None
    csl = None
    if title or doi or year:
        csl = CSLItem(
            id=reference_id,
            type="article",
            title=title,
            author=[CSLName(family="Vaswani")] if title else [],
            issued=issued,
            doi=doi,
            archive="arXiv" if arxiv else None,
            archive_location=arxiv,
        )
    return Reference(
        id=reference_id,
        raw_text=title or "",
        csl=csl,
        status=status,  # type: ignore[arg-type]
        raw_fields={"title": title, "identifiers": identifiers} if identifiers or title else {},
    )


ATTENTION_WORK = {
    "id": "https://openalex.org/W2964141474",
    "doi": "https://doi.org/10.48550/arxiv.1706.03762",
    "display_name": "Attention is All you Need",
    "publication_year": 2017,
    "ids": {"openalex": "https://openalex.org/W2964141474", "doi": "https://doi.org/10.48550/arxiv.1706.03762"},
    "abstract_inverted_index": {
        "The": [0],
        "dominant": [1],
        "sequence": [2],
        "transduction": [3],
        "models": [4],
    },
    "primary_location": {"landing_page_url": "https://arxiv.org/abs/1706.03762"},
    "cited_by_count": 120000,
}


class OpenAlexHelpersTest(unittest.TestCase):
    def test_reconstruct_abstract(self) -> None:
        self.assertEqual(
            reconstruct_abstract({"models": [2], "The": [0], "dominant": [1]}),
            "The dominant models",
        )
        self.assertIsNone(reconstruct_abstract(None))
        self.assertIsNone(reconstruct_abstract({}))

    def test_normalize_identifiers(self) -> None:
        self.assertEqual(normalize_doi("https://doi.org/10.1145/123"), "10.1145/123")
        self.assertEqual(normalize_doi("doi:10.1145/123."), "10.1145/123")
        self.assertEqual(normalize_arxiv("arXiv:1706.03762v5[cs.CL]"), "1706.03762")

    def test_title_similarity_and_disambiguation(self) -> None:
        self.assertGreater(
            title_similarity("Attention Is All You Need", "Attention is All you Need"),
            0.9,
        )
        chosen = choose_title_match(
            [ATTENTION_WORK],
            "Attention Is All You Need",
            2017,
        )
        self.assertIsNotNone(chosen)
        assert chosen is not None
        self.assertEqual(chosen[1], "high")

        ambiguous = choose_title_match(
            [
                {**ATTENTION_WORK, "display_name": "Attention is All you Need"},
                {**ATTENTION_WORK, "id": "https://openalex.org/W2", "display_name": "Attention is All you Need"},
            ],
            "Attention Is All You Need",
            2017,
        )
        self.assertIsNone(ambiguous)

    def test_work_from_payload(self) -> None:
        work = work_from_payload(ATTENTION_WORK, "doi", "high")
        self.assertEqual(work.id, "https://openalex.org/W2964141474")
        self.assertEqual(work.doi, "10.48550/arxiv.1706.03762")
        self.assertEqual(work.abstract, "The dominant sequence transduction models")
        self.assertEqual(work.match_method, "doi")


class OpenAlexEnricherTest(unittest.IsolatedAsyncioTestCase):
    async def test_matches_by_doi(self) -> None:
        repository = AsyncMock()
        repository.get_by_doi = AsyncMock(return_value=ATTENTION_WORK)
        repository.get_by_arxiv = AsyncMock(return_value=None)
        repository.search_by_title = AsyncMock(return_value=None)
        enricher = OpenAlexEnricher(repository)

        paper = await enricher.enrich_paper(
            paper_with(reference("b0", title="Attention Is All You Need", doi="10.48550/arXiv.1706.03762", year=2017))
        )

        self.assertEqual(paper.references[0].openalex_status, "matched")
        self.assertEqual(paper.references[0].openalex.match_method, "doi")
        self.assertIn("The dominant", paper.references[0].openalex.abstract or "")
        repository.get_by_doi.assert_awaited_once()
        repository.search_by_title.assert_not_awaited()
        self.assertTrue(any("OpenAlex matched 1/1" in warning for warning in paper.warnings))

    async def test_falls_back_to_arxiv_then_title(self) -> None:
        repository = AsyncMock()
        repository.get_by_doi = AsyncMock(return_value=None)
        repository.get_by_arxiv = AsyncMock(return_value=ATTENTION_WORK)
        repository.search_by_title = AsyncMock(return_value=None)
        enricher = OpenAlexEnricher(repository)

        paper = await enricher.enrich_paper(
            paper_with(reference("b0", title="Attention Is All You Need", arxiv="1706.03762", year=2017))
        )

        self.assertEqual(paper.references[0].openalex_status, "matched")
        self.assertEqual(paper.references[0].openalex.match_method, "arxiv")

        repository.get_by_arxiv = AsyncMock(return_value=None)
        repository.search_by_title = AsyncMock(return_value={"results": [ATTENTION_WORK]})
        paper = await enricher.enrich_paper(
            paper_with(reference("b1", title="Attention Is All You Need", year=2017))
        )
        repository.search_by_title.assert_awaited()
        self.assertEqual(paper.references[0].openalex_status, "matched")
        self.assertEqual(paper.references[0].openalex.match_method, "title")

    async def test_unmatched_and_skipped_and_error(self) -> None:
        repository = AsyncMock()
        repository.get_by_doi = AsyncMock(return_value=None)
        repository.get_by_arxiv = AsyncMock(return_value=None)
        repository.search_by_title = AsyncMock(return_value={"results": []})
        enricher = OpenAlexEnricher(repository)

        unmatched = reference("b0", title="A paper OpenAlex has never seen", year=1999)
        skipped = Reference(id="b1", raw_text="", csl=None, status="failed")
        paper = await enricher.enrich_paper(paper_with(unmatched, skipped))

        self.assertEqual(paper.references[0].openalex_status, "unmatched")
        self.assertEqual(paper.references[1].openalex_status, "skipped")
        self.assertIsNone(paper.references[0].openalex)

        repository.search_by_title = AsyncMock(side_effect=OpenAlexError("OpenAlex is unavailable."))
        paper = await enricher.enrich_paper(
            paper_with(reference("b2", title="Anything", year=2017))
        )
        self.assertEqual(paper.references[0].openalex_status, "error")
        self.assertEqual(paper.references[0].openalex_error, "OpenAlex is unavailable.")
        self.assertTrue(any("1 lookup errors" in warning for warning in paper.warnings))


class OpenAlexRepositoryRetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_retries_rate_limits_then_succeeds(self) -> None:
        from app.repositories.openalex import OpenAlexRepository

        limited = httpx.Response(429, headers={"Retry-After": "0"}, request=httpx.Request("GET", "https://api.openalex.org/works"))
        ok = httpx.Response(
            200,
            json={"results": [ATTENTION_WORK]},
            request=httpx.Request("GET", "https://api.openalex.org/works"),
        )
        client = AsyncMock()
        client.get = AsyncMock(side_effect=[limited, ok])
        repository = OpenAlexRepository(client)

        work = await repository.get_by_doi("10.1038/nature14539")
        self.assertEqual(work["id"], ATTENTION_WORK["id"])
        self.assertEqual(client.get.await_count, 2)

    async def test_durable_cache_port_skips_repeat_requests(self) -> None:
        from app.repositories.openalex import OpenAlexRepository

        ok = httpx.Response(
            200,
            json={"results": [ATTENTION_WORK]},
            request=httpx.Request("GET", "https://api.openalex.org/works"),
        )
        client = AsyncMock()
        client.get = AsyncMock(return_value=ok)
        values = {}
        cache = SimpleNamespace(
            get_cached=AsyncMock(
                side_effect=lambda _provider, key: SimpleNamespace(
                    found=key in values,
                    value=values.get(key),
                )
            ),
            store_response=AsyncMock(
                side_effect=lambda _provider, key, response, **_kwargs: (
                    values.__setitem__(key, response) or 1
                )
            ),
        )
        repository = OpenAlexRepository(client, cache=cache)
        first = await repository.get_by_doi("10.1038/nature14539")
        second = await repository.get_by_doi("10.1038/nature14539")

        self.assertEqual(first["id"], ATTENTION_WORK["id"])
        self.assertEqual(second["id"], ATTENTION_WORK["id"])
        self.assertEqual(client.get.await_count, 1)
        cache.store_response.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
