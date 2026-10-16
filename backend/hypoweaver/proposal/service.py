from sqlalchemy import select, func
from .. import jobs
from ..llm.service import model_name
from ..errors import AppError
from ..projects import service as projects
from ..literature.service import evidence, serialize
from ..candidates.models import Candidate, CandidateSet
from ..plans.models import StudyPlan
from ..stats.models import AnalysisRun
from ..datasets.models import Dataset
from ..binding.models import VariableBinding
from ..binding.service import readiness
from ..claims.service import list_ as claims_list, LABELS
from ..claims.models import STRENGTHS
from .models import Proposal
from .metadata import source_year, validation_metadata
from .rendering import NARRATIVE, TOKEN, issues, result_table, render_markdown


def context(db, project_id):
    project = projects.get(db, project_id)
    candidate = db.get(Candidate, project.selected_candidate_id) if project.selected_candidate_id else None
    if not candidate:
        raise AppError("candidate_required", "请先选择研究候选，再生成提案")
    candidate_set = db.get(CandidateSet, candidate.set_id)
    plan = db.scalar(
        select(StudyPlan)
        .where(StudyPlan.project_id == project_id, StudyPlan.candidate_id == candidate.id)
        .order_by(StudyPlan.version.desc())
    )
    if not plan:
        raise AppError("plan_required", "请先起草研究方案")
    if candidate_set.stale or plan.stale:
        raise AppError("upstream_stale", "候选或方案已过期，请先更新后生成提案")
    run = db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.plan_id == plan.id, AnalysisRun.status == "succeeded", AnalysisRun.stale == False)
        .order_by(AnalysisRun.created_at.desc())
    )
    binding = db.get(VariableBinding, plan.id)
    dataset = db.get(Dataset, binding.dataset_id) if binding else None
    cards = [serialize(c) for c in evidence(db, project_id) if c.included]
    claims = claims_list(db, run.id) if run else []
    return {
        "project": serialize(project),
        "candidate": serialize(candidate),
        "plan": serialize(plan),
        "run": serialize(run) if run else None,
        "binding": serialize(binding) if binding else None,
        "dataset": ({k: v for k, v in serialize(dataset).items() if k != "file_path"} if dataset else None),
        "claims": claims,
        "evidence": cards,
        "readiness": readiness(db, plan.id)
        if plan.status == "confirmed"
        else {"data_plan": ["方案尚未确认，请审阅变量、识别假设与数据需求"]},
    }


def get(db, identifier):
    entity = db.get(Proposal, identifier)
    if not entity:
        raise AppError("proposal_not_found", "提案不存在", 404)
    return entity


def list_(db, project_id):
    projects.get(db, project_id)
    return [
        public(p)
        for p in db.scalars(
            select(Proposal).where(Proposal.project_id == project_id).order_by(Proposal.version.desc()).limit(30)
        ).all()
    ]


def public(entity):
    data = serialize(entity)
    from .narrative import failure_summary

    failures = failure_summary(entity.narrative_errors)
    data["narrative_failures"] = failures
    data["narrative_errors"] = failures  # Compatibility alias for one release.
    if isinstance(data.get("interpretation"), dict):
        data["interpretation"] = {
            **data["interpretation"],
            "narrative_failures": failures,
            "narrative_errors": failures,
        }
    data["markdown"] = render_markdown(entity)
    return data


