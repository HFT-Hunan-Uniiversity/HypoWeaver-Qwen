# ============================================================================
# 切片引擎 (Chunker) — C 角色技术规划 §3
# ============================================================================
# 把一篇清洗后的 markdown (含 #【章节】语义标记) 切成：
#   Layer 0: 元数据层（标题/摘要/关键词，不切）
#   Layer 1: 语义层（按 #【章节】 → ## 标题 → 段落，最大 semantic_max_tokens）
#   Layer 2: 滑动窗口层（重叠 overlap tokens）
# 输出 ChunkPayload 列表，供分类器 → 检索 / PaperProfile 抽取使用。
# ============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from schemas.chunk_schema import (
    ChunkLevel, ChunkPayload, ChunkingConfig, build_chunk_id,
)

# 语义标记: #【摘要】 #【理论假设】 ... 注入在章节标题前一行
_SEM_MARKER = re.compile(r'^#【(.+?)】\s*$')

# 标题: "## 一、引言" / "## 二、理论分析与研究假设" / "# 标题"
_HEADING = re.compile(r'^(#{1,5})\s+(.*?)\s*$')

# 段内按句切分的最小句号集合
_SENT_SPLIT = re.compile(r'(?<=[。；;！？])')


def _estimate_tokens(text: str) -> int:
    """粗略估计 token 数（中文字约 1.5 字/token，英文约 4 字符/token）"""
    # 简化：中文按字计（~1x），英文按空格分词计
    cjk = len(re.findall(r'[一-鿿]', text))
    ascii_words = len(re.findall(r'[A-Za-z0-9_\-]+', text))
    return cjk + ascii_words


def _split_by_max_tokens(paras: List[str], max_tokens: int) -> List[str]:
    """把超长段落按句号拆分，保证每段 ≤ max_tokens"""
    out: List[str] = []
    for para in paras:
        if _estimate_tokens(para) <= max_tokens:
            out.append(para)
            continue
        # 按句子切，再贪心合并
        sents = [s for s in _SENT_SPLIT.split(para) if s.strip()]
        buf = ""
        for s in sents:
            if _estimate_tokens(buf + s) > max_tokens and buf:
                out.append(buf.strip())
                buf = s
            else:
                buf += s
        if buf.strip():
            out.append(buf.strip())
    return out


def chunk_markdown(
    doc_id: str,
    md_text: str,
    metadata: dict,
    config: Optional[ChunkingConfig] = None,
) -> List[ChunkPayload]:
    """
    主入口：切分一篇清洗后的 markdown。

    参数:
      doc_id:   B 阶段 ParsedDoc.doc_id
      md_text:  cleaned/*.md 内容
      metadata: 元数据（title/authors/abstract/keywords/journal/year 等）

    返回 ChunkPayload 列表（metadata + semantic + sliding）。
    """
    config = config or ChunkingConfig()

    # ---- Layer 0: 元数据层 ----
    meta_chunk = _build_metadata_chunk(doc_id, metadata, config)

    # ---- 按语义标记 + 标题切语义层 ----
    sections = _split_sections(md_text)   # [(sem_name, heading_level, heading_title, body), ...]

    semantic: List[ChunkPayload] = []
    seq = 0
    for sem, level, heading_title, body in sections:
        # 先按空行分段落
        paras = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
        paras = _split_by_max_tokens(paras, config.semantic_max_tokens)
        for para in paras:
            if _estimate_tokens(para) < config.min_chunk_tokens:
                continue
            seq += 1
            semantic.append(ChunkPayload(
                chunk_id=build_chunk_id(doc_id, seq, "semantic"),
                doc_id=doc_id,
                source_type=metadata.get("source_type", "paper"),
                chunk_level=ChunkLevel.SEMANTIC.value,
                chunk_seq=seq,
                chunk_text=para,
                token_count=_estimate_tokens(para),
                metadata=dict(metadata),
                section_title=f"{sem} / {heading_title}" if sem else heading_title,
                section_level=level,
            ))

    # ---- Layer 2: 滑动窗口层 ----
    sliding = _build_sliding(doc_id, md_text, metadata, semantic[-1].chunk_seq if semantic else 0,
                             config)

    return [meta_chunk] + semantic + sliding


