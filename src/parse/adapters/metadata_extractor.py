# 本地元数据抽取器(CNKI 中文论文)
# 零成本: 只用 PyMuPDF + 正则, 不依赖任何外部 API
# 从 PDF 第一页文本中抽: 标题 / 作者 / 摘要 / 关键词 / 期刊名 / DOI

import re
from pathlib import Path
from typing import Optional, Dict, Any

import fitz  # PyMuPDF

from src.parse.adapters.llm_metadata import extract_with_llm
from src.parse.config.doc_types import infer_doc_type


# ============ 可疑结果校验(触发 LLM 重抽) ============

# 明显不是论文标题/作者的词: 大学名/期刊名/模板残留/页眉
_SUS_TITLE_WORDS = re.compile(
    r'(University|College|Institute|School|Department|'
    r'Journal|Review|Research|Science|Elsevier|Springer|'
    r'MsWord|Style\s*file|Template|Word\s*file|'
    r'Received|Accepted|Available|Volume|Issue|Pages|'
    r'Electronic\s*copy|Working\s*Paper|Discussion\s*Paper)',
    re.I
)


def _title_suspicious(title: Optional[str]) -> bool:
    """标题可信度: 含大学/期刊/模板残留词 → 可疑"""
    if not title:
        return False
    # 纯英文短标题(如 "ESG" 单词)或含模板词
    if _SUS_TITLE_WORDS.search(title):
        return True
    # 标题太短(<8字符)且是英文, 不像完整标题
    if re.fullmatch(r'[A-Za-z\s]{1,10}', title):
        return True
    return False


# 作者位置抽到期刊名/机构名的特征
_SUS_AUTHOR_WORDS = re.compile(
    r'(Journal|Review|Research|Science|University|College|Institute|'
    r'School|Department|Press|Papers?|Conference|Symposium|'
    r'Business\s*Strategy|Open\s*Journal|Aalborg|Elsevier|Springer)',
    re.I
)


def _authors_suspicious(authors: list) -> bool:
    """作者可信度: 抽到期刊名/机构名 → 可疑"""
    if not authors:
        return False
    for a in authors:
        if _SUS_AUTHOR_WORDS.search(a):
            return True
    return False


# ============ 核心抽取逻辑 ============

def extract_metadata(pdf_path: str, doc_type: str = "paper") -> Dict[str, Any]:
    """
    从 PDF 文件直接抽取元数据。

    doc_type 决定抽取策略（从配置注册表读）：
      - "regex+llm": 正则优先，缺失/可疑字段走千问补抽（论文）
      - "llm_only":  直接千问全量抽取（政策/ESG/新闻/未知）

    返回:
      {
        "title": str | None,
        "authors": [str],
        "abstract": str | None,
        "keywords": [str],
        "journal": str | None,
        "doi": str | None,
        "year": str | None,
        "issuer": str | None,      # 政策: 发文机关
        "doc_number": str | None, # 政策: 文号
        "date": str | None,       # 政策/新闻: 发布日期
        "extraction_method": str,
        "extraction_notes": [str],
      }
    """
    from src.parse.config.doc_types import get_meta_strategy

    pdf_path = str(pdf_path)
    notes = []

    doc = fitz.open(pdf_path)
    try:
        pages = doc.page_count

        # 1) 尝试 PDF 元数据
        pdf_meta = doc.metadata
        title_from_meta = (pdf_meta.get("title") or "").strip()
        author_from_meta = (pdf_meta.get("author") or "").strip()

        # 2) 从正文抽 (扫描前 3 页)
        p_text = ""
        for i in range(min(3, pages)):
            p_text += (doc[i].get_text() + "\n")

        # 统一换行, 清理多余空白
        p_text = re.sub(r'\r\n?', '\n', p_text)
        p_text = re.sub(r'[ \t]+', ' ', p_text)

        strategy = get_meta_strategy(doc_type)

        # ===== 策略 A: 论文 → 正则优先 + LLM 补抽 =====
        if strategy == "regex+llm":
            return _extract_paper_metadata(p_text, title_from_meta, author_from_meta, notes)

        # ===== 策略 B: 非论文 → LLM 全量抽取 =====
        notes.append(f"文档类型 {doc_type} 使用 LLM 全量抽取")
        print(f"  🤖 调用千问 LLM 全量抽取 ({doc_type})")
        llm_result = extract_with_llm(p_text, doc_type)

        if not llm_result:
            notes.append("LLM 全量抽取失败")
            return {
                "title": title_from_meta or None,
                "authors": [author_from_meta] if author_from_meta else [],
                "abstract": None, "keywords": [], "journal": None,
                "doi": None, "year": None,
                "issuer": None, "doc_number": None, "date": None,
                "extraction_method": "pdf_metadata", "extraction_notes": notes,
            }

        notes.append("LLM 全量抽取成功")
        return {
            "title": llm_result.get("title") or title_from_meta or None,
            "authors": llm_result.get("authors") or ([author_from_meta] if author_from_meta else []),
            "abstract": llm_result.get("abstract"),
            "keywords": llm_result.get("keywords") or [],
            "journal": None, "doi": None,
            "year": _extract_year(p_text),
            "issuer": llm_result.get("issuer"),
            "doc_number": llm_result.get("doc_number"),
            "date": llm_result.get("date"),
            "extraction_method": "llm",
            "extraction_notes": notes,
        }
    finally:
        doc.close()


