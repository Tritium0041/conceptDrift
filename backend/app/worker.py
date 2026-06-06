from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.models import Report, SourceItem, Task
from app.providers import InspirationProvider
from app.schemas import GenerateTaskRequest


class TaskQueue:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        provider: InspirationProvider,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        with suppress(asyncio.CancelledError):
            await self._worker

    async def enqueue(self, task_id: str) -> None:
        await self._queue.put(task_id)

    def update_provider(self, provider: InspirationProvider) -> None:
        self._provider = provider

    async def join(self) -> None:
        await self._queue.join()

    async def _run(self) -> None:
        while True:
            task_id = await self._queue.get()
            try:
                await self.process(task_id)
            finally:
                self._queue.task_done()

    async def process(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(Task, task_id)
            if task is None or task.status == "failed":
                return
            request = GenerateTaskRequest(
                direction=task.direction,
                sources=task.sources,
                depth=task.depth,
                mode=task.mode,
                checkpoint=task.checkpoint or {},
            )
            task.status = "running"
            task.progress = max(task.progress, 5)
            task.stage = "任务续跑开始" if task.checkpoint else "任务开始"
            session.commit()

        async def progress(value: int, stage: str) -> None:
            with self._session_factory() as session:
                task = session.get(Task, task_id)
                if task is None:
                    return
                task.progress = max(task.progress, value)
                task.stage = stage
                session.commit()

        async def save_checkpoint(patch: dict[str, Any]) -> None:
            with self._session_factory() as session:
                task = session.get(Task, task_id)
                if task is None:
                    return
                task.checkpoint = _deep_merge(task.checkpoint or {}, patch)
                session.commit()

        progress.save_checkpoint = save_checkpoint  # type: ignore[attr-defined]

        try:
            generated = await self._provider.generate(request, progress)
            with self._session_factory() as session:
                report = Report(
                    title=generated.title,
                    summary=generated.summary,
                    markdown=generated.markdown,
                    scores=generated.scores,
                    tags=generated.tags,
                    archived=False,
                )
                report.sources = [
                    SourceItem(
                        source=item.source,
                        title=item.title,
                        url=item.url,
                        summary=item.summary,
                        signal_score=item.signal_score,
                    )
                    for item in generated.sources
                ]
                session.add(report)
                session.flush()

                task = session.get(Task, task_id)
                if task is not None:
                    task.status = "succeeded"
                    task.progress = 100
                    task.stage = "报告已生成"
                    task.report_id = report.id
                    task.error = None
                    task.checkpoint = {}
                session.commit()
        except Exception as exc:
            with self._session_factory() as session:
                task = session.get(Task, task_id)
                if task is not None:
                    task.status = "failed"
                    task.stage = "任务失败，可续跑"
                    task.error = str(exc)
                    session.commit()


def create_task(session: Session, request: GenerateTaskRequest) -> Task:
    direction = request.direction.strip()
    if request.mode == "yolo":
        direction = direction or "YOLO 自动探索"

    task = Task(
        id=str(uuid4()),
        direction=direction or "随机开发者工具灵感",
        sources=request.sources,
        depth=request.depth,
        mode=request.mode,
        checkpoint={},
        status="pending",
        progress=0,
        stage="等待执行",
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def _deep_merge(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
