from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.agent_runtime import (
    CodexResearchConfig,
    CodexResearchRuntime,
)
from app.config import Settings
from app.schemas import GenerateTaskRequest
from app.source_tools import (
    SourceSignal,
    SourceSnapshot,
    build_source_research_target,
    fallback_signal,
    score,
    source_home_url,
    source_label,
)


ProgressCallback = Callable[[int, str], Awaitable[None]]
logger = logging.getLogger("uvicorn.error")


async def _save_resume_checkpoint(
    progress: ProgressCallback,
    patch: dict[str, Any],
) -> None:
    saver = getattr(progress, "save_checkpoint", None)
    if saver is not None:
        await saver(patch)


@dataclass(frozen=True)
class GeneratedSource:
    source: str
    title: str
    url: str
    summary: str
    signal_score: int


@dataclass(frozen=True)
class GeneratedReport:
    title: str
    summary: str
    markdown: str
    scores: dict[str, int]
    tags: list[str]
    sources: list[GeneratedSource]


@dataclass(frozen=True)
class OpenAIProviderConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float
    tracing_disabled: bool = True
    codex_agent_timeout_seconds: float = 120.0
    codex_agent_network_enabled: bool = True
    codex_agent_web_search_mode: str = "live"


class InspirationProvider(Protocol):
    async def generate(
        self,
        request: GenerateTaskRequest,
        progress: ProgressCallback,
    ) -> GeneratedReport:
        pass


class ResearchRuntime(Protocol):
    async def run(
        self,
        prompt: str,
        output_schema: dict[str, Any] | None = None,
    ) -> str:
        pass


class _OpenAISourcePayload(BaseModel):
    source: str
    title: str
    url: str
    summary: str
    signal_score: int


class _OpenAIReportPayload(BaseModel):
    title: str
    summary: str
    markdown: str
    scores: dict[str, int]
    tags: list[str]
    sources: list[_OpenAISourcePayload]


class _SourceAgentPayload(BaseModel):
    source_id: str | None = None
    source: str | None = None
    analysis: str
    signals: list[_OpenAISourcePayload]


class _YoloDiscoveryPayload(BaseModel):
    direction: str
    rationale: str
    signals: list[_OpenAISourcePayload]
    rejected_directions: list[str]


OPENAI_REPORT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "summary", "markdown", "scores", "tags", "sources"],
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "markdown": {"type": "string"},
        "scores": {
            "type": "object",
            "additionalProperties": False,
            "required": ["technical_feasibility", "market_novelty", "business_potential"],
            "properties": {
                "technical_feasibility": {"type": "integer"},
                "market_novelty": {"type": "integer"},
                "business_potential": {"type": "integer"},
            },
        },
        "tags": {"type": "array", "items": {"type": "string"}},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source", "title", "url", "summary", "signal_score"],
                "properties": {
                    "source": {"type": "string"},
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "summary": {"type": "string"},
                    "signal_score": {"type": "integer"},
                },
            },
        },
    },
}

YOLO_DISCOVERY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["direction", "rationale", "signals", "rejected_directions"],
    "properties": {
        "direction": {"type": "string"},
        "rationale": {"type": "string"},
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source", "title", "url", "summary", "signal_score"],
                "properties": {
                    "source": {"type": "string"},
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "summary": {"type": "string"},
                    "signal_score": {"type": "integer"},
                },
            },
        },
        "rejected_directions": {"type": "array", "items": {"type": "string"}},
    },
}

SOURCE_RESEARCH_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["source_id", "source", "analysis", "signals"],
    "properties": {
        "source_id": {"type": "string"},
        "source": {"type": "string"},
        "analysis": {"type": "string"},
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source", "title", "url", "summary", "signal_score"],
                "properties": {
                    "source": {"type": "string"},
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "summary": {"type": "string"},
                    "signal_score": {"type": "integer"},
                },
            },
        },
    },
}


