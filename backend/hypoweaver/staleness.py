"""Mark downstream records without deleting historical results."""
from sqlalchemy import update
from .db import Base

TARGETS = {
    'direction': ['candidate_sets', 'study_plans', 'analysis_runs', 'proposals'],
    'candidate': ['study_plans', 'analysis_runs', 'proposals'],
    'plan': ['analysis_runs', 'proposals'],
    'data': ['analysis_runs', 'proposals'],
}


def invalidate(db, project_id, event):
    affected = []
    for name in TARGETS[event]:
        table = Base.metadata.tables.get(name)
        if table is not None:
            result = db.execute(update(table).where(table.c.project_id == project_id).values(stale=True))
            if result.rowcount:
                affected.append(name)
    return affected
