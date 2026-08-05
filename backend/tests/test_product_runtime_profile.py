from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi import HTTPException


def _profile_payload() -> dict:
    return {
        "schema_version": "ip-agent-runtime-profile-v1",
        "enabled": True,
        "product_id": "ip-agent",
        "assistant_id": "ip-agent",
        "agent_artifact_sha256": "b" * 64,
        "capability_contract": {
            "tool_allowlist": ["web_search", "read_file"],
            "skills": [],
            "memory_enabled": False,
        },
        "entrypoints": {
            "customer_run": "pin",
            "owner_im": "pin",
            "scheduler": "pin",
            "video_workbench": "off",
        },
    }


def _agent_config(**overrides):
    values = {
        "name": "ip-agent",
        "tool_allowlist": ["web_search", "read_file"],
        "skills": [],
        "memory_enabled": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _patch_provisioned_agent(monkeypatch, product_runtime, config=None):
    calls = []

    def _ensure(**kwargs):
        calls.append(kwargs)
        return config or _agent_config()

    monkeypatch.setattr(
        product_runtime,
        "ensure_product_owner_agent",
        _ensure,
        raising=False,
    )
    return calls


def test_missing_product_profile_keeps_generic_deerflow_behavior(tmp_path):
    from app.gateway.product_runtime import load_product_runtime_profile

    assert load_product_runtime_profile(tmp_path / "missing.yaml") is None


def test_missing_product_profile_never_provisions_owner_agent(
    tmp_path,
    monkeypatch,
):
    from app.gateway import product_runtime

    monkeypatch.setattr(
        product_runtime,
        "_profile_path",
        lambda: tmp_path / "missing.yaml",
    )

    def _unexpected_provision(**kwargs):
        raise AssertionError("generic DeerFlow must not install product state")

    monkeypatch.setattr(
        product_runtime,
        "ensure_product_owner_agent",
        _unexpected_provision,
        raising=False,
    )
    request = SimpleNamespace(
        headers={},
        state=SimpleNamespace(
            auth_source="session",
            user=SimpleNamespace(id="owner-1"),
        ),
    )

    assert product_runtime.resolve_product_runtime_binding(request, {}) is None


def test_shipped_product_profile_is_valid_and_video_entrypoint_is_dormant():
    """The checked-in YAML must preserve the string action, not YAML bool false."""
    from app.gateway.product_runtime import load_product_runtime_profile
    from deerflow.config.agents_config import agent_artifact_sha256

    root = Path(__file__).resolve().parents[2]
    profile = load_product_runtime_profile(root / "product" / "defaults" / "product-runtime-profile.yaml")

    assert profile is not None
    assert profile.entrypoints.video_workbench == "off"
    assert profile.agent_artifact_sha256 == agent_artifact_sha256(root / "product" / "defaults" / "agents" / "ip-agent")


def test_external_customer_run_is_pinned_and_receipted(tmp_path, monkeypatch):
    from app.gateway import product_runtime

    path = tmp_path / "product-runtime-profile.yaml"
    path.write_text(yaml.safe_dump(_profile_payload()), encoding="utf-8")
    monkeypatch.setattr(product_runtime, "_profile_path", lambda: path)
    provisioning_calls = _patch_provisioned_agent(monkeypatch, product_runtime)
    request = SimpleNamespace(
        headers={},
        state=SimpleNamespace(
            auth_source="session",
            user=SimpleNamespace(id="owner-1"),
        ),
    )

    binding = product_runtime.resolve_product_runtime_binding(request, {})

    assert binding is not None
    assert binding.assistant_id == "ip-agent"
    assert binding.entrypoint == "customer_run"
    assert binding.receipt == {
        "schema_version": "product-runtime-binding-v1",
        "product_id": "ip-agent",
        "entrypoint": "customer_run",
        "assistant_id": "ip-agent",
        "agent_artifact_sha256": "b" * 64,
        "declared_capability_digest": binding.receipt["declared_capability_digest"],
    }
    assert len(binding.receipt["declared_capability_digest"]) == 64
    assert provisioning_calls[0]["owner_user_id"] == "owner-1"
    assert provisioning_calls[0]["assistant_id"] == "ip-agent"
    assert provisioning_calls[0]["declared_artifact_sha256"] == "b" * 64


def test_new_owner_is_provisioned_from_shipped_defaults_before_binding(
    tmp_path,
    monkeypatch,
):
    """Exercise the real installer with an internal User.id and no Owner files."""
    from app.gateway import product_owner_provisioning, product_runtime
    from deerflow.config.paths import Paths

    root = Path(__file__).resolve().parents[2]
    state = tmp_path / "state"
    monkeypatch.setattr(
        product_runtime,
        "_profile_path",
        lambda: root / "product" / "defaults" / "product-runtime-profile.yaml",
    )
    monkeypatch.setattr(product_owner_provisioning, "get_paths", lambda: Paths(state))
    monkeypatch.setattr(
        product_owner_provisioning,
        "runtime_project_root",
        lambda: root,
    )
    request = SimpleNamespace(
        headers={},
        state=SimpleNamespace(
            auth_source="session",
            user=SimpleNamespace(id="new-user-uuid-1"),
        ),
    )

    binding = product_runtime.resolve_product_runtime_binding(
        request,
        {},
        requested_assistant_id="lead_agent",
    )

    target = state / "users" / "new-user-uuid-1" / "agents" / "ip-agent"
    assert binding is not None
    assert binding.assistant_id == "ip-agent"
    assert (target / "config.yaml").is_file()
    assert (target / "SOUL.md").is_file()


@pytest.mark.parametrize(
    ("requested_assistant_id", "request_config", "request_context", "status_code"),
    [
        (
            "lead_agent",
            {"context": {"is_bootstrap": True}},
            {},
            403,
        ),
        (
            "another-agent",
            None,
            {},
            409,
        ),
    ],
)
def test_product_request_rejects_unsupported_selectors_before_agent_lookup(
    tmp_path,
    monkeypatch,
    requested_assistant_id,
    request_config,
    request_context,
    status_code,
):
    """Product requests fail closed instead of silently changing identity."""
    from app.gateway import product_runtime

    path = tmp_path / "product-runtime-profile.yaml"
    path.write_text(yaml.safe_dump(_profile_payload()), encoding="utf-8")
    monkeypatch.setattr(product_runtime, "_profile_path", lambda: path)

    def _unexpected_lookup(*args, **kwargs):
        raise AssertionError("AgentConfig must not be read after selector rejection")

    monkeypatch.setattr(
        product_runtime,
        "ensure_product_owner_agent",
        _unexpected_lookup,
        raising=False,
    )
    request = SimpleNamespace(
        headers={},
        state=SimpleNamespace(
            auth_source="session",
            user=SimpleNamespace(id="owner-1"),
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        product_runtime.resolve_product_runtime_binding(
            request,
            request_context,
            requested_assistant_id=requested_assistant_id,
            request_config=request_config,
        )

    assert exc_info.value.status_code == status_code


@pytest.mark.parametrize(
    ("overrides", "mismatch"),
    [
        ({"tool_allowlist": ["web_search", "read_file", "bash"]}, "tool_allowlist"),
        ({"skills": ["personal-ip-operator"]}, "skills"),
        ({"memory_enabled": True}, "memory_enabled"),
    ],
)
def test_capability_drift_fails_closed_before_run(
    tmp_path,
    monkeypatch,
    overrides,
    mismatch,
):
    from app.gateway import product_runtime

    path = tmp_path / "product-runtime-profile.yaml"
    path.write_text(yaml.safe_dump(_profile_payload()), encoding="utf-8")
    monkeypatch.setattr(product_runtime, "_profile_path", lambda: path)
    _patch_provisioned_agent(
        monkeypatch,
        product_runtime,
        _agent_config(**overrides),
    )
    request = SimpleNamespace(
        headers={},
        state=SimpleNamespace(
            auth_source="auth_disabled",
            user=SimpleNamespace(id="default"),
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        product_runtime.resolve_product_runtime_binding(request, {})

    assert exc_info.value.status_code == 503
    assert mismatch in exc_info.value.detail


def test_missing_product_agent_fails_closed(tmp_path, monkeypatch):
    from app.gateway import product_runtime

    path = tmp_path / "product-runtime-profile.yaml"
    path.write_text(yaml.safe_dump(_profile_payload()), encoding="utf-8")
    monkeypatch.setattr(product_runtime, "_profile_path", lambda: path)

    def _missing(**kwargs):
        raise RuntimeError("source missing")

    monkeypatch.setattr(
        product_runtime,
        "ensure_product_owner_agent",
        _missing,
        raising=False,
    )
    request = SimpleNamespace(
        headers={},
        state=SimpleNamespace(
            auth_source="session",
            user=SimpleNamespace(id="owner-1"),
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        product_runtime.resolve_product_runtime_binding(request, {})

    assert exc_info.value.status_code == 503
    assert "unavailable" in exc_info.value.detail


def test_only_trusted_internal_entrypoint_activates_product_profile(
    tmp_path,
    monkeypatch,
):
    from app.gateway import product_runtime

    path = tmp_path / "product-runtime-profile.yaml"
    path.write_text(yaml.safe_dump(_profile_payload()), encoding="utf-8")
    monkeypatch.setattr(product_runtime, "_profile_path", lambda: path)
    _patch_provisioned_agent(monkeypatch, product_runtime)
    from app.gateway.internal_auth import INTERNAL_OWNER_USER_ID_HEADER_NAME

    request = SimpleNamespace(
        headers={INTERNAL_OWNER_USER_ID_HEADER_NAME: "owner-1"},
        state=SimpleNamespace(
            auth_source="internal",
            user=SimpleNamespace(id="internal", system_role="internal"),
        ),
    )

    assert product_runtime.resolve_product_runtime_binding(request, {}) is None
    binding = product_runtime.resolve_product_runtime_binding(
        request,
        {"product_entrypoint": "scheduler", "user_id": "owner-1"},
    )
    assert binding is not None
    assert binding.entrypoint == "scheduler"


def test_internal_context_user_id_cannot_select_product_owner(
    tmp_path,
    monkeypatch,
):
    from app.gateway import product_runtime

    path = tmp_path / "product-runtime-profile.yaml"
    path.write_text(yaml.safe_dump(_profile_payload()), encoding="utf-8")
    monkeypatch.setattr(product_runtime, "_profile_path", lambda: path)
    request = SimpleNamespace(
        headers={},
        state=SimpleNamespace(
            auth_source="internal",
            user=SimpleNamespace(id="internal", system_role="internal"),
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        product_runtime.resolve_product_runtime_binding(
            request,
            {"product_entrypoint": "scheduler", "user_id": "forged-owner"},
        )

    assert exc_info.value.status_code == 503
    assert "trusted owner" in exc_info.value.detail


def test_denied_product_entrypoint_fails_closed(tmp_path, monkeypatch):
    from app.gateway import product_runtime

    path = tmp_path / "product-runtime-profile.yaml"
    payload = _profile_payload()
    payload["entrypoints"]["video_workbench"] = "deny"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    monkeypatch.setattr(product_runtime, "_profile_path", lambda: path)
    request = SimpleNamespace(
        headers={},
        state=SimpleNamespace(
            auth_source="internal",
            user=SimpleNamespace(id="internal"),
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        product_runtime.resolve_product_runtime_binding(
            request,
            {"product_entrypoint": "video_workbench", "user_id": "owner-1"},
        )

    assert exc_info.value.status_code == 403
