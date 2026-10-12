import asyncio
from sqlalchemy import select
from .. import jobs
from ..db import now
from ..errors import AppError
from ..plans import service as plans
from ..datasets import service as datasets
from ..binding import service as binding_service
from ..binding.models import VariableBinding
from ..literature.service import serialize
from ..projects import service as projects
from .models import AnalysisSpec, AnalysisRun
from .engine import run_analysis
from .reproduction import reproduce
from ..claims.service import assess
from ..claims.models import ClaimAssessment

STEPS = ["main", "event_study", "robustness", "permutation", "reproduction", "assessment"]
LABELS = {
    "main": "主模型",
    "event_study": "事件研究",
    "robustness": "稳健性",
    "permutation": "置换检验",
    "reproduction": "独立复算",
    "assessment": "结论评估",
}


def compile_spec(plan, binding):
    mappings = binding.bindings

    def value(v):
        item = mappings.get(v["name"], {})
        expression = item.get("field") or item.get("formula")
        if not expression:
            raise AppError("binding_missing", "变量未绑定：" + v["name"])
        return expression

    role = {v["role"]: value(v) for v in plan.variables if v["role"] != "control"}
    return AnalysisSpec(
        method_family=plan.method_family,
        unit=role["unit"],
        time=role["time"],
        outcome=role["outcome"],
        treatment=role["treatment"],
        controls=[value(v) for v in plan.variables if v["role"] == "control"],
        fe=plan.model["fixed_effects"],
        cluster=plan.model["cluster"],
        event={"bins": plan.model["bins"]},
        robustness=plan.robustness,
        permutation=plan.permutation,
        mechanism=role.get("mechanism"),
        moderator=role.get("moderator"),
    )


def get(db, run_id):
    run = db.get(AnalysisRun, run_id)
    if not run:
        raise AppError("run_not_found", "检验运行不存在", 404)
    return run


def list_(db, project_id=None, plan_id=None):
    query = select(AnalysisRun)
    if project_id:
        projects.get(db, project_id)
        query = query.where(AnalysisRun.project_id == project_id)
    if plan_id:
        plans.get(db, plan_id)
        query = query.where(AnalysisRun.plan_id == plan_id)
    return [serialize(r) for r in db.scalars(query.order_by(AnalysisRun.created_at.desc()).limit(30)).all()]


def recover(sessions):
    with sessions() as db:
        for run in db.scalars(select(AnalysisRun).where(AnalysisRun.status.in_(["queued", "running"]))).all():
            run.status, run.error, run.finished_at = "failed", "服务重启中断统计，请重新发起", now()
            run.steps = {
                k: {"status": "failed", "error": "服务重启中断"} if v["status"] in {"queued", "running"} else v
                for k, v in run.steps.items()
            }
        db.commit()


def start(app, plan_id):
    with app.state.sessions() as db:
        plan = plans.get(db, plan_id)
        ready = binding_service.readiness(db, plan_id)
        if ready["status"] != "ready":
            raise AppError("not_ready", "尚未就绪：" + "；".join(ready["data_plan"]))
        binding = db.get(VariableBinding, plan_id)
        spec = compile_spec(plan, binding)
        project_id, dataset_id = plan.project_id, binding.dataset_id
        binding_snapshot, plan_snapshot = serialize(binding), plans.public(db, plan)
        run = AnalysisRun(
            project_id=project_id,
            plan_id=plan_id,
            dataset_id=dataset_id,
            spec=spec.model_dump(),
            plan_snapshot=plan_snapshot,
            binding_snapshot=binding_snapshot,
            steps={k: {"status": "queued", "error": None} for k in STEPS},
        )
        db.add(run)
        db.commit()
        run_id = run.id

    def step(name, status, error=None):
        with app.state.sessions() as db:
            run = get(db, run_id)
            run.steps = {**run.steps, name: {"status": status, "error": error}}
            db.commit()

    def calculate(progress):
        with app.state.sessions() as db:
            frame = datasets.frame(db, dataset_id)
        result = run_analysis(spec, frame, on_step=step, progress=progress)
        step("reproduction", "running")
        progress("正在使用独立实现复算主模型与稳健性")
        reproduction = reproduce(spec, frame, result)
        step(
            "reproduction",
            "succeeded" if reproduction["consistent"] else "failed",
            None if reproduction["consistent"] else "复算未全部一致，请查看对照",
        )
        step("assessment", "running")
        claims = assess(plan_snapshot, result, reproduction)
        step("assessment", "succeeded")
        return result, reproduction, claims

    async def work(progress):
        with app.state.sessions() as db:
            get(db, run_id).status = "running"
            db.commit()
        try:
            progress("正在执行主模型与诊断")
            result, reproduction, claims = await asyncio.to_thread(calculate, progress)
            with app.state.sessions() as db:
                run = get(db, run_id)
                run.result, run.status, run.finished_at = result, "succeeded", now()
                current_plan = plans.get(db, plan_id)
                current_binding = db.get(VariableBinding, plan_id)
                run.stale = (
                    run.stale
                    or current_plan.stale
                    or current_plan.status != "confirmed"
                    or serialize(current_binding) != binding_snapshot
                )
                run.reproduction = reproduction
                for claim in claims:
                    db.add(ClaimAssessment(run_id=run_id, **claim))
                db.commit()
            return {"run_id": run_id}
        except BaseException as exc:
            with app.state.sessions() as db:
                run = get(db, run_id)
                run.status, run.finished_at = "failed", now()
                run.error = exc.message if isinstance(exc, AppError) else "统计执行中断或失败，请查看输入与步骤状态"
                run.steps = {
                    k: {"status": "failed", "error": run.error} if v["status"] in {"running", "queued"} else v
                    for k, v in run.steps.items()
                }
                for claim in assess(plan_snapshot, None, None):
                    db.merge(ClaimAssessment(run_id=run_id, **claim))
                db.commit()
            raise

    job_id = jobs.submit(app, "analysis", project_id, work)
    with app.state.sessions() as db:
        get(db, run_id).job_id = job_id
        db.commit()
    return job_id
