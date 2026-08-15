# API smoke-test record

Run date: 2026-08-15 (local Docker Compose stack)

The OpenAPI document exposes 37 operations. Every operation was exercised against the running API with real BERT paper state. The primary durable paper was `e75a807a-9d63-45d4-88c5-c1048b4360d7`; mutation checks used immutable manuscript revisions so their effects were directly comparable.

## Results

| # | Operation | Result and evidence |
| ---: | --- | --- |
| 1 | `GET /hello` | `200 application/json`; health payload returned. |
| 2 | `POST /papers` | `202 application/json` in 0.075 s; 775,166-byte BERT PDF persisted with a durable paper ID. |
| 3 | `POST /papers/normalize` | `200 application/json` in 0.034 s; BERT TEI normalized to 29 sections and 55 references. |
| 4 | `POST /papers/parse` | `200 application/json` in 3.576 s after the persistence-order fix; returned Paper JSON with 29 sections and 58 references. |
| 5 | `POST /papers/enrich` | `200 application/json` in 2.295 s; 36 matched, 18 unmatched, and one provider error were represented explicitly. |
| 6 | `POST /papers/missing-works` | `200 application/json` in 4.228 s; returned four query outcomes, findings, and warnings without fabricated sources. |
| 7 | `GET /papers/{paper_id}` | `200 application/json`; lifecycle, authoritative Paper AST, manuscript revision, and retrieval mode returned. |
| 8 | `GET /papers/{paper_id}/source` | `200 application/pdf`; source size matched the uploaded 775,166-byte PDF. |
| 9 | `GET /papers/artifacts/{artifact_id}/tei` | `200 application/tei+xml`; 207,717-byte immutable TEI downloaded. |
| 10 | `POST /papers/{paper_id}/index` | `202 application/json`; idempotent repeat truthfully returned `status=completed`. |
| 11 | `GET /papers/{paper_id}/pipeline` | `200 application/json`; all nine stages reached `completed` with `error=null`. |
| 12 | `GET /papers/{paper_id}/jobs` | `200 application/json`; quick-read, parse, index, OpenAlex, and citation-audit jobs all reported completed with no stale errors. |
| 13 | `POST /papers/{paper_id}/pipeline/{stage}/retry` | A genuinely failed stage returned `202` and recovered; retrying an already completed stage returned the expected `409 application/json`. |
| 14 | `POST /papers/{paper_id}/enrichments/openalex` | `202 application/json`; idempotent response reported the existing completed job. |
| 15 | `GET /papers/{paper_id}/enrichments/openalex` | `200 application/json`; 58 references accounted for: 38 matched, 17 unmatched, two skipped, one failed. |
| 16 | `POST /papers/{paper_id}/citation-audit` | `202 application/json`; existing completed audit resumed pending source fulfillment. |
| 17 | `GET /papers/{paper_id}/citation-audit` | `200 application/json`; audit completed and all 24 original source searches reached terminal state (`sourceSearchPending=0`). |
| 18 | `POST /papers/{paper_id}/citation-audit/findings/{finding_id}/candidates/{candidate_id}/decision` | Both branches passed. Rejecting a real pending candidate returned `editProposal=null`; accepting a genuinely verified candidate returned one valid `insert_citation` proposal. The paper and manuscript revision remained byte-for-byte unchanged before approval. |
| 19 | `POST /papers/{paper_id}/citation-audit/findings/{finding_id}/feedback` | `201 application/json`; `needs_review` feedback persisted with an actor and note. |
| 20 | `GET /papers/{paper_id}/citation-audit/feedback` | `200 application/json`; summary reflected both decision and review feedback. |
| 21 | `GET /papers/{paper_id}/claim-citation-review` | `200 application/json`; 89/89 exact claim/citation findings returned with a completed status. |
| 22 | `POST /papers/{paper_id}/section-review` | `202 application/json`; one-section missing/existing citation review completed. Repeating the same scope returned `status=completed` and left both pipeline stages completed. |
| 23 | `POST /papers/{paper_id}/edits` | `200 application/json` in 2.288 s; “make the abstract a little shorter” produced one valid `replace_text` proposal and did not mutate the manuscript. |
| 24 | `GET /papers/{paper_id}/edits/latest` | `200 application/json`; latest proposal and its validation state returned. |
| 25 | `GET /papers/{paper_id}/edits/{proposal_id}` | `200 application/json`; exact proposal and operation diff returned. |
| 26 | `POST /papers/{paper_id}/edits/{proposal_id}/approve` | Both operation classes passed. Text approval created revision 2 and shortened the abstract; verified `insert_citation` approval atomically added one citation and one CSL reference. A later approved `remove_citation` inverse created a new revision whose Paper AST exactly matched the pre-insertion snapshot. |
| 27 | `GET /papers/{paper_id}/revisions` | `200 application/json`; all immutable parse/edit/revert/restore revisions and approved operations returned. |
| 28 | `GET /papers/{paper_id}/revisions/{revision}` | `200 application/json`; complete historical Paper AST returned. |
| 29 | `POST /papers/{paper_id}/revisions/{revision}/restore` | `200 application/json`; restoring revision 3 created revision 6 with an exact historical snapshot. |
| 30 | `POST /papers/{paper_id}/revisions/{revision}/revert` | `200 application/json`; reverting one non-latest revision-3 operation created revision 7 while preserving the full citation identity set. |
| 31 | `GET /papers/{paper_id}/citation-style` | `200 application/json`; detected family and installed CSL candidates returned. |
| 32 | `PUT /papers/{paper_id}/citation-style` | `200 application/json`; APA was confirmed. An unavailable style returned the expected `422 application/json`. |
| 33 | `POST /papers/{paper_id}/exports` | `202 application/json`; revision-7 APA export queued. |
| 34 | `GET /papers/{paper_id}/exports/{export_id}` | `200 application/json`; final export reached `completed` with both download URLs and an explicit reconstruction warning. |
| 35 | `GET /papers/{paper_id}/exports/{export_id}/download/{format}` | Both variants passed: LaTeX returned `200 application/zip` (34,976 bytes, four valid files) and PDF returned `200 application/pdf` (154,170 bytes, 17 pages, PDF 1.7). |
| 36 | `POST /chat` | `200 text/event-stream` in 8.253 s; emitted tool calls for revision list/detail, grounded answer text, and `RUN_FINISHED` with no `RUN_ERROR`. |
| 37 | `GET /chat/{thread_id}` | `200 application/json`; the user and assistant messages from the streamed run were persisted. |

