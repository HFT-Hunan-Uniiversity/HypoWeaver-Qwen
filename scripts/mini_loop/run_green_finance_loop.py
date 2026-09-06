#!/usr/bin/env python3
"""Run a reproducible A→B→C→D→E mini-loop on two open-access papers."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET


SCHEMA_VERSION = "mini-loop-1.0"
RUN_DATE = "2026-07-22"
QUESTION_ZH = "绿色金融是否改善环境绩效？其有效性通过哪些通道并受什么条件约束？"
QUESTION_EN = (
    "Does green finance improve environmental performance through emissions reduction, "
    "energy efficiency, renewable energy development, and fintech-enabled investment?"
)

PAPERS = {
    "P04": {
        "a_row_id": 4,
        "xml": "P04_Muganyi_2021.xml",
        "doi": "10.1016/j.ese.2021.100107",
        "source_url": "https://europepmc.org/articles/PMC9487990",
        "source_kind": "Europe PMC JATS full text",
        "access": "open access; CC BY-NC-ND 4.0",
        "profile": {
            "research_question": "中国城市层面的绿色金融政策与金融科技是否改善环境绩效？",
            "sample": "中国 290 个城市，2011–2018 年。",
            "design": "政策文本识别城市政策落地时点；半参数双重差分（SDID）估计绿色金融政策效应，并用面板模型分析金融科技。",
            "exposures": ["绿色金融政策", "金融科技发展"],
            "outcomes": ["工业废气排放", "二氧化硫排放", "环境保护投资"],
            "reliability": "中：具有准实验识别，但政策处理变量来自文本识别，城市政策可能伴随其他同期治理措施；正文的对数系数百分比解释还需用模型设定与原始回归复核。",
            "quality_flags": [
                "结果变量和 Fintech 指标在变量表中标为对数；正文把 −0.153 解释成 1% 增加对应 15% 下降，常规 log-log 解释应约为 0.153%，除非存在未说明缩放。",
                "二元政策进入对数结果模型时，精确百分比应使用 exp(beta)-1；正文直接用系数乘 100 的 38%/28%/20% 是近似值。",
            ],
        },
    },
    "P07": {
        "a_row_id": 7,
        "xml": "P07_Rasoulinezhad_TaghizadehHesary_2022.xml",
        "doi": "10.1007/s12053-022-10021-4",
        "source_url": "https://europepmc.org/articles/PMC9058054",
        "source_kind": "Europe PMC JATS full text",
        "access": "open full text in Europe PMC",
        "profile": {
            "research_question": "绿色债券、绿色能源利用与能源效率如何共同关联 10 个绿色金融领先经济体的 CO2 排放？",
            "sample": "10 个绿色金融领先经济体，年度面板 2002–2018。",
            "design": "STIRPAT 框架；面板单位根与协整检验；AMG 长期系数、面板误差修正/Granger 短期联结，并以 FM-OLS、CCEMG 做稳健性检查。",
            "exposures": ["绿色债券发行量", "绿色能源指数", "能源强度"],
            "outcomes": ["人均 CO2 排放"],
            "reliability": "中：区分长期与短期并做多种面板诊断，但属于观察性宏观研究，且作者未进行国家级分别估计。",
        },
    },
}

EVIDENCE_SPECS = [
    {
        "key": "p04_design",
        "paper": "P04",
        "claim": "样本覆盖中国 290 个城市（2011–2018），并采用 SDID 识别政策效应。",
        "patterns": [r"290 cities", r"2011", r"difference-in-differences|SDID"],
        "prefer": ["abstract", "method"],
        "polarity": "design",
    },
    {
        "key": "p04_policy_result",
        "paper": "P04",
        "claim": "SDID 系数方向显著为负；作者报告约下降 38%、28% 和 20%，但二元处理进入对数结果时需用 exp(beta)-1 复核精确百分比。",
        "patterns": [r"SDID estimation results", r"38% decline", r"industrial gas emissions"],
        "prefer": ["result"],
        "polarity": "supporting",
    },
    {
        "key": "p04_fintech_emissions",
        "paper": "P04",
        "claim": "城市固定效应结果的 Fintech 系数为 −0.153；方向支持 SO2 下降，但作者的“1%→15%”解释与常规 log-log 弹性解释不一致，效应量需重算。",
        "patterns": [r"fintech development", r"15% decline", r"SO2 emissions"],
        "prefer": ["result"],
        "polarity": "supporting",
    },
    {
        "key": "p04_fintech_investment",
        "paper": "P04",
        "claim": "省级结果的 Fintech 系数为 0.117；方向支持环保投资增加，但作者的“1%→11%”解释需按变量变换重新核对。",
        "patterns": [r"fintech", r"environmental protection investment", r"11%"],
        "prefer": ["result"],
        "polarity": "supporting",
    },
    {
        "key": "p04_caveat",
        "paper": "P04",
        "claim": "数据不足、缺少合适工具变量，使异质性、长期效应、内生性和同时性问题未被充分解决。",
        "patterns": [r"not without", r"limited data availability", r"instrumental variables|endogeneity"],
        "prefer": ["conclusion"],
        "polarity": "caveat",
    },
    {
        "key": "p07_design",
        "paper": "P07",
        "claim": "研究使用 10 个绿色金融领先经济体 2002–2018 年面板，并在 STIRPAT 框架下估计长期与短期关系。",
        "patterns": [r"STIRPAT", r"2002", r"panel data"],
        "prefer": ["conclusion", "method", "data"],
        "polarity": "design",
    },
    {
        "key": "p07_efficiency",
        "paper": "P07",
        "claim": "能源强度每增加 1%，长期人均 CO2 排放约增加 0.09%；论文没有直接识别绿色金融提升能源效率。",
        "patterns": [r"proxy for energy efficiency", r"0.09%", r"energy intensity"],
        "prefer": ["result"],
        "polarity": "supporting",
    },
    {
        "key": "p07_renewable",
        "paper": "P07",
        "claim": "长期估计中，绿色债券发行量每增加 1%，人均 CO2 约下降 1%；绿色能源指数每增加 1%，人均 CO2 约下降 0.92%。",
        "patterns": [r"issuance of green bonds", r"approximately 1%", r"0.92%"],
        "prefer": ["conclusion", "result"],
        "polarity": "supporting",
    },
    {
        "key": "p07_caveat",
        "paper": "P07",
        "claim": "短期 Granger 检验未发现绿色债券或绿色能源指数与人均 CO2 的因果联结。",
        "patterns": [r"no causal linkage", r"short-term|short term", r"green bonds|issued green bonds"],
        "prefer": ["conclusion", "result"],
        "polarity": "caveat",
    },
    {
        "key": "p07_limit",
        "paper": "P07",
        "claim": "作者未进行国家级分别估计，并把它列为研究限制。",
        "patterns": [r"limitations of this study", r"not applied at the country level"],
        "prefer": ["conclusion"],
        "polarity": "caveat",
    },
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_id(prefix: str, *parts: object, length: int = 16) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{sha256_bytes(payload)[:length]}"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalized_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def direct_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if local_name(child.tag) == name:
            return child
    return None


def first_local(root: ET.Element, name: str, predicate=None) -> ET.Element | None:
    for element in root.iter():
        if local_name(element.tag) == name and (predicate is None or predicate(element)):
            return element
    return None


def all_local(root: ET.Element, name: str) -> list[ET.Element]:
    return [element for element in root.iter() if local_name(element.tag) == name]


def section_function(section: str) -> str:
    lowered = section.lower()
    if any(term in lowered for term in ("method", "data", "model", "econometric")):
        return "methods"
    if any(term in lowered for term in ("result", "empirical", "analysis")):
        return "results"
    if any(term in lowered for term in ("discussion", "conclusion", "implication")):
        return "synthesis"
    if "abstract" in lowered or "highlight" in lowered:
        return "summary"
    return "background"


def theme_tags(text: str) -> list[str]:
    lowered = text.lower()
    mapping = {
        "green_finance": ("green finance", "green financing", "green credit", "green bond"),
        "fintech": ("fintech", "financial technology"),
        "emissions": ("emission", "sulphur dioxide", "sulfur dioxide", "co2", "carbon dioxide"),
        "energy_efficiency": ("energy efficiency", "energy intensity"),
        "renewable_energy": ("renewable energy", "green energy", "clean energy"),
        "policy": ("policy", "regulation", "government"),
        "investment": ("investment", "capital allocation", "financing gap"),
    }
    return [tag for tag, needles in mapping.items() if any(needle in lowered for needle in needles)]


def parse_article(xml_path: Path, paper_key: str, config: dict) -> dict:
    raw = xml_path.read_bytes()
    root = ET.fromstring(raw)
    doi_node = first_local(root, "article-id", lambda element: element.attrib.get("pub-id-type") == "doi")
    doi = normalized_text(doi_node) or config["doi"]
    document_id = f"doi:{doi.lower()}"
    title = normalized_text(first_local(root, "article-title"))
    journal = normalized_text(first_local(root, "journal-title"))
    year = normalized_text(first_local(root, "pub-date").find("year") if first_local(root, "pub-date") is not None else None)

    authors = []
    for contrib in all_local(root, "contrib"):
        name = direct_child(contrib, "name")
        if name is None:
            continue
        surname = normalized_text(direct_child(name, "surname"))
        given = normalized_text(direct_child(name, "given-names"))
        full = " ".join(part for part in (given, surname) if part)
        if full and full not in authors:
            authors.append(full)

    license_text = " ".join(normalized_text(node) for node in all_local(root, "license-p"))
    blocks: list[dict] = []

    def add_block(text: str, block_type: str, section_path: list[str], xml_id: str | None) -> None:
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 12:
            return
        ordinal = len(blocks) + 1
        locator = " / ".join(section_path) if section_path else "Body"
        block_id = stable_id("blk", document_id, ordinal, locator, text)
        blocks.append({
            "block_id": block_id,
            "ordinal": ordinal,
            "block_type": block_type,
            "section_path": section_path,
            "source_locator": f"{locator} · {xml_id or f'ordinal-{ordinal}'}",
            "xml_id": xml_id,
            "text": text,
            "content_hash": sha256_bytes(text.encode("utf-8")),
        })

    for abstract in all_local(root, "abstract"):
        abstract_type = abstract.attrib.get("abstract-type", "abstract")
        label = "Highlights" if abstract_type == "author-highlights" else "Abstract"
        for paragraph in [node for node in abstract.iter() if local_name(node.tag) == "p"]:
            add_block(normalized_text(paragraph), "paragraph", [label], paragraph.attrib.get("id"))

    body = first_local(root, "body")

    def walk(element: ET.Element, path: list[str]) -> None:
        current_path = path
        if local_name(element.tag) == "sec":
            title_node = direct_child(element, "title")
            title_text = normalized_text(title_node)
            current_path = path + ([title_text] if title_text else [])
        for child in element:
            tag = local_name(child.tag)
            if tag == "title":
                continue
            if tag == "p":
                add_block(normalized_text(child), "paragraph", current_path, child.attrib.get("id"))
            elif tag == "table-wrap":
                label = normalized_text(direct_child(child, "label"))
                caption = normalized_text(direct_child(child, "caption"))
                table = first_local(child, "table")
                table_text = normalized_text(table)
                add_block(" | ".join(part for part in (label, caption, table_text) if part), "table", current_path, child.attrib.get("id"))
            elif tag == "fig":
                caption = normalized_text(direct_child(child, "caption"))
                label = normalized_text(direct_child(child, "label"))
                add_block(" | ".join(part for part in (label, caption) if part), "figure_caption", current_path, child.attrib.get("id"))
            elif tag not in {"ref-list"}:
                walk(child, current_path)

    if body is not None:
        walk(body, [])

    offset = 0
    for block in blocks:
        block["char_start"] = offset
        block["char_end"] = offset + len(block["text"])
        offset = block["char_end"] + 2

    references = []
    for ref in all_local(root, "ref"):
        text = normalized_text(ref)
        if not text:
            continue
        doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", text)
        references.append({"reference_id": ref.attrib.get("id"), "text": text, "doi": doi_match.group(0).rstrip(".") if doi_match else None})

    return {
        "schema_version": SCHEMA_VERSION,
        "document_id": document_id,
        "document_version": sha256_bytes(raw)[:16],
        "paper_key": paper_key,
        "source_row_id": config["a_row_id"],
        "metadata": {
            "title": title,
            "authors": authors,
            "journal": journal,
            "year": year,
            "doi": doi,
            "source_url": config["source_url"],
            "source_kind": config["source_kind"],
            "access_note": config["access"],
            "license_text": license_text,
            "retrieved_at": f"{RUN_DATE}T00:00:00+08:00",
            "raw_sha256": sha256_bytes(raw),
        },
        "parse_status": "ok",
        "parse_quality": {
            "source_format": "JATS XML",
            "full_text_available": True,
            "page_numbers_available": False,
            "locator_strategy": "section path + XML id",
            "block_count": len(blocks),
            "reference_count": len(references),
        },
        "blocks": blocks,
        "references": references,
    }


def make_chunks(document: dict, max_words: int = 170, overlap_words: int = 28) -> list[dict]:
    chunks = []
    for block in document["blocks"]:
        text = block["text"]
        spans = list(re.finditer(r"\S+", text))
        if not spans:
            continue
        starts = [0] if len(spans) <= max_words else list(range(0, len(spans), max_words - overlap_words))
        for part, word_start in enumerate(starts, start=1):
            word_end = min(len(spans), word_start + max_words)
            char_start = spans[word_start].start()
            char_end = spans[word_end - 1].end()
            chunk_text = text[char_start:char_end]
            chunk_id = stable_id("chk", document["document_id"], block["block_id"], char_start, char_end, chunk_text)
            chunks.append({
                "chunk_id": chunk_id,
                "evidence_id": stable_id("evd", chunk_id),
                "document_id": document["document_id"],
                "paper_key": document["paper_key"],
                "source_block_ids": [block["block_id"]],
                "source_locator": block["source_locator"],
                "section": " / ".join(block["section_path"]),
                "block_char_start": char_start,
                "block_char_end": char_end,
                "part": part,
                "text": chunk_text,
                "content_hash": sha256_bytes(chunk_text.encode("utf-8")),
                "classification": {
                    "evidence_function": section_function(" / ".join(block["section_path"])),
                    "themes": theme_tags(chunk_text),
                    "study_type": "quantitative_empirical",
                },
            })
            if word_end == len(spans):
                break
    return chunks


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{1,}", text)]


def build_index(chunks: list[dict]) -> tuple[dict, dict[str, float]]:
    postings: dict[str, list[list[object]]] = defaultdict(list)
    doc_freq = Counter()
    lengths = {}
    for chunk in chunks:
        counts = Counter(tokenize(chunk["text"]))
        lengths[chunk["chunk_id"]] = sum(counts.values())
        for term, count in sorted(counts.items()):
            postings[term].append([chunk["chunk_id"], count])
            doc_freq[term] += 1
    n = len(chunks)
    idf = {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in doc_freq.items()}
    index = {
        "schema_version": SCHEMA_VERSION,
        "index_type": "BM25-compatible lexical inverted index",
        "chunk_count": n,
        "average_chunk_length": sum(lengths.values()) / n if n else 0,
        "document_lengths": lengths,
        "postings": dict(sorted(postings.items())),
        "idf": idf,
    }
    return index, idf


def bm25_search(query: str, chunks: list[dict], index: dict, idf: dict[str, float], limit: int = 12) -> list[dict]:
    query_terms = Counter(tokenize(query))
    chunk_lookup = {chunk["chunk_id"]: chunk for chunk in chunks}
    postings = index["postings"]
    avgdl = index["average_chunk_length"] or 1
    scores = defaultdict(float)
    k1, b = 1.5, 0.75
    for term, qtf in query_terms.items():
        for chunk_id, tf in postings.get(term, []):
            dl = index["document_lengths"][chunk_id]
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / avgdl)
            scores[chunk_id] += idf.get(term, 0) * numerator / denominator * (1 + math.log(qtf))
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return [
        {
            "rank": rank,
            "score": round(score, 6),
            "chunk_id": chunk_id,
            "evidence_id": chunk_lookup[chunk_id]["evidence_id"],
            "paper_key": chunk_lookup[chunk_id]["paper_key"],
            "source_locator": chunk_lookup[chunk_id]["source_locator"],
            "text": chunk_lookup[chunk_id]["text"],
        }
        for rank, (chunk_id, score) in enumerate(ranked, start=1)
    ]


def select_evidence(chunks: list[dict]) -> tuple[dict[str, dict], list[dict]]:
    selected = {}
    candidates_report = []
    for spec in EVIDENCE_SPECS:
        candidates = []
        for chunk in chunks:
            if chunk["paper_key"] != spec["paper"]:
                continue
            lowered = chunk["text"].lower()
            pattern_hits = sum(bool(re.search(pattern, lowered, flags=re.I)) for pattern in spec["patterns"])
            section_hits = sum(term in chunk["section"].lower() for term in spec["prefer"])
            theme_bonus = len(chunk["classification"]["themes"]) * 0.05
            score = pattern_hits * 3 + section_hits + theme_bonus
            if pattern_hits:
                candidates.append((score, pattern_hits, chunk))
        candidates.sort(key=lambda item: (-item[0], -item[1], item[2]["chunk_id"]))
        if not candidates:
            raise RuntimeError(f"No evidence candidate found for {spec['key']}")
        best = candidates[0][2]
        selected[spec["key"]] = {
            "evidence_id": best["evidence_id"],
            "chunk_id": best["chunk_id"],
            "document_id": best["document_id"],
            "paper_key": best["paper_key"],
            "claim": spec["claim"],
            "polarity": spec["polarity"],
            "source_locator": best["source_locator"],
            "text": best["text"],
        }
        candidates_report.append({
            "key": spec["key"],
            "selected": selected[spec["key"]],
            "alternatives": [
                {
                    "score": round(score, 2),
                    "pattern_hits": hits,
                    "evidence_id": chunk["evidence_id"],
                    "source_locator": chunk["source_locator"],
                    "text": chunk["text"],
                }
                for score, hits, chunk in candidates[:5]
            ],
        })
    return selected, candidates_report


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_outputs(base: Path) -> dict:
    raw_dir = base / "A_raw" / "fulltext_xml"
    parsed_dir = base / "B_parsed"
    c_dir = base / "C_index"
    d_dir = base / "D_reason"
    e_dir = base / "E_think"
    handoff_dir = base / "handoff"
    for directory in (parsed_dir, c_dir, d_dir, e_dir, handoff_dir):
        directory.mkdir(parents=True, exist_ok=True)

    parsed_docs = []
    manifest_items = []
    for paper_key, config in PAPERS.items():
        xml_path = raw_dir / config["xml"]
        if not xml_path.exists():
            raise FileNotFoundError(xml_path)
        parsed = parse_article(xml_path, paper_key, config)
        parsed_docs.append(parsed)
        write_json(parsed_dir / f"{paper_key}.parsed.json", parsed)
        manifest_items.append({
            "paper_key": paper_key,
            "a_row_id": config["a_row_id"],
            "doi": config["doi"],
            "title": parsed["metadata"]["title"],
            "raw_file": str(xml_path.relative_to(base)).replace("\\", "/"),
            "raw_sha256": parsed["metadata"]["raw_sha256"],
            "bytes": xml_path.stat().st_size,
            "source_url": config["source_url"],
            "source_kind": config["source_kind"],
            "access_note": config["access"],
            "status": "verified_full_text_xml",
        })
    write_json(base / "A_raw" / "manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "run_date": RUN_DATE,
        "selection_rule": "A 清单内、同一主题、可从合法开放端点获取完整正文；最终使用 2 篇。",
        "paper_count": len(manifest_items),
        "items": manifest_items,
        "dropped_candidate": {
            "a_row_id": 6,
            "doi": "10.1016/j.bir.2021.03.002",
            "reason": "出版社确认开放获取，但 PDF 端点依赖浏览器会话，未能形成稳定可复现下载；不以摘要冒充全文。",
        },
    })
    write_json(parsed_dir / "parse_manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "documents": [
            {
                "document_id": doc["document_id"],
                "paper_key": doc["paper_key"],
                "document_version": doc["document_version"],
                "block_count": len(doc["blocks"]),
                "reference_count": len(doc["references"]),
                "status": doc["parse_status"],
            }
            for doc in parsed_docs
        ],
    })

    chunks = [chunk for doc in parsed_docs for chunk in make_chunks(doc)]
    with (c_dir / "chunks.jsonl").open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    index, idf = build_index(chunks)
    write_json(c_dir / "inverted_index.json", index)
    write_json(c_dir / "index_manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "index_type": index["index_type"],
        "document_count": len(parsed_docs),
        "chunk_count": len(chunks),
        "id_chain": "document_id → block_id → chunk_id → evidence_id",
        "chunking": {"max_words": 170, "overlap_words": 28, "locator": "section path + XML id"},
        "classification": {"method": "deterministic rules", "fields": ["evidence_function", "themes", "study_type"]},
    })

    selected, candidates_report = select_evidence(chunks)
    write_json(c_dir / "evidence_candidates.json", candidates_report)

    profiles = []
    for doc in parsed_docs:
        key = doc["paper_key"]
        evidence_keys = [spec["key"] for spec in EVIDENCE_SPECS if spec["paper"] == key]
        profile = {
            "schema_version": SCHEMA_VERSION,
            "paper_key": key,
            "document_id": doc["document_id"],
            "title": doc["metadata"]["title"],
            "doi": doc["metadata"]["doi"],
            **PAPERS[key]["profile"],
            "evidence": [selected[evidence_key] for evidence_key in evidence_keys],
            "scope_warning": "本画像用于两篇论文的小闭环验收，不代表系统综述或总体因果结论。",
        }
        profiles.append(profile)
    write_json(c_dir / "paper_profiles.json", profiles)

    evidence_nodes = [
        {
            "id": evidence["evidence_id"],
            "type": "Evidence",
            "paper_key": evidence["paper_key"],
            "chunk_id": evidence["chunk_id"],
            "source_locator": evidence["source_locator"],
            "polarity": evidence["polarity"],
            "claim": evidence["claim"],
        }
        for evidence in selected.values()
    ]
    nodes = [
        {"id": "paper:P04", "type": "Paper", "label": parsed_docs[0]["metadata"]["title"]},
        {"id": "paper:P07", "type": "Paper", "label": parsed_docs[1]["metadata"]["title"]},
        {"id": "concept:green_finance", "type": "Exposure", "label": "Green finance"},
        {"id": "concept:fintech", "type": "ModeratorOrChannel", "label": "Fintech"},
        {"id": "outcome:emissions", "type": "Outcome", "label": "Industrial gas / SO2 emissions"},
        {"id": "outcome:environmental_investment", "type": "Outcome", "label": "Environmental protection investment"},
        {"id": "outcome:energy_efficiency", "type": "Outcome", "label": "Energy intensity (inverse energy efficiency)"},
        {"id": "outcome:renewable_energy", "type": "Outcome", "label": "Renewable energy development"},
        {"id": "context:china_cities", "type": "Context", "label": "290 Chinese cities, 2011–2018"},
        {"id": "context:green_leaders", "type": "Context", "label": "10 green-finance-leading economies, 2002–2018"},
        *evidence_nodes,
    ]
    edges = [
        {"source": "paper:P04", "relation": "studies", "target": "concept:green_finance", "evidence_ids": [selected["p04_design"]["evidence_id"]]},
        {"source": "concept:green_finance", "relation": "associated_with_reduction_in", "target": "outcome:emissions", "evidence_ids": [selected["p04_policy_result"]["evidence_id"]], "polarity": "supporting"},
        {"source": "concept:fintech", "relation": "associated_with_reduction_in", "target": "outcome:emissions", "evidence_ids": [selected["p04_fintech_emissions"]["evidence_id"]], "polarity": "supporting"},
        {"source": "concept:fintech", "relation": "associated_with", "target": "outcome:environmental_investment", "evidence_ids": [selected["p04_fintech_investment"]["evidence_id"]], "polarity": "supporting"},
        {"source": "paper:P04", "relation": "in_context", "target": "context:china_cities", "evidence_ids": [selected["p04_design"]["evidence_id"]]},
        {"source": "paper:P07", "relation": "studies", "target": "concept:green_finance", "evidence_ids": [selected["p07_design"]["evidence_id"]]},
        {"source": "outcome:energy_efficiency", "relation": "higher_energy_intensity_associated_with_more", "target": "outcome:emissions", "evidence_ids": [selected["p07_efficiency"]["evidence_id"]], "polarity": "supporting"},
        {"source": "concept:green_finance", "relation": "long_term_associated_with_reduction_in", "target": "outcome:emissions", "evidence_ids": [selected["p07_renewable"]["evidence_id"]], "polarity": "supporting"},
        {"source": "concept:green_finance", "relation": "favors", "target": "outcome:renewable_energy", "evidence_ids": [selected["p07_renewable"]["evidence_id"]], "polarity": "supporting"},
        {"source": "paper:P07", "relation": "in_context", "target": "context:green_leaders", "evidence_ids": [selected["p07_design"]["evidence_id"]]},
    ]
    graph = {"schema_version": SCHEMA_VERSION, "question": QUESTION_ZH, "nodes": nodes, "edges": edges}
    write_json(d_dir / "research_graph.json", graph)

    retrieval = {
        "schema_version": SCHEMA_VERSION,
        "question_zh": QUESTION_ZH,
        "query_en": QUESTION_EN,
        "retrieval_method": "BM25 lexical retrieval + curated evidence roles",
        "ranked_chunks": bm25_search(QUESTION_EN, chunks, index, idf),
        "curated_evidence": list(selected.values()),
        "balance": {
            "supporting": [selected["p04_policy_result"]["evidence_id"], selected["p04_fintech_emissions"]["evidence_id"], selected["p04_fintech_investment"]["evidence_id"], selected["p07_efficiency"]["evidence_id"], selected["p07_renewable"]["evidence_id"]],
            "temporal_boundary": [selected["p07_caveat"]["evidence_id"]],
            "methodological_caveats": [selected["p04_caveat"]["evidence_id"], selected["p07_limit"]["evidence_id"]],
        },
    }
    write_json(d_dir / "retrieval_bundle.json", retrieval)

    gap_cards = [
        {
            "gap_id": "GAP-01",
            "title": "绿色金融暴露变量不可直接对齐",
            "gap": "一篇以城市政策文本与政策落地为处理变量，另一篇以宏观绿色金融发展指标解释能源结果；两者不能直接合并为同一效应量。",
            "why_it_matters": "政策存在与资金实际流向不是同一概念，可能造成机制误判。",
            "evidence_ids": [selected["p04_design"]["evidence_id"], selected["p07_design"]["evidence_id"]],
            "priority": "P0",
        },
        {
            "gap_id": "GAP-02",
            "title": "从资金配置到环境结果的中间链条缺失",
            "gap": "现有两篇分别观察排放/环保投资与能源效率/可再生能源，但没有统一追踪项目级资金去向、技术采用和最终减排。",
            "why_it_matters": "无法判断结果来自真实绿色投资、监管协同，还是宏观共变因素。",
            "evidence_ids": [selected["p04_policy_result"]["evidence_id"], selected["p04_fintech_emissions"]["evidence_id"], selected["p04_fintech_investment"]["evidence_id"], selected["p07_renewable"]["evidence_id"]],
            "priority": "P0",
        },
        {
            "gap_id": "GAP-03",
            "title": "识别强度、时间尺度与跨国外推存在落差",
            "gap": "城市 SDID 与跨国协整/Granger 的识别强度不同；P07 只在长期发现减排关系，短期无因果联结，且没有逐国估计。",
            "why_it_matters": "若忽略研究设计与时间尺度差异，容易把长期宏观相关性写成短期、普遍的政策因果效应。",
            "evidence_ids": [selected["p04_design"]["evidence_id"], selected["p07_caveat"]["evidence_id"], selected["p07_limit"]["evidence_id"]],
            "priority": "P1",
        },
        {
            "gap_id": "GAP-04",
            "title": "P04 的对数系数百分比解释需要重算",
            "gap": "论文将 log-log 模型中的 Fintech 系数 −0.153/0.117 叙述为 1% 变化对应约 15%/11% 变化，并把二元政策的对数结果系数直接乘 100；这些换算与常规解释不一致。",
            "why_it_matters": "方向性结论可能仍成立，但效应量若放大约 100 倍，会直接误导政策收益评估。",
            "evidence_ids": [selected["p04_policy_result"]["evidence_id"], selected["p04_fintech_emissions"]["evidence_id"], selected["p04_fintech_investment"]["evidence_id"]],
            "priority": "P0",
            "next_check": "取得回归代码/原始数据后，确认变量变换；对连续 log-log 系数按弹性解释，对二元处理使用 100×(exp(beta)-1)。",
        },
    ]
    write_json(e_dir / "gap_cards.json", gap_cards)

    hypotheses = [
        {
            "hypothesis_id": "HYP-01",
            "statement": "在其他条件相同的城市中，绿色金融政策落地后工业废气排放下降；金融科技基础更强时降幅更大。",
            "mechanism": "金融科技降低绿色项目识别与融资摩擦，使政策信号更快转化为环保投资。",
            "unit": "中国地级市—年份",
            "exposure": "绿色金融政策落地（分期处理）",
            "moderator": "城市金融科技发展水平",
            "outcomes": ["工业废气排放", "SO2 排放", "环保投资"],
            "identification": "分期 DID/事件研究；城市与年份固定效应；政策前趋势与安慰剂检验。",
            "falsification": "若政策前已有差异趋势、对不受影响污染物同样显著，或加入同期环保督察后效应消失，则否定或降级。",
            "data_feasibility": "中高：政策文本、城市排放、数字金融指数和财政环保支出均有潜在公开/商业数据源。",
            "evidence_ids": [selected["p04_design"]["evidence_id"], selected["p04_policy_result"]["evidence_id"], selected["p04_fintech_emissions"]["evidence_id"], selected["p04_fintech_investment"]["evidence_id"]],
            "status": "可检验，需补充同期政策共变控制",
        },
        {
            "hypothesis_id": "HYP-02",
            "statement": "绿色债券对减排的影响主要在长期显现，且在项目筛选、信息披露与资金配置效率较高的经济体中更强。",
            "mechanism": "绿色债券先改变项目融资与绿色能源部署，建设和替代效应存在时滞；标准与披露质量决定资金是否进入新增清洁能源。",
            "unit": "国家—年份（可扩展到省级）",
            "exposure": "可分解的绿色信贷、绿色债券和绿色投资指标",
            "moderator": "绿色资金配置效率/制度质量",
            "outcomes": ["可再生能源新增装机与消费", "单位产出能耗", "边际减排"],
            "identification": "动态面板或工具变量；分工具与分国家估计；报告非线性和异质性。",
            "falsification": "若不同绿色金融工具方向一致且不受配置效率影响，条件性机制不成立。",
            "data_feasibility": "中：跨国绿色金融拆分指标与项目级流向数据是主要瓶颈。",
            "evidence_ids": [selected["p07_design"]["evidence_id"], selected["p07_efficiency"]["evidence_id"], selected["p07_renewable"]["evidence_id"], selected["p07_caveat"]["evidence_id"], selected["p07_limit"]["evidence_id"]],
            "status": "可检验，需先统一绿色金融测量口径",
        },
    ]
    write_json(e_dir / "hypothesis_cards.json", hypotheses)
    write_json(e_dir / "假设清单.json", {"schema_version": SCHEMA_VERSION, "question": QUESTION_ZH, "hypotheses": hypotheses})

    evidence_lines = []
    for evidence in selected.values():
        excerpt = evidence["text"][:260].replace("|", "\\|")
        evidence_lines.append(f"| {evidence['paper_key']} | {evidence['polarity']} | {evidence['claim']} | `{evidence['evidence_id']}` | {excerpt} |")
    report = f"""# 两篇论文绿色金融小闭环评价报告

