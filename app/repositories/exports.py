from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PaperCSLStyleRecord, PaperExportRecord
from app.schemas.documents import CitationStyleStatus, PaperExport


STYLE_CANDIDATES = {
    "numeric": [("ieee", "IEEE"), ("vancouver", "Vancouver")],
    "author-year": [("apa", "APA"), ("chicago-author-date", "Chicago author-date")],
    "author-page": [("modern-language-association", "MLA")],
}


class PaperExportRepository:
    """Own confirmed style state and durable export lifecycle projections."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def style_status(self, paper_id: str, detected_family: str | None = None) -> CitationStyleStatus:
        record = await self._session.get(PaperCSLStyleRecord, paper_id)
        family = record.detected_family if record else detected_family
        candidates = STYLE_CANDIDATES.get(family or "", [("apa", "APA"), ("ieee", "IEEE")])
        return CitationStyleStatus(
            paper_id=paper_id,
            style_id=record.style_id if record else None,
            confirmed=record.confirmed if record else False,
            detected_family=family,
            candidates=[{"id": style_id, "label": label} for style_id, label in candidates],
        )

    async def confirm_style(self, paper_id: str, style_id: str, detected_family: str | None) -> CitationStyleStatus:
        statement = insert(PaperCSLStyleRecord).values(
            paper_id=paper_id,
            style_id=style_id,
            confirmed=True,
            detected_family=detected_family,
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["paper_id"],
                set_={
                    "style_id": style_id,
                    "confirmed": True,
                    "detected_family": detected_family,
                    "updated_at": datetime.now(UTC),
                },
            )
        )
        await self._session.commit()
        return await self.style_status(paper_id, detected_family)

    async def create(self, paper_id: str, revision: int) -> PaperExportRecord:
        style = await self._session.get(PaperCSLStyleRecord, paper_id)
        if style is None or not style.confirmed:
            raise ValueError("Confirm a CSL citation style before exporting.")
        record = PaperExportRecord(
            id=str(uuid.uuid4()),
            paper_id=paper_id,
            manuscript_revision=revision,
            style_id=style.style_id,
            status="queued",
        )
        self._session.add(record)
        await self._session.commit()
        return record

    async def begin(self, export_id: str) -> PaperExportRecord:
        record = await self._locked(export_id)
        record.status = "running"
        record.error = None
        await self._session.commit()
        return record

    async def complete(
        self,
        export_id: str,
        *,
        latex_object_key: str,
        pdf_object_key: str,
        warnings: list[str],
        compiler_output: str,
    ) -> PaperExportRecord:
        record = await self._locked(export_id)
        record.status = "completed"
        record.latex_object_key = latex_object_key
        record.pdf_object_key = pdf_object_key
        record.warnings = warnings
        record.compiler_output = compiler_output[-8_000:]
        record.completed_at = datetime.now(UTC)
        await self._session.commit()
        return record

    async def fail(self, export_id: str, error: str) -> None:
        record = await self._locked(export_id)
        record.status = "failed"
        record.error = error[:4_000]
        record.completed_at = datetime.now(UTC)
        await self._session.commit()

    async def get(self, paper_id: str, export_id: str) -> PaperExportRecord:
        record = await self._session.scalar(
            select(PaperExportRecord).where(
                PaperExportRecord.id == export_id,
                PaperExportRecord.paper_id == paper_id,
            )
        )
        if record is None:
            raise LookupError("The export was not found.")
        return record

    async def _locked(self, export_id: str) -> PaperExportRecord:
        record = await self._session.scalar(
            select(PaperExportRecord)
            .where(PaperExportRecord.id == export_id)
            .with_for_update()
        )
        if record is None:
            raise LookupError("The export was not found.")
        return record


def project_export(record: PaperExportRecord) -> PaperExport:
    base = f"/papers/{record.paper_id}/exports/{record.id}/download"
    return PaperExport(
        id=record.id,
        paper_id=record.paper_id,
        revision=record.manuscript_revision,
        style_id=record.style_id,
        status=record.status,  # type: ignore[arg-type]
        warnings=record.warnings,
        error=record.error,
        latex_url=f"{base}/latex" if record.latex_object_key else None,
        pdf_url=f"{base}/pdf" if record.pdf_object_key else None,
    )
