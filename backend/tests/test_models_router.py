import hashlib
import json
from types import SimpleNamespace

import pytest

from app.gateway.routers.models import (
    _EFFECTIVE_CONFIG_SCHEMA,
    _effective_model_config_projection,
    _effective_model_config_sha256,
    get_model,
    list_models,
)
from deerflow.config.model_config import ModelConfig


def _model_config(**overrides) -> ModelConfig:
    values = {
        "name": "doubao-seed-evolving-m2-e3",
        "display_name": "M2 E3",
        "description": "Controlled comparison model",
        "use": "deerflow.models.patched_deepseek:PatchedChatDeepSeek",
        "model": "doubao-seed-evolving",
        "supports_thinking": True,
        "supports_reasoning_effort": True,
        "supports_vision": True,
        "temperature": 0,
        "max_tokens": 16_000,
        "top_p": 0.85,
        "reasoning_effort": "high",
        "base_url": "https://ark.example.test/api/v3",
        "api_key": "top-level-secret",
        "when_thinking_enabled": {
            "thinking": {"type": "enabled"},
            "access_token": "nested-secret",
        },
        "default_headers": {"Authorization": "Bearer header-secret"},
    }
    values.update(overrides)
    return ModelConfig.model_validate(values)


def _expected_sha(projection: dict) -> str:
    canonical = json.dumps(
        {"schema": _EFFECTIVE_CONFIG_SCHEMA, "config": projection},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@pytest.mark.anyio
async def test_model_routes_return_effective_config_receipt_without_secrets():
    model = _model_config()
    config = SimpleNamespace(
        models=[model],
        token_usage=SimpleNamespace(enabled=True),
        get_model_config=lambda name: model if name == model.name else None,
    )

    listed = await list_models(config)
    detailed = await get_model(model.name, config)

    assert listed.models == [detailed]
    assert detailed.temperature == 0
    assert detailed.max_tokens == 16_000
    assert detailed.supports_vision is True
    assert detailed.effective_config_sha256 == _effective_model_config_sha256(model)
    assert len(detailed.effective_config_sha256 or "") == 64

    serialized_response = detailed.model_dump_json()
    assert "top-level-secret" not in serialized_response
    assert "nested-secret" not in serialized_response
    assert "header-secret" not in serialized_response
    assert "base_url" not in serialized_response
    assert "config_path" not in serialized_response


def test_effective_config_hash_is_stable_and_covers_safe_inference_settings():
    first = _model_config(
        custom_generation={"frequency_penalty": 0.2, "stop": ["END"]},
    )
    second_values = first.model_dump(mode="python")
    second_values["custom_generation"] = {
        "stop": ["END"],
        "frequency_penalty": 0.2,
    }
    second = ModelConfig.model_validate(second_values)

    projection = _effective_model_config_projection(first)

    assert projection["name"] == "doubao-seed-evolving-m2-e3"
    assert projection["use"] == "deerflow.models.patched_deepseek:PatchedChatDeepSeek"
    assert projection["model"] == "doubao-seed-evolving"
    assert projection["temperature"] == 0
    assert projection["max_tokens"] == 16_000
    assert projection["supports_thinking"] is True
    assert projection["supports_reasoning_effort"] is True
    assert projection["supports_vision"] is True
    assert projection["top_p"] == 0.85
    assert projection["reasoning_effort"] == "high"
    assert projection["custom_generation"] == {
        "frequency_penalty": 0.2,
        "stop": ["END"],
    }
    assert "display_name" not in projection
    assert "description" not in projection
    assert "api_key" not in projection
    assert "default_headers" not in projection
    assert "access_token" not in projection["when_thinking_enabled"]

    assert _effective_model_config_sha256(first) == _expected_sha(projection)
    assert _effective_model_config_sha256(first) == _effective_model_config_sha256(second)


def test_secret_changes_do_not_change_effective_config_hash():
    first = _model_config(
        api_key="first-api-key",
        when_thinking_enabled={
            "thinking": {"type": "enabled"},
            "client_secret": "first-client-secret",
            "apiToken": "first-api-token",
        },
        default_headers={"X-Api-Key": "first-header-key"},
    )
    second = _model_config(
        api_key="second-api-key",
        when_thinking_enabled={
            "thinking": {"type": "enabled"},
            "client_secret": "second-client-secret",
            "apiToken": "second-api-token",
        },
        default_headers={"X-Api-Key": "second-header-key"},
    )

    assert _effective_model_config_sha256(first) == _effective_model_config_sha256(second)


@pytest.mark.parametrize(
    ("field_name", "changed_value"),
    [
        ("temperature", 0.4),
        ("max_tokens", 8_000),
        ("top_p", 0.4),
        ("reasoning_effort", "low"),
        ("supports_vision", False),
    ],
)
def test_effective_parameter_changes_change_config_hash(field_name, changed_value):
    baseline = _model_config()
    changed = _model_config(**{field_name: changed_value})

    assert _effective_model_config_sha256(baseline) != _effective_model_config_sha256(changed)
