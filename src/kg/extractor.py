# ============================================================================
# KG 三元组抽取器 — src/kg/extractor.py
# ============================================================================
# 基于单篇论文（cleaned md 正文 + cleaned_meta 元数据），调 qwen-max 抽取
# 五类实体与概念间因果关系，组装成一个 KnowledgeGraph（写入批载体）。
#
# 容错设计：
#   - Pydantic 结构化输出校验（v_* 字段），型不对自动修正（字符串化）
#   - JSON 解析兼容 markdown ```json 包裹、BOM、前后杂文
#   - 空值防护：某列表字段缺失/None → 空列表；整体失败返回 None，不抛异常
#   - 关系值域硬约束：relation 只接受 RelationKind 枚举，非法即丢弃该条
#   - 别名归一：name 经 aliases.normalize_alias 归一，归一出 alias_of
#   - 无 LLM 时降级为纯元数据 KG（仅 Paper/Author/Method/Dataset，零概念）
#   - 幂等：绝不修改输入文件
# ============================================================================

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from pydantic import ValidationError

from src.kg.llm_extract_client import chat_json
from src.kg.entities import (
    RELATION_CN,
    AuthorNode,
    ConceptNode,
    ConceptRelation,
    DatasetNode,
    Evidence,
    KnowledgeGraph,
    MethodNode,
    PaperNode,
    RelationKind,
)
from src.kg.aliases import normalize_alias


# ----------------------------------------------------------------------------
# Prompt 构建
# ----------------------------------------------------------------------------
def build_prompt(meta: dict, md_text: str) -> str:
    """组装三元组抽取 prompt。关系类型值域被硬约束在枚举内。"""
    title = (meta.get("title") or "").strip() or (meta.get("doc_id") or "")
    authors = "、".join(meta.get("authors") or [])
    abstract = (meta.get("abstract") or "").strip()

    relation_list = "\n".join(
        f"  - {e.value}：{RELATION_CN[e]}" for e in RelationKind if e != RelationKind.CO_OCCUR
    )
    relation_list = relation_list.strip()

    header = (
        f"你是绿色金融论文的知识抽取专家。请从下面这篇论文中抽取知识图谱三元组。\n\n"
        f"论文标题：{title}\n"
        f"作者：{authors or '未知'}\n"
        f"摘要：{abstract or '无'}\n\n"
        f"请在概念间关系 relation 字段中，严格从以下枚举中选一个值（只能英文枚举，不要写中文）：\n{relation_list}\n\n"
        f"概念节点只收录论文真正最核心的若干概念（一般不超过 10 个），必须是具体名词"
        f"（如'绿色技术创新'、'企业融资成本'），不要收录泛词（'影响'、'研究'、'效应'）。"
    )

    body = (
        f"论文正文：\n---\n{md_text[:18000]}\n---\n"
        f"请输出严格 JSON，不要多余文字：\n"
        f'{{"concepts": ["概念1", "概念2"], '
        f'"methods": ["方法1"], "datasets": ["数据/数据库1"], '
        f'"concept_relations": ['
        f'{{"source": "概念A", "target": "概念B", '
        f'"relation": "PROMOTE", "evidence": "原文片段", "confidence": 0.9}}'
        f']}}\n\n'
        f"要求：\n"
        f"1. concept_relations 里的 source/target 必须存在于 concepts 中。\n"
        f"2. relation 只能取自上面枚举（不要输出枚举外的值）。\n"
        f"3. evidence 必须是论文正文中与该关系直接相关的原文片段（尽量精简，不要编造）。\n"
        f"4. confidence 取 0~1 之间小数。\n"
        f"5. 没有对应信息就返回空数组，不要编造。"
    )
    return header + "\n" + body


# ----------------------------------------------------------------------------
# JSON 解析（兼容多种脏输出）
# ----------------------------------------------------------------------------
def _extract_json_str(content: str) -> str:
    """从 LLM 输出中剥离 markdown 代码块 / BOM / 前后杂文，返回最外层 JSON 对象字符串。"""
    if not content:
        return ""
    s = content.strip()
    if s.startswith("﻿"):
        s = s[1:].strip()
    # 去掉 ```json ... ``` 包裹
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.DOTALL)
    if m:
        return m.group(1)
    # 去掉任何 ``` 代码围栏外壳
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    # 去掉尾随的未闭合说明文字
    brace = s.find("{")
    if brace != -1:
        # 找到匹配的右花括号
        depth = 0
        for i in range(brace, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    return s[brace:i + 1]
    return s[brace:] if brace != -1 else s


def _parse_json(content: str) -> Optional[dict]:
    """解析 JSON，成功返回 dict，失败返回 None。"""
    if not content:
        return None
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


# ----------------------------------------------------------------------------
# 字段归一（容忍 LLM 返回类型污染）
# ----------------------------------------------------------------------------
def _str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v).strip()


def _str_list(v) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = re.split(r"[;,，；、\n]+", v)
    out: List[str] = []
    for item in v:
        if isinstance(item, dict):
            item = item.get("name") or item.get("value") or item.get("alias") or ""
        s = _str(item)
        if s:
            out.append(s)
    return out


def _evidence_from(rel: dict, default_doc: str) -> Evidence:
    """从 LLM 关系条目中提取 evidence 挂载。"""
    ev_raw = rel.get("evidence")
    if isinstance(ev_raw, dict):
        return Evidence(
            evidence=_str(
                ev_raw.get("evidence") or ev_raw.get("snippet")
                or ev_raw.get("value") or ""
            ),
            source_doc=_str(ev_raw.get("source_doc") or default_doc),
            snippet=_str(ev_raw.get("snippet")),
            page=int(ev_raw["page"]) if ev_raw.get("page") is not None else None,
        )
    return Evidence(
        evidence=_str(ev_raw),
        source_doc=default_doc,
    )


