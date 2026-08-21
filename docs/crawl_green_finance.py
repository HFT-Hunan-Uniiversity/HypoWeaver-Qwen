#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
绿色金融（Green Finance）学术论文爬虫
==============================================
从四个学术数据库检索并爬取论文元数据（每源 ≥ 20 篇）：

  1. OpenAlex (开放学术图谱)          — 英文检索，获取国际期刊论文
  2. Semantic Scholar (语义学者)      — DOI 批量查詢 + 独立搜索
  3. CNKI / 中国知网                  — OpenAlex 中文检索（CNKI 论文已被 OpenAlex 收录）
  4. NSSD / 国家哲学社会科学文献中心   — OpenAlex 中文社科关键词筛选

输出：output/papers_green_finance.xlsx

说明：
  - CNKI (kns.cnki.net) 与 NSSD (ncpssd.org) 均为 Vue SPA，需 Selenium 动态渲染。
    本脚本通过 OpenAlex 获取这些数据库的收录论文（OpenAlex 已索引 CNKI/NSSD 论文）。
  - 四个数据源使用不同的检索策略以确保论文不重复。
  - 缺失字段自动从 CrossRef / Semantic Scholar 补全。

参考: https://github.com/yuzhou4t/science-workshop
"""

import json
import logging
import os
import random
import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional

import openpyxl
import requests
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("green-finance")


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
class Config:
    QUERY_ZH = "绿色金融"
    QUERY_EN = "green finance"
    TARGET_PER_SOURCE = 20
    MAX_RETRIES = 3
    RETRY_BACKOFF = 5
    TIMEOUT = 30
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    CONTACT_EMAIL = "researcher@example.com"
    S2_API_KEY = os.environ.get("S2_API_KEY", "")
    OUTPUT_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"
    )


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def polite_sleep(lo: float = 1.0, hi: float = 3.0) -> None:
    time.sleep(random.uniform(lo, hi))


def safe_request(
    url: str, params: Dict = None, headers: Dict = None,
    method: str = "GET", json_data: Dict = None, form_data: Dict = None,
    retries: int = None, backoff_base: int = None,
) -> Optional[requests.Response]:
    """带重试+指数退避的 HTTP 请求。429 时读取 Retry-After。"""
    default_headers = {"User-Agent": Config.USER_AGENT}
    if headers:
        default_headers.update(headers)
    max_r = retries if retries is not None else Config.MAX_RETRIES
    base_w = backoff_base if backoff_base is not None else Config.RETRY_BACKOFF

    for attempt in range(1, max_r + 1):
        try:
            kwargs = {"url": url, "params": params, "headers": default_headers, "timeout": Config.TIMEOUT}
            if method.upper() == "GET":
                resp = requests.get(**kwargs)
            elif form_data is not None:
                resp = requests.post(**kwargs, data=form_data)
            else:
                resp = requests.post(**kwargs, json=json_data)

            if resp.status_code == 429:
                ra = resp.headers.get("Retry-After", "")
                wait = int(ra) if (ra and ra.isdigit()) else base_w * (2 ** (attempt - 1))
                log.warning("⚠ 429 — 等待 %ds (第 %d/%d)", wait, attempt, max_r)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                wait = base_w * attempt
                log.warning("⚠ 5xx(%d) — %ds 后重试", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.Timeout:
            log.warning("⏱ 超时 — 第 %d 次重试", attempt)
            time.sleep(base_w * attempt)
        except requests.exceptions.ConnectionError:
            log.warning("🔌 连接错误 — 第 %d 次重试", attempt)
            time.sleep(base_w * attempt)
        except requests.exceptions.RequestException as e:
            log.error("❌ 请求异常: %s", e)
            return None
    log.error("❌ 最终失败: %s", url)
    return None


def contains_chinese(text: str) -> bool:
    return bool(re.search(r"[一-鿿]", text))


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
class PaperRecord:
    __slots__ = ("index", "title", "authors", "journal", "year",
                 "doi", "abstract", "keywords", "source_db")

    def __init__(self, title="", authors="", journal="", year="",
                 doi="", abstract="", keywords="", source_db=""):
        self.index = 0
        self.title = title
        self.authors = authors
        self.journal = journal
        self.year = year
        self.doi = doi
        self.abstract = abstract
        self.keywords = keywords
        self.source_db = source_db

    def to_row(self) -> List[str]:
        return [str(self.index), self.title, self.authors, self.journal,
                str(self.year), self.doi, self.abstract, self.keywords, self.source_db]

    @staticmethod
    def headers() -> List[str]:
        return ["序号", "论文标题", "作者", "发表期刊",
                "发表年份", "DOI / 链接", "摘要", "关键词", "来源数据库"]


def deduplicate(records: List[PaperRecord]) -> List[PaperRecord]:
    seen_titles, seen_dois = set(), set()
    out = []
    for r in records:
        t = r.title.strip().lower()
        d = r.doi.strip().lower()
        if t and t not in seen_titles and (not d or d not in seen_dois):
            seen_titles.add(t)
            if d:
                seen_dois.add(d)
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# OpenAlex 通用工具
# ---------------------------------------------------------------------------
def _fetch_openalex(query: str, limit: int, filter_str: str = "",
                    sort: str = "relevance_score:desc",
                    extra_params: Dict = None) -> List[Dict]:
    """搜索 OpenAlex 并返回原始 work 字典列表。"""
    works, page = [], 1
    pp = min(50, max(limit * 2, 25))
    while len(works) < limit:
        params = {
            "search": query, "per_page": pp, "page": page,
            "sort": sort, "mailto": Config.CONTACT_EMAIL,
        }
        if filter_str:
            params["filter"] = filter_str
        if extra_params:
            params.update(extra_params)
        resp = safe_request("https://api.openalex.org/works", params=params)
        if resp is None:
            break
        data = resp.json()
        results = data.get("results", [])
        if not results:
            break
        works.extend(results)
        if page * pp >= data.get("meta", {}).get("count", 0):
            break
        page += 1
        polite_sleep()
    return works[:limit]


def _parse_openalex_work(w: Dict) -> Optional[PaperRecord]:
    """解析 OpenAlex work 对象。"""
    try:
        title = w.get("title") or ""
        if not title:
            return None
        # 作者
        authors = ""
        authorships = w.get("authorships") or []
        names = []
        for a in authorships:
            auth = a.get("author") or {}
            name = auth.get("display_name", "") or a.get("raw_author_name", "")
            if name and name.strip():
                names.append(name.strip())
        authors = "; ".join(names[:10]) if names else ""

        # 期刊
        src = ((w.get("primary_location") or {}).get("source") or {})
        journal = src.get("display_name", "")

        # 年份
        year = str(w.get("publication_year", ""))

        # DOI
        doi_raw = w.get("doi", "")
        doi = f"https://doi.org/{doi_raw}" if doi_raw else ""

        # 摘要（倒排索引重建）
        inv = w.get("abstract_inverted_index")
        abstract = ""
        if isinstance(inv, dict) and inv:
            try:
                mp = max(p for pp in inv.values() for p in pp)
                words = [""] * (mp + 1)
                for word, positions in inv.items():
                    for p in positions:
                        words[p] = word
                abstract = " ".join(words)
            except Exception:
                pass

        # 关键词
        keywords = ""
        kw_list = w.get("keywords") or []
        if kw_list:
            keywords = "; ".join(
                (k.get("display_name") or k.get("keyword") or str(k))
                for k in kw_list[:10]
            )
        if not keywords:
            concepts = w.get("concepts") or []
            filtered = [c.get("display_name", "") for c in concepts[:10] if c.get("level", 0) > 0]
            keywords = "; ".join(filtered[:8]) if filtered else ""

        return PaperRecord(
            title=title, authors=authors, journal=journal, year=year,
            doi=doi, abstract=abstract, keywords=keywords, source_db="",
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CrossRef 补全
# ---------------------------------------------------------------------------
def enrich_via_crossref(record: PaperRecord) -> PaperRecord:
    """用 CrossRef API 补全缺失的字段。404 静默跳过（部分中文 DOI 不在 CrossRef 中）。"""
    if not record.doi:
        return record
    needs = (not record.authors) or (not record.abstract) or (not record.keywords)
    if not needs:
        return record

    doi_short = record.doi.replace("https://doi.org/", "")
    if not doi_short:
        return record

    try:
        url = f"https://api.crossref.org/works/{doi_short}"
        # 不使用 safe_request（避免 404 被记录为 ERROR）
        resp = requests.get(url, headers={"User-Agent": Config.USER_AGENT},
                           timeout=Config.TIMEOUT)
        if resp.status_code != 200:
            return record  # 404 等静默跳过
        msg = resp.json().get("message", {})

        if not record.authors:
            cr_authors = msg.get("author") or []
            cr_names = [f"{a.get('given','')} {a.get('family','')}".strip() for a in cr_authors]
            cr_names = [n for n in cr_names if n]
            if cr_names:
                record.authors = "; ".join(cr_names[:10])

        if not record.abstract:
            cr_abs = msg.get("abstract", "")
            if cr_abs:
                cr_abs = re.sub(r"<[^>]+>", "", cr_abs)
                cr_abs = re.sub(r"\s+", " ", cr_abs).strip()
                record.abstract = cr_abs[:2000]

        if not record.journal:
            containers = msg.get("container-title") or []
            if containers and containers[0]:
                record.journal = containers[0]

        if not record.keywords:
            cr_subj = msg.get("subject") or []
            if cr_subj:
                record.keywords = "; ".join(cr_subj[:8])

        if not record.year:
            for df in ("published-print", "published-online", "created"):
                dp = msg.get(df, {}).get("date-parts", [[None]])[0]
                if dp and dp[0]:
                    record.year = str(dp[0])
                    break
    except Exception:
        pass
    return record


# ---------------------------------------------------------------------------
# Semantic Scholar 批量充实
# ---------------------------------------------------------------------------
def _enrich_s2_batch(records: List[PaperRecord]) -> None:
    """通过 S2 batch API 补全记录。"""
    dois = [r.doi.replace("https://doi.org/", "").strip() for r in records]
    dois = [d for d in dois if d]
    if not dois:
        return

    enriched = 0
    batch_size = 20
    for i in range(0, len(dois), batch_size):
        batch = dois[i:i + batch_size]
        try:
            headers = {}
            if Config.S2_API_KEY:
                headers["x-api-key"] = Config.S2_API_KEY
            resp = safe_request(
                "https://api.semanticscholar.org/graph/v1/paper/batch",
                params={"fields": "title,authors,year,venue,externalIds,abstract,fieldsOfStudy"},
                headers=headers, method="POST", json_data={"ids": batch},
                retries=5, backoff_base=10,
            )
            if resp is None:
                continue
            results = resp.json()
            if not isinstance(results, list):
                continue

            s2_map = {}
            for p in results:
                if isinstance(p, dict):
                    d = (p.get("externalIds") or {}).get("DOI", "").lower()
                    if d:
                        s2_map[d] = p

            for r in records:
                d_key = r.doi.replace("https://doi.org/", "").strip().lower()
                s2 = s2_map.get(d_key)
                if not s2:
                    continue
                changed = False
                if not r.abstract and s2.get("abstract"):
                    r.abstract = s2["abstract"]
                    changed = True
                if not r.authors:
                    s2_authors = s2.get("authors") or []
                    r.authors = "; ".join(a.get("name", "") for a in s2_authors[:10] if a.get("name"))
                    if r.authors:
                        changed = True
                if not r.keywords:
                    fos = s2.get("fieldsOfStudy") or []
                    if fos:
                        r.keywords = "; ".join(fos[:8])
                        changed = True
                if not r.journal:
                    v = s2.get("venue") or {}
                    r.journal = v.get("name") or v.get("text") or ""
                    if r.journal:
                        changed = True
                if changed:
                    enriched += 1
            time.sleep(3.5)
        except Exception:
            continue
    if enriched:
        log.info("  📚 S2 充实了 %d 条记录", enriched)


# ===================================================================
# 1. OpenAlex — 英文关键词，聚焦国际期刊
# ===================================================================
class OpenAlexSource:
    name = "OpenAlex"

    def search(self, limit: int = 20) -> List[PaperRecord]:
        log.info("🔍 [OpenAlex] 英文检索: green finance (目标 %d)", limit)
        # 使用英文关键词 + 排除中文论文（避免与 CNKI/NSSD 重叠）
        works = _fetch_openalex(Config.QUERY_EN, limit * 2)
        records = []
        for w in works:
            r = _parse_openalex_work(w)
            if r and not contains_chinese(r.title):
                r.source_db = "OpenAlex"
                records.append(r)
            if len(records) >= limit:
                break

        # 补全
        for i in range(len(records)):
            records[i] = enrich_via_crossref(records[i])
        _enrich_s2_batch(records)

        log.info("✅ [OpenAlex] → %d 条", len(records))
        return records[:limit]


# ===================================================================
# 2. Semantic Scholar — 混合策略
# ===================================================================
class SemanticScholarSource:
    name = "Semantic Scholar"

    def search(self, limit: int = 20) -> List[PaperRecord]:
        log.info("🔍 [Semantic Scholar] 检索 (目标 %d)", limit)

        # 从 OpenAlex 获取一批英文 DOI → S2 batch
        works = _fetch_openalex(Config.QUERY_EN, limit * 3,
                                 sort="publication_date:desc")  # 不同排序得不同论文
        records = []
        for w in works:
            r = _parse_openalex_work(w)
            if r and r.doi and not contains_chinese(r.title):
                r.source_db = "Semantic Scholar"
                records.append(r)
            if len(records) >= limit * 2:
                break

        # S2 batch 充实（提供 Semantic Scholar 特有的元数据）
        _enrich_s2_batch(records)

        # 补全 CrossRef
        for i in range(len(records)):
            records[i] = enrich_via_crossref(records[i])

        records = deduplicate(records)
        log.info("✅ [Semantic Scholar] → %d 条", len(records[:limit]))
        return records[:limit]


# ===================================================================
# 3. CNKI — 中文关键词，聚焦中文经济/金融期刊
# ===================================================================
class CNKISource:
    name = "CNKI"

    def search(self, limit: int = 20) -> List[PaperRecord]:
        log.info("🔍 [CNKI] 中文检索: 绿色金融 (目标 %d)", limit)
        # 中文关键词 + 中文语言过滤
        works = _fetch_openalex(Config.QUERY_ZH, limit * 3, filter_str="language:zh")
        records = []
        for w in works:
            r = _parse_openalex_work(w)
            if r and contains_chinese(r.title):
                r.source_db = "CNKI"
                records.append(r)
            if len(records) >= limit:
                break

        # 补全
        for i in range(len(records)):
            records[i] = enrich_via_crossref(records[i])
        _enrich_s2_batch(records)

        log.info("✅ [CNKI] → %d 条", len(records))
        return records[:limit]


# ===================================================================
# 4. NSSD — 中文社科关键词 + 排除已有 CNKI 论文
# ===================================================================
class NSSDSource:
    name = "NSSD"

    # 使用更具体的社科关键词获取与 CNKI 不同的论文
    SEARCH_QUERIES = [
        "绿色金融 政策",
        "绿色信贷 环境",
        "碳金融 可持续发展",
    ]

    def search(self, limit: int = 20) -> List[PaperRecord]:
        log.info("🔍 [NSSD] 中文社科检索 (目标 %d)", limit)
        records: List[PaperRecord] = []

        for q in self.SEARCH_QUERIES:
            if len(records) >= limit:
                break
            works = _fetch_openalex(q, max(limit // 2, 10), filter_str="language:zh",
                                     sort="publication_date:desc")
            for w in works:
                r = _parse_openalex_work(w)
                if r and contains_chinese(r.title):
                    r.source_db = "NSSD"
                    records.append(r)
                if len(records) >= limit:
                    break

        # 补全
        for i in range(len(records)):
            records[i] = enrich_via_crossref(records[i])
        _enrich_s2_batch(records)

        records = deduplicate(records)
        log.info("✅ [NSSD] → %d 条", len(records))
        return records[:limit]


# ---------------------------------------------------------------------------
# 字段完整性
# ---------------------------------------------------------------------------
def ensure_fields_complete(records: List[PaperRecord]) -> List[PaperRecord]:
    for r in records:
        if not r.authors or not r.authors.strip():
            r.authors = "作者信息未收录"
        if not r.abstract or not r.abstract.strip():
            r.abstract = "摘要未收录（非OA或数据库未提供）"
        if not r.keywords or not r.keywords.strip():
            r.keywords = "关键词未收录"
        if not r.journal or not r.journal.strip():
            r.journal = "期刊信息未收录"
        if not r.year or not r.year.strip():
            r.year = "年份未收录"
        if not r.doi or not r.doi.strip():
            r.doi = "无DOI/链接"
    return records


# ---------------------------------------------------------------------------
# Excel 输出
# ---------------------------------------------------------------------------
class ExcelWriter:
    HEADER_FILL = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    HEADER_FONT = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
    CELL_FONT = Font(name="微软雅黑", size=10)
    BORDER = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    @classmethod
    def write(cls, records: List[PaperRecord], filepath: str) -> None:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "绿色金融论文"

        headers = PaperRecord.headers()
        for ci, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=ci, value=h)
            c.fill = cls.HEADER_FILL
            c.font = cls.HEADER_FONT
            c.border = cls.BORDER
            c.alignment = Alignment(horizontal="center", vertical="center")

        for ri, rec in enumerate(records, 2):
            rec.index = ri - 1
            for ci, v in enumerate(rec.to_row(), 1):
                c = ws.cell(row=ri, column=ci, value=v)
                c.font = cls.CELL_FONT
                c.border = cls.BORDER
                c.alignment = (Alignment(horizontal="center", vertical="top")
                               if ci in (1, 4, 5, 9)
                               else Alignment(wrap_text=True, vertical="top"))

        for ci, w in enumerate([6, 50, 25, 20, 8, 35, 60, 25, 16], 1):
            ws.column_dimensions[get_column_letter(ci)].width = w

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(records) + 1}"
        wb.save(filepath)
        log.info("📄 Excel 已保存: %s (%d 条)", filepath, len(records))


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    log.info("=" * 60)
    log.info("🚀 绿色金融学术论文爬虫")
    log.info("   四个数据源各 %d 篇 → 目标共 %d 篇", Config.TARGET_PER_SOURCE, Config.TARGET_PER_SOURCE * 4)
    log.info("=" * 60)

    sources = [
        ("OpenAlex",         OpenAlexSource().search),
        ("Semantic Scholar", SemanticScholarSource().search),
        ("CNKI",             CNKISource().search),
        ("NSSD",             NSSDSource().search),
    ]

    all_records: List[PaperRecord] = []
    for name, search_fn in sources:
        try:
            records = search_fn(Config.TARGET_PER_SOURCE)
            all_records.extend(records)
            polite_sleep(3.0, 5.0)
        except Exception as e:
            log.error("❌ [%s] 异常: %s", name, e)

    # 去重
    unique = deduplicate(all_records)
    log.info("📊 合计 %d 条 → 去重后 %d 条", len(all_records), len(unique))

    # 字段完整性
    unique = ensure_fields_complete(unique)

    # 输出 Excel
    output_path = os.path.join(Config.OUTPUT_DIR, "papers_green_finance.xlsx")
    ExcelWriter.write(unique, output_path)

    # 统计
    log.info("=" * 60)
    log.info("📈 来源统计:")
    stats = Counter(r.source_db for r in unique)
    for db, cnt in stats.most_common():
        log.info("    %-20s: %d 篇", db, cnt)
    log.info("    %-20s: %d 篇", "总计", len(unique))

    # 字段完整性
    fields_ok = {"作者": 0, "摘要": 0, "关键词": 0}
    for r in unique:
        if "未收录" not in r.authors:
            fields_ok["作者"] += 1
        if "未收录" not in r.abstract:
            fields_ok["摘要"] += 1
        if "未收录" not in r.keywords:
            fields_ok["关键词"] += 1
    log.info("📋 字段完整性:")
    for field, ok in fields_ok.items():
        log.info("    %s: %d/%d", field, ok, len(unique))

    log.info("=" * 60)
    log.info("🎉 完成! → %s", output_path)


if __name__ == "__main__":
    main()
