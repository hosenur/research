from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from citeproc_styles import get_style_filepath

from app.schemas.paper import CitationItem, CitationNode, Paper, TextNode


@dataclass(frozen=True)
class RenderedCSLDocument:
    latex: str
    references_json: bytes
    style: bytes
    warnings: list[str]


class CitationRenderer(Protocol):
    def render_marker(
        self,
        paper: Paper,
        citation: CitationNode,
        style_id: str,
    ) -> str: ...

    def render_document(self, paper: Paper, style_id: str) -> RenderedCSLDocument: ...


class PandocCSLRenderer:
    """Render canonical CSL-JSON without application-owned citation templates."""

    def __init__(self, executable: str | None = None) -> None:
        self._executable = executable or shutil.which("pandoc") or "pandoc"

    def render_marker(
        self,
        paper: Paper,
        citation: CitationNode,
        style_id: str,
    ) -> str:
        references = csl_references(paper)
        missing = [item.source_id for item in citation.items if item.source_id not in references]
        if missing:
            raise ValueError(
                "CSL-JSON is unavailable for citation source(s): " + ", ".join(missing)
            )
        markdown = citation_markdown(citation)
        with tempfile.TemporaryDirectory(prefix="csl-marker-") as directory:
            root = Path(directory)
            references_path = root / "references.json"
            references_path.write_text(
                json.dumps(list(references.values()), ensure_ascii=False),
                encoding="utf-8",
            )
            result = self._run(
                [
                    "--from=markdown+citations",
                    "--to=plain",
                    "--citeproc",
                    f"--csl={style_path(style_id)}",
                    f"--bibliography={references_path}",
                    "--metadata=suppress-bibliography:true",
                    "--wrap=none",
                ],
                markdown,
            )
        marker = " ".join(result.split()).strip()
        if not marker:
            raise RuntimeError(
                f"The CSL processor returned an empty marker for style '{style_id}'."
            )
        return marker

    def render_document(self, paper: Paper, style_id: str) -> RenderedCSLDocument:
        references = csl_references(paper)
        references_json = json.dumps(
            list(references.values()),
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        warnings: list[str] = []
        markdown = paper_markdown(paper, references, warnings)
        selected_style = style_path(style_id)
        metadata = {
            "title": paper.title,
            "author": [display_name(author) for author in paper.authors],
            "abstract": paper.abstract or "",
            "link-citations": True,
            "nocite": "@*",
        }
        with tempfile.TemporaryDirectory(prefix="csl-document-") as directory:
            root = Path(directory)
            references_path = root / "references.json"
            metadata_path = root / "metadata.json"
            references_path.write_bytes(references_json)
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False),
                encoding="utf-8",
            )
            latex = self._run(
                [
                    "--from=markdown+citations",
                    "--to=latex",
                    "--standalone",
                    "--citeproc",
                    f"--csl={selected_style}",
                    f"--bibliography={references_path}",
                    f"--metadata-file={metadata_path}",
                    "--wrap=none",
                ],
                markdown,
            )
        if not latex.strip():
            raise RuntimeError("Pandoc returned an empty LaTeX document.")
        return RenderedCSLDocument(
            latex=latex,
            references_json=references_json,
            style=selected_style.read_bytes(),
            warnings=list(dict.fromkeys(warnings)),
        )

    def _run(self, arguments: list[str], input_text: str) -> str:
        try:
            result = subprocess.run(
                [self._executable, *arguments],
                input=input_text,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Pandoc is required for CSL citation rendering but is unavailable."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("CSL citation rendering timed out.") from exc
        if result.returncode != 0:
            detail = result.stderr.strip()[-2_000:]
            raise RuntimeError(f"CSL citation rendering failed: {detail}")
        return result.stdout


def style_path(style_id: str) -> Path:
    path = Path(get_style_filepath(style_id))
    if not path.is_file():
        raise ValueError(f"The CSL style '{style_id}' is unavailable.")
    return path


def csl_references(paper: Paper) -> dict[str, dict]:
    return {
        reference.id: reference.csl.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        for reference in paper.references
        if reference.csl is not None
    }


def paper_markdown(
    paper: Paper,
    references: dict[str, dict],
    warnings: list[str],
) -> str:
    blocks: list[str] = []
    for section in paper.sections:
        blocks.append(f"# {markdown_escape(section.title)}")
        for paragraph in section.paragraphs:
            parts: list[str] = []
            for node in paragraph.nodes:
                if isinstance(node, TextNode):
                    parts.append(markdown_escape(node.text))
                    continue
                missing = [
                    item.source_id
                    for item in node.items
                    if item.source_id not in references
                ]
                if missing or not node.items:
                    parts.append(markdown_escape(node.raw_text))
                    warnings.append(
                        "An unresolved citation marker was preserved verbatim: "
                        + (node.raw_text or ", ".join(missing))
                    )
                    continue
                parts.append(citation_markdown(node))
            blocks.append("".join(parts).strip())
    return "\n\n".join(blocks) + "\n"


def citation_markdown(citation: CitationNode) -> str:
    if not citation.items:
        raise ValueError("A CSL citation marker requires at least one citation item.")
    if citation.form == "narrative" and len(citation.items) == 1:
        item = citation.items[0]
        return citation_token(item, author_in_text=True)
    if any(item.author_only for item in citation.items):
        if len(citation.items) != 1:
            raise ValueError("Author-only CSL citations cannot be rendered as a cluster.")
        return citation_token(citation.items[0], author_in_text=True)
    return "[" + "; ".join(citation_token(item) for item in citation.items) + "]"


def citation_token(item: CitationItem, *, author_in_text: bool = False) -> str:
    if not re.fullmatch(r"[^\s@,;\[\]]+", item.source_id):
        raise ValueError(f"Citation source id '{item.source_id}' is not CSL-safe.")
    prefix = citation_affix(item.prefix)
    cite = f"@{item.source_id}"
    if item.suppress_author and not author_in_text:
        cite = f"-@{item.source_id}"
    suffix_parts: list[str] = []
    if item.locator:
        label = locator_label(item.label)
        suffix_parts.append(f"{label} {citation_affix(item.locator)}".strip())
    if item.suffix:
        suffix_parts.append(citation_affix(item.suffix))
    suffix = f", {', '.join(suffix_parts)}" if suffix_parts else ""
    return " ".join(part for part in [prefix, f"{cite}{suffix}"] if part).strip()


def locator_label(label: str | None) -> str:
    labels = {
        "page": "p.",
        "chapter": "chap.",
        "section": "sec.",
        "paragraph": "para.",
        "volume": "vol.",
        "issue": "no.",
        "figure": "fig.",
    }
    return labels.get((label or "page").casefold(), label or "p.")


def citation_affix(value: str | None) -> str:
    return re.sub(r"[\[\];]", " ", value or "").strip()


def markdown_escape(value: str) -> str:
    return re.sub(r"([\\`*{}\[\]<>#_])", r"\\\1", value)


def display_name(name: object) -> str:
    literal = getattr(name, "literal", None)
    if literal:
        return str(literal)
    return " ".join(
        part
        for part in [getattr(name, "given", None), getattr(name, "family", None)]
        if part
    )
