from sqlalchemy import inspect, text


ADDITIONS = {
    "projects": {"case": "TEXT"},
    "variable_bindings": {"inherited_from": "TEXT"},
    "candidate_sets": {"llm_model": "TEXT"},
    "study_plans": {"llm_model": "TEXT", "suggested_binding": "JSON"},
    "proposals": {
        "llm_model": "TEXT",
        "interpretation": "JSON",
        "narrative_status": "TEXT",
        "narrative_errors": "JSON",
    },
}


def migrate(engine):
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table, additions in ADDITIONS.items():
            present = {column["name"] for column in inspector.get_columns(table)}
            for column, sql_type in additions.items():
                if column not in present:
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'))
            if table in {"candidate_sets", "proposals"} and "model" in present:
                connection.execute(
                    text(f'UPDATE "{table}" SET llm_model = model WHERE llm_model IS NULL AND model IS NOT NULL')
                )
        connection.execute(
            text(
                "UPDATE proposals SET interpretation = json_remove("
                "CASE WHEN json_type(interpretation, '$.llm_model') IS NULL "
                "THEN json_set(interpretation, '$.llm_model', json_extract(interpretation, '$.model')) "
                "ELSE interpretation END, '$.model') "
                "WHERE json_type(interpretation) = 'object' AND json_type(interpretation, '$.model') IS NOT NULL"
            )
        )
