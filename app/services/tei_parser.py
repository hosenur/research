from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

from app.schemas.paper import (
    CSLDate,
    CSLItem,
    CSLName,
    CitationNode,
    Paper,
    Paragraph,
    ParagraphNode,
    Reference,
    Section,
    TextNode,
)
from app.services.citation_utils import (
    AuthorYearMention,
    arxiv_year,
    detect_citation_style,
    extract_cite_keys,
    extract_year_label,
    is_affiliation_author,
    is_figure_or_prompt_section,
    is_special_token_citation,
    is_spurious_bibliography_entry,
    looks_like_name_list,
    normalize_name_key,
    normalize_section_title,
    parse_author_year_mentions,
    parse_name_list,
    recover_title_from_raw,
    strip_bibliography_prefix,
    strip_year_prefix,
    year_label,
)

TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
NS = {"tei": TEI_NAMESPACE}


class TEIParseError(ValueError):
    """Raised when a document cannot be interpreted as GROBID TEI XML."""


def qname(local_name: str) -> str:
    return f"{{{TEI_NAMESPACE}}}{local_name}"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return clean_text("".join(element.itertext()))


def first_text(element: ET.Element, paths: list[str]) -> str | None:
    for path in paths:
        value = element_text(element.find(path, NS))
        if value:
            return value
    return None


def parse_tei(xml: bytes) -> Paper:
    """Convert GROBID TEI into the Paper AST.

    Pipeline:
    1. Reject DTDs, parse XML, require a TEI root.
    2. Read title, authors, identifiers, and abstract from the header.
    3. Walk body ``div``s into sections, skipping figure/prompt dumps.
    4. Split paragraphs into text vs bibliography ``ref`` nodes. Special
       tokens such as ``[CLS]`` stay text. Adjacent GROBID cite fragments
       are merged and stray brackets are pulled back onto the cite.
    5. Keep every real bibliography entry as CSL-JSON, recover missing
       title/author/date from raw text, and drop acknowledgements or
       examples that GROBID parked in ``listBibl``.
    6. Link leftover author-year and Harvard-key cites to those entries.
       Anything still unmatched stays visible as ``unresolvedFragments``.
    """
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise TEIParseError("DTD and entity declarations are not accepted.")

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise TEIParseError(f"Malformed TEI XML: {exc}.") from exc

    if local_name(root.tag) != "TEI":
        raise TEIParseError("The XML root element must be TEI.")

    title = first_text(
        root,
        [
            ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title[@type='main']",
            ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title",
            ".//tei:teiHeader/tei:fileDesc/tei:sourceDesc//tei:title[@type='main']",
        ],
    ) or ""

    authors, identifiers, year = parse_header_metadata(root)
    abstract_element = root.find(".//tei:teiHeader/tei:profileDesc/tei:abstract", NS)
    abstract = parse_abstract(abstract_element)
    sections = parse_sections(root.find(".//tei:text/tei:body", NS))
    references, omitted_references = parse_references(root)
    resolve_citations(sections, references)

    citation_nodes = [
        node
        for section in sections
        for paragraph in section.paragraphs
        for node in paragraph.nodes
        if isinstance(node, CitationNode)
    ]
    known_reference_ids = {reference.id for reference in references}
    cited_reference_ids = {
        reference_id
        for node in citation_nodes
        for reference_id in node.reference_ids
    }
    unresolved_fragments = [
        fragment
        for node in citation_nodes
        for fragment in node.unresolved_fragments
    ]

    warnings: list[str] = []
    if omitted_references:
        warnings.append(
            f"Omitted {omitted_references} bibliography entries that are not references."
        )
    if unresolved_fragments:
        warnings.append(
            f"{len(unresolved_fragments)} in-text citation fragments could not be linked."
        )

    return Paper(
        title=title,
        abstract=abstract,
        authors=authors,
        year=year,
        identifiers=identifiers,
        citation_style=detect_citation_style([node.raw_text for node in citation_nodes]),
        sections=sections,
        references=references,
        unresolved_reference_ids=sorted(cited_reference_ids - known_reference_ids),
        warnings=warnings,
    )