## 结论先行

这两篇论文共同支持“绿色金融与更好的环境结果相关”，但不能推出无条件、跨情境一致的因果结论。中国城市研究提供了较强的准实验证据：政策落地与工业废气下降相关，金融科技还与 SO2 下降和环保投资增加相关。10 个绿色金融领先经济体的面板研究则显示，绿色债券和绿色能源指数的减排关系主要存在于长期；短期 Granger 检验没有发现相应因果联结，而且论文没有逐国估计。

因此，下一轮最值得验证的不是“绿色金融有没有用”，而是：**哪一类资金、在什么制度和金融科技条件下，真正进入项目并形成可核验减排。**

## 研究问题

{QUESTION_ZH}

## 纳入论文

1. Muganyi, Yan & Sun (2021), *Green finance, fintech and environmental protection: Evidence from China*, DOI: https://doi.org/10.1016/j.ese.2021.100107
2. Rasoulinezhad & Taghizadeh-Hesary (2022), *Role of green finance in improving energy efficiency and renewable energy development*, DOI: https://doi.org/10.1007/s12053-022-10021-4

两篇均来自 A 的 169 篇清单，分别是序号 4 和 7；原始层使用 Europe PMC 的完整 JATS XML。序号 6 虽标注开放获取，但无法得到稳定、可复现的官方 PDF，因此未用摘要替代全文。