def _extract_paper_metadata(p_text: str, title_from_meta: str, author_from_meta: str, notes: list) -> Dict[str, Any]:
    """论文元数据: 正则优先 + LLM 补抽"""
    title = _extract_title(p_text, title_from_meta)
    authors = _extract_authors(p_text, author_from_meta)
    abstract = _extract_abstract(p_text)
    keywords = _extract_keywords(p_text)
    journal = _extract_journal(p_text)
    year = _extract_year(p_text)
    doi = _extract_doi(p_text)

    method = "pymupdf"
    llm_called = False
    if not title and not authors:
        method = "pdf_metadata"
        notes.append("第一页正文未找到标题/作者, 回退到 PDF 元数据")

    # ===== LLM fallback: 正则缺失字段或可疑结果走千问补抽 =====
    missing_fields = []
    if not title: missing_fields.append("title")
    elif _title_suspicious(title):
        missing_fields.append("title(可疑)")
        notes.append(f"正则标题可疑({title[:40]}...)，触发 LLM 重抽")
    if not abstract: missing_fields.append("abstract")
    if not keywords: missing_fields.append("keywords")
    if not authors:
        missing_fields.append("authors")
    elif _authors_suspicious(authors):
        missing_fields.append("authors(可疑)")
        notes.append(f"正则作者可疑({authors}...)，触发 LLM 重抽")

    if missing_fields:
        notes.append(f"正则缺失字段 {missing_fields}，调用千问 LLM fallback...")
        print(f"  🤖 调用千问 LLM 补抽: {missing_fields}")
        llm_result = extract_with_llm(p_text, "paper")
        llm_called = True

        if llm_result:
            if (not title or _title_suspicious(title)) and llm_result.get("title"):
                title = llm_result["title"]
                notes.append(f"LLM 补全标题: {title[:50]}...")
                print(f"    ✅ LLM 补全标题: {title[:50]}...")
            if not abstract and llm_result.get("abstract"):
                abstract = llm_result["abstract"]
                notes.append("LLM 补全摘要")
                print(f"    ✅ LLM 补全摘要 ({len(abstract)} 字)")
            if not keywords and llm_result.get("keywords"):
                keywords = llm_result["keywords"]
                notes.append(f"LLM 补全关键词: {keywords}")
                print(f"    ✅ LLM 补全关键词: {keywords}")
            if (not authors or _authors_suspicious(authors)) and llm_result.get("authors"):
                authors = llm_result["authors"]
                notes.append("LLM 补全作者")
                print(f"    ✅ LLM 补全作者: {authors}")
        else:
            notes.append("LLM fallback 调用失败")
            print(f"    ⚠️  LLM fallback 调用失败")

    if not abstract:
        notes.append("未找到摘要")
    if not keywords:
        notes.append("未找到关键词")

    return {
        "title": title or title_from_meta or None,
        "authors": authors or ([author_from_meta] if author_from_meta else []),
        "abstract": abstract,
        "keywords": keywords,
        "journal": journal,
        "doi": doi,
        "year": year,
        "issuer": None, "doc_number": None, "date": None,
        "extraction_method": "pymupdf+llm" if llm_called else method,
        "extraction_notes": notes,
    }