def parse_header_metadata(
    root: ET.Element,
) -> tuple[list[CSLName], dict[str, str], int | None]:
    source = root.find(".//tei:teiHeader/tei:fileDesc/tei:sourceDesc/tei:biblStruct", NS)
    if source is None:
        return [], {}, None

    analytic = source.find("tei:analytic", NS)
    authors = [
        author
        for author in parse_authors(analytic if analytic is not None else source)
        if not is_affiliation_author(author)
    ]
    identifiers = parse_identifiers(source)
    issued, _ = parse_issued_date(source)
    year = issued.date_parts[0][0] if issued and issued.date_parts else None
    arxiv_id = identifiers.get("arxiv")
    if arxiv_id:
        identifiers["arxiv"] = arxiv_id
        year = arxiv_year(arxiv_id) or year
    return authors, identifiers, year


def parse_abstract(abstract: ET.Element | None) -> str | None:
    if abstract is None:
        return None

    paragraphs = [element_text(paragraph) for paragraph in abstract.findall(".//tei:p", NS)]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    if paragraphs:
        return "\n\n".join(paragraphs)

    value = element_text(abstract)
    return value or None


def parse_sections(body: ET.Element | None) -> list[Section]:
    if body is None:
        return []

    sections: list[Section] = []
    paragraph_number = 0

    def add_section(container: ET.Element, fallback_title: str) -> None:
        nonlocal paragraph_number

        head = container.find("tei:head", NS)
        number = head.get("n") if head is not None else None
        title = normalize_section_title(element_text(head) or fallback_title)
        nested_paragraphs = {
            id(paragraph)
            for nested_div in container.findall("tei:div", NS)
            for paragraph in nested_div.iter(qname("p"))
        }
        paragraph_elements = [
            paragraph
            for paragraph in container.iter(qname("p"))
            if id(paragraph) not in nested_paragraphs
        ]

        paragraphs: list[Paragraph] = []
        for paragraph_element in paragraph_elements:
            nodes = parse_paragraph_nodes(paragraph_element)
            if not nodes:
                continue
            paragraph_number += 1
            paragraph_id = paragraph_element.get(XML_ID) or f"paragraph-{paragraph_number}"
            paragraphs.append(Paragraph(id=paragraph_id, nodes=nodes))

        if paragraphs and not is_figure_or_prompt_section(title):
            section_id = container.get(XML_ID) or f"section-{len(sections) + 1}"
            sections.append(
                Section(
                    id=section_id,
                    title=title,
                    number=number,
                    paragraphs=paragraphs,
                )
            )

        for nested_div in container.findall("tei:div", NS):
            add_section(nested_div, "Untitled section")

    direct_paragraphs = body.findall("tei:p", NS)
    if direct_paragraphs:
        wrapper = ET.Element(qname("div"))
        for paragraph in direct_paragraphs:
            wrapper.append(paragraph)
        add_section(wrapper, "Body")

    for div in body.findall("tei:div", NS):
        add_section(div, "Untitled section")

    return sections


def parse_paragraph_nodes(paragraph: ET.Element) -> list[ParagraphNode]:
    nodes: list[ParagraphNode] = []

    def append_text(value: str | None) -> None:
        if not value:
            return
        normalized = re.sub(r"\s+", " ", value)
        if nodes and isinstance(nodes[-1], TextNode):
            nodes[-1].text += normalized
        else:
            nodes.append(TextNode(text=normalized))

    def walk(element: ET.Element) -> None:
        append_text(element.text)
        for child in element:
            if local_name(child.tag) == "ref" and child.get("type") == "bibr":
                raw_text = element_text(child)
                if is_special_token_citation(raw_text):
                    append_text(raw_text)
                else:
                    reference_ids = parse_targets(child.get("target", ""))
                    nodes.append(
                        CitationNode(
                            raw_text=raw_text,
                            reference_ids=reference_ids,
                            unresolved_fragments=[] if reference_ids else [raw_text],
                        )
                    )
            else:
                walk(child)
            append_text(child.tail)

    walk(paragraph)
    return normalize_nodes(nodes)


def parse_targets(target: str) -> list[str]:
    reference_ids: list[str] = []
    for value in re.split(r"[\s,]+", target.strip()):
        if not value:
            continue
        reference_id = value.rsplit("#", 1)[-1]
        if reference_id and reference_id not in reference_ids:
            reference_ids.append(reference_id)
    return reference_ids