class MockInspirationProvider:
    async def generate(
        self,
        request: GenerateTaskRequest,
        progress: ProgressCallback,
    ) -> GeneratedReport:
        direction = self._direction(request)
        if request.mode == "yolo":
            await progress(12, "YOLO agent 自动发现候选方向")
            await asyncio.sleep(0.01)
        await progress(15, "采集多元灵感信号")
        await asyncio.sleep(0.01)
        sources = self._build_sources(request.sources, direction)

        await progress(40, "评估技术可行性")
        await asyncio.sleep(0.01)
        feasibility = self._feasibility(direction, request.depth)

        await progress(65, "分析市场新颖性")
        await asyncio.sleep(0.01)
        novelty = self._novelty(direction)

        await progress(85, "整理商业潜力与报告")
        await asyncio.sleep(0.01)

        title = f"{direction}：开发者灵感报告"
        tags = self._tags(direction, request.sources)
        if request.mode == "yolo":
            tags = ["yolo", *tags]
        scores = {
            "technical_feasibility": feasibility,
            "market_novelty": novelty,
            "business_potential": 72 if request.depth != "quick" else 64,
        }
        if request.mode == "yolo":
            summary = (
                f"YOLO 模式自动选择“{direction}”作为本次探索方向。该方向适合以个人开发者可维护的 "
                "MVP 先验证需求，再逐步扩展数据源、自动化和付费能力。"
            )
        else:
            summary = (
                f"围绕“{direction}”生成的轻量调研报告。该方向适合以个人开发者可维护的 "
                "MVP 先验证需求，再逐步扩展数据源、自动化和付费能力。"
            )
        markdown = self._markdown(direction, request, summary, scores, sources)
        return GeneratedReport(
            title=title,
            summary=summary,
            markdown=markdown,
            scores=scores,
            tags=tags,
            sources=sources,
        )

    def _direction(self, request: GenerateTaskRequest) -> str:
        if request.mode == "yolo":
            return "AI 原生开发工作流机会雷达"
        return request.direction.strip() or "随机开发者工具灵感"

    def _build_sources(self, source_names: list[str], direction: str) -> list[GeneratedSource]:
        labels = {
            "github_trending": "GitHub Trending",
            "hackernews": "Hacker News",
            "product_hunt": "Product Hunt",
            "reddit": "Reddit",
        }
        sources: list[GeneratedSource] = []
        for index, source in enumerate(source_names, start=1):
            readable = labels.get(source, source.replace("_", " ").title())
            sources.append(
                GeneratedSource(
                    source=readable,
                    title=f"{readable} signal #{index}: {direction}",
                    url=f"https://example.com/conceptdrift/{source}",
                    summary=(
                        f"模拟来源显示，开发者正在寻找围绕“{direction}”的更低摩擦、"
                        "更自动化的工具链。"
                    ),
                    signal_score=max(55, 88 - index * 7),
                )
            )
        return sources

    def _feasibility(self, direction: str, depth: str) -> int:
        base = 78 if depth == "quick" else 74 if depth == "standard" else 68
        if "AI" in direction.upper() or "LLM" in direction.upper():
            base += 4
        return min(base, 92)

    def _novelty(self, direction: str) -> int:
        return 76 if len(direction) > 8 else 68

    def _tags(self, direction: str, sources: list[str]) -> list[str]:
        tags = ["developer-tool", "mvp", "mock-provider"]
        if "AI" in direction.upper() or "LLM" in direction.upper():
            tags.append("ai")
        tags.extend(source.replace("_", "-") for source in sources[:2])
        return list(dict.fromkeys(tags))

    def _markdown(
        self,
        direction: str,
        request: GenerateTaskRequest,
        summary: str,
        scores: dict[str, int],
        sources: list[GeneratedSource],
    ) -> str:
        source_lines = "\n".join(
            f"- **{item.source}**：[{item.title}]({item.url})，信号分 {item.signal_score}。"
            for item in sources
        )
        return f"""# {direction}：开发者灵感报告

## 摘要
{summary}

## 核心概念
构建一个面向个人开发者的轻量工具，帮助他们在日常研发、调研或发布流程中减少重复决策。第一版应专注一个明确场景，使用少量高价值输入生成可直接行动的建议。

## 技术可行性
- 评分：{scores["technical_feasibility"]}/100
- 建议栈：FastAPI/SQLite 负责数据与任务状态，Next.js 提供工作台式交互。
- 预计周期：{self._duration(request.depth)}
- 主要风险：真实数据源质量、LLM 输出稳定性、导出格式细节。

## 市场新颖性
- 评分：{scores["market_novelty"]}/100
- 差异化空间：聚焦“个人开发者灵感到执行”的闭环，而不是泛化的趋势摘要。
- 竞品观察：多数工具停留在内容聚合，较少把技术可行性、市场空白和 MVP 路线压缩到一份报告。

## 商业潜力参考
- 评分：{scores["business_potential"]}/100
- 目标用户：独立开发者、开源维护者、技术创作者。
- 变现路径：免费生成少量报告，高级版提供更多数据源、导出模板和自动化定时调研。

## 灵感来源
{source_lines}

## MVP 建议
1. 先实现单方向输入、报告生成、历史归档和 Markdown 导出。
2. 增加真实数据源 Provider，并保留 mock provider 作为回归测试基线。
3. 对高价值报告加入收藏、标签和二次追问能力。
"""

    def _duration(self, depth: str) -> str:
        if depth == "quick":
            return "3-5 天完成可演示原型"
        if depth == "deep":
            return "2-3 周完成数据源与质量打磨"
        return "1-2 周完成可用 MVP"