# ============ 各字段抽取 ============

def _extract_title(text: str, meta_title: str) -> Optional[str]:
    """
    定位标题: 排除期刊名/摘要/关键词等干扰行。
    策略: 找第一页中"最大字号"(视觉上居中的段落)。
    退化: 如果 meta_title 有值, 优先用。
    """
    # 优先用 PDF 元数据
    if meta_title and len(meta_title) > 4 and "摘要" not in meta_title:
        return meta_title

    lines = text.split('\n')
    lines = [l.strip() for l in lines if l.strip()]

    # 排除列表: 不可能是标题的行
    skip_patterns = re.compile(
        r'^(第\d+期|No\.?\s*\d+|年|月|vol\.?\s*|'
        r'摘\s*要|关键\s*词|参考\s*文献|'
        r'收稿日期|基金项目|作者简介|'
        r'中图分类号|文献标识码|文章编号|'
        r'doi|DOI|'
        r'[A-Z]{2,}\s*$)',  # 纯英文期刊缩略名
        re.I
    )

    candidates = []
    for i, line in enumerate(lines):
        if skip_patterns.match(line):
            continue
        # 标题特征: 长度 5-60 字符, 不含句号(标题一般无句号)
        if 5 <= len(line) <= 60 and '。' not in line and '，' not in line:
            # 排除明显的期刊名: 含"Journal"、"学报"、"研究"但不含"基于"/"影响"等论文词汇
            if re.match(r'^(Journal|学报|研究|经济|管理|金融|科学|技术|社会|大学|学院)', line, re.I) and len(line) < 20:
                if not any(k in line for k in ("基于", "影响", "视角", "证据", "效应")):
                    continue
            candidates.append((i, line))

    # 取第一个候选(通常标题在第 3-8 行)
    for i, c in candidates[:3]:
        # 检查前后行: 标题后一行通常是作者名
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            # 作者名特征: 2-4 个中文字符, 无标点
            if re.match(r'^[一-鿿]{2,4}$', next_line):
                return c
        # 标题后跟着"摘 要"的情况
        if i + 1 < len(lines) and re.match(r'摘\s*要', lines[i + 1]):
            return c

    # 退化: 取第一个非排除的长句
    for c in candidates[:1]:
        return c[1]

    return None


def _extract_authors(text: str, meta_author: str) -> list:
    """
    抽作者: 标题后一行, 或"摘 要"前一行。
    支持多个作者用空格/逗号/分号分隔。
    中文: 2-4 字姓名
    英文: 识别 "First Last" 或 "Last, First" 格式
    """
    lines = text.split('\n')
    lines = [l.strip() for l in lines if l.strip()]

    authors = []

    # 策略1: 找标题行(长的、非排除的)的下一行
    title_idx = None
    skip_patterns = re.compile(
        r'^(第\d+期|No\.?\s*\d+|年|月|vol\.?\s*|'
        r'摘\s*要|关键\s*词|参考\s*文献|'
        r'收稿日期|基金项目|作者简介|'
        r'中图分类号|文献标识码|文章编号|'
        r'doi|DOI|'
        r'[A-Z]{2,}\s*$)', re.I
    )
    for i, line in enumerate(lines):
        if skip_patterns.match(line):
            continue
        if 5 <= len(line) <= 60 and '。' not in line and '，' not in line:
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # 中文作者: 2-4 字
                if re.match(r'^[一-鿿]{2,4}$', next_line):
                    title_idx = i
                    break
                # 英文作者: 含逗号或 "First Last, First Last" 格式
                if re.match(r'^[A-Z][a-z]+ [A-Z][a-z]+', next_line) or ',' in next_line:
                    title_idx = i
                    break

    # 策略2: 找作者行
    start = title_idx + 1 if title_idx is not None else 0
    for i in range(start, min(start + 5, len(lines))):
        line = lines[i]
        # 中文作者
        cns = re.findall(r'[一-鿿]{2,4}', line)
        if cns and len(''.join(cns)) / max(len(line), 1) > 0.5:
            authors.extend(cns)
            break
        # 英文作者: "Last, First" 或 "First Last" 模式
        en_parts = re.split(r'[;；,，\s]{2,}', line)
        en_names = []
        for p in en_parts:
            p = p.strip()
            # "First Last" or "Last, First"
            if re.match(r'^[A-Z][a-z]+[ ,][A-Z][a-z]+', p):
                en_names.append(p)
            # "First Middle Last"
            elif re.match(r'^[A-Z][a-z]+ [A-Z]\.? [A-Z][a-z]+$', p):
                en_names.append(p)
        if en_names:
            authors.extend(en_names)
            break

    if not authors and meta_author and meta_author != "CNKI":
        authors = [meta_author]

    # 去重
    seen = set()
    unique = []
    for a in authors:
        if a not in seen:
            seen.add(a)
            unique.append(a)

    return unique


