from sqlalchemy import select
from .. import jobs
from ..db import now
from ..errors import AppError
from ..projects import service as projects
from .models import EvidenceCard, LiteratureSearch
from .sources import merge_cards, doi_normalize, title_key


def serialize(entity):
    return {c.name: getattr(entity, c.name) for c in entity.__table__.columns}


def evidence(db, project_id):
    projects.get(db, project_id)
    return db.scalars(select(EvidenceCard).where(EvidenceCard.project_id == project_id).order_by(EvidenceCard.year.desc())).all()


def searches(db, project_id):
    projects.get(db, project_id)
    return db.scalars(select(LiteratureSearch).where(LiteratureSearch.project_id == project_id).order_by(LiteratureSearch.created_at.desc())).all()


def save_cards(db, project_id, cards, search_id=None):
    from ..candidates.service import invalidate
    existing = evidence(db, project_id)
    before = [serialize(c) for c in existing if c.included]
    by_doi = {doi_normalize(card.doi): card for card in existing if card.doi}
    by_title = {title_key(card.title, card.year): card for card in existing}
    for values in merge_cards(cards):
        doi = values.get("doi")
        title = title_key(values["title"], values.get("year"))
        card = by_doi.get(doi) if doi else by_title.get(title)
        if card is None and title in by_title and not by_title[title].doi:
            card = by_title[title]
        if card:
            enriched = merge_cards([serialize(card), values])[0]
            for key in ["sources", "doi", "abstract", "concepts", "authors", "venue", "cited_by", "fulltext_excerpt"]:
                if key in enriched:
                    setattr(card, key, enriched[key])
        else:
            card = EvidenceCard(project_id=project_id, search_id=search_id, **values)
            db.add(card)
        if doi:
            by_doi[doi] = card
        by_title[title] = card
    db.flush()
    after = [serialize(c) for c in evidence(db, project_id) if c.included]
    if before != after:
        invalidate(db, project_id)
    projects.get(db, project_id).updated_at = now()
    db.commit()


def start_search(app, project_id, queries):
    with app.state.sessions() as db:
        projects.get(db, project_id)
        search = LiteratureSearch(project_id=project_id, queries=queries)
        db.add(search)
        db.commit()
        search_id = search.id

    async def work(progress):
        progress("正在联合检索 OpenAlex 与 Crossref")
        try:
            cards, statuses = await app.state.literature_client.search_all(queries)
            failed = not cards and all(s["status"] == "failed" for s in statuses.values())
            with app.state.sessions() as db:
                save_cards(db, project_id, cards, search_id)
                search = db.get(LiteratureSearch, search_id)
                search.per_source_status = statuses
                search.hit_count = len(cards)
                search.status = "failed" if failed else "completed"
                db.commit()
            if failed:
                raise AppError("search_failed", "所有文献来源均检索失败，请查看检索记录中的原因")
            return {"search_id": search_id, "hit_count": len(cards)}
        except BaseException:
            with app.state.sessions() as db:
                search = db.get(LiteratureSearch, search_id)
                if search and search.status == "running":
                    search.status = "failed"
                    search.per_source_status = {"system": {"status": "failed", "hits": 0, "reason": "检索中断，请重新发起"}}
                    db.commit()
            raise

    job_id = jobs.submit(app, "literature", project_id, work)
    with app.state.sessions() as db:
        db.get(LiteratureSearch, search_id).job_id = job_id
        db.commit()
    return job_id


def patch(db, card_id, payload):
    card = db.get(EvidenceCard, card_id)
    if not card:
        raise AppError("evidence_not_found", "证据卡不存在", 404)
    from ..candidates.service import invalidate
    if any(getattr(card, k) != v for k, v in payload.model_dump(exclude_none=True).items()):
        invalidate(db, card.project_id)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(card, key, value)
    projects.get(db, card.project_id).updated_at = now()
    db.commit()
    return card


def recover(sessions):
    with sessions() as db:
        searches = db.scalars(select(LiteratureSearch).where(LiteratureSearch.status == "running")).all()
        for search in searches:
            search.status = "failed"
            search.per_source_status = {"system": {"status": "failed", "hits": 0, "reason": "服务重启中断检索，请重新发起"}}
        db.commit()


async def add_pdf(app, project_id, file):
    import asyncio
    from ..db import uid
    from .documents import MAX_PDF_BYTES, extract_pdf, enrich_pdf
    with app.state.sessions() as db:
        projects.get(db, project_id)
    data = await file.read(MAX_PDF_BYTES + 1)
    card = await asyncio.to_thread(extract_pdf, data, file.filename or "document.pdf")
    card, note = await enrich_pdf(card, app.state.settings)
    destination = app.state.settings.storage_dir() / "uploads" / project_id
    destination.mkdir(parents=True, exist_ok=True)
    (destination / (uid("pdf") + ".pdf")).write_bytes(data)
    with app.state.sessions() as db:
        save_cards(db, project_id, [card])
    return {"message": note}
