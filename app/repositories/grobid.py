from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import GROBID_RETRY_ATTEMPTS, GROBID_RETRY_BASE_SECONDS
from app.exceptions import (
    GrobidBusyError,
    GrobidEmptyResultError,
    GrobidNoTextError,
    GrobidRequestError,
    GrobidUnavailableError,
)


FULLTEXT_OPTIONS: dict[str, Any] = {
    "consolidateHeader": "0",
    "consolidateCitations": "0",
    "includeRawCitations": "1",
    "segmentSentences": "1",
    "generateIDs": "1",
    "teiCoordinates": ["ref", "biblStruct", "s", "figure", "formula"],
}


@dataclass(frozen=True)
class GrobidResult:
    xml: bytes
    endpoint: str
    options: dict[str, Any]


class GrobidRepository:
    """Talk to GROBID while keeping request options and failures explicit."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def version(self) -> str | None:
        try:
            response = await self._client.get("/api/version")
        except httpx.RequestError:
            return None
        return response.text.strip() if response.status_code == 200 else None

    async def process_fulltext(
        self,
        pdf: bytes,
        filename: str,
        *,
        flavor: str | None = None,
    ) -> GrobidResult:
        options = dict(FULLTEXT_OPTIONS)
        if flavor:
            options["flavor"] = flavor
        response = await self._post_pdf(
            "/api/processFulltextDocument",
            pdf,
            filename,
            options,
        )
        return GrobidResult(
            xml=response.content,
            endpoint="processFulltextDocument",
            options=options,
        )

    async def process_references(self, pdf: bytes, filename: str) -> GrobidResult:
        options: dict[str, Any] = {
            "consolidateCitations": "0",
            "includeRawCitations": "1",
        }
        response = await self._post_pdf(
            "/api/processReferences",
            pdf,
            filename,
            options,
        )
        return GrobidResult(
            xml=response.content,
            endpoint="processReferences",
            options=options,
        )

    async def _post_pdf(
        self,
        path: str,
        pdf: bytes,
        filename: str,
        options: dict[str, Any],
    ) -> httpx.Response:
        response: httpx.Response | None = None
        for attempt in range(GROBID_RETRY_ATTEMPTS):
            multipart: list[tuple[str, tuple[Any, ...]]] = [
                ("input", (filename, pdf, "application/pdf"))
            ]
            for key, value in options.items():
                values = value if isinstance(value, list) else [value]
                multipart.extend((key, (None, str(item))) for item in values)

            try:
                response = await self._client.post(path, files=multipart)
            except httpx.TimeoutException as exc:
                if attempt + 1 < GROBID_RETRY_ATTEMPTS:
                    await asyncio.sleep(GROBID_RETRY_BASE_SECONDS * (attempt + 1))
                    continue
                raise GrobidUnavailableError(
                    "GROBID timed out while processing the PDF.",
                    context={"attempts": GROBID_RETRY_ATTEMPTS},
                ) from exc
            except httpx.RequestError as exc:
                raise GrobidUnavailableError("The GROBID service is unavailable.") from exc

            if response.status_code != 503:
                break
            if attempt + 1 < GROBID_RETRY_ATTEMPTS:
                await asyncio.sleep(GROBID_RETRY_BASE_SECONDS * (attempt + 1))

        if response is None:
            raise GrobidUnavailableError("The GROBID service did not return a response.")
        self._raise_for_response(response)
        return response

    @staticmethod
    def _raise_for_response(response: httpx.Response) -> None:
        if response.status_code == 200:
            return
        if response.status_code == 204:
            raise GrobidEmptyResultError(
                "GROBID processed the PDF but could not extract structured content."
            )
        if response.status_code == 503:
            raise GrobidBusyError(
                "GROBID is busy after multiple retries. Try the paper again shortly."
            )

        body = response.text.strip()[:1000]
        upper = body.upper()
        if "NO_BLOCKS" in upper:
            raise GrobidNoTextError(
                "The PDF contains no selectable text blocks and likely needs OCR."
            )

        messages = {
            "TOO_MANY_BLOCKS": "The PDF contains too many layout blocks for GROBID.",
            "TOO_MANY_TOKENS": "The PDF contains too many tokens for GROBID.",
            "TIMEOUT": "GROBID stopped because PDF processing exceeded its limit.",
            "TAGGING_ERROR": "GROBID could not label this document with its configured models.",
            "PDFALTO_CONVERSION_FAILURE": "GROBID could not convert the PDF layout.",
            "PARSING_ERROR": "GROBID could not parse the PDF structure.",
            "BAD_INPUT_DATA": "GROBID rejected the uploaded PDF as invalid input.",
        }
        for code, message in messages.items():
            if code in upper:
                raise GrobidRequestError(
                    message,
                    context={"grobidCode": code, "status": response.status_code},
                )

        detail = f"GROBID returned HTTP {response.status_code}."
        if body:
            detail = f"{detail} {body}"
        raise GrobidRequestError(detail, context={"status": response.status_code})
