from __future__ import annotations

import asyncio

from bullmq import Job, Worker
from openai import AsyncOpenAI

from app.config import (
    OPENAI_TIMEOUT_SECONDS,
    PAPER_QUICK_READ_QUEUE_NAME,
    bullmq_options,
    openai_api_key,
    openai_base_url,
)
from app.database.session import get_session_factory
from app.repositories.artifacts import create_paper_artifact_store
from app.repositories.papers import PaperDocumentRepository
from app.repositories.pipeline import PaperPipelineRepository
from app.services.paper_index import PaperIndexer
from app.services.quick_read import QuickTextExtractor


async def run() -> None:
    artifacts = create_paper_artifact_store()
    extractor = QuickTextExtractor()
    async with AsyncOpenAI(
        api_key=openai_api_key(),
        base_url=openai_base_url(),
        timeout=OPENAI_TIMEOUT_SECONDS,
    ) as client:
        indexer = PaperIndexer(client, api_key=openai_api_key())

        async def process(job: Job, _token: str) -> dict[str, int | str]:
            paper_id = str(job.data.get("paperId") or "")
            if not paper_id:
                raise ValueError("The paper-quick-read job is missing paperId.")
            active_stage = "quick-extraction"
            try:
                async with get_session_factory()() as session:
                    documents = PaperDocumentRepository(session)
                    filename, object_key = await documents.source(paper_id)
                    pipeline = PaperPipelineRepository(session)
                    await pipeline.begin(paper_id, active_stage)
                await job.updateProgress({"stage": "extracting-text"})
                content = await asyncio.to_thread(artifacts.read_source, object_key)
                document = await extractor.extract(content)
                async with get_session_factory()() as session:
                    pipeline = PaperPipelineRepository(session)
                    await pipeline.complete(
                        paper_id,
                        active_stage,
                        progress={
                            "characters": document.character_count,
                            "chunks": len(document.chunks),
                            "filename": filename,
                        },
                    )
                    active_stage = "quick-index"
                    await pipeline.begin(
                        paper_id,
                        active_stage,
                        progress={"chunks": len(document.chunks)},
                    )
                    await job.updateProgress({"stage": "embedding", "chunks": len(document.chunks)})
                    count = await indexer.index_quick_text(session, paper_id, document.chunks)
                async with get_session_factory()() as session:
                    await PaperPipelineRepository(session).complete(
                        paper_id,
                        active_stage,
                        progress={"chunks": count, "indexKind": "provisional"},
                    )
                return {"paperId": paper_id, "chunks": count, "indexKind": "provisional"}
            except Exception as exc:
                async with get_session_factory()() as session:
                    await PaperPipelineRepository(session).fail(paper_id, active_stage, str(exc))
                raise

        worker = Worker(
            PAPER_QUICK_READ_QUEUE_NAME,
            process,
            {**bullmq_options(), "autorun": False, "concurrency": 2},
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(run())
