# Submission guide and evidence

## Assessment coverage

| Requirement | Implemented evidence |
| --- | --- |
| PDF structure and citation parsing | Typed Paper AST, raw TEI artifact, stable anchors, unresolved-state projection, extraction quality report |
| Missing-citation peer review | Two-lane claim discovery, exact source spans, OpenAlex/Semantic Scholar search, provider-grounded support verification |
| Existing citation audit | Exact claim/citation pairs, cosine prioritization, evidence-only four-way classification, provider links |
| Natural-language editing | One mode-free agent thread, typed operation planning, invariant validation, inline diff, and explicit Approve/Discard actions |
| Safe citation insertion | Verified candidate becomes an `insert_citation` proposal with provider-derived CSL; no immediate mutation |
| Revision control | Immutable snapshots, conflict checks, all-version agent tools, compare, full restore, and targeted non-latest undo |
| Citation style | Confirmation UI and real `citeproc-py` processing from canonical CSL-JSON |
| Export | Editable LaTeX ZIP and compiled PDF, both revision-specific, with explicit fidelity warnings |
| Responsive UX | Immediate local PDF, durable async upload, provisional Quick Read, progressive pipeline/review polling |
| Reliability | PostgreSQL-backed queues, stable job IDs, failed-job recovery after deploys, incremental commits, independent retries, manual retry |
| Large papers | Whole-document review limit at 80 pages and section-scoped review of at most five sections |
| System design | `SYSTEM_DESIGN.md` documents boundaries, algorithms, invariants, failures, security, and scaling |

## Recommended recording script

Record one uninterrupted workflow using a born-digital sample paper:

1. Show the upload warning and select `sample_papers/attention-is-all-you-need.pdf`.
2. Show the PDF immediately, then the durable `/papers/{id}` URL and processing stages.
3. Ask a broad question as soon as **Quick read · provisional** appears; point out the provisional label and locked citation-sensitive tools.
4. Wait for the authoritative structured manuscript and show extraction quality, a resolved inline citation, and an unresolved/partial state if the sample contains one.
5. Open Review and show both a missing-citation finding and an existing claim/citation classification with provider evidence.
6. Open a finding in the manuscript, inspect a verified source, choose **Use source**, and review the unapplied citation diff in the focused approval modal.
7. Approve the citation proposal and show the new immutable revision.
8. In the Agent chat, ask it to shorten an introduction paragraph, inspect and approve the inline diff, then ask the same agent to undo a specific older change while retaining newer work.
9. Confirm a CSL style, export the current revision, download the LaTeX ZIP and compiled PDF, and show the reconstruction warnings.
10. Finish on Export to show the revision-specific LaTeX and PDF artifacts.

Do not hide slow or failed stages in the recording. A failed provider result or an `unverifiable` citation is useful evidence that uncertainty is represented honestly.

## Capture checklist

- Browser URL shows durable paper ID.
- Quick Read label and authoritative promotion are both visible.
- Structured manuscript and optional PDF split are visible.
- Missing and existing citation lanes are visible.
- At least one finding is anchored back to the manuscript.
- Provider URL, evidence, and confidence are visible.
- Proposal diff is visible before approval.
- Revision number changes only after approval.
- LaTeX ZIP and PDF downloads complete.

## AI-use disclosure

AI coding assistance was used to help design, implement, refactor, and document this assessment. Model calls are also part of the product for grounded chat, claim discovery, claim/source support judgment, and constrained edit planning. Deterministic application code—not model output—owns PDF validation, AST parsing, provider identity, exact-span checks, citation and structure invariants, human approval, persistence, and export compilation. All model outputs cross typed validation boundaries before they can become durable product state.

## Known limitations

- Authentication, tenant isolation, deletion/retention workflows, and confidential-document handling are intentionally outside this assessment scope.
- Quick Read quality depends on selectable PDF text and is deliberately not citation-safe.
- GROBID and OCR can still lose complex math, tables, figures, reading order, or typography; the export reports this instead of claiming visual fidelity.
- Citation-support judgments are limited by provider abstract availability. Full-text source verification is not implemented; absent evidence becomes `unverifiable`.
- OpenAlex is the primary bibliography enrichment source. Both OpenAlex and Semantic Scholar participate in missing-source discovery and deduplication.
- The automatic whole-document model review limit is 80 pages. Larger papers require section selection.
- One worker process currently hosts all queue consumers. Production scale should split worker types and tune their independent concurrency/resource classes.
- UUID routes are convenient demo identifiers, not access control.

## Validation record

The complete per-operation runtime record is in [`SMOKE_RESULTS.md`](SMOKE_RESULTS.md).

| Check | Result |
| --- | --- |
| Backend Python compile | Passed: `python3 -m compileall -q app` |
| Frontend production build | Passed: Vite transformed 5,624 modules and `tsc -b` completed |
| Whitespace/conflict-marker audit | Passed: `git diff --check`; no conflict markers found |
| Non-Phosphor icon-source audit | Passed: no Heroicons, Lucide, or Iconoir source/package references |
| Docker image build | Passed for API and worker images |
| Alembic head on local PostgreSQL | Passed: `20260815_07 (head)`; migration service exited 0 |
| API/worker/GROBID/MinIO health | Passed: API, PostgreSQL, MinIO, and GROBID healthy; worker running |
| Real sample upload + stage timings | Passed: Quick Read about 2.59 s; authoritative GROBID parse 11.399 s |
| Edit/history runtime | Passed: propose, approve, non-latest targeted undo, full restore, and direct selective revert |
| CSL LaTeX/PDF runtime export | Passed: valid four-file ZIP and 17-page PDF downloaded |
| OpenAPI operation smoke test | Passed: all 37 operations exercised with expected JSON/binary/SSE types |

The user explicitly authorized an all-endpoint smoke test. No synthetic test suite was added; validation used production builds, static compilation, migrations, service health, and real vertical runtime behavior.
