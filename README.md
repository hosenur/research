# Research Paper API

A FastAPI service for parsing research-paper PDFs into a durable Paper JSON
document, a PostgreSQL-backed BullMQ worker for asynchronous OpenAlex
enrichment, and a Vite React frontend using TanStack Router, TanStack AI, SWR,
and Tailwind CSS.

Implementation and submission evidence:

- [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — completed phase plan and acceptance criteria
- [`COMPLETION_AUDIT.md`](COMPLETION_AUDIT.md) — runtime-backed pass/fail audit for all six phases
- [`SYSTEM_DESIGN.md`](SYSTEM_DESIGN.md) — architecture, algorithms, safety invariants, recovery, and scaling
- [`SMOKE_RESULTS.md`](SMOKE_RESULTS.md) — real all-endpoint runtime results and timings
- [`SUBMISSION.md`](SUBMISSION.md) — assessment coverage and recording checklist

## Start the stack

Docker and the Docker Compose plugin are required. From this directory, run:

```bash
docker compose up --build
```

The first run downloads the configured extraction and object-storage images,
so it can take a few minutes. Compose starts PostgreSQL, persistent MinIO,
GROBID, runs Alembic migrations, and then starts the API and all queue workers.
Once the stack is ready:

- FastAPI hello route: <http://rig:3333/hello>
- Durable PDF ingestion: `POST http://rig:3333/papers`
- Parsed paper route: `GET http://rig:3333/papers/{paperId}`
- Persisted source PDF: `GET http://rig:3333/papers/{paperId}/source`
- OpenAlex job route: `POST/GET http://rig:3333/papers/{paperId}/enrichments/openalex`
- Interactive API docs: <http://rig:3333/docs>
- MinIO API (localhost only): <http://127.0.0.1:9000>
- MinIO console (localhost only): <http://127.0.0.1:9001>

Verify the API:

```bash
curl http://rig:3333/hello
```

Expected response:

```json
{"message":"Hello, World!"}
```

Upload a paper through FastAPI and save the returned lifecycle envelope:

```bash
curl --form file=@sample_papers/attention-is-all-you-need.pdf \
  http://rig:3333/papers \
  --output paper.json
```

The endpoint accepts PDFs up to 50 MB, stores the immutable source in MinIO,
creates a lifecycle row in PostgreSQL, enqueues parsing, and immediately returns
`202` with `id`, `status`, `revision`, and `sourceUrl`. Poll the returned paper
route until `status` is `ready`; `paper` is nullable while the worker calls
GROBID. The compatibility `POST /papers/parse` route remains synchronous for
older clients.

### PDF extraction and recovery

The PDF boundary is an explicit, auditable pipeline:

1. Poppler preflight reads page count, encryption, and selectable text from a
   small page sample.
2. Text-poor PDFs pass through OCRmyPDF when `OCR_ENABLED=1`.
3. GROBID full-text extraction requests sentence segmentation, generated TEI
   IDs, raw bibliography strings, and coordinates for sentences, citation
   refs, bibliography entries, figures, and formulas.
4. An empty body retries with `GROBID_FALLBACK_FLAVOR` (default
   `article/light-ref`). A paper with citation markers but no bibliography uses
   `/api/processReferences` and merges the recovered list into the source TEI.
5. The normalized Paper receives an extraction quality report. The untouched
   final TEI is stored in MinIO (or the filesystem development adapter) and can be downloaded from
   `GET /papers/artifacts/{teiArtifactId}/tei`.

GROBID consolidation remains disabled: external identity and metadata are
added later through the explicit OpenAlex/Semantic Scholar provider boundary.
The default Compose image is the higher-accuracy `grobid:0.9.0-full`. For a
smaller CPU-only environment, set:

```bash
GROBID_IMAGE=grobid/grobid:0.9.0-crf docker compose up --build
```

The nested `paper` response exposes `extraction.requestOptions`, PDF and TEI hashes,
GROBID version, OCR and recovery history, the raw artifact ID, and quality
metrics. Paragraphs contain stable internal sentence spans; `source` and
`sourceSpans` retain GROBID IDs and PDF coordinate boxes separately so internal
IDs remain stable across repeated parses.

### Normalize TEI into Paper JSON

Convert an existing GROBID TEI file into the internal Paper AST:

```bash
curl --form file=@paper.tei.xml \
  http://rig:3333/papers/normalize \
  --output paper.json
```

The upload route runs the complete PDF → GROBID → Paper JSON pipeline and
persists its result:

```bash
curl --form file=@sample_papers/bert.pdf \
  http://rig:3333/papers/parse \
  --output paper.json
```

The JSON preserves sections and paragraph-level text/citation nodes. Adjacent
GROBID citation fragments are grouped into one stable citation occurrence. Each
occurrence has a deterministic `id`, preserves the original `rawText`, and
contains structured `items` whose `sourceId` values link to bibliography
entries. An `anchor` records half-open offsets in the normalized paragraph text,
while `resolution` exposes status, confidence, matching methods, ambiguous
candidates, and missing source IDs. Any targetless GROBID citation fragments
remain visible in `unresolvedFragments`; IDs targeting a missing bibliography
entry are also reported in the paper's `unresolvedReferenceIds`.

Older Paper JSON containing `referenceIds` is accepted at the API boundary and
migrated to `items`, but newly serialized papers use only the canonical citation
item structure.

```json
{
  "type": "citation",
  "id": "paragraph-4-citation-1",
  "rawText": "[3, 7]",
  "items": [
    {
      "sourceId": "b2",
      "resolutionMethod": "grobid-target",
      "confidence": "high"
    },
    {
      "sourceId": "b6",
      "resolutionMethod": "grobid-target",
      "confidence": "high"
    }
  ],
  "anchor": {
    "paragraphId": "paragraph-4",
    "startOffset": 182,
    "endOffset": 188
  },
  "form": "numeric",
  "resolution": {
    "status": "resolved",
    "confidence": "high",
    "methods": ["grobid-target"],
    "candidateSourceIds": [],
    "unresolvedSourceIds": []
  },
  "unresolvedFragments": [],
  "warnings": []
}
```

Citation item fields also reserve CSL-compatible `prefix`, `suffix`, `locator`,
`label`, `suppressAuthor`, and `authorOnly` values for editing and rendering.

The parser classifies citation style at two levels. `citationStyle` preserves
the broad compatibility value (`numeric`, `author-year`, `author-page`,
`harvard-key`, or `mixed`). `citationStyleDetection` explains how that decision
was made: observed marker syntaxes, confidence, evidence counts, and ranked CSL
style candidates. Bibliography punctuation contributes supporting evidence, but
the parser always sets `needsConfirmation` because styles such as APA, Chicago,
and Harvard can share the same in-text form after PDF extraction.

```json
{
  "citationStyle": "author-year",
  "citationStyleDetection": {
    "family": "author-year",
    "syntaxes": ["author-year-narrative", "author-year-parenthetical-comma"],
    "confidence": "high",
    "cslCandidates": [
      {
        "id": "apa",
        "label": "APA",
        "score": 0.72,
        "reason": "Comma-separated citations and parenthesized bibliography years are APA-like."
      }
    ],
    "needsConfirmation": true,
    "evidence": {
      "authorYearParentheticalComma": 14,
      "authorYearNarrative": 6,
      "referenceParenthesizedYear": 18
    },
    "reasons": ["Many author-year styles share identical in-text markers."]
  }
}
```

Every bibliography entry is retained with its original `rawText`, extracted
`rawFields`, and a canonical CSL-JSON `csl` object. Reference status is:

- `parsed` when title, author, and issued date were all extracted
- `partial` when some structured CSL data exists but core fields are missing
- `failed` when GROBID supplied no usable structured fields (`csl` is `null`)

### Chat with a parsed paper

The post-upload workspace uses TanStack AI's React `useChat` hook and AG-UI
server-sent events. The browser sends the parsed Paper JSON as conversation
context to `POST /chat`; the FastAPI endpoint removes coordinate-heavy source
metadata, grounds the model in the remaining paper content, and streams the
answer back into the existing chat UI.

Set the API key in `.env` before starting or rebuilding the API service:

```dotenv
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-5.4-nano
CLAIM_AUDIT_MODEL=gpt-5.4-nano
CLAIM_AUDIT_REVIEW_MODEL=gpt-5.4-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

The key stays on the FastAPI service and is never exposed to the browser.
`OPENAI_MODEL` is configurable; the default is `gpt-5.4-nano`. One Agent
conversation supports both grounded questions and proposed edits. It can inspect
sections, references, audit results, every immutable manuscript revision, and
exact historical snapshots. Edit commands appear as validated inline diffs and
change nothing until approval. Confirmed missing-citation findings are handed to
a separate background literature-search queue.

### Audit likely missing citations

The workspace starts a persistent citation audit after parsing. It has two
concurrent lanes:

1. Verbal heuristics identify uncited sentences containing quantitative,
   comparative, causal, prior-research, association, or generalized factual
   language. The low-cost model must return a decision for every candidate;
   candidates it does not confidently publish are independently reviewed by
   the stronger fallback model.
2. A compact projection of the complete body is scanned independently so the
   model can discover claims that do not match the verbal rules. This scan
   also reconsiders heuristic candidates so a false negative in the priority
   lane cannot permanently hide a claim.

The browser never receives raw heuristic candidates. Only high-confidence
findings confirmed by either configured model are stored and shown. Private
candidate decisions are retained for diagnosis but are not sent to the
browser. The model is
given section, paragraph, sentence, and citation identifiers, but not PDF
bytes, coordinates, extraction diagnostics, reference enrichment payloads, or
other irrelevant Paper JSON.

Start or resume the idempotent audit:

```bash
curl --request POST http://rig:3333/papers/{paperId}/citation-audit
```

Poll progress and findings newer than a known revision:

```bash
curl 'http://rig:3333/papers/{paperId}/citation-audit?afterRevision=1'
```

Completed AI batches, private verification decisions, and accepted findings are committed incrementally to
PostgreSQL. BullMQ retries can therefore resume without repeating completed
batches. The frontend uses an SWR Mutation to start the audit and SWR polling
to append newly confirmed findings.

Each confirmed finding enqueues an idempotent source-search job. The worker
queries the canonical PostgreSQL work index first, then consults both OpenAlex
and Semantic Scholar using the claim, section context, and paper topic. Exact
provider responses and normalized papers are persisted in PostgreSQL, so a
repeated query is served from the database before any external request. Known
bibliography entries are excluded, weak local-only matches are withheld, and
ranked candidates arrive through the same revision-based polling response.

At worker startup, the legacy `/data/openalex-cache.jsonl` file is imported
idempotently into the provider-response and scholarly-work tables. New
responses are written only to PostgreSQL. `SEMANTIC_SCHOLAR_API_KEY` is
optional; setting it in `.env` provides the provider's authenticated rate
limits.

### Enrich references in the background

After parsing, enqueue OpenAlex enrichment using the returned document ID. The
request returns `202 Accepted` without waiting for all bibliography lookups:

```bash
curl --request POST \
  http://rig:3333/papers/{paperId}/enrichments/openalex
```

The stable job ID makes this operation idempotent. A dedicated Python BullMQ
worker consumes it continuously; this is not a cron job. BullMQ uses the same
PostgreSQL instance as the application, in a separate `bullmq` schema, and no
Redis service is required. The worker matches each bibliography entry by DOI,
then arXiv ID, then title and year. Each completed reference is committed
individually so progress survives a process restart.

Poll for queue state, counters, and only the reference changes since a known
revision:

```bash
curl 'http://rig:3333/papers/{paperId}/enrichments/openalex?afterRevision=1'
```

The response reports `queued`, `running`, `completed`, or `failed`, along with
`progress`, the latest `revision`, and `referenceUpdates`. Each updated
reference receives `openalex`, `openalexStatus` (`matched`, `unmatched`,
`error`, or `skipped`), and `openalexError` when lookup failed. Fetch
`GET /papers/{paperId}` at any time for the complete current Paper projection.

Successful provider responses are also cached in
`/data/openalex-cache.jsonl` so repeated matching does not spend OpenAlex
quota. Set `OPENALEX_MAILTO` in `.env` to use the polite pool, and
`OPENALEX_PROXY` if requests should leave through a configured proxy. The
legacy synchronous `POST /papers/enrich` endpoint remains available for direct
API use, but the frontend uses the background workflow.

### Find missing related work

After parse (and preferably after OpenAlex enrichment), search for papers the
bibliography does not already contain:

```bash
curl --header 'Content-Type: application/json' \
  --data @paper.json \
  http://rig:3333/papers/missing-works \
  --output missing-works.json
```

The API extracts a few claim-like sentences from Introduction / Related Work,
searches OpenAlex, and drops anything already cited by DOI, arXiv id, OpenAlex
id, or title. Empty or failed searches are returned as-is. No invented papers.

## Networking

FastAPI is published only on this machine's Tailscale address, configured by
`TAILSCALE_IP` and `API_PORT` in `.env`. With Tailscale MagicDNS enabled, other
devices in the tailnet can access it at `http://rig:3333`; it is not bound to
the machine's LAN or public interfaces. Port `3333` is used because this host
already has another application listening on port `8000`.

GROBID has no host port. It is attached only to Compose's internal `backend`
network and is reachable from FastAPI at `http://grobid:8070`. If the machine's
Tailscale address changes, run `tailscale ip -4`, update `.env`, and recreate
the stack.

## Sample research papers

The `sample_papers` directory contains three open-access arXiv papers that can
be used to exercise the endpoint:

- `attention-is-all-you-need.pdf` — Vaswani et al., 2017
- `bert.pdf` — Devlin et al., 2018
- `language-models-are-few-shot-learners.pdf` — Brown et al., 2020

Try any of them using the cURL command above or the upload form in the
interactive API documentation.

## Frontend development

The React app lives in `frontend/`. Its Vite server listens only on SSH-local
`127.0.0.1:5555` and proxies `/api` calls to the Tailscale-bound FastAPI service.
HTTP state is encapsulated in React hooks: SWR Mutation owns upload and job
start operations, while SWR owns incremental enrichment polling. TanStack AI's
`useChat` hook continues to own the streaming chat transport.

```bash
cd frontend
bun install
bun run dev
```

Use SSH port forwarding if you want to view it from your computer without
publishing another service:

```bash
ssh -L 5555:127.0.0.1:5555 rig
```

Then open <http://localhost:5555>. Routes are defined under
`frontend/src/routes`; TanStack Router generates the route tree during dev and
build.

## GROBID image choice

The Compose stack defaults to `grobid/grobid:0.9.0-full` for higher extraction
accuracy, especially around citations and references. The full image is much
larger and works best with a supported GPU. Set
`GROBID_IMAGE=grobid/grobid:0.9.0-crf` for the smaller CPU-only variant.
