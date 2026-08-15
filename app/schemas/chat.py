from typing import Any, Literal

from pydantic import Field

from app.schemas.paper import ApiModel, Paper


class ChatWireMessage(ApiModel):
    """The subset of an AG-UI message needed by the model bridge."""

    id: str | None = None
    role: Literal["system", "user", "assistant", "tool", "reasoning"]
    content: Any = ""
    parts: list[dict[str, Any]] = Field(default_factory=list)


class AgentSelectionContext(ApiModel):
    kind: Literal["missing", "existing", "reference"]
    label: str | None = None
    finding_id: str | None = None
    candidate_id: str | None = None
    reference_id: str | None = None
    citation_id: str | None = None
    paragraph_id: str | None = None
    text: str | None = None
    classification: Literal[
        "supported", "weak", "contradicted", "unverifiable"
    ] | None = None


class ChatForwardedProps(ApiModel):
    paper: Paper | None = None
    paper_id: str | None = None
    selection_context: AgentSelectionContext | None = None


class PaperChatRequest(ApiModel):
    """AG-UI RunAgentInput sent by TanStack AI's SSE connection."""

    thread_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    messages: list[ChatWireMessage] = Field(default_factory=list)
    forwarded_props: ChatForwardedProps
    paper_id: str | None = None
