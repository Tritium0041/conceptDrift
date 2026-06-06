from __future__ import annotations

import json
from pathlib import Path
from time import monotonic, sleep

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.database import INTERRUPTED_MESSAGE, create_db_engine, create_session_factory, init_database
from app.main import create_app
from app.models import Task
from app.providers import (
    GeneratedReport,
    GeneratedSource,
    OpenAIInspirationProvider,
    OpenAIProviderConfig,
)


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'conceptdrift-test.sqlite3'}",
        agent_provider="mock",
        cors_origins="http://localhost:3000",
    )
    return TestClient(create_app(settings))


def wait_for_task(client: TestClient, task_id: str) -> dict:
    deadline = monotonic() + 5
    last_payload: dict | None = None
    while monotonic() < deadline:
        response = client.get(f"/api/tasks/{task_id}")
        response.raise_for_status()
        last_payload = response.json()
        if last_payload["status"] in {"succeeded", "failed"}:
            return last_payload
        sleep(0.05)
    raise AssertionError(f"Task did not finish: {last_payload}")


def test_health(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "mock", "database": "sqlite"}


def test_config_api_updates_env_and_runtime_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NamedProvider:
        def __init__(self, name: str) -> None:
            self.name = name

        async def generate(self, request, progress):  # type: ignore[no-untyped-def]
            await progress(80, f"{self.name} provider")
            return GeneratedReport(
                title=f"{self.name}: {request.direction}",
                summary="runtime provider switched",
                markdown=f"# {self.name}",
                scores={
                    "technical_feasibility": 80,
                    "market_novelty": 70,
                    "business_potential": 60,
                },
                tags=[self.name],
                sources=[
                    GeneratedSource(
                        source="Config Test",
                        title="Runtime config",
                        url="https://example.com/config",
                        summary="Provider came from updated config.",
                        signal_score=75,
                    )
                ],
            )

    built_providers: list[str] = []

    def fake_build_provider(settings: Settings) -> NamedProvider:
        built_providers.append(settings.agent_provider)
        return NamedProvider(settings.agent_provider)

    monkeypatch.setattr("app.main.build_provider", fake_build_provider)
    env_path = tmp_path / ".env"
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'config.sqlite3'}",
        agent_provider="mock",
        openai_api_key="",
        config_env_path=str(env_path),
    )

    with TestClient(create_app(settings)) as client:
        config_response = client.get("/api/config")
        assert config_response.status_code == 200
        assert config_response.json()["openai_api_key_configured"] is False

        update_response = client.put(
            "/api/config",
            json={
                "agent_provider": "response",
                "openai_api_key": "sk-live-1234567890",
                "openai_base_url": "https://openai.test/v1",
                "openai_model": "gpt-test",
                "openai_timeout_seconds": 45,
                "openai_tracing_disabled": True,
                "codex_agent_timeout_seconds": 120,
                "codex_agent_network_enabled": True,
                "codex_agent_web_search_mode": "live",
            },
        )
        assert update_response.status_code == 200
        payload = update_response.json()
        assert payload["agent_provider"] == "response"
        assert payload["openai_api_key_configured"] is True
        assert payload["openai_api_key_masked"] == "sk-...7890"
        assert "sk-live" not in update_response.text

        health_response = client.get("/api/health")
        assert health_response.json()["provider"] == "response"

        task_id = client.post(
            "/api/tasks/generate",
            json={"direction": "config smoke", "sources": ["reddit"], "depth": "quick"},
        ).json()["id"]
        task_payload = wait_for_task(client, task_id)
        report = client.get(f"/api/tasks/{task_id}/result").json()

    assert task_payload["status"] == "succeeded"
    assert report["title"].startswith("response")
    assert built_providers == ["mock", "response"]
    env_text = env_path.read_text(encoding="utf-8")
    assert "CONCEPTDRIFT_AGENT_PROVIDER=response" in env_text
    assert "OPENAI_API_KEY=sk-live-1234567890" in env_text
    assert "OPENAI_MODEL=gpt-test" in env_text


