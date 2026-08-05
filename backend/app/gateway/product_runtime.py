"""Server-owned runtime identity and capability contract for product installs.

The profile is optional.  Its absence preserves generic DeerFlow behavior.
When installed, it pins only explicitly classified product entrypoints and
verifies the owner-scoped Agent config before a Run row or model call exists.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.gateway.auth_disabled import AUTH_SOURCE_INTERNAL
from app.gateway.internal_auth import get_trusted_internal_owner_user_id
from app.gateway.product_owner_provisioning import ensure_product_owner_agent
from deerflow.config.agents_config import validate_agent_name
from deerflow.config.paths import get_paths

PRODUCT_RUNTIME_PROFILE_FILENAME = "product-runtime-profile.yaml"
PRODUCT_RUNTIME_PROFILE_SCHEMA = "ip-agent-runtime-profile-v1"
PRODUCT_RUNTIME_RECEIPT_KEY = "deerflow_product_runtime"
ProductEntrypoint = Literal[
    "customer_run",
    "owner_im",
    "scheduler",
    "video_workbench",
]
EntrypointAction = Literal["off", "pin", "deny"]


class ProductCapabilityContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_allowlist: list[str]
    skills: list[str]
    memory_enabled: bool

    @field_validator("tool_allowlist", "skills")
    @classmethod
    def _reject_duplicates(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("capability lists must not contain duplicates")
        return values


class ProductEntrypoints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_run: EntrypointAction = "off"
    owner_im: EntrypointAction = "off"
    scheduler: EntrypointAction = "off"
    video_workbench: EntrypointAction = "off"


class ProductRuntimeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[PRODUCT_RUNTIME_PROFILE_SCHEMA]
    enabled: bool = False
    product_id: str = Field(min_length=1)
    assistant_id: str
    agent_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_contract: ProductCapabilityContract
    entrypoints: ProductEntrypoints

    @field_validator("assistant_id")
    @classmethod
    def _validate_assistant_id(cls, value: str) -> str:
        validated = validate_agent_name(value)
        if validated is None:
            raise ValueError("assistant_id is required")
        return validated


@dataclass(frozen=True, slots=True)
class ProductRuntimeBinding:
    assistant_id: str
    entrypoint: ProductEntrypoint
    receipt: dict[str, str]


def _profile_path() -> Path:
    return get_paths().base_dir / PRODUCT_RUNTIME_PROFILE_FILENAME


def load_product_runtime_profile(
    path: Path | None = None,
) -> ProductRuntimeProfile | None:
    source = path or _profile_path()
    if not source.is_file():
        return None
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        profile = ProductRuntimeProfile.model_validate(payload)
    except Exception as exc:
        raise RuntimeError(f"Product runtime profile is invalid: {source}") from exc
    return profile if profile.enabled else None


def require_customer_mutable_agent_name(agent_name: str) -> None:
    """Reject customer mutation of the profile-owned product Agent."""
    try:
        profile = load_product_runtime_profile()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if profile is not None and agent_name == profile.assistant_id:
        raise HTTPException(
            status_code=403,
            detail=f"Agent {agent_name!r} is operator-owned by the product runtime",
        )


def _resolve_entrypoint(
    request: Request,
    request_context: Mapping[str, Any] | None,
) -> ProductEntrypoint | None:
    auth_source = getattr(getattr(request, "state", None), "auth_source", None)
    if auth_source != AUTH_SOURCE_INTERNAL:
        return "customer_run"
    if not isinstance(request_context, Mapping):
        return None
    value = request_context.get("product_entrypoint")
    if value in {"owner_im", "scheduler", "video_workbench"}:
        return value
    return None


def _resolve_owner_user_id(
    request: Request,
) -> str | None:
    trusted_owner = get_trusted_internal_owner_user_id(request)
    if trusted_owner:
        return trusted_owner
    auth_source = getattr(getattr(request, "state", None), "auth_source", None)
    if auth_source == AUTH_SOURCE_INTERNAL:
        return None
    user_id = getattr(getattr(getattr(request, "state", None), "user", None), "id", None)
    return str(user_id) if user_id is not None else None


def _capability_digest(
    profile: ProductRuntimeProfile,
) -> str:
    payload = {
        "schema_version": profile.schema_version,
        "product_id": profile.product_id,
        "assistant_id": profile.assistant_id,
        "agent_artifact_sha256": profile.agent_artifact_sha256,
        "capability_contract": profile.capability_contract.model_dump(),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_requested_identity(value: str) -> str:
    stripped = value.strip()
    if stripped == "lead_agent":
        return "lead_agent"
    normalized = stripped.lower().replace("_", "-")
    if not normalized or not re.fullmatch(r"[a-z0-9-]+", normalized):
        raise HTTPException(
            status_code=409,
            detail=f"Product runtime received an invalid Agent identity {value!r}",
        )
    return normalized


def _product_request_selectors(
    requested_assistant_id: str | None,
    request_config: Mapping[str, Any] | None,
    request_context: Mapping[str, Any] | None,
) -> tuple[set[str], bool]:
    raw_selectors: list[str] = []
    if isinstance(requested_assistant_id, str) and requested_assistant_id.strip():
        raw_selectors.append(requested_assistant_id)
    bootstrap = False
    for container in (
        request_context,
        request_config.get("context") if isinstance(request_config, Mapping) else None,
        request_config.get("configurable") if isinstance(request_config, Mapping) else None,
    ):
        if not isinstance(container, Mapping):
            continue
        value = container.get("agent_name")
        if isinstance(value, str) and value.strip():
            raw_selectors.append(value)
        bootstrap = bootstrap or container.get("is_bootstrap") is True
    return {_normalize_requested_identity(value) for value in raw_selectors}, bootstrap


def resolve_product_runtime_binding(
    request: Request,
    request_context: Mapping[str, Any] | None,
    *,
    requested_assistant_id: str | None = None,
    request_config: Mapping[str, Any] | None = None,
) -> ProductRuntimeBinding | None:
    """Return the server binding for one product entrypoint, if configured."""
    try:
        profile = load_product_runtime_profile()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if profile is None:
        return None

    entrypoint = _resolve_entrypoint(request, request_context)
    if entrypoint is None:
        return None
    action = getattr(profile.entrypoints, entrypoint)
    if action == "off":
        return None
    if action == "deny":
        raise HTTPException(
            status_code=403,
            detail=f"Product entrypoint {entrypoint!r} is disabled by the runtime profile",
        )

    selectors, bootstrap = _product_request_selectors(
        requested_assistant_id,
        request_config,
        request_context,
    )
    if bootstrap:
        raise HTTPException(
            status_code=403,
            detail="Agent bootstrap is disabled for this product entrypoint",
        )
    allowed_selectors = {"lead_agent", profile.assistant_id}
    unsupported = selectors - allowed_selectors
    if unsupported:
        raise HTTPException(
            status_code=409,
            detail=(f"This product entrypoint cannot select a different Agent: {sorted(unsupported)!r}"),
        )

    owner_user_id = _resolve_owner_user_id(request)
    if owner_user_id is None:
        raise HTTPException(
            status_code=503,
            detail=(f"Product entrypoint {entrypoint!r} has no trusted owner binding"),
        )
    try:
        agent_config = ensure_product_owner_agent(
            owner_user_id=owner_user_id,
            assistant_id=profile.assistant_id,
            declared_capability=profile.capability_contract.model_dump(),
            declared_artifact_sha256=profile.agent_artifact_sha256,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(f"Product Agent {profile.assistant_id!r} is unavailable: {exc}"),
        ) from exc

    expected = profile.capability_contract
    mismatches: list[str] = []
    if agent_config.name != profile.assistant_id:
        mismatches.append("name")
    if agent_config.tool_allowlist != expected.tool_allowlist:
        mismatches.append("tool_allowlist")
    if agent_config.skills != expected.skills:
        mismatches.append("skills")
    if agent_config.memory_enabled is not expected.memory_enabled:
        mismatches.append("memory_enabled")
    if mismatches:
        raise HTTPException(
            status_code=503,
            detail=(f"Product Agent {profile.assistant_id!r} capability drift: {', '.join(mismatches)}"),
        )

    receipt = {
        "schema_version": "product-runtime-binding-v1",
        "product_id": profile.product_id,
        "entrypoint": entrypoint,
        "assistant_id": profile.assistant_id,
        "agent_artifact_sha256": profile.agent_artifact_sha256,
        "declared_capability_digest": _capability_digest(profile),
    }
    return ProductRuntimeBinding(
        assistant_id=profile.assistant_id,
        entrypoint=entrypoint,
        receipt=receipt,
    )
