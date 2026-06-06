from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Task


INTERRUPTED_MESSAGE = "服务重启导致任务中断"


def _sqlite_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    raw_path = database_url.removeprefix("sqlite:///")
    if raw_path == ":memory:":
        return None
    return Path(raw_path)


def create_db_engine(database_url: str) -> Engine:
    path = _sqlite_path(database_url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _ensure_sqlite_task_columns(engine)


def _ensure_sqlite_task_columns(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(tasks)").fetchall()
        }
        if "mode" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE tasks ADD COLUMN mode VARCHAR(20) NOT NULL DEFAULT 'guided'"
            )
        if "checkpoint" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE tasks ADD COLUMN checkpoint JSON NOT NULL DEFAULT '{}'"
            )


def mark_interrupted_tasks(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        result = session.execute(
            update(Task)
            .where(Task.status.in_(["pending", "running"]))
            .values(status="failed", error=INTERRUPTED_MESSAGE, stage="任务已中断")
        )
        session.commit()
        return int(result.rowcount or 0)


def task_exists(session: Session, task_id: str) -> bool:
    return session.execute(select(Task.id).where(Task.id == task_id)).first() is not None


def get_db(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    with session_factory() as session:
        yield session
