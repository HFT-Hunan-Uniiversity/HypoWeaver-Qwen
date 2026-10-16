import re
from ..claims.service import check_wording
from .metadata import without_metadata

TITLES = {
    "problem": "一、待研究问题",
    "rationale": "二、解决思路",
    "techniques": "三、必要的技术手段",
    "datasets": "四、数据集",
    "title": "五、标题",
    "abstract": "六、摘要",
    "methods": "七、方法论",
    "experiments": "八、实验设计",
    "results": "九、实验结果",
    "references": "十、参考论文",
}
# 旧版提案（十项改造前）的节名，仅用于展示/导出历史版本，不再生成。
LEGACY_TITLES = {
    "overview": "一页概览",
    "question": "研究问题与贡献",
    "literature": "文献依据",
    "gap": "研究缺口",
    "hypothesis": "假设与机制",
    "design": "识别设计",
    "data": "数据与变量",
    "conclusions": "结论与边界",
    "limitations": "局限和后续计划",
}
SYSTEM_SECTIONS = {"results", "references"}
NARRATIVE = [k for k in TITLES if k not in SYSTEM_SECTIONS]
# Method-description sections may name identification strategies (含「因果」等术语);
# conclusion-strength wording is enforced on problem/abstract/title/rationale/datasets/results.
METHOD_DESCRIPTION_SECTIONS = frozenset({"techniques", "experiments", "methods"})


def section_title(key):
    return TITLES.get(key) or LEGACY_TITLES.get(key) or key


TOKEN = re.compile(r"\{\{num:([a-zA-Z0-9_.]+)\}\}")


def number(value):
    if value is None:
        return "未估计"
    if isinstance(value, int):
        return str(value)
    return format(value, ".6g")


def numerical_prose(text):
    """Exclude code spans, balanced log calls and arithmetic expressions from number checks."""
    text = re.sub(r"```[\s\S]*?```|`[^`\n]*`", "", text)
    spans = []
    for match in re.finditer(r"(?<![A-Za-z0-9_])log(?:1p)?\s*\(", text):
        depth = 1
        for end in range(match.end(), len(text)):
            depth += (text[end] == "(") - (text[end] == ")")
            if depth == 0:
                spans.append((match.start(), end + 1))
                break
    for start, end in reversed(spans):
        text = text[:start] + " " * (end - start) + text[end:]
    identifier = r"[A-Za-z_][A-Za-z0-9_]*"
    term = rf"(?:{identifier}|\d+(?:\.\d+)?)"
    arithmetic = rf"(?<![A-Za-z0-9_]){term}(?:\s*[+*/-]\s*{term})+"
    text = re.sub(arithmetic, lambda m: "" if re.search(r"[A-Za-z_]", m[0]) else m[0], text)
    # Keep English number words as prose; digit/underscore-bearing identifiers are fields.
    return re.sub(
        rf"(?<![A-Za-z0-9_]){identifier}", lambda m: "" if re.search(r"[0-9_]", m[0]) or m[0] == "log" else m[0], text
    )


def issues(text, numbers, strength, metadata=None, section=None):
    bad = []
    if any(k not in numbers for k in TOKEN.findall(text)):
        bad.append("存在未知数字占位符")
    stripped = TOKEN.sub("", text)
    quantitative = numerical_prose(without_metadata(stripped, metadata) if metadata else stripped)
    for phrase in [
        "零膨胀",
        "零值",
        "二元",
        "两类",
        "两者",
        "单一",
        "首次",
        "进一步",
        "一方面",
        "另一方面",
        "另一个",
        "另一项",
        "另一",
        "其一",
        "之一",
        "一致",
        "一般",
        "统一",
        "不一定",
        "一定程度",
        "一并",
        "逐一",
        "一旦",
        "唯一",
        "同一",
        # 「数」后接「分」会被误当成量词表达（系数分别、计数分布）。
        "分别",
        "分布",
        "分析",
        "分组",
        "分样本",
    ]:
        quantitative = quantitative.replace(phrase, "")
    chinese_number = (
        r"[零〇一二两三四五六七八九十百千万亿半壹贰叁肆伍陆柒捌玖拾佰仟数几]+"
        r"(?:点[零〇一二两三四五六七八九]+)?\s*"
        r"(?:家|名|个|条|行|次|期|年|月|日|天|倍|成|项|类|组|种|份|篇|例|人|元|岁|分|秒|小时|数|%|％)"
        r"|翻倍|成倍"
    )
    english_number = (
        r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
        r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|"
        r"seventy|eighty|ninety|hundred|thousand|million|billion|half|quarter|third|double|triple)\b"
    )
    if (
        re.search(r"\d", quantitative)
        or re.search(chinese_number, quantitative)
        or re.search(english_number, quantitative, re.I)
    ):
        bad.append("所有数字须使用给定占位符")
    # techniques/experiments/methods describe methods, not study conclusions.
    if section not in METHOD_DESCRIPTION_SECTIONS:
        if not check_wording(stripped, strength, (metadata or {}).get("titles", []))["valid"]:
            bad.append("存在超出结论上限的措辞")
    return bad


def inject(text, numbers):
    return TOKEN.sub(lambda m: number(numbers[m.group(1)]), text)


def render_markdown(proposal):
    parts = [
        "# " + proposal.snapshot["project"]["title"],
        "计划型提案（尚无实证结果）" if proposal.kind == "plan_only" else "含探索性结果的研究提案",
    ]
    if getattr(proposal, "narrative_status", None) == "partial":
        parts.append("> 部分叙述未通过校验，已保留合格章节，其余使用默认说明；请查看失败原因。")
    if proposal.stale:
        parts.append("> 上游信息已变更，本提案已过期。")
    for section in proposal.sections:
        parts += ["## " + section_title(section["key"]), inject(section["markdown"], section["injected_numbers_ref"])]
    return "\n\n".join(parts) + "\n"


def result_table(result, numbers):
    if not result:
        return "尚无实证结果。需补齐变量、确认绑定并完成统计检验。"
    header = "| 检验 | 系数 | 标准误 | p 值 | 观测数 |\n|---|---:|---:|---:|---:|"
    rows = []
    for i, r in enumerate([result["main"], *result["robustness"]]):
        if r.get("status", "succeeded") != "succeeded":
            rows.append(f"| {r['change']} | 失败 | — | — | — |")
            continue
        prefix = "main" if i == 0 else f"robust{i}"
        for k in ["coef", "se", "p", "n_obs"]:
            numbers[prefix + "." + k] = r[k]
        label = "主模型" if i == 0 else r["change"]
        rows.append(
            "| "
            + label
            + " | "
            + " | ".join("{{num:" + prefix + "." + k + "}}" for k in ["coef", "se", "p", "n_obs"])
            + " |"
        )
    diagnostic = []
    if result.get("event"):
        numbers["event.pretrend_p"] = result["event"]["pretrend_wald"]["p"]
        diagnostic.append("前趋势联合检验 p={{num:event.pretrend_p}}。")
    if result.get("permutation"):
        numbers["permutation.p"] = result["permutation"]["p"]
        numbers["permutation.n"] = result["permutation"]["n"]
        numbers["permutation.observed"] = result["permutation"]["observed"]
        diagnostic.append(
            "置换检验：无控制变量模型，观测系数 {{num:permutation.observed}}；"
            "置换 {{num:permutation.n}} 次，双侧 p={{num:permutation.p}}。"
        )
    return header + "\n" + "\n".join(rows) + "\n\n" + " ".join(diagnostic)
