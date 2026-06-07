from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol


StreamCallback = Callable[[str], Awaitable[None]]
logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class AgentRuntimeConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float
    tracing_disabled: bool


@dataclass(frozen=True)
class AgentRunSpec:
    name: str
    instructions: str
    input: str
    tools: list[Any] = field(default_factory=list)
    max_turns: int = 8
    stream: bool = True


class AgentRuntime(Protocol):
    async def run(self, spec: AgentRunSpec, on_event: StreamCallback | None = None) -> str:
        pass


class AgentsSdkRuntime:
    def __init__(self, config: AgentRuntimeConfig) -> None:
        self._config = config

    async def run(self, spec: AgentRunSpec, on_event: StreamCallback | None = None) -> str:
        from agents import Agent, ModelSettings, Runner
        from agents.models.openai_provider import OpenAIProvider
        from agents.run_config import RunConfig

        logger.info(
            "ConceptDrift agent run starting: name=%s stream=%s tools=%s",
            spec.name,
            spec.stream,
            len(spec.tools),
        )
        model_provider = OpenAIProvider(
            api_key=self._config.api_key,
            base_url=self._config.base_url,
            use_responses=True,
        )
        run_config = RunConfig(
            model=self._config.model,
            model_provider=model_provider,
            model_settings=ModelSettings(max_tokens=5000),
            tracing_disabled=self._config.tracing_disabled,
            workflow_name="ConceptDrift Agent Workflow",
        )
        agent = Agent(
            name=spec.name,
            instructions=spec.instructions,
            model=self._config.model,
            tools=spec.tools,
        )

        if not spec.stream:
            result = await Runner.run(
                agent,
                spec.input,
                max_turns=spec.max_turns,
                run_config=run_config,
            )
            logger.info("ConceptDrift agent run completed: name=%s", spec.name)
            return str(result.final_output)

        result = Runner.run_streamed(
            agent,
            spec.input,
            max_turns=spec.max_turns,
            run_config=run_config,
        )
        event_count = 0
        async for event in result.stream_events():
            event_count += 1
            if on_event is not None and event_count % 4 == 0:
                await on_event(self._event_name(event))
        logger.info(
            "ConceptDrift agent run completed: name=%s stream_events=%s",
            spec.name,
            event_count,
        )
        return str(result.final_output)

    def _event_name(self, event: Any) -> str:
        return str(getattr(event, "type", event.__class__.__name__))


@dataclass(frozen=True)
class CodexResearchConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float
    network_access_enabled: bool = True
    web_search_mode: str = "live"
    working_directory: str | None = None


class CodexResearchRuntime:
    def __init__(self, config: CodexResearchConfig) -> None:
        self._config = config

    async def run(
        self,
        prompt: str,
        output_schema: dict[str, Any] | None = None,
    ) -> str:
        from agents.extensions.experimental.codex import (
            Codex,
            CodexOptions,
            ThreadOptions,
            TurnOptions,
        )

        logger.info(
            "ConceptDrift Codex research run starting: model=%s timeout=%s web_search_mode=%s",
            self._config.model,
            self._config.timeout_seconds,
            self._config.web_search_mode,
        )
        codex = Codex(
            CodexOptions(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
            )
        )
        with self._working_directory() as working_directory:
            thread = codex.start_thread(
                ThreadOptions(
                    model=self._config.model,
                    sandbox_mode="read-only",
                    working_directory=working_directory,
                    skip_git_repo_check=True,
                    model_reasoning_effort="xhigh",
                    network_access_enabled=self._config.network_access_enabled,
                    web_search_mode=self._web_search_mode(),
                    approval_policy="never",
                )
            )
            turn = await thread.run(
                prompt,
                TurnOptions(
                    output_schema=output_schema,
                    idle_timeout_seconds=self._config.timeout_seconds,
                ),
            )
        logger.info("ConceptDrift Codex research run completed")
        return turn.final_response

    @contextmanager
    def _working_directory(self) -> Iterator[str]:
        if self._config.working_directory:
            path = Path(self._config.working_directory).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            yield str(path)
            return
        with TemporaryDirectory(prefix="conceptdrift-codex-") as workdir:
            yield workdir

    def _web_search_mode(self) -> str:
        if self._config.web_search_mode in {"disabled", "cached", "live"}:
            return self._config.web_search_mode
        return "live"
