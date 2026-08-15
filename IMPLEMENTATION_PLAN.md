# Paper Improvement Agent — implementation plan

This plan turns the decisions in `ASSUMPTIONS.md` into one dependency-ordered vertical workflow. The target is a responsive assessment demo whose first useful interaction is immediate, whose long-running work is durable, and whose edits cannot silently damage citations or manuscript structure.

## Product contract

- Upload opens a real workspace immediately and returns a durable paper ID when transfer finishes.
- A provisional **Quick read** becomes available while GROBID performs authoritative extraction.
- Parsing, indexing, reference resolution, missing-work discovery, and claim/citation verification start automatically.
- Results arrive progressively and survive refresh, disconnects, service restarts, and independent stage failures.
- The original PDF is immutable. The editable source of truth is a versioned Paper AST.
- New citations come only from verified OpenAlex or Semantic Scholar records represented as CSL-JSON.
- Natural-language commands become constrained AST operations, a validated diff, and an explicit approval.
- Export produces an editable LaTeX project and compiled PDF with honest reconstruction warnings.

## Target flow

```text
select PDF
   │
   ├─ show local PDF immediately
   │
   └─ upload → MinIO + paper record → /papers/:paperId
                    │
                    ├─ quick extraction → provisional chunks → embeddings → Quick read
                    │
                    └─ GROBID parse → authoritative Paper AST
                                      │
                                      ├─ authoritative chunks + embeddings
                                      ├─ bibliography resolution
                                      ├─ missing-citation review → source search/verification
                                      └─ existing claim/citation verification
                                                      │
                                                      └─ anchored findings
                                                              │
                                           natural-language edit plan
                                                              │
                                         invariant validation + diff
                                                              │
                                                   human approval
                                                              │
                                               immutable revision
                                                              │
                                              CSL → LaTeX → PDF
```

## Module design

### 1. Paper artifacts

**Interface**

- Store and load an original PDF by paper ID.
- Store and load TEI extraction artifacts by stable artifact ID.
- Store and load export bundles by paper/revision.
- Hide bucket creation, key layout, content types, MinIO connection details, and local filesystem paths.

**Adapters**

- `MinioPaperArtifacts`: production adapter using the private S3-compatible MinIO service.
- `LocalPaperArtifacts`: local adapter rooted at the configured artifact directory.

The rest of the code must not know bucket names or object keys.

### 2. Paper lifecycle

**Interface**

- `ingest(filename, content) -> PaperLifecycle`
- `get(paper_id) -> PaperLifecycle`
- `begin_stage`, `complete_stage`, and `fail_stage` for durable worker transitions.
- `complete_parse(paper_id, Paper)` publishes the authoritative projection atomically.

The module owns validation, hashes, object persistence, database transitions, stable queue IDs, retries, and public error projection. Routers only invoke the interface and serialize its result.

### 3. Retrieval index

**Interface**

- Build either a provisional or authoritative index for a paper revision.
- Search the best currently available index and return traceable chunks.
- Promote authoritative chunks atomically so chat never mixes index generations.

Quick extraction uses rough text chunks. Authoritative extraction uses stable abstract, section, paragraph, sentence, citation, and reference identifiers. Embeddings prioritize retrieval; they never decide whether a citation supports a claim.

### 4. Review orchestrator

**Interface**

- Start or resume the automatic review DAG for a parsed revision.
- Return a revision-based stream/poll projection of stages and findings.
- Retry one failed stage without discarding successful outputs.

The implementation coordinates bibliography resolution, missing-citation discovery, source verification, and existing claim/citation verification. Findings share one anchored representation and are classified by review type.

### 5. Manuscript revisions

**Interface**

- Plan constrained operations from a natural-language command.
- Validate a proposal against citation and structure invariants.
- Approve all or selected diff hunks into one immutable revision.
- Compare, restore, or selectively revert revisions.

The implementation owns stable-node addressing, source acceptance, CSL insertion, citation anchoring, claim-support checks, and conflict detection. The model never writes the database projection directly.

### 6. Citation rendering and export

**Interface**

- Confirm a CSL style for a paper.
- Render citations and bibliography from canonical CSL-JSON.
- Export a revision as a LaTeX bundle and compiled PDF.

The implementation owns CSL processor integration, bibliography ordering, escaping, LaTeX templates, compilation, MinIO storage, and explicit warnings for unrecoverable content.

## Persistence changes

### Papers

Extend `papers` with:

