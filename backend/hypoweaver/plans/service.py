from sqlalchemy import select, func
from .. import jobs
from ..db import now
from ..errors import AppError
from ..staleness import invalidate
from ..projects import service as projects
from ..candidates.models import Candidate, CandidateSet
from ..literature.service import serialize
from .models import StudyPlan, PlanDraft, CarbonPlanDraft, DecisionRules, Permutation


def schema_for(project):
    text = (project.title + " " + str(project.direction)).lower()
    return CarbonPlanDraft if "碳" in text or "carbon" in text or "emissions trading" in text else PlanDraft


def get(db, plan_id):
    entity = db.get(StudyPlan, plan_id)
    if not entity:
        raise AppError('plan_not_found', '研究方案不存在', 404)
    return entity


def list_(db, project_id):
    projects.get(db, project_id)
    return [serialize(p) for p in db.scalars(select(StudyPlan).where(StudyPlan.project_id == project_id).order_by(StudyPlan.version.desc())).all()]


def create(db, project_id, candidate_id, data, stale=False):
    version = (db.scalar(select(func.max(StudyPlan.version)).where(StudyPlan.project_id == project_id)) or 0) + 1
    entity = StudyPlan(project_id=project_id, candidate_id=candidate_id, version=version, stale=stale, **data)
    db.add(entity)
    projects.get(db, project_id).updated_at = now()
    db.commit()
    return entity


def draft(app, project_id, llm):
    with app.state.sessions() as db:
        project = projects.get(db, project_id)
        candidate = db.get(Candidate, project.selected_candidate_id) if project.selected_candidate_id else None
        if not candidate:
            raise AppError('candidate_required', '请先选择一个研究候选')
        source_set = db.get(CandidateSet, candidate.set_id)
        if source_set.stale:
            raise AppError('candidate_stale', '所选候选已过期，请重新生成并选择')
        candidate_id = candidate.id
        snapshot = serialize(candidate)
        direction = project.direction
        schema = schema_for(project)

    async def work(progress):
        progress('正在起草变量、识别设定与决策规则')
        output = await llm.generate('draft_plan', {'candidate': snapshot, 'direction': direction, 'supported_methods': ['policy_causal', 'panel_association', 'mechanism_boundary']}, schema, project_id)
        data = output.model_dump()
        # Only the human editor can assert real treatment assignment.
        data['treatment_is_real_assignment'] = False
        data['decision_rules'] = DecisionRules().model_dump()
        data['permutation'] = Permutation().model_dump()
        with app.state.sessions() as db:
            project = projects.get(db, project_id)
            current = db.get(Candidate, candidate_id)
            stale = project.direction != direction or project.selected_candidate_id != candidate_id or serialize(current) != snapshot or db.get(CandidateSet, current.set_id).stale
            entity = create(db, project_id, candidate_id, data, stale)
            return {'plan_id': entity.id}
    return jobs.submit(app, 'plan', project_id, work)


def edit(db, plan_id, payload):
    entity = get(db, plan_id)
    data = schema_for(projects.get(db, entity.project_id)).model_validate(payload.model_dump()).model_dump()
    invalidate(db, entity.project_id, 'plan')
    if entity.status != 'draft':
        return create(db, entity.project_id, entity.candidate_id, data, entity.stale)
    for key, value in data.items():
        setattr(entity, key, value)
    projects.get(db, entity.project_id).updated_at = now()
    db.commit()
    return entity


def new_version(db, plan_id):
    entity = get(db, plan_id)
    data = PlanDraft.model_validate(serialize(entity)).model_dump()
    invalidate(db, entity.project_id, 'plan')
    return create(db, entity.project_id, entity.candidate_id, data, entity.stale)


def confirm(db, plan_id):
    entity = get(db, plan_id)
    if entity.stale:
        raise AppError('plan_stale', '方案已过期，请根据当前候选重新起草')
    if entity.status == 'superseded':
        raise AppError('plan_superseded', '此方案已有新的确认版本，请新建版本后审阅')
    if entity.status == 'confirmed':
        return entity
    schema_for(projects.get(db, entity.project_id)).model_validate(serialize(entity))
    for old in db.scalars(select(StudyPlan).where(StudyPlan.project_id == entity.project_id, StudyPlan.status == 'confirmed')).all():
        old.status = 'superseded'
    entity.status = 'confirmed'
    projects.get(db, entity.project_id).updated_at = now()
    db.commit()
    return entity
