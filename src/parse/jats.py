"""Parse a Europe PMC JATS batch into auditable documents and chunks.

The implementation deliberately uses only the Python standard library.  It
does not resolve external DTDs, execute network requests, or infer research
claims.  Its job is to preserve research-semantic source text and its stable
location while excluding administrative prose from the retrieval corpus.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET


PARSER_VERSION = "greenfin-jats-parser/1.0.0"
PARSED_DOCUMENT_SCHEMA_VERSION = "greenfin-parsed-jats/1.0.0"
PARSED_BATCH_SCHEMA_VERSION = "greenfin-parsed-batch/1.0.0"
CHUNK_SCHEMA_VERSION = "greenfin-chunk/1.0.0"
CHUNKING_RULE_VERSION = "jats-block-word-window-cs01"
EXCLUSION_RULE_VERSION = "jats-nonresearch-exclusion/1.0.0"
DEFAULT_MAX_WORDS = 180
DEFAULT_OVERLAP_WORDS = 30

_DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.I)
_DATE_IN_PATH = re.compile(r"(?P<year>20\d{2})-(?P<month>\d{2})-(?P<day>\d{2})")
_PMCID_VERSION = re.compile(r"^PMC\d+\.(?P<version>\d+)$", re.I)
_SAFE_RELEASE_PART = re.compile(r"[^a-z0-9._-]+")

# Section-title rules are intentionally anchored.  A research section such as
# "funding constraints as a mechanism" must not be discarded merely because it
# contains the word "funding".
_SECTION_EXCLUSION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("acknowledgements", re.compile(r"^acknowledg(?:e)?ments?$", re.I)),
    ("funding", re.compile(r"^(?:fund|funding|funding statement|financial support)$", re.I)),
    (
        "author_contributions",
        re.compile(
            r"^(?:credit authorship contribution statement|author(?:s|['’]s)? "
            r"contributions?(?: statement)?|contributor information)$",
            re.I,
        ),
    ),
    (
        "declarations",
        re.compile(
            r"^(?:declarations?|declaration of competing interests?|competing interests?|"
            r"conflicts? of interests?|disclosure(?: statement)?|ethics(?: approval)?(?: statement)?|"
            r"consent(?: for publication)?(?: statement)?)$",
            re.I,
        ),
    ),
    ("data_availability", re.compile(r"^data availability(?: statement)?$", re.I)),
    (
        "supplementary_material",
        re.compile(r"^(?:supporting information|supplementary (?:data|information|materials?))$", re.I),
    ),
    ("associated_data", re.compile(r"^associated data$", re.I)),
)

_SEC_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("acknowledgements", ("ack", "acknowledgment", "acknowledgement")),
    ("funding", ("fund", "funding")),
    ("author_contributions", ("author-contributions", "contrib-info")),
    ("declarations", ("coi-statement", "conflict-of-interest", "declarations")),
    ("data_availability", ("data-availability", "data-availability-statement")),
    ("supplementary_material", ("supplementary-material", "supplementary-materials")),
    ("associated_data", ("associated-data",)),
)

_CONTAINER_EXCLUSIONS: dict[str, str] = {
    "ack": "acknowledgements",
    "funding-group": "funding",
    "author-notes": "author_notes",
    "fn-group": "footnotes",
    "permissions": "rights_metadata",
    "supplementary-material": "supplementary_material",
    "supplementary-materials": "supplementary_material",
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _stable_id(prefix: str, material: object, length: int) -> str:
    return f"{prefix}{_sha256_text(_canonical_json(material))[:length]}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_tex_math(value: str) -> str:
    """Return only the formula body from PMC's standalone TeX wrappers.

    Some Europe PMC JATS records embed a complete compilable TeX document for
    every inline symbol.  Indexing that wrapper repeats package names hundreds
    of times and overwhelms semantic retrieval.  The source formula is kept as
    compact LaTeX; only rendering boilerplate and spacing commands are removed.
    """

    raw = value.strip()
    document_match = re.search(
        r"\\begin\s*\{document\}(.*?)(?:\\end\s*\{document\}|$)",
        raw,
        flags=re.I | re.S,
    )
    core = document_match.group(1) if document_match else raw
    if document_match is None:
        kept_lines = []
        for line in core.splitlines():
            stripped = line.strip()
            if re.match(
                r"^\\(?:documentclass|usepackage|setlength|pagestyle|thispagestyle)\b",
                stripped,
                flags=re.I,
            ):
                continue
            kept_lines.append(line)
        core = " ".join(kept_lines)
    core = re.sub(r"\\(?:begin|end)\s*\{document\}", " ", core, flags=re.I)
    core = core.strip()
    core = re.sub(r"^\$\$?|\$\$?$", "", core).strip()
    core = re.sub(r"^\\\[|\\\]$|^\\\(|\\\)$", "", core).strip()
    core = re.sub(r"\\[,:;!]", " ", core)
    core = re.sub(r"\\(?:quad|qquad)\b", " ", core)
    core = re.sub(r"\\(?:left|right)(?![A-Za-z])", "", core)
    core = _normalize_space(core)
    # A final defensive gate prevents a malformed wrapper from leaking into
    # chunks even if its exact formatting differs from the known PMC pattern.
    if re.search(r"\\(?:documentclass|usepackage|begin\s*\{document\})", core, flags=re.I):
        core = re.sub(r"\\documentclass(?:\[[^]]*\])?\s*\{[^}]*\}", " ", core, flags=re.I)
        core = re.sub(r"\\usepackage(?:\[[^]]*\])?\s*\{[^}]*\}", " ", core, flags=re.I)
        core = re.sub(r"\\(?:begin|end)\s*\{document\}", " ", core, flags=re.I)
        core = _normalize_space(core)
    return core


def _mathml_text(element: ET.Element) -> str:
    tex_annotation = next(
        (
            node
            for node in element.iter()
            if _local_name(node.tag) == "annotation"
            and "tex" in node.attrib.get("encoding", "").casefold()
        ),
        None,
    )
    if tex_annotation is not None:
        return _clean_tex_math("".join(tex_annotation.itertext()))

    def visible(node: ET.Element) -> str:
        if _local_name(node.tag) in {"annotation", "annotation-xml"}:
            return ""
        parts = [node.text or ""]
        for child in node:
            parts.append(visible(child))
            parts.append(child.tail or "")
        return "".join(parts)

    return _normalize_space(visible(element))


def _semantic_xml_text(element: ET.Element) -> str:
    """Extract element text while collapsing formula alternatives once."""

    tag = _local_name(element.tag)
    if tag == "tex-math":
        core = _clean_tex_math("".join(element.itertext()))
        return f" {core} " if core else " "
    if tag == "math":
        core = _mathml_text(element)
        return f" {core} " if core else " "
    if tag == "alternatives":
        tex = next((child for child in element if _local_name(child.tag) == "tex-math"), None)
        math = next((child for child in element if _local_name(child.tag) == "math"), None)
        if tex is not None:
            return _semantic_xml_text(tex)
        if math is not None:
            return _semantic_xml_text(math)

    parts = [element.text or ""]
    for child in element:
        parts.append(_semantic_xml_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _element_text(element: ET.Element | None) -> str:
    return _normalize_space(_semantic_xml_text(element)) if element is not None else ""


def _direct_child(element: ET.Element | None, tag: str) -> ET.Element | None:
    if element is None:
        return None
    return next((child for child in element if _local_name(child.tag) == tag), None)


def _first_descendant(
    element: ET.Element,
    tag: str,
    *,
    attribute: str | None = None,
    value: str | None = None,
) -> ET.Element | None:
    for candidate in element.iter():
        if _local_name(candidate.tag) != tag:
            continue
        if attribute is None or candidate.attrib.get(attribute) == value:
            return candidate
    return None


def _descendants(element: ET.Element, tag: str) -> Iterable[ET.Element]:
    return (candidate for candidate in element.iter() if _local_name(candidate.tag) == tag)


def _element_paths(root: ET.Element) -> dict[ET.Element, str]:
    """Build namespace-agnostic, sibling-indexed XPath locators."""

    paths: dict[ET.Element, str] = {root: f"/{_local_name(root.tag)}[1]"}

    def walk(parent: ET.Element) -> None:
        counts: Counter[str] = Counter()
        for child in parent:
            tag = _local_name(child.tag)
            counts[tag] += 1
            paths[child] = f"{paths[parent]}/{tag}[{counts[tag]}]"
            walk(child)

    walk(root)
    return paths


def _normalized_doi(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    match = _DOI_PATTERN.search(normalized)
    return match.group(0).rstrip(".,;)").casefold() if match else None


def _pmc_document_version(root: ET.Element, pmcid: str) -> tuple[str, str]:
    version_node = _first_descendant(root, "article-id", attribute="pub-id-type", value="pmcid-ver")
    pmcid_version = _element_text(version_node) or f"{pmcid}.1"
    match = _PMCID_VERSION.fullmatch(pmcid_version)
    version = int(match.group("version")) if match else 1
    return f"v{version:03d}", pmcid_version


def _section_exclusion(title: str, sec_type: str | None) -> str | None:
    normalized_title = _normalize_space(title).rstrip(".:")
    normalized_type = (sec_type or "").casefold().replace("_", "-").strip()
    for category, candidates in _SEC_TYPE_RULES:
        if any(candidate == normalized_type or candidate in normalized_type.split("|") for candidate in candidates):
            return category
    for category, pattern in _SECTION_EXCLUSION_RULES:
        if pattern.fullmatch(normalized_title):
            return category
    return None


def _table_text(element: ET.Element) -> str:
    parts: list[str] = []
    label = _element_text(_direct_child(element, "label"))
    caption = _element_text(_direct_child(element, "caption"))
    if label:
        parts.append(label)
    if caption:
        parts.append(caption)
    for row in _descendants(element, "tr"):
        cells = [
            _element_text(cell)
            for cell in row
            if _local_name(cell.tag) in {"th", "td"} and _element_text(cell)
        ]
        if cells:
            parts.append(" | ".join(cells))
    return _normalize_space(" \n ".join(parts))


def _figure_text(element: ET.Element) -> str:
    label = _element_text(_direct_child(element, "label"))
    caption = _element_text(_direct_child(element, "caption"))
    return _normalize_space(" | ".join(part for part in (label, caption) if part))


def _candidate_text_blocks(element: ET.Element) -> list[tuple[ET.Element, str, str]]:
    """Return non-overlapping auditable text blocks inside an excluded subtree."""

    candidates: list[tuple[ET.Element, str, str]] = []

    def walk(node: ET.Element) -> None:
        tag = _local_name(node.tag)
        if tag == "p":
            text = _element_text(node)
            if text:
                candidates.append((node, "paragraph", text))
            return
        if tag == "table-wrap":
            text = _table_text(node)
            if text:
                candidates.append((node, "table", text))
            return
        if tag == "fig":
            text = _figure_text(node)
            if text:
                candidates.append((node, "figure_caption", text))
            return
        for child in node:
            walk(child)

    walk(element)
    if not candidates:
        text = _element_text(element)
        if text:
            candidates.append((element, _local_name(element.tag), text))
    return candidates


def _published_date(root: ET.Element) -> str | None:
    dates = [node for node in _descendants(root, "pub-date")]
    preferred = sorted(
        dates,
        key=lambda node: 0 if node.attrib.get("pub-type") in {"epub", "electronic"} else 1,
    )
    for node in preferred:
        year = _element_text(_direct_child(node, "year"))
        month = _element_text(_direct_child(node, "month"))
        day = _element_text(_direct_child(node, "day"))
        if not year:
            continue
        try:
            return f"{int(year):04d}-{int(month or '1'):02d}-{int(day or '1'):02d}"
        except ValueError:
            continue
    return None


def _authors(root: ET.Element) -> list[str]:
    authors: list[str] = []
    for contrib in _descendants(root, "contrib"):
        if contrib.attrib.get("contrib-type", "author") != "author":
            continue
        name = _direct_child(contrib, "name")
        if name is None:
            continue
        given = _element_text(_direct_child(name, "given-names"))
        surname = _element_text(_direct_child(name, "surname"))
        full_name = _normalize_space(" ".join(part for part in (given, surname) if part))
        if full_name and full_name not in authors:
            authors.append(full_name)
    return authors


def _references(root: ET.Element) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for ref in _descendants(root, "ref"):
        text = _element_text(ref)
        if not text:
            continue
        doi_node = next(
            (
                node
                for node in ref.iter()
                if _local_name(node.tag) == "pub-id" and node.attrib.get("pub-id-type") == "doi"
            ),
            None,
        )
        doi = _normalized_doi(_element_text(doi_node))
        if doi is None:
            doi = _normalized_doi(text)
        title = _element_text(_first_descendant(ref, "article-title")) or None
        year_text = _element_text(_first_descendant(ref, "year"))
        references.append(
            {
                "reference_id": ref.attrib.get("id"),
                "title": title,
                "year": int(year_text) if year_text.isdigit() else None,
                "doi": doi,
                "text": text,
                "text_sha256": _sha256_text(text),
            }
        )
    return references


def parse_jats_article(
    xml_path: Path | str,
    manifest_item: Mapping[str, Any],
    *,
    release_id: str,
    batch_id: str,
    retrieved_at: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse one verified JATS XML asset and return document plus exclusions."""

    source = Path(xml_path)
    raw = source.read_bytes()
    raw_sha256 = _sha256_bytes(raw)
    expected_sha256 = str(manifest_item.get("raw_sha256") or "").casefold()
    if expected_sha256 and expected_sha256 != raw_sha256:
        raise ValueError(f"{source}: raw_sha256 does not match the source manifest")
    expected_bytes = manifest_item.get("bytes")
    if isinstance(expected_bytes, int) and expected_bytes != len(raw):
        raise ValueError(f"{source}: byte count does not match the source manifest")

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"{source}: invalid JATS XML: {exc}") from exc
    if _local_name(root.tag) != "article":
        raise ValueError(f"{source}: root element must be article")
    element_paths = _element_paths(root)

    xml_doi = _normalized_doi(
        _element_text(_first_descendant(root, "article-id", attribute="pub-id-type", value="doi"))
    )
    manifest_doi = _normalized_doi(str(manifest_item.get("doi") or ""))
    if xml_doi and manifest_doi and xml_doi != manifest_doi:
        raise ValueError(f"{source}: DOI differs between XML and manifest")
    doi = xml_doi or manifest_doi
    if doi is None:
        raise ValueError(f"{source}: a DOI is required for the pilot document_id")

    xml_pmcid = _element_text(
        _first_descendant(root, "article-id", attribute="pub-id-type", value="pmcid")
    ).upper()
    pmcid = str(manifest_item.get("pmcid") or xml_pmcid).upper()
    if not pmcid or (xml_pmcid and xml_pmcid != pmcid):
        raise ValueError(f"{source}: PMCID differs between XML and manifest")

    document_id = f"doi:{doi}"
    document_version, pmcid_version = _pmc_document_version(root, pmcid)
    asset_id = f"asset:epmc:{pmcid.casefold()}:fulltext-xml:{raw_sha256[:16]}"
    source_uri = str(manifest_item.get("source_url") or f"https://europepmc.org/articles/{pmcid}")
    access_level = str(manifest_item.get("access_level") or "unknown")
    license_value = str(manifest_item.get("license") or "").strip()
    rights_status = str(manifest_item.get("rights_status") or "unknown")

    blocks: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    audited_containers: set[int] = set()

    def source_ref(xml_id: str | None) -> str:
        return f"{source_uri}#{xml_id}" if xml_id else source_uri

    def add_block(
        text: str,
        block_type: str,
        section_path: Sequence[str],
        source_element: ET.Element,
    ) -> None:
        normalized = _normalize_space(text)
        if len(normalized) < 12:
            return
        ordinal = len(blocks) + 1
        section_values = list(section_path) or ["Body"]
        section = " / ".join(section_values)
        block_source_type = (
            "paper_abstract"
            if section_values[0].casefold().startswith("abstract")
            else "paper_fulltext"
        )
        xml_id = source_element.attrib.get("id")
        xml_path = element_paths[source_element]
        content_hash = _sha256_text(normalized)
        block_id = _stable_id(
            "blk_",
            {
                "document_id": document_id,
                "document_version": document_version,
                "raw_sha256": raw_sha256,
                "ordinal": ordinal,
                "block_type": block_type,
                "source_type": block_source_type,
                "section_path": section_values,
                "xml_id": xml_id,
                "xml_path": xml_path,
                "text_sha256": content_hash,
            },
            24,
        )
        blocks.append(
            {
                "block_id": block_id,
                "ordinal": ordinal,
                "block_type": block_type,
                "source_type": block_source_type,
                "section": section,
                "section_path": section_values,
                "xml_id": xml_id,
                "xml_path": xml_path,
                "source_ref": source_ref(xml_id),
                "text": normalized,
                "text_sha256": content_hash,
            }
        )

    def audit_excluded(
        element: ET.Element,
        category: str,
        section_path: Sequence[str],
        *,
        reason: str,
    ) -> None:
        audited_containers.add(id(element))
        section_values = list(section_path) or ["Administrative matter"]
        section = " / ".join(section_values)
        for node, block_type, text in _candidate_text_blocks(element):
            xml_id = node.attrib.get("id") or element.attrib.get("id")
            xml_path = element_paths[node]
            text_hash = _sha256_text(text)
            excluded_id = _stable_id(
                "xcl_",
                {
                    "document_id": document_id,
                    "document_version": document_version,
                    "category": category,
                    "section": section,
                    "xml_id": xml_id,
                    "xml_path": xml_path,
                    "text_sha256": text_hash,
                },
                24,
            )
            exclusions.append(
                {
                    "schema_version": "greenfin-excluded-block/1.0.0",
                    "excluded_block_id": excluded_id,
                    "release_id": release_id,
                    "batch_id": batch_id,
                    "document_id": document_id,
                    "document_version": document_version,
                    "asset_id": asset_id,
                    "doi": doi,
                    "pmcid": pmcid,
                    "raw_sha256": raw_sha256,
                    "category": category,
                    "reason": reason,
                    "element_type": block_type,
                    "xml_id": xml_id,
                    "xml_path": xml_path,
                    "section": section,
                    "section_path": section_values,
                    "source_ref": source_ref(xml_id),
                    "char_count": len(text),
                    "text_sha256": text_hash,
                    "text_preview": text[:240],
                }
            )

    def walk(element: ET.Element, section_path: Sequence[str]) -> None:
        for child in element:
            tag = _local_name(child.tag)
            if tag in {"title", "label"}:
                continue
            if tag == "sec":
                title = _element_text(_direct_child(child, "title"))
                child_path = list(section_path) + ([title] if title else [])
                category = _section_exclusion(title, child.attrib.get("sec-type"))
                if category:
                    audit_excluded(
                        child,
                        category,
                        child_path,
                        reason=f"section excluded by {EXCLUSION_RULE_VERSION}",
                    )
                else:
                    walk(child, child_path)
                continue
            container_category = _CONTAINER_EXCLUSIONS.get(tag)
            if container_category:
                audit_excluded(
                    child,
                    container_category,
                    section_path,
                    reason=f"<{tag}> excluded by {EXCLUSION_RULE_VERSION}",
                )
                continue
            if tag == "p":
                add_block(_element_text(child), "paragraph", section_path, child)
            elif tag == "table-wrap":
                add_block(_table_text(child), "table", section_path, child)
            elif tag == "fig":
                add_block(_figure_text(child), "figure_caption", section_path, child)
            elif tag not in {"ref-list", "back"}:
                walk(child, section_path)

    for abstract in _descendants(root, "abstract"):
        # Skip translated/graphical abstracts only when they have no paragraphs;
        # otherwise retain their independently locatable research text.
        abstract_type = abstract.attrib.get("abstract-type", "").strip()
        label = "Abstract" if not abstract_type else f"Abstract [{abstract_type}]"
        walk(abstract, [label])

    body = _first_descendant(root, "body")
    if body is None:
        raise ValueError(f"{source}: JATS body is missing")
    walk(body, ["Body"])
    if not blocks:
        raise ValueError(f"{source}: no research-semantic text blocks were extracted")

    # Audit administrative containers outside the body.  Skip descendants of a
    # container already audited as a unit, preventing duplicate log entries.
    parent_map = {child: parent for parent in root.iter() for child in parent}
    body_nodes = set(body.iter())
    for candidate in root.iter():
        if candidate in body_nodes or id(candidate) in audited_containers:
            continue
        tag = _local_name(candidate.tag)
        title = _element_text(_direct_child(candidate, "title")) if tag == "sec" else ""
        category = (
            _section_exclusion(title, candidate.attrib.get("sec-type"))
            if tag == "sec"
            else _CONTAINER_EXCLUSIONS.get(tag)
        )
        if not category:
            continue
        ancestor = parent_map.get(candidate)
        already_covered = False
        while ancestor is not None:
            if id(ancestor) in audited_containers:
                already_covered = True
                break
            ancestor = parent_map.get(ancestor)
        if already_covered:
            continue
        audit_excluded(
            candidate,
            category,
            [title] if title else [tag],
            reason=f"<{tag}> outside body excluded by {EXCLUSION_RULE_VERSION}",
        )

    document_offset = 0
    for block in blocks:
        block["document_char_start"] = document_offset
        block["document_char_end"] = document_offset + len(block["text"])
        document_offset = block["document_char_end"] + 2

    title = _element_text(_first_descendant(root, "article-title")) or str(manifest_item.get("title") or "")
    journal = _element_text(_first_descendant(root, "journal-title")) or str(manifest_item.get("journal") or "")
    authors = _authors(root) or [str(item) for item in manifest_item.get("authors", []) if str(item).strip()]
    published_date = _published_date(root)
    year = int(published_date[:4]) if published_date else manifest_item.get("year")
    pmid = _element_text(_first_descendant(root, "article-id", attribute="pub-id-type", value="pmid")) or None
    references = _references(root)
    exclusion_counts = Counter(item["category"] for item in exclusions)

    document = {
        "schema_version": PARSED_DOCUMENT_SCHEMA_VERSION,
        "parser": {
            "name": "greenfin-jats-parser",
            "version": PARSER_VERSION,
            "exclusion_rule_version": EXCLUSION_RULE_VERSION,
        },
        "release_id": release_id,
        "batch_id": batch_id,
        "document_id": document_id,
        "document_version": document_version,
        "asset_id": asset_id,
        "source_type": "paper_fulltext",
        "access_level": access_level,
        "license": license_value,
        "rights_status": rights_status,
        "source_uri": source_uri,
        "retrieved_at": retrieved_at,
        "metadata": {
            "doi": doi,
            "pmcid": pmcid,
            "pmcid_version": pmcid_version,
            "pmid": pmid,
            "title": title,
            "authors": authors,
            "journal": journal,
            "year": year,
            "published_date": published_date,
            "language": root.attrib.get("{http://www.w3.org/XML/1998/namespace}lang", "en"),
        },
        "raw_asset": {
            "file": source.name,
            "bytes": len(raw),
            "sha256": raw_sha256,
            "media_type": "application/xml",
        },
        "parse_quality": {
            "status": "ok",
            "source_format": "JATS XML",
            "page_numbers_available": False,
            "locator_strategy": "section_path + XML id + normalized-block character offsets",
            "block_count": len(blocks),
            "reference_count": len(references),
            "excluded_block_count": len(exclusions),
            "excluded_by_category": dict(sorted(exclusion_counts.items())),
        },
        "blocks": blocks,
        "references": references,
    }
    return document, exclusions