- `status`: `uploaded | parsing | ready | failed`
- nullable `paper_json` until authoritative parsing completes
- `source_object_key` and original content hash
- nullable `parse_error`, page count, and processing timestamps
- current authoritative revision and current approved manuscript revision

### Pipeline stages

Add `paper_pipeline_stages` keyed by `(paper_id, stage)` with status, attempt, progress JSON, error, started/completed timestamps, and revision. Stages include upload, quick extraction, quick index, authoritative parse/index, reference resolution, missing-citation review, existing-citation review, and export.

### Retrieval

Extend `paper_chunks` with `index_kind`, paper revision, and source-node identity. A uniqueness constraint prevents provisional and authoritative generations from colliding. Promotion replaces only the matching generation inside one transaction.

### Existing citation review

Add durable claim/citation pairs and judgments with claim span, citation/reference IDs, provider evidence, embedding priority, model, classification, confidence, explanation, and review revision.

### Editing

Add:

- `manuscript_revisions`: immutable Paper AST snapshots or parent-relative patches with content hashes.
- `edit_proposals`: command, base revision, status, summary, warnings, and proposed operations.
- `edit_operations`: typed operation payload, affected node IDs, validation result, and approval state.
- `paper_csl_styles`: detected candidates and confirmed style.

### Exports

Add export records keyed by paper revision and format, with MinIO keys, warnings, compiler status, and error details.

## HTTP interface

### Ingestion and workspace

- `POST /papers` — upload PDF, persist it, enqueue durable work, return `202` with paper ID and lifecycle.
- `GET /papers/{paperId}` — return lifecycle plus the latest available projections; `paper` is nullable until GROBID succeeds.
- `GET /papers/{paperId}/source` — proxy the private MinIO PDF for inline viewing.
- `GET /papers/{paperId}/pipeline` — return stage progress and public errors.
- `POST /papers/{paperId}/pipeline/{stage}/retry` — retry only one failed stage.

Keep `POST /papers/parse` temporarily as a compatibility path, then remove it after the frontend and documented examples use durable ingestion.

### Review

- Continue revision-based finding retrieval, but unify missing-citation and existing-citation findings in one review projection.
- Finding records include exact AST anchors, classification, evidence, confidence, provider links, and actionable state.
- `Use source` creates an edit proposal; it does not mutate the manuscript.

### Editing and revisions

- `POST /papers/{paperId}/edits` — plan an edit against a required base revision.
- `GET /papers/{paperId}/edits/{proposalId}` — retrieve operations, validation, and diff.
- `POST /papers/{paperId}/edits/{proposalId}/approve` — approve all or selected hunks.
- `POST /papers/{paperId}/edits/{proposalId}/discard` — reject a pending proposal without changing the manuscript.
- `GET /papers/{paperId}/revisions` and `/revisions/{revision}` — history and comparison.
- `POST /papers/{paperId}/revisions/{revision}/restore` — create a new revision restoring prior content.

### Export

- `PUT /papers/{paperId}/citation-style` — confirm a detected CSL style.
- `POST /papers/{paperId}/exports` — enqueue LaTeX/PDF generation for a revision.
- `GET /papers/{paperId}/exports/{exportId}` — status, warnings, and download URLs.

## Worker DAG

1. Ingestion stores the source PDF and creates the paper row.
2. Quick extraction and authoritative parsing start concurrently.
3. Quick extraction builds provisional chunks and embeddings, then unlocks Quick read.
4. Authoritative parsing stores TEI and publishes the Paper AST.
5. Authoritative indexing and bibliography resolution start concurrently.
6. Missing-citation review can begin from the AST while bibliography resolution continues.
7. Existing claim/citation verification begins as individual references gain provider evidence.
8. Source search starts per accepted missing-citation finding and streams candidates independently.
9. A failed stage retries with backoff and never resets unrelated completed stages.
10. Papers over 80 pages skip automatic whole-document model review and expose section-scoped review instead.

Stable BullMQ job IDs make every stage idempotent. Workers commit incremental batches so retries resume rather than repeat completed provider/model work.

## Frontend experience

### Upload and routing

- Selecting a valid PDF immediately opens the workspace using a local object URL.
- Upload progress remains visible without replacing the whole screen.
- On `202`, navigate to `/papers/:paperId` and switch the preview to the persisted source endpoint when available.
- All server state and polling live in SWR hooks; upload progress remains in the dedicated transport hook.

### Workspace

- Primary surface: structured manuscript viewer/editor.
- Context panel tabs: Review, Agent, References, and Export.
- Optional original-PDF split view.
- Before authoritative parsing: PDF plus Quick-read status; citation-sensitive controls are disabled with a reason.
- After parsing: manuscript appears, chat promotes automatically, review findings anchor to exact nodes, and ordinary editing unlocks.

