from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings, masked_secret, merged_settings, persist_settings
from app.database import create_db_engine, create_session_factory, init_database, mark_interrupted_tasks
from app.exporting import markdown_bytes, pdf_bytes
from app.models import Report, Task
from app.providers import build_provider
from app.schemas import (
    AppConfigOut,
    AppConfigUpdate,
    GenerateTaskRequest,
    HealthOut,
    ReportListOut,
    ReportOut,
    TaskListOut,
    TaskOut,
)
from app.worker import TaskQueue, create_task


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    settings_holder = {"settings": active_settings}
    engine = create_db_engine(active_settings.database_url)
    session_factory = create_session_factory(engine)
    provider = build_provider(active_settings)
    queue = TaskQueue(session_factory, provider)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_database(engine)
        mark_interrupted_tasks(session_factory)
        queue.start()
        app.state.session_factory = session_factory
        app.state.task_queue = queue
        app.state.settings = active_settings
        yield
        await queue.stop()

    app = FastAPI(title="ConceptDrift API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def db_dependency() -> Session:
        with session_factory() as session:
            yield session

    @app.get("/api/health", response_model=HealthOut)
    def health() -> HealthOut:
        current_settings = settings_holder["settings"]
        return HealthOut(
            status="ok",
            provider=current_settings.agent_provider,
            database="sqlite" if current_settings.database_url.startswith("sqlite") else "other",
        )

    @app.get("/api/config", response_model=AppConfigOut)
    def get_config() -> AppConfigOut:
        return _config_out(settings_holder["settings"])

    @app.put("/api/config", response_model=AppConfigOut)
    def update_config(payload: AppConfigUpdate) -> AppConfigOut:
        current_settings = settings_holder["settings"]
        updates = payload.model_dump(exclude={"openai_api_key", "clear_openai_api_key"})
        submitted_key = payload.openai_api_key.strip() if payload.openai_api_key else ""
        if payload.clear_openai_api_key:
            updates["openai_api_key"] = ""
        elif submitted_key:
            updates["openai_api_key"] = submitted_key

        try:
            next_settings = merged_settings(current_settings, updates)
            next_provider = build_provider(next_settings)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        persist_settings(next_settings, updates)
        settings_holder["settings"] = next_settings
        app.state.settings = next_settings
        queue.update_provider(next_provider)
        return _config_out(next_settings)

    @app.post("/api/tasks/generate", response_model=TaskOut, status_code=201)
    async def generate_task(
        payload: GenerateTaskRequest,
        session: Session = Depends(db_dependency),
    ) -> Task:
        task = create_task(session, payload)
        await queue.enqueue(task.id)
        return task

    @app.post("/api/tasks/{task_id}/resume", response_model=TaskOut)
    async def resume_task(
        task_id: str,
        session: Session = Depends(db_dependency),
    ) -> Task:
        task = session.get(Task, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.status == "succeeded":
            raise HTTPException(status_code=409, detail="Task already succeeded")
        if task.status in {"pending", "running"}:
            return task

        task.status = "pending"
        task.stage = "等待续跑"
        task.error = None
        task.progress = max(task.progress, 5)
        session.commit()
        session.refresh(task)
        await queue.enqueue(task.id)
        return task

    @app.get("/api/tasks", response_model=TaskListOut)
    def list_tasks(
        status: str | None = Query(default=None, max_length=40),
        limit: int = Query(default=10, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        session: Session = Depends(db_dependency),
    ) -> TaskListOut:
        list_stmt = select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)
        total_stmt = select(func.count()).select_from(Task)
        if status:
            statuses = [item.strip() for item in status.split(",") if item.strip()]
            if statuses:
                list_stmt = list_stmt.where(Task.status.in_(statuses))
                total_stmt = total_stmt.where(Task.status.in_(statuses))

        total = session.scalar(total_stmt) or 0
        items = list(session.scalars(list_stmt))
        return TaskListOut(items=items, total=total, limit=limit, offset=offset)

    @app.get("/api/tasks/{task_id}", response_model=TaskOut)
    def get_task(task_id: str, session: Session = Depends(db_dependency)) -> Task:
        task = session.get(Task, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @app.get("/api/tasks/{task_id}/events")
    async def stream_task_events(
        task_id: str,
        session: Session = Depends(db_dependency),
    ) -> StreamingResponse:
        if session.get(Task, task_id) is None:
            raise HTTPException(status_code=404, detail="Task not found")

        async def event_stream() -> AsyncIterator[str]:
            last_payload: str | None = None
            while True:
                with session_factory() as event_session:
                    task = event_session.get(Task, task_id)
                    if task is None:
                        yield 'event: error\ndata: {"detail":"Task not found"}\n\n'
                        return
                    payload = TaskOut.model_validate(task).model_dump_json()
                    terminal = task.status in {"succeeded", "failed"}

                if payload != last_payload:
                    yield f"event: task\ndata: {payload}\n\n"
                    last_payload = payload

                if terminal:
                    yield "event: done\ndata: {}\n\n"
                    return
                await asyncio.sleep(0.4)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/tasks/{task_id}/result", response_model=ReportOut)
    def get_task_result(task_id: str, session: Session = Depends(db_dependency)) -> Report:
        task = session.get(Task, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.status == "failed":
            raise HTTPException(status_code=409, detail=task.error or "Task failed")
        if task.report is None:
            raise HTTPException(status_code=202, detail="Report is not ready")
        return task.report

    @app.get("/api/reports", response_model=ReportListOut)
    def list_reports(
        q: str | None = Query(default=None, max_length=100),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        session: Session = Depends(db_dependency),
    ) -> ReportListOut:
        filters = []
        if q:
            pattern = f"%{q}%"
            filters.append(or_(Report.title.ilike(pattern), Report.summary.ilike(pattern)))

        total_stmt = select(func.count()).select_from(Report)
        list_stmt = select(Report).order_by(Report.created_at.desc()).limit(limit).offset(offset)
        if filters:
            total_stmt = total_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        total = session.scalar(total_stmt) or 0
        items = list(session.scalars(list_stmt))
        return ReportListOut(items=items, total=total, limit=limit, offset=offset)

    @app.get("/api/reports/{report_id}", response_model=ReportOut)
    def get_report(report_id: int, session: Session = Depends(db_dependency)) -> Report:
        report = session.get(Report, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return report

    @app.get("/api/reports/{report_id}/export")
    def export_report(
        report_id: int,
        format: str = Query(default="markdown", pattern="^(markdown|pdf)$"),
        session: Session = Depends(db_dependency),
    ) -> Response:
        report = session.get(Report, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")

        if format == "pdf":
            body = pdf_bytes(report)
            media_type = "application/pdf"
            suffix = "pdf"
        else:
            body = markdown_bytes(report)
            media_type = "text/markdown; charset=utf-8"
            suffix = "md"

        safe_name = f"conceptdrift-report-{report.id}.{suffix}"
        return Response(
            content=body,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
        )

    return app


app = create_app()


def _config_out(settings: Settings) -> AppConfigOut:
    return AppConfigOut(
        agent_provider=settings.agent_provider,
        openai_api_key_configured=bool(settings.openai_api_key),
        openai_api_key_masked=masked_secret(settings.openai_api_key),
        openai_base_url=settings.openai_base_url,
        openai_model=settings.openai_model,
        openai_timeout_seconds=settings.openai_timeout_seconds,
        openai_tracing_disabled=settings.openai_tracing_disabled,
        codex_agent_timeout_seconds=settings.codex_agent_timeout_seconds,
        codex_agent_network_enabled=settings.codex_agent_network_enabled,
        codex_agent_web_search_mode=settings.codex_agent_web_search_mode,
    )
