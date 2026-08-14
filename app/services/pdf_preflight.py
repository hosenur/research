from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.config import (
    OCR_TIMEOUT_SECONDS,
    PDF_MIN_SELECTABLE_CHARACTERS,
    PDF_PREFLIGHT_SAMPLE_PAGES,
)
from app.exceptions import InvalidDocumentError, OcrFailedError
from app.schemas.paper import PdfPreflightReport


class PdfPreflightService:
    """Inspect PDFs with Poppler and apply OCR only when extraction needs it."""

    async def inspect(self, pdf: bytes) -> PdfPreflightReport:
        return await asyncio.to_thread(self._inspect_sync, pdf)

    async def apply_ocr(self, pdf: bytes) -> bytes:
        return await asyncio.to_thread(self._apply_ocr_sync, pdf)

    def _inspect_sync(self, pdf: bytes) -> PdfPreflightReport:
        warnings: list[str] = []
        if shutil.which("pdfinfo") is None or shutil.which("pdftotext") is None:
            warnings.append("Poppler is unavailable; PDF text preflight was skipped.")
            return PdfPreflightReport(warnings=warnings)

        with tempfile.TemporaryDirectory(prefix="paper-preflight-") as directory:
            source = Path(directory) / "input.pdf"
            source.write_bytes(pdf)
            info = self._run(["pdfinfo", str(source)], timeout=30)
            if info.returncode != 0:
                raise InvalidDocumentError(
                    "The PDF could not be inspected and may be damaged or password protected."
                )

            page_match = re.search(r"^Pages:\s+(\d+)", info.stdout, re.MULTILINE)
            encrypted_match = re.search(
                r"^Encrypted:\s+(yes|no)", info.stdout, re.MULTILINE | re.IGNORECASE
            )
            page_count = int(page_match.group(1)) if page_match else None
            encrypted = bool(encrypted_match and encrypted_match.group(1).lower() == "yes")
            if encrypted:
                return PdfPreflightReport(
                    page_count=page_count,
                    encrypted=True,
                    warnings=["Password-protected PDFs cannot be processed."],
                )

            sampled_pages = min(page_count or PDF_PREFLIGHT_SAMPLE_PAGES, PDF_PREFLIGHT_SAMPLE_PAGES)
            text = self._run(
                [
                    "pdftotext",
                    "-f",
                    "1",
                    "-l",
                    str(max(sampled_pages, 1)),
                    str(source),
                    "-",
                ],
                timeout=45,
            )
            selectable_characters = len(re.sub(r"\s+", "", text.stdout)) if text.returncode == 0 else 0
            ocr_recommended = selectable_characters < PDF_MIN_SELECTABLE_CHARACTERS
            if ocr_recommended:
                warnings.append(
                    "The sampled pages contain little selectable text; OCR is recommended."
                )
            return PdfPreflightReport(
                page_count=page_count,
                selectable_text_characters=selectable_characters,
                sampled_pages=sampled_pages,
                encrypted=False,
                ocr_recommended=ocr_recommended,
                warnings=warnings,
            )

    def _apply_ocr_sync(self, pdf: bytes) -> bytes:
        if shutil.which("ocrmypdf") is None:
            raise OcrFailedError(
                "The PDF appears scanned, but OCRmyPDF is not installed on the server."
            )
        with tempfile.TemporaryDirectory(prefix="paper-ocr-") as directory:
            source = Path(directory) / "input.pdf"
            output = Path(directory) / "ocr.pdf"
            source.write_bytes(pdf)
            result = self._run(
                [
                    "ocrmypdf",
                    "--force-ocr",
                    "--deskew",
                    "--output-type",
                    "pdf",
                    str(source),
                    str(output),
                ],
                timeout=OCR_TIMEOUT_SECONDS,
            )
            if result.returncode != 0 or not output.exists():
                detail = result.stderr.strip()[-500:]
                raise OcrFailedError(
                    "OCR could not create a searchable version of this PDF."
                    + (f" {detail}" if detail else "")
                )
            return output.read_bytes()

    @staticmethod
    def _run(command: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrFailedError("PDF preprocessing timed out.") from exc