### Review

- One inbox grouped by missing citation, weak support, contradiction, and uncertainty.
- Clicking a finding scrolls to and highlights the exact manuscript sentence.
- Candidate cards show provider links, evidence, confidence, and honest unverifiable states.
- `Use source` opens a controlled Intent UI modal containing the proposal diff and Approve/Discard actions instead of changing the paper.
- Keep resolved findings accessible and use an SWR mutation to prepare a reversible `Remove source` proposal in the same modal.

### Editing

- Commands produce a streaming plan followed by a command-level diff.
- Users approve all or inspect and approve individual sentence-level hunks.
- Unsafe operations never receive an enabled approval control.
- Revision history supports compare, selective revert, restore, and export.

## Performance and observability

Targets for a typical 20-page born-digital PDF:

- workspace/PDF visible: `<1s`
- durable paper ID: immediately after transfer
- Quick read: `<5s`
- authoritative parse: `<30s`
- first verified finding: `<45s`

Record stage queue latency, runtime, attempt count, provider latency, model batch size, and time to first result. Expose product-friendly stages rather than provider implementation details.

## Delivery phases

### Phase 1 — durable ingestion foundation

**Status: complete.**

- MinIO/local artifact adapters and bucket bootstrap.
- Paper lifecycle migration and repository methods.
- `POST /papers`, lifecycle polling, source-PDF endpoint, parse queue, parse worker, automatic downstream fan-out.
- `/papers/:paperId` frontend route with persisted reload state.

**Acceptance:** upload returns before GROBID; closing/reopening the route restores progress; parsing survives API restarts; completed parse automatically starts existing indexing, enrichment, and audit jobs.

### Phase 2 — Quick read

**Status: complete.**

- Fast full-text extraction, provisional chunker, provisional pgvector generation, and phase-aware search.
- Chat labels provisional answers and promotes future turns to authoritative context without rewriting history.

**Acceptance:** broad chat becomes available within the target while citation-sensitive actions stay locked.

### Phase 3 — manuscript-centered workspace

**Status: complete.**

- Typed Paper AST projection in the frontend.
- Structured sections, citation anchors, quality summary, contextual tabs, and optional PDF split.
- Progressive pipeline and retry controls.

**Acceptance:** researchers can inspect what was parsed, including partial and unresolved citations.

### Phase 4 — complete peer review

**Status: complete.**

- Existing claim/citation pair extraction, embedding priority, batched verification, and anchored classifications.
- Unified review inbox and progressive findings alongside the existing missing-work pipeline.

**Acceptance:** both required review lanes are grounded in linkable OpenAlex/Semantic Scholar evidence; unavailable evidence is `unverifiable`.

### Phase 5 — constrained editing and revisions

**Status: complete.**

- One mode-free agent chat, typed operation schema, all-version agent tools, invariant validator, inline diff projection, explicit Approve/Discard actions, and immutable history.
- Convert accepted source candidates into citation/bibliography edit proposals.
- Support exact historical revision restore and targeted undo of a specific older operation without discarding later unrelated work.

**Acceptance:** a natural-language command can safely shorten a section and add a verified citation without silently losing existing citations.

### Phase 6 — CSL and export

**Status: complete.**

- Style confirmation, CSL processor, LaTeX renderer/compiler, warning model, and MinIO export downloads.

**Acceptance:** an approved revision exports as both an editable LaTeX project and compiled PDF with stable citations and bibliography.

### Phase 7 — hardening and submission evidence

**Status: engineering and evidence complete; the final browser recording is a manual submission artifact.**

- Independent stage retries, 80-page policy, metrics, error copy, performance measurement, system-design diagrams, known limitations, AI-use note, and real-paper recording.

The user authorized a complete endpoint smoke test. All 37 OpenAPI operations were exercised with real paper state; the exact record, timings, edit invariants, export artifact checks, and defects fixed during the run are in `SMOKE_RESULTS.md`. The frontend production build, backend compile, Docker build, migration head, and service health checks also pass. The remaining human submission action is recording the scripted browser walkthrough in `SUBMISSION.md`.

## Deployment discipline

- Application code reaches Railway only through commits pushed to the connected Git repository.
- Railway CLI is reserved for MinIO/database/service configuration, variables, logs, status, and diagnostics.
- Database migrations run before application instances begin using new lifecycle columns.
- New variables are first added as non-breaking optional configuration; production references are wired before the Git deployment that makes them required.
