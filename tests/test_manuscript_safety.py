import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.approved_edit_refresh import ApprovedEditRefresher
from app.services.citation_actions import rank_opportunities
from app.services.manuscript_revisions import is_extractive_tightening


class ExtractiveEditingTest(unittest.TestCase):
    def test_deletion_only_tightening_is_allowed(self) -> None:
        self.assertTrue(
            is_extractive_tightening(
                "The model is substantially faster in our controlled evaluation.",
                "The model is faster in our evaluation.",
            )
        )

    def test_shorter_novel_claim_is_rejected(self) -> None:
        self.assertFalse(
            is_extractive_tightening(
                "The model is discussed in our evaluation.",
                "The model causes better outcomes.",
            )
        )
        self.assertFalse(
            is_extractive_tightening(
                "The treatment improves outcomes.",
                "The treatment does not improve outcomes.",
            )
        )


class CitationOpportunityRankingTest(unittest.TestCase):
    def test_section_and_topic_resolve_to_exact_findings(self) -> None:
        introduction = SimpleNamespace(
            id="f1",
            section_id="s1",
            section_title="Introduction",
            claim_text="Transformers improve language modeling.",
            confidence=0.9,
            revision=1,
        )
        methods = SimpleNamespace(
            id="f2",
            section_id="s2",
            section_title="Methodology",
            claim_text="The optimization method converges faster.",
            confidence=0.8,
            revision=2,
        )
        ranked = rank_opportunities(
            [introduction, methods],
            section="Methodology",
            topic="optimization",
        )
        self.assertEqual([item.id for item in ranked], ["f2"])


class _FakeQueue:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str]] = []

    async def add_once(self, name, data, *, job_id, attempts) -> None:
        self.calls.append((name, job_id))
        if self.error:
            raise self.error


class ApprovedEditRefreshTest(unittest.IsolatedAsyncioTestCase):
    async def test_queue_failure_does_not_change_approval_result(self) -> None:
        paper = SimpleNamespace(
            sections=[
                SimpleNamespace(
                    id="s1",
                    paragraphs=[SimpleNamespace(id="p1")],
                )
            ]
        )
        documents = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(paper=paper))
        )
        audits = SimpleNamespace(
            create_or_get=AsyncMock(return_value=SimpleNamespace(id="audit-1"))
        )
        pipeline = SimpleNamespace(queued=AsyncMock(), fail=AsyncMock())
        index_queue = _FakeQueue(RuntimeError("queue unavailable"))
        missing_queue = _FakeQueue()
        existing_queue = _FakeQueue()
        approved = SimpleNamespace(
            approved_revision=2,
            operations=[
                SimpleNamespace(
                    approved=True,
                    operation_type="replace_text",
                    node_ids=["p1"],
                )
            ],
        )
        warnings = await ApprovedEditRefresher(
            documents=documents,
            audits=audits,
            pipeline=pipeline,
            index_jobs=index_queue,
            missing_review_jobs=missing_queue,
            existing_review_jobs=existing_queue,
            audit_model="test-model",
        ).schedule("paper-1", approved)

        self.assertTrue(any("reindexing" in warning for warning in warnings))
        pipeline.fail.assert_awaited_once()
        self.assertEqual(len(missing_queue.calls), 1)
        self.assertEqual(len(existing_queue.calls), 1)


if __name__ == "__main__":
    unittest.main()
