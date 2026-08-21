# ============================================================================
# KG 批量流水线 — src/kg/pipeline.py
# ============================================================================
# 遍历 37 篇 cleaned_md + cleaned_meta，对每篇：
#   1. 加载元数据与正文
#   2. 调用 extractor 抽取 KnowledgeGraph（含 qwen-max 三元组）
#   3. 调用 concept_edges 补充共现边
#   4. 写入 Neo4j（MERGE 去重）
#   5. 记录成功 / 失败到失败清单 + 断点续跑文件
#
# 异常设计：
#   - 单篇失败不影响整批，写失败清单后继续下一篇
#   - 失败文档可单独重试（已成功的不重复处理）
#   - 断点文件 (kg_done.json) 记录已成功 doc_id，按需清理
# ============================================================================

from __future__ import annotations

import datetime
import json
import sys
import time
from pathlib import Path
from typing import List, Optional, Set, Tuple

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.config import (
    ARTIFACTS_KG_DIR,
    CLEANED_DIR,
    CLEANED_META_DIR,
    FAILED_LIST_PATH,
    RECORD_PATH,
    ENABLE_ALIAS,
    ensure_dirs,
    resolve_input_pairs,
)
from src.kg.neo4j_client import Neo4jClient
from src.kg.extractor import extract_relations_from_doc
from src.kg.concept_edges import extract_co_occur
from src.status import (
    mark_kg_done as status_mark_kg_done,
    mark_kg_failed as status_mark_kg_failed,
    get_pending_kg_docs,
    load_status,
    save_status,
)


# ============================================================================
# 加载输入
# ============================================================================
def load_meta(meta_path: Path) -> dict:
    """加载 cleaned_meta/*.json，返回 extra_info 字典。"""
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
        return {"_error": f"元数据 JSON 解析失败: {e}"}
    if not isinstance(raw, dict):
        return {"_error": "元数据 JSON 不是字典"}
    # 读取 extra_info 内部字段
    extra = raw.get("extra_info") or {}
    if extra:
        # 从 extra_info 拉取（run_batch_mineru 的产出）
        meta = dict(extra)
        meta["doc_id"] = raw.get("doc_id") or meta.get("doc_id", "")
        # title 可能为空（英文文档顶层 title=None）；回退到 doc_id
        if not meta.get("title"):
            meta["title"] = raw.get("title") or meta["doc_id"] or ""
        return meta
    # extra_info 为空（部分早期处理的文件）；从顶层各字段直接构建
    meta = {
        "doc_id": raw.get("doc_id", ""),
        "title": raw.get("title", ""),
        "authors": _safe_list(raw.get("authors")),
        "abstract": raw.get("abstract") or None,
        "keywords": _safe_list(raw.get("keywords")),
        "journal": raw.get("journal"),
        "year": raw.get("year"),
        "doi": raw.get("doi"),
    }
    # 如果顶层也没有，尝试从 metadata_extraction_report 兜底
    if not meta["authors"] and not meta["abstract"]:
        report_meta = _fallback_meta_from_report(meta["doc_id"])
        if report_meta:
            report_meta.update({k: v for k, v in meta.items() if v})
            meta = report_meta
    return meta


def load_md(md_path: Path) -> str:
    """加载 cleaned/*.md，返回正文。"""
    try:
        return md_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as e:
        return ""


def _safe_list(v) -> list:
    """把任意值安全转成 list[str]。"""
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x]
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return []


def _fallback_meta_from_report(doc_id: str) -> dict:
    """从 metadata_extraction_report.json 读取该文档元数据（顶层 extra_info 缺失时的兜底）。

    注意：cleaned md 的文件名经过 safe_filename 清洗（去掉了标点如 ——、：），
    而报告里的文件名保留原始 PDF 名，所以用"书名号/破折号剥离后再比对"。
    """
    import re

    _PUNCT = re.compile(r"[^\w一-鿿-]")
    target_norm = _PUNCT.sub("", doc_id)
    try:
        report_path = PROJECT_ROOT / "metadata_extraction_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for d in report.get("details", []):
            raw_name = d.get("file", "")
            raw_stem = Path(raw_name).stem
            if _PUNCT.sub("", raw_stem) == target_norm or raw_stem == doc_id:
                return {
                    "doc_id": doc_id,
                    "title": d.get("title") or doc_id,
                    "authors": _safe_list(d.get("authors")) or [],
                    "abstract": d.get("abstract") or None,
                    "keywords": _safe_list(d.get("keywords")) or [],
                    "journal": d.get("journal"),
                    "year": d.get("year"),
                    "doi": d.get("doi"),
                }
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {}


