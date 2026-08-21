# MinerU 云端精准解析 API 封装
# API 文档: https://mineru.net/apiManage/docs
# 每日免费 2000 页，pipeline 模型
# 本地文件上传模式（签名上传 + 轮询）

import json, os, re, sys, time
from pathlib import Path
from typing import Optional

import requests
import fitz  # PyMuPDF 读页数，不花 API 额度

# Windows GBK 控制台输出兜底: 强制 UTF-8, 避免 emoji/特殊字符崩溃
if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ============ 配置 ============

API_KEY = os.environ.get("MINERU_API_KEY", "")
if not API_KEY:
    print("⚠️  MINERU_API_KEY 未设置，解析功能不可用", file=sys.stderr)
BASE_URL = "https://mineru.net/api/v4"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

# 页数限额文件路径（与 src/parse/config/ 对齐）
QUOTA_FILE = Path(__file__).resolve().parent.parent / "config" / "mineru_quota.json"
DAILY_LIMIT = 2000


# ============ 页数限额跟踪 ============

def _load_quota() -> dict:
    """读取当日页数使用情况"""
    today = time.strftime("%Y-%m-%d")
    if QUOTA_FILE.exists():
        data = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
        if data.get("date") == today:
            return data
    # 每日重置
    return {"date": today, "pages_used": 0, "daily_limit": DAILY_LIMIT}


def _save_quota(data: dict):
    QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUOTA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_pdf_page_count(pdf_path: str) -> int:
    """用 PyMuPDF 快速读 PDF 页数，不花 API 额度"""
    doc = fitz.open(pdf_path)
    pages = doc.page_count
    doc.close()
    return pages


def check_quota(pdf_path: str) -> tuple:
    """
    检查配额，返回 (ok: bool, pages_needed: int, pages_remaining: int)
    ok=False 时不要提交
    """
    pages_needed = get_pdf_page_count(pdf_path)
    quota = _load_quota()
    pages_remaining = DAILY_LIMIT - quota["pages_used"]

    if pages_needed > pages_remaining:
        return False, pages_needed, pages_remaining

    return True, pages_needed, pages_remaining


def deduct_quota(pages: int):
    """解析成功后扣减额度"""
    quota = _load_quota()
    quota["pages_used"] += pages
    _save_quota(quota)


def get_quota_summary() -> str:
    """返回当日配额使用摘要"""
    quota = _load_quota()
    remaining = DAILY_LIMIT - quota["pages_used"]
    return f"📊 MinerU 配额: 今日已用 {quota['pages_used']}/{DAILY_LIMIT} 页，剩余 {remaining} 页"


# ============ MinerU API 调用 ============

