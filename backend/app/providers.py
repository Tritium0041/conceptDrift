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
    AgentRunSpec,
    AgentRuntime,
    AgentRuntimeConfig,
    AgentsSdkRuntime,
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
        direction = request.direction.strip() or "随机开发者工具灵感"
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
        scores = {
            "technical_feasibility": feasibility,
            "market_novelty": novelty,
            "business_potential": 72 if request.depth != "quick" else 64,
        }
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
        runtime: AgentRuntime | None = None,
        research_runtime: ResearchRuntime | None = None,
    ) -> None:
        self._config = config
        self._runtime = runtime or AgentsSdkRuntime(
            AgentRuntimeConfig(
                api_key=config.api_key,
                base_url=config.base_url,
                model=config.model,
                timeout_seconds=config.timeout_seconds,
                tracing_disabled=config.tracing_disabled,
            )
        )
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

        direction = request.direction.strip() or "随机开发者工具灵感"
        await progress(8, "启动 OpenAI Agents SDK 与 Codex 调研")

        await progress(18, "Codex agent 并发调研外部信号")
        source_results = await self._run_source_agents(
            request=request,
            progress=progress,
        )
        snapshots = [result["snapshot"] for result in source_results]
        source_analyses = [
            {"source": result["snapshot"].source, "analysis": result["analysis"]}
            for result in source_results
        ]

        await progress(65, "Codex agent 复核技术可行性")
        technical_analysis = await self._research_runtime.run(
            self._technical_research_prompt(
                direction=direction,
                depth=request.depth,
                source_analyses=source_analyses,
                snapshots=snapshots,
            )
        )

        await progress(82, "Orchestrator Agent 汇总报告")
        final_text = await self._runtime.run(
            AgentRunSpec(
                name="ConceptDrift Orchestrator Agent",
                instructions=self._orchestrator_instructions(),
                input=json.dumps(
                    {
                        "direction": direction,
                        "depth": request.depth,
                        "requested_sources": request.sources,
                        "source_snapshots": [snapshot.as_dict() for snapshot in snapshots],
                        "source_analyses": source_analyses,
                        "codex_technical_analysis": technical_analysis,
                        "required_json_schema": OPENAI_REPORT_JSON_SCHEMA,
                    },
                    ensure_ascii=False,
                ),
                max_turns=10,
                stream=True,
            ),
            on_event=lambda event: progress(88, f"Orchestrator 流式事件：{event}"),
        )

        await progress(95, "校验多 Agent 报告结构")
        return self._parse_report_text(final_text)

    async def _run_source_agents(
        self,
        request: GenerateTaskRequest,
        progress: ProgressCallback,
    ) -> list[dict[str, Any]]:
        direction = request.direction.strip() or "随机开发者工具灵感"

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
            return {"snapshot": snapshot, "analysis": analysis}

        return list(await asyncio.gather(*(run_one(source_id) for source_id in request.sources)))

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
                    "signals. Do not call or rely on ConceptDrift backend source-scraping APIs. "
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

    def _orchestrator_instructions(self) -> str:
        return (
            "你是 ConceptDrift 的中心编排 Agent。你必须综合 source_analyses、"
            "source_snapshots 和 codex_technical_analysis，生成最终开发者灵感报告。"
            "只返回 JSON，不要 Markdown code fence，不要解释。JSON 必须符合输入中的 "
            "required_json_schema。markdown 字段内部必须是完整 Markdown 报告，并包含："
            "摘要、核心概念、技术可行性、市场新颖性、商业潜力、灵感来源、MVP 建议。"
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
        payload = self._request_payload(request)
        await progress(35, "OpenAI Agent 正在调研与生成结构化报告")

        response_payload = await self._post_response(payload)
        await progress(75, "解析 OpenAI Agent 返回结果")

        text = self._extract_output_text(response_payload)
        report = self._parse_report_text(text)
        await progress(90, "校验报告结构并准备入库")
        return report

    def _request_payload(self, request: GenerateTaskRequest) -> dict[str, Any]:
        direction = request.direction.strip() or "随机开发者工具灵感"
        source_list = ", ".join(request.sources)
        depth_instruction = {
            "quick": "输出更短，突出可快速验证的 MVP。",
            "standard": "保持完整但避免冗长，覆盖调研、判断和 MVP 路线。",
            "deep": "输出更深入，补充风险、差异化和商业化判断。",
        }.get(request.depth, "保持标准深度。")

        return {
            "model": self._config.model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "你是 ConceptDrift 的开发者灵感调研 Agent。"
                        "你必须根据用户给定方向生成可执行的项目灵感报告，"
                        "只输出符合 JSON schema 的结构化数据。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"探索方向：{direction}\n"
                        f"信号源标识：{source_list}\n"
                        f"调研深度：{request.depth}\n"
                        f"{depth_instruction}\n\n"
                        "要求：\n"
                        "1. title 使用中文或中英混合，明确项目方向。\n"
                        "2. summary 用 2-4 句话说明机会点。\n"
                        "3. markdown 生成完整 Markdown 报告，必须包含摘要、核心概念、"
                        "技术可行性、市场新颖性、商业潜力、灵感来源、MVP 建议。\n"
                        "4. scores 的三个分数必须是 0-100 的整数。\n"
                        "5. sources 至少覆盖用户选择的信号源；无法实时访问某来源时，"
                        "给出可追溯的公开主页 URL，并在 summary 中说明它代表的信号类型。"
                    ),
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
