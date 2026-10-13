from sqlalchemy import select, func
from .. import jobs
from ..llm.service import model_name
from ..db import now
from ..errors import AppError
from ..staleness import invalidate
from ..projects import service as projects
from ..candidates.models import Candidate, CandidateSet
from ..literature.service import serialize
from .semantics import public
from .models import StudyPlan, PlanDraft, CarbonPlanDraft, DecisionRules, Permutation


def schema_for(db, project, dataset_id=None):
    from ..binding.models import VariableBinding
    from ..datasets.models import Dataset
    from ..cases.carbon import DOI

    if project.case == "carbon":
        return CarbonPlanDraft
    bound = db.scalars(
        select(Dataset)
        .join(VariableBinding, VariableBinding.dataset_id == Dataset.id)
        .join(StudyPlan, StudyPlan.id == VariableBinding.plan_id)
        .where(StudyPlan.project_id == project.id)
    ).all()
    incoming = db.get(Dataset, dataset_id) if dataset_id else None
    if incoming is not None:
        bound.append(incoming)
    return CarbonPlanDraft if any(d.source.get("doi") == DOI for d in bound) else PlanDraft


def get(db, plan_id):
    entity = db.get(StudyPlan, plan_id)
    if not entity:
        raise AppError("plan_not_found", "研究方案不存在", 404)
    return entity


def list_(db, project_id):
    projects.get(db, project_id)
    return [
        public(db, p)
        for p in db.scalars(
            select(StudyPlan).where(StudyPlan.project_id == project_id).order_by(StudyPlan.version.desc())
        ).all()
    ]


def create(db, project_id, candidate_id, data, stale=False, llm_model=None):
    version = (db.scalar(select(func.max(StudyPlan.version)).where(StudyPlan.project_id == project_id)) or 0) + 1
    entity = StudyPlan(
        llm_model=llm_model, project_id=project_id, candidate_id=candidate_id, version=version, stale=stale, **data
    )
    db.add(entity)
    projects.get(db, project_id).updated_at = now()
    db.commit()
    return entity


def draft(app, project_id, llm):
    with app.state.sessions() as db:
        project = projects.get(db, project_id)
        candidate = db.get(Candidate, project.selected_candidate_id) if project.selected_candidate_id else None
        if not candidate:
            raise AppError("candidate_required", "请先选择一个研究候选")
        source_set = db.get(CandidateSet, candidate.set_id)
        if source_set.stale:
            raise AppError("candidate_stale", "所选候选已过期，请重新生成并选择")
        candidate_id = candidate.id
        snapshot = serialize(candidate)
        direction = project.direction
        case = project.case
        schema = schema_for(db, project)
        from ..datasets.context import payload as data_payload

        data_context = data_payload(db, project)

    async def work(progress):
        progress("正在起草变量、识别设定与决策规则")
        output = await llm.generate(
            "draft_plan",
            {
                **data_context,
                "case": case,
                "candidate": snapshot,
                "direction": direction,
                "supported_methods": ["policy_causal", "panel_association", "mechanism_boundary"],
            },
            schema,
            project_id,
        )
        data = output.model_dump()
        if case == "carbon":
            from ..cases.carbon import plan_defaults

            data = plan_defaults(data)
        # Only the human editor can assert real treatment assignment.
        data["treatment_is_real_assignment"] = False
        data["decision_rules"] = DecisionRules().model_dump()
        data["permutation"] = Permutation().model_dump()
        with app.state.sessions() as db:
            project = projects.get(db, project_id)
            current = db.get(Candidate, candidate_id)
            stale = (
                project.direction != direction
                or project.case != case
                or schema_for(db, project) is not schema
                or project.selected_candidate_id != candidate_id
                or serialize(current) != snapshot
                or db.get(CandidateSet, current.set_id).stale
            )
            entity = create(db, project_id, candidate_id, data, stale, model_name(llm))
            return {"plan_id": entity.id}

    return jobs.submit(app, "plan", project_id, work)


def edit(db, plan_id, payload):
    entity = get(db, plan_id)
    data = schema_for(db, projects.get(db, entity.project_id)).model_validate(payload.model_dump()).model_dump()
    invalidate(db, entity.project_id, "plan")
    if entity.status != "draft":
        return create(db, entity.project_id, entity.candidate_id, data, entity.stale, entity.llm_model)
    for key, value in data.items():
        setattr(entity, key, value)
    projects.get(db, entity.project_id).updated_at = now()
    db.commit()
    return entity


def new_version(db, plan_id):
    entity = get(db, plan_id)
    data = PlanDraft.model_validate(serialize(entity)).model_dump()
    invalidate(db, entity.project_id, "plan")
    return create(db, entity.project_id, entity.candidate_id, data, entity.stale, entity.llm_model)


def confirm(db, plan_id):
    entity = get(db, plan_id)
    if entity.stale:
        raise AppError("plan_stale", "方案已过期，请根据当前候选重新起草")
    if entity.status == "superseded":
        raise AppError("plan_superseded", "此方案已有新的确认版本，请新建版本后审阅")
    if entity.status == "confirmed":
        return entity
    schema_for(db, projects.get(db, entity.project_id)).model_validate(serialize(entity))
    for old in db.scalars(
        select(StudyPlan).where(StudyPlan.project_id == entity.project_id, StudyPlan.status == "confirmed")
    ).all():
        old.status = "superseded"
    entity.status = "confirmed"
    projects.get(db, entity.project_id).updated_at = now()
    db.commit()
    return entity
