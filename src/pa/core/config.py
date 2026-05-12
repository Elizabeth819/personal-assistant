"""Centralized configuration via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PA_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "dev"
    log_level: str = "INFO"
    model: str = "claude-opus-4-7"
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    data_dir: Path = Path("./data")
    db_url: str = "sqlite+aiosqlite:///./data/pa.db"

    host: str = "127.0.0.1"
    port: int = 8765

    claude_mem_dir: Path = Path.home() / ".claude/plugins/data/claude-mem-thedotmack"

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-01-preview"
    azure_realtime_deployment: str = "gpt-4o-realtime-preview"
    azure_chat_deployment: str = "gpt-4.1"
    azure_whisper_deployment: str = "whisper"

    tasker_webhook: str = ""
    ios_shortcuts_webhook: str = ""
    wechat_gateway_url: str = ""

    ios_device_udid: str = ""
    ios_device_autorun: bool = False


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
