from __future__ import annotations

from app.source_tools import (
    build_source_research_target,
    fallback_signal,
    score,
    source_home_url,
    source_label,
)


def test_source_research_target_describes_public_source_without_fetching() -> None:
    target = build_source_research_target("github_trending")

    assert target.source_id == "github_trending"
    assert target.source == "GitHub Trending"
    assert target.url == "https://github.com/trending"
    assert "Research recent GitHub repositories" in target.guidance


def test_last30days_target_directs_codex_to_user_installed_skill() -> None:
    target = build_source_research_target("last30days")

    assert target.source_id == "last30days"
    assert target.source == "Last30Days"
    assert target.url == "https://github.com/mvanhorn/last30days-skill"
    assert "user-installed Codex skill `last30days`" in target.guidance
    assert "setup is required" in target.guidance


def test_unknown_source_gets_safe_defaults() -> None:
    target = build_source_research_target("indie_blogs")

    assert target.source == "Indie Blogs"
    assert target.url == "https://example.com"
    assert "public web signals" in target.guidance


def test_fallback_signal_is_bounded_and_points_to_public_home() -> None:
    signal = fallback_signal("hackernews", "dev tool", "bad JSON")

    assert signal.source == source_label("hackernews")
    assert signal.url == source_home_url("hackernews")
    assert signal.signal_score == 35
    assert "Codex agent 未能返回可解析" in signal.summary


def test_score_clamps_signal_score() -> None:
    assert score(120) == 100
    assert score(-3) == 0
    assert score(72) == 72