## Edit and history invariants

The mutation smoke test went beyond the happy path:

- Abstract shortening created revision 2 only after explicit approval.
- An unrelated Introduction edit created revision 3.
- A natural-language request to undo only the revision-2 abstract change created revision 4; the abstract exactly matched revision 1 while the later Introduction edit still exactly matched revision 3.
- A natural-language full restore created revision 5 whose complete Paper JSON exactly matched revision 2.
- Direct restore and selective-revert endpoints then created revisions 6 and 7; citation node identities were unchanged by the selective text revert.
- A verified source created a valid citation proposal without mutation. Approval added exactly one citation and bibliography item; asking the agent to undo that exact operation ID produced a valid `remove_citation` proposal, and approval restored the original Paper AST exactly in another immutable revision.

## Defects found and fixed during the run

- Synchronous parse inserted a manuscript revision before its new parent paper because the models have no ORM relationship. The repository now flushes the paper first; the same PDF now returns `200 application/json`.
- Source-search jobs exhausted under an earlier invalid strict schema and remained permanently queued. The idempotent enqueuer now reprocesses jobs from an older search version with reset attempt counters, while current-version failures remain terminal; all pending findings recovered.
- `pdflatex` output contained non-UTF-8 bytes. Compiler output now decodes with replacement instead of crashing the export worker.
- Extracted academic text contained Unicode mathematical symbols unsupported by `pdflatex`. The renderer now emits safe LaTeX equivalents; the real BERT export compiles.
- Completed queue jobs leaked historical `failedReason` values and the index start route always claimed `queued`. Public status now reflects current state and only exposes errors for failed jobs.
- Scoped review progress could report fewer total pairs than persisted findings. The projection now maintains `completed <= total`.
- The model could understand an explicit historical citation-undo command yet omit the operation ID from its structured field. Durable operation IDs written in an undo command are now matched deterministically against known history; the exact citation inverse passed through approval.
- Unexpected server errors now use a stable JSON error envelope, preventing the HTML/plain-text response class that originally appeared in deployment.

## Performance observed

| Milestone | Observed |
| --- | ---: |
| Durable upload response | 0.075 s |
| Quick extraction | 0.238 s |
| Provisional index | 2.355 s |
| Quick Read ready | about 2.59 s |
| Authoritative GROBID parse | 11.399 s |
| Authoritative index | 3.232 s |
| Reference resolution | 4.173 s |
| Missing-citation review | 21.472 s |

These measurements are from a warm local Compose environment and are evidence, not production latency guarantees.
