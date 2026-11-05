"""集中配置：全部来自环境变量（可被 repo 根 .env 覆盖）。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "rider-platform-api"
    api_prefix: str = "/api/v1"
    env: str = "dev"
    # 允许跨域来源（逗号分隔；* = 任意，仅适合本地演示/内网）
    cors_origins: str = "*"

    # 存储
    database_url: str = "postgresql://rider:rider_dev_password@127.0.0.1:55432/rider"
    cache_url: str = "redis://127.0.0.1:56379/0"
    db_pool_min: int = 1
    db_pool_max: int = 20

    auto_init: bool = True
    auto_seed: bool = True

    # 安全
    jwt_secret: str = "dev-only-jwt-secret-change-me"
    jwt_ttl_seconds: int = 12 * 3600
    vault_key: str = "dev-only-vault-key-change-me-32bytes!!"
    webhook_secret: str = "dev-only-webhook-secret"
    webhook_endpoint: str = ""
    webhook_backoff_base_seconds: float = 2.0
    webhook_max_attempts: int = 6

    # LLM（可插拔；mock 为确定性本地实现，不联网）
    llm_mode: Literal["mock", "openai"] = "mock"
    llm_base_url: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_timeout_seconds: float = 5.0

    # 政策检索
    policy_min_score: float = 0.30
    policy_top_k: int = 3

    # 保留期
    retention_unhired_days: int = 90
    retention_conversation_days: int = 30
    retention_minor_hours: int = 24

    @property
    def init_sql_path(self) -> Path:
        return Path(__file__).resolve().parent / "db" / "init.sql"


@lru_cache
def get_settings() -> Settings:
    return Settings()