async def build_proposal(snapshot, llm, project_id, progress):
    run = snapshot["run"]
    result = run["result"] if run else None
    claims = snapshot["claims"]
    candidate = snapshot["candidate"]
    plan = snapshot["plan"]
    active = [c for c in claims if c["user_decision"] not in {"deferred", "rejected"}]
    strength = min((c["chosen_strength"] for c in active), key=STRENGTHS.index, default="insufficient")
    numbers = {}
    metadata = validation_metadata(snapshot)
    result_md = result_table(result, numbers)
    if run and run.get("reproduction"):
        numbers["reproduction.max_diff"] = run["reproduction"]["max_relative_diff"]
        result_md += "\n\n独立复算最大相对差：{{num:reproduction.max_diff}}。"
    if snapshot["dataset"]:
        numbers["dataset.rows"] = snapshot["dataset"]["n_rows"]
        year = source_year(snapshot["dataset"].get("source") or {})
        if year is not None:
            numbers["dataset.source_year"] = year
        import math

        panel = snapshot["dataset"].get("panel", {})
        for key, source in [("year_min", "time_min"), ("year_max", "time_max"), ("n_units", "n_units")]:
            try:
                value = float(panel[source])
                if math.isfinite(value):
                    numbers["dataset." + key] = int(value) if value.is_integer() else value
            except (KeyError, TypeError, ValueError):
                pass
    valid = {c["id"]: c for c in snapshot["evidence"]}
    removed = 0
    sections = []
    progress("正在撰写研究提案叙述")
    payload = {
        "candidate": candidate,
        "plan": plan,
        "evidence": [
            {"id": c["id"], "title": c["title"], "abstract": (c["abstract"] or "")[:800]}
            for c in snapshot["evidence"][:80]
        ],
        "section_keys": NARRATIVE,
        "kind": "empirical" if run else "plan_only",
        "numbers": numbers,
        "metadata": metadata,
        "max_strength": strength,
        "data_plan": snapshot["readiness"].get("data_plan", []),
        "binding": snapshot["binding"],
        "dataset": snapshot["dataset"],
    }
    from .narrative import generate_sections

    generated, narrative_errors = await generate_sections(llm, payload, project_id)
    defaults = {
        "problem": "待研究问题与研究假设仍需结合已纳入文献与数据条件进一步核实；所列假设属于待检验命题，不是已有结论。",
        "rationale": "研究思路依据已审阅方案组织：先界定变量与识别策略，再以可复算的统计检验评估假设。",
        "techniques": "需要文献检索与证据整理、面板数据处理、固定效应回归与稳健性检验等技术手段，具体实现以方案为准。",
        "datasets": "Source（历史数据）与 Target（拟采集验证数据）的来源、变量含义与可获得性需逐项核对。",
        "title": "标题待研究者根据研究问题确定。",
        "abstract": "摘要待补：应概括研究背景、方法与预期或主要结果。",
        "methods": "研究依照已审阅的变量角色与模型设定执行；识别假设仍需研究者核实。",
        "experiments": "实验设计依照已审阅方案的主模型与稳健性检验执行，基线与评估指标需研究者核实。",
    }
    refs = set(ref for ref in candidate["evidence_ids"] if ref in valid)
    for key in NARRATIVE:
        draft = generated.get(key)
        text = draft.markdown if draft else defaults[key]
        if draft:
            removed += sum(ref not in valid for ref in draft.evidence_ids)
            refs.update(ref for ref in draft.evidence_ids if ref in valid)
        sections.append(
            {"key": key, "markdown": text, "injected_numbers_ref": numbers, "editable": True, "max_strength": strength}
        )
    progress("正在核对结果解读与数字占位符")
    interpretation = {}
    conservative = {
        "insufficient": "现有证据不足以支持结论。",
        "preliminary": "结果仅提供初步线索，仍需进一步检验。",
        "mixed": "不同检验证据混合，尚不能形成稳定结论。",
        "associational": "在当前样本和设定下，两者存在条件关联。",
        "causal_cautious": "仅在识别假设成立时支持谨慎的因果解释。",
    }
    if active and run:
        from .narrative import generate_interpretations

        interpretation, interpretation_errors = await generate_interpretations(
            llm, active, numbers, project_id, metadata
        )
        narrative_errors.extend(interpretation_errors)
    conclusions = []
    for c in claims:
        if c["user_decision"] in {"deferred", "rejected"}:
            conclusions.append(
                "研究者已" + ("暂缓" if c["user_decision"] == "deferred" else "拒绝") + "该条结论，不作为本提案结论。"
            )
        else:
            final_text = (
                c["final_text"]
                if not issues(c["final_text"], numbers, c["chosen_strength"], metadata)
                else conservative[c["chosen_strength"]]
            )
            paragraph = interpretation.get(c["claim_id"], conservative[c["chosen_strength"]])
            conclusion = paragraph if final_text.strip() in paragraph else final_text + " " + paragraph
            conclusions.append(
                ("研究者尚未确认。" if c["user_decision"] == "pending" else "")
                + "采用强度："
                + LABELS[c["chosen_strength"]]
                + "。"
                + conclusion
            )
    data_plan = snapshot["readiness"].get("data_plan", [])
    if run:
        results_md = result_md + "\n\n### 结论强度与边界\n\n" + "\n\n".join(conclusions or ["尚无可报告的结论。"])
    else:
        results_md = "计划型提案尚无实证结果，不作结果判断。" + (
            "\n\n待补数据计划：\n" + "\n".join("- " + s for s in data_plan) if data_plan else ""
        )
    limitations = [
        "结论强度上限为「" + LABELS[strength] + "」，不得据此作超出该强度的解读。",
        "需补充关键文献、核验数据字段含义与识别假设，并如实报告不支持或失败的检验。",
    ]
    if run and data_plan:
        limitations.append("后续数据计划：" + "；".join(data_plan))
    results_md += "\n\n### 局限与后续计划\n\n" + "\n".join("- " + x for x in limitations)
    sections.append({"key": "results", "markdown": results_md, "injected_numbers_ref": numbers, "editable": False})
    for section in sections:
        section["source_ref"] = run["id"] if run else plan["id"]
    references = []
    for ref in sorted(refs):
        c = valid[ref]
        authors = "、".join(c["authors"]) if c["authors"] and isinstance(c["authors"][0], str) else ""
        references.append(
            f"- {authors}（{c['year'] or '年份未详'}）。{c['title']}。{c['venue'] or ''}"
            + (f" [DOI](https://doi.org/{c['doi']})" if c["doi"] else "")
        )
    data_sources = []
    if snapshot["dataset"]:
        source = snapshot["dataset"]["source"]
        data_sources.append(
            "- 数据来源："
            + str(source.get("citation") or source.get("doi") or source.get("url") or "待补来源")
            + "；许可："
            + str(source.get("license") or "待确认")
            + "。仅作为数据来源引用。"
        )
    sections.append(
        {
            "key": "references",
            "markdown": "\n".join(references or ["尚无有效引用，请补充证据。"])
            + ("\n\n### 数据来源\n\n" + "\n".join(data_sources) if data_sources else ""),
            "injected_numbers_ref": {},
            "editable": False,
        }
    )
    from .rendering import TITLES

    sections.sort(key=lambda s: list(TITLES).index(s["key"]))
    interpretation_record = {
        "llm_model": model_name(llm),
        "paragraphs": interpretation,
        "status": "generated" if interpretation else "not_generated",
        "narrative_status": "partial" if narrative_errors else "complete",
        "narrative_errors": narrative_errors,
    }
    return sections, removed, interpretation_record


