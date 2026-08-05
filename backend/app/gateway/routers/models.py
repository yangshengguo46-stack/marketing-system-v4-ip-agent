import hashlib
import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.gateway.deps import get_config
from deerflow.config.app_config import AppConfig
from deerflow.config.model_config import ModelConfig

router = APIRouter(prefix="/api", tags=["models"])


_EFFECTIVE_CONFIG_SCHEMA = "deerflow-model-effective-config-v1"
_NON_EFFECTIVE_MODEL_FIELDS = frozenset({"display_name", "description"})
_SENSITIVE_CONFIG_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "auth_token",
        "access_token",
        "refresh_token",
        "bearer_token",
        "client_secret",
        "cookie",
        "cookies",
        "credential",
        "credentials",
        "default_headers",
        "extra_headers",
        "headers",
        "key",
        "password",
        "passphrase",
        "private_key",
        "proxy_authorization",
        "secret",
        "secret_key",
        "token",
    }
)
_SENSITIVE_KEY_PARTS = frozenset(
    {
        "cookie",
        "cookies",
        "credential",
        "credentials",
        "passwd",
        "password",
        "secret",
    }
)


def _is_sensitive_config_key(key: str) -> bool:
    """Return whether a model-config key can contain authentication material.

    Matching is deliberately key-aware instead of using a broad ``"token" in
    key`` test: inference parameters such as ``max_tokens`` and
    ``tokenizer_model_name`` are part of the effective configuration receipt.
    """

    snake_key = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    normalized = re.sub(r"[^a-z0-9]+", "_", snake_key.casefold()).strip("_")
    compact = normalized.replace("_", "")
    if normalized in _SENSITIVE_CONFIG_KEYS or compact in _SENSITIVE_CONFIG_KEYS:
        return True
    if _SENSITIVE_KEY_PARTS.intersection(normalized.split("_")):
        return True
    return normalized.endswith(
        (
            "_api_key",
            "_apikey",
            "_access_token",
            "_auth_token",
            "_bearer_token",
            "_client_secret",
            "_private_key",
            "_refresh_token",
            "_secret_key",
            "_token",
        )
    )


def _strip_sensitive_config(value: Any) -> Any:
    """Recursively remove credential-bearing keys from a JSON-safe value."""

    if isinstance(value, dict):
        return {str(key): _strip_sensitive_config(child) for key, child in value.items() if not _is_sensitive_config_key(str(key))}
    if isinstance(value, list):
        return [_strip_sensitive_config(child) for child in value]
    return value


def _effective_model_config_projection(model: ModelConfig) -> dict[str, Any]:
    """Build the stable, credential-free projection sealed by the receipt.

    ``ModelConfig`` allows provider-specific extras, so a fixed allowlist would
    omit parameters such as ``top_p`` or ``reasoning_effort`` that materially
    affect generation.  Start from the exact config loaded by the Gateway,
    remove presentation-only metadata, and recursively discard authentication
    material.  The projection is never returned by the API.
    """

    raw = model.model_dump(mode="json", exclude_none=False)
    for field_name in _NON_EFFECTIVE_MODEL_FIELDS:
        raw.pop(field_name, None)
    projection = _strip_sensitive_config(raw)
    if not isinstance(projection, dict):  # pragma: no cover - model_dump contract
        raise TypeError("ModelConfig projection must be a mapping")
    return projection


def _effective_model_config_sha256(model: ModelConfig) -> str:
    """Seal the current effective model configuration without exposing it."""

    receipt = {
        "schema": _EFFECTIVE_CONFIG_SCHEMA,
        "config": _effective_model_config_projection(model),
    }
    canonical = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class ModelResponse(BaseModel):
    """Response model for model information."""

    name: str = Field(..., description="Unique identifier for the model")
    model: str = Field(..., description="Actual provider model identifier")
    display_name: str | None = Field(None, description="Human-readable name")
    description: str | None = Field(None, description="Model description")
    supports_thinking: bool = Field(default=False, description="Whether model supports thinking mode")
    supports_reasoning_effort: bool = Field(default=False, description="Whether model supports reasoning effort")
    supports_vision: bool = Field(default=False, description="Whether model supports image inputs")
    temperature: float | None = Field(default=None, description="Effective configured sampling temperature")
    max_tokens: int | None = Field(default=None, description="Effective configured maximum output tokens")
    effective_config_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256 receipt for the Gateway's credential-free effective model configuration",
    )


def _model_response(model: ModelConfig) -> ModelResponse:
    """Create the public model view and its effective-config receipt."""

    projection = _effective_model_config_projection(model)
    return ModelResponse(
        name=model.name,
        model=model.model,
        display_name=model.display_name,
        description=model.description,
        supports_thinking=model.supports_thinking,
        supports_reasoning_effort=model.supports_reasoning_effort,
        supports_vision=model.supports_vision,
        temperature=projection.get("temperature"),
        max_tokens=projection.get("max_tokens"),
        effective_config_sha256=_effective_model_config_sha256(model),
    )


class TokenUsageResponse(BaseModel):
    """Token usage display configuration."""

    enabled: bool = Field(default=False, description="Whether token usage display is enabled")


class ModelsListResponse(BaseModel):
    """Response model for listing all models."""

    models: list[ModelResponse]
    token_usage: TokenUsageResponse


@router.get(
    "/models",
    response_model=ModelsListResponse,
    summary="List All Models",
    description="Retrieve a list of all available AI models configured in the system.",
)
async def list_models(config: AppConfig = Depends(get_config)) -> ModelsListResponse:
    """List all available models from configuration.

    Returns model information suitable for frontend display,
    excluding sensitive fields like API keys and internal configuration.

    Returns:
        A list of all configured models with their metadata and token usage display settings.

    Example Response:
        ```json
        {
            "models": [
                {
                    "name": "gpt-4",
                    "model": "gpt-4",
                    "display_name": "GPT-4",
                    "description": "OpenAI GPT-4 model",
                    "supports_thinking": false,
                    "supports_reasoning_effort": false
                },
                {
                    "name": "claude-3-opus",
                    "model": "claude-3-opus",
                    "display_name": "Claude 3 Opus",
                    "description": "Anthropic Claude 3 Opus model",
                    "supports_thinking": true,
                    "supports_reasoning_effort": false
                }
            ],
            "token_usage": {
                "enabled": true
            }
        }
        ```
    """
    models = [_model_response(model) for model in config.models]
    return ModelsListResponse(
        models=models,
        token_usage=TokenUsageResponse(enabled=config.token_usage.enabled),
    )


@router.get(
    "/models/{model_name}",
    response_model=ModelResponse,
    summary="Get Model Details",
    description="Retrieve detailed information about a specific AI model by its name.",
)
async def get_model(model_name: str, config: AppConfig = Depends(get_config)) -> ModelResponse:
    """Get a specific model by name.

    Args:
        model_name: The unique name of the model to retrieve.

    Returns:
        Model information if found.

    Raises:
        HTTPException: 404 if model not found.

    Example Response:
        ```json
        {
            "name": "gpt-4",
            "display_name": "GPT-4",
            "description": "OpenAI GPT-4 model",
            "supports_thinking": false
        }
        ```
    """
    model = config.get_model_config(model_name)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

    return _model_response(model)
