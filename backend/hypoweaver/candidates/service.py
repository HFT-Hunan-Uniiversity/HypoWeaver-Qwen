from sqlalchemy import select, func, update
from .. import jobs
from ..llm.service import model_name
from ..db import uid, now
from ..errors import AppError
from ..projects import service as projects
from ..literature.service import evidence, serialize
from ..landscape.service import build_landscape
from .models import CandidateSet, Candidate, CandidateOutput, ReviewOutput


def invalidate(db, project_id):
    db.execute(update(CandidateSet).where(CandidateSet.project_id == project_id).values(stale=True))


def list_(db, project_id):
    projects.get(db, project_id)
    sets = db.scalars(
        select(CandidateSet).where(CandidateSet.project_id == project_id).order_by(CandidateSet.version.desc())
    ).all()
    return [
        {
            **serialize(s),
            "candidates": [serialize(c) for c in db.scalars(select(Candidate).where(Candidate.set_id == s.id)).all()],
        }
        for s in sets
    ]


def recover(sessions):
    with sessions() as db:
        db.execute(
            update(CandidateSet)
            .where(CandidateSet.status == "generating")
            .values(status="failed", error="服务重启中断生成，请重试")
        )
        db.commit()


def start(app, project_id, llm):
    with app.state.sessions() as db:
        project = projects.get(db, project_id)
        direction = project.direction
        all_cards = [serialize(c) for c in evidence(db, project_id) if c.included]
        if len(all_cards) < 2:
            raise AppError("evidence_required", "请先纳入至少两张证据卡")
        # Bound context by card count and excerpt length; never fabricate missing abstracts.
        cards = [
            {k: c[k] for k in ["id", "title", "year"]}
            | {"abstract": (c["abstract"] or c["fulltext_excerpt"] or "")[:1200]}
            for c in all_cards[:80]
        ]
        version = (
            db.scalar(select(func.max(CandidateSet.version)).where(CandidateSet.project_id == project_id)) or 0
        ) + 1
        entity = CandidateSet(
            llm_model=model_name(llm), project_id=project_id, version=version, evidence_ids=[c["id"] for c in cards]
        )
        db.add(entity)
        db.commit()
        set_id = entity.id
    valid = {c["id"] for c in cards}

    def clean(output):
        removed = 0
        candidates = []
        for draft in output.candidates:
            data = draft.model_dump()
            removed += sum(ref not in valid for ref in data["evidence_ids"])
            data["evidence_ids"] = list(dict.fromkeys(ref for ref in data["evidence_ids"] if ref in valid))
            candidates.append({"id": uid("cand"), **data})
        with app.state.sessions() as db:
            entity = db.get(CandidateSet, set_id)
            if entity:
                entity.removed_references += removed
                db.commit()
        if any(len(c["evidence_ids"]) < 2 for c in candidates):
            raise AppError(
                "insufficient_references", f"移除无效引用 {removed} 处后，有候选不足两条有效引用，请补充证据后重新生成"
            )
        return candidates

    async def work(progress):
        try:
            payload = {"direction": direction, "evidence": cards, "landscape": build_landscape(all_cards)}
            progress("正在基于已纳入文献生成候选")
            output = await llm.generate("generate_candidates", payload, CandidateOutput, project_id)
            candidates = clean(output)
            progress("正在自审候选的引用、增量与可行性")
            review = await llm.generate(
                "review_candidates", {"candidates": candidates, "evidence": cards}, ReviewOutput, project_id
            )
            if review.decision == "revise":
                progress("正在根据自审意见修订一次")
                output = await llm.generate(
                    "generate_candidates",
                    {**payload, "previous_candidates": candidates, "review": review.model_dump()},
                    CandidateOutput,
                    project_id,
                )
                candidates = clean(output)
            with app.state.sessions() as db:
                project = projects.get(db, project_id)
                entity = db.get(CandidateSet, set_id)
                for data in candidates:
                    db.add(Candidate(set_id=set_id, **data))
                entity.review = {**review.model_dump(), "revised": review.decision == "revise"}
                entity.recommendation_text = output.recommendation_text
                entity.status = "ready"
                project.updated_at = now()
                db.commit()
            return {"set_id": set_id}
        except BaseException as exc:
            with app.state.sessions() as db:
                entity = db.get(CandidateSet, set_id)
                if entity:
                    entity.status = "failed"
                    entity.error = exc.message if isinstance(exc, AppError) else "候选生成中断或输出无效，请重试"
                    db.commit()
            raise

    job_id = jobs.submit(app, "candidates", project_id, work)
    with app.state.sessions() as db:
        db.get(CandidateSet, set_id).job_id = job_id
        db.commit()
    return job_id


def get(db, candidate_id):
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise AppError("candidate_not_found", "候选不存在", 404)
    return candidate


def edit(db, candidate_id, payload):
    from ..staleness import invalidate as downstream

    candidate = get(db, candidate_id)
    candidate_set = db.get(CandidateSet, candidate.set_id)
    project_id = candidate_set.project_id
    valid = {c.id for c in evidence(db, project_id) if c.included}
    data = payload.model_dump()
    refs = list(dict.fromkeys(data["evidence_ids"]))
    if len(refs) < 2 or not set(refs) <= valid:
        raise AppError("invalid_references", "每个候选须引用至少两张当前已纳入文献，请检查引用")
    data["evidence_ids"] = refs
    for k, v in data.items():
        setattr(candidate, k, v)
    candidate.user_edited = True
    downstream(db, project_id, "candidate")
    projects.get(db, project_id).updated_at = now()
    db.commit()
    return serialize(candidate)


def select_(db, candidate_id):
    from ..staleness import invalidate as downstream

    candidate = get(db, candidate_id)
    candidate_set = db.get(CandidateSet, candidate.set_id)
    if candidate_set.stale:
        raise AppError("candidate_stale", "该候选版本已过期，请重新生成")
    project = projects.get(db, candidate_set.project_id)
    if project.selected_candidate_id != candidate.id:
        downstream(db, project.id, "candidate")
        project.selected_candidate_id = candidate.id
        project.updated_at = now()
        db.commit()
    return serialize(project)
