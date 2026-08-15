from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from citeproc import (
    Citation,
    CitationItem as ProcessorCitationItem,
    CitationStylesBibliography,
    CitationStylesStyle,
    formatter,
)
from citeproc.source.json import CiteProcJSON
from citeproc_styles import get_style_filepath

from app.schemas.paper import CitationNode, Paper, TextNode


@dataclass(frozen=True)
class GeneratedPaperExport:
    latex_bundle: bytes
    pdf: bytes
    warnings: list[str]
    compiler_output: str


class CSLPaperExporter:
    """Render canonical CSL-JSON through citeproc, then build a semantic LaTeX project."""

    def generate(self, paper: Paper, style_id: str) -> GeneratedPaperExport:
        style_path = Path(get_style_filepath(style_id))
        if not style_path.is_file():
            raise ValueError(f"The CSL style '{style_id}' is unavailable.")
        csl_items = [
            reference.csl.model_dump(mode="json", by_alias=True, exclude_none=True)
            for reference in paper.references
            if reference.csl is not None
        ]
        warnings = [
            "The export reconstructs semantic structure from PDF extraction; original figures, equations, page layout, and typography may need manual restoration."
        ]
        missing_csl = [reference.id for reference in paper.references if reference.csl is None]
        if missing_csl:
            warnings.append(
                f"{len(missing_csl)} references lacked CSL-JSON and were omitted from styled rendering: {', '.join(missing_csl[:12])}."
            )
        source = CiteProcJSON(csl_items)
        style = CitationStylesStyle(str(style_path), validate=False)
        bibliography = CitationStylesBibliography(style, source, formatter.plain)
        known_ids = {str(item["id"]) for item in csl_items}
        citations: dict[int, Citation] = {}
        for node in citation_nodes(paper):
            ids = [item.source_id for item in node.items if item.source_id in known_ids]
            if not ids:
                continue
            citation = Citation([ProcessorCitationItem(source_id) for source_id in ids])
            citations[id(node)] = citation
            bibliography.register(citation)

        def warn(item: object) -> None:
            warnings.append(f"CSL could not resolve a citation item: {item}.")

        rendered: dict[int, str] = {}
        for node in citation_nodes(paper):
            citation = citations.get(id(node))
            if citation is None:
                rendered[id(node)] = node.raw_text
                continue
            value = bibliography.cite(citation, warn)
            rendered[id(node)] = flatten_citeproc(value) or node.raw_text
        rendered_bibliography = [flatten_citeproc(item) for item in bibliography.bibliography()]
        latex = render_latex(paper, rendered, rendered_bibliography, style_id)
        pdf, compiler_output = compile_latex(latex)
        bundle = build_bundle(
            latex,
            csl_items,
            style_path.read_bytes(),
            style_id,
            warnings,
        )
        return GeneratedPaperExport(bundle, pdf, list(dict.fromkeys(warnings)), compiler_output)


def citation_nodes(paper: Paper) -> list[CitationNode]:
    return [
        node
        for section in paper.sections
        for paragraph in section.paragraphs
        for node in paragraph.nodes
        if isinstance(node, CitationNode)
    ]


def flatten_citeproc(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "".join(flatten_citeproc(item) for item in value)
    return str(value)


def render_latex(
    paper: Paper,
    citations: dict[int, str],
    bibliography: list[str],
    style_id: str,
) -> str:
    authors = ", ".join(
        name.literal or " ".join(part for part in [name.given, name.family] if part)
        for name in paper.authors
    )
    body: list[str] = []
    if paper.abstract:
        body.extend(["\\begin{abstract}", latex_escape(paper.abstract), "\\end{abstract}"])
    for section in paper.sections:
        body.append(f"\\section{{{latex_escape(section.title)}}}")
        for paragraph in section.paragraphs:
            parts = [
                latex_escape(node.text)
                if isinstance(node, TextNode)
                else latex_escape(citations.get(id(node), node.raw_text))
                for node in paragraph.nodes
            ]
            body.append("".join(parts) + "\n")
    body.extend(["\\section*{References}", "\\begin{enumerate}"])
    body.extend(f"\\item {latex_escape(item)}" for item in bibliography if item)
    body.append("\\end{enumerate}")
    return "\n".join(
        [
            "\\documentclass[11pt]{article}",
            "\\usepackage[T1]{fontenc}",
            "\\usepackage[utf8]{inputenc}",
            "\\usepackage[margin=1in]{geometry}",
            "\\usepackage[hidelinks]{hyperref}",
            f"% Citations and bibliography rendered with CSL style: {style_id}",
            f"\\title{{{latex_escape(paper.title)}}}",
            f"\\author{{{latex_escape(authors)}}}",
            "\\date{}",
            "\\begin{document}",
            "\\maketitle",
            *body,
            "\\end{document}",
            "",
        ]
    )


def latex_escape(value: str) -> str:
    substitutions = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    escaped = re.sub(
        r"[\\&%$#_{}~^]",
        lambda match: substitutions[match.group(0)],
        value,
    )
    unicode_substitutions = {
        "×": r"$\times$",
        "ŝ": r"\^{s}",
        "β": r"$\beta$",
        "τ": r"$\tau$",
        "–": "--",
        "•": r"\textbullet{}",
        "∅": r"$\emptyset$",
        "∈": r"$\in$",
        "≤": r"$\leq$",
        "≥": r"$\geq$",
    }
    return "".join(unicode_substitutions.get(character, character) for character in escaped)


def compile_latex(latex: str) -> tuple[bytes, str]:
    executable = shutil.which("pdflatex")
    if executable is None:
        raise RuntimeError("PDF export requires pdflatex on the worker service.")
    with tempfile.TemporaryDirectory(prefix="paper-export-") as directory:
        root = Path(directory)
        (root / "main.tex").write_text(latex, encoding="utf-8")
        outputs: list[str] = []
        for _pass in range(2):
            result = subprocess.run(
                [executable, "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
                cwd=root,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            outputs.extend([result.stdout, result.stderr])
            if result.returncode != 0:
                raise RuntimeError("LaTeX compilation failed: " + result.stdout[-1_500:])
        output = root / "main.pdf"
        if not output.is_file():
            raise RuntimeError("LaTeX compilation did not produce a PDF.")
        return output.read_bytes(), "\n".join(outputs)


def build_bundle(
    latex: str,
    references: list[dict],
    style: bytes,
    style_id: str,
    warnings: list[str],
) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("main.tex", latex)
        archive.writestr("references.json", json.dumps(references, ensure_ascii=False, indent=2))
        archive.writestr(f"styles/{style_id}.csl", style)
        archive.writestr(
            "README.txt",
            "This editable LaTeX project was reconstructed from a PDF Paper AST.\n\n"
            + "Warnings:\n"
            + "\n".join(f"- {warning}" for warning in warnings),
        )
    return output.getvalue()
