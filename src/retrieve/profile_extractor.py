# ============================================================================
# PaperProfile 抽取引擎 — C 角色技术规划 §6
# ============================================================================
# 从已分类的论文 chunk 中，用 LLM 抽取结构化档案（PaperProfile）。
# 流程：
#   1. 按分类标签筛选候选 chunk（HYPOTHESIS/FINDING/METHODOLOGY/DATA/LIMITATION）
#   2. 组装 prompt（profile_prompts.py）调 qwen-turbo
#   3. 解析 JSON → 反序列化为 PaperProfile
#   4. 校验器校验，返回错误/警告
# ============================================================================

from __future__ import annotations

import json
import re
import time
from typing import Dict, List, Optional, Tuple

from schemas.paper_profile import (
    EvidencedList, EvidencedValue,
    PaperLayer1, PaperLayer2, PaperLayer3, PaperLayer4, PaperProfile,
)
from schemas.chunk_schema import ChunkPayload
from src.retrieve.profile_prompts import build_profile_prompt
from src.retrieve.profile_validator import validate_profile

try:
    from src.parse.adapters.llm_metadata import DASHSCOPE_URL, MODEL, HEADERS
    import requests
except Exception:
    requests = None
    DASHSCOPE_URL = MODEL = HEADERS = None

# 参与抽取的主题标签 → 候选字段
_CANDIDATE_TOPICS = {"HYPOTHESIS", "FINDING", "METHODOLOGY", "DATA", "LIMITATION"}


def select_candidate_chunks(chunks: List[ChunkPayload]) -> List[ChunkPayload]:
    """按分类标签筛选参与抽取的 chunk（决策3: 只用已分类的相关 chunk）"""
    cand = []
    for c in chunks:
        topics = set(c.topics or [])
        if topics & _CANDIDATE_TOPICS:
            c.is_selected = True
            cand.append(c)
    return cand


def _to_profiles(chunks: List[ChunkPayload]) -> List[dict]:
    """把候选 chunk 转成 prompt 需要的 dict 列表"""
    return [
        {"chunk_id": c.chunk_id, "text": c.chunk_text,
         "topics": list(c.topics or []), "structures": list(c.structures or [])}
        for c in chunks
    ]


def extract_profile(
    doc_id: str,
    title: str,
    abstract: str,
    candidate_chunks: List[ChunkPayload],
) -> Tuple[Optional[PaperProfile], List[str], List[str]]:
    """
    抽取一篇论文的 PaperProfile。

    返回 (profile, errors, warnings)
      profile 为 None 表示抽取整体失败。
    """
    if requests is None or HEADERS is None:
        return None, ["LLM 客户端不可用"], []

    if not candidate_chunks:
        return None, ["无可抽取的候选 chunk"], []

    prompt = build_profile_prompt(
        title, abstract, _to_profiles(candidate_chunks)
    )

    data = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},  # 强制 JSON（DashScope 支持）
    }

    content = None
    try:
        resp = requests.post(DASHSCOPE_URL, headers=HEADERS, json=data, timeout=120)
        if resp.status_code != 200:
            return None, [f"LLM 调用失败: HTTP {resp.status_code}"], []
        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return None, ["LLM 返回空内容"], []

        parsed = json.loads(_extract_json(content))
    except Exception as e:
        return None, [f"JSON 解析失败: {e}"], []

    # ---- 构建 PaperProfile ----
    profile = _assemble(parsed, doc_id, title, candidate_chunks)

    # ---- 校验 ----
    chunk_texts = {c.chunk_id: c.chunk_text for c in candidate_chunks}
    errors, warnings = validate_profile(profile, chunk_texts)

    return profile, errors, warnings


def _extract_json(content: str) -> str:
    """从模型输出中提取 JSON（兼容 markdown 代码块包裹）"""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if m:
        return m.group(1)
    return content


def _parse_ev(entry, default_chunk: str) -> Optional[EvidencedValue]:
    """解析单条 {value, evidence, chunk_id, confidence}"""
    if not entry:
        return None
    if isinstance(entry, str):
        return EvidencedValue(value=entry, evidence="", chunk_id=default_chunk, confidence="low")
    value = entry.get("value") or entry.get("claim")
    if not value or not str(value).strip():
        return None
    return EvidencedValue(
        value=str(value).strip(),
        evidence=str(entry.get("evidence") or "").strip(),
        chunk_id=str(entry.get("chunk_id") or default_chunk),
        confidence=str(entry.get("confidence") or "medium"),
    )


