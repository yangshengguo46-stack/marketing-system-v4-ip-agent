"""Operator configuration for the bundled local MineContext source."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class MineContextConfig(BaseModel):
    """Startup-only limits for per-owner MineContext sidecars.

    The Personal-IP product enables the bundled source for new owners by
    default. An owner can still disable it persistently from Settings.
    """

    enabled: bool = True
    auto_enable_new_owners: bool = True
    source_path: str = "third_party/volcengine/MineContext"
    runtime_python: str | None = None
    host: str = "127.0.0.1"
    port_start: int = Field(default=17400, ge=1024, le=65535)
    port_end: int = Field(default=17500, ge=1024, le=65535)
    start_timeout_seconds: float = Field(default=120.0, ge=1.0, le=120.0)
    stop_timeout_seconds: float = Field(default=5.0, ge=0.1, le=30.0)
    max_owner_processes: int = Field(default=2, ge=1, le=32)
    default_retention_days: int = Field(default=30, ge=1, le=365)
    max_retention_days: int = Field(default=365, ge=1, le=3650)
    min_screen_interval_seconds: int = Field(default=60, ge=60, le=86_400)
    max_evidence_records: int = Field(default=2000, ge=1, le=100_000)
    max_sync_results: int = Field(default=20, ge=1, le=100)
    vlm_base_url_env: str = "MINECONTEXT_VLM_BASE_URL"
    vlm_api_key_env: str = "MINECONTEXT_VLM_API_KEY"
    vlm_model_env: str = "MINECONTEXT_VLM_MODEL"
    embedding_base_url_env: str = "MINECONTEXT_EMBEDDING_BASE_URL"
    embedding_api_key_env: str = "MINECONTEXT_EMBEDDING_API_KEY"
    embedding_model_env: str = "MINECONTEXT_EMBEDDING_MODEL"
    fallback_api_key_env: str = "VOLCENGINE_API_KEY"
    default_vlm_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    default_vlm_model: str = "doubao-seed-2-0-pro-260215"
    default_embedding_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    default_embedding_model: str = "doubao-embedding-vision-250615"
    vlm_provider: str = "doubao"
    embedding_provider: str = "doubao"

    @field_validator("host")
    @classmethod
    def require_loopback(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("MineContext host must be a loopback address")
        return normalized

    @field_validator(
        "vlm_base_url_env",
        "vlm_api_key_env",
        "vlm_model_env",
        "embedding_base_url_env",
        "embedding_api_key_env",
        "embedding_model_env",
        "fallback_api_key_env",
    )
    @classmethod
    def validate_environment_name(cls, value: str) -> str:
        value = value.strip()
        if not value or not value.replace("_", "A").isalnum() or not value[0].isalpha():
            raise ValueError("MineContext credential settings must name explicit environment variables")
        return value

    @field_validator("vlm_provider", "embedding_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"doubao", "openai"}:
            raise ValueError("MineContext provider must be 'doubao' or 'openai'")
        return normalized

    @model_validator(mode="after")
    def validate_ranges(self) -> MineContextConfig:
        if self.port_end < self.port_start:
            raise ValueError("port_end must be greater than or equal to port_start")
        if self.default_retention_days > self.max_retention_days:
            raise ValueError("default_retention_days cannot exceed max_retention_days")
        return self
