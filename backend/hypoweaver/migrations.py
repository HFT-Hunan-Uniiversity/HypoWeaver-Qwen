from sqlalchemy import inspect, text


ADDITIONS = {
    "candidate_sets": {"model": "TEXT"},
    "study_plans": {"llm_model": "TEXT"},
    "proposals": {"model": "TEXT", "interpretation": "JSON"},
}


def migrate(engine):
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table, additions in ADDITIONS.items():
            present = {column["name"] for column in inspector.get_columns(table)}
            for column, sql_type in additions.items():
                if column not in present:
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'))