def _parse_list(entries, default_chunk: str) -> EvidencedList:
    """解析列表字段，过滤无效项"""
    lst = EvidencedList()
    if not entries or not isinstance(entries, list):
        return lst
    for e in entries:
        ev = _parse_ev(e, default_chunk)
        if ev and ev.value:
            lst.items.append(ev)
    return lst


def _assemble(parsed: dict, doc_id: str, title: str, chunks: List[ChunkPayload]) -> PaperProfile:
    """把 LLM 返回的 dict 组装成 PaperProfile"""
    default_chunk = chunks[0].chunk_id if chunks else ""

    l1 = PaperLayer1(doc_id=doc_id, title=title)
    l2 = PaperLayer2(
        research_question=_parse_ev(parsed.get("research_question"), default_chunk),
        theoretical_framework=_parse_ev(parsed.get("theoretical_framework"), default_chunk),
        hypotheses=_parse_list(parsed.get("hypotheses"), default_chunk),
        methodology=_parse_ev(parsed.get("methodology"), default_chunk),
        data_source=_parse_ev(parsed.get("data_source"), default_chunk),
        main_findings=_parse_list(parsed.get("main_findings"), default_chunk),
        conclusion=_parse_ev(parsed.get("conclusion"), default_chunk),
    )
    l3 = PaperLayer3(
        key_variables=_parse_list(parsed.get("key_variables"), default_chunk),
        key_statistics=_parse_list(parsed.get("key_statistics"), default_chunk),
        mechanisms=_parse_list(parsed.get("mechanisms"), default_chunk),
        identification_strategy=_parse_ev(parsed.get("identification_strategy"), default_chunk),
    )
    l4 = PaperLayer4(
        gaps_identified=_parse_list(parsed.get("gaps_identified"), default_chunk),
    )

    profile = PaperProfile(
        layer1=l1, layer2=l2, layer3=l3, layer4=l4,
        source_chunks=[c.chunk_id for c in chunks],
        extraction_model=MODEL,
        extraction_time=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    return profile


def _ev_dict(ev):
    return ev.__dict__ if ev else None


# ===== 命令行测试 =====
if __name__ == "__main__":
    import sys
    from pathlib import Path
    from src.retrieve.chunker import chunk_markdown
    from src.retrieve.classifier import classify_chunk
    import json as j

    md_path = sys.argv[1] if len(sys.argv) > 1 else \
        "cleaned/绿色金融政策如何影响绿色技术创新基于高耗能企业的经验证据_周莹莹.md"

    md = Path(md_path).read_text(encoding="utf-8")
    doc_id = Path(md_path).stem
    chunks = chunk_markdown(doc_id, md, {"title": Path(md_path).stem, "source_type": "paper"})

    # 分类
    for c in chunks:
        cls = classify_chunk(c, use_llm=False)
        c.topics = sorted(cls.topics)
        c.structures = sorted(cls.structures)

    # 筛选候选
    cand = select_candidate_chunks(chunks)
    print(f"候选 chunk: {len(cand)} 个")

    profile, errors, warnings = extract_profile(
        doc_id, Path(md_path).stem,
        "", cand,
    )
    if profile is None:
        print("❌ 抽取失败:", errors)
        sys.exit(1)

    print("✅ 抽取成功")
    print(f"  假设 {profile.layer2.hypotheses.count} 条, 发现 {profile.layer2.main_findings.count} 条, "
          f"变量 {profile.layer3.key_variables.count} 条, 机制 {profile.layer3.mechanisms.count} 条")
    if errors:
        print("❌ 校验错误:")
        for e in errors[:10]:
            print(f"   - {e}")
    if warnings:
        print("⚠️ 警告:")
        for w in warnings[:10]:
            print(f"   - {w}")

    # 保存
    out_path = Path("artifacts") / f"{profile.doc_id}.profile.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(j.dumps(
        {
            "doc_id": profile.doc_id,
            "title": profile.title,
            "research_question": _ev_dict(profile.layer2.research_question),
            "hypotheses": [ev.__dict__ for ev in profile.hypotheses],
            "methodology": _ev_dict(profile.layer2.methodology),
            "data_source": _ev_dict(profile.layer2.data_source),
            "main_findings": [ev.__dict__ for ev in profile.main_findings],
            "key_variables": [ev.__dict__ for ev in profile.layer3.key_variables.items],
            "mechanisms": [ev.__dict__ for ev in profile.layer3.mechanisms.items],
            "identification_strategy": _ev_dict(profile.layer3.identification_strategy),
            "gaps_identified": [ev.__dict__ for ev in profile.layer4.gaps_identified.items],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"📁 档案保存: {out_path}")