def make_chunks(
    document: Mapping[str, Any],
    *,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[dict[str, Any]]:
    """Create stable word-window chunks without crossing parsed block borders."""

    if max_words < 20:
        raise ValueError("max_words must be at least 20")
    if overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("overlap_words must be non-negative and smaller than max_words")
    step = max_words - overlap_words
    chunks: list[dict[str, Any]] = []
    for block in document["blocks"]:
        text = str(block["text"])
        spans = list(re.finditer(r"\S+", text))
        if not spans:
            continue
        starts = [0] if len(spans) <= max_words else list(range(0, len(spans), step))
        windows: list[tuple[int, int, int, int]] = []
        for word_start in starts:
            word_end = min(len(spans), word_start + max_words)
            start_char = spans[word_start].start()
            end_char = spans[word_end - 1].end()
            windows.append((word_start, word_end, start_char, end_char))
            if word_end == len(spans):
                break
        for part_index, (word_start, word_end, start_char, end_char) in enumerate(windows, start=1):
            chunk_text = text[start_char:end_char]
            text_sha256 = _sha256_text(chunk_text)
            locator = {
                "coordinate_system": "normalized_block_text",
                "block_id": block["block_id"],
                "section": block["section"],
                "section_path": list(block["section_path"]),
                "xml_id": block.get("xml_id"),
                "xml_path": block["xml_path"],
                "start_char": start_char,
                "end_char": end_char,
                "document_start_char": block["document_char_start"] + start_char,
                "document_end_char": block["document_char_start"] + end_char,
                "source_ref": block["source_ref"],
            }
            chunk_id = _stable_id(
                "chk_",
                {
                    "chunking_rule": CHUNKING_RULE_VERSION,
                    "document_id": document["document_id"],
                    "document_version": document["document_version"],
                    "raw_sha256": document["raw_asset"]["sha256"],
                    "block_id": block["block_id"],
                    "start_char": start_char,
                    "end_char": end_char,
                    "text_sha256": text_sha256,
                },
                24,
            )
            evidence_id = _stable_id(
                "evd:",
                {
                    "document_id": document["document_id"],
                    "document_version": document["document_version"],
                    "chunk_id": chunk_id,
                    "locator": locator,
                    "text_sha256": text_sha256,
                },
                20,
            )
            chunks.append(
                {
                    "schema_version": CHUNK_SCHEMA_VERSION,
                    "chunk_schema_version": CHUNKING_RULE_VERSION,
                    "chunk_id": chunk_id,
                    "evidence_id": evidence_id,
                    "release_id": document["release_id"],
                    "batch_id": document["batch_id"],
                    "document_id": document["document_id"],
                    "document_version": document["document_version"],
                    "asset_id": document["asset_id"],
                    "doi": document["metadata"]["doi"],
                    "pmcid": document["metadata"]["pmcid"],
                    "source_type": block.get("source_type", "paper_fulltext"),
                    "access_level": document["access_level"],
                    "license": document["license"],
                    "rights_status": document["rights_status"],
                    "content_sha256": document["raw_asset"]["sha256"],
                    "raw_sha256": document["raw_asset"]["sha256"],
                    "block_id": block["block_id"],
                    "block_type": block["block_type"],
                    "section": block["section"],
                    "section_path": list(block["section_path"]),
                    "xml_id": block.get("xml_id"),
                    "xml_path": block["xml_path"],
                    "locator": locator,
                    "source_ref": block["source_ref"],
                    "part_index": part_index,
                    "part_count": len(windows),
                    "word_start": word_start,
                    "word_end": word_end,
                    "word_count": word_end - word_start,
                    "text": chunk_text,
                    "text_sha256": text_sha256,
                    "content_hash": text_sha256,
                    "chunk_label": "research_semantic",
                    "qc_status": "pass",
                    "retrieved_at": document["retrieved_at"],
                }
            )
    return chunks


def _derive_batch_id(manifest_path: Path) -> str:
    match = _DATE_IN_PATH.search(str(manifest_path))
    date = "".join(match.group("year", "month", "day")) if match else "unknown"
    return f"batch-{date}-001"


def _derive_release_id(manifest_path: Path, manifest_sha256: str) -> str:
    run_name = manifest_path.parent.parent.name.casefold()
    safe_run = _SAFE_RELEASE_PART.sub("-", run_name).strip("-") or "jats-batch"
    return f"release:{safe_run}:{manifest_sha256[:16]}"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(_canonical_json(value) + "\n")


def build_parsed_batch(
    manifest_path: Path | str,
    output_dir: Path | str,
    *,
    release_id: str | None = None,
    batch_id: str | None = None,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
    build_timestamp: str | None = None,
) -> dict[str, Any]:
    """Parse every verified XML item in a source manifest and write outputs."""

    manifest_source = Path(manifest_path)
    output = Path(output_dir)
    raw_manifest = manifest_source.read_bytes()
    manifest_sha256 = _sha256_bytes(raw_manifest)
    try:
        source_manifest = json.loads(raw_manifest.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{manifest_source}: invalid JSON manifest") from exc
    items = source_manifest.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError(f"{manifest_source}: items must be a non-empty array")
    expected_count = source_manifest.get("record_count")
    if isinstance(expected_count, int) and expected_count != len(items):
        raise ValueError(f"{manifest_source}: record_count does not match items")

    release_id = release_id or _derive_release_id(manifest_source, manifest_sha256)
    batch_id = batch_id or _derive_batch_id(manifest_source)
    retrieved_at = str(source_manifest.get("retrieved_at") or datetime.now(timezone.utc).isoformat())
    # Defaulting to the immutable source-batch timestamp makes the generated
    # files byte-for-byte reproducible for identical input and configuration.
    generated_at = build_timestamp or retrieved_at

    parsed_documents: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    seen_documents: set[tuple[str, str]] = set()
    seen_assets: set[str] = set()

    for item_number, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{manifest_source}: item {item_number} must be an object")
        raw_file = item.get("raw_file")
        if not isinstance(raw_file, str) or not raw_file.strip():
            raise ValueError(f"{manifest_source}: item {item_number} has no raw_file")
        xml_path = manifest_source.parent / raw_file
        document, document_exclusions = parse_jats_article(
            xml_path,
            item,
            release_id=release_id,
            batch_id=batch_id,
            retrieved_at=retrieved_at,
        )
        identity = (document["document_id"], document["document_version"])
        if identity in seen_documents:
            raise ValueError(f"duplicate document/version in manifest: {identity}")
        if document["asset_id"] in seen_assets:
            raise ValueError(f"duplicate asset_id in manifest: {document['asset_id']}")
        seen_documents.add(identity)
        seen_assets.add(document["asset_id"])
        document_chunks = make_chunks(
            document,
            max_words=max_words,
            overlap_words=overlap_words,
        )
        document["parse_quality"]["chunk_count"] = len(document_chunks)
        parsed_documents.append(document)
        chunks.extend(document_chunks)
        exclusions.extend(document_exclusions)

    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    evidence_ids = [chunk["evidence_id"] for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("chunk_id collision in parsed batch")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("evidence_id collision in parsed batch")

    output.mkdir(parents=True, exist_ok=True)
    document_entries: list[dict[str, Any]] = []
    chunk_counts = Counter(chunk["document_id"] for chunk in chunks)
    for document in parsed_documents:
        parsed_file = f"{document['metadata']['pmcid']}.parsed.json"
        parsed_path = output / parsed_file
        _write_json(parsed_path, document)
        document_entries.append(
            {
                "document_id": document["document_id"],
                "document_version": document["document_version"],
                "doi": document["metadata"]["doi"],
                "pmcid": document["metadata"]["pmcid"],
                "asset_id": document["asset_id"],
                "raw_file": document["raw_asset"]["file"],
                "raw_sha256": document["raw_asset"]["sha256"],
                "parsed_file": parsed_file,
                "parsed_sha256": _sha256_bytes(parsed_path.read_bytes()),
                "block_count": document["parse_quality"]["block_count"],
                "chunk_count": chunk_counts[document["document_id"]],
                "reference_count": document["parse_quality"]["reference_count"],
                "excluded_block_count": document["parse_quality"]["excluded_block_count"],
                "status": "ok",
            }
        )

    chunks_path = output / "chunks.jsonl"
    exclusions_path = output / "excluded_blocks.jsonl"
    _write_jsonl(chunks_path, chunks)
    _write_jsonl(exclusions_path, exclusions)
    excluded_counts = Counter(item["category"] for item in exclusions)
    chunk_source_type_counts = Counter(item["source_type"] for item in chunks)
    config = {
        "chunk_schema_version": CHUNK_SCHEMA_VERSION,
        "chunking_rule_version": CHUNKING_RULE_VERSION,
        "max_words": max_words,
        "overlap_words": overlap_words,
        "exclusion_rule_version": EXCLUSION_RULE_VERSION,
    }
    output_manifest = {
        "schema_version": PARSED_BATCH_SCHEMA_VERSION,
        "parser": {"name": "greenfin-jats-parser", "version": PARSER_VERSION},
        "generated_at": generated_at,
        "batch_id": batch_id,
        "release_id": release_id,
        "source_manifest": str(manifest_source.as_posix()),
        "source_manifest_sha256": manifest_sha256,
        "source_schema_version": source_manifest.get("schema_version"),
        "source": source_manifest.get("source"),
        "retrieved_at": retrieved_at,
        "parser_config": config,
        "parser_config_sha256": _sha256_text(_canonical_json(config)),
        "document_count": len(parsed_documents),
        "block_count": sum(len(document["blocks"]) for document in parsed_documents),
        "chunk_count": len(chunks),
        "excluded_block_count": len(exclusions),
        "excluded_by_category": dict(sorted(excluded_counts.items())),
        "chunk_source_type_counts": dict(sorted(chunk_source_type_counts.items())),
        "exclusion_policy": {
            "scope": "non-research administrative text is excluded from retrieval chunks and retained in excluded_blocks.jsonl",
            "data_availability": "excluded from strong-semantic chunks; retained in the audit log for later feasibility-specific retrieval",
            "abstracts": "retained as paper_abstract and therefore cannot satisfy paper_fulltext strong-evidence gates",
        },
        "chunks_file": chunks_path.name,
        "chunks_sha256": _sha256_bytes(chunks_path.read_bytes()),
        "excluded_blocks_file": exclusions_path.name,
        "excluded_blocks_sha256": _sha256_bytes(exclusions_path.read_bytes()),
        "id_chain": "doi document_id -> PMC source version -> block_id -> chunk_id -> evidence_id",
        "documents": document_entries,
    }
    _write_json(output / "manifest.json", output_manifest)
    return output_manifest


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse a verified JATS XML manifest into standard chunks")
    parser.add_argument("--manifest", type=Path, required=True, help="input full-text manifest.json")
    parser.add_argument("--output-dir", type=Path, required=True, help="output C_parsed directory")
    parser.add_argument("--release-id", help="override the deterministic batch release_id")
    parser.add_argument("--batch-id", help="override the batch_id")
    parser.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS)
    parser.add_argument("--overlap-words", type=int, default=DEFAULT_OVERLAP_WORDS)
    parser.add_argument(
        "--build-timestamp",
        help="fixed ISO-8601 manifest timestamp; defaults to the source retrieved_at for deterministic reruns",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    manifest = build_parsed_batch(
        args.manifest,
        args.output_dir,
        release_id=args.release_id,
        batch_id=args.batch_id,
        max_words=args.max_words,
        overlap_words=args.overlap_words,
        build_timestamp=args.build_timestamp,
    )
    print(
        _canonical_json(
            {
                "status": "ok",
                "release_id": manifest["release_id"],
                "document_count": manifest["document_count"],
                "block_count": manifest["block_count"],
                "chunk_count": manifest["chunk_count"],
                "excluded_block_count": manifest["excluded_block_count"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
