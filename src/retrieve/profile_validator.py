# ============================================================================
# PaperProfile 校验器 — C 角色技术规划 §6.3
# ============================================================================
# 校验抽取质量，返回错误 / 警告列表。
# 核心约束（防幻觉）：
#   1. evidence 必须存在且非空
#   2. evidence 必须存在于其声明的 chunk_text 中
#   3. 假设和主要发现必须有值（论文核心字段）
# ============================================================================

from __future__ import annotations

from typing import Dict, List, Tuple

from schemas.paper_profile import EvidencedList, EvidencedValue, PaperProfile


def validate_profile(profile: PaperProfile, chunks: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """
    校验一个 PaperProfile。

    参数:
      profile: 待校验的档案
      chunks:  {chunk_id: chunk_text} 映射（用于 evidence 子串校验）

    返回 (errors, warnings)
      errors:   必须修复的错误
      warnings: 低危问题（如个别字段为空）
    """
    errors: List[str] = []
    warnings: List[str] = []

    # 1. 单值字段
    single_fields = [
        ("research_question", profile.layer2.research_question),
        ("theoretical_framework", profile.layer2.theoretical_framework),
        ("methodology", profile.layer2.methodology),
        ("data_source", profile.layer2.data_source),
        ("conclusion", profile.layer2.conclusion),
        ("identification_strategy", profile.layer3.identification_strategy),
    ]
    for name, ev in single_fields:
        if ev is None:
            continue
        errors += _check_evidence(ev, chunks, f"{name}")

    # 2. 列表字段
    list_fields = [
        ("hypotheses", profile.layer2.hypotheses),
        ("main_findings", profile.layer2.main_findings),
        ("key_variables", profile.layer3.key_variables),
        ("key_statistics", profile.layer3.key_statistics),
        ("mechanisms", profile.layer3.mechanisms),
        ("supported_literature", profile.layer4.supported_literature),
        ("challenged_literature", profile.layer4.challenged_literature),
        ("gaps_identified", profile.layer4.gaps_identified),
    ]
    for name, lst in list_fields:
        for item in lst.items:
            errors += _check_evidence(item, chunks, f"{name}")

    # 3. 论文核心字段必须有值
    if not profile.layer2.hypotheses.items:
        warnings.append("hypotheses 为空（论文核心字段缺失）")
    if not profile.layer2.main_findings.items:
        warnings.append("main_findings 为空（论文核心字段缺失）")

    # 4. 去重检查
    dup = _find_duplicates(profile.layer2.hypotheses)
    for d in dup:
        warnings.append(f"假设疑似重复: {d[:40]}...")
    dup = _find_duplicates(profile.layer2.main_findings)
    for d in dup:
        warnings.append(f"发现疑似重复: {d[:40]}...")

    return errors, warnings


def _norm(s: str) -> str:
    """
    归一化用于宽松 evidence 匹配：
      1. 去掉所有空白
      2. 全角标点 → 半角
      3. 剥离 LaTeX 数学标记（$ \ { } _ ^），使 PDF 里的公式与 LLM 摘录对齐
    返回归一化后的紧凑字符串。
    """
    import re
    s = s.replace('，', ',').replace('。', '.').replace('；', ';').replace('：', ':')
    s = re.sub(r'[$\s\\{}_^{}]+', '', s)   # 去空白 + LaTeX 控制符
    s = re.sub(r'\s+', '', s)
    return s


def _evidence_in_chunk(evidence: str, chunk_text: str) -> bool:
    """evidence 是否可信地存在于 chunk_text 中（三级宽松匹配）。"""
    if not evidence or not chunk_text:
        return False
    # 1. 精确子串
    if evidence in chunk_text:
        return True
    ne, nc = _norm(evidence), _norm(chunk_text)
    # 2. 归一化后子串
    if ne and ne in nc:
        return True
    # 3. 模糊最佳对齐（容忍 LaTeX 改写 / 跨句合并），阈值 0.85
    if len(ne) < 20:
        return False
    from difflib import SequenceMatcher
    # 在 chunk 内滑动，找到与 evidence 最相似的一段
    win = min(len(ne), len(nc))
    if win < 20:
        return False
    best = 0.0
    for i in range(len(nc) - win + 1):
        r = SequenceMatcher(None, ne, nc[i:i + win]).ratio()
        if r > best:
            best = r
        if best >= 0.9:
            return True
    return best >= 0.85


def _check_evidence(ev: EvidencedValue, chunks: Dict[str, str], field: str) -> List[str]:
    """校验单条 evidence，返回错误列表"""
    errs: List[str] = []
    if not ev.value or not ev.value.strip():
        errs.append(f"{field}: value 为空")
        return errs
    if not ev.evidence or not ev.evidence.strip():
        errs.append(f"{field}: evidence 为空（value='{ev.value[:30]}'...）")
        return errs
    if ev.chunk_id not in chunks:
        errs.append(f"{field}: chunk_id 不存在 ({ev.chunk_id})")
        return errs
    chunk_text = chunks[ev.chunk_id]
    if not _evidence_in_chunk(ev.evidence, chunk_text):
        errs.append(f"{field}: evidence 不在 chunk_text 中 (chunk={ev.chunk_id})")
    return errs


def _find_duplicates(lst: EvidencedList) -> List[str]:
    """检测 value 重复的项，返回重复内容"""
    seen = set()
    dups = []
    for item in lst.items:
        v = item.value.strip()
        if v in seen:
            dups.append(v)
        seen.add(v)
    return dups
