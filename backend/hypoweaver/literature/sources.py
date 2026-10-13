import asyncio
import html
import re
import unicodedata
import httpx


def doi_normalize(value):
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", (value or "").strip(), flags=re.I).lower() or None


def title_key(title, year):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", title).lower()), year


def restore_abstract(index):
    words = [(position, word) for word, positions in (index or {}).items() for position in positions]
    return " ".join(word for _, word in sorted(words)) or None


def openalex_card(item):
    location = item.get("primary_location") or {}
    return dict(
        source="openalex",
        sources=["openalex"],
        doi=doi_normalize(item.get("doi")),
        title=item.get("title") or item.get("display_name") or "无标题",
        authors=[a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])],
        year=item.get("publication_year"),
        venue=(location.get("source") or {}).get("display_name", ""),
        cited_by=item.get("cited_by_count"),
        abstract=restore_abstract(item.get("abstract_inverted_index")),
        concepts=[
            c["display_name"] for c in item.get("concepts", []) + item.get("topics", []) if c.get("display_name")
        ],
    )


def crossref_card(item):
    date = (item.get("issued") or item.get("published") or {}).get("date-parts", [[]])
    abstract = html.unescape(re.sub(r"<[^>]+>", " ", item.get("abstract") or "")).strip() or None
    return dict(
        source="crossref",
        sources=["crossref"],
        doi=doi_normalize(item.get("DOI")),
        title=(item.get("title") or ["无标题"])[0],
        authors=[
            " ".join(filter(None, [a.get("given"), a.get("family")])) or a.get("name", "")
            for a in item.get("author", [])
        ],
        year=date[0][0] if date and date[0] else None,
        venue=(item.get("container-title") or [""])[0],
        cited_by=item.get("is-referenced-by-count"),
        abstract=abstract,
        concepts=item.get("subject", []),
    )


def merge_cards(cards):
    merged, dois, titles = [], {}, {}
    for card in cards:
        card = {**card, "doi": doi_normalize(card.get("doi"))}
        title = title_key(card["title"], card.get("year"))
        match = dois.get(card["doi"]) if card["doi"] else titles.get(title)
        if match is None and title in titles and not merged[titles[title]].get("doi"):
            match = titles[title]
        if match is None:
            match = len(merged)
            merged.append(card)
        else:
            existing = merged[match]
            if "_relevance" in card:
                existing["_relevance"] = existing.get("_relevance", 0) + card["_relevance"]
            existing["sources"] = sorted(
                set(existing.get("sources", [existing["source"]]) + card.get("sources", [card["source"]]))
            )
            for key in ["doi", "authors", "year", "venue", "abstract", "fulltext_excerpt"]:
                if not existing.get(key) and card.get(key):
                    existing[key] = card[key]
            existing["concepts"] = sorted(set(existing.get("concepts", []) + card.get("concepts", [])))
            if card.get("cited_by") is not None:
                existing["cited_by"] = max(existing.get("cited_by") or 0, card["cited_by"])
        if card["doi"]:
            dois[card["doi"]] = match
        titles[title] = match
    return merged


class LiteratureClient:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    async def search(self, source, queries):
        settings = self.settings
        cards, errors, query_log = [], [], []
        url = settings.openalex_url if source == "openalex" else settings.crossref_url
        async with httpx.AsyncClient(timeout=20, transport=self.transport, follow_redirects=True) as client:
            for query in queries:
                params = (
                    {"search": query["text"], "per_page": 25}
                    if source == "openalex"
                    else {"query.bibliographic": query["text"], "rows": 25}
                )
                if settings.contact_email:
                    params["mailto"] = settings.contact_email
                for attempt in range(2):
                    try:
                        response = await client.get(url, params=params)
                        response.raise_for_status()
                        payload = response.json()
                        rows = (
                            payload.get("results", [])
                            if source == "openalex"
                            else payload.get("message", {}).get("items", [])
                        )
                        converter = openalex_card if source == "openalex" else crossref_card
                        # Reciprocal rank fusion treats each provider/query ranking equally.
                        cards.extend(
                            {**converter(row), "_relevance": 1 / (60 + rank)} for rank, row in enumerate(rows, 1)
                        )
                        query_log.append({"query": query["text"], "hits": len(rows), "status": "ok"})
                        break
                    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
                        if attempt == 0:
                            continue
                        reason = (
                            f"HTTP {exc.response.status_code}"
                            if isinstance(exc, httpx.HTTPStatusError)
                            else f"请求或响应解析失败（{type(exc).__name__}）"
                        )
                        errors.append(reason)
                        query_log.append({"query": query["text"], "hits": 0, "status": "failed", "reason": reason})
        return cards, {
            "status": "failed" if errors else "ok",
            "reason": "; ".join(sorted(set(errors))),
            "hits": len(cards),
            "queries": query_log,
        }

    async def search_all(self, queries):
        results = await asyncio.gather(*(self.search(source, queries) for source in ["openalex", "crossref"]))
        names = ["openalex", "crossref"]
        if self.settings.local_library_dir:
            from .documents import search_local

            try:
                local = await asyncio.to_thread(search_local, self.settings.local_library_dir, queries)
            except Exception as exc:
                local = ([], {"status": "failed", "hits": 0, "reason": f"本地库读取失败（{type(exc).__name__}）"})
            results.append(local)
            names.append("local")
        return merge_cards([card for cards, _ in results for card in cards]), dict(
            zip(names, [status for _, status in results])
        )
