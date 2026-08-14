"""Parse sample PDFs through GROBID and print a quality report."""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import httpx

from app.schemas.paper import CitationNode, Paper
from app.services.tei_parser import parse_tei

PAPERS_DIR = Path(os.environ.get("SAMPLE_PAPERS_DIR", "/tmp/sample_papers"))
OUT_DIR = Path(os.environ.get("PARSE_OUT_DIR", "/tmp/parse_out"))
GROBID_URL = os.environ.get("GROBID_URL", "http://grobid:8070")
TIMEOUT = 300.0


def grobid_fulltext(pdf: bytes, filename: str) -> bytes:
    with httpx.Client(base_url=GROBID_URL, timeout=TIMEOUT) as client:
        response = client.post(
            "/api/processFulltextDocument",
            files={"input": (filename, pdf, "application/pdf")},
            data={
                "consolidateHeader": "0",
                "consolidateCitations": "0",
                "includeRawCitations": "1",
            },
        )
        response.raise_for_status()
        return response.content


def flatten_citations(paper: Paper) -> list[CitationNode]:
    return [
        node
        for section in paper.sections
        for paragraph in section.paragraphs
        for node in paragraph.nodes
        if isinstance(node, CitationNode)
    ]


def report(name: str, paper: Paper) -> dict:
    citations = flatten_citations(paper)
    status_counts = Counter(reference.status for reference in paper.references)
    cited_ids = {source_id for node in citations for source_id in node.source_ids}
    known_ids = {reference.id for reference in paper.references}
    empty_citation_text = sum(1 for node in citations if not node.raw_text.strip())
    unresolved_fragments = [
        fragment for node in citations for fragment in node.unresolved_fragments
    ]
    untitled = [section.title for section in paper.sections if section.title == "Untitled section"]
    missing_title = sum(1 for reference in paper.references if not (reference.csl and reference.csl.title))
    missing_author = sum(1 for reference in paper.references if not (reference.csl and reference.csl.author))
    missing_date = sum(1 for reference in paper.references if not (reference.csl and reference.csl.issued))

    summary = {
        "file": name,
        "title": paper.title,
        "has_abstract": bool(paper.abstract),
        "abstract_chars": len(paper.abstract or ""),
        "sections": len(paper.sections),
        "section_titles": [section.title for section in paper.sections],
        "paragraphs": sum(len(section.paragraphs) for section in paper.sections),
        "citation_nodes": len(citations),
        "cited_ids": len(cited_ids),
        "references": len(paper.references),
        "status": dict(status_counts),
        "unresolved_reference_ids": paper.unresolved_reference_ids,
        "unresolved_fragments": unresolved_fragments,
        "empty_citation_text": empty_citation_text,
        "untitled_sections": len(untitled),
        "refs_missing_title": missing_title,
        "refs_missing_author": missing_author,
        "refs_missing_date": missing_date,
        "cited_not_in_bibl": sorted(cited_ids - known_ids),
        "bibl_never_cited": sorted(known_ids - cited_ids),
        "sample_citations": [
            {
                "id": node.id,
                "rawText": node.raw_text,
                "items": [
                    item.model_dump(by_alias=True, exclude_none=True)
                    for item in node.items
                ],
                "anchor": (
                    node.anchor.model_dump(by_alias=True)
                    if node.anchor
                    else None
                ),
                "form": node.form,
                "resolution": node.resolution.model_dump(by_alias=True),
                "unresolvedFragments": node.unresolved_fragments,
                "warnings": node.warnings,
            }
            for node in citations[:12]
        ],
        "failed_or_partial": [
            {
                "id": reference.id,
                "status": reference.status,
                "rawText": reference.raw_text[:180],
                "warnings": reference.warnings,
                "csl": reference.csl.model_dump(by_alias=True, exclude_none=True) if reference.csl else None,
            }
            for reference in paper.references
            if reference.status != "parsed"
        ],
    }
    return summary


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(PAPERS_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {PAPERS_DIR}", file=sys.stderr)
        return 1

    reports = []
    for pdf_path in pdfs:
        print(f"\n=== {pdf_path.name} ===", flush=True)
        pdf = pdf_path.read_bytes()
        tei = grobid_fulltext(pdf, pdf_path.name)
        (OUT_DIR / f"{pdf_path.stem}.tei.xml").write_bytes(tei)
        paper = parse_tei(tei)
        payload = paper.model_dump(by_alias=True)
        (OUT_DIR / f"{pdf_path.stem}.json").write_text(json.dumps(payload, indent=2))
        summary = report(pdf_path.name, paper)
        reports.append(summary)
        print(json.dumps({k: v for k, v in summary.items() if k not in {"failed_or_partial", "sample_citations", "section_titles"}}, indent=2))
        print("section_titles:", summary["section_titles"])
        print("sample_citations:", json.dumps(summary["sample_citations"], indent=2))
        print("failed_or_partial count:", len(summary["failed_or_partial"]))
        for item in summary["failed_or_partial"][:15]:
            print(" ", item["id"], item["status"], item["warnings"], item["rawText"][:120])

    (OUT_DIR / "summary.json").write_text(json.dumps(reports, indent=2))
    print(f"\nWrote reports to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