def normalize_nodes(nodes: list[ParagraphNode]) -> list[ParagraphNode]:
    normalized: list[ParagraphNode] = []

    for node in nodes:
        if isinstance(node, TextNode):
            node.text = re.sub(r"\s+", " ", node.text)
            if not node.text.strip():
                continue
            if normalized and isinstance(normalized[-1], TextNode):
                normalized[-1].text += node.text
            else:
                normalized.append(node)
            continue

        if normalized and isinstance(normalized[-1], CitationNode):
            previous = normalized[-1]
            previous.raw_text = clean_text(f"{previous.raw_text} {node.raw_text}")
            previous.reference_ids = list(
                dict.fromkeys([*previous.reference_ids, *node.reference_ids])
            )
            previous.unresolved_fragments.extend(node.unresolved_fragments)
        else:
            normalized.append(node)

    expand_citation_boundaries(normalized)

    if normalized and isinstance(normalized[0], TextNode):
        normalized[0].text = normalized[0].text.lstrip()
    if normalized and isinstance(normalized[-1], TextNode):
        normalized[-1].text = normalized[-1].text.rstrip()

    return [
        node
        for node in normalized
        if not isinstance(node, TextNode) or bool(node.text)
    ]


def expand_citation_boundaries(nodes: list[ParagraphNode]) -> None:
    """Recover bracket text that GROBID occasionally leaves just outside a ref tag."""
    for index, node in enumerate(nodes):
        if not isinstance(node, CitationNode):
            continue

        for opener, closer in (("(", ")"), ("[", "]")):
            if node.raw_text.count(closer) > node.raw_text.count(opener):
                if index > 0 and isinstance(nodes[index - 1], TextNode):
                    previous = nodes[index - 1]
                    opener_index = unmatched_opener_index(previous.text, opener, closer)
                    if opener_index is not None and len(previous.text) - opener_index <= 200:
                        prefix = previous.text[opener_index:]
                        previous.text = previous.text[:opener_index]
                        node.raw_text = clean_text(f"{prefix}{node.raw_text}")

            if node.raw_text.count(opener) > node.raw_text.count(closer):
                if index + 1 < len(nodes) and isinstance(nodes[index + 1], TextNode):
                    following = nodes[index + 1]
                    closer_index = following.text.find(closer)
                    if 0 <= closer_index < 200:
                        suffix = following.text[: closer_index + 1]
                        following.text = following.text[closer_index + 1 :]
                        node.raw_text = clean_text(f"{node.raw_text}{suffix}")


def unmatched_opener_index(value: str, opener: str, closer: str) -> int | None:
    depth = 0
    for index in range(len(value) - 1, -1, -1):
        if value[index] == closer:
            depth += 1
        elif value[index] == opener:
            if depth == 0:
                return index
            depth -= 1
    return None


def parse_references(root: ET.Element) -> tuple[list[Reference], int]:
    references: list[Reference] = []
    bibliography_entries: list[ET.Element] = []
    seen_entries: set[int] = set()
    omitted = 0

    # GROBID normally emits direct biblStruct children in text/back, but TEI also
    # permits nested bibliography lists and unstructured bibl entries. Walk every
    # listBibl in document order and de-duplicate entries reached through a nested
    # list so no bibliography record is silently omitted or returned twice.
    for bibliography in root.findall(".//tei:listBibl", NS):
        for element in bibliography.iter():
            if local_name(element.tag) not in {"biblStruct", "bibl"}:
                continue
            element_identity = id(element)
            if element_identity in seen_entries:
                continue
            seen_entries.add(element_identity)
            bibliography_entries.append(element)

    for index, bibl in enumerate(bibliography_entries, start=1):
        reference_id = bibl.get(XML_ID) or f"b{index}"
        raw_text = strip_bibliography_prefix(
            first_text(bibl, ["tei:note[@type='raw_reference']"]) or element_text(bibl)
        )
        csl, raw_fields, warnings = reference_to_csl(bibl, reference_id, raw_text)

        if is_spurious_bibliography_entry(
            raw_text,
            csl.title if csl else None,
            has_year=bool(csl and csl.issued) or bool(raw_fields.get("yearLabel")),
            has_identifier=bool(raw_fields.get("identifiers")),
        ):
            omitted += 1
            continue

        if not bibl.get(XML_ID):
            warnings.append(
                f"Bibliography entry had no xml:id; assigned {reference_id}."
            )
        if not raw_text:
            warnings.append("Bibliography entry contained no raw text.")

        if csl is None:
            reference_status = "failed"
        elif csl.title and csl.author and csl.issued:
            reference_status = "parsed"
        else:
            reference_status = "partial"
            missing = [
                name
                for name, present in (
                    ("title", bool(csl.title)),
                    ("author", bool(csl.author)),
                    ("issued date", bool(csl.issued)),
                )
                if not present
            ]
            warnings.append(f"Missing core CSL fields: {', '.join(missing)}.")

        references.append(
            Reference(
                id=reference_id,
                raw_text=raw_text,
                csl=csl,
                status=reference_status,
                raw_fields=raw_fields,
                warnings=warnings,
            )
        )

    return references, omitted


