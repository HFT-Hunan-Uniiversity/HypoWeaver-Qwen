# ============================================================================
# 远程问答助手 — scripts/qa_remote.py
# ============================================================================
# 用法（本地执行，无需同步任何数据到本地）:
#   python scripts/qa_remote.py "绿色金融政策如何影响绿色技术创新"
#   python scripts/qa_remote.py                          # 交互模式
#
# 原理:
#   数据（cleaned/ + 1169 篇 KG + 19567 条向量 + DASHSCOPE_API_KEY）
#   全在服务器 /srv/green-finance-vector/ 上，本脚本通过 SSH 在服务器跑
#   AnswerEngine，把结果 JSON 拉回本地格式化显示。本地只有代码，无数据。
#
# 前提:
#   - 本机已配置免密 SSH（greenfinance-vector@106.53.153.215）
#   - 服务器 .env 已配置 DASHSCOPE_API_KEY（不会传回本地/聊天）
# ============================================================================

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

SERVER = "greenfinance-vector@106.53.153.215"
PROJECT_DIR = "/srv/green-finance-vector"

# Windows 终端中文乱码修复：强制 UTF-8 输出
# （终端若仍乱码，先执行 chcp 65001 切到 UTF-8 代码页）
import io
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ----------------------------------------------------------------------------
# 服务器端一次性执行的 Python 代码（由 SSH 调用）
# 通过环境变量 QA_QUESTION 传入问题，避免 shell 转义问题
# ----------------------------------------------------------------------------
_SERVER_RUNNER = r"""
import json, os, sys, time
sys.path.insert(0, ".")
os.environ.setdefault("DASHSCOPE_API_KEY", "")
from src.reason.answer_engine import AnswerEngine

q = os.environ.get("QA_QUESTION", "")
if not q:
    print(json.dumps({"error": "QA_QUESTION 为空"}, ensure_ascii=False))
    sys.exit(1)

t0 = time.time()
try:
    engine = AnswerEngine()
    result = engine.answer(q)
    result["_elapsed_s"] = round(time.time() - t0, 1)
    print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    import traceback
    print(json.dumps({"error": str(e), "_traceback": traceback.format_exc()[-800:]},
                     ensure_ascii=False))
    sys.exit(2)
"""


def run_remote(question: str, verbose: bool = False) -> dict:
    """在服务器上执行问答，返回结果 dict。"""
    remote_script = tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                                encoding="utf-8", delete=False)
    remote_script.write(_SERVER_RUNNER)
    remote_script.close()
    local_py = remote_script.name

    try:
        # 1. 上传 runner 到服务器
        subprocess.run(
            ["scp", "-q", local_py, f"{SERVER}:/tmp/qa_remote_runner.py"],
            check=True, timeout=30,
        )
        # 2. SSH 执行；问题通过环境变量传入（环境变量值直接传 JSON 安全）
        cmd = (
            f"ssh -o ConnectTimeout=15 {SERVER} "
            f"\"cd {PROJECT_DIR} && set -a && . ./.env && set +a && "
            f"source .venv/bin/activate && "
            f"QA_QUESTION={shlex.quote(question)} python /tmp/qa_remote_runner.py\""
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                               encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            return {"error": f"SSH 执行失败 (rc={proc.returncode})",
                    "_stderr": proc.stderr[-500:]}
        # 3. stdout 最后一行是 JSON（BGE 加载进度在 stderr）
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        if not lines:
            return {"error": "服务器无输出", "_stderr": proc.stderr[-500:]}
        try:
            return json.loads(lines[-1])
        except json.JSONDecodeError:
            return {"error": "结果解析失败", "_raw": proc.stdout[-1000:]}
    finally:
        Path(local_py).unlink(missing_ok=True)


def safe_print(*args, **kwargs):
    """兼容 Windows GBK 终端（跳过 emoji）。"""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        msg = " ".join(str(a) for a in args)
        # 移除 emoji 等非 ASCII 字符
        msg = msg.encode("ascii", errors="replace").decode("ascii")
        print(msg, **kwargs)


def print_result(result: dict) -> None:
    """格式化输出回答结果（与本地 qa_runner.py 输出风格一致）。"""
    if result.get("error"):
        safe_print(f"[错误] {result['error']}")
        if result.get("_stderr"):
            safe_print(f"   {result['_stderr'][-400:]}")
        return

    safe_print(f"\n{'='*60}")
    safe_print(f"Q: {result.get('question', '')}")
    safe_print(f"回答: {result.get('answer', '（无回答）')}")
    if result.get("conclusion"):
        safe_print(f"\n核心结论: {result['conclusion']}")
    safe_print(f"置信度: {result.get('confidence', 'medium')}")

    if result.get("graph_paths"):
        safe_print(f"\n知识图谱路径 ({len(result['graph_paths'])} 条):")
        for p in result["graph_paths"][:5]:
            safe_print(f"  {p['source']} --{p['relation']}--> {p['target']}  "
                       f"[{p['source_doc'][:25]}]")
        if len(result['graph_paths']) > 5:
            safe_print(f"  ... 还有 {len(result['graph_paths']) - 5} 条")

    if result.get("evidence"):
        safe_print(f"\n原文证据 ({len(result['evidence'])} 条):")
        for e in result["evidence"][:3]:
            safe_print(f"  [{e['source_doc'][:25]}] {e['snippet'][:80]}...")
        if len(result['evidence']) > 3:
            safe_print(f"  ... 还有 {len(result['evidence']) - 3} 条")

    if result.get("source_papers"):
        safe_print(f"\n涉及论文 ({len(result['source_papers'])} 篇):")
        for p in result["source_papers"][:5]:
            safe_print(f"  - {p[:40]}")
        if len(result['source_papers']) > 5:
            safe_print(f"  ... 还有 {len(result['source_papers']) - 5} 篇")

    if result.get("_elapsed_s"):
        safe_print(f"\n耗时: {result['_elapsed_s']}s（含服务器检索+LLM 生成）")


def main():
    verbose = "--verbose" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args:
        q = " ".join(args)
        safe_print(f"[远程问答] 问题: {q}")
        safe_print(f"  服务器: {SERVER}:{PROJECT_DIR}")
        safe_print(f"  数据: 1169 篇 / 19567 向量 / 10138 节点（全部在服务器）\n")
        result = run_remote(q, verbose)
        print_result(result)
        return

    # 交互模式
    safe_print("远程问答（SSH 服务器全量数据）")
    safe_print("输入 'q' 退出\n")
    while True:
        try:
            q = input("Q: ").strip()
        except (EOFError, KeyboardInterrupt):
            safe_print("\n退出")
            break
        if not q:
            continue
        if q.lower() == "q":
            safe_print("退出")
            break
        result = run_remote(q)
        print_result(result)
        safe_print()


if __name__ == "__main__":
    main()