def test_config_api_keeps_existing_secret_when_key_is_blank(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'config-keep.sqlite3'}",
        agent_provider="mock",
        openai_api_key="sk-existing-9999",
        config_env_path=str(env_path),
    )

    with TestClient(create_app(settings)) as client:
        response = client.put(
            "/api/config",
            json={
                "agent_provider": "mock",
                "openai_api_key": "",
                "openai_base_url": "https://api.openai.com/v1",
                "openai_model": "gpt-5",
                "openai_timeout_seconds": 90,
                "openai_tracing_disabled": True,
                "codex_agent_timeout_seconds": 120,
                "codex_agent_network_enabled": True,
                "codex_agent_web_search_mode": "live",
            },
        )

    assert response.status_code == 200
    assert response.json()["openai_api_key_masked"] == "sk-...9999"
    assert "OPENAI_API_KEY" not in env_path.read_text(encoding="utf-8")


def test_config_api_reports_codex_agent_settings_for_codex_provider(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'config-codex.sqlite3'}",
        agent_provider="codex",
        openai_api_key="sk-test",
        codex_agent_timeout_seconds=99,
        codex_agent_network_enabled=True,
        codex_agent_web_search_mode="live",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["agent_provider"] == "codex"
    assert response.json()["codex_agent_timeout_seconds"] == 99
    assert response.json()["codex_agent_network_enabled"] is True
    assert response.json()["codex_agent_web_search_mode"] == "live"


def test_generate_task_to_report(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        create_response = client.post(
            "/api/tasks/generate",
            json={
                "direction": "AI code review assistant",
                "sources": ["github_trending", "hackernews"],
                "depth": "standard",
            },
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["id"]

        task_payload = wait_for_task(client, task_id)
        assert task_payload["status"] == "succeeded"
        assert task_payload["progress"] == 100
        assert task_payload["report_id"] is not None

        result_response = client.get(f"/api/tasks/{task_id}/result")
        assert result_response.status_code == 200
        report = result_response.json()
        assert report["title"].startswith("AI code review assistant")
        assert "技术可行性" in report["markdown"]
        assert report["sources"][0]["source"] == "GitHub Trending"


def test_generate_task_to_report_with_openai_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []
    openai_payload = {
        "title": "AI Code Review Copilot",
        "summary": "A real OpenAI-backed report summary.",
        "markdown": "# AI Code Review Copilot\n\n## 技术可行性\n可落地。",
        "scores": {
            "technical_feasibility": 88,
            "market_novelty": 77,
            "business_potential": 81,
        },
        "tags": ["openai", "code-review"],
        "sources": [
            {
                "source": "GitHub Trending",
                "title": "Review automation signal",
                "url": "https://github.com/trending",
                "summary": "Developers are adopting automated review workflows.",
                "signal_score": 84,
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(openai_payload),
                            }
                        ],
                    }
                ]
            },
        )

    provider = OpenAIInspirationProvider(
        OpenAIProviderConfig(
            api_key="sk-test",
            base_url="https://openai.test/v1",
            model="gpt-test",
            timeout_seconds=30,
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr("app.main.build_provider", lambda settings: provider)

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'openai-provider.sqlite3'}",
        agent_provider="response",
        openai_api_key="sk-test",
        openai_base_url="https://openai.test/v1",
        openai_model="gpt-test",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/tasks/generate",
            json={
                "direction": "AI code review assistant",
                "sources": ["github_trending"],
                "depth": "standard",
            },
        )
        assert response.status_code == 201
        task_id = response.json()["id"]

        task_payload = wait_for_task(client, task_id)
        assert task_payload["status"] == "succeeded"

        report_response = client.get(f"/api/tasks/{task_id}/result")
        assert report_response.status_code == 200
        report = report_response.json()

    assert report["title"] == "AI Code Review Copilot"
    assert report["scores"]["technical_feasibility"] == 88
    assert report["sources"][0]["url"] == "https://github.com/trending"
    assert len(requests) == 1
    assert requests[0].url == "https://openai.test/v1/responses"
    assert requests[0].headers["authorization"] == "Bearer sk-test"
    sent_body = json.loads(requests[0].content)
    assert sent_body["model"] == "gpt-test"
    assert sent_body["text"]["format"]["type"] == "json_schema"
    assert sent_body["text"]["format"]["name"] == "conceptdrift_report"