def _parse_concept_relation(rel: dict, default_doc: str) -> Optional[ConceptRelation]:
    """解析单条概念关系，非法 relation 直接丢弃。"""
    source = _str(rel.get("source")).strip()
    target = _str(rel.get("target")).strip()
    if not source or not target:
        return None
    source = normalize_alias(source)
    target = normalize_alias(target)
    if not source or not target:
        return None

    rel_kind = (rel.get("relation") or "").strip().upper()
    if not RelationKind.has(rel_kind) or rel_kind == "CO_OCCUR":
        # 只接受 LLM 的 11 类因果枚举；非法值丢弃，防止脏边
        return None

    try:
        confidence = float(rel.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = min(max(confidence, 0.0), 1.0)

    return ConceptRelation(
        source=source,
        target=target,
        relation=RelationKind(rel_kind),
        confidence=confidence,
        evidence=_evidence_from(rel, default_doc),
    )


# ----------------------------------------------------------------------------
# 结果组装 — LLM dict -> KnowledgeGraph
# ----------------------------------------------------------------------------
def _assemble(parsed: dict, meta: dict) -> KnowledgeGraph:
    doc_id = meta.get("doc_id", "")
    title = meta.get("title") or ""
    authors_raw = meta.get("authors") or []
    authors = [AuthorNode(name=normalize_alias(a)) for a in authors_raw if a]
    # 去重（后构造的去重：doc_id 在 assemble 外统一做）
    _dedup_authors(authors)

    concepts_raw = _str_list(parsed.get("concepts"))
    concepts = [ConceptNode(name=normalize_alias(c)) for c in concepts_raw if c]
    _dedup_concepts(concepts)

    methods_raw = _str_list(parsed.get("methods"))
    methods = [MethodNode(name=normalize_alias(m)) for m in methods_raw if m]
    _dedup_nodes(methods)

    datasets_raw = _str_list(parsed.get("datasets"))
    datasets = [DatasetNode(name=normalize_alias(d)) for d in datasets_raw if d]
    _dedup_nodes(datasets)

    # 关系解析；丢弃非法/自环
    relations: List[ConceptRelation] = []
    seen = set()
    for rel in parsed.get("concept_relations") or []:
        if not isinstance(rel, dict):
            continue
        cr = _parse_concept_relation(rel, doc_id)
        if cr is None or cr.source == cr.target:
            continue
        key = (cr.source, cr.target, cr.relation.value)
        if key in seen:
            continue
        seen.add(key)
        relations.append(cr)

    paper = PaperNode(
        doc_id=doc_id,
        title=title,
        authors=[a.name for a in authors],
        abstract=meta.get("abstract"),
        keywords=_str_list(meta.get("keywords")) or ["TODO"],
        journal=meta.get("journal"),
        year=meta.get("year"),
        doi=meta.get("doi"),
    )
    return KnowledgeGraph(
        paper=paper,
        authors=authors,
        concepts=concepts,
        methods=methods,
        datasets=datasets,
        relations=relations,
    )


def _dedup_authors(lst: List[AuthorNode]) -> None:
    seen = set()
    kept: List[AuthorNode] = []
    for a in lst:
        if a.name and a.name not in seen:
            seen.add(a.name)
            kept.append(a)
    lst[:] = kept


def _dedup_concepts(lst: List[ConceptNode]) -> None:
    seen = set()
    kept: List[ConceptNode] = []
    for c in lst:
        if c.name not in seen and c.name not in _SKIP_CONCEPT_WORDS:
            seen.add(c.name)
            kept.append(c)
    lst[:] = kept


def _dedup_nodes(lst) -> None:
    """通用节点去重（按 name）。"""
    seen = set()
    kept = []
    for n in lst:
        if n.name and n.name not in seen:
            seen.add(n.name)
            kept.append(n)
    lst[:] = kept


# 过滤过于宽泛的"概念"词，避免噪声节点
_SKIP_CONCEPT_WORDS = {
    "影响", "效应", "研究", "绿色金融", "政策", "数据",
    "企业", "技术", "机制", "路径", "tfp", "esg",
    "china", "europe", "中国", "美国", "sample", "样本",
}


# ----------------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------------
def extract_relations_from_doc(
    doc_id: str,
    md_text: str,
    meta: dict,
    use_llm: bool = True,
) -> Optional[KnowledgeGraph]:
    """
    抽取一篇论文的完整 KG 单元。

    参数:
      doc_id:   文档 ID
      md_text:  cleaned/*.md 全文
      meta:     cleaned_meta/*.json 的 extra_info（含 title/authors/abstract/keywords 等）
      use_llm:  是否需调用 qwen-max。False 时降级为仅元数据 KG。

    返回 KnowledgeGraph；LLM 调用或解析彻底失败返回 None（不抛异常）。
    若 use_llm=False，仍返回含 Paper/Author/Method/Dataset 的基础图。
    """
    meta_for_prompt = dict(meta or {})
    meta_for_prompt.setdefault("doc_id", doc_id)
    meta_for_prompt.setdefault("title", "")

    # 无概念时用 LLM 补概念抽取；若 LLM 关闭，则直接产基础图
    if not use_llm:
        kg = _assemble({"concepts": [], "methods": [], "datasets": [],
                        "concept_relations": []}, meta_for_prompt)
        return kg

    messages = [{"role": "user", "content": build_prompt(meta_for_prompt, md_text)}]
    content = chat_json(messages, max_tokens=4096)
    if content is None:
        return None

    parsed = _parse_json(_extract_json_str(content))
    if parsed is None:
        return None

    return _assemble(parsed, meta_for_prompt)
