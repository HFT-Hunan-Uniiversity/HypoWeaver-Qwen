# ParsedDoc IR 精简版(Pydantic V2)
# 主体是 Markdown 文件(LlamaIndex 消费), ParsedDoc JSON 只做元数据容器

from pydantic import BaseModel, field_validator
from typing import List, Optional, Dict, Any


class ParsedDoc(BaseModel):
    """文档解析后的元数据容器"""
    doc_id: str
    doc_type: str            # paper / policy / esg_report / ...
    doc_type_cn: str
    title: str
    source_loc: str          # 原始 PDF 路径
    global_review_flag: str = "ok"  # ok / needs_human_review
    clean_log: List[Dict[str, Any]] = []
    extra_info: Dict[str, Any] = {}
    # 论文: 元数据抽取器(pymupdf+LLM)产出的 doi/authors/year/references
    # 政策: policy_no/issuer/effective_date
    # ESG: company/report_year
    markdown_path: str = ""  # cleaned/<doc_id>.md
    normalized_values: List[Dict[str, Any]] = []

    @field_validator('global_review_flag')
    @classmethod
    def check_flag(cls, v):
        assert v in ('ok', 'needs_human_review'), f"非法 flag: {v}"
        return v


# 类型映射
DOC_TYPE_MAP = {
    "paper": "论文",
    "policy": "政策",
    "esg_report": "ESG 报告",
}