def _extract_abstract(text: str) -> Optional[str]:
    """
    抽摘要: 中文"摘 要" 或 英文 "Abstract" 引导。
    兼容: 全角空格(\\u3000)、半角空格、混合空格。
    英文摘要可能跨多行, 没有明确结束标记, 取到 Keywords/JEL/1./章节前。
    """
    # 中文: "摘　　要" 或 "摘要" 标记
    m = re.search(
        r'(摘[\s　]{0,3}要[\s　]{0,3}[:：]?\s*)(.+?)(?=关键[\s　]{0,3}词|关键词|Ｉ|Ⅰ|一、|二、|$|\n\s*\n\s*\n)',
        text, re.I | re.DOTALL
    )
    if m:
        abstract = m.group(2).strip()
        abstract = re.sub(r'\s+', ' ', abstract)
        return abstract[:2000]

    # 英文: "Abstract" 单独一行或带冒号, 后面内容到 Keywords/JEL/1./\n\n 前
    m = re.search(
        r'(?:^|\n)\s*[Aa]bstract\s*[:：]?\s*\n(.+?)(?=\n\s*(?:Keywords|JEL|INTRODUCTION|1\.\s|I\.\s|$|\n\s*\n))',
        text, re.DOTALL
    )
    if m:
        abstract = m.group(1).strip()
        abstract = re.sub(r'\s+', ' ', abstract)
        return abstract[:2000]

    return None


def _extract_keywords(text: str) -> list:
    """
    抽关键词: 中文"关键词" 或 英文 "Keywords" 引导, 分号/空格/逗号分隔。
    兼容全角空格。
    """
    # 中文
    m = re.search(
        r'(关键[\s　]{0,3}词[\s　]{0,3}[:：]?\s*)(.+?)(?=\n\s*\n|中图分类号|$|\n\d+\s*[、.．])',
        text, re.I | re.DOTALL
    )
    if m:
        kw_text = m.group(2).strip()
        keywords = re.split(r'[;；;、\s]{1,3}', kw_text)
        keywords = [k.strip().strip('。"＂') for k in keywords if k.strip() and len(k.strip()) >= 2]
        return keywords[:10]

    # 英文
    m = re.search(
        r'(?:^|\n)\s*[Kk]eywords?\s*[:：]?\s*(.+?)(?=\n\s*\n|$|\n[IJ\d]\.?\s)',
        text, re.DOTALL
    )
    if m:
        kw_text = m.group(1).strip()
        keywords = re.split(r'[;；,、\s]{1,3}', kw_text)
        keywords = [k.strip().strip('.') for k in keywords if k.strip() and len(k.strip()) >= 2]
        return keywords[:10]

    return []


def _extract_journal(text: str) -> Optional[str]:
    """抽期刊名: 第一页文本中出现的期刊名称"""
    lines = text.split('\n')
    lines = [l.strip() for l in lines if l.strip()]

    if lines:
        first = lines[0]
        # 期刊名特征: 2-15 个中文字符, 不含标点
        if re.match(r'^[一-鿿（）()]{2,15}$', first):
            return first

    # 退化: 有些期刊名在第二行(如"地理科学" + "Geographical Science")
    for line in lines[1:5]:
        if re.match(r'^[一-鿿（）()]{2,15}$', line):
            return line

    return None


def _extract_year(text: str) -> Optional[str]:
    """抽年份: 找 20xx 年份"""
    m = re.search(r'(20\d{2})', text)
    if m:
        return m.group(1)
    return None


def _extract_doi(text: str) -> Optional[str]:
    """抽 DOI"""
    m = re.search(r'(10\.\d{4,}/[^\s,，；;]+)', text)
    if m:
        return m.group(1).strip()
    return None


