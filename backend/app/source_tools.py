from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SOURCE_LABELS = {
    "github_trending": "GitHub Trending",
    "hackernews": "Hacker News",
    "product_hunt": "Product Hunt",
    "reddit": "Reddit",
}

SOURCE_HOME_URLS = {
    "github_trending": "https://github.com/trending",
    "hackernews": "https://news.ycombinator.com",
    "product_hunt": "https://www.producthunt.com",
    "reddit": "https://www.reddit.com/r/programming",
}

SOURCE_RESEARCH_GUIDANCE = {
    "github_trending": (
        "Research recent GitHub repositories, trending projects, commits, issues, and ecosystem "
        "activity related to the direction. Prefer repository pages and official project docs."
    ),
    "hackernews": (
        "Research recent Hacker News stories and discussions related to the direction. Prefer "
        "news.ycombinator.com item pages and linked primary sources."
    ),
    "product_hunt": (
        "Research recent Product Hunt launches and adjacent products related to the direction. "
        "Prefer Product Hunt launch pages and product websites."
    ),
    "reddit": (
        "Research recent Reddit developer discussions related to the direction, especially "
        "r/programming and adjacent developer communities. Prefer public thread URLs."
    ),
}


@dataclass(frozen=True)
class SourceSignal:
    source_id: str
    source: str
    title: str
    url: str
    summary: str
    signal_score: int


@dataclass(frozen=True)
class SourceSnapshot:
    source_id: str
    source: str
    url: str
    signals: list[SourceSignal]
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source": self.source,
            "url": self.url,
            "signals": [asdict(signal) for signal in self.signals],
            "error": self.error,
        }


@dataclass(frozen=True)
class SourceResearchTarget:
    source_id: str
    source: str
    url: str
    guidance: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def source_label(source_id: str) -> str:
    return SOURCE_LABELS.get(source_id, source_id.replace("_", " ").title())


def source_home_url(source_id: str) -> str:
    return SOURCE_HOME_URLS.get(source_id, "https://example.com")


def source_research_guidance(source_id: str) -> str:
    return SOURCE_RESEARCH_GUIDANCE.get(
        source_id,
        "Research current public web signals related to the direction. Prefer primary sources.",
    )


def build_source_research_target(source_id: str) -> SourceResearchTarget:
    return SourceResearchTarget(
        source_id=source_id,
        source=source_label(source_id),
        url=source_home_url(source_id),
        guidance=source_research_guidance(source_id),
    )


def fallback_signal(source_id: str, direction: str, reason: str) -> SourceSignal:
    label = source_label(source_id)
    return SourceSignal(
        source_id=source_id,
        source=label,
        title=f"{label}: {direction.strip() or 'developer tools'}",
        url=source_home_url(source_id),
        summary=f"Codex agent 未能返回可解析的实时条目，原因：{reason}。该来源仍可作为后续人工复核入口。",
        signal_score=35,
    )


def score(value: int) -> int:
    return max(0, min(100, int(value)))
