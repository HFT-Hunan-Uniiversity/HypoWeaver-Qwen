import re
from sqlalchemy import select, update
from ..errors import AppError
from ..literature.service import serialize
from ..db import Base
from .models import ClaimAssessment, STRENGTHS

LABELS = {
    "insufficient": "证据不足",
    "preliminary": "初步线索",
    "mixed": "混合证据",
    "associational": "关联",
    "causal_cautious": "谨慎因果",
}


def check_wording(text, max_strength, known_titles=()):
    if max_strength == "causal_cautious":
        return {"valid": True, "violations": []}
    for title in sorted(set(known_titles), key=len, reverse=True):
        if title:
            text = text.replace(title, " ")
    cleaned = re.sub(
        (
            "不能解释为因果|不代表因果关系|不构成因果证据|无法确认因果关系|不能据此推断因果|"
            "不能推断因果|不支持因果解释|并非因果证据|does not (?:establish|imply|demonstrate) "
            "causality|cannot (?:infer|establish) causality"
        ),
        "",
        text,
        flags=re.I,
    )
    # Negation is scoped to the current clause; double negation does not license a causal claim.
    cleaned = re.sub(
        r"(?:尚不能|不能|不足以|不支持|无法|不作|不据此|不宜|避免)"
        r"(?:(?!否认|排除|不|但|却|然而)[^，。；！？,;!?\n]){0,30}因果"
        r"(?:关系|解释|证据|效应)?",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?:待|具备|获得|补齐|满足)(?:(?!但|却|然而)[^，。；！？,;!?\n]){0,60}后再"
        r"(?:考虑|开展)(?:(?!但|却|然而)[^，。；！？,;!?\n]){0,30}因果(?:识别|研究|分析|设计)*",
        "",
        cleaned,
    )
    # Book-title brackets or an attribution cue identify titles, not quoted author claims.
    english_prose = re.sub(
        r"《[^》\n]*》|(?:标题(?:为|是)?|文献(?:为|是)?|论文(?:为|是)?|数据集(?:为|是)?|(?:发布|发表)的)"
        r'\s*[:：]?\s*(?:“[^”\n]*”|「[^」\n]*」|"[^"\n]*")',
        " ",
        cleaned,
    )
    pattern = (
        "\\b(?:caus(?:e[sd]?|ing|al(?:ity)?)|promot(?:e[sd]?|"
        "ing)|induc(?:e[sd]?|ing)|driv(?:e[sn]?|ing)|led to|leads? to|effect of)\\b"
    )
    violations = list(
        dict.fromkeys(
            re.findall("促进|导致|造成|驱动|引致|因果", cleaned) + re.findall(pattern, english_prose, flags=re.I)
        )
    )
    return {"valid": not violations, "violations": violations}


def assess(plan, result, reproduction):
    rules = plan["decision_rules"]
    main = (result or {}).get("main")
    blockers = []
    main_consistent = False
    if reproduction:
        rows = reproduction.get("rows")
        main_consistent = (
            reproduction.get("main_consistent", rows[0].get("status") == "consistent")
            if rows
            else reproduction.get("main_consistent", reproduction.get("consistent", False))
        )
    if not main or not main_consistent:
        verdict = "insufficient"
        blockers.append("主模型失败或独立复算未确认一致")
    else:
        direction = main["coef"] * rules["expected_sign"] > 0 and main["p"] < rules["alpha"]
        robustness = result.get("robustness", [])
        share = (
            sum(r.get("status") == "succeeded" and r.get("coef", 0) * rules["expected_sign"] > 0 for r in robustness)
            / len(robustness)
            if robustness
            else 0
        )
        if share < rules["robustness_share"]:
            blockers.append("指定稳健性同向比例未达门槛，失败检查计入分母")
        permutation = result.get("permutation")
        if not permutation or permutation["p"] >= rules["permutation_alpha"]:
            blockers.append("置换检验未通过或未完成")
        if plan["method_family"] == "policy_causal":
            pre = ((result.get("event") or {}).get("pretrend_wald") or {}).get("p")
            if pre is None or pre < rules["pretrend_alpha"]:
                blockers.append("前趋势检验未通过或不可估计")
        if not direction:
            blockers.append("主系数方向或显著性不支持预期")
        verdict = "not_supportive" if not direction else "mixed" if blockers else "supportive"
    strength = (
        "insufficient"
        if verdict in {"insufficient", "not_supportive"}
        else "preliminary"
        if verdict == "mixed"
        else "associational"
    )
    if (
        verdict == "supportive"
        and plan["method_family"] == "policy_causal"
        and plan["treatment_is_real_assignment"]
        and plan.get("treatment_semantics") == "real_assignment"
    ):
        strength = "causal_cautious"
    if plan.get("treatment_semantics") != "real_assignment":
        blockers.append("处理变量为同群/暴露变量，非真实分配")
    texts = {
        "insufficient": "现有证据不足以支持该结论。",
        "not_supportive": "本次检验未支持预期方向的结论。",
        "mixed": "本次结果提供初步线索，但诊断证据不一致。",
        "supportive": "在当前样本与模型设定下，两者存在符合预期方向的条件关联。",
    }
    output = []
    for claim in plan["claims_planned"]:
        matching = claim["type"] == "main" or plan["method_family"] == "mechanism_boundary"
        item_strength = strength if matching else "insufficient"
        text = texts[verdict] if matching else "本次运行未直接检验该机制或边界结论，证据不足。"
        if item_strength == "causal_cautious":
            text = "在已确认的真实处理分配及识别假设成立的条件下，结果支持谨慎的因果解释。"
        output.append(
            {
                "claim_id": claim["id"],
                "verdict": verdict if matching else "insufficient",
                "max_strength": item_strength,
                "allowed_wording": text,
                "blockers": list(blockers) if matching else ["本次运行没有直接检验该类结论"],
                "user_decision": "pending",
                "chosen_strength": item_strength,
                "final_text": text,
            }
        )
    return output


def list_(db, run_id):
    from ..stats.service import get

    get(db, run_id)
    return [serialize(x) for x in db.scalars(select(ClaimAssessment).where(ClaimAssessment.run_id == run_id)).all()]


def decide(db, run_id, claim_id, decision):
    claim = db.get(ClaimAssessment, (run_id, claim_id))
    if not claim:
        raise AppError("claim_not_found", "结论评估不存在", 404)
    rank = STRENGTHS.index(decision.chosen_strength)
    upper = STRENGTHS.index(claim.max_strength)
    if rank > upper or (decision.user_decision == "downgraded" and rank >= upper):
        raise AppError("strength_exceeded", "不能升级结论；降级必须选择更低强度")
    if not check_wording(decision.final_text, decision.chosen_strength)["valid"]:
        raise AppError("wording_invalid", "叙述含超出结论强度的措辞，请修改")
    for key, value in decision.model_dump().items():
        setattr(claim, key, value)
    table = Base.metadata.tables.get("proposals")
    if table is not None:
        from ..stats.service import get

        db.execute(update(table).where(table.c.project_id == get(db, run_id).project_id).values(stale=True))
    db.commit()
    return serialize(claim)