class OpenAIAgentsProvider:
    def __init__(
        self,
        config: OpenAIProviderConfig,
        runtime: Any | None = None,
        research_runtime: ResearchRuntime | None = None,
    ) -> None:
        self._config = config
        _ = runtime
        self._research_runtime = research_runtime or CodexResearchRuntime(
            CodexResearchConfig(
                api_key=config.api_key,
                base_url=config.base_url,
                model=config.model,
                timeout_seconds=config.codex_agent_timeout_seconds,
                network_access_enabled=config.codex_agent_network_enabled,
                web_search_mode=config.codex_agent_web_search_mode,
            )
        )

    async def generate(
        self,
        request: GenerateTaskRequest,
        progress: ProgressCallback,
    ) -> GeneratedReport:
        if not self._config.api_key.strip():
            raise RuntimeError(
                "OPENAI_API_KEY is required when CONCEPTDRIFT_AGENT_PROVIDER=codex"
            )

        checkpoint = self._codex_checkpoint(request)
        direction = checkpoint.get("direction") or request.direction.strip() or "随机开发者工具灵感"
        await progress(8, "启动 Codex 调研与编排")

        yolo_discovery: dict[str, Any] | None = None
        if request.mode == "yolo":
            cached_yolo = checkpoint.get("yolo_discovery")
            if isinstance(cached_yolo, dict):
                await progress(12, "复用 YOLO 自动发现方向")
                yolo_discovery = self._restore_yolo_discovery(cached_yolo, request)
                direction = yolo_discovery["direction"]
            else:
                await progress(12, "YOLO agent 联网发现候选方向")
                yolo_discovery = await self._run_yolo_discovery(request)
                direction = yolo_discovery["direction"]
                await _save_resume_checkpoint(
                    progress,
                    {
                        "codex": {
                            "direction": direction,
                            "yolo_discovery": self._yolo_discovery_checkpoint(yolo_discovery),
                        }
                    },
                )
        elif checkpoint.get("direction"):
            await progress(12, "复用已确认探索方向")

        await progress(18, "Codex agent 并发调研外部信号")
        research_request = GenerateTaskRequest(
            direction=direction,
            sources=request.sources,
            depth=request.depth,
            mode=request.mode,
            checkpoint=request.checkpoint,
        )
        source_results = await self._run_source_agents(
            request=research_request,
            progress=progress,
        )
        snapshots = [result["snapshot"] for result in source_results]
        source_analyses = [
            {"source": result["snapshot"].source, "analysis": result["analysis"]}
            for result in source_results
        ]
        if yolo_discovery is not None:
            snapshots = [yolo_discovery["snapshot"], *snapshots]
            source_analyses = [
                {
                    "source": yolo_discovery["snapshot"].source,
                    "analysis": yolo_discovery["analysis"],
                },
                *source_analyses,
            ]

        await progress(65, "Codex agent 复核技术可行性")
        cached_technical_analysis = checkpoint.get("technical_analysis")
        if isinstance(cached_technical_analysis, str) and cached_technical_analysis.strip():
            await progress(65, "复用技术可行性复核")
            technical_analysis = cached_technical_analysis
        else:
            technical_analysis = await self._research_runtime.run(
                self._technical_research_prompt(
                    direction=direction,
                    depth=request.depth,
                    source_analyses=source_analyses,
                    snapshots=snapshots,
                )
            )
            await _save_resume_checkpoint(
                progress,
                {"codex": {"direction": direction, "technical_analysis": technical_analysis}},
            )

        cached_final_text = checkpoint.get("orchestrator_output_text")
        if isinstance(cached_final_text, str) and cached_final_text.strip():
            await progress(82, "复用 Codex Orchestrator 汇总报告")
            final_text = cached_final_text
        else:
            await progress(82, "Codex Orchestrator 汇总报告")
            final_text = await self._research_runtime.run(
                self._orchestrator_prompt(
                    {
                        "direction": direction,
                        "request_mode": request.mode,
                        "original_direction": request.direction.strip(),
                        "yolo_discovery": (
                            yolo_discovery["snapshot"].as_dict()
                            if yolo_discovery is not None
                            else None
                        ),
                        "depth": request.depth,
                        "requested_sources": request.sources,
                        "source_snapshots": [snapshot.as_dict() for snapshot in snapshots],
                        "source_analyses": source_analyses,
                        "codex_technical_analysis": technical_analysis,
                    }
                ),
                output_schema=OPENAI_REPORT_JSON_SCHEMA,
            )

        await progress(95, "校验多 Agent 报告结构")
        report = self._parse_report_text(final_text)
        if not isinstance(cached_final_text, str) or not cached_final_text.strip():
            await _save_resume_checkpoint(
                progress,
                {"codex": {"direction": direction, "orchestrator_output_text": final_text}},
            )
        return report

    async def _run_yolo_discovery(self, request: GenerateTaskRequest) -> dict[str, Any]:
        text = await self._research_runtime.run(
            self._yolo_discovery_prompt(request),
            output_schema=YOLO_DISCOVERY_JSON_SCHEMA,
        )
        return self._parse_yolo_discovery_text(text, request)

    def _codex_checkpoint(self, request: GenerateTaskRequest) -> dict[str, Any]:
        checkpoint = request.checkpoint.get("codex")
        return checkpoint if isinstance(checkpoint, dict) else {}

    def _yolo_discovery_checkpoint(self, discovery: dict[str, Any]) -> dict[str, Any]:
        snapshot = discovery["snapshot"]
        return {
            "direction": discovery["direction"],
            "snapshot": snapshot.as_dict(),
            "analysis": discovery["analysis"],
        }

    def _restore_yolo_discovery(
        self,
        checkpoint: dict[str, Any],
        request: GenerateTaskRequest,
    ) -> dict[str, Any]:
        snapshot = self._snapshot_from_dict(checkpoint.get("snapshot"))
        if snapshot is None:
            return self._fallback_yolo_discovery(
                request,
                "Saved YOLO checkpoint was incomplete",
                str(checkpoint.get("analysis") or ""),
            )
        direction = str(checkpoint.get("direction") or "").strip() or self._fallback_yolo_direction()
        return {
            "direction": direction[:300],
            "snapshot": snapshot,
            "analysis": str(checkpoint.get("analysis") or "").strip(),
        }

    def _restore_source_result(self, checkpoint: dict[str, Any]) -> dict[str, Any] | None:
        snapshot = self._snapshot_from_dict(checkpoint.get("snapshot"))
        if snapshot is None:
            return None
        return {
            "snapshot": snapshot,
            "analysis": str(checkpoint.get("analysis") or "").strip(),
        }

    def _snapshot_from_dict(self, payload: Any) -> SourceSnapshot | None:
        if not isinstance(payload, dict):
            return None
        raw_signals = payload.get("signals")
        if not isinstance(raw_signals, list):
            return None
        signals: list[SourceSignal] = []
        for item in raw_signals:
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary") or "").strip()
            if not summary:
                continue
            try:
                signal_score = int(item.get("signal_score") or 0)
            except (TypeError, ValueError):
                signal_score = 50
            signals.append(
                SourceSignal(
                    source_id=str(item.get("source_id") or payload.get("source_id") or ""),
                    source=str(item.get("source") or payload.get("source") or "Codex").strip(),
                    title=str(item.get("title") or item.get("source") or "Codex signal").strip(),
                    url=str(item.get("url") or payload.get("url") or "https://example.com").strip(),
                    summary=summary,
                    signal_score=score(signal_score),
                )
            )
        if not signals:
            return None
        return SourceSnapshot(
            source_id=str(payload.get("source_id") or "codex"),
            source=str(payload.get("source") or "Codex").strip(),
            url=str(payload.get("url") or signals[0].url).strip(),
            signals=signals,
            error=payload.get("error") if isinstance(payload.get("error"), str) else None,
        )

    async def _run_source_agents(
        self,
        request: GenerateTaskRequest,
        progress: ProgressCallback,
    ) -> list[dict[str, Any]]:
        direction = request.direction.strip() or "随机开发者工具灵感"
        checkpoint = self._codex_checkpoint(request)
        cached_sources = checkpoint.get("sources")
        source_checkpoints = cached_sources if isinstance(cached_sources, dict) else {}
        results_by_source: dict[str, dict[str, Any]] = {}

        async def run_one(source_id: str) -> dict[str, Any]:
            target = build_source_research_target(source_id)
            await progress(28, f"Codex agent 调研 {target.source}")
            text = await self._research_runtime.run(
                self._source_research_prompt(
                    direction=direction,
                    depth=request.depth,
                    target=target.as_dict(),
                ),
                output_schema=SOURCE_RESEARCH_JSON_SCHEMA,
            )
            snapshot, analysis = self._parse_source_research_text(text, source_id, direction)
            result = {"snapshot": snapshot, "analysis": analysis}
            await _save_resume_checkpoint(
                progress,
                {
                    "codex": {
                        "direction": direction,
                        "sources": {
                            source_id: {
                                "snapshot": snapshot.as_dict(),
                                "analysis": analysis,
                            }
                        },
                    }
                },
            )
            return result

        missing_sources: list[str] = []
        for source_id in request.sources:
            cached_source = source_checkpoints.get(source_id)
            if isinstance(cached_source, dict):
                restored = self._restore_source_result(cached_source)
                if restored is not None:
                    await progress(28, f"复用 Codex agent 调研 {restored['snapshot'].source}")
                    results_by_source[source_id] = restored
                    continue
            missing_sources.append(source_id)

        gathered = await asyncio.gather(
            *(run_one(source_id) for source_id in missing_sources),
            return_exceptions=True,
        )
        errors: list[BaseException] = []
        for source_id, result in zip(missing_sources, gathered, strict=True):
            if isinstance(result, BaseException):
                errors.append(result)
            else:
                results_by_source[source_id] = result
        if errors:
            raise errors[0]

        return [results_by_source[source_id] for source_id in request.sources]

    def _yolo_discovery_prompt(self, request: GenerateTaskRequest) -> str:
        seed = request.direction.strip()
        return json.dumps(
            {
                "role": "Codex YOLO direction discovery agent",
                "language": "zh-CN",
                "task": (
                    "Autonomously discover one interesting, researchable developer-product "
                    "direction. Use your own browser/web-search/network tools to scan current "
                    "public web signals. Do not ask the user for a direction and do not depend "
                    "on this application's backend scraping APIs."
                ),
                "optional_seed": seed if seed and seed != "YOLO 自动探索" else "",
                "depth": request.depth,
                "source_targets": [
                    build_source_research_target(source_id).as_dict()
                    for source_id in request.sources
                ],
                "selection_criteria": [
                    "Pick a direction with visible current developer pain, not a broad category.",
                    "Prefer directions that a solo developer could prototype in days or weeks.",
                    "Use fresh public signals from inspected URLs and avoid generic AI wrapper ideas.",
                    "Reject at least two weaker alternatives and briefly name why they lost.",
                ],
                "requirements": [
                    "Return only JSON matching the supplied output schema.",
                    "direction must be specific enough to become the final report topic.",
                    "signals must include 2-5 inspected public URLs when available.",
                    "rationale must explain why this direction is worth exploring now.",
                ],
            },
            ensure_ascii=False,
        )

    def _source_research_prompt(
        self,
        direction: str,
        depth: str,
        target: dict[str, str],
    ) -> str:
        return json.dumps(
            {
                "role": "Codex source research agent",
                "language": "zh-CN",
                "task": (
                    "Use your own browser/web-search/network tools to research current public "
                    "signals. Do not call or rely on this application's backend source-scraping APIs. "
                    "Prefer primary URLs and cite only pages you actually inspected."
                ),
                "direction": direction,
                "depth": depth,
                "source_target": target,
                "requirements": [
                    "Return only JSON matching the supplied output schema.",
                    "Collect 1-5 high-signal items from this source or closely related primary sources.",
                    "Each signal summary must explain why it matters for the requested direction.",
                    "analysis must summarize opportunities, noise, risks, and actionable insight.",
                    "If the source has little relevant activity, say so and return the best public fallback URL.",
                ],
            },
            ensure_ascii=False,
        )

    def _technical_research_prompt(
        self,
        direction: str,
        depth: str,
        source_analyses: list[dict[str, str]],
        snapshots: list[SourceSnapshot],
    ) -> str:
        return json.dumps(
            {
                "role": "Codex technical feasibility agent",
                "language": "zh-CN",
                "task": (
                    "Review the MVP implementation path, engineering risks, package/framework "
                    "choices, testing strategy, and maintainability. Use your own browser/web-search "
                    "tools when current ecosystem facts would materially affect the conclusion. "
                    "Use the direct Codex research runtime for this work."
                ),
                "direction": direction,
                "depth": depth,
                "source_analyses": source_analyses,
                "source_snapshots": [snapshot.as_dict() for snapshot in snapshots],
                "output": "Return concise Chinese prose, not JSON.",
            },
            ensure_ascii=False,
        )

    def _orchestrator_prompt(self, payload: dict[str, Any]) -> str:
        return json.dumps(
            {
                "role": "Codex Orchestrator Agent",
                "language": "zh-CN",
                "task": (
                    "Synthesize the final developer inspiration report for the opportunity in "
                    "input.direction using the provided Codex research snapshots, source analyses, "
                    "and technical review. ConceptDrift is only the local report-generation app, "
                    "not the product, opportunity, startup, or project being evaluated unless the "
                    "user explicitly supplied it as input.direction. Do not call this application's "
                    "backend scraping APIs. Treat source_snapshots as the evidence base and only "
                    "use browser/web-search tools if a current fact is materially necessary."
                ),
                "input": payload,
                "requirements": [
                    "Return only JSON matching the supplied output schema.",
                    (
                        "title, summary, markdown, tags, and sources must center on input.direction; "
                        "do not use ConceptDrift as the report topic, product name, source, or tag "
                        "unless input.direction explicitly asks for it."
                    ),
                    (
                        "markdown must be a complete Markdown report with 摘要、核心概念、"
                        "技术可行性、市场新颖性、商业潜力、灵感来源、"
                        "MVP 建议."
                    ),
                    (
                        "When request_mode is yolo, center the report on input.direction "
                        "and explain why YOLO Discovery selected it."
                    ),
                    (
                        "scores.technical_feasibility, scores.market_novelty, and "
                        "scores.business_potential must be integers from 0 to 100."
                    ),
                    "sources must be grounded in the provided source_snapshots.",
                ],
            },
            ensure_ascii=False,
        )

    def _parse_yolo_discovery_text(
        self,
        text: str,
        request: GenerateTaskRequest,
    ) -> dict[str, Any]:
        try:
            payload = _YoloDiscoveryPayload.model_validate_json(text)
        except ValidationError:
            return self._fallback_yolo_discovery(
                request,
                "Codex YOLO discovery output was not valid JSON",
                text,
            )

        direction = payload.direction.strip() or self._fallback_yolo_direction()
        signals = [
            SourceSignal(
                source_id="yolo_discovery",
                source=item.source.strip() or "YOLO Discovery",
                title=item.title.strip() or "YOLO discovery signal",
                url=item.url.strip() or self._fallback_yolo_url(request),
                summary=item.summary.strip(),
                signal_score=score(item.signal_score),
            )
            for item in payload.signals
            if item.summary.strip()
        ]
        if not signals:
            return self._fallback_yolo_discovery(
                request,
                "Codex YOLO discovery returned no usable signals",
                payload.rationale,
            )

        rejected = [item.strip() for item in payload.rejected_directions if item.strip()]
        analysis = payload.rationale.strip()
        if rejected:
            analysis = f"{analysis}\n\n被淘汰方向：{'; '.join(rejected)}"
        snapshot = SourceSnapshot(
            source_id="yolo_discovery",
            source="YOLO Discovery",
            url=signals[0].url,
            signals=signals,
        )
        return {"direction": direction[:300], "snapshot": snapshot, "analysis": analysis}

    def _parse_source_research_text(
        self,
        text: str,
        source_id: str,
        direction: str,
    ) -> tuple[SourceSnapshot, str]:
        try:
            payload = _SourceAgentPayload.model_validate_json(text)
        except ValidationError:
            return self._fallback_snapshot(source_id, direction, "Codex output was not valid JSON", text)

        label = payload.source or source_label(source_id)
        snapshot_source_id = payload.source_id or source_id
        signals = [
            SourceSignal(
                source_id=snapshot_source_id,
                source=item.source.strip() or label,
                title=item.title.strip() or label,
                url=item.url.strip() or source_home_url(source_id),
                summary=item.summary.strip(),
                signal_score=score(item.signal_score),
            )
            for item in payload.signals
            if item.summary.strip()
        ]
        if not signals:
            return self._fallback_snapshot(source_id, direction, "Codex returned no usable signals", payload.analysis)
        snapshot = SourceSnapshot(
            source_id=snapshot_source_id,
            source=label,
            url=source_home_url(source_id),
            signals=signals,
        )
        return snapshot, payload.analysis.strip()

    def _fallback_snapshot(
        self,
        source_id: str,
        direction: str,
        reason: str,
        analysis: str,
    ) -> tuple[SourceSnapshot, str]:
        label = source_label(source_id)
        snapshot = SourceSnapshot(
            source_id=source_id,
            source=label,
            url=source_home_url(source_id),
            signals=[fallback_signal(source_id, direction, reason)],
            error=reason,
        )
        return snapshot, analysis.strip() or reason

    def _fallback_yolo_discovery(
        self,
        request: GenerateTaskRequest,
        reason: str,
        analysis: str,
    ) -> dict[str, Any]:
        direction = self._fallback_yolo_direction()
        signal = SourceSignal(
            source_id="yolo_discovery",
            source="YOLO Discovery",
            title=f"YOLO fallback: {direction}",
            url=self._fallback_yolo_url(request),
            summary=(
                f"YOLO 方向发现未能返回可解析实时条目，原因：{reason}。"
                "后续调研将围绕一个可由个人开发者验证的默认方向继续。"
            ),
            signal_score=40,
        )
        snapshot = SourceSnapshot(
            source_id="yolo_discovery",
            source="YOLO Discovery",
            url=signal.url,
            signals=[signal],
            error=reason,
        )
        return {"direction": direction, "snapshot": snapshot, "analysis": analysis.strip() or reason}

    def _fallback_yolo_direction(self) -> str:
        return "AI 原生开发工作流机会雷达"

    def _fallback_yolo_url(self, request: GenerateTaskRequest) -> str:
        if request.sources:
            return source_home_url(request.sources[0])
        return "https://github.com/trending"

    def _orchestrator_instructions(self) -> str:
        return (
            "你是开发者灵感报告的中心编排 Agent。ConceptDrift 只是生成报告的本地应用名，"
            "不是被调研的产品、机会、创业项目或开源项目，除非 direction 明确要求调研它。"
            "你必须综合 source_analyses、"
            "source_snapshots 和 codex_technical_analysis，生成最终开发者灵感报告。"
            "title、summary、markdown、tags 和 sources 必须围绕 direction 字段里的主题，"
            "不要把 ConceptDrift 当作报告主题、产品名、来源或标签。"
            "只返回 JSON，不要 Markdown code fence，不要解释。JSON 必须符合输入中的 "
            "required_json_schema。markdown 字段内部必须是完整 Markdown 报告，并包含："
            "摘要、核心概念、技术可行性、市场新颖性、商业潜力、灵感来源、MVP 建议。"
            "当 request_mode 为 yolo 时，报告必须围绕 direction 字段里的自动发现方向，"
            "并在摘要或灵感来源中说明 YOLO Discovery 为什么选择它。"
            "scores 三个分数必须是 0-100 整数；sources 必须来自 Codex 调研生成的 "
            "source_snapshots。"
        )

    def _parse_report_text(self, text: str) -> GeneratedReport:
        return OpenAIResponsesProvider(self._config)._parse_report_text(text)


