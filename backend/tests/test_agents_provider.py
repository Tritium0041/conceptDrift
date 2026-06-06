from __future__ import annotations

import asyncio
import json

import pytest

from app.providers import OpenAIAgentsProvider, OpenAIProviderConfig
from app.schemas import GenerateTaskRequest


class FakeRuntime:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, *args, **kwargs) -> str:  # type: ignore[no-untyped-def]
        self.calls += 1
        raise AssertionError("Codex provider should not call Agents SDK orchestrator")


class FakeResearchRuntime:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.schemas: list[dict | None] = []
        self.active_source_runs = 0
        self.max_active_source_runs = 0

    async def run(self, prompt: str, output_schema=None) -> str:  # type: ignore[no-untyped-def]
        self.prompts.append(prompt)
        self.schemas.append(output_schema)
        payload = json.loads(prompt)

        if payload["role"] == "Codex Orchestrator Agent":
            report_input = payload["input"]
            if report_input.get("request_mode") == "yolo":
                assert report_input["direction"] == "Localhost OAuth callback debugger"
                assert report_input["original_direction"] == ""
                assert report_input["yolo_discovery"]["source_id"] == "yolo_discovery"
                assert report_input["source_analyses"][0]["source"] == "YOLO Discovery"
                return json.dumps(
                    {
                        "title": "Localhost OAuth Callback Debugger",
                        "summary": "Synthesized from YOLO discovery.",
                        "markdown": (
                            "# Localhost OAuth Callback Debugger\n\n## MVP 建议\nBuild it."
                        ),
                        "scores": {
                            "technical_feasibility": 83,
                            "market_novelty": 81,
                            "business_potential": 70,
                        },
                        "tags": ["yolo", "oauth"],
                        "sources": [
                            {
                                "source": "YOLO Discovery",
                                "title": "OAuth callback debugging pain",
                                "url": "https://news.ycombinator.com",
                                "summary": "Developers struggle with local OAuth callbacks.",
                                "signal_score": 86,
                            }
                        ],
                    }
                )

            assert len(report_input["source_analyses"]) == 2
            first_signal = report_input["source_snapshots"][0]["signals"][0]
            assert first_signal["title"].startswith("Codex signal") or first_signal[
                "signal_score"
            ] == 35
            assert report_input["codex_technical_analysis"] == "Codex feasibility review"
            return json.dumps(
                {
                    "title": "Multi-agent Developer Tool",
                    "summary": "Synthesized by orchestrator.",
                    "markdown": "# Multi-agent Developer Tool\n\n## MVP 建议\nBuild it.",
                    "scores": {
                        "technical_feasibility": 87,
                        "market_novelty": 79,
                        "business_potential": 74,
                    },
                    "tags": ["agents", "codex"],
                    "sources": [
                        {
                            "source": "GitHub Trending",
                            "title": "Codex signal github_trending",
                            "url": "https://github.com/trending",
                            "summary": "Repo summary",
                            "signal_score": 80,
                        }
                    ],
                }
            )

        if output_schema is not None:
            source_id = payload["source_target"]["source_id"]
            source = payload["source_target"]["source"]
            self.active_source_runs += 1
            self.max_active_source_runs = max(
                self.max_active_source_runs,
                self.active_source_runs,
            )
            await asyncio.sleep(0.01)
            self.active_source_runs -= 1
            return json.dumps(
                {
                    "source_id": source_id,
                    "source": source,
                    "analysis": f"{source} Codex analysis",
                    "signals": [
                        {
                            "source": source,
                            "title": f"Codex signal {source_id}",
                            "url": payload["source_target"]["url"],
                            "summary": "Codex researched this source with external search.",
                            "signal_score": 82,
                        }
                    ],
                }
            )

        return "Codex feasibility review"


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
async def test_openai_agents_provider_runs_parallel_codex_research() -> None:
    runtime = FakeRuntime()
    research_runtime = FakeResearchRuntime()
    provider = OpenAIAgentsProvider(
        _config(),
        runtime=runtime,
        research_runtime=research_runtime,
    )

    report = await provider.generate(
        GenerateTaskRequest(
            direction="developer workflow",
            sources=["github_trending", "hackernews"],
            depth="deep",
        ),
        _progress,
    )

    assert report.title == "Multi-agent Developer Tool"
    assert report.scores["technical_feasibility"] == 87
    assert research_runtime.max_active_source_runs == 2
    assert len(research_runtime.prompts) == 4
    assert research_runtime.schemas[:2] == [
        research_runtime.schemas[0],
        research_runtime.schemas[1],
    ]
    assert research_runtime.schemas[0] is not None
    assert research_runtime.schemas[1] is not None
    assert research_runtime.schemas[2] is None
    assert research_runtime.schemas[3] is not None
    assert runtime.calls == 0
    assert "Use your own browser/web-search/network tools" in research_runtime.prompts[0]
    orchestrator_prompt = json.loads(research_runtime.prompts[3])
    assert orchestrator_prompt["role"] == "Codex Orchestrator Agent"


