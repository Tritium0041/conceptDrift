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
        self.active_analysis_runs = 0
        self.max_active_analysis_runs = 0

    async def run(self, prompt: str, output_schema=None) -> str:  # type: ignore[no-untyped-def]
        self.prompts.append(prompt)
        self.schemas.append(output_schema)
        payload = json.loads(prompt)

        if payload["role"] == "Codex Orchestrator Agent":
            report_input = payload["input"]
            assert "codex_competitor_research" in report_input
            assert (
                report_input["codex_competitor_research"]["products"][0]["name"]
                == "Adjacent.dev"
            )
            assert (
                report_input["codex_competitor_research"]["differentiation_strategy"][0]
                == "Own the narrow workflow."
            )
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

        if payload["role"] == "Codex competitor landscape agent":
            assert output_schema is not None
            assert "codex_technical_analysis" not in payload["input"]
            await self._track_analysis_run()
            return json.dumps(
                {
                    "analysis": "The market has adjacent developer workflow tools.",
                    "products": [
                        {
                            "name": "Adjacent.dev",
                            "url": "https://example.com/adjacent",
                            "positioning": "General developer workflow discovery.",
                            "overlap": "Targets similar developer planning pain.",
                            "difference": (
                                "It does not combine source evidence with MVP execution advice."
                            ),
                            "threat_level": 71,
                        }
                    ],
                    "differentiation_strategy": ["Own the narrow workflow."],
                    "uniqueness_angle": "Be narrower, more evidence-backed, and more actionable.",
                }
            )

        if payload["role"] == "Codex technical feasibility agent":
            assert output_schema is None
            await self._track_analysis_run()
            return "Codex feasibility review"

        if payload["role"] == "Codex source research agent":
            assert output_schema is not None
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

        raise AssertionError(f"Unexpected Codex research role: {payload['role']}")

    async def _track_analysis_run(self) -> None:
        self.active_analysis_runs += 1
        self.max_active_analysis_runs = max(
            self.max_active_analysis_runs,
            self.active_analysis_runs,
        )
        await asyncio.sleep(0.01)
        self.active_analysis_runs -= 1


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
    assert research_runtime.max_active_analysis_runs == 2
    assert len(research_runtime.prompts) == 5
    assert research_runtime.schemas[:2] == [
        research_runtime.schemas[0],
        research_runtime.schemas[1],
    ]
    assert research_runtime.schemas[0] is not None
    assert research_runtime.schemas[1] is not None
    assert research_runtime.schemas[2] is None
    assert research_runtime.schemas[3] is not None
    assert research_runtime.schemas[4] is not None
    assert runtime.calls == 0
    assert "Use your own browser/web-search/network tools" in research_runtime.prompts[0]
    competitor_prompt = json.loads(research_runtime.prompts[3])
    orchestrator_prompt = json.loads(research_runtime.prompts[4])
    assert competitor_prompt["role"] == "Codex competitor landscape agent"
    assert "similar products or close substitutes" in competitor_prompt["requirements"][1]
    assert orchestrator_prompt["role"] == "Codex Orchestrator Agent"
    assert (
        orchestrator_prompt["input"]["codex_competitor_research"]["products"][0]["name"]
        == "Adjacent.dev"
    )
    assert "ConceptDrift is only the local report-generation app" in orchestrator_prompt["task"]
    assert "do not use ConceptDrift as the report topic" in orchestrator_prompt["requirements"][1]
    assert "同类产品侦查" in orchestrator_prompt["requirements"][2]


@pytest.mark.asyncio
async def test_openai_agents_provider_prompts_last30days_skill_source() -> None:
    runtime = FakeRuntime()
    research_runtime = FakeResearchRuntime()
    provider = OpenAIAgentsProvider(
        _config(),
        runtime=runtime,
        research_runtime=research_runtime,
    )

    await provider.generate(
        GenerateTaskRequest(
            direction="developer workflow",
            sources=["github_trending", "last30days"],
            depth="standard",
        ),
        _progress,
    )

    source_prompt = json.loads(research_runtime.prompts[1])
    assert source_prompt["source_target"]["source_id"] == "last30days"
    assert "user-installed Codex skill `last30days`" in source_prompt["source_target"]["guidance"]
    assert any(
        "invoke the user-installed Codex skill `last30days`" in item
        for item in source_prompt["requirements"]
    )
    assert any("must install mvanhorn/last30days-skill" in item for item in source_prompt["requirements"])


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
    assert len(research_runtime.prompts) == 5
    discovery_prompt = json.loads(research_runtime.prompts[0])
    source_prompt = json.loads(research_runtime.prompts[1])
    competitor_prompt = json.loads(research_runtime.prompts[3])
    orchestrator_prompt = json.loads(research_runtime.prompts[4])
    assert discovery_prompt["role"] == "Codex YOLO direction discovery agent"
    assert "Do not ask the user" in discovery_prompt["task"]
    assert source_prompt["direction"] == "Localhost OAuth callback debugger"
    assert competitor_prompt["role"] == "Codex competitor landscape agent"
    assert competitor_prompt["input"]["direction"] == "Localhost OAuth callback debugger"
    assert orchestrator_prompt["input"]["request_mode"] == "yolo"
    assert orchestrator_prompt["input"]["codex_competitor_research"]["products"]
    assert "ConceptDrift is only the local report-generation app" in orchestrator_prompt["task"]
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
            "competitor_research": {
                "analysis": "Cached competitor landscape",
                "products": [
                    {
                        "name": "Adjacent.dev",
                        "url": "https://example.com/adjacent",
                        "positioning": "General developer workflow discovery.",
                        "overlap": "Targets similar developer planning pain.",
                        "difference": "It lacks evidence-backed MVP advice.",
                        "threat_level": 71,
                    }
                ],
                "differentiation_strategy": ["Own the narrow workflow."],
                "uniqueness_angle": "Be narrower, more evidence-backed, and more actionable.",
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
    assert (
        orchestrator_payload["codex_competitor_research"]["analysis"]
        == "Cached competitor landscape"
    )
    assert runtime.calls == 0


@pytest.mark.asyncio
async def test_openai_agents_provider_refreshes_final_when_competitor_checkpoint_missing() -> None:
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
            "orchestrator_output_text": json.dumps(
                {
                    "title": "Stale report",
                    "summary": "This old report lacks competitor research.",
                    "markdown": "# Stale report",
                    "scores": {
                        "technical_feasibility": 70,
                        "market_novelty": 70,
                        "business_potential": 70,
                    },
                    "tags": ["stale"],
                    "sources": [
                        {
                            "source": "GitHub Trending",
                            "title": "Old signal",
                            "url": "https://github.com/trending",
                            "summary": "Old summary",
                            "signal_score": 70,
                        }
                    ],
                }
            ),
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
    assert [json.loads(prompt)["role"] for prompt in research_runtime.prompts] == [
        "Codex competitor landscape agent",
        "Codex Orchestrator Agent",
    ]
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
