from functools import lru_cache
from pathlib import Path
import re
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="sqlite:///./data/conceptdrift.sqlite3",
        validation_alias="CONCEPTDRIFT_DATABASE_URL",
    )
    agent_provider: str = Field(default="mock", validation_alias="CONCEPTDRIFT_AGENT_PROVIDER")
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        validation_alias="CONCEPTDRIFT_CORS_ORIGINS",
    )
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", validation_alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-5", validation_alias="OPENAI_MODEL")
    openai_timeout_seconds: float = Field(default=90.0, validation_alias="OPENAI_TIMEOUT_SECONDS")
    openai_tracing_disabled: bool = Field(
        default=True,
        validation_alias="CONCEPTDRIFT_OPENAI_TRACING_DISABLED",
    )
    codex_agent_timeout_seconds: float = Field(
        default=120.0,
        validation_alias="CONCEPTDRIFT_CODEX_AGENT_TIMEOUT_SECONDS",
    )
    codex_agent_network_enabled: bool = Field(
        default=True,
        validation_alias="CONCEPTDRIFT_CODEX_AGENT_NETWORK_ENABLED",
    )
    codex_agent_web_search_mode: str = Field(
        default="live",
        validation_alias="CONCEPTDRIFT_CODEX_AGENT_WEB_SEARCH_MODE",
    )
    config_env_path: str = Field(default=".env", validation_alias="CONCEPTDRIFT_CONFIG_ENV_PATH")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


CONFIG_ENV_KEYS = {
    "agent_provider": "CONCEPTDRIFT_AGENT_PROVIDER",
    "openai_api_key": "OPENAI_API_KEY",
    "openai_base_url": "OPENAI_BASE_URL",
    "openai_model": "OPENAI_MODEL",
    "openai_timeout_seconds": "OPENAI_TIMEOUT_SECONDS",
    "openai_tracing_disabled": "CONCEPTDRIFT_OPENAI_TRACING_DISABLED",
    "codex_agent_timeout_seconds": "CONCEPTDRIFT_CODEX_AGENT_TIMEOUT_SECONDS",
    "codex_agent_network_enabled": "CONCEPTDRIFT_CODEX_AGENT_NETWORK_ENABLED",
    "codex_agent_web_search_mode": "CONCEPTDRIFT_CODEX_AGENT_WEB_SEARCH_MODE",
}


def masked_secret(value: str) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}...{value[-4:]}"


def merged_settings(current: Settings, updates: dict[str, Any]) -> Settings:
    data = current.model_dump()
    data.update(updates)
    return Settings(**data)


def persist_settings(settings: Settings, updates: dict[str, Any]) -> None:
    env_updates = {
        CONFIG_ENV_KEYS[field]: _format_env_value(value)
        for field, value in updates.items()
        if field in CONFIG_ENV_KEYS
    }
    if not env_updates:
        return

    path = _env_path(settings.config_env_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    next_lines: list[str] = []
    pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")

    for line in lines:
        match = pattern.match(line)
        if match and match.group(1) in env_updates:
            key = match.group(1)
            next_lines.append(f"{key}={env_updates[key]}")
            seen.add(key)
        else:
            next_lines.append(line)

    missing = [key for key in env_updates if key not in seen]
    if missing and next_lines and next_lines[-1].strip():
        next_lines.append("")
    for key in missing:
        next_lines.append(f"{key}={env_updates[key]}")

    path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")


def _env_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _format_env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if not text:
        return ""
    if re.search(r"\s|#|['\"]", text):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text