@pytest.mark.asyncio
async def test_openai_agents_provider_yolo_discovers_direction_before_research() -> None:
    class YoloResearchRuntime(FakeResearchRuntime):
        async def run(self, prompt: str, output_schema=None) -> str:  # type: ignore[no-untyped-def]
            payload = json.loads(prompt)
            if payload["role"] == "Codex YOLO direction discovery agent":
                self.prompts.append(prompt)
                self.schemas.append(output_schema)
                return json.dumps(
                    {
                        "direction": "Localhost OAuth callback debugger",
                        "rationale": "Recent discussions show repeated local OAuth setup pain.",
                        "rejected_directions": [
                            "generic AI task manager",
                            "another README generator",
                        ],
                        "signals": [
                            {
                                "source": "Hacker News",
                                "title": "OAuth localhost callback discussion",
                                "url": "https://news.ycombinator.com",
                                "summary": "A concrete developer workflow pain worth exploring.",
                                "signal_score": 86,
                            }
                        ],
                    }
                )
            return await super().run(prompt, output_schema)

    runtime = FakeRuntime()
    research_runtime = YoloResearchRuntime()
    provider = OpenAIAgentsProvider(
        _config(),
        runtime=runtime,
        research_runtime=research_runtime,
    )

    report = await provider.generate(
        GenerateTaskRequest(
            direction="",
            sources=["github_trending"],
            depth="standard",
            mode="yolo",
        ),
        _progress,
    )

    assert report.title == "Localhost OAuth Callback Debugger"
    assert report.tags == ["yolo", "oauth"]
    assert len(research_runtime.prompts) == 4
    discovery_prompt = json.loads(research_runtime.prompts[0])
    source_prompt = json.loads(research_runtime.prompts[1])
    orchestrator_prompt = json.loads(research_runtime.prompts[3])
    assert discovery_prompt["role"] == "Codex YOLO direction discovery agent"
    assert "Do not ask the user" in discovery_prompt["task"]
    assert source_prompt["direction"] == "Localhost OAuth callback debugger"
    assert orchestrator_prompt["input"]["request_mode"] == "yolo"
    assert runtime.calls == 0


@pytest.mark.asyncio
async def test_openai_agents_provider_reuses_codex_checkpoint() -> None:
    runtime = FakeRuntime()
    research_runtime = FakeResearchRuntime()
    provider = OpenAIAgentsProvider(
        _config(),
        runtime=runtime,
        research_runtime=research_runtime,
    )
    checkpoint = {
        "codex": {
            "direction": "developer workflow",
            "technical_analysis": "Codex feasibility review",
            "sources": {
                "github_trending": {
                    "analysis": "Cached GitHub analysis",
                    "snapshot": {
                        "source_id": "github_trending",
                        "source": "GitHub Trending",
                        "url": "https://github.com/trending",
                        "error": None,
                        "signals": [
                            {
                                "source_id": "github_trending",
                                "source": "GitHub Trending",
                                "title": "Codex signal github_trending",
                                "url": "https://github.com/trending",
                                "summary": "Cached GitHub signal.",
                                "signal_score": 82,
                            }
                        ],
                    },
                },
                "hackernews": {
                    "analysis": "Cached Hacker News analysis",
                    "snapshot": {
                        "source_id": "hackernews",
                        "source": "Hacker News",
                        "url": "https://news.ycombinator.com",
                        "error": None,
                        "signals": [
                            {
                                "source_id": "hackernews",
                                "source": "Hacker News",
                                "title": "Codex signal hackernews",
                                "url": "https://news.ycombinator.com",
                                "summary": "Cached Hacker News signal.",
                                "signal_score": 78,
                            }
                        ],
                    },
                },
            },
        }
    }

    report = await provider.generate(
        GenerateTaskRequest(
            direction="developer workflow",
            sources=["github_trending", "hackernews"],
            depth="standard",
            checkpoint=checkpoint,
        ),
        _progress,
    )

    assert report.title == "Multi-agent Developer Tool"
    assert len(research_runtime.prompts) == 1
    orchestrator_payload = json.loads(research_runtime.prompts[0])["input"]
    assert orchestrator_payload["source_analyses"][0]["analysis"] == "Cached GitHub analysis"
    assert orchestrator_payload["codex_technical_analysis"] == "Codex feasibility review"
    assert runtime.calls == 0


@pytest.mark.asyncio
async def test_openai_agents_provider_uses_fallback_snapshot_for_unparseable_codex_output() -> None:
    class BadResearchRuntime(FakeResearchRuntime):
        async def run(self, prompt: str, output_schema=None) -> str:  # type: ignore[no-untyped-def]
            payload = json.loads(prompt)
            if payload["role"] == "Codex source research agent":
                self.prompts.append(prompt)
                self.schemas.append(output_schema)
                return "not json"
            return await super().run(prompt, output_schema)

    runtime = FakeRuntime()
    research_runtime = BadResearchRuntime()
    provider = OpenAIAgentsProvider(
        _config(),
        runtime=runtime,
        research_runtime=research_runtime,
    )

    report = await provider.generate(
        GenerateTaskRequest(
            direction="developer workflow",
            sources=["github_trending", "hackernews"],
            depth="standard",
        ),
        _progress,
    )

    assert report.title == "Multi-agent Developer Tool"
    orchestrator_payload = json.loads(research_runtime.prompts[-1])["input"]
    assert orchestrator_payload["source_snapshots"][0]["error"] == "Codex output was not valid JSON"
    assert orchestrator_payload["source_snapshots"][0]["signals"][0]["signal_score"] == 35
    assert runtime.calls == 0
