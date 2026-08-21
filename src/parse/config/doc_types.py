# 文档类型配置注册表
# 所有支持的文档类型定义在这里，清洗/元数据/推断都从这读配置
# 加新类型只需在这里加一条记录，流水线代码不用改

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF 读第一页文本

# ============ 文档类型定义 ============

# 每种类型配置：
#   section_map:   章节标记映射（清洗层用）
#   meta_strategy: 元数据抽取策略 "regex+llm" | "llm_only"
#   keywords:      文件名关键词推断规则（命中一个即判为该类型）
#   description:   中文描述

DOC_TYPE_CONFIGS = {
    "paper": {
        "description": "论文",
        "meta_strategy": "regex+llm",
        "keywords": [
            "基于", "经验证据", "实证", "影响研究", "视角", "研究",
            "evidence", "journal", "review",
            "_",  # 中文论文常见 "标题_作者" 命名
        ],
        "section_map": {
            "摘要":   ["摘要", "abstract", "概要", "提 要"],
            "综述":   ["引言", "文献综述", "研究背景", "绪论", "introduction",
                       "literature review", "相关问题", "述评"],
            "理论假设": ["理论分析", "研究假设", "理论框架", "机制分析",
                       "理论基础", "假设", "hypothesis", "theoretical", "理论"],
            "实证":   ["实证分析", "实证检验", "研究设计", "数据来源",
                       "模型设定", "变量", "描述性统计", "回归", "结果分析",
                       "实证结果", "methodology", "empirical", "data", "研究样本"],
            "异质性": ["异质性", "稳健性", "内生性", "robustness",
                       "heterogeneity", "进一步分析"],
            "结论":   ["结论", "研究结论", "启示", "政策建议", "conclusion", "总结"],
        },
    },
    "esg_report": {
        "description": "ESG 报告",
        "meta_strategy": "llm_only",
        "keywords": [
            "esg_report", "sustainability_report",
            "环境、社会", "可持续", "管治报告",
            " esg ", " esg,", "_esg", "esg_", "-esg", "esg-", "_esg_",
        ],
        "section_map": {
            "摘要":   ["摘要", "概要", "关于本报告", "报告简介"],
            "公司概况": ["公司简介", "企业概况", "关于我们", "organization profile"],
            "环境":   ["环境", "气候变化", "碳排放", "绿色运营", "environmental"],
            "社会":   ["社会", "员工", "供应链", "社区", "social"],
            "治理":   ["治理", "公司治理", "董事会", "风险管理", "governance"],
            "绩效":   ["绩效", "指标", "数据", "目标", "performance", "esg 指标"],
            "附录":   ["附录", "索引", "编制说明", "附录"],
        },
    },
    "policy": {
        "description": "政策文件",
        "meta_strategy": "llm_only",
        "keywords": [
            "办法", "通知", "指引", "意见", "条例", "规划",
            "实施方案", "指导意见", "管理规范", "暂行规定",
        ],
        "section_map": {
            "总则":   ["总则", "指导思想", "总体要求", "基本原则"],
            "重点任务": ["重点任务", "主要任务", "工作任务", "实施内容"],
            "保障措施": ["保障措施", "政策保障", "组织保障", "机制保障"],
            "监督管理": ["监督管理", "监督", "考核", "评估", "检查"],
            "附则":   ["附则", "附则", "施行日期", "有效期"],
        },
    },
    "news": {
        "description": "新闻",
        "meta_strategy": "llm_only",
        "keywords": [
            "新闻", "日报", "快讯", "新华社", "报道",
            "news", "press", "release", "announcement",
        ],
        "section_map": {
            "导语":   ["导语", "核心事实", "本报讯"],
            "背景":   ["背景", "事件背景", "深度"],
            "各方回应": ["各方回应", "回应", "观点", "评论"],
            "影响分析": ["影响", "意义", "展望", "下一步"],
        },
    },
}


# ============ 辅助函数 ============

def get_supported_types() -> List[str]:
    """返回所有支持的文档类型列表"""
    return list(DOC_TYPE_CONFIGS.keys())


def get_section_map(doc_type: str) -> Dict[str, List[str]]:
    """获取指定类型的章节标记映射"""
    config = DOC_TYPE_CONFIGS.get(doc_type)
    if config:
        return config["section_map"]
    return {}


def get_meta_strategy(doc_type: str) -> str:
    """获取元数据抽取策略"""
    config = DOC_TYPE_CONFIGS.get(doc_type)
    if config:
        return config["meta_strategy"]
    return "llm_only"  # 未知类型默认 LLM 全量


def get_description(doc_type: str) -> str:
    """获取类型中文描述"""
    config = DOC_TYPE_CONFIGS.get(doc_type)
    if config:
        return config["description"]
    return doc_type


def get_type_keywords(doc_type: str) -> List[str]:
    """获取文件名关键词推断规则"""
    config = DOC_TYPE_CONFIGS.get(doc_type)
    if config:
        return config["keywords"]
    return []


# ============ 文档类型推断（含 LLM 兜底） ============

def infer_doc_type(filename: str, pdf_path: Optional[str] = None) -> Tuple[str, str]:
    """
    推断文档类型。
    第一层：文件名关键词匹配
    第二层：关键词匹配不出结果 → LLM 读第一页文本兜底
    第三层：LLM 也返回 unknown → 默认 paper

    返回 (doc_type, doc_type_cn)
    """
    name_lower = filename.lower()
    stem = Path(filename).stem

    # ===== 第一层：文件名关键词匹配 =====
    # 优先检查论文明确特征（"基于"、"经验证据"等），再检查其他类型
    # 用文件名中的中文特性判断：论文通常是"标题_作者"格式
    # 其他类型有明确的关键词标记

    # 1. 论文明确特征
    if any(h in stem for h in ("基于", "经验证据", "实证", "影响研究", "视角")):
        return "paper", "论文"

    # 2. 其他类型（政策/新闻/esg）
    for dt in ["policy", "news", "esg_report"]:
        keywords = get_type_keywords(dt)
        if any(k in name_lower for k in keywords):
            return dt, get_description(dt)

    # 3. 论文带作者尾缀（"标题_作者"）
    if "_" in filename:
        return "paper", "论文"

    # ===== 第二层：LLM 兜底（需要 PDF 文件路径读第一页） =====
    if pdf_path and Path(pdf_path).exists():
        try:
            # 延迟导入避免循环依赖
            from src.parse.config.llm_type_infer import infer_type_with_llm

            doc = fitz.open(pdf_path)
            first_page_text = doc[0].get_text()[:2000] if doc.page_count > 0 else ""
            doc.close()

            if first_page_text.strip():
                llm_result = infer_type_with_llm(first_page_text)
                if llm_result and llm_result["doc_type"] != "unknown":
                    dt = llm_result["doc_type"]
                    print(f"  🤖 LLM 推断类型: {dt} ({llm_result['confidence']})")
                    return dt, get_description(dt)
        except Exception as e:
            print(f"  ⚠️ LLM 类型推断失败: {e}")

    # ===== 第三层：默认兜底 =====
    return "paper", "论文"