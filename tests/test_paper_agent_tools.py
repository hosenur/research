import inspect
import unittest

from app.routers.papers import approve_manuscript_edit
from app.schemas.chat import PaperChatRequest
from app.services.paper_chat import PAPER_TOOLS, PaperChatService


class PaperAgentToolContractTest(unittest.TestCase):
    def test_tool_registry_is_unique_and_supports_broad_citation_requests(self) -> None:
        names = [tool["name"] for tool in PAPER_TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("find_citation_opportunities", names)
        self.assertIn("propose_citation_change", names)

    def test_citation_change_actions_are_explicit(self) -> None:
        tool = next(
            item for item in PAPER_TOOLS if item["name"] == "propose_citation_change"
        )
        actions = tool["parameters"]["properties"]["action"]["enum"]
        self.assertEqual(
            actions,
            ["add", "supplement", "replace", "remove", "update_metadata"],
        )

    def test_approval_route_declares_the_index_queue_dependency(self) -> None:
        self.assertIn("index_queue", inspect.signature(approve_manuscript_edit).parameters)

    def test_chat_request_preserves_forwarded_paper_id(self) -> None:
        request = PaperChatRequest.model_validate(
            {
                "threadId": "thread-1",
                "runId": "run-1",
                "messages": [],
                "forwardedProps": {"paperId": "paper-1"},
            }
        )
        self.assertEqual(request.forwarded_props.paper_id, "paper-1")


class PaperAgentIdentityTest(unittest.IsolatedAsyncioTestCase):
    async def test_route_paper_id_overrides_forwarded_context(self) -> None:
        request = PaperChatRequest.model_validate(
            {
                "threadId": "thread-1",
                "runId": "run-1",
                "messages": [],
                "forwardedProps": {"paperId": "stale-paper"},
            }
        )
        service = object.__new__(PaperChatService)
        resolved = await service._resolve_paper_id(request, "route-paper")
        self.assertEqual(resolved, "route-paper")


if __name__ == "__main__":
    unittest.main()
