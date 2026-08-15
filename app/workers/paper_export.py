from __future__ import annotations

import asyncio

from bullmq import Job, Worker
from sqlalchemy import select

from app.config import PAPER_EXPORT_QUEUE_NAME, bullmq_options
from app.database.models import ManuscriptRevisionRecord
from app.database.session import get_session_factory
from app.repositories.artifacts import create_paper_artifact_store
from app.repositories.exports import PaperExportRepository
from app.repositories.pipeline import PaperPipelineRepository
from app.schemas.paper import Paper
from app.services.paper_exports import CSLPaperExporter


async def run() -> None:
    artifacts = create_paper_artifact_store()
    generator = CSLPaperExporter()

    async def process(job: Job, _token: str) -> dict[str, int | str]:
        export_id = str(job.data.get("exportId") or "")
        paper_id = str(job.data.get("paperId") or "")
        if not export_id or not paper_id:
            raise ValueError("The paper-export job is missing exportId or paperId.")
        try:
            async with get_session_factory()() as session:
                exports = PaperExportRepository(session)
                record = await exports.begin(export_id)
                await PaperPipelineRepository(session).begin(
                    paper_id, "export", revision=record.manuscript_revision
                )
                revision = await session.scalar(
                    select(ManuscriptRevisionRecord).where(
                        ManuscriptRevisionRecord.paper_id == paper_id,
                        ManuscriptRevisionRecord.revision == record.manuscript_revision,
                    )
                )
                if revision is None:
                    raise LookupError("The manuscript revision for this export was not found.")
                paper = Paper.model_validate(revision.paper_json)
                style_id = record.style_id
            generated = await asyncio.to_thread(generator.generate, paper, style_id)
            latex_key = await asyncio.to_thread(
                artifacts.save_export,
                paper_id,
                export_id,
                f"paper-r{record.manuscript_revision}.zip",
                generated.latex_bundle,
                "application/zip",
            )
            pdf_key = await asyncio.to_thread(
                artifacts.save_export,
                paper_id,
                export_id,
                f"paper-r{record.manuscript_revision}.pdf",
                generated.pdf,
                "application/pdf",
            )
            async with get_session_factory()() as session:
                await PaperExportRepository(session).complete(
                    export_id,
                    latex_object_key=latex_key,
                    pdf_object_key=pdf_key,
                    warnings=generated.warnings,
                    compiler_output=generated.compiler_output,
                )
                await PaperPipelineRepository(session).complete(
                    paper_id,
                    "export",
                    revision=record.manuscript_revision,
                    progress={"exportId": export_id, "formats": ["latex", "pdf"]},
                )
            return {"exportId": export_id, "revision": record.manuscript_revision}
        except Exception as exc:
            async with get_session_factory()() as session:
                try:
                    await PaperExportRepository(session).fail(export_id, str(exc))
                    await PaperPipelineRepository(session).fail(
                        paper_id, "export", str(exc)
                    )
                except LookupError:
                    pass
            raise

    worker = Worker(
        PAPER_EXPORT_QUEUE_NAME,
        process,
        {**bullmq_options(), "autorun": False, "concurrency": 1},
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run())
