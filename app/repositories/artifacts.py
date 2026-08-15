from __future__ import annotations

import hashlib
import io
import re
import threading
from pathlib import Path
from typing import Protocol

from minio import Minio
from minio.error import S3Error

from app.config import (
    extraction_artifact_path,
    object_store_access_key,
    object_store_bucket,
    object_store_endpoint,
    object_store_region,
    object_store_secret_key,
    object_store_secure,
)
from app.exceptions import ExtractionArtifactNotFoundError

ARTIFACT_ID_RE = re.compile(r"^[a-f0-9]{16}-[a-f0-9]{16}$")


class PaperArtifactStore(Protocol):
    """Durable paper bytes without exposing storage-provider details."""

    def save_source(self, paper_id: str, filename: str, content: bytes) -> str: ...

    def read_source(self, object_key: str) -> bytes: ...

    def save_tei(self, pdf_sha256: str, tei: bytes) -> str: ...

    def read_tei(self, artifact_id: str) -> bytes: ...

    def save_export(
        self,
        paper_id: str,
        export_id: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> str: ...

    def read_export(self, object_key: str) -> bytes: ...


class LocalPaperArtifactStore:
    """Filesystem adapter for local development and single-host deployments."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def save_source(self, paper_id: str, filename: str, content: bytes) -> str:
        del filename
        object_key = f"papers/{paper_id}/source.pdf"
        target = self._path_for_key(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            temporary = target.with_name(f".{target.name}.tmp")
            temporary.write_bytes(content)
            temporary.replace(target)
        return object_key

    def read_source(self, object_key: str) -> bytes:
        target = self._path_for_key(object_key)
        if not target.is_file():
            raise ExtractionArtifactNotFoundError("The source PDF was not found.")
        return target.read_bytes()

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

    def save_export(self, paper_id: str, export_id: str, filename: str, content: bytes, content_type: str) -> str:
        del content_type
        object_key = export_object_key(paper_id, export_id, filename)
        target = self._path_for_key(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
        return object_key

    def read_export(self, object_key: str) -> bytes:
        target = self._path_for_key(object_key)
        if not target.is_file():
            raise ExtractionArtifactNotFoundError("The generated export was not found.")
        return target.read_bytes()

    def _path_for_key(self, object_key: str) -> Path:
        if not valid_paper_object_key(object_key):
            raise ExtractionArtifactNotFoundError("The source PDF key is invalid.")
        return self._root / object_key


class MinioPaperArtifactStore:
    """S3-compatible production adapter backed by the private MinIO service."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
        secure: bool,
    ) -> None:
        self._client = Minio(
            _normalize_endpoint(endpoint),
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            secure=secure,
        )
        self._bucket = bucket
        self._region = region
        self._bucket_ready = False
        self._bucket_lock = threading.Lock()

    def save_source(self, paper_id: str, filename: str, content: bytes) -> str:
        del filename
        object_key = f"papers/{paper_id}/source.pdf"
        self._put(
            object_key,
            content,
            content_type="application/pdf",
        )
        return object_key

    def read_source(self, object_key: str) -> bytes:
        if not re.fullmatch(r"papers/[a-f0-9-]{36}/source\.pdf", object_key):
            raise ExtractionArtifactNotFoundError("The source PDF key is invalid.")
        return self._get(object_key, "The source PDF was not found.")

    def save_tei(self, pdf_sha256: str, tei: bytes) -> str:
        tei_sha256 = hashlib.sha256(tei).hexdigest()
        artifact_id = f"{pdf_sha256[:16]}-{tei_sha256[:16]}"
        self._put(
            f"extractions/{artifact_id}.tei.xml",
            tei,
            content_type="application/tei+xml",
        )
        return artifact_id

    def read_tei(self, artifact_id: str) -> bytes:
        if not ARTIFACT_ID_RE.fullmatch(artifact_id):
            raise ExtractionArtifactNotFoundError("The TEI artifact ID is invalid.")
        return self._get(
            f"extractions/{artifact_id}.tei.xml",
            "The TEI extraction artifact was not found.",
        )

    def save_export(self, paper_id: str, export_id: str, filename: str, content: bytes, content_type: str) -> str:
        object_key = export_object_key(paper_id, export_id, filename)
        self._put(object_key, content, content_type=content_type)
        return object_key

    def read_export(self, object_key: str) -> bytes:
        if not valid_paper_object_key(object_key) or "/exports/" not in object_key:
            raise ExtractionArtifactNotFoundError("The export object key is invalid.")
        return self._get(object_key, "The generated export was not found.")

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        with self._bucket_lock:
            if self._bucket_ready:
                return
            if not self._client.bucket_exists(self._bucket):
                try:
                    self._client.make_bucket(self._bucket, location=self._region)
                except S3Error as exc:
                    if exc.code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                        raise
            self._bucket_ready = True

    def _put(
        self,
        object_key: str,
        content: bytes,
        *,
        content_type: str,
    ) -> None:
        self._ensure_bucket()
        self._client.put_object(
            self._bucket,
            object_key,
            io.BytesIO(content),
            len(content),
            content_type=content_type,
        )

    def _get(self, object_key: str, not_found_message: str) -> bytes:
        self._ensure_bucket()
        try:
            response = self._client.get_object(self._bucket, object_key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise ExtractionArtifactNotFoundError(not_found_message) from exc
            raise


# Compatibility name for callers that explicitly construct the local adapter.
ExtractionArtifactStore = LocalPaperArtifactStore


def create_paper_artifact_store() -> PaperArtifactStore:
    endpoint = object_store_endpoint()
    if not endpoint:
        return LocalPaperArtifactStore(Path(extraction_artifact_path()))

    access_key = object_store_access_key()
    secret_key = object_store_secret_key()
    if not access_key or not secret_key:
        raise RuntimeError(
            "S3_ACCESS_KEY and S3_SECRET_KEY are required when S3_ENDPOINT is set."
        )
    return MinioPaperArtifactStore(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        bucket=object_store_bucket(),
        region=object_store_region(),
        secure=object_store_secure(),
    )


def _normalize_endpoint(endpoint: str) -> str:
    return endpoint.removeprefix("http://").removeprefix("https://").rstrip("/")


def export_object_key(paper_id: str, export_id: str, filename: str) -> str:
    if not re.fullmatch(r"[a-f0-9-]{36}", paper_id) or not re.fullmatch(r"[a-f0-9-]{36}", export_id):
        raise ExtractionArtifactNotFoundError("The export identity is invalid.")
    if not re.fullmatch(r"paper-r\d+\.(?:zip|pdf)", filename):
        raise ExtractionArtifactNotFoundError("The export filename is invalid.")
    return f"papers/{paper_id}/exports/{export_id}/{filename}"


def valid_paper_object_key(object_key: str) -> bool:
    return bool(
        re.fullmatch(r"papers/[a-f0-9-]{36}/source\.pdf", object_key)
        or re.fullmatch(
            r"papers/[a-f0-9-]{36}/exports/[a-f0-9-]{36}/paper-r\d+\.(?:zip|pdf)",
            object_key,
        )
    )