def test_report_list_search_and_exports(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        task_id = client.post(
            "/api/tasks/generate",
            json={"direction": "CLI release checklist", "sources": ["product_hunt"], "depth": "quick"},
        ).json()["id"]
        report_id = wait_for_task(client, task_id)["report_id"]

        list_response = client.get("/api/reports", params={"q": "CLI"})
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1

        markdown_response = client.get(f"/api/reports/{report_id}/export?format=markdown")
        assert markdown_response.status_code == 200
        assert markdown_response.headers["content-type"].startswith("text/markdown")
        assert b"CLI release checklist" in markdown_response.content

        pdf_response = client.get(f"/api/reports/{report_id}/export?format=pdf")
        assert pdf_response.status_code == 200
        assert pdf_response.headers["content-type"] == "application/pdf"
        assert pdf_response.content.startswith(b"%PDF")


def test_not_ready_and_missing_task_responses(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        missing = client.get("/api/tasks/missing")
        assert missing.status_code == 404

        create_response = client.post(
            "/api/tasks/generate",
            json={"direction": "slow idea", "sources": ["reddit"], "depth": "deep"},
        )
        task_id = create_response.json()["id"]
        early_result = client.get(f"/api/tasks/{task_id}/result")
        assert early_result.status_code in {200, 202}


def test_task_events_stream_terminal_state(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        task_id = client.post(
            "/api/tasks/generate",
            json={"direction": "event stream", "sources": ["reddit"], "depth": "quick"},
        ).json()["id"]
        wait_for_task(client, task_id)

        with client.stream("GET", f"/api/tasks/{task_id}/events") as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

    assert "event: task" in body
    assert '"status":"succeeded"' in body
    assert "event: done" in body


def test_task_events_missing_task_response(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/tasks/missing/events")

    assert response.status_code == 404


def test_list_tasks_returns_persisted_tasks(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        first_id = client.post(
            "/api/tasks/generate",
            json={"direction": "first persistent task", "sources": ["reddit"], "depth": "quick"},
        ).json()["id"]
        second_id = client.post(
            "/api/tasks/generate",
            json={"direction": "second persistent task", "sources": ["hackernews"], "depth": "quick"},
        ).json()["id"]
        wait_for_task(client, first_id)
        wait_for_task(client, second_id)

        response = client.get("/api/tasks", params={"limit": 5})
        assert response.status_code == 200
        payload = response.json()

    assert payload["total"] == 2
    assert [item["id"] for item in payload["items"]] == [second_id, first_id]
    assert payload["items"][0]["direction"] == "second persistent task"


def test_list_tasks_filters_by_status(tmp_path: Path) -> None:
    db_path = tmp_path / "tasks-filter.sqlite3"
    database_url = f"sqlite:///{db_path}"
    engine = create_db_engine(database_url)
    init_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        session.add_all(
            [
                Task(
                    id="running-task",
                    direction="running",
                    sources=["github_trending"],
                    depth="standard",
                    status="failed",
                    progress=50,
                    stage="失败",
                ),
                Task(
                    id="done-task",
                    direction="done",
                    sources=["github_trending"],
                    depth="standard",
                    status="succeeded",
                    progress=100,
                    stage="完成",
                ),
            ]
        )
        session.commit()

    settings = Settings(database_url=database_url, agent_provider="mock", openai_api_key="")
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/tasks", params={"status": "succeeded"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == "done-task"


def test_startup_marks_interrupted_tasks_failed(tmp_path: Path) -> None:
    db_path = tmp_path / "restart.sqlite3"
    database_url = f"sqlite:///{db_path}"
    engine = create_db_engine(database_url)
    init_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        session.add(
            Task(
                id="interrupted",
                direction="unfinished",
                sources=["github_trending"],
                depth="standard",
                status="running",
                progress=42,
                stage="处理中",
            )
        )
        session.commit()

    settings = Settings(database_url=database_url, agent_provider="mock")
    with TestClient(create_app(settings)):
        pass

    with session_factory() as session:
        task = session.scalar(select(Task).where(Task.id == "interrupted"))
        assert task is not None
        assert task.status == "failed"
        assert task.error == INTERRUPTED_MESSAGE
