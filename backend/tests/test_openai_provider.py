from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.providers import (
    OpenAIAgentsProvider,
    OpenAIInspirationProvider,
    OpenAIProviderConfig,
    OpenAIResponsesProvider,
    build_provider,
)
from app.schemas import GenerateTaskRequest


async def _progress(_value: int, _stage: str) -> None:
    return None


def _config(**overrides: object) -> OpenAIProviderConfig:
    values = {
        "api_key": "sk-test",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-test",
        "timeout_seconds": 30.0,
    }
    values.update(overrides)
    return OpenAIProviderConfig(**values)


@pytest.mark.asyncio
async def test_openai_provider_requires_api_key() -> None:
    provider = OpenAIInspirationProvider(_config(api_key=""))

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await provider.generate(
            GenerateTaskRequest(direction="test", sources=["github_trending"], depth="quick"),
            _progress,
        )


@pytest.mark.asyncio
async def test_openai_provider_extracts_output_text_and_clamps_scores() -> None:
    response_payload = {
        "title": "Terminal UX Watcher",
        "summary": "A useful summary.",
        "markdown": "# Terminal UX Watcher\n\n## MVP 建议\nShip it.",
        "scores": {
            "technical_feasibility": 105,
            "market_novelty": -4,
            "business_potential": 72,
        },
        "tags": ["cli", "cli", "developer-tool"],
        "sources": [
            {
                "source": "Hacker News",
                "title": "CLI workflow discussion",
                "url": "https://news.ycombinator.com",
                "summary": "Developers want smoother terminal workflows.",
                "signal_score": 131,
            }
        ],
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output_text": json.dumps(response_payload)})

    provider = OpenAIInspirationProvider(
        _config(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    report = await provider.generate(
        GenerateTaskRequest(direction="terminal UX", sources=["hackernews"], depth="standard"),
        _progress,
    )

    assert report.title == "Terminal UX Watcher"
    assert report.scores == {
        "technical_feasibility": 100,
        "market_novelty": 0,
        "business_potential": 72,
    }
    assert report.tags == ["cli", "developer-tool"]
    assert report.sources[0].signal_score == 100


@pytest.mark.asyncio
async def test_openai_provider_request_payload_supports_yolo_mode() -> None:
    requests: list[httpx.Request] = []
    response_payload = {
        "title": "Localhost OAuth Callback Debugger",
        "summary": "YOLO selected a concrete developer workflow pain.",
        "markdown": "# Localhost OAuth Callback Debugger\n\n## MVP 建议\nShip it.",
        "scores": {
            "technical_feasibility": 82,
            "market_novelty": 78,
            "business_potential": 69,
        },
        "tags": ["yolo", "oauth"],
        "sources": [
            {
                "source": "Hacker News",
                "title": "OAuth callback thread",
                "url": "https://news.ycombinator.com",
                "summary": "A visible developer pain.",
                "signal_score": 84,
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"output_text": json.dumps(response_payload)})

    provider = OpenAIInspirationProvider(
        _config(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    report = await provider.generate(
        GenerateTaskRequest(direction="", sources=["hackernews"], depth="quick", mode="yolo"),
        _progress,
    )

    sent_body = json.loads(requests[0].content)
    user_content = sent_body["input"][1]["content"]
    assert report.title == "Localhost OAuth Callback Debugger"
    assert "探索模式：YOLO 自动选题" in user_content
    assert "不要要求用户补充方向" in user_content
    assert "探索方向：" not in user_content


@pytest.mark.asyncio
async def test_openai_provider_reuses_saved_output_text() -> None:
    response_payload = {
        "title": "Saved Response Report",
        "summary": "Parsed from checkpoint.",
        "markdown": "# Saved Response Report\n\n## MVP 建议\nShip it.",
        "scores": {
            "technical_feasibility": 82,
            "market_novelty": 74,
            "business_potential": 68,
        },
        "tags": ["resume"],
        "sources": [
            {
                "source": "Checkpoint",
                "title": "Saved model output",
                "url": "https://example.com/checkpoint",
                "summary": "The output was saved before retry.",
                "signal_score": 80,
            }
        ],
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Network should not be called when output_text is checkpointed")

    provider = OpenAIInspirationProvider(
        _config(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    report = await provider.generate(
        GenerateTaskRequest(
            direction="saved output",
            sources=["hackernews"],
            depth="quick",
            checkpoint={"response": {"output_text": json.dumps(response_payload)}},
        ),
        _progress,
    )

    assert report.title == "Saved Response Report"
    assert report.tags == ["resume"]


@pytest.mark.asyncio
async def test_openai_provider_reports_api_errors() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "Incorrect API key provided"}},
        )

    provider = OpenAIInspirationProvider(
        _config(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(RuntimeError, match=r"OpenAI API request failed \(401\).*Incorrect API key"):
        await provider.generate(
            GenerateTaskRequest(direction="test", sources=["github_trending"], depth="quick"),
            _progress,
        )


def test_build_provider_routes_openai_modes() -> None:
    codex_provider = build_provider(
        Settings(agent_provider="codex", openai_api_key="sk-test", openai_model="gpt-test")
    )
    responses_provider = build_provider(
        Settings(agent_provider="response", openai_api_key="sk-test", openai_model="gpt-test")
    )

    assert isinstance(codex_provider, OpenAIAgentsProvider)
    assert isinstance(responses_provider, OpenAIResponsesProvider)


def test_build_provider_rejects_removed_provider_names() -> None:
    for provider_name in ["openai", "openai_codex", "openai_responses", "responses"]:
        with pytest.raises(ValueError, match="Unsupported agent provider"):
            build_provider(
                Settings(agent_provider=provider_name, openai_api_key="sk-test", openai_model="gpt-test")
            )