def resolve_citations(sections: list[Section], references: list[Reference]) -> None:
    index = CitationIndex.from_references(references)
    for section in sections:
        for paragraph in section.paragraphs:
            for node in paragraph.nodes:
                if isinstance(node, CitationNode):
                    index.resolve(node)


class CitationIndex:
    def __init__(self) -> None:
        self.exact: dict[tuple[str, int, str], str] = {}
        self.by_year: dict[tuple[str, int], list[str]] = {}
        self.cite_keys: dict[str, str] = {}
        self.references: dict[str, Reference] = {}

    @classmethod
    def from_references(cls, references: list[Reference]) -> CitationIndex:
        index = cls()
        for reference in references:
            index.add(reference)
        return index

    def add(self, reference: Reference) -> None:
        self.references[reference.id] = reference
        for key in extract_cite_keys(reference.raw_text):
            self.cite_keys.setdefault(key, reference.id)

        authors = reference.csl.author if reference.csl else []
        if not authors:
            return
        family = normalize_name_key(authors[0].family or authors[0].literal or "")
        if not family:
            return

        labels: list[tuple[int, str]] = []
        year_from_label = reference.raw_fields.get("yearLabel")
        if isinstance(year_from_label, str):
            parsed_year, letter = extract_year_label(year_from_label)
            if parsed_year:
                labels.append((parsed_year, letter or ""))
        if reference.csl and reference.csl.issued and reference.csl.issued.date_parts:
            labels.append((reference.csl.issued.date_parts[0][0], ""))

        seen: set[tuple[int, str]] = set()
        for year, letter in labels:
            marker = (year, letter)
            if marker in seen:
                continue
            seen.add(marker)
            self.exact.setdefault((family, year, letter), reference.id)
            bucket = self.by_year.setdefault((family, year), [])
            if reference.id not in bucket:
                bucket.append(reference.id)

    def lookup_mention(self, mention: AuthorYearMention) -> str | None:
        family = mention.key[0]
        exact = self.exact.get((family, mention.year, mention.letter or ""))
        if exact:
            return exact
        candidates = self.by_year.get((family, mention.year), [])
        if len(candidates) == 1:
            return candidates[0]
        return None

    def mention_covered(self, mention: AuthorYearMention, linked_ids: list[str]) -> bool:
        mention_tokens = {
            token
            for token in re.findall(r"[a-z]+", mention.author.lower())
            if token not in {"and", "et", "al"}
        }
        for reference_id in linked_ids:
            reference = self.references.get(reference_id)
            if not reference or not reference.csl:
                continue
            author_tokens: set[str] = set()
            for author in reference.csl.author:
                author_tokens.update(
                    re.findall(
                        r"[a-z]+",
                        f"{author.given or ''} {author.family or ''} {author.literal or ''}".lower(),
                    )
                )
            if mention_tokens & author_tokens:
                return True
        return False

    def resolve(self, node: CitationNode) -> None:
        search_text = " ".join([node.raw_text, *node.unresolved_fragments])
        matched_ids: list[str] = []
        unresolved: list[str] = []

        for key in extract_cite_keys(search_text):
            reference_id = self.cite_keys.get(key)
            if reference_id:
                matched_ids.append(reference_id)

        linked_ids = list(dict.fromkeys([*node.reference_ids, *matched_ids]))
        mentions = parse_author_year_mentions(search_text)
        if mentions:
            for mention in mentions:
                reference_id = self.lookup_mention(mention)
                if reference_id:
                    matched_ids.append(reference_id)
                    if reference_id not in linked_ids:
                        linked_ids.append(reference_id)
                elif not self.mention_covered(mention, linked_ids):
                    unresolved.append(mention.raw.rstrip(").,;"))
        elif not node.reference_ids:
            unresolved.extend(
                fragment.strip()
                for fragment in node.unresolved_fragments
                if fragment.strip()
            )

        node.reference_ids = list(dict.fromkeys([*node.reference_ids, *matched_ids]))
        node.unresolved_fragments = list(dict.fromkeys(unresolved))