def _build_metadata_chunk(doc_id: str, meta: dict, config: ChunkingConfig) -> ChunkPayload:
    text_parts = []
    if meta.get("title"):
        text_parts.append(f"标题: {meta['title']}")
    if meta.get("authors"):
        text_parts.append(f"作者: {'、'.join(meta['authors'])}")
    if meta.get("abstract"):
        text_parts.append(f"摘要: {meta['abstract']}")
    if meta.get("keywords"):
        text_parts.append(f"关键词: {'; '.join(meta['keywords'])}")

    return ChunkPayload(
        chunk_id=build_chunk_id(doc_id, 0, "metadata"),
        doc_id=doc_id,
        source_type=meta.get("source_type", "paper"),
        chunk_level=ChunkLevel.METADATA.value,
        chunk_seq=0,
        chunk_text="\n".join(text_parts),
        token_count=_estimate_tokens("\n".join(text_parts)),
        metadata=dict(meta),
        section_title="元数据",
        section_level=0,
    )


def _split_sections(md_text: str) -> List[Tuple[Optional[str], Optional[int], str, str]]:
    """
    按 "#【章节】" 语义标记 + markdown 标题拆段。
    返回 [(sem_name, heading_level, heading_title, body), ...]
    """
    lines = md_text.split("\n")
    sections: List[Tuple[Optional[str], Optional[int], str, str]] = []
    cur_sem: Optional[str] = None
    cur_level: Optional[int] = None
    cur_title = ""
    cur_body: List[str] = []

    def flush():
        if cur_body or cur_title:
            sections.append((cur_sem, cur_level, cur_title, "\n".join(cur_body)))
        cur_body.clear()

    for line in lines:
        m = _SEM_MARKER.match(line.strip())
        if m:
            cur_sem = m.group(1)
            continue
        h = _HEADING.match(line)
        if h:
            flush()
            cur_level = len(h.group(1))
            cur_title = h.group(2).strip()
            cur_sem = cur_sem  # 保持当前语义标记（可能持续到下一个 #【】）
            continue
        cur_body.append(line)

    flush()
    return sections


def _build_sliding(doc_id: str, md_text: str, metadata: dict, start_seq: int,
                   config: ChunkingConfig) -> List[ChunkPayload]:
    """滑动窗口层：把全文摊平成纯段落后按窗口切"""
    # 去掉标题行与语义标记，只保留正文文本
    body_lines = [l for l in md_text.split("\n")
                  if not _SEM_MARKER.match(l.strip()) and not _HEADING.match(l)]
    full = re.sub(r'\s+', ' ', "\n".join(body_lines)).strip()

    if not full:
        return []

    chars_per_tok = 1.5  # 中文近似
    win_chars = int(config.sliding_window_size * chars_per_tok)
    step_chars = int((config.sliding_window_size - config.sliding_overlap) * chars_per_tok)

    chunks: List[ChunkPayload] = []
    seq = start_seq
    start = 0
    while start < len(full):
        end = min(start + win_chars, len(full))
        text = full[start:end].strip()
        if _estimate_tokens(text) >= config.min_chunk_tokens:
            seq += 1
            chunks.append(ChunkPayload(
                chunk_id=build_chunk_id(doc_id, seq, "sliding"),
                doc_id=doc_id,
                source_type=metadata.get("source_type", "paper"),
                chunk_level=ChunkLevel.SLIDING.value,
                chunk_seq=seq,
                chunk_text=text,
                token_count=_estimate_tokens(text),
                metadata=dict(metadata),
            ))
        if end >= len(full):
            break
        start = end - int(config.sliding_overlap * chars_per_tok)

    return chunks


# ===== 命令行测试 =====
if __name__ == "__main__":
    import sys
    md_path = sys.argv[1] if len(sys.argv) > 1 else \
        "cleaned/绿色金融政策如何影响绿色技术创新基于高耗能企业的经验证据_周莹莹.md"
    chunks = chunk_markdown(
        "test_doc",
        Path(md_path).read_text(encoding="utf-8"),
        {"title": "测试论文", "source_type": "paper"},
    )
    print(f"共 {len(chunks)} 个 chunk (metadata=1 + semantic + sliding)")
    for c in chunks[:8]:
        print(f"  [{c.chunk_level}] seq={c.chunk_seq} tok={c.token_count} title={c.section_title}")
        print(f"      {c.chunk_text[:60]}...")