# ============ 批量分析 ============

def batch_analyze(pdf_dir: str) -> dict:
    """
    批量分析目录下所有 PDF 的抽取率。
    返回统计信息。
    """
    pdf_dir = Path(pdf_dir)
    # 注意: Windows glob 大小写不敏感, *.pdf + *.PDF 会重复匹配同一批文件
    # 用后缀统一判断, 避免重复统计
    pdfs = sorted(
        p for p in pdf_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf"
    )

    total = len(pdfs)
    stats = {
        "total": total,
        "title_found": 0,
        "author_found": 0,
        "abstract_found": 0,
        "keywords_found": 0,
        "journal_found": 0,
        "year_found": 0,
        "doi_found": 0,
        "details": [],
    }

    for pdf in pdfs:
        dt, _ = infer_doc_type(pdf.name, str(pdf))
        meta = extract_metadata(str(pdf), dt)
        stats["title_found"] += 1 if meta["title"] else 0
        stats["author_found"] += 1 if meta["authors"] else 0
        stats["abstract_found"] += 1 if meta["abstract"] else 0
        stats["keywords_found"] += 1 if meta["keywords"] else 0
        stats["journal_found"] += 1 if meta["journal"] else 0
        stats["year_found"] += 1 if meta["year"] else 0
        stats["doi_found"] += 1 if meta["doi"] else 0

        stats["details"].append({
            "file": pdf.name,
            "title": meta["title"],
            "authors": meta["authors"],
            "abstract": meta["abstract"],
            "abstract_len": len(meta["abstract"]) if meta["abstract"] else 0,
            "keywords": meta["keywords"],
            "journal": meta["journal"],
            "year": meta["year"],
            "doi": meta["doi"],
            "notes": meta["extraction_notes"],
        })

    return stats


def print_report(stats: dict):
    """打印抽取率报告"""
    t = stats["total"]
    print(f"\n{'='*60}")
    print(f"📊 元数据抽取率报告 (共 {t} 篇)")
    print(f"{'='*60}")
    print(f"  标题:     {stats['title_found']}/{t} = {stats['title_found']/t*100:.0f}%")
    print(f"  作者:     {stats['author_found']}/{t} = {stats['author_found']/t*100:.0f}%")
    print(f"  摘要:     {stats['abstract_found']}/{t} = {stats['abstract_found']/t*100:.0f}%")
    print(f"  关键词:   {stats['keywords_found']}/{t} = {stats['keywords_found']/t*100:.0f}%")
    print(f"  期刊名:   {stats['journal_found']}/{t} = {stats['journal_found']/t*100:.0f}%")
    print(f"  年份:     {stats['year_found']}/{t} = {stats['year_found']/t*100:.0f}%")
    print(f"  DOI:      {stats['doi_found']}/{t} = {stats['doi_found']/t*100:.0f}%")
    print(f"{'='*60}")

    # 列出失败的
    print(f"\n❌ 抽取失败的详情:")
    fail_count = 0
    for d in stats["details"]:
        issues = []
        if not d["title"]: issues.append("无标题")
        if not d["authors"]: issues.append("无作者")
        if not d["abstract"]: issues.append("无摘要")
        if not d["keywords"]: issues.append("无关键词")
        if issues:
            fail_count += 1
            print(f"  [{d['file']}]\n      {'; '.join(issues)}")
            if d["notes"]:
                for n in d["notes"]:
                    print(f"      提示: {n}")
    if fail_count == 0:
        print("  (全部成功!)")


# ============ CLI ============
if __name__ == "__main__":
    import sys, json

    if len(sys.argv) > 1 and sys.argv[1] == "batch":
        pdf_dir = sys.argv[2] if len(sys.argv) > 2 else "PDFs"
        stats = batch_analyze(pdf_dir)
        print_report(stats)
        # 保存详细结果
        out_path = Path(pdf_dir).parent / "metadata_extraction_report.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"\n📁 详细报告保存: {out_path}")
    else:
        # 单文件测试
        pdf = sys.argv[1] if len(sys.argv) > 1 else "PDFs/绿色金融政策如何影响绿色技术创新——基于高耗能企业的经验证据_周莹莹.pdf"
        meta = extract_metadata(pdf)
        print(json.dumps(meta, ensure_ascii=False, indent=2))