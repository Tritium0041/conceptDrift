from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


DEFAULT_SOURCES = ["github_trending", "hackernews", "product_hunt", "last30days"]


class GenerateTaskRequest(BaseModel):
    direction: str = Field(default="随机开发者工具灵感", max_length=300)
    sources: list[str] = Field(default_factory=lambda: DEFAULT_SOURCES.copy(), min_length=1)
    depth: Literal["quick", "standard", "deep"] = "standard"
    mode: Literal["guided", "yolo"] = "guided"
    checkpoint: dict[str, Any] = Field(default_factory=dict, exclude=True)


class TaskOut(BaseModel):
    id: str
    direction: str
    sources: list[str]
    depth: str
    mode: str
    status: str
    progress: int
    stage: str
    error: str | None
    report_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int
    limit: int
    offset: int


class SourceItemOut(BaseModel):
    id: int
    source: str
    title: str
    url: str
    summary: str
    signal_score: int

    model_config = {"from_attributes": True}


class ReportOut(BaseModel):
    id: int
    title: str
    summary: str
    markdown: str
    scores: dict[str, int]
    tags: list[str]
    archived: bool
    sources: list[SourceItemOut]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportListItem(BaseModel):
    id: int
    title: str
    summary: str
    scores: dict[str, int]
    tags: list[str]
    archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportListOut(BaseModel):
    items: list[ReportListItem]
    total: int
    limit: int
    offset: int


class HealthOut(BaseModel):
    status: str
    provider: str
    database: str


ProviderName = Literal["mock", "codex", "response"]


class AppConfigOut(BaseModel):
    agent_provider: ProviderName
    openai_api_key_configured: bool
    openai_api_key_masked: str | None
    openai_base_url: str
    openai_model: str
    openai_timeout_seconds: float
    openai_tracing_disabled: bool
    codex_agent_timeout_seconds: float
    codex_agent_network_enabled: bool
    codex_agent_web_search_mode: str


class AppConfigUpdate(BaseModel):
    agent_provider: ProviderName
    openai_api_key: str | None = Field(default=None, max_length=500)
    clear_openai_api_key: bool = False
    openai_base_url: str = Field(default="https://api.openai.com/v1", max_length=500)
    openai_model: str = Field(default="gpt-5", max_length=100)
    openai_timeout_seconds: float = Field(default=90.0, ge=1, le=600)
    openai_tracing_disabled: bool = True
    codex_agent_timeout_seconds: float = Field(default=120.0, ge=1, le=600)
    codex_agent_network_enabled: bool = True
    codex_agent_web_search_mode: str = Field(default="live", pattern="^(disabled|cached|live)$")
