from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from app.schemas.paper import Paper
from app.services.csl_rendering import CitationRenderer, PandocCSLRenderer


@dataclass(frozen=True)
class GeneratedPaperExport:
    latex_bundle: bytes
    pdf: bytes
    warnings: list[str]
    compiler_output: str


class CSLPaperExporter:
    """Render canonical CSL-JSON through Pandoc citeproc and compile its LaTeX."""

    def __init__(self, renderer: CitationRenderer | None = None) -> None:
        self._renderer = renderer or PandocCSLRenderer()

    def generate(self, paper: Paper, style_id: str) -> GeneratedPaperExport:
        rendered = self._renderer.render_document(paper, style_id)
        missing_csl = [reference.id for reference in paper.references if reference.csl is None]
        warnings = list(rendered.warnings)
        if missing_csl:
            warnings.append(
                f"{len(missing_csl)} references lacked CSL-JSON and were preserved only "
                f"where their raw marker appeared: {', '.join(missing_csl[:12])}."
            )
        pdf, compiler_output = compile_latex(rendered.latex)
        bundle = build_bundle(
            rendered.latex,
            rendered.references_json,
            rendered.style,
            style_id,
            warnings,
        )
        return GeneratedPaperExport(bundle, pdf, list(dict.fromkeys(warnings)), compiler_output)


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
    references_json: bytes,
    style: bytes,
    style_id: str,
    warnings: list[str],
) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("main.tex", latex)
        archive.writestr("references.json", references_json)
        archive.writestr(f"styles/{style_id}.csl", style)
        archive.writestr(
            "README.txt",
            "This editable LaTeX project was reconstructed from a PDF Paper AST.\n\n"
            + "Warnings:\n"
            + "\n".join(f"- {warning}" for warning in warnings),
        )
    return output.getvalue()
