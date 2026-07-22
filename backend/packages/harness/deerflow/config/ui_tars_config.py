"""Configuration for the optional local UI-TARS desktop operator."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class UITarsConfig(BaseModel):
    """A single-step UI-TARS organ controlled by the DeerFlow lead agent.

    The operator is intentionally not an Agent TARS runtime.  It accepts one
    bounded visual step per DeerFlow tool call and is disabled by default.
    """

    enabled: bool = Field(default=False, description="Expose the native UI-TARS fallback tool.")
    mode: Literal["managed", "connect"] = Field(
        default="managed",
        description="Start the bundled local operator or connect to an already running loopback operator.",
    )
    endpoint: str = Field(default="http://127.0.0.1:9137", description="Loopback URL of the local operator.")
    model: str = Field(default="", description="Exact UI-TARS model/deployment identifier used in receipts.")
    api_base: str = Field(default="", description="OpenAI-compatible UI-TARS model base URL.")
    api_key_env: str = Field(default="UI_TARS_API_KEY", description="Environment variable holding the model API key.")
    request_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    screenshot_privacy: Literal["pixelated", "blocked"] = Field(
        default="pixelated",
        description="Only privacy-transformed screenshots may leave the local operator; blocked disables model steps.",
    )
    pixelation_block_size: int = Field(
        default=24,
        ge=16,
        le=128,
        description="Minimum whole-screen pixelation block used before a screenshot reaches a model.",
    )

    @field_validator("endpoint")
    @classmethod
    def _loopback_endpoint_only(cls, value: str) -> str:
        from urllib.parse import urlsplit

        endpoint = value.strip().rstrip("/")
        parsed = urlsplit(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("ui_tars.endpoint must be a loopback HTTP URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("ui_tars.endpoint cannot contain credentials, a query, or a fragment")
        return endpoint

    @field_validator("api_base")
    @classmethod
    def _model_endpoint_policy(cls, value: str) -> str:
        from urllib.parse import urlsplit

        endpoint = value.strip().rstrip("/")
        if not endpoint:
            return endpoint
        parsed = urlsplit(endpoint)
        if parsed.scheme == "https":
            return endpoint
        if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
            return endpoint
        raise ValueError("ui_tars.api_base must use HTTPS or loopback HTTP")

    @field_validator("api_key_env")
    @classmethod
    def _api_key_env_name(cls, value: str) -> str:
        import re

        name = value.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", name):
            raise ValueError("ui_tars.api_key_env must be an uppercase environment-variable name")
        return name
