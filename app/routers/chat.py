from typing import Annotated

from openai import AsyncOpenAI
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from fastapi.responses import StreamingResponse

from app.config import (
    OPENAI_TIMEOUT_SECONDS,
    openai_api_key,
    openai_base_url,
    openai_chat_model,
)
from app.schemas.chat import PaperChatRequest
from app.services.paper_chat import PaperChatService
from app.database.models import ChatMessageRecord
from app.database.session import get_session_factory

router = APIRouter(prefix="/chat", tags=["chat"])


async def get_paper_chat_service():
    client = AsyncOpenAI(
        api_key=openai_api_key(),
        base_url=openai_base_url(),
        timeout=OPENAI_TIMEOUT_SECONDS,
    )
    try:
        yield PaperChatService(client, api_key=openai_api_key(), model=openai_chat_model())
    finally:
        await client.close()


PaperAgent = Annotated[PaperChatService, Depends(get_paper_chat_service)]


@router.post("")
async def chat_with_paper(
    request: PaperChatRequest,
    agent: PaperAgent,
) -> StreamingResponse:
    if not agent.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The paper agent is not configured. Set OPENAI_API_KEY on the API service.",
        )
    return StreamingResponse(
        agent.stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{thread_id}")
async def get_chat_thread(
    thread_id: str,
    paper_id: str | None = Query(default=None),
) -> dict[str, object]:
    async with get_session_factory()() as session:
        statement = select(ChatMessageRecord).where(ChatMessageRecord.thread_id == thread_id).order_by(ChatMessageRecord.sequence)
        if paper_id:
            statement = statement.where(ChatMessageRecord.paper_id == paper_id)
        messages = list(await session.scalars(statement))
    return {"threadId": thread_id, "messages": [{"id": message.id, "role": message.role, "content": message.content} for message in messages]}
