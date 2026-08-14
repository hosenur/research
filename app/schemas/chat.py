from typing import Any, Literal

from pydantic import Field

from app.schemas.paper import ApiModel, Paper


class ChatWireMessage(ApiModel):
    """The subset of an AG-UI message needed by the model bridge."""

    id: str | None = None
    role: Literal["system", "user", "assistant", "tool", "reasoning"]
    content: Any = ""
    parts: list[dict[str, Any]] = Field(default_factory=list)


class ChatForwardedProps(ApiModel):
    paper: Paper


class PaperChatRequest(ApiModel):
    """AG-UI RunAgentInput sent by TanStack AI's SSE connection."""

    thread_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    messages: list[ChatWireMessage] = Field(default_factory=list)
    forwarded_props: ChatForwardedProps
    paper_id: str | None = None
