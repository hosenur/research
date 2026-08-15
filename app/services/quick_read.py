from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.exceptions import InvalidDocumentError


QUICK_READ_TIMEOUT_SECONDS = 60
QUICK_CHUNK_CHARACTERS = 2_400


@dataclass(frozen=True)
class QuickTextChunk:
    key: str
    text: str
    order: int


@dataclass(frozen=True)
class QuickTextDocument:
    chunks: list[QuickTextChunk]
    character_count: int


class QuickTextExtractor:
    """Create a rough, retrieval-only text projection without pretending it is a Paper AST."""

    async def extract(self, pdf: bytes) -> QuickTextDocument:
        return await asyncio.to_thread(self._extract_sync, pdf)

    def _extract_sync(self, pdf: bytes) -> QuickTextDocument:
        executable = shutil.which("pdftotext")
        if executable is None:
            raise RuntimeError("Quick read requires Poppler's pdftotext executable.")
        with tempfile.TemporaryDirectory(prefix="paper-quick-read-") as directory:
            source = Path(directory) / "source.pdf"
            source.write_bytes(pdf)
            try:
                result = subprocess.run(
                    [executable, "-layout", "-enc", "UTF-8", str(source), "-"],
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=QUICK_READ_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Quick text extraction timed out.") from exc
        if result.returncode != 0:
            raise InvalidDocumentError(
                "Quick text extraction could not read this PDF. The authoritative parser is still running."
            )
        text = normalize_extracted_text(result.stdout)
        if len(re.sub(r"\s+", "", text)) < 80:
            raise InvalidDocumentError(
                "The PDF has too little selectable text for Quick read. The OCR-aware parser is still running."
            )
        chunks = chunk_quick_text(text)
        return QuickTextDocument(chunks=chunks, character_count=len(text))


def normalize_extracted_text(value: str) -> str:
    value = value.replace("\x0c", "\n\n").replace("\r\n", "\n")
    value = re.sub(r"(?<=\w)-\n(?=[a-z])", "", value)
    paragraphs = []
    for block in re.split(r"\n\s*\n", value):
        lines = [re.sub(r"\s+", " ", line).strip() for line in block.splitlines()]
        paragraph = " ".join(line for line in lines if line).strip()
        if paragraph:
            paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


def chunk_quick_text(text: str) -> list[QuickTextChunk]:
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        pieces = [
            paragraph[index : index + QUICK_CHUNK_CHARACTERS]
            for index in range(0, len(paragraph), QUICK_CHUNK_CHARACTERS)
        ]
        for piece in pieces:
            candidate = f"{current}\n\n{piece}".strip() if current else piece
            if current and len(candidate) > QUICK_CHUNK_CHARACTERS:
                chunks.append(current)
                current = piece
            else:
                current = candidate
    if current:
        chunks.append(current)
    return [
        QuickTextChunk(key=f"quick:{index}", text=chunk, order=index)
        for index, chunk in enumerate(chunks)
    ]
