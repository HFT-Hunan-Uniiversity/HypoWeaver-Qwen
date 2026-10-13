"""Known source metadata is attribution, not a model-generated quantitative result."""

import re

QUOTED = re.compile(r'“([^”\n]+)”|《([^》\n]+)》|"([^"\n]+)"')
YEAR = re.compile(r"[（(]\s*(\d{4})\s*[）)]")


def source_year(source):
    match = YEAR.search(source.get("citation") or "")
    return int(match[1]) if match else None


def validation_metadata(snapshot):
    dataset = snapshot.get("dataset") or {}
    source = dataset.get("source") or {}
    citation = source.get("citation") or ""
    titles = [dataset.get("name", "")]
    titles.extend(next(part for part in match.groups() if part) for match in QUOTED.finditer(citation))
    literals = [source.get(key, "") for key in ("license", "doi", "url", "citation")]
    citations = []
    match = YEAR.search(citation)
    if match:
        author = citation[: match.start()].strip().rstrip(",，")
        citations.extend((name, match[1]) for name in (author, author.split(",")[0].strip()) if name)
    for card in snapshot.get("evidence", []):
        titles.append(card.get("title", ""))
        literals.append(card.get("doi", ""))
        if card.get("year"):
            for author in card.get("authors") or []:
                if isinstance(author, str) and author.strip():
                    citations.append((author, str(card["year"])))
    return {"titles": [t for t in titles if t], "literals": [v for v in literals if v], "citations": citations}


def without_metadata(text, metadata):
    for value in sorted(set(metadata["titles"] + metadata["literals"]), key=len, reverse=True):
        # Do not turn a registered DOI/version into a prefix exemption for a different one.
        pattern = (r"(?<![A-Za-z0-9_])" if value[0].isascii() and value[0].isalnum() else "") + re.escape(value)
        if value[-1].isascii() and value[-1].isalnum():
            pattern += r"(?![A-Za-z0-9_])"
        text = re.sub(pattern, " ", text)
    for author, year in metadata["citations"]:
        text = re.sub(re.escape(author) + r"\s*[（(]\s*" + re.escape(year) + r"\s*[）)]", " ", text)
    return text