def reference_to_csl(
    bibl: ET.Element,
    reference_id: str,
    raw_text: str = "",
) -> tuple[CSLItem | None, dict[str, Any], list[str]]:
    analytic = bibl.find("tei:analytic", NS)
    monogr = bibl.find("tei:monogr", NS)
    author_container = analytic if analytic is not None else monogr

    title = None
    if analytic is not None:
        title = first_text(analytic, ["tei:title[@type='main']", "tei:title"])
    if not title and monogr is not None:
        title = first_text(monogr, ["tei:title[@type='main']", "tei:title"])

    authors = parse_authors(author_container)
    issued, raw_date = parse_issued_date(bibl)
    identifiers = parse_identifiers(bibl)
    title, authors, issued, raw_date, fallback_warnings = recover_csl_fields(
        bibl,
        raw_text,
        title,
        authors,
        issued,
        raw_date,
    )
    container_title = None
    if analytic is not None and monogr is not None:
        container_title = first_text(monogr, ["tei:title[@type='main']", "tei:title"])

    volume = bibl_scope(bibl, "volume")
    issue = bibl_scope(bibl, "issue")
    page = bibl_scope(bibl, "page")
    publisher = first_text(bibl, [".//tei:publisher"])
    publisher_place = first_text(bibl, [".//tei:pubPlace"])
    meeting = first_text(bibl, [".//tei:meeting"])
    report_type = first_text(bibl, ["tei:note[@type='report_type']"])

    item_type = "article"
    if meeting:
        item_type = "paper-conference"
    elif analytic is not None:
        item_type = "article-journal"
    elif "arxiv" in identifiers or report_type:
        item_type = "report"
    elif publisher and monogr is not None:
        item_type = "book"

    arxiv_id = identifiers.get("arxiv")
    url = identifiers.get("url")
    if not url and arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"

    parsed_year, parsed_letter = extract_year_label(
        " ".join(part for part in (raw_date, title, raw_text) if part)
    )
    raw_fields: dict[str, Any] = {
        "title": title,
        "authors": [
            {"given": author.given, "family": author.family, "literal": author.literal}
            for author in authors
        ],
        "date": raw_date,
        "yearLabel": year_label(parsed_year, parsed_letter) if parsed_year else None,
        "containerTitle": container_title,
        "volume": volume,
        "issue": issue,
        "page": page,
        "publisher": publisher,
        "publisherPlace": publisher_place,
        "meeting": meeting,
        "reportType": report_type,
        "identifiers": identifiers,
    }
    raw_fields = {key: value for key, value in raw_fields.items() if value not in (None, [], {})}

    has_structured_value = any(
        [
            title,
            authors,
            issued,
            identifiers,
            container_title,
            volume,
            issue,
            page,
            publisher,
        ]
    )
    if not has_structured_value:
        return None, raw_fields, ["GROBID produced no usable structured fields."]

    csl = CSLItem(
        id=reference_id,
        type=item_type,
        title=title,
        author=authors,
        issued=issued,
        container_title=container_title,
        volume=volume,
        issue=issue,
        page=page,
        publisher=publisher,
        publisher_place=publisher_place,
        doi=identifiers.get("doi"),
        url=url,
        isbn=identifiers.get("isbn"),
        issn=identifiers.get("issn"),
        pmid=identifiers.get("pmid"),
        pmcid=identifiers.get("pmcid"),
        archive="arXiv" if arxiv_id else None,
        archive_location=arxiv_id,
    )
    return csl, raw_fields, fallback_warnings