def start(app, project_id, llm):
    with app.state.sessions() as db:
        snapshot = context(db, project_id)

    async def work(progress):
        sections, removed, interpretation = await build_proposal(snapshot, llm, project_id, progress)
        with app.state.sessions() as db:
            try:
                stale = context(db, project_id) != snapshot
            except AppError:
                stale = True
            version = (db.scalar(select(func.max(Proposal.version)).where(Proposal.project_id == project_id)) or 0) + 1
            entity = Proposal(
                llm_model=model_name(llm),
                narrative_status=interpretation["narrative_status"],
                narrative_errors=interpretation["narrative_errors"],
                interpretation=interpretation,
                project_id=project_id,
                version=version,
                kind="empirical" if snapshot["run"] else "plan_only",
                sections=sections,
                snapshot=snapshot,
                removed_references=removed,
                stale=stale,
            )
            db.add(entity)
            db.commit()
            return {"proposal_id": entity.id}

    return jobs.submit(app, "proposal", project_id, work)


def edit(db, identifier, key, payload):
    entity = get(db, identifier)
    section = next((s for s in entity.sections if s["key"] == key), None)
    if not section or not section["editable"]:
        raise AppError("section_locked", "此节包含系统结果或引用，只能重新生成，不能直接修改")
    problems = issues(
        payload.markdown, section["injected_numbers_ref"], section["max_strength"], validation_metadata(entity.snapshot)
    )
    if TOKEN.findall(payload.markdown) != TOKEN.findall(section["markdown"]):
        problems.append("不能增加、删除或更换数字占位符")
    if problems:
        raise AppError("invalid_narrative", "；".join(problems))
    entity.sections = [{**s, "markdown": payload.markdown} if s["key"] == key else s for s in entity.sections]
    db.commit()
    return public(entity)
