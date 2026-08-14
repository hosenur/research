"""Helpers for citation styles, raw-reference fallback, and author-year linking."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.paper import (
    CSLName,
    CSLStyleCandidate,
    CitationStyleDetection,
)

SPECIAL_TOKEN_RE = re.compile(
    r"^\(?\[(?:CLS|SEP|MASK|PAD|UNK)\]\)?$",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"(?<![/.])\b((?:19|20)\d{2})([a-z])?\b")
YEAR_PREFIX_RE = re.compile(r"^((?:19|20)\d{2})([a-z])?\.\s+(.*)$", re.DOTALL)
CITE_KEY_RE = re.compile(r"\[([^]]+)\]")
LEADING_REFERENCES_RE = re.compile(r"^References\s+", re.IGNORECASE)
NAME_PART_RE = r"[A-Z][^\s,;()0-9]{1,30}"
AUTHOR_YEAR_RE = re.compile(
    rf"""
    (?P<author>{NAME_PART_RE}(?:\s+{NAME_PART_RE}){{0,3}})
    (?:
        \s+et\s+al\.?
        |
        \s+(?:and|&)\s+{NAME_PART_RE}(?:\s+{NAME_PART_RE}){{0,3}}
    )?
    [\s,;]*
    \(?
    (?P<year>(?:19|20)\d{{2}})(?P<letter>[a-z])?
    \)?
    """,
    re.VERBOSE,
)
CONTRIBUTION_VERB_RE = re.compile(
    r"\b("
    r"implemented|conducted|collected|developed|designed and led|"
    r"originally demonstrated|worked on|experimented|optimized|advised|"
    r"was an early advocate|led the analysis|led the research|"
    r"contributed|predicted that|assisted with|showed that|"
    r"wrote the paper|systematically studied"
    r")\b",
    re.IGNORECASE,
)
DIALOGUE_RE = re.compile(
    r"Poor English input|Good English output",
    re.IGNORECASE,
)
VENUE_RE = re.compile(
    r"\b(arxiv|proceedings|journal|conference|preprint|doi|workshop|transactions)\b",
    re.IGNORECASE,
)
ORG_PUBLISHER_RE = re.compile(
    r"\b(university|institute|ltd|inc\.?|gmbh|publishers?|association|ieee|acm)\b",
    re.IGNORECASE,
)
AFFILIATION_AUTHORS = {("google", "brain"), ("google", "research")}
AUTHOR_STOPWORDS = {
    "in",
    "on",
    "for",
    "the",
    "and",
    "from",
    "to",
    "with",
    "by",
    "of",
    "at",
    "as",
}
TABLEISH_SHORT_TOKEN_RE = re.compile(r"^[A-Z0-9]{1,3}$")
NUMERIC_SQUARE_RE = re.compile(
    r"^\[\s*\d+(?:\s*(?:,|;|[-–—])\s*\d+)*\s*\][.,;:]?$"
)
NUMERIC_PAREN_RE = re.compile(
    r"^\(\s*\d+(?:\s*(?:,|;|[-–—])\s*\d+)*\s*\)[.,;:]?$"
)
AUTHOR_PAGE_RE = re.compile(
    r"^\(\s*[A-Z][^()\d,;]{1,50}\s+\d+(?:\s*[-–—]\s*\d+)?\s*\)[.,;:]?$"
)
BRACKETED_REFERENCE_RE = re.compile(r"^\s*\[\d+\]")
NUMBERED_REFERENCE_RE = re.compile(r"^\s*\d+[.)]\s+")
PARENTHESIZED_YEAR_RE = re.compile(r"\(\s*(?:19|20)\d{2}[a-z]?\s*\)")
PLAIN_AUTHOR_YEAR_RE = re.compile(
    rf"^\s*{NAME_PART_RE}(?:\s*,\s*|\s+).{{0,80}}\b(?:19|20)\d{{2}}[a-z]?\b"
)


@dataclass(frozen=True)
class AuthorYearMention:
    author: str
    year: int
    letter: str | None
    raw: str

    @property
    def key(self) -> tuple[str, int, str]:
        return (normalize_name_key(self.author), self.year, self.letter or "")


def is_special_token_citation(text: str) -> bool:
    return bool(SPECIAL_TOKEN_RE.fullmatch(clean_space(text)))


def clean_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_name_key(value: str) -> str:
    words = re.findall(r"[a-z]+", value.lower())
    if not words:
        return value.lower()
    # Author-year cites usually key off the first author's surname.
    return words[-1]


def normalize_cite_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9+]", "", value.upper())


def strip_bibliography_prefix(raw_text: str) -> str:
    value = LEADING_REFERENCES_RE.sub("", raw_text).strip()
    return value


def year_label(year: int, letter: str | None = None) -> str:
    return f"{year}{letter or ''}"


def extract_year_label(text: str | None) -> tuple[int | None, str | None]:
    if not text:
        return None, None
    match = YEAR_PREFIX_RE.match(text.strip())
    if match:
        return int(match.group(1)), match.group(2)
    matches = list(YEAR_RE.finditer(text))
    if not matches:
        return None, None
    # Prefer a year that carries a disambiguator (2018a) when present.
    for match in matches:
        if match.group(2):
            return int(match.group(1)), match.group(2)
    match = matches[-1]
    return int(match.group(1)), match.group(2)


def recover_title_from_raw(raw_text: str) -> str | None:
    text = re.sub(
        r"^(?:\[[^\]]+\]|[A-Z]{2,}[^\]\n]{0,40}\])\s*",
        "",
        strip_bibliography_prefix(raw_text),
    ).strip()
    if not text:
        return None
    parts = [
        part.strip(" .")
        for part in re.split(r"(?<!\b[A-Z])\.\s+", text)
        if part.strip(" .")
    ]
    if len(parts) < 2:
        return None

    year_indexes = [index for index, part in enumerate(parts) if YEAR_RE.fullmatch(part)]
    if year_indexes and year_indexes[0] == 1 and len(parts) > 2:
        title = parts[2]
    elif looks_like_name_list(parts[0]) and not YEAR_RE.fullmatch(parts[1]):
        title = parts[1]
    else:
        return None

    if len(title) < 3 or DIALOGUE_RE.search(title) or CONTRIBUTION_VERB_RE.search(title):
        return None
    return title


def strip_year_prefix(title: str | None) -> tuple[str | None, int | None, str | None]:
    if not title:
        return title, None, None
    match = YEAR_PREFIX_RE.match(title.strip())
    if not match:
        return title, None, None
    return match.group(3).strip(), int(match.group(1)), match.group(2)


def extract_cite_keys(text: str) -> list[str]:
    keys: list[str] = []
    for match in CITE_KEY_RE.finditer(text):
        for part in re.split(r"\s*,\s*", match.group(1)):
            part = part.strip()
            if not part or re.fullmatch(r"\d+", part):
                continue
            if not re.search(r"[A-Za-z]", part):
                continue
            key = normalize_cite_key(part)
            if key and key not in keys:
                keys.append(key)
    return keys


def parse_author_year_mentions(text: str) -> list[AuthorYearMention]:
    mentions: list[AuthorYearMention] = []
    seen: set[tuple[str, int, str]] = set()
    for match in AUTHOR_YEAR_RE.finditer(text):
        author = clean_space(match.group("author"))
        if not author or author.isupper() or author.lower() in AUTHOR_STOPWORDS:
            continue
        mention = AuthorYearMention(
            author=author,
            year=int(match.group("year")),
            letter=match.group("letter"),
            raw=clean_space(match.group(0)),
        )
        if mention.key in seen:
            continue
        seen.add(mention.key)
        mentions.append(mention)
    return mentions


def looks_like_name_list(value: str | None) -> bool:
    if not value or ORG_PUBLISHER_RE.search(value):
        return False
    parts = [
        part.strip()
        for part in re.split(r",|\s+and\s+", value)
        if part.strip() and part.strip().lower() != "and"
    ]
    if not parts or len(parts) > 12:
        return False
    name = re.compile(rf"^{NAME_PART_RE}(?:\s+{NAME_PART_RE}){{0,3}}$")
    return all(name.fullmatch(part) for part in parts)


def parse_name_list(value: str) -> list[CSLName]:
    parts = [
        part.strip()
        for part in re.split(r",|\s+and\s+", value)
        if part.strip() and part.strip().lower() != "and"
    ]
    names: list[CSLName] = []
    for part in parts:
        tokens = part.split()
        if not tokens:
            continue
        if len(tokens) == 1:
            names.append(CSLName(family=tokens[0]))
        else:
            names.append(CSLName(given=" ".join(tokens[:-1]), family=tokens[-1]))
    return names


def is_affiliation_author(author: CSLName) -> bool:
    given = (author.given or "").strip().lower()
    family = (author.family or "").strip().lower()
    if (given, family) in AFFILIATION_AUTHORS:
        return True
    return not given and not family and not author.literal


def is_spurious_bibliography_entry(
    raw_text: str,
    title: str | None,
    *,
    has_year: bool,
    has_identifier: bool,
) -> bool:
    blob = f"{title or ''} {raw_text}".strip()
    if not blob:
        return True
    if DIALOGUE_RE.search(blob):
        return True
    if has_identifier:
        return False
    if CONTRIBUTION_VERB_RE.search(blob) and not VENUE_RE.search(blob):
        if not has_year or not looks_like_bibliographic_sentence(blob):
            return True
    return False


def looks_like_bibliographic_sentence(text: str) -> bool:
    return bool(VENUE_RE.search(text) or re.search(r"\.\s+[A-Z]", text))


def is_figure_or_prompt_section(title: str) -> bool:
    if re.fullmatch(r"Input-Input Layer\d+", title):
        return True
    if "→" in title or "->" in title:
        return True
    if re.match(r"^(Figure|Table|Fig\.?)\s*\d", title, re.IGNORECASE):
        return True
    tokens = title.split()
    if len(tokens) >= 4:
        short = sum(1 for token in tokens if TABLEISH_SHORT_TOKEN_RE.fullmatch(token))
        if short >= 3:
            return True
    return False


def normalize_section_title(title: str) -> str:
    title = clean_space(title)
    if len(title) <= 80:
        return title
    acronym = re.match(r"^([A-Z]{2,}[A-Z0-9\-]*)\b", title)
    if acronym:
        return acronym.group(1)
    words = title.split()
    if len(words) > 8:
        return " ".join(words[:8]).rstrip(".,;:")
    return title


def classify_citation_style(
    raw_texts: list[str],
    reference_texts: list[str] | None = None,
) -> CitationStyleDetection:
    """Classify citation family and expose evidence without guessing an exact CSL style.

    In-text markers are the primary signal. Bibliography punctuation only adjusts
    the ordering of plausible CSL candidates because many publisher styles are
    visually indistinguishable after PDF extraction.
    """
    evidence = {
        "numericSquare": 0,
        "numericParenthetical": 0,
        "authorYearParentheticalComma": 0,
        "authorYearParentheticalNoComma": 0,
        "authorYearNarrative": 0,
        "authorPage": 0,
        "harvardKey": 0,
        "unclassified": 0,
        "referenceBracketNumbered": 0,
        "referenceNumbered": 0,
        "referenceParenthesizedYear": 0,
        "referencePlainYear": 0,
    }
    family_counts = {
        "numeric": 0,
        "author-year": 0,
        "author-page": 0,
        "harvard-key": 0,
    }
    syntaxes: set[str] = set()
    nonempty = 0

    for raw_text in raw_texts:
        text = clean_space(raw_text)
        if not text:
            continue
        nonempty += 1

        if NUMERIC_SQUARE_RE.fullmatch(text):
            evidence["numericSquare"] += 1
            family_counts["numeric"] += 1
            syntaxes.add("square-bracket")
            continue
        if NUMERIC_PAREN_RE.fullmatch(text):
            evidence["numericParenthetical"] += 1
            family_counts["numeric"] += 1
            syntaxes.add("numeric-parenthetical")
            continue
        mentions = parse_author_year_mentions(text)
        if mentions:
            family_counts["author-year"] += 1
            if text.lstrip().startswith("("):
                if re.search(r",\s*(?:19|20)\d{2}", text):
                    evidence["authorYearParentheticalComma"] += 1
                    syntaxes.add("author-year-parenthetical-comma")
                else:
                    evidence["authorYearParentheticalNoComma"] += 1
                    syntaxes.add("author-year-parenthetical-no-comma")
            else:
                evidence["authorYearNarrative"] += 1
                syntaxes.add("author-year-narrative")
            continue

        if AUTHOR_PAGE_RE.fullmatch(text):
            evidence["authorPage"] += 1
            family_counts["author-page"] += 1
            syntaxes.add("author-page")
            continue

        if extract_cite_keys(text):
            evidence["harvardKey"] += 1
            family_counts["harvard-key"] += 1
            syntaxes.add("citation-key")
            continue

        evidence["unclassified"] += 1

    for raw_reference in reference_texts or []:
        reference = clean_space(raw_reference)
        if not reference:
            continue
        if BRACKETED_REFERENCE_RE.search(reference):
            evidence["referenceBracketNumbered"] += 1
        elif NUMBERED_REFERENCE_RE.search(reference):
            evidence["referenceNumbered"] += 1
        if PARENTHESIZED_YEAR_RE.search(reference):
            evidence["referenceParenthesizedYear"] += 1
        elif PLAIN_AUTHOR_YEAR_RE.search(reference):
            evidence["referencePlainYear"] += 1

    present = {family: count for family, count in family_counts.items() if count}
    recognized = sum(family_counts.values())
    if not present:
        family = "unknown"
    elif len(present) == 1:
        family = next(iter(present))
    else:
        family = "mixed"
        syntaxes.add("mixed")

    coverage = recognized / nonempty if nonempty else 0
    dominant_share = max(present.values(), default=0) / recognized if recognized else 0
    if family != "mixed" and recognized >= 3 and coverage >= 0.8 and dominant_share >= 0.8:
        confidence = "high"
    elif recognized and coverage >= 0.5:
        confidence = "medium"
    else:
        confidence = "low"

    candidates, reasons = _csl_candidates(family, evidence)
    if evidence["unclassified"]:
        reasons.append(
            f'{evidence["unclassified"]} citation marker(s) did not match a known family.'
        )
    if family == "mixed":
        reasons.append("More than one citation family appears in the paper.")
    if family == "unknown":
        reasons.append("No reliable citation-family signal was found.")

    return CitationStyleDetection(
        family=family,
        syntaxes=sorted(syntaxes),
        confidence=confidence,
        csl_candidates=candidates,
        needs_confirmation=True,
        evidence=evidence,
        reasons=reasons,
    )


def _csl_candidates(
    family: str,
    evidence: dict[str, int],
) -> tuple[list[CSLStyleCandidate], list[str]]:
    candidates: list[CSLStyleCandidate] = []
    reasons: list[str] = []

    def add(style_id: str, label: str, score: float, reason: str) -> None:
        candidates.append(
            CSLStyleCandidate(id=style_id, label=label, score=score, reason=reason)
        )

    if family == "numeric":
        bracketed = evidence["numericSquare"] + evidence["referenceBracketNumbered"]
        numbered = evidence["numericParenthetical"] + evidence["referenceNumbered"]
        if bracketed > numbered:
            add("ieee", "IEEE", 0.72, "Square-bracket citations and numbered references are IEEE-like.")
            add("vancouver", "Vancouver", 0.52, "Some Vancouver variants also use bracketed numbers.")
        else:
            add("vancouver", "Vancouver", 0.68, "Parenthetical or simply numbered references are Vancouver-like.")
            add("ieee", "IEEE", 0.45, "IEEE remains possible for extracted numeric citations.")
        reasons.append("Numeric punctuation alone cannot uniquely identify a publisher style.")
    elif family == "author-year":
        comma = evidence["authorYearParentheticalComma"]
        no_comma = evidence["authorYearParentheticalNoComma"]
        if comma >= no_comma and evidence["referenceParenthesizedYear"]:
            add("apa", "APA", 0.72, "Comma-separated citations and parenthesized bibliography years are APA-like.")
            add("harvard-cite-them-right", "Harvard – Cite Them Right", 0.56, "Harvard variants share this author-year syntax.")
        elif no_comma > comma or evidence["referencePlainYear"]:
            add("chicago-author-date", "Chicago author-date", 0.68, "Author-year citations without a comma are Chicago-like.")
            add("harvard-cite-them-right", "Harvard – Cite Them Right", 0.54, "A Harvard variant remains plausible.")
        else:
            add("apa", "APA", 0.58, "The observed syntax belongs to the APA-compatible author-year family.")
            add("chicago-author-date", "Chicago author-date", 0.52, "Chicago cannot be excluded from markers alone.")
            add("harvard-cite-them-right", "Harvard – Cite Them Right", 0.52, "Harvard cannot be excluded from markers alone.")
        reasons.append("Many author-year styles share identical in-text markers.")
    elif family == "author-page":
        add("modern-language-association", "MLA", 0.78, "Author-page citations are characteristic of MLA.")
        reasons.append("The family is clear, but the exact MLA edition still needs confirmation.")
    elif family == "harvard-key":
        reasons.append("Bracketed citation keys are document keys, not enough to select a CSL style.")
    elif family == "mixed":
        reasons.append("Choose one target CSL style before rendering or export.")

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates, reasons


def detect_citation_style(raw_texts: list[str]) -> str | None:
    """Compatibility accessor for callers that only need the broad family."""
    family = classify_citation_style(raw_texts).family
    return None if family == "unknown" else family


def arxiv_year(arxiv_id: str | None) -> int | None:
    if not arxiv_id:
        return None
    match = re.match(r"^(\d{2})(\d{2})\.\d+", arxiv_id)
    if not match:
        return None
    year = int(match.group(1))
    return 2000 + year if year < 90 else 1900 + year