class OpenAIResponsesProvider:
    def __init__(
        self,
        config: OpenAIProviderConfig,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._client = client

    async def generate(
        self,
        request: GenerateTaskRequest,
        progress: ProgressCallback,
    ) -> GeneratedReport:
        if not self._config.api_key.strip():
            raise RuntimeError(
                "OPENAI_API_KEY is required when CONCEPTDRIFT_AGENT_PROVIDER=response"
        )

        await progress(10, "连接 OpenAI Agent")
        checkpoint = self._response_checkpoint(request)
        cached_payload = checkpoint.get("payload")
        payload = cached_payload if isinstance(cached_payload, dict) else self._request_payload(request)
        await _save_resume_checkpoint(progress, {"response": {"payload": payload}})
        await progress(35, "OpenAI Agent 正在调研与生成结构化报告")

        cached_text = checkpoint.get("output_text")
        if isinstance(cached_text, str) and cached_text.strip():
            await progress(75, "复用 OpenAI Agent 返回结果")
            text = cached_text
        else:
            response_payload = await self._post_response(payload)
            await progress(75, "解析 OpenAI Agent 返回结果")
            text = self._extract_output_text(response_payload)
            await _save_resume_checkpoint(
                progress,
                {"response": {"payload": payload, "output_text": text}},
            )

        report = self._parse_report_text(text)
        await progress(90, "校验报告结构并准备入库")
        return report

    def _response_checkpoint(self, request: GenerateTaskRequest) -> dict[str, Any]:
        checkpoint = request.checkpoint.get("response")
        return checkpoint if isinstance(checkpoint, dict) else {}

    def _request_payload(self, request: GenerateTaskRequest) -> dict[str, Any]:
        seed = request.direction.strip()
        direction = seed or "随机开发者工具灵感"
        source_list = ", ".join(request.sources)
        depth_instruction = {
            "quick": "输出更短，突出可快速验证的 MVP。",
            "standard": "保持完整但避免冗长，覆盖调研、判断和 MVP 路线。",
            "deep": "输出更深入，补充风险、差异化和商业化判断。",
        }.get(request.depth, "保持标准深度。")
        if request.mode == "yolo":
            task_instruction = (
                "探索模式：YOLO 自动选题\n"
                f"可选种子：{seed if seed and seed != 'YOLO 自动探索' else '无'}\n"
                f"信号源标识：{source_list}\n"
                f"调研深度：{request.depth}\n"
                f"{depth_instruction}\n\n"
                "要求：\n"
                "1. 先自主选择一个当前值得研究的具体开发者产品方向，不要要求用户补充方向。\n"
                "2. title、summary、markdown 都必须围绕你选择出的方向。\n"
                "3. 不要把 ConceptDrift 当作被调研产品、报告主题、来源或标签。\n"
                "4. markdown 生成完整 Markdown 报告，必须包含摘要、核心概念、"
                "技术可行性、市场新颖性、商业潜力、灵感来源、MVP 建议。\n"
                "5. 在摘要或灵感来源中说明 YOLO 选择该方向的理由。\n"
                "6. scores 的三个分数必须是 0-100 的整数。\n"
                "7. sources 至少覆盖用户选择的信号源；无法实时访问某来源时，"
                "给出可追溯的公开主页 URL，并在 summary 中说明它代表的信号类型。"
            )
        else:
            task_instruction = (
                f"探索方向：{direction}\n"
                f"信号源标识：{source_list}\n"
                f"调研深度：{request.depth}\n"
                f"{depth_instruction}\n\n"
                "要求：\n"
                "1. title 使用中文或中英混合，明确项目方向。\n"
                "2. summary 用 2-4 句话说明机会点。\n"
                "3. 不要把 ConceptDrift 当作被调研产品、报告主题、来源或标签。\n"
                "4. markdown 生成完整 Markdown 报告，必须包含摘要、核心概念、"
                "技术可行性、市场新颖性、商业潜力、灵感来源、MVP 建议。\n"
                "5. scores 的三个分数必须是 0-100 的整数。\n"
                "6. sources 至少覆盖用户选择的信号源；无法实时访问某来源时，"
                "给出可追溯的公开主页 URL，并在 summary 中说明它代表的信号类型。"
            )

        return {
            "model": self._config.model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "你是开发者灵感调研 Agent。ConceptDrift 是生成报告的本地应用名，"
                        "不是被调研产品、机会、创业项目或开源项目，除非用户方向明确要求调研它。"
                        "你必须根据请求模式生成可执行的项目灵感报告；"
                        "guided 模式围绕用户方向，yolo 模式先自主选择方向。"
                        "title、summary、markdown、tags 和 sources 必须围绕实际调研方向，"
                        "不要把 ConceptDrift 当作被调研产品、报告主题、来源或标签。"
                        "只输出符合 JSON schema 的结构化数据。"
                    ),
                },
                {
                    "role": "user",
                    "content": task_instruction,
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "conceptdrift_report",
                    "strict": True,
                    "schema": OPENAI_REPORT_JSON_SCHEMA,
                }
            },
            "max_output_tokens": 5000,
        }

    async def _post_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            response = await self._client.post(self._responses_url(), headers=headers, json=payload)
        else:
            timeout = httpx.Timeout(self._config.timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self._responses_url(), headers=headers, json=payload)

        if response.status_code >= 400:
            message = self._error_message(response)
            raise RuntimeError(f"OpenAI API request failed ({response.status_code}): {message}")
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI API returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("OpenAI API returned an unexpected response shape")
        return data

    def _responses_url(self) -> str:
        base_url = self._config.base_url.strip().rstrip("/")
        if base_url.endswith("/responses"):
            return base_url
        if base_url.endswith("/v1"):
            return f"{base_url}/responses"
        if "api.openai.com" in base_url:
            return f"{base_url}/v1/responses"
        return f"{base_url}/responses"

    def _error_message(self, response: httpx.Response) -> str:
        try:
            body = response.json()
        except json.JSONDecodeError:
            return response.text[:500] or "unknown error"
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                return error["message"]
            if isinstance(body.get("message"), str):
                return body["message"]
        return response.text[:500] or "unknown error"

    def _extract_output_text(self, payload: dict[str, Any]) -> str:
        direct_text = payload.get("output_text")
        if isinstance(direct_text, str) and direct_text.strip():
            return direct_text

        fragments: list[str] = []
        for output_item in payload.get("output", []):
            if not isinstance(output_item, dict):
                continue
            for content_item in output_item.get("content", []):
                if not isinstance(content_item, dict):
                    continue
                if content_item.get("type") in {"output_text", "text"}:
                    text = content_item.get("text")
                    if isinstance(text, str):
                        fragments.append(text)
                refusal = content_item.get("refusal")
                if isinstance(refusal, str) and refusal.strip():
                    raise RuntimeError(f"OpenAI refused the request: {refusal}")

        text = "\n".join(fragments).strip()
        if not text:
            raise RuntimeError("OpenAI API response did not contain output text")
        return text

    def _parse_report_text(self, text: str) -> GeneratedReport:
        try:
            raw_payload = json.loads(text)
            parsed = _OpenAIReportPayload.model_validate(raw_payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError("OpenAI API returned a report that did not match the expected schema") from exc

        required_scores = ["technical_feasibility", "market_novelty", "business_potential"]
        scores = {
            score_name: self._score(parsed.scores.get(score_name, 0))
            for score_name in required_scores
        }
        tags = [tag.strip() for tag in parsed.tags if tag.strip()]
        sources = [
            GeneratedSource(
                source=item.source.strip() or "OpenAI",
                title=item.title.strip() or item.source.strip() or "OpenAI signal",
                url=item.url.strip() or "https://openai.com",
                summary=item.summary.strip(),
                signal_score=self._score(item.signal_score),
            )
            for item in parsed.sources
        ]
        if not sources:
            raise RuntimeError("OpenAI API returned a report without sources")

        return GeneratedReport(
            title=parsed.title.strip(),
            summary=parsed.summary.strip(),
            markdown=parsed.markdown.strip(),
            scores=scores,
            tags=list(dict.fromkeys(tags)),
            sources=sources,
        )

    def _score(self, value: int) -> int:
        return max(0, min(100, int(value)))


def _openai_config(settings: Settings) -> OpenAIProviderConfig:
    return OpenAIProviderConfig(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
        tracing_disabled=settings.openai_tracing_disabled,
        codex_agent_timeout_seconds=settings.codex_agent_timeout_seconds,
        codex_agent_network_enabled=settings.codex_agent_network_enabled,
        codex_agent_web_search_mode=settings.codex_agent_web_search_mode,
    )


def build_provider(settings: Settings | str) -> InspirationProvider:
    if isinstance(settings, str):
        active_settings = Settings(agent_provider=settings)
        normalized = active_settings.agent_provider.strip().lower()
        config = _openai_config(active_settings)
    else:
        normalized = settings.agent_provider.strip().lower()
        config = _openai_config(settings)

    if normalized in {"mock", ""}:
        return MockInspirationProvider()
    if normalized == "response":
        return OpenAIResponsesProvider(config)
    if normalized == "codex":
        return OpenAIAgentsProvider(config)
    raise ValueError(f"Unsupported agent provider: {normalized}")


OpenAIInspirationProvider = OpenAIResponsesProvider
