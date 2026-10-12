from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from fastapi import Request


class Base(DeclarativeBase):
    pass


def uid(prefix):
    return f"{prefix}_{uuid4().hex}"


def now():
    return datetime.now(timezone.utc).isoformat()


def create_database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")

    return engine, sessionmaker(engine, expire_on_commit=False)


def session(request: Request):
    with request.app.state.sessions() as db:
        yield db
