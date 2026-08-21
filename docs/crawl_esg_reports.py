#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股上市公司 ESG 报告爬虫
==============================================
从巨潮资讯网 (cninfo.com.cn) 检索 A 股上市公司的 ESG/可持续发展/社会责任报告。

策略：
  - 绿色金融相关公司列表（银行、新能源、环保等）
  - 用 "公司名 + ESG/社会责任/可持续发展" 关键词搜索
  - 提取报告标题、PDF 链接、页数（通过 PDF 文件大小估算）
  - 标注"独立报告"或"年报内嵌"

输出：output/esg_reports_green_finance.xlsx
"""

import logging, os, random, re, time, json
from collections import Counter
from typing import List, Dict, Optional
from urllib.parse import quote, urljoin

import requests
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("esg")

# ===== 配置 =====
# 绿色金融相关公司：银行 + 新能源 + 环保 + 保险
COMPANIES = [
    # 银行（绿色信贷主力）
    ("601398", "工商银行"), ("601939", "建设银行"), ("601288", "农业银行"),
    ("601988", "中国银行"), ("600036", "招商银行"), ("601166", "兴业银行"),
    ("600000", "浦发银行"), ("601328", "交通银行"), ("000001", "平安银行"),
    ("002142", "宁波银行"), ("600016", "民生银行"), ("601818", "光大银行"),
    # 新能源
    ("300750", "宁德时代"), ("601012", "隆基绿能"), ("002594", "比亚迪"),
    ("300274", "阳光电源"), ("600438", "通威股份"), ("002459", "晶澳科技"),
    ("688599", "天合光能"), ("601615", "明阳智能"),
    # 环保
    ("300070", "碧水源"), ("603568", "伟明环保"), ("600323", "瀚蓝环境"),
    # 保险
    ("601318", "中国平安"), ("601628", "中国人寿"),
    # 其他绿色相关
    ("600900", "长江电力"), ("003816", "中国广核"),
]

SEARCH_KEYS = [
    ("ESG报告", "ESG"), ("环境社会及管治报告", "ESG"),
    ("社会责任报告", "社会责任"), ("可持续发展报告", "可持续发展"),
    ("环境信息披露报告", "环境信息"), ("碳中和报告", "碳中和"),
    ("绿色金融报告", "绿色金融"),
]

TARGET_PER_COMPANY = 3  # 每家公司最多取 3 份报告（让更多公司被覆盖）
TOTAL_TARGET = 80

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")


# ===== 工具函数 =====
def nap(lo=0.3, hi=0.8): time.sleep(random.uniform(lo, hi))


def api_search(stock_code: str, company_name: str, keyword: str,
               column: str = "szse", page_size: int = 20) -> List[Dict]:
    """调用巨潮资讯网公告查询 API"""
    url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    data = {
        "pageNum": "1",
        "pageSize": str(page_size),
        "column": column,
        "tabName": "fulltext",
        "plate": "",
        "stockCode": "",
        "searchkey": f"{company_name} {keyword}",
        "secid": "",
        "category": "",
        "trade": "",
        "seDate": "",
    }
    h = {"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"}

    try:
        resp = requests.post(url, data=data, headers=h, timeout=15)
        if resp.status_code != 200:
            return []

        r = resp.json()
        if r is None:
            return []

        announcements = r.get("announcements") or []
        return announcements
    except Exception as e:
        log.debug("API error for %s: %s", company_name, e)
        return []


def classify_report(title: str) -> str:
    """根据标题判断报告类型"""
    t = title.lower()
    if "esg" in t or "环境社会" in t or "环境、社会" in t:
        return "ESG报告"
    if "可持续发展" in t:
        return "可持续发展报告"
    if "社会责任" in t:
        return "社会责任报告"
    if "环境信息" in t:
        return "环境信息披露报告"
    if "碳中和" in t or "碳达峰" in t:
        return "碳中和报告"
    if "绿色金融" in t:
        return "绿色金融报告"
    if "年报" in t and any(w in t for w in ["环境", "社会", "治理", "esg", "可持续"]):
        return "年报（含ESG章节）"
    if "年报" in t:
        return "年报（含ESG章节）"  # 年报可能含社会责任章节
    return "其他"


def is_esg_related(title: str) -> bool:
    """判断标题是否与 ESG 相关"""
    keywords = ["ESG", "esg", "环境社会", "社会责任", "可持续发展",
                "环境信息", "碳中和", "碳达峰", "绿色金融",
                "环境、社会", "管治报告", "企业社会责任"]
    return any(kw in title for kw in keywords)


def is_announcement_notice(title: str) -> bool:
    """判断是否为'关于发布XX报告的公告'而非报告本身"""
    notice_patterns = [
        r"关于.*(?:发布|披露|公开).*(?:报告|年报)的公告",
        r"关于.*(?:发布|披露|公开).*(?:报告|年报)的提示性",
        r"自愿披露.*公告",
    ]
    for pat in notice_patterns:
        if re.search(pat, title):
            return True
    return False


def estimate_pages(adjunct_size: int) -> str:
    """根据 PDF 文件大小(KB)估算页数"""
    if not adjunct_size or adjunct_size <= 0:
        return "未知"
    # 经验：普通 PDF 每页约 50-200KB，ESG 报告通常图文丰富约 100KB/页
    pages = max(1, int(adjunct_size / 80))
    return str(pages)


def get_column(code: str) -> str:
    """根据股票代码判断所属交易所"""
    if code.startswith(("60", "68")):
        return "sse"
    else:
        return "szse"


# ===== 主搜索 =====
def search_all() -> List[Dict]:
    """遍历所有公司和关键词组合，检索 ESG 报告"""
    log.info("🔍 检索 %d 家公司 × %d 个关键词", len(COMPANIES), len(SEARCH_KEYS))

    all_results = []
    seen_urls = set()

    for stock_code, company_name in COMPANIES:
        company_results = []
        column = get_column(stock_code)

        for search_key, report_type in SEARCH_KEYS:
            announcements = api_search(stock_code, company_name, search_key, column)

            for a in announcements:
                title = a.get("announcementTitle", "")
                if not title or len(title) < 5:
                    continue
                if not is_esg_related(title):
                    continue
                if is_announcement_notice(title):
                    continue  # 跳过"关于发布XX报告的公告"

                pdf_url = a.get("adjunctUrl", "")
                if pdf_url and not pdf_url.startswith("http"):
                    pdf_url = "https://static.cninfo.com.cn/" + pdf_url

                # 去重（按 PDF URL）
                if pdf_url and pdf_url in seen_urls:
                    continue
                if pdf_url:
                    seen_urls.add(pdf_url)

                adjunct_size = a.get("adjunctSize") or 0
                try:
                    adjunct_size = int(adjunct_size)
                except (ValueError, TypeError):
                    adjunct_size = 0

                timestamp = a.get("announcementTime") or 0
                year = ""
                if timestamp:
                    try:
                        year = time.strftime("%Y", time.localtime(timestamp / 1000))
                    except Exception:
                        pass
                # fallback: 从标题提取年份
                if not year:
                    ym = re.search(r"(20\d{2})", title)
                    if ym:
                        year = ym.group(1)

                report_cat = classify_report(title)
                pages = estimate_pages(adjunct_size)

                # 判断是独立报告还是年报内嵌
                note = "独立报告"
                if "年报" in title and report_cat in ("ESG报告", "社会责任报告"):
                    note = "年报内嵌（年报中含ESG/社会责任章节）"
                elif "年报" in title:
                    note = "年报（可能含ESG章节）"

                record = {
                    "company_name": company_name,
                    "stock_code": stock_code,
                    "report_title": title,
                    "report_year": year,
                    "report_type": report_cat,
                    "pdf_url": pdf_url,
                    "pages": pages,
                    "note": note,
                    "adjunct_size": adjunct_size,
                }
                company_results.append(record)

            nap()

        # 每家公司最多取 TARGET_PER_COMPANY 份
        company_results = _dedup_company(company_results)[:TARGET_PER_COMPANY]
        all_results.extend(company_results)

        if company_results:
            log.info("  [%s-%s] %d 份报告", stock_code, company_name, len(company_results))

    log.info("📊 合计 %d 份报告", len(all_results))
    return all_results


def _dedup_company(results: List[Dict]) -> List[Dict]:
    """同公司内去重（按标题相似度）"""
    if not results:
        return results
    out = []
    seen_titles = set()
    for r in results:
        # 简化的标题去重：取前30个字符
        t_key = r["report_title"][:40].strip().lower()
        if t_key not in seen_titles:
            seen_titles.add(t_key)
            out.append(r)
    return out


# ===== Excel 输出 =====
def write_excel(records: List[Dict], filepath: str):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ESG报告"

    headers = ["序号", "公司名称", "股票代码", "报告名称", "报告年份",
               "报告类型", "原文链接/下载链接", "报告页数(估)", "备注"]
    HF = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    HFT = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
    CF = Font(name="微软雅黑", size=10)
    BD = Border(left=Side(style="thin"), right=Side(style="thin"),
                top=Side(style="thin"), bottom=Side(style="thin"))

    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.fill = HF; c.font = HFT; c.border = BD
        c.alignment = Alignment(horizontal="center", vertical="center")

    for ri, rec in enumerate(records, 2):
        # 字段补全
        for k, d in [("report_title","标题未收录"), ("company_name",""), ("stock_code",""),
                     ("report_year",""), ("report_type",""), ("pdf_url",""),
                     ("pages","未知"), ("note","独立报告")]:
            if not rec.get(k, ""):
                rec[k] = d

        row = [ri - 1, rec["company_name"], rec["stock_code"],
               rec["report_title"], rec["report_year"], rec["report_type"],
               rec["pdf_url"], rec["pages"], rec["note"]]
        for ci, v in enumerate(row, 1):
            c = ws.cell(row=ri, column=ci, value=v)
            c.font = CF; c.border = BD
            c.alignment = (Alignment(horizontal="center", vertical="top")
                          if ci in (1, 2, 3, 5, 6, 8)
                          else Alignment(wrap_text=True, vertical="top"))

    widths = [6, 14, 10, 55, 8, 16, 55, 10, 30]
    for ci, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.freeze_panes = "A2"

    wb.save(filepath)
    log.info("📄 Excel: %s (%d 条)", filepath, len(records))


# ===== 主入口 =====
def main():
    import urllib3; urllib3.disable_warnings()
    log.info("=" * 60)
    log.info("🚀 ESG 报告爬虫 - 巨潮资讯网")
    log.info("   公司: %d 家 | 关键词: %d 组", len(COMPANIES), len(SEARCH_KEYS))
    log.info("=" * 60)

    all_records = search_all()

    # 去重
    seen = set()
    unique = []
    for r in all_records:
        u = r["pdf_url"].strip().lower()
        if u and u not in seen:
            seen.add(u)
            unique.append(r)

    log.info("📊 去重后 %d 份 → 输出前 %d 份", len(unique), min(len(unique), TOTAL_TARGET))
    unique = unique[:TOTAL_TARGET]

    fp = os.path.join(OUT, "esg_reports_green_finance.xlsx")
    write_excel(unique, fp)

    log.info("📈 统计:")
    for company, cnt in Counter(r["company_name"] for r in unique).most_common(15):
        log.info("    %-12s: %d 份", company, cnt)
    log.info("    %-12s: %d 份", "总计", len(unique))

    # 报告类型
    type_stats = Counter(r["report_type"] for r in unique)
    for t, cnt in type_stats.most_common():
        log.info("  [%s]: %d", t, cnt)

    log.info("=" * 60)
    log.info("🎉 完成! -> %s", fp)


if __name__ == "__main__":
    main()
