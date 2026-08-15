import os

MAX_PDF_SIZE = 50 * 1024 * 1024
MAX_TEI_SIZE = 100 * 1024 * 1024
GROBID_TIMEOUT_SECONDS = 300.0
GROBID_RETRY_ATTEMPTS = 3
GROBID_RETRY_BASE_SECONDS = 5.0
GROBID_FALLBACK_FLAVOR = "article/light-ref"
PDF_PREFLIGHT_SAMPLE_PAGES = 3
PDF_MIN_SELECTABLE_CHARACTERS = 80
OCR_TIMEOUT_SECONDS = 300.0
OPENAI_TIMEOUT_SECONDS = 120.0
OPENAI_CHAT_MODEL = "gpt-5.4-nano"
OPENAI_MAX_OUTPUT_TOKENS = 2_048
CLAIM_AUDIT_MODEL = "gpt-5.4-nano"
CLAIM_AUDIT_REVIEW_MODEL = "gpt-5.4-mini"
CLAIM_AUDIT_MAX_OUTPUT_TOKENS = 2_048
CLAIM_AUDIT_BATCH_CHARACTERS = 12_000
CLAIM_AUDIT_PRIORITY_BATCH_CANDIDATES = 12
CLAIM_AUDIT_CONFIDENCE_THRESHOLD = 0.8
OPENALEX_TIMEOUT_SECONDS = 20.0
OPENALEX_CONCURRENCY = 2
OPENALEX_MIN_INTERVAL_SECONDS = 0.12
OPENALEX_RETRY_ATTEMPTS = 4
OPENALEX_MAX_RETRY_AFTER_SECONDS = 20.0
SEMANTIC_SCHOLAR_TIMEOUT_SECONDS = 20.0
SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS = 1.0
SEMANTIC_SCHOLAR_RETRY_ATTEMPTS = 3
SOURCE_SEARCH_RESULTS_PER_PROVIDER = 5
SOURCE_SEARCH_MAX_CANDIDATES = 5
SOURCE_SEARCH_VERSION = 10
SOURCE_VERIFICATION_MODEL = "gpt-5.4-nano"
MISSING_WORK_MAX_CLAIMS = 4
MISSING_WORK_RESULTS_PER_CLAIM = 5
REFERENCE_EVIDENCE_QUEUE_NAME = "reference-evidence"
CLAIM_AUDIT_QUEUE_NAME = "citation-audit"
CLAIM_CITATION_REVIEW_QUEUE_NAME = "claim-citation-review"
SOURCE_SEARCH_QUEUE_NAME = "citation-source-search"
PAPER_INDEX_QUEUE_NAME = "paper-index"
PAPER_PARSE_QUEUE_NAME = "paper-parse"
PAPER_QUICK_READ_QUEUE_NAME = "paper-quick-read"
PAPER_EXPORT_QUEUE_NAME = "paper-export"
BULLMQ_SCHEMA = "bullmq"


def grobid_url() -> str:
    return os.getenv("GROBID_URL", "http://localhost:8070")


def grobid_fallback_flavor() -> str | None:
    value = os.getenv("GROBID_FALLBACK_FLAVOR", GROBID_FALLBACK_FLAVOR).strip()
    return value or None


def ocr_enabled() -> bool:
    return os.getenv("OCR_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def extraction_artifact_path() -> str:
    return os.getenv("EXTRACTION_ARTIFACT_PATH", "/data/extractions")


def object_store_endpoint() -> str | None:
    value = os.getenv("S3_ENDPOINT", "").strip()
    return value or None


def object_store_access_key() -> str | None:
    value = os.getenv("S3_ACCESS_KEY", "").strip()
    return value or None


def object_store_secret_key() -> str | None:
    value = os.getenv("S3_SECRET_KEY", "").strip()
    return value or None


def object_store_bucket() -> str:
    return os.getenv("S3_BUCKET", "research-papers").strip() or "research-papers"


def object_store_region() -> str:
    return os.getenv("S3_REGION", "us-east-1").strip() or "us-east-1"


def object_store_secure() -> bool:
    value = os.getenv("S3_SECURE", "0").strip().lower()
    return value in {"1", "true", "yes"}


def database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://research:research-dev@localhost:5432/research",
    )


def bullmq_database_url() -> str:
    """Return psycopg conninfo without SQLAlchemy's explicit driver marker."""
    return database_url().replace("postgresql+psycopg://", "postgresql://", 1)


def bullmq_options() -> dict[str, object]:
    return {
        "backend": "postgres",
        "connection": bullmq_database_url(),
        "schema": BULLMQ_SCHEMA,
    }


def openai_api_key() -> str | None:
    value = os.getenv("OPENAI_API_KEY", "").strip()
    return value or None


def openai_base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def openai_chat_model() -> str:
    return os.getenv("OPENAI_MODEL", OPENAI_CHAT_MODEL).strip() or OPENAI_CHAT_MODEL


def claim_audit_model() -> str:
    return (
        os.getenv("CLAIM_AUDIT_MODEL", CLAIM_AUDIT_MODEL).strip()
        or CLAIM_AUDIT_MODEL
    )


def claim_audit_review_model() -> str:
    return (
        os.getenv("CLAIM_AUDIT_REVIEW_MODEL", CLAIM_AUDIT_REVIEW_MODEL).strip()
        or CLAIM_AUDIT_REVIEW_MODEL
    )


def source_verification_model() -> str:
    return os.getenv("SOURCE_VERIFICATION_MODEL", SOURCE_VERIFICATION_MODEL).strip() or SOURCE_VERIFICATION_MODEL


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


def semantic_scholar_url() -> str:
    return os.getenv(
        "SEMANTIC_SCHOLAR_URL",
        "https://api.semanticscholar.org/graph/v1",
    ).rstrip("/")


def semantic_scholar_api_key() -> str | None:
    value = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    return value or None