def recover_csl_fields(
    bibl: ET.Element,
    raw_text: str,
    title: str | None,
    authors: list[CSLName],
    issued: CSLDate | None,
    raw_date: str | None,
) -> tuple[str | None, list[CSLName], CSLDate | None, str | None, list[str]]:
    warnings: list[str] = []
    cleaned_title, prefix_year, prefix_letter = strip_year_prefix(title)
    if prefix_year and cleaned_title:
        title = cleaned_title
        if issued is None:
            issued = CSLDate(date_parts=[[prefix_year]])
            raw_date = raw_date or year_label(prefix_year, prefix_letter)
        warnings.append("Moved a leading year off the title into issued.")

    if not title:
        untitled_note = None
        for note in bibl.findall("tei:note", NS):
            if note.get("type") in {None, "report_type"}:
                value = element_text(note)
                if value and note.get("type") != "raw_reference":
                    untitled_note = value
                    break
        if untitled_note:
            recovered = untitled_note.split("arXiv")[0].strip(" .")
            if recovered and not is_spurious_bibliography_entry(
                recovered, recovered, has_year=False, has_identifier=False
            ):
                title = recovered
                warnings.append("Recovered title from a GROBID note.")

    if not title:
        recovered = recover_title_from_raw(raw_text)
        if recovered:
            title = recovered
            warnings.append("Recovered title from the raw reference string.")

    if not authors:
        publisher = first_text(bibl, [".//tei:publisher"])
        if looks_like_name_list(publisher):
            authors = parse_name_list(publisher or "")
            warnings.append("Recovered authors from a publisher field that contained names.")
        elif looks_like_name_list(raw_text.split(".")[0] if raw_text else ""):
            authors = parse_name_list(raw_text.split(".")[0])
            warnings.append("Recovered authors from the raw reference string.")

    if issued is None:
        year, letter = extract_year_label(raw_text)
        if year:
            issued = CSLDate(date_parts=[[year]])
            raw_date = year_label(year, letter)
            warnings.append("Recovered issued date from the raw reference string.")

    return title, authors, issued, raw_date, warnings


def parse_authors(container: ET.Element | None) -> list[CSLName]:
    if container is None:
        return []

    authors: list[CSLName] = []
    for author in container.findall("tei:author", NS):
        person_name = author.find("tei:persName", NS)
        if person_name is not None:
            given = " ".join(
                value
                for value in (element_text(name) for name in person_name.findall("tei:forename", NS))
                if value
            )
            family = " ".join(
                value
                for value in (element_text(name) for name in person_name.findall("tei:surname", NS))
                if value
            )
            if given or family:
                authors.append(CSLName(given=given or None, family=family or None))
                continue

        literal = element_text(author)
        if literal:
            authors.append(CSLName(literal=literal))

    return authors


def parse_issued_date(bibl: ET.Element) -> tuple[CSLDate | None, str | None]:
    date = bibl.find(".//tei:imprint/tei:date[@type='published']", NS)
    if date is None:
        date = bibl.find(".//tei:imprint/tei:date", NS)
    if date is None:
        return None, None

    raw_date = date.get("when") or element_text(date)
    parts = [int(part) for part in re.findall(r"\d+", raw_date)[:3]]
    if not parts:
        return None, raw_date
    return CSLDate(date_parts=[parts]), raw_date


def parse_identifiers(bibl: ET.Element) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    for identifier in bibl.findall(".//tei:idno", NS):
        value = element_text(identifier)
        if not value:
            continue
        identifier_type = (identifier.get("type") or "").lower()
        if identifier_type == "doi":
            value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value, flags=re.I)
        elif identifier_type == "arxiv":
            value = re.sub(r"^arxiv:\s*", "", value, flags=re.I)
            value = re.sub(r"v\d+(?:\[[^]]+\])?$", "", value)
        if identifier_type:
            identifiers.setdefault(identifier_type, value)

    for pointer in bibl.findall(".//tei:ptr", NS):
        target = pointer.get("target")
        if target and target.startswith(("http://", "https://")):
            identifiers.setdefault("url", target)

    return identifiers


def bibl_scope(bibl: ET.Element, unit: str) -> str | None:
    scope = bibl.find(f".//tei:biblScope[@unit='{unit}']", NS)
    if scope is None:
        return None
    start = scope.get("from")
    end = scope.get("to")
    if start and end and start != end:
        return f"{start}-{end}"
    return start or end or element_text(scope) or None