# ============================================================================
# 结构化日志（jsonl）
# ============================================================================
def _log_dir() -> Path:
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def _append_log(event: str, **kwargs) -> None:
    """追加一条结构化日志到 logs/kg_YYYY-MM-DD.jsonl。"""
    log_path = _log_dir() / f"kg_{datetime.date.today().isoformat()}.jsonl"
    entry = {"time": datetime.datetime.now().isoformat(), "event": event, **kwargs}
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ============================================================================
# 断点续跑：读写已成功的 doc_id 集合
# ============================================================================
def load_done_set() -> Set[str]:
    """从 kg_done.json 读取已成功 doc_id 集合（兼容旧格式）。"""
    try:
        data = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(data)
        if isinstance(data, dict):
            return set(data.get("done", []))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return set()


def save_done(doc_id: str, done_set: Set[str]) -> None:
    """追加一个 doc_id 到 kg_done.json（兼容旧格式）。"""
    done_set.add(doc_id)
    RECORD_PATH.write_text(
        json.dumps({"done": sorted(done_set)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # 同时写入 unified status
    status_mark_kg_done(doc_id)


# ============================================================================
# 失败清单（JSONL，每行一个失败记录）
# ============================================================================
def append_failed(doc_id: str, error: str, stage: str = "extract") -> None:
    """追加一条失败记录到 failed_docs.jsonl + unified status。"""
    entry = {
        "doc_id": doc_id,
        "stage": stage,
        "error": error,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with open(FAILED_LIST_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # 同时写入 unified status
    status_mark_kg_failed(doc_id, error, stage)
    _append_log("kg_failed", doc_id=doc_id, stage=stage, error=str(error)[:200])


# ============================================================================
# 处理单篇论文
# ============================================================================
def process_one(
    doc_id: str,
    md_path: Path,
    meta_path: Path,
    neo4j: Optional[Neo4jClient],
    use_llm: bool = True,
    enable_co_occur: bool = True,
) -> Tuple[bool, str]:
    """
    处理单篇论文，返回 (成功标志, 消息)。

    流程：加载元数据 → 加载正文 → LLM 抽取 KG → 共现补边 → 写入 Neo4j.
    """
    # 1. 加载元数据
    meta = load_meta(meta_path)
    if "_error" in meta:
        return False, meta["_error"]
    if not meta.get("doc_id"):
        meta["doc_id"] = doc_id
    if not meta.get("title"):
        meta["title"] = doc_id

    # 2. 加载正文
    md_text = load_md(md_path)
    if not md_text:
        append_failed(doc_id, "正文为空 (cleaned md 不可读)", "load_md")
        return False, "正文为空"

    # 3. LLM 抽取 KnowledgeGraph
    try:
        kg = extract_relations_from_doc(doc_id, md_text, meta, use_llm=use_llm)
    except Exception as e:
        msg = f"LLM 抽取异常: {e}"
        append_failed(doc_id, msg, "extract")
        return False, msg

    if kg is None:
        msg = "LLM 抽取返回 None（API 失败或 JSON 解析失败）"
        append_failed(doc_id, msg, "extract")
        return False, msg

    # 4. 概念共现补边（零 Token）
    if enable_co_occur and len(kg.concepts) >= 2:
        concept_names = [c.name for c in kg.concepts]
        try:
            co_edges = extract_co_occur(md_text, concept_names, doc_id)
            kg.relations.extend(co_edges)
        except Exception as e:
            # 共现失败不中断流程
            pass

    # 5. 写入 Neo4j
    if neo4j and neo4j.is_connected:
        try:
            ok, msg = neo4j.write_kg(kg)
            if not ok:
                append_failed(doc_id, msg, "neo4j_write")
                return False, msg
        except Exception as e:
            msg = f"Neo4j 写入异常: {e}"
            append_failed(doc_id, msg, "neo4j_write")
            return False, msg
    else:
        # 无 Neo4j 时仍输出 KG 到本地文件以便调试
        _dump_kg_local(kg)
        pass  # 无 Neo4j 不报错，仅保存本地

    return True, kg


def _dump_kg_local(kg) -> None:
    """将 KnowledgeGraph 保存为本地 JSON 文件（供调试/无 Neo4j 环境）。"""
    try:
        out_path = ARTIFACTS_KG_DIR / f"{kg.doc_id}.kg.json"
        out_path.write_text(
            json.dumps(
                {
                    "doc_id": kg.doc_id,
                    "paper": kg.paper.model_dump(exclude_none=True),
                    "authors": [a.model_dump(exclude_none=True) for a in kg.authors],
                    "concepts": [c.model_dump(exclude_none=True) for c in kg.concepts],
                    "methods": [m.model_dump(exclude_none=True) for m in kg.methods],
                    "datasets": [d.model_dump(exclude_none=True) for d in kg.datasets],
                    "relations": [
                        {
                            "source": r.source,
                            "target": r.target,
                            "relation": r.relation.value,
                            "confidence": r.confidence,
                            "evidence": r.evidence.evidence[:200],
                            "source_doc": r.evidence.source_doc,
                        }
                        for r in kg.relations
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


# ============================================================================
# 批量运行
# ============================================================================
def run_batch(
    use_llm: bool = True,
    enable_co_occur: bool = True,
    max_docs: Optional[int] = None,
    skip_done: bool = True,
    retry_failed: bool = False,
) -> Tuple[int, int, List[str]]:
    """
    批量运行 KG 构建流水线。

    参数:
      use_llm:        是否调用 qwen-max 做三元组抽取（False = 仅元数据 KG）
      enable_co_occur: 是否生成概念共现边
      max_docs:       最多处理论文数（None = 全部）
      skip_done:      是否跳过已成功 doc_id（断点续跑）
      retry_failed:   是否重新处理失败文档（True = 忽略失败清单，重试全部）

    返回 (成功数, 失败数, 失败 doc_id 列表)。
    """
    ensure_dirs()

    # 1. 扫描输入
    pairs = resolve_input_pairs()
    print(f"📂 共 {len(pairs)} 篇论文待处理")

    if not pairs:
        print("⚠️  无输入数据（cleaned/ 或 cleaned_meta/ 为空）")
        return 0, 0, []

    # 2. 断点续跑
    done_set = set()
    if skip_done:
        done_set = load_done_set()
        if retry_failed:
            done_set.clear()  # 重试失败：清空 done 记录，重新跑
        _remove_failed_ids(done_set)
        print(f"⏭️  已跳过 {len(done_set)} 篇（之前成功）")

    # 3. 连接 Neo4j
    neo4j = Neo4jClient()
    connected = neo4j.connect()
    if not connected:
        print("  ⚠️  Neo4j 未连接，KG 写入本地文件（仅调试）")

    # 4. 逐篇处理
    success = 0
    failed = 0
    failed_ids: List[str] = []
    total = min(max_docs, len(pairs)) if max_docs else len(pairs)

    # 确定候选列表
    candidates = []
    for doc_id, md_path, meta_path in pairs:
        if skip_done and doc_id in done_set:
            continue
        candidates.append((doc_id, md_path, meta_path))
        if max_docs and len(candidates) >= max_docs:
            break

    print(f"🚀 实际处理 {len(candidates)} 篇\n")

    for i, (doc_id, md_path, meta_path) in enumerate(candidates, 1):
        print(f"[{i}/{len(candidates)}] 📄 {doc_id[:60]}")
        t0 = time.time()

        ok, result = process_one(
            doc_id, md_path, meta_path, neo4j=neo4j,
            use_llm=use_llm, enable_co_occur=enable_co_occur,
        )

        elapsed = time.time() - t0
        if ok:
            kg = result
            print(f"  ✅ 成功 ({elapsed:.1f}s) | 概念 {len(kg.concepts)} 个, "
                  f"方法 {len(kg.methods)} 个, 关系 {len(kg.relations)} 条")
            save_done(doc_id, done_set)
            _append_log("kg_done", doc_id=doc_id,
                        concepts=len(kg.concepts), methods=len(kg.methods),
                        relations=len(kg.relations), elapsed_s=round(elapsed, 1))
            success += 1
        else:
            print(f"  ❌ 失败: {result} ({elapsed:.1f}s)")
            failed += 1
            failed_ids.append(doc_id)

        if i < len(candidates):
            time.sleep(0.5)  # 请求间隔

    # 5. 关闭 Neo4j 连接
    neo4j.close()

    # 6. 报告
    print(f"\n{'='*60}")
    print(f"📊 完成: 成功 {success} / 失败 {failed} / 共 {len(candidates)}")
    print(f"失败清单（可重试）: {FAILED_LIST_PATH}")
    if failed_ids:
        print(f"失败文档: {', '.join(failed_ids[:10])}{'...' if len(failed_ids) > 10 else ''}")
    print(f"断点记录: {RECORD_PATH}")
    print(f"本地 KG 备份: {ARTIFACTS_KG_DIR}")

    return success, failed, failed_ids


def _remove_failed_ids(done_set: Set[str]) -> None:
    """从完成集中剔除失败清单里的 doc_id（重试模式）。"""
    try:
        with open(FAILED_LIST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    did = entry.get("doc_id")
                    if did in done_set:
                        done_set.discard(did)
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass


# ============================================================================
# CLI
# ============================================================================
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="KG 批量流水线：抽取三元组 → 写入 Neo4j"
    )
    parser.add_argument("--max", type=int, default=None, help="最大处理篇数")
    parser.add_argument("--no-llm", action="store_true", help="不调用 LLM（仅元数据 KG）")
    parser.add_argument("--no-cooccur", action="store_true", help="不生成共现边")
    parser.add_argument("--no-skip-done", action="store_true", help="不跳过已成功的（重新跑所有）")
    parser.add_argument("--retry-failed", action="store_true", help="重试失败文档")
    parser.add_argument("--single", type=str, default=None, help="仅处理单篇（doc_id 或文件名）")
    parser.add_argument("--mode", type=str, default=None,
                        choices=["incremental", "full", "retry_failed"],
                        help="运行模式（覆盖 --retry-failed / --no-skip-done）")

    args = parser.parse_args()

    # --mode 快捷参数
    if args.mode == "full":
        args.no_skip_done = True
    elif args.mode == "retry_failed":
        args.retry_failed = True

    if args.single:
        # 单篇模式
        sid = args.single
        # 去掉 .md 后缀
        if sid.endswith(".md"):
            sid = sid[:-3]
        md_path = CLEANED_DIR / f"{sid}.md"
        meta_path = CLEANED_META_DIR / f"{sid}.json"
        if not md_path.exists():
            print(f"❌ 未找到: {md_path}")
            return 1
        if not meta_path.exists():
            print(f"❌ 未找到: {meta_path}")
            return 1

        ensure_dirs()
        neo4j = Neo4jClient()
        connected = neo4j.connect()
        if not connected:
            print("  ⚠️  Neo4j 未连接，仅保存本地")

        ok, msg = process_one(
            sid, md_path, meta_path, neo4j=neo4j,
            use_llm=not args.no_llm, enable_co_occur=not args.no_cooccur,
        )
        neo4j.close()
        if ok:
            print(f"✅ 单篇完成: {sid}")
            return 0
        print(f"❌ 单篇失败: {msg}")
        return 1

    # 批量模式
    run_batch(
        use_llm=not args.no_llm,
        enable_co_occur=not args.no_cooccur,
        max_docs=args.max,
        skip_done=not args.no_skip_done,
        retry_failed=args.retry_failed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())