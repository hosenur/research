"""Create a small, self-contained PDF fixture for citation-audit development.

The PDF deliberately mixes cited and uncited claims. The bibliography contains
real papers, so source search can resolve the omitted citations against them.
This avoids requiring a PDF-generation dependency in the application image.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT = 54
TOP = 744
BOTTOM = 54
FONT_SIZE = 10
LEADING = 14
CONTENT_WIDTH = 88


DOCUMENT: list[tuple[str, str]] = [
    ("title", "Evaluating Retrieval-Augmented Language Models"),
    ("subtitle", "A citation-audit fixture built from real research literature"),
    ("authors", "Mira Sen, Daniel Ortiz, and the Research Systems Group"),
    ("abstract", "Abstract"),
    (
        "body",
        "Retrieval-augmented language models combine a parametric generator with "
        "an external non-parametric memory. They are particularly useful when a "
        "system must answer questions about information that changes over time. "
        "The experiments and bibliography in this document are based on real "
        "research papers, but several supporting citations have intentionally "
        "been removed to create a missing-citation audit fixture.",
    ),
    ("heading", "1 Introduction"),
    (
        "body",
        "The Transformer architecture replaces recurrence with attention and is "
        "more parallelizable during training [1]. This design made it practical "
        "to train increasingly large language representations.",
    ),
    (
        "body",
        "Retrieval-augmented generation combines a pre-trained sequence-to-sequence "
        "model with a dense vector index and improves performance on knowledge-" 
        "intensive question answering tasks.",
    ),
    (
        "body",
        "Bidirectional pre-training lets an encoder condition on both left and right "
        "context, which supports strong transfer across language-understanding "
        "tasks [2].",
    ),
    (
        "body",
        "A retrieval layer can also provide provenance for generated statements, "
        "making factual errors easier to inspect.",
    ),
    ("heading", "2 Related Work"),
    (
        "body",
        "Residual learning reformulates a deep network as a stack of residual "
        "functions and makes substantially deeper models easier to optimize.",
    ),
    (
        "body",
        "RoBERTa demonstrated that training duration, batch size, masking strategy, "
        "and data volume materially affect the measured quality of masked-language "
        "pre-training [5].",
    ),
    (
        "body",
        "Dense Passage Retrieval uses a dual-encoder retriever to identify passages "
        "for open-domain question answering.",
    ),
    (
        "body",
        "The Adam optimizer combines momentum-like first-moment estimates with a "
        "second-moment normalization and is commonly used for transformer training.",
    ),
    ("heading", "3 Evaluation Protocol"),
    (
        "body",
        "We compare a parametric-only baseline with a retrieval-augmented variant. "
        "Both systems use the same generator and decoding configuration. The only "
        "difference is whether an indexed document collection is consulted before "
        "generation.",
    ),
    (
        "body",
        "The retrieval index contains passages from a filtered English-language "
        "encyclopedic collection. Queries are encoded independently from candidate "
        "passages, and the highest-scoring passages are concatenated with the input.",
    ),
    (
        "body",
        "Because the evaluation compares systems on identical prompts, a difference "
        "in factuality can be attributed to access to retrieved evidence only if the "
        "retrieval and generation stages are measured separately.",
    ),
    ("heading", "4 Results"),
    (
        "body",
        "The retrieval-augmented system answers more knowledge-intensive questions "
        "correctly than the parametric-only baseline and produces more specific "
        "answers.",
    ),
    (
        "body",
        "The Transformer baseline reaches 28.4 BLEU on WMT 2014 English-to-German, "
        "an improvement over earlier reported systems [1].",
    ),
    (
        "body",
        "The BERT model reports a GLUE score of 80.5 and strong results on several "
        "question-answering and language-inference benchmarks.",
    ),
    (
        "body",
        "The largest gains occur on questions whose answers require information not "
        "reliably encoded in the generator parameters.",
    ),
    ("heading", "5 Discussion"),
    (
        "body",
        "These results suggest that retrieval changes the information interface of a "
        "language model rather than merely increasing its parameter count. Retrieved "
        "passages can be inspected, replaced, and re-indexed without retraining the "
        "generator.",
    ),
    (
        "body",
        "The approach still depends on retrieval quality: a fluent generator can "
        "compose a convincing answer from an irrelevant passage. This motivates "
        "evaluations that score both answer quality and evidence alignment.",
    ),
    ("heading", "References"),
    (
        "reference",
        "[1] Vaswani, A., Shazeer, N., Parmar, N., et al. (2017). Attention Is All You Need. "
        "Advances in Neural Information Processing Systems. arXiv:1706.03762. "
        "https://arxiv.org/abs/1706.03762",
    ),
    (
        "reference",
        "[2] Devlin, J., Chang, M.-W., Lee, K., and Toutanova, K. (2019). BERT: Pre-training "
        "of Deep Bidirectional Transformers for Language Understanding. NAACL-HLT, 4171-4186. "
        "https://doi.org/10.18653/v1/N19-1423",
    ),
    (
        "reference",
        "[3] Lewis, P., Perez, E., Piktus, A., et al. (2020). Retrieval-Augmented Generation "
        "for Knowledge-Intensive NLP Tasks. NeurIPS. arXiv:2005.11401. "
        "https://arxiv.org/abs/2005.11401",
    ),
    (
        "reference",
        "[4] He, K., Zhang, X., Ren, S., and Sun, J. (2016). Deep Residual Learning for Image "
        "Recognition. Proceedings of CVPR, 770-778. https://doi.org/10.1109/CVPR.2016.90",
    ),
    (
        "reference",
        "[5] Liu, Y., Ott, M., Goyal, N., et al. (2019). RoBERTa: A Robustly Optimized BERT "
        "Pretraining Approach. arXiv:1907.11692. https://arxiv.org/abs/1907.11692",
    ),
    (
        "reference",
        "[6] Karpukhin, V., Oguz, B., Min, S., et al. (2020). Dense Passage Retrieval for "
        "Open-Domain Question Answering. EMNLP. arXiv:2004.04906. "
        "https://arxiv.org/abs/2004.04906",
    ),
    (
        "reference",
        "[7] Kingma, D. P., and Ba, J. (2015). Adam: A Method for Stochastic Optimization. "
        "ICLR. arXiv:1412.6980. https://arxiv.org/abs/1412.6980",
    ),
]


def wrap(text: str, width: int = CONTENT_WIDTH) -> list[str]:
    words = re.findall(r"\S+", text)
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or [""]


def pdf_escape(value: str) -> str:
    value = value.encode("latin-1", "replace").decode("latin-1")
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def page_lines() -> list[list[tuple[str, str]]]:
    pages: list[list[tuple[str, str]]] = [[]]
    y_lines = 0
    for kind, text in DOCUMENT:
        if kind == "title":
            lines = [text]
        elif kind == "subtitle":
            lines = [text]
        else:
            lines = wrap(text, 84 if kind == "reference" else CONTENT_WIDTH)
        gap = 2 if kind in {"heading", "abstract", "title", "subtitle", "authors"} else 1
        if y_lines + len(lines) + gap > 48:
            pages.append([])
            y_lines = 0
        pages[-1].extend((kind, line) for line in lines)
        pages[-1].append(("gap", ""))
        y_lines += len(lines) + gap
    return pages


def content_stream(lines: list[tuple[str, str]], page_number: int) -> bytes:
    commands = ["BT"]
    y = TOP
    for kind, line in lines:
        if kind == "gap":
            y -= 7
            continue
        if kind == "title":
            size, font = 18, "F1"
        elif kind == "subtitle":
            size, font = 11, "F1"
        elif kind in {"heading", "abstract"}:
            size, font = 12, "F1"
        elif kind == "reference":
            size, font = 9, "F1"
        else:
            size, font = FONT_SIZE, "F1"
        commands.extend([
            f"/{font} {size} Tf",
            f"1 0 0 1 {LEFT} {y:.1f} Tm",
            f"({pdf_escape(line)}) Tj",
        ])
        y -= size + 4
    commands.extend([
        "/F1 8 Tf",
        f"1 0 0 1 {LEFT} 30 Tm",
        f"(Page {page_number}) Tj",
        "ET",
    ])
    return ("\n".join(commands)).encode("latin-1")


def make_pdf(output: Path) -> None:
    pages = page_lines()
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_refs = " ".join(f"{4 + index * 2} 0 R" for index in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{page_refs}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, page in enumerate(pages, start=1):
        stream = content_stream(page, index)
        page_object = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + (index - 1) * 2} 0 R >>"
        )
        objects.append(page_object.encode())
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode())
        data.extend(obj)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)


if __name__ == "__main__":
    make_pdf(Path(sys.argv[1] if len(sys.argv) > 1 else "/mnt/data/missing-citations-real-papers.pdf"))
