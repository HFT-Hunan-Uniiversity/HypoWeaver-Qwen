# 清洗规则(引擎无关) + 章节语义标记注入
# 输入: MinerU 输出的 raw markdown + doc_type
# 输出: 清洗后 + 注入 #【摘要】#【理论假设】 等语义标记的 markdown

import re
from typing import Dict, List, Optional, Tuple

from src.parse.config.doc_types import get_section_map


# 可选的标题序号前缀: "一、" / "（一）" / "(1)" / "1." / "1、" 等
_NUM_PREFIX = r'(?:[一二三四五六七八九十]+[、.．]?|\([一二三四五六七八九十]+\)|[（(][一二三四五六七八九十]+[)）]|\d+[.、．]?)?'


def inject_section_markers(md: str, doc_type: str = "paper") -> str:
    """
    根据文档类型加载对应的章节标记映射，匹配标题行前插 #【语义名】。
    doc_type 从配置注册表读取 section_map。
    """
    section_map = get_section_map(doc_type)
    if not section_map:
        # 没有配置则用 paper 默认
        section_map = get_section_map("paper")

    for sem, keys in section_map.items():
        # 关键词按长度降序排，优先匹配长词（如"研究假设"先于"假设"）
        keys = sorted(keys, key=len, reverse=True)
        pattern = (
            r'(?m)^(\s*#{1,4}\s*' + _NUM_PREFIX
            + r'(' + '|'.join(keys) + r')[\s:：、.．\-—]*[^\n]*)$'
        )
        md = re.sub(pattern, r'#【%s】\n\1' % sem, md, flags=re.IGNORECASE)
    return md


# ============ 基础清洗规则(原自研逻辑简化) ============

def remove_header_footer(md: str) -> str:
    """去掉明显的页眉页脚: 期刊名/页码/DOI 行等"""
    lines = md.split("\n")
    out = []
    for line in lines:
        s = line.strip()
        # 纯页码行
        if re.fullmatch(r"\d{1,4}", s):
            continue
        # 页眉页脚常见 pattern: 期刊名 + 年份/卷期 + 页码
        if re.fullmatch(r"(.*(journal|review|research|journal of|journalof).*)(\d{4}|vol\.?\s*\d+|\d+\s*[-–]\s*\d+)", s, re.I):
            continue
        out.append(line)
    return "\n".join(out)


def merge_paragraphs(md: str) -> str:
    """合并被 PDF 换行打断的段落(行尾无双空格且非空行/非标题/非列表项则接续)"""
    lines = md.split("\n")
    out = []
    for line in lines:
        s = line.rstrip()
        if not out:
            out.append(s)
            continue
        prev = out[-1]
        # 段落接续条件: 当前行非空、非标题、非列表; 上一行非空、非标题、非列表、非代码块、行尾无 2 空格
        if (s.strip() and not s.lstrip().startswith(("#", "-", "*", "|", ">", "```", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "0."))
                and prev.strip() and not prev.lstrip().startswith(("#", "-", "*", "|", ">", "```", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "0."))
                and not prev.rstrip().endswith("  ")):
            out[-1] = prev + " " + s.strip()
        else:
            out.append(s)
    return "\n".join(out)


def normalize_special_chars(md: str) -> str:
    """统一特殊字符(引号/破折号/空白)"""
    md = md.replace("“", '"').replace("”", '"')   # 中文引号→英文
    md = md.replace("‘", "'").replace("’", "'")
    md = md.replace("–", "-").replace("—", "-")   # 破折号
    md = re.sub(r"[ \t]+", " ", md)                          # 连续空白
    return md


def normalize_values(md: str) -> Tuple[str, list]:
    """
    数值标准化: 全角数字→半角, 千分位/百分号/小数统一。
    返回 normalized_values 列表(记录到 ParsedDoc 供 E 用)。
    """
    normalized = []
    # 全角数字 → 半角
    md_new = md.translate(str.maketrans("０１２３４５６７８９．％", "0123456789.%"))
    # 提取带单位的数值(时间/百分比/百万等)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(%|％|亿元|万元|百万|亿|年|月)", md_new):
        normalized.append({"value": float(m.group(1)), "unit": m.group(2)})
    return md_new, normalized


def cleanup_markers(md: str) -> str:
    """清理 MinerU 常见冗余标记: 图片占位、多余空行"""
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "[图片]", md)   # 图片→占位
    md = re.sub(r"\n{3,}", "\n\n", md)                    # 多余空行
    return md


# ============ 主入口 ============

def clean_mineru_markdown(md_text: str, doc_type: str = "paper") -> Tuple[str, list]:
    """
    对 MinerU 输出的 markdown 做清洗 + 注入章节标记。
    根据 doc_type 加载对应的章节标记映射。

    返回 (cleaned_md, normalized_values)
    """
    md = remove_header_footer(md_text)
    md = merge_paragraphs(md)
    md = normalize_special_chars(md)
    md, normalized = normalize_values(md)
    md = cleanup_markers(md)
    md = inject_section_markers(md, doc_type)
    return md, normalized


# ============ 命令行测试 ============
if __name__ == "__main__":
    import sys
    sample = """1

Journal of Financial Economics
2024

Abstract
This paper studies green credit.

假设
H1: 环境规制促进绿色创新。

结果
显著为正。
"""
    if len(sys.argv) > 1:
        sample = open(sys.argv[1], encoding="utf-8").read()
    dt = sys.argv[2] if len(sys.argv) > 2 else "paper"
    cleaned, normalized = clean_mineru_markdown(sample, dt)
    print("--- 清洗后 ---")
    print(cleaned)
    print(f"\n--- 归一化数值 {len(normalized)} 项 ---")
    print(normalized[:10])