def parse_pdf(pdf_path: str, model_version: str = "pipeline",
              language: str = "ch", enable_table: bool = True,
              enable_formula: bool = True, is_ocr: bool = False,
              poll_interval: int = 3, poll_timeout: int = 300) -> Optional[dict]:
    """
    上传 PDF 到 MinerU 云端解析，轮询等待结果。

    返回:
      {
        "markdown": str,         # full.md 文本
        "content_list": dict,    # content_list.json 结构化数据
        "zip_url": str,          # zip 包下载链接
        "pages": int,            # 实际页数（扣减配额用）
      }
    或 None（失败/超限）
    """
    pdf_path = str(pdf_path)

    # ===== 1. 配额检查 =====
    ok, pages_needed, remaining = check_quota(pdf_path)
    if not ok:
        print(f"❌ 配额不足: 需要 {pages_needed} 页，仅剩 {remaining} 页。跳过 {pdf_path}")
        return None

    file_name = os.path.basename(pdf_path)
    print(f"📄 提交 {file_name} ({pages_needed} 页)")

    # MinerU 限制: files.data_id ≤ 128 字节 (UTF-8)
    # 超长文件名截断 + 哈希保证唯一
    data_id = file_name
    if len(data_id.encode("utf-8")) > 120:
        import hashlib
        suffix = hashlib.md5(data_id.encode("utf-8")).hexdigest()[:10]
        # 按字节截断到 110 字节 + "_" + suffix(10 字节) = 121 字节
        encoded = data_id.encode("utf-8")
        truncated = encoded[:110].decode("utf-8", errors="ignore")
        data_id = truncated + "_" + suffix

    # ===== 2. 获取签名上传链接 =====
    url = f"{BASE_URL}/file-urls/batch"
    data = {
        "files": [{"name": file_name, "data_id": data_id}],
        "model_version": model_version,
        "language": language,
        "enable_table": enable_table,
        "enable_formula": enable_formula,
        "is_ocr": is_ocr,
    }
    resp = requests.post(url, headers=HEADERS, json=data, timeout=30)
    if resp.status_code != 200:
        print(f"❌ 获取上传链接失败: HTTP {resp.status_code}")
        return None

    result = resp.json()
    if result.get("code") != 0:
        print(f"❌ 获取上传链接失败: {result.get('msg')}")
        return None

    batch_id = result["data"]["batch_id"]
    upload_url = result["data"]["file_urls"][0]
    print(f"  ✅ 上传链接获取成功, batch_id={batch_id[:12]}...")

    # ===== 3. PUT 上传文件到 OSS =====
    with open(pdf_path, "rb") as f:
        put_resp = requests.put(upload_url, data=f, timeout=120)
    if put_resp.status_code not in (200, 201):
        print(f"  ❌ 文件上传失败: HTTP {put_resp.status_code}")
        return None
    print(f"  ✅ 文件上传成功")

    # ===== 4. 轮询等待解析完成 =====
    # 批量查询结果
    query_url = f"{BASE_URL}/extract-results/batch/{batch_id}"
    start = time.time()
    state_labels = {"waiting-file": "等待文件上传", "pending": "排队中",
                    "running": "解析中", "converting": "格式转换中"}

    while time.time() - start < poll_timeout:
        resp = requests.get(query_url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            time.sleep(poll_interval)
            continue

        result = resp.json()
        if result.get("code") != 0:
            time.sleep(poll_interval)
            continue

        items = result["data"]["extract_result"]
        for item in items:
            state = item["state"]
            elapsed = int(time.time() - start)

            if state == "done":
                zip_url = item["full_zip_url"]
                print(f"  ✅ [{elapsed}s] 解析完成")

                # ===== 5. 下载结果 =====
                return _download_result(zip_url, file_name, pages_needed)

            if state == "failed":
                err_msg = item.get("err_msg", "未知错误")
                print(f"  ❌ [{elapsed}s] 解析失败: {err_msg}")
                return None

            label = state_labels.get(state, state)
            if elapsed % 15 < 3:  # 每 15 秒打印一次，减少输出
                print(f"  ⏳ [{elapsed}s] {label}...")

        time.sleep(poll_interval)

    print(f"  ❌ 轮询超时 ({poll_timeout}s)")
    return None


def _download_result(zip_url: str, file_name: str, pages: int) -> dict:
    """下载并解析 MinerU 结果 zip 包"""
    import io, zipfile

    # 下载 zip
    resp = requests.get(zip_url, timeout=120)
    if resp.status_code != 200:
        print(f"  ❌ 下载结果失败: HTTP {resp.status_code}")
        return None

    # 解压
    result = {"markdown": "", "content_list": {}, "zip_url": zip_url, "pages": pages}
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        # 取 full.md
        for name in z.namelist():
            if name.endswith("full.md"):
                result["markdown"] = z.read(name).decode("utf-8")
                break

        # 取 content_list.json（结构化数据，含表格/图片元数据）
        for name in z.namelist():
            if name.endswith("content_list.json"):
                try:
                    result["content_list"] = json.loads(z.read(name).decode("utf-8"))
                except json.JSONDecodeError:
                    result["content_list"] = {}
                break

    # 扣减配额
    deduct_quota(pages)
    print(f"  ✅ 配额已扣减: {pages} 页")

    return result


# ============ 命令行测试 ============
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python mineru_api.py <pdf_path>")
        print(get_quota_summary())
        sys.exit(1)

    result = parse_pdf(sys.argv[1])
    if result:
        print(f"\n{'='*60}")
        print(f"Markdown 长度: {len(result['markdown'])} 字符")
        print(f"Content list: {len(result['content_list'])} 项" if result['content_list'] else "无 content_list")
        print(f"\n--- 前 500 字符 ---")
        print(result['markdown'][:500])
    else:
        print("解析失败")