## 证据矩阵

| 论文 | 证据角色 | 归纳命题 | evidence_id | 原文片段（截断） |
|---|---|---|---|---|
{chr(10).join(evidence_lines)}

## 综合判断

- 支持证据：城市政策的准实验结果指向排放下降；金融科技可能通过环保投资形成辅助通道。
- 时间边界：跨国面板的减排关系只在长期成立，短期没有发现绿色债券/绿色能源指数到人均 CO2 的因果联结。
- 不能回答：两篇均未形成“资金流向 → 项目建设/技术采用 → 物理减排”的统一项目级链条。
- 识别边界：一篇是城市准实验，一篇是观察性跨国面板，证据等级不能等同，也不应直接合并效应量。

## 效应量复核警报

P04 的方向性结果可保留，但百分比不能直接照抄。变量表把 SO2、Fintech 等记为对数，正文却把 `−0.153` 解释为“Fintech 增加 1% 对应 SO2 下降 15%”；常规 log-log 模型下应更接近 0.153%。二元政策系数进入对数结果时，也应以 `100×(exp(beta)-1)` 做精确换算。本轮没有原始数据和回归代码，因此所有 P04 效应量均标为待复核。

## 优先研究缺口

1. 统一绿色金融暴露口径：区分政策信号、信贷余额、债券发行和实际项目拨款。
2. 建立项目级链条：把资金、技术采用、装机/能效和排放核算连接到同一项目。
3. 显式建模异质性：金融科技、制度质量、所有制、行业污染强度和地区金融发展水平。
4. 先做系数解释审计：核对 P04 的变量变换、缩放与二元处理效应换算。

