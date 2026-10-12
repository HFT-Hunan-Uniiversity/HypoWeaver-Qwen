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
from .models import Proposal, Interpretation, SectionsDraft
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
    data["markdown"] = render_markdown(entity)
    return data


async def checked_call(llm, name, payload, schema, project_id, validate):
    for attempt in range(2):
        output = await llm.generate(name, payload, schema, project_id)
        problems = validate(output)
        if not problems:
            return output
        payload = {**payload, "previous": output.model_dump(), "rewrite_reasons": problems}
    return None


async def build_proposal(snapshot, llm, project_id, progress):
    run = snapshot["run"]
    result = run["result"] if run else None
    claims = snapshot["claims"]
    candidate = snapshot["candidate"]
    plan = snapshot["plan"]
    active = [c for c in claims if c["user_decision"] not in {"deferred", "rejected"}]
    strength = min((c["chosen_strength"] for c in active), key=STRENGTHS.index, default="insufficient")
    numbers = {}
    result_md = result_table(result, numbers)
    if run and run.get("reproduction"):
        numbers["reproduction.max_diff"] = run["reproduction"]["max_relative_diff"]
        result_md += "\n\n独立复算最大相对差：{{num:reproduction.max_diff}}。"
    if snapshot["dataset"]:
        numbers["dataset.rows"] = snapshot["dataset"]["n_rows"]
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
        "max_strength": strength,
        "data_plan": snapshot["readiness"].get("data_plan", []),
        "binding": snapshot["binding"],
        "dataset": snapshot["dataset"],
    }
    output = await checked_call(
        llm,
        "write_proposal_sections",
        payload,
        SectionsDraft,
        project_id,
        lambda o: (
            [problem for s in o.sections for problem in issues(s.markdown, numbers, strength)]
            + (
                []
                if {s.key for s in o.sections} == set(NARRATIVE) and len(o.sections) == len(NARRATIVE)
                else ["章节须完整且不重复"]
            )
        ),
    )
    generated = {s.key: s for s in output.sections} if output else {}
    defaults = {
        "overview": "本提案围绕所选研究问题组织文献依据、变量与可执行方案。",
        "question": "研究问题及预期贡献仍需结合文献与数据条件进一步核实。",
        "literature": "下列参考文献来自本项目已纳入证据，需回到原文核对具体论断。",
        "gap": "研究缺口是待核实的工作假设，需继续核对已有文献。",
        "hypothesis": "所列假设属于待检验命题，不是已有结论。",
        "design": "研究依照已审阅的变量角色与模型设定执行；识别假设仍需研究者核实。",
        "data": "数据来源、变量含义与可获得性需逐项核对。",
        "limitations": "应补充关键文献、数据含义核验和识别假设论证，并如实报告不支持的证据。",
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
        output = await checked_call(
            llm,
            "interpret_results",
            {"claims": active, "numbers": numbers},
            Interpretation,
            project_id,
            lambda o: (
                [
                    p
                    for item in o.paragraphs
                    for p in issues(
                        item.text,
                        numbers,
                        next((c["chosen_strength"] for c in active if c["claim_id"] == item.claim_id), "insufficient"),
                    )
                ]
                + (
                    []
                    if {p.claim_id for p in o.paragraphs} == {c["claim_id"] for c in active}
                    and len(o.paragraphs) == len(active)
                    else ["结论标识须完整且有效"]
                )
            ),
        )
        if output:
            interpretation = {p.claim_id: p.text for p in output.paragraphs}
    conclusions = []
    for c in claims:
        if c["user_decision"] in {"deferred", "rejected"}:
            conclusions.append(
                "研究者已" + ("暂缓" if c["user_decision"] == "deferred" else "拒绝") + "该条结论，不作为本提案结论。"
            )
        else:
            conclusions.append(
                ("研究者尚未确认。" if c["user_decision"] == "pending" else "")
                + "采用强度："
                + LABELS[c["chosen_strength"]]
                + "。"
                + (
                    c["final_text"]
                    if not issues(c["final_text"], numbers, c["chosen_strength"])
                    else conservative[c["chosen_strength"]]
                )
                + " "
                + interpretation.get(c["claim_id"], conservative[c["chosen_strength"]])
            )
    sections += [
        {"key": "results", "markdown": result_md, "injected_numbers_ref": numbers, "editable": False},
        {
            "key": "conclusions",
            "markdown": "\n\n".join(conclusions)
            if run
            else "计划型提案尚无实证结果，不作结果判断。\n\n待补数据计划：\n"
            + "\n".join("- " + s for s in snapshot["readiness"].get("data_plan", [])),
            "injected_numbers_ref": numbers,
            "editable": False,
        },
    ]
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
    if snapshot["dataset"]:
        source = snapshot["dataset"]["source"]
        references.append(
            "- 数据来源："
            + str(source.get("citation") or source.get("doi") or source.get("url") or "待补来源")
            + "；许可："
            + str(source.get("license") or "待确认")
            + "。仅作为数据来源引用。"
        )
    sections.append(
        {
            "key": "references",
            "markdown": "\n".join(references) or "尚无有效引用，请补充证据。",
            "injected_numbers_ref": {},
            "editable": False,
        }
    )
    from .rendering import TITLES

    sections.sort(key=lambda s: list(TITLES).index(s["key"]))
    interpretation_record = {
        "model": model_name(llm),
        "paragraphs": interpretation,
        "status": "generated" if interpretation else "not_generated",
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
                model=model_name(llm),
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
    problems = issues(payload.markdown, section["injected_numbers_ref"], section["max_strength"])
    if TOKEN.findall(payload.markdown) != TOKEN.findall(section["markdown"]):
        problems.append("不能增加、删除或更换数字占位符")
    if problems:
        raise AppError("invalid_narrative", "；".join(problems))
    entity.sections = [{**s, "markdown": payload.markdown} if s["key"] == key else s for s in entity.sections]
    db.commit()
    return public(entity)
