import os

MAX_PDF_SIZE = 50 * 1024 * 1024
MAX_TEI_SIZE = 100 * 1024 * 1024
GROBID_TIMEOUT_SECONDS = 300.0
OPENALEX_TIMEOUT_SECONDS = 20.0
OPENALEX_CONCURRENCY = 2
OPENALEX_MIN_INTERVAL_SECONDS = 0.12
OPENALEX_RETRY_ATTEMPTS = 4
OPENALEX_MAX_RETRY_AFTER_SECONDS = 20.0
MISSING_WORK_MAX_CLAIMS = 4
MISSING_WORK_RESULTS_PER_CLAIM = 5


def grobid_url() -> str:
    return os.getenv("GROBID_URL", "http://localhost:8070")


def openalex_url() -> str:
    return os.getenv("OPENALEX_URL", "https://api.openalex.org")


def openalex_mailto() -> str | None:
    value = os.getenv("OPENALEX_MAILTO", "").strip()
    return value or None


def openalex_api_key() -> str | None:
    value = os.getenv("OPENALEX_API_KEY", "").strip()
    return value or None


def openalex_cache_path() -> str:
    return os.getenv("OPENALEX_CACHE_PATH", "/data/openalex-cache.jsonl")


def openalex_proxy() -> str | None:
    value = (
        os.getenv("OPENALEX_PROXY", "").strip()
        or os.getenv("HTTPS_PROXY", "").strip()
        or os.getenv("HTTP_PROXY", "").strip()
    )
    return value or None