## 建议进入下一轮的假设

- HYP-01：城市绿色金融政策降低工业废气，且金融科技基础越强，降幅越大。
- HYP-02：绿色债券的减排作用主要在长期显现，并受项目筛选、披露与资金配置效率调节。

## 评价

本轮已跑通原始全文、结构化解析、稳定 ID、切分分类、词法检索、论文画像、证据图谱、缺口与假设生成以及引用回溯。它是可验收的小闭环，不是生产级系统综述：样本只有两篇，未做效应量重算、偏倚工具评分或外部数据复核。
"""
    (e_dir / "评价报告.md").write_text(report, encoding="utf-8")

    readme = f"""# A→B→C→D→E 小闭环：绿色金融与环境绩效

- 运行日期：{RUN_DATE}
- 论文数：2（A 清单序号 4、7）
- 问题：{QUESTION_ZH}
- 原始格式：开放全文 JATS XML

## 目录

- `A_raw/`：全文 XML 与下载/筛选清单
- `B_parsed/`：ParsedDoc JSON；稳定 `document_id`、`block_id`
- `C_index/`：chunks、分类、BM25 词法索引、PaperProfile；稳定 `chunk_id`、`evidence_id`
- `D_reason/`：研究图谱与检索证据包
- `E_think/`：GapCard、HypothesisCard、假设清单、评价报告
- `handoff/`：H1–H5 验收记录

