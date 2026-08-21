# ============================================================================
# 实体别名归一 — src/kg/aliases.py
# ============================================================================
# 两步归一的前半部分：静态别名字典（简易、零成本、程序直接替换）。
#
# 说明：
#   - 当前只实现第 1 步：哈希查找 + 固定术语替换（如 "DID" -> "双重差分模型"）。
#   - 第 2 步（大批量数据后用向量相似度聚类合并）不放在本模块，而是在
#     pipeline 预留 on_alias 钩子 / 后期新增 cluster_aliases()。
#   - 归一适用对象：Concept、Method、Dataset 的 name（跨论文归一共用）。
#
# 词典分两层：
#   _GREEDY_EXACT : 全字符串精确匹配（不分大小写）
#   _SUBSTR       : 子串包含匹配（长术语缩写，如出现 "双重差分" 就算命中）
# ============================================================================

from __future__ import annotations

import re
from typing import Optional, Dict, Tuple

# ----------------------------------------------------------------------------
# 第 1 层：精确别名映射（英文缩写 -> 规范中文全称）
# ----------------------------------------------------------------------------
_EXACT_ALIASES: Dict[str, str] = {
    # ---- 计量模型 / 识别策略 ----
    "DID": "双重差分模型",
    "DD": "双重差分模型",
    "DIF-IN-DIF": "双重差分模型",
    "DIFFERENCE-IN-DIFFERENCES": "双重差分模型",
    "DDD": "三重差分模型",
    "DIDD": "三重差分模型",
    "IV": "工具变量法",
    "2SLS": "两阶段最小二乘",
    "TSLS": "两阶段最小二乘",
    "RDD": "断点回归",
    "RD": "断点回归",
    "PSTR": "面板平滑转换回归",
    "GMM": "广义矩估计",
    "SYS-GMM": "系统广义矩估计",
    "PSM": "倾向得分匹配",
    "PSM-DID": "倾向得分匹配双重差分",
    "OLS": "普通最小二乘",
    "2DID": "双重差分模型",
    "SYSDIFF": "系统广义矩估计",

    # ---- 数据集 / 数据库 ----
    "CNRDS": "中国研究数据服务平台CNRDS",
    "CSMAR": "国泰安数据库",
    "WIND": "万得数据库",
    "CFPS": "中国家庭追踪调查",
    "CGSS": "中国综合社会调查",
    "CHFS": "中国家庭金融调查",
    "CEIC": "CEIC数据库",
    "CNDRS": "中国研究数据服务平台CNRDS",
    "EPS": "EPS数据平台",

    # ---- 常用概念 ----
    "ESG": "ESG",
    "TFP": "全要素生产率",
    "GT": "绿色技术创新",
    "GZ": "绿色技术创新",
    "LPM": "下偏矩",                    # Lower Partial Moments
    "VAR": "风险价值",
    "CEO": "CEO",

    # ---- 政策试点常用 ----
    "DID-PSM": "倾向得分匹配双重差分",
}


# ----------------------------------------------------------------------------
# 第 2 层：子串别名（长术语缩写映射）
#   key 出现在实体名中即整体替换为目标规范名，避免
#   "双重差分"、"双重差分模型"、"DID模型" 等变体各自成节点。
# ----------------------------------------------------------------------------
_SUBSTR_ALIASES: Dict[str, str] = {
    "双重差分": "双重差分模型",
    "三重差分": "三重差分模型",
    "倾向得分匹配": "倾向得分匹配",
    "渐进双重差分": "双重差分模型",
    "工具变量": "工具变量法",
    "断点回归": "断点回归",
    "事件研究": "事件研究法",
}

# 命中后统一清理的多余空白
_WS = re.compile(r"\s+")


def normalize_alias(name: str) -> str:
    """
    对实体名做静态别名归一。返回规范名（可能与传入不同）。

    顺序：
      1. 去首尾空白、压缩内部空白
      2. 精确匹配表（不分大小写）
      3. 中子串表（任一命中则替换为该规范名）
      4. 兜底原样返回清理后的名字
    """
    if not name:
        return name
    cleaned = _WS.sub(" ", name).strip()

    # 精确匹配（英文缩写不区分大小写）
    upper = cleaned.upper()
    if upper in _EXACT_ALIASES:
        return _EXACT_ALIASES[upper]

    # 子串匹配（对 cleaned 与 upper 都试）
    for key, target in _SUBSTR_ALIASES.items():
        if key in cleaned or key in upper:
            return target

    return cleaned


def normalize_list(names) -> "list[str]":
    """批量归一，过滤空值，保留顺序与去重。"""
    out: list = []
    seen = set()
    for n in names or []:
        if not n:
            continue
        n = str(n).strip()
        if not n:
            continue
        n = normalize_alias(n)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def redirect_alias(name: str) -> Tuple[str, Optional[str]]:
    """
    归一 + 返回别名指向（用于 Concept/Method 节点上记录 alias_of）。

    返回 (规范名, 别名指向或 None)。
    若入参本身就是规范名，则 alias_of=None；否则 alias_of=入参原样。
    """
    canonical = normalize_alias(name)
    if canonical == _WS.sub(" ", name or "").strip():
        return canonical, None
    return canonical, (name or "").strip()


def build_alias_table() -> dict:
    """
    生成"规范名 -> 别名列表"的汇总表，供审计/导出使用。
    """
    table: dict = {}
    for alias, canonical in list(_EXACT_ALIASES.items()) + list(_SUBSTR_ALIASES.items()):
        table.setdefault(canonical, []).append(alias)
    return table


if __name__ == "__main__":
    # 冒烟测试
    samples = [
        "DID", "双重差分模型", "双重差分", "did", "CSMAR", "TFP 回归",
        "国泰安数据库", "CNRDS", "", "   ", "工具变量回归",
    ]
    for s in samples:
        print(f"{s!r:>16} -> {normalize_alias(s)!r}")
