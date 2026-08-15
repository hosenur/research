from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

from bullmq import Queue

from app.repositories.artifacts import PaperArtifactStore
from app.repositories.papers import PaperDocumentRepository
from app.repositories.pipeline import PaperPipelineRepository
from app.schemas.documents import PaperLifecycle
from app.services.papers import validate_pdf


class PaperIngestionService:
    """Persist one upload and enqueue parsing behind a small ingestion interface."""

    def __init__(
        self,
        documents: PaperDocumentRepository,
        pipeline: PaperPipelineRepository,
        artifacts: PaperArtifactStore,
        parse_queue: Queue,
        quick_read_queue: Queue,
    ) -> None:
        self._documents = documents
        self._pipeline = pipeline
        self._artifacts = artifacts
        self._parse_queue = parse_queue
        self._quick_read_queue = quick_read_queue

    async def ingest(self, filename: str, content: bytes) -> PaperLifecycle:
        pdf = validate_pdf(content)
        paper_id = str(uuid.uuid4())
        safe_filename = Path(filename).name[:512] or "paper.pdf"
        content_sha256 = hashlib.sha256(pdf).hexdigest()
        object_key = await asyncio.to_thread(
            self._artifacts.save_source,
            paper_id,
            safe_filename,
            pdf,
        )
        lifecycle = await self._documents.create_pending(
            paper_id=paper_id,
            filename=safe_filename,
            content_sha256=content_sha256,
            source_object_key=object_key,
        )
        await self._pipeline.initialize(paper_id)
        try:
            await self._quick_read_queue.add(
                "quick-read-paper",
                {"paperId": paper_id},
                {
                    "jobId": quick_read_job_id(paper_id),
                    "attempts": 3,
                    "backoff": {"type": "exponential", "delay": 1_000},
                    "removeOnComplete": False,
                    "removeOnFail": False,
                },
            )
            await self._parse_queue.add(
                "parse-paper",
                {"paperId": paper_id},
                {
                    "jobId": parse_job_id(paper_id),
                    "attempts": 4,
                    "backoff": {"type": "exponential", "delay": 2_000},
                    "removeOnComplete": False,
                    "removeOnFail": False,
                },
            )
        except Exception:
            await self._documents.fail_parse(
                paper_id,
                "The parse job could not be queued. Retry the upload.",
            )
            raise
        return lifecycle


def parse_job_id(paper_id: str) -> str:
    return f"paper-parse-{paper_id}"


def quick_read_job_id(paper_id: str) -> str:
    return f"paper-quick-read-{paper_id}"