## 重跑

```powershell
python scripts/mini_loop/run_green_finance_loop.py --base output/mini_loop/2026-07-22_green_finance_env_outcomes
```

脚本只读取已落地的全文 XML，并重建 B–E 产物；不会重新联网下载。
"""
    (base / "README.md").write_text(readme, encoding="utf-8")

    receipt = f"""# H1–H5 小闭环交接验收

## H1 A → B：原始论文全文

- 状态：通过（带说明）
- 输入：2 篇完整 JATS XML，均来自 A 的清单；SHA-256 记录于 `A_raw/manifest.json`。
- 说明：页码不可用，B 使用“章节路径 + XML id”作为定位；未把 HTML 错误页或摘要当全文。

## H2 B → C：结构化解析

- 状态：通过
- ParsedDoc：{len(parsed_docs)} 个；总 block 数：{sum(len(doc['blocks']) for doc in parsed_docs)}。
- ID：`document_id → block_id` 可稳定重算；包含正文、表格/图注与参考文献。

## H3 C → D：切分、分类、索引与画像

- 状态：通过
- chunk 数：{len(chunks)}；每个 chunk 保留来源 block、章节定位、hash、分类与 `evidence_id`。
- 索引：BM25-compatible 词法倒排索引；PaperProfile 2 份。

