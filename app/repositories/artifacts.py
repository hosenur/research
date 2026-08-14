from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.exceptions import ExtractionArtifactNotFoundError

ARTIFACT_ID_RE = re.compile(r"^[a-f0-9]{16}-[a-f0-9]{16}$")


class ExtractionArtifactStore:
    """Persist raw TEI separately from the normalized Paper response."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def save_tei(self, pdf_sha256: str, tei: bytes) -> str:
        tei_sha256 = hashlib.sha256(tei).hexdigest()
        artifact_id = f"{pdf_sha256[:16]}-{tei_sha256[:16]}"
        self._root.mkdir(parents=True, exist_ok=True)
        target = self._root / f"{artifact_id}.tei.xml"
        if not target.exists():
            temporary = self._root / f".{artifact_id}.tmp"
            temporary.write_bytes(tei)
            temporary.replace(target)
        return artifact_id

    def read_tei(self, artifact_id: str) -> bytes:
        if not ARTIFACT_ID_RE.fullmatch(artifact_id):
            raise ExtractionArtifactNotFoundError("The TEI artifact ID is invalid.")
        target = self._root / f"{artifact_id}.tei.xml"
        if not target.is_file():
            raise ExtractionArtifactNotFoundError("The TEI extraction artifact was not found.")
        return target.read_bytes()
