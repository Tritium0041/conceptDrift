from __future__ import annotations

import asyncio
import json

import pytest

from app.agent_runtime import AgentRunSpec
from app.providers import OpenAIAgentsProvider, OpenAIProviderConfig
from app.schemas import GenerateTaskRequest


class FakeRuntime:
    def __init__(self) -> None:
        self.specs: list[AgentRunSpec] = []

    async def run(self, spec: AgentRunSpec, on_event=None) -> str:  # type: ignore[no-untyped-def]
        self.specs.append(spec)
        if on_event is not None:
            await on_event("fake_stream")

        if spec.name == "ConceptDrift Orchestrator Agent":
            payload = json.loads(spec.input)
            assert len(payload["source_analyses"]) == 2
            first_signal = payload["source_snapshots"][0]["signals"][0]
            assert first_signal["title"].startswith("Codex signal") or first_signal["signal_score"] == 35
            assert payload["codex_technical_analysis"] == "Codex feasibility review"
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

        raise AssertionError(f"Unexpected agent run: {spec.name}")


class FakeResearchRuntime:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.schemas: list[dict | None] = []
        self.active_source_runs = 0
        self.max_active_source_runs = 0

    async def run(self, prompt: str, output_schema=None) -> str:  # type: ignore[no-untyped-def]
        self.prompts.append(prompt)
        self.schemas.append(output_schema)

        if output_schema is not None:
            payload = json.loads(prompt)
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
    assert len(research_runtime.prompts) == 3
    assert research_runtime.schemas[:2] == [
        research_runtime.schemas[0],
        research_runtime.schemas[1],
    ]
    assert research_runtime.schemas[0] is not None
    assert research_runtime.schemas[1] is not None
    assert research_runtime.schemas[2] is None
    assert [spec.name for spec in runtime.specs] == ["ConceptDrift Orchestrator Agent"]
    assert "Use your own browser/web-search/network tools" in research_runtime.prompts[0]


@pytest.mark.asyncio
async def test_openai_agents_provider_uses_fallback_snapshot_for_unparseable_codex_output() -> None:
    class BadResearchRuntime(FakeResearchRuntime):
        async def run(self, prompt: str, output_schema=None) -> str:  # type: ignore[no-untyped-def]
            self.prompts.append(prompt)
            self.schemas.append(output_schema)
            if output_schema is not None:
                return "not json"
            return "Codex feasibility review"

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
    orchestrator_payload = json.loads(runtime.specs[0].input)
    assert orchestrator_payload["source_snapshots"][0]["error"] == "Codex output was not valid JSON"
    assert orchestrator_payload["source_snapshots"][0]["signals"][0]["signal_score"] == 35
