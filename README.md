# Paper Review Agent

A citation-aware workspace that turns a PDF into a structured manuscript, checks missing and existing citations against real scholarly sources, proposes reviewable edits, and exports a CSL-rendered PDF or editable LaTeX bundle.

## Run

```bash
cp .env.example .env                 # set TAILSCALE_IP and OPENAI_API_KEY
docker compose up --build            # API, worker, PostgreSQL, MinIO, GROBID
cd frontend && bun install && bun run dev
```

The frontend runs at `http://127.0.0.1:5555`, the API at `http://$TAILSCALE_IP:3333`, and API docs at `/docs`. Do not upload confidential papers: this assessment build intentionally has no authentication or tenancy.

Railway deploys the API and worker from the connected Git repository. They share one image; Alembic runs before startup, while PostgreSQL, MinIO, and GROBID stay on private service URLs.

## System design

```text
React + SWR + TanStack AI ──HTTP / AG-UI SSE──> FastAPI
                                                   ├── PostgreSQL + pgvector: papers, indexes, findings, revisions, caches
                                                   ├── MinIO: immutable PDFs, TEI, and exports
                                                   └── PostgreSQL-backed BullMQ ──> workers
                                                                                   ├── GROBID / OCR / Poppler
                                                                                   ├── OpenAlex + Semantic Scholar
                                                                                   └── OpenAI
```

Upload validates a PDF up to 50 MB, stores it first, creates a durable UUID, and returns `202` immediately. Quick Read and authoritative GROBID parsing run in parallel. Quick Read permits provisional Q&A; citation review, editing, and export unlock only after the stable Paper AST is ready. Workers then build the pgvector index, resolve references, review missing and existing citations, and publish results incrementally.

The Paper AST preserves sections, paragraphs, sentences, citation nodes, reference IDs, anchors, raw text, CSL-JSON, extraction quality, and source coordinates. The browser only polls durable state; refreshes and worker restarts do not restart completed work.

## Decisions for fast interaction and reuse

- The local PDF appears immediately; parsing and reviews never block entry to the workspace.
- Independent jobs run concurrently with stable IDs, bounded retries, stage-level status, and manual recovery.
- A paper's first successful parse persists its source PDF, raw TEI, Paper AST, quick/authoritative indexes, findings, and immutable revision history. Reopening its UUID reuses that state without parsing again.
- Provider responses are cached by exact request in PostgreSQL. Normalized scholarly works are deduplicated by provider IDs/DOI/title and searched locally before external calls, so sources discovered for one paper can support future papers.
- Repeat uploads currently create a new paper UUID; reuse is guaranteed for an existing paper URL and the shared scholarly-work/provider cache, not by upload hash.
- Papers over 80 pages still parse and support chat, but automated review is section-scoped to bound latency and cost.

## Trust and editing rules

- OpenAlex and Semantic Scholar are the only sources for suggested papers. A citation is insertable only when provider title/abstract evidence verifies support for the exact anchored claim.
- Citation form, locators, narrative markers, and bibliography layout are rendered by Pandoc citeproc from canonical CSL-JSON and a user-confirmed installed CSL style (APA, IEEE, and others), never handwritten marker templates.
- General prose edits are extractive tightenings: deterministic validation rejects introduced words or novel claims. Citation tools attach a verified source to an existing claim rather than inventing factual prose.
- Every mutation is a typed proposal. Nothing changes until explicit approval; approval creates an immutable hashed snapshot and supports selective revert or full restore.
- Approval commits the manuscript before refresh jobs are queued. A queue outage returns a warning and marks refresh work failed without turning a successful edit into a misleading HTTP error.
- Export is semantically faithful, not pixel-identical: Pandoc produces CSL citations and references, then LaTeX produces a PDF plus an editable bundle. Complex figures, equations, typography, and page layout may require restoration.

OpenAI is used for grounded chat, claim discovery, evidence classification, and constrained edit planning. Deterministic code owns PDF validation, AST anchors, provider provenance, CSL rendering, mutation validation, approval, and history.

## Assumptions and fixtures

GROBID is the authoritative parser; text-poor PDFs may use OCR. Review quality depends on provider metadata/abstract availability and configured API access (`OPENAI_API_KEY`; optional `OPENALEX_API_KEY`, `OPENALEX_MAILTO`, and `SEMANTIC_SCHOLAR_API_KEY`). The sample PDFs are open-access arXiv fixtures: Attention Is All You Need ([1706.03762](https://arxiv.org/abs/1706.03762)), BERT ([1810.04805](https://arxiv.org/abs/1810.04805)), and Language Models are Few-Shot Learners ([2005.14165](https://arxiv.org/abs/2005.14165)); their authors retain ownership.

Frontend primitives come from the Intent UI registry and licensed Beautiful UI components; registry metadata and the bundled [`LICENSE`](frontend/src/components/ui/LICENSE) are retained.

## Validation

```bash
docker compose build api
docker compose run --rm api python -m unittest discover -s tests -v
cd frontend && bun run build
```

The backend suite contains 48 passing tests, including paper-scoped agent tools, automatic controlled citation search, real APA/IEEE CSL rendering, full CSL bibliographies, compiled PDF and editable exports, grounded citation selection, approval recovery, parser/provider behavior, and three real-paper fixtures.
