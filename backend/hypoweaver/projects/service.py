from sqlalchemy import select
from ..db import now
from ..errors import AppError
from .models import Project

STAGES = [
    ("direction", "研究方向"),
    ("literature", "文献调研"),
    ("candidates", "缺口与候选"),
    ("plan", "研究方案"),
    ("data", "数据与检验"),
    ("proposal", "研究提案"),
]


def get(db, project_id):
    project = db.get(Project, project_id)
    if not project:
        raise AppError("project_not_found", "项目不存在", 404)
    return project


def list_(db):
    return db.scalars(select(Project).order_by(Project.updated_at.desc())).all()


def create(db, payload):
    project = Project(case=payload.case, title=payload.title.strip(), direction=payload.direction.model_dump())
    db.add(project)
    db.commit()
    return project


def update(db, project_id, payload):
    project = get(db, project_id)
    affected = []
    case_changed = "case" in payload.model_fields_set and payload.case != project.case
    if case_changed or (payload.direction is not None and payload.direction.model_dump() != project.direction):
        from ..staleness import invalidate

        affected = invalidate(db, project_id, "direction")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(project, key, value)
    if "case" in payload.model_fields_set:
        project.case = payload.case
    project.updated_at = now()
    db.commit()
    return project, affected


def delete(db, project_id):
    db.delete(get(db, project_id))
    db.commit()


def stage_status(db, project):
    from ..literature.models import EvidenceCard, LiteratureSearch
    from ..candidates.models import CandidateSet, Candidate
    from ..plans.models import StudyPlan
    from ..stats.models import AnalysisRun
    from ..proposal.models import Proposal
    from ..binding.models import VariableBinding
    from ..jobs import Job
    from sqlalchemy import func

    pid = project.id
    count = db.scalar(
        select(func.count())
        .select_from(EvidenceCard)
        .where(EvidenceCard.project_id == pid, EvidenceCard.included == True)
    )
    searches = db.scalar(
        select(LiteratureSearch).where(LiteratureSearch.project_id == pid).order_by(LiteratureSearch.created_at.desc())
    )
    candidates = db.scalar(
        select(CandidateSet).where(CandidateSet.project_id == pid).order_by(CandidateSet.version.desc())
    )
    selected = db.get(Candidate, project.selected_candidate_id) if project.selected_candidate_id else None
    selected_set = db.get(CandidateSet, selected.set_id) if selected else None
    plan = db.scalar(select(StudyPlan).where(StudyPlan.project_id == pid).order_by(StudyPlan.version.desc()))
    run = db.scalar(select(AnalysisRun).where(AnalysisRun.project_id == pid).order_by(AnalysisRun.created_at.desc()))
    proposal = db.scalar(select(Proposal).where(Proposal.project_id == pid).order_by(Proposal.version.desc()))
    binding = db.get(VariableBinding, plan.id) if plan else None
    active_jobs = db.scalars(select(Job).where(Job.project_id == pid, Job.status.in_(["queued", "running"]))).all()
    kinds = {j.kind for j in active_jobs}
    states = {
        "direction": (
            "completed" if project.direction.get("text", "").strip() else "not_started",
            "研究方向已填写" if project.direction.get("text", "").strip() else "先明确问题与约束",
        ),
        "literature": (
            "running"
            if searches and searches.status == "running"
            else "completed"
            if count
            else "failed"
            if searches and searches.status == "failed"
            else "not_started",
            f"已纳入 {count} 张证据卡",
        ),
        "candidates": (
            "stale"
            if (selected_set and selected_set.stale) or (candidates and candidates.stale)
            else "running"
            if candidates and candidates.status == "generating"
            else ("completed" if selected else "awaiting_selection")
            if candidates and candidates.status == "ready"
            else "failed"
            if candidates
            else "not_started",
            "已选择候选" if selected else "比较候选并选择研究切入点",
        ),
        "plan": (
            "stale"
            if plan and plan.stale
            else "running"
            if "plan" in kinds
            else "completed"
            if plan and plan.status == "confirmed"
            else "draft"
            if plan
            else "not_started",
            f"第 {plan.version} 版方案" if plan else "起草并审阅可执行研究方案",
        ),
        "data": (
            "stale"
            if run and run.stale
            else "running"
            if "analysis" in kinds or "dataset" in kinds
            else "failed"
            if run and (run.status == "failed" or any(s["status"] == "failed" for s in run.steps.values()))
            else "completed"
            if run and run.status == "succeeded"
            else "ready"
            if binding and binding.confirmed
            else "not_started",
            f"有效 {run.result['main']['n_obs']} 条观测"
            if run and run.result
            else "已确认变量绑定"
            if binding and binding.confirmed
            else "导入、绑定数据，再执行检验",
        ),
        "proposal": (
            "running"
            if "proposal" in kinds
            else "stale"
            if proposal and proposal.stale
            else "completed"
            if proposal
            else "not_started",
            f"第 {proposal.version} 版" + ("计划型提案" if proposal.kind == "plan_only" else "含探索性结果提案")
            if proposal
            else "支持计划型或含结果提案",
        ),
    }
    return [{"key": key, "label": label, "status": states[key][0], "summary": states[key][1]} for key, label in STAGES]