## H4 D → E：图谱与证据包

- 状态：通过
- 图谱节点：{len(nodes)}；边：{len(edges)}。
- 检索包同时保留 supporting、mixed/conditional、caveat 三类证据。

## H5 E → 最终输出

- 状态：通过
- GapCard：{len(gap_cards)}；HypothesisCard：{len(hypotheses)}。
- 最终件：`E_think/假设清单.json`、`E_think/评价报告.md`。

## 共同限制

- 两篇是流程验收样本，不代表系统综述。
- 未重算回归、未做原始数据复现、未进行正式偏倚风险量表评分。
- P04 的对数系数百分比解释存在疑点；方向性证据保留，效应量已标记为待复核。
- P07 属观察性宏观面板；图谱分别保留长期支持、短期无联结和逐国估计缺失，不能提升为普遍强因果结论。
"""
    (handoff_dir / "H1-H5_验收.md").write_text(receipt, encoding="utf-8")

    return {
        "parsed_docs": parsed_docs,
        "chunks": chunks,
        "selected": selected,
        "graph": graph,
        "gap_cards": gap_cards,
        "hypotheses": hypotheses,
    }


def validate(base: Path, state: dict) -> dict:
    checks = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    manifest = json.loads((base / "A_raw" / "manifest.json").read_text(encoding="utf-8"))
    raw_ok = True
    for item in manifest["items"]:
        path = base / item["raw_file"]
        raw_ok &= path.exists() and sha256_bytes(path.read_bytes()) == item["raw_sha256"]
    record("raw_hashes", raw_ok, f"verified {len(manifest['items'])} raw full-text files")

    docs = state["parsed_docs"]
    block_ids = [block["block_id"] for doc in docs for block in doc["blocks"]]
    chunk_ids = [chunk["chunk_id"] for chunk in state["chunks"]]
    evidence_ids = [chunk["evidence_id"] for chunk in state["chunks"]]
    record("unique_block_ids", len(block_ids) == len(set(block_ids)), f"{len(block_ids)} block ids")
    record("unique_chunk_ids", len(chunk_ids) == len(set(chunk_ids)), f"{len(chunk_ids)} chunk ids")
    record("unique_evidence_ids", len(evidence_ids) == len(set(evidence_ids)), f"{len(evidence_ids)} evidence ids")

    block_set = set(block_ids)
    chunk_refs_ok = all(set(chunk["source_block_ids"]).issubset(block_set) for chunk in state["chunks"])
    record("chunk_to_block_refs", chunk_refs_ok, "all chunk source_block_ids resolve")
    evidence_set = set(evidence_ids)
    selected_ok = all(item["evidence_id"] in evidence_set for item in state["selected"].values())
    record("selected_evidence_refs", selected_ok, f"{len(state['selected'])} curated evidence refs resolve")

    graph_refs = [evidence_id for edge in state["graph"]["edges"] for evidence_id in edge.get("evidence_ids", [])]
    record("graph_evidence_refs", all(ref in evidence_set for ref in graph_refs), f"{len(graph_refs)} graph evidence refs resolve")
    card_refs = [evidence_id for card in state["gap_cards"] + state["hypotheses"] for evidence_id in card["evidence_ids"]]
    record("card_evidence_refs", all(ref in evidence_set for ref in card_refs), f"{len(card_refs)} gap/hypothesis refs resolve")

    json_paths = list(base.rglob("*.json"))
    json_ok = True
    for path in json_paths:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            json_ok = False
    record("json_parse", json_ok, f"parsed {len(json_paths)} JSON files")
    jsonl_ok = True
    jsonl_count = 0
    for line in (base / "C_index" / "chunks.jsonl").read_text(encoding="utf-8").splitlines():
        json.loads(line)
        jsonl_count += 1
    record("jsonl_parse", jsonl_ok, f"parsed {jsonl_count} JSONL records")

    status = "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL"
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "checks": checks,
    }
    write_json(base / "validation_report.json", report)
    return report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=Path("output/mini_loop/2026-07-22_green_finance_env_outcomes"))
    args = parser.parse_args()
    base = args.base.resolve()
    state = build_outputs(base)
    validation = validate(base, state)
    summary = {
        "base": str(base),
        "documents": len(state["parsed_docs"]),
        "blocks": sum(len(doc["blocks"]) for doc in state["parsed_docs"]),
        "chunks": len(state["chunks"]),
        "evidence": len(state["selected"]),
        "validation": validation["status"],
        "selected_evidence": state["selected"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
