#!/usr/bin/env python3
"""Offline verifier and explicitly gated live canary for Writer Brain v2.

The default command is a zero-network, zero-database readiness check.  A live
run needs three exact environment values and accepts only a loopback Gateway.
Each invocation runs one frozen case in a new task and seals an immutable
evidence packet; it never retries a model call.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
HARNESS_DIR = REPO_ROOT / "backend/packages/harness"
for _import_path in (HARNESS_DIR, SCRIPT_DIR):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

from personal_ip_writer_v2_acceptance_oracle import (  # noqa: E402
    evaluate_writer_behavior_acceptance,
)

from deerflow.config.agents_config import agent_artifact_sha256  # noqa: E402
from deerflow.personal_ip.data_lifecycle import EXPORT_DATASET_NAMES  # noqa: E402

TEST_STATE_RELATIVE = Path("backend/.deer-flow-ip-test")
TEST_MARKER_NAME = ".ip-agent-test-mode.json"
PRODUCT_AGENT_RELATIVE = Path("product/defaults/agents/ip-agent")
PRODUCT_PROFILE_RELATIVE = Path("product/defaults/product-runtime-profile.yaml")
LIVE_ACK = "RUN_REAL_DEFAULT_AGENT"
PACKET_SCHEMA = "personal-ip-writer-v2-acceptance-packet-v1"
RUN_RECEIPT_SCHEMA = "personal-ip-writer-v2-run-receipt-v1"
EXPORT_RECEIPT_SCHEMA = "personal-ip-owner-backup-export-receipt-v1"
BACKUP_SCHEMA = "personal-ip-owner-backup-v5"
BACKUP_ALGORITHM = "hmac-sha256-canonical-json-v1"
LIVE_ARTIFACT_NAMES = (
    "case-input.json",
    "answer.txt",
    "run-receipt.json",
    "tool-receipt.json",
    "lineage.json",
    "owner-backup-v5.json",
)
SYNTHETIC_SOURCES = frozenset({"mock", "replay", "fixture"})
LIVE_SOURCE = "live_gateway"
DIRECT_WRITER_CALLS = (
    "ip-agent-script-writer-v2",
    "ip-agent-script-boundary-verifier-v2",
)
SEMANTIC_WRITER_CALLS = (
    "ip-agent-story-engine-v2",
    *DIRECT_WRITER_CALLS,
)
EXPECTED_CAPABILITY = {
    "tool_allowlist": [
        "web_search",
        "image_search",
        "ls",
        "read_file",
        "glob",
        "grep",
        "view_image",
        "ask_clarification",
        "ip_evidence_collect_douyin_benchmark_account",
        "ip_evidence_inspect_reference_videos",
        "ip_content_read",
        "ip_content_save_breakdown",
        "ip_content_write",
        "ip_content_start_production",
    ],
    "skills": [],
    "memory_enabled": False,
}
EXPECTED_CREDENTIAL_POLICY = {
    "credentials_included": False,
    "oauth_states_included": False,
    "paid_call_admissions_included": False,
    "platform_reauthorization_required_after_restore": True,
    "paid_call_reapproval_required_after_restore": True,
}
EXPECTED_ARTIFACT_POLICY = {
    "metadata_included": True,
    "binary_files_included": False,
    "content_must_be_downloaded_separately": True,
}
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_16 = re.compile(r"^[0-9a-f]{16}$")
FORBIDDEN_MODEL_MARKERS = ("mock", "test", "fixture", "replay", "fake")
MALFORMED_TOOL_CLASSIFICATION = "malformed_tool_arguments"


@dataclass(frozen=True, slots=True)
class FrozenCase:
    case_id: str
    prompt: str
    expected_route: str
    expected_story_mode: str


_CANONICAL_FROZEN_CASES = (
    FrozenCase(
        case_id="urgent_fruit_offer",
        prompt=("我是果农，800斤桃已进入7天采摘窗口，过期会软烂；5斤装49元，可以展示成熟度、分拣、称重和当天发货。当前第一目标是在7天内卖出去，不做长期人物IP。请直接策划并保存第一条完整直售脚本，不要反问。"),
        expected_route="offer",
        expected_story_mode="factual",
    ),
    FrozenCase(
        case_id="long_term_person_semantic_story",
        prompt=("水果目前不急卖，未来一年希望观众记住果农本人。第一条不要卖货，要做一条明确标注虚构的短剧情，围绕“看不到回报时还守不守承诺”；水果、果园和节气只是语义入口，不能把剧情冒充我的真实经历。请直接保存完整脚本。"),
        expected_route="semantic_story",
        expected_story_mode="fictional",
    ),
    FrozenCase(
        case_id="mcn_brand_explanation",
        prompt=(
            "我经营 Northstar Creators，要做 TikTok MCN 官方账号。未来一年优先级明确为："
            "机构品牌认知第一、合格创作者申请第二、信任作为支撑；不是老板个人IP。"
            "我们真实实行分成、结算和退出规则透明，创作者保留内容决定权，也不承诺爆款或收入。"
            "第一条请解释“加入后第一周实际会发生什么”，直接保存完整脚本。"
        ),
        expected_route="explanation",
        expected_story_mode="factual",
    ),
    FrozenCase(
        case_id="drummer_mom_demonstration",
        prompt=("我曾是地下乐队鼓手，停了5年，现在也是孩子的母亲，准备通过一年真实训练重返舞台。我做的是个人IP，孩子不出镜，也不做育儿内容。第一条记录训练第一天，请直接保存完整脚本。"),
        expected_route="demonstration",
        expected_story_mode="factual",
    ),
)
FROZEN_CASES = _CANONICAL_FROZEN_CASES


class AcceptanceError(RuntimeError):
    """Stable fail-closed acceptance error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise AcceptanceError(code)


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _sequence(value: Any) -> Sequence[Any] | None:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return None


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _validated_invalid_tool_receipts(value: Any) -> list[dict[str, str]]:
    raw_receipts = _sequence(value)
    if raw_receipts is None:
        _fail("LEAD_MODEL_RECOVERY_INVALID")
    receipts: list[dict[str, str]] = []
    for raw in raw_receipts:
        receipt = _mapping(raw)
        if receipt is None or set(receipt) != {"name", "classification"} or not isinstance(receipt.get("name"), str) or not receipt.get("name") or receipt.get("classification") != MALFORMED_TOOL_CLASSIFICATION:
            _fail("LEAD_MODEL_RECOVERY_INVALID")
        receipts.append(
            {
                "name": str(receipt["name"]),
                "classification": MALFORMED_TOOL_CLASSIFICATION,
            }
        )
    return receipts


def _seal_invalid_tool_payloads(value: Any) -> Any:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_seal_invalid_tool_payloads(item) for item in value]
    message = _mapping(value)
    if message is None:
        return copy.deepcopy(value)
    raw_invalid_value = message.get("invalid_tool_calls", [])
    raw_invalid = _sequence(raw_invalid_value)
    if raw_invalid is None:
        _fail("LEAD_MODEL_RECOVERY_INVALID")
    already_sealed = message.get("acceptance_invalid_tool_calls")
    if raw_invalid and already_sealed is not None:
        _fail("LEAD_MODEL_RECOVERY_INVALID")
    sealed: dict[str, Any] = {}
    for key, item in message.items():
        if key in {
            "invalid_tool_calls",
            "acceptance_invalid_tool_calls",
        }:
            continue
        if key == "additional_kwargs" and ("tool_calls" in message or "invalid_tool_calls" in message):
            additional = _mapping(item)
            if additional is None:
                _fail("LEAD_MODEL_RECOVERY_INVALID")
            item = {additional_key: additional_value for additional_key, additional_value in additional.items() if additional_key not in {"tool_calls", "function_call"}}
        sealed[str(key)] = _seal_invalid_tool_payloads(item)
    if "invalid_tool_calls" in message:
        sealed["invalid_tool_calls"] = []
    if raw_invalid:
        receipts: list[dict[str, str]] = []
        for raw in raw_invalid:
            invalid = _mapping(raw)
            name = invalid.get("name") if invalid is not None else None
            if not isinstance(name, str) or not name:
                _fail("LEAD_MODEL_RECOVERY_INVALID")
            receipts.append(
                {
                    "name": name,
                    "classification": MALFORMED_TOOL_CLASSIFICATION,
                }
            )
        sealed["acceptance_invalid_tool_calls"] = receipts
    elif already_sealed is not None:
        sealed["acceptance_invalid_tool_calls"] = _validated_invalid_tool_receipts(
            already_sealed,
        )
    return sealed


def _seal_invalid_tool_calls(message: Mapping[str, Any]) -> dict[str, Any]:
    sealed = _seal_invalid_tool_payloads(message)
    if not isinstance(sealed, dict):
        _fail("LEAD_MODEL_RECOVERY_INVALID")
    return sealed


def _lead_tool_receipt_from_content(content: Mapping[str, Any]) -> dict[str, Any]:
    raw_valid = _sequence(content.get("tool_calls", []))
    raw_invalid = _sequence(content.get("invalid_tool_calls", []))
    if raw_valid is None or raw_invalid is None or raw_invalid:
        _fail("LEAD_MODEL_RECOVERY_INVALID")
    valid_names: list[str] = []
    for raw in raw_valid:
        call = _mapping(raw)
        name = call.get("name") if call is not None else None
        if not isinstance(name, str) or not name:
            _fail("LEAD_MODEL_RECOVERY_INVALID")
        valid_names.append(name)
    sealed_invalid_value = content.get("acceptance_invalid_tool_calls", [])
    invalid_receipts = _validated_invalid_tool_receipts(sealed_invalid_value)
    response_metadata = _mapping(content.get("response_metadata")) or {}
    additional = _mapping(content.get("additional_kwargs")) or {}
    finish_reason = response_metadata.get("finish_reason")
    if not isinstance(finish_reason, str) or not finish_reason:
        _fail("LEAD_MODEL_RECOVERY_INVALID")
    return {
        "finish_reason": finish_reason,
        "valid_tool_call_names": valid_names,
        "invalid_tool_calls": invalid_receipts,
        "fallback": additional.get("deerflow_error_fallback") is True,
    }


def _validated_lead_tool_receipt(value: Any) -> dict[str, Any]:
    receipt = _mapping(value)
    if receipt is None or set(receipt) != {
        "finish_reason",
        "valid_tool_call_names",
        "invalid_tool_calls",
        "fallback",
    }:
        _fail("LEAD_MODEL_RECOVERY_INVALID")
    valid_names = _sequence(receipt.get("valid_tool_call_names"))
    if not isinstance(receipt.get("finish_reason"), str) or not receipt.get("finish_reason") or valid_names is None or any(not isinstance(name, str) or not name for name in valid_names) or type(receipt.get("fallback")) is not bool:
        _fail("LEAD_MODEL_RECOVERY_INVALID")
    return {
        "finish_reason": str(receipt["finish_reason"]),
        "valid_tool_call_names": list(valid_names),
        "invalid_tool_calls": _validated_invalid_tool_receipts(
            receipt.get("invalid_tool_calls"),
        ),
        "fallback": bool(receipt["fallback"]),
    }


def _seal_gateway_events(
    events: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    sealed_events: list[dict[str, Any]] = []
    for raw_event in events:
        event = _seal_invalid_tool_calls(raw_event)
        if event.get("event_type") == "llm.ai.response" and _mapping(event.get("content")) is None:
            _fail("GATEWAY_EVENT_RECEIPT_INVALID")
        sealed_events.append(event)
    return sealed_events


def _seal_checkpoint_state(state: Mapping[str, Any]) -> dict[str, Any]:
    sealed = _seal_invalid_tool_calls(state)
    values = _mapping(sealed.get("values"))
    messages = _sequence(values.get("messages")) if values else None
    if values is None or messages is None:
        _fail("CHECKPOINT_RECEIPT_INVALID")
    if any(_mapping(raw_message) is None for raw_message in messages):
        _fail("CHECKPOINT_RECEIPT_INVALID")
    return sealed


def _load_yaml_mapping(path: Path, code: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        _fail(code)
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError):
        _fail(code)
    if not isinstance(value, dict):
        _fail(code)
    return value


def _load_json_mapping(path: Path, code: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        _fail(code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail(code)
    if not isinstance(value, dict):
        _fail(code)
    return value


def _validate_frozen_catalog() -> None:
    if tuple(FROZEN_CASES) != _CANONICAL_FROZEN_CASES:
        _fail("FROZEN_CASE_CATALOG_INVALID")


def _validate_product_contract(root: Path) -> tuple[str, dict[str, Any]]:
    agent_dir = root / PRODUCT_AGENT_RELATIVE
    try:
        artifact_digest = agent_artifact_sha256(agent_dir)
    except (OSError, ValueError):
        _fail("AGENT_ARTIFACT_DIGEST_MISMATCH")
    profile = _load_yaml_mapping(
        root / PRODUCT_PROFILE_RELATIVE,
        "RUNTIME_CAPABILITY_CONTRACT_MISMATCH",
    )
    if profile.get("agent_artifact_sha256") != artifact_digest:
        _fail("AGENT_ARTIFACT_DIGEST_MISMATCH")
    agent_config = _load_yaml_mapping(
        agent_dir / "config.yaml",
        "RUNTIME_CAPABILITY_CONTRACT_MISMATCH",
    )
    if (
        profile.get("schema_version") != "ip-agent-runtime-profile-v1"
        or profile.get("enabled") is not True
        or profile.get("product_id") != "ip-agent"
        or profile.get("assistant_id") != "ip-agent"
        or profile.get("capability_contract") != EXPECTED_CAPABILITY
        or {key: agent_config.get(key) for key in EXPECTED_CAPABILITY} != EXPECTED_CAPABILITY
    ):
        _fail("RUNTIME_CAPABILITY_CONTRACT_MISMATCH")
    return artifact_digest, profile


def _credential_free_model_receipt(root: Path) -> dict[str, Any]:
    config = _load_yaml_mapping(root / "config.yaml", "MODEL_CONFIGURATION_INVALID")
    models = config.get("models")
    if not isinstance(models, list) or not models:
        _fail("MODEL_CONFIGURATION_INVALID")
    model = next((item for item in models if isinstance(item, Mapping)), None)
    if model is None:
        _fail("MODEL_CONFIGURATION_INVALID")
    configured_name = model.get("name")
    provider_model = model.get("model")
    if not isinstance(configured_name, str) or not configured_name.strip():
        _fail("MODEL_CONFIGURATION_INVALID")
    if not isinstance(provider_model, str) or not provider_model.strip():
        _fail("MODEL_CONFIGURATION_INVALID")
    projection = {str(key): value for key, value in model.items() if not any(marker in re.sub(r"[^a-z0-9]", "", str(key).casefold()) for marker in ("apikey", "secret", "token", "password", "credential"))}
    return {
        "configured_name": configured_name,
        "provider_model": provider_model,
        "credential_free_config_sha256": _sha256_json(projection),
    }


def run_readiness(
    *,
    root: Path,
    result_dir: Path,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    """Validate immutable inputs without reading environment values or writing."""

    del environment
    root = root.resolve()
    _validate_frozen_catalog()
    artifact_digest, _profile = _validate_product_contract(root)
    model = _credential_free_model_receipt(root)
    return {
        "status": "ready",
        "mode": "readiness",
        "case_ids": [case.case_id for case in FROZEN_CASES],
        "gateway_requests": 0,
        "model_calls": 0,
        "database_writes": 0,
        "credential_value_reads": 0,
        "result_directory_created": result_dir.exists() and False,
        "evidence_class": "synthetic_contract",
        "ledger_eligible": False,
        "agent_artifact_sha256": artifact_digest,
        "model_configuration": model,
    }


def validate_live_gate(environment: Mapping[str, str]) -> str:
    if environment.get("LIVE") != "1":
        _fail("LIVE_OPT_IN_REQUIRED")
    selected = environment.get("CASE")
    if not isinstance(selected, str) or not selected or selected == "all" or "," in selected:
        _fail("EXACTLY_ONE_CASE_REQUIRED")
    case_ids = {case.case_id for case in _CANONICAL_FROZEN_CASES}
    if selected not in case_ids:
        _fail("UNKNOWN_CASE")
    if environment.get("ACK") != LIVE_ACK:
        _fail("LIVE_ACK_REQUIRED")
    return selected


def validate_loopback_gateway_url(base_url: str) -> str:
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except (TypeError, ValueError):
        _fail("GATEWAY_MUST_BE_LOOPBACK")
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or port is None or parsed.username is not None or parsed.password is not None or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        _fail("GATEWAY_MUST_BE_LOOPBACK")
    return base_url


def validate_clean_test_state(root: Path) -> dict[str, Any]:
    root = root.resolve()
    state_dir = (root / TEST_STATE_RELATIVE).resolve()
    marker = _load_json_mapping(
        state_dir / TEST_MARKER_NAME,
        "CLEAN_TEST_PROFILE_REQUIRED",
    )
    expected_marker = {
        "schema_version": "ip-agent-test-mode-v1",
        "root": str(root),
        "state_dir": str(state_dir),
        "database_dir": str(state_dir / "data"),
        "profile": "clean",
    }
    if any(marker.get(key) != value for key, value in expected_marker.items()):
        _fail("CLEAN_TEST_PROFILE_REQUIRED")
    product_digest, product_profile = _validate_product_contract(root)
    installed_agent = state_dir / "users/default/agents/ip-agent"
    try:
        installed_digest = agent_artifact_sha256(installed_agent)
    except (OSError, ValueError):
        _fail("TEST_AGENT_ARTIFACT_MISMATCH")
    installed_profile = _load_yaml_mapping(
        state_dir / "product-runtime-profile.yaml",
        "TEST_AGENT_ARTIFACT_MISMATCH",
    )
    if installed_digest != product_digest or installed_profile != product_profile or installed_profile.get("agent_artifact_sha256") != installed_digest:
        _fail("TEST_AGENT_ARTIFACT_MISMATCH")
    return {
        "schema_version": "personal-ip-writer-v2-clean-state-receipt-v1",
        "profile": "clean",
        "state_dir": str(state_dir),
        "database_dir": str(state_dir / "data"),
        "owner_user_id": "default",
        "agent_artifact_sha256": installed_digest,
    }


def _validate_gateway_export_receipt(
    backup: Mapping[str, Any],
    receipt: Mapping[str, Any] | None,
) -> None:
    if receipt is None:
        _fail("OWNER_BACKUP_GATEWAY_RECEIPT_INVALID")
    base_url = receipt.get("base_url")
    try:
        validate_loopback_gateway_url(str(base_url))
    except AcceptanceError:
        _fail("OWNER_BACKUP_GATEWAY_RECEIPT_INVALID")
    disposition = receipt.get("content_disposition")
    if (
        receipt.get("schema_version") != EXPORT_RECEIPT_SCHEMA
        or receipt.get("method") != "GET"
        or receipt.get("path") != "/api/personal-ip/data/export"
        or receipt.get("status_code") != 200
        or str(receipt.get("cache_control", "")).casefold() != "no-store"
        or not isinstance(disposition, str)
        or not disposition.startswith('attachment; filename="personal-ip-backup-')
        or not disposition.endswith('.json"')
        or receipt.get("body_sha256") != _sha256_json(backup)
    ):
        _fail("OWNER_BACKUP_GATEWAY_RECEIPT_INVALID")


def _validate_v5_backup_structure(
    backup: Mapping[str, Any],
    *,
    expected_owner_user_id: str,
    require_empty: bool,
) -> tuple[dict[str, list[Mapping[str, Any]]], int]:
    if backup.get("schema_version") != BACKUP_SCHEMA:
        _fail("OWNER_BACKUP_V5_INVALID")
    if backup.get("owner_user_id") != expected_owner_user_id:
        _fail("OWNER_BASELINE_OWNER_MISMATCH")
    datasets_value = _sequence(backup.get("datasets"))
    if datasets_value is None:
        _fail("OWNER_BACKUP_V5_INVALID")

    # Baseline occupancy is checked before digests so a non-empty scope cannot
    # be disguised as a generic signature-format failure.
    preliminary_count = 0
    for dataset in datasets_value:
        item = _mapping(dataset)
        if item is None:
            _fail("OWNER_BACKUP_V5_INVALID")
        count = item.get("count")
        records = _sequence(item.get("records"))
        if type(count) is not int or records is None:
            _fail("OWNER_BACKUP_V5_INVALID")
        if require_empty and (count != 0 or len(records) != 0):
            _fail("OWNER_BASELINE_NOT_EMPTY")
        preliminary_count += len(records)

    if (
        backup.get("credential_policy") != EXPECTED_CREDENTIAL_POLICY
        or backup.get("artifact_policy") != EXPECTED_ARTIFACT_POLICY
        or not isinstance(backup.get("exported_at"), str)
        or not backup.get("exported_at")
        or len(datasets_value) != len(EXPORT_DATASET_NAMES)
    ):
        _fail("OWNER_BACKUP_V5_INVALID")

    records_by_name: dict[str, list[Mapping[str, Any]]] = {}
    digest_projection: list[dict[str, Any]] = []
    for expected_name, raw_dataset in zip(
        EXPORT_DATASET_NAMES,
        datasets_value,
        strict=True,
    ):
        dataset = _mapping(raw_dataset)
        if dataset is None or dataset.get("name") != expected_name:
            _fail("OWNER_BACKUP_V5_INVALID")
        records_raw = _sequence(dataset.get("records"))
        count = dataset.get("count")
        if records_raw is None or type(count) is not int or count != len(records_raw):
            _fail("OWNER_BACKUP_V5_INVALID")
        records: list[Mapping[str, Any]] = []
        for record in records_raw:
            mapped = _mapping(record)
            if mapped is None:
                _fail("OWNER_BACKUP_V5_INVALID")
            records.append(mapped)
        if dataset.get("digest") != _sha256_json({"name": expected_name, "records": list(records_raw)}):
            _fail("OWNER_BACKUP_V5_INVALID")
        records_by_name[expected_name] = records
        digest_projection.append({"name": expected_name, "records": list(records_raw)})

    verification = _mapping(backup.get("verification"))
    if (
        verification is None
        or verification.get("algorithm") != BACKUP_ALGORITHM
        or not HEX_16.fullmatch(str(verification.get("key_id", "")))
        or verification.get("data_digest") != _sha256_json(digest_projection)
        or not HEX_64.fullmatch(str(verification.get("manifest_digest", "")))
    ):
        _fail("OWNER_BACKUP_V5_INVALID")
    return records_by_name, preliminary_count


def validate_empty_owner_baseline(
    backup: Mapping[str, Any],
    *,
    expected_owner_user_id: str,
    gateway_export_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    _records, record_count = _validate_v5_backup_structure(
        backup,
        expected_owner_user_id=expected_owner_user_id,
        require_empty=True,
    )
    _validate_gateway_export_receipt(backup, gateway_export_receipt)
    return {
        "schema_version": BACKUP_SCHEMA,
        "owner_user_id": expected_owner_user_id,
        "record_count": record_count,
        "verification_algorithm": BACKUP_ALGORITHM,
        "gateway_export_bound": True,
        "backup_sha256": _sha256_json(backup),
    }


def _expected_writer_calls(case_id: str) -> tuple[str, ...]:
    if case_id == "long_term_person_semantic_story":
        return SEMANTIC_WRITER_CALLS
    if case_id in {case.case_id for case in _CANONICAL_FROZEN_CASES}:
        return DIRECT_WRITER_CALLS
    _fail("UNKNOWN_CASE")


def _model_identity(model: Mapping[str, Any]) -> str:
    return _sha256_json(
        {
            "configured_name": model.get("configured_name"),
            "provider": model.get("provider"),
            "provider_model": model.get("provider_model"),
            "effective_config_sha256": model.get("effective_config_sha256"),
        }
    )


def _product_capability_digest(agent_artifact: str) -> str:
    return _sha256_json(
        {
            "schema_version": "ip-agent-runtime-profile-v1",
            "product_id": "ip-agent",
            "assistant_id": "ip-agent",
            "agent_artifact_sha256": agent_artifact,
            "capability_contract": EXPECTED_CAPABILITY,
        }
    )


def _validate_embedded_gateway_receipts(
    run_receipt: Mapping[str, Any],
    *,
    calls: Sequence[Mapping[str, Any]],
    effective_model: Mapping[str, Any],
    expected_total: int,
    expected_agent_artifact_sha256: str,
) -> None:
    embedded = _mapping(run_receipt.get("gateway_receipts"))
    if embedded is None:
        _fail("GATEWAY_PRODUCT_BINDING_MISMATCH")
    raw_run = _mapping(embedded.get("run"))
    raw_checkpoint = _mapping(embedded.get("checkpoint"))
    raw_events = _sequence(embedded.get("events"))
    raw_token_usage = _mapping(embedded.get("token_usage"))
    raw_model = _mapping(embedded.get("model"))
    owner_baseline = _mapping(embedded.get("owner_baseline"))
    raw_metadata = _mapping(raw_run.get("metadata")) if raw_run else None
    binding = _mapping(raw_metadata.get("deerflow_product_runtime")) if raw_metadata else None
    checkpoint_state = _mapping(raw_checkpoint.get("state")) if raw_checkpoint else None
    if raw_checkpoint is None or checkpoint_state is None:
        _fail("CHECKPOINT_RECEIPT_INVALID")
    if (
        raw_run is None
        or raw_events is None
        or raw_token_usage is None
        or raw_model is None
        or owner_baseline is None
        or binding is None
        or raw_run.get("run_id") != run_receipt.get("run_id")
        or raw_run.get("thread_id") != run_receipt.get("thread_id")
        or raw_run.get("assistant_id") != "ip-agent"
        or raw_run.get("status") != "success"
        or binding.get("schema_version") != "product-runtime-binding-v1"
        or binding.get("product_id") != "ip-agent"
        or binding.get("entrypoint") != "customer_run"
        or binding.get("assistant_id") != "ip-agent"
        or binding.get("agent_artifact_sha256") != expected_agent_artifact_sha256
        or binding.get("declared_capability_digest") != _product_capability_digest(expected_agent_artifact_sha256)
        or raw_model.get("configured_name") != effective_model.get("configured_name")
        or raw_model.get("provider_model") != effective_model.get("provider_model")
        or raw_model.get("provider") != effective_model.get("provider")
        or raw_model.get("effective_config_sha256") != effective_model.get("effective_config_sha256")
        or raw_token_usage.get("total_tokens") != expected_total
        or raw_token_usage.get("total_runs") != 1
        or raw_token_usage.get("thread_id") != run_receipt.get("thread_id")
    ):
        _fail("GATEWAY_PRODUCT_BINDING_MISMATCH")

    baseline_backup = _mapping(owner_baseline.get("backup"))
    baseline_export = _mapping(owner_baseline.get("gateway_export_receipt"))
    auth_receipt = _mapping(owner_baseline.get("auth_receipt"))
    if (
        baseline_backup is None
        or baseline_backup.get("owner_user_id") != "default"
        or auth_receipt is None
        or auth_receipt.get("schema_version") != "personal-ip-writer-v2-auth-receipt-v1"
        or auth_receipt.get("method") != "GET"
        or auth_receipt.get("path") != "/api/v1/auth/me"
        or auth_receipt.get("status_code") != 200
        or auth_receipt.get("user")
        != {
            "id": "default",
            "email": "default@test.local",
            "system_role": "admin",
            "needs_setup": False,
            "oauth_provider": None,
        }
    ):
        _fail("OWNER_BACKUP_V5_INVALID")
    validate_empty_owner_baseline(
        baseline_backup,
        expected_owner_user_id="default",
        gateway_export_receipt=baseline_export,
    )

    source_calls: list[dict[str, Any]] = []
    seen_event_sequences: set[int] = set()
    previous_event_sequence = 0
    for raw_event in raw_events:
        event = _mapping(raw_event)
        if event is None:
            _fail("GATEWAY_EVENT_RECEIPT_INVALID")
        event_sequence = event.get("seq")
        if (
            event.get("thread_id") != run_receipt.get("thread_id")
            or event.get("run_id") != run_receipt.get("run_id")
            or type(event_sequence) is not int
            or event_sequence < 1
            or event_sequence in seen_event_sequences
            or event_sequence <= previous_event_sequence
        ):
            _fail("GATEWAY_EVENT_RECEIPT_INVALID")
        seen_event_sequences.add(event_sequence)
        previous_event_sequence = event_sequence
        if event.get("event_type") != "llm.ai.response":
            continue
        metadata = _mapping(event.get("metadata")) or {}
        content = _mapping(event.get("content")) or {}
        response_metadata = _mapping(content.get("response_metadata")) or {}
        additional = _mapping(content.get("additional_kwargs")) or {}
        usage = _mapping(metadata.get("usage")) or {}
        caller = metadata.get("caller")
        source_call = {
            "llm_call_index": metadata.get("llm_call_index"),
            "caller": caller,
            "model_name": response_metadata.get("model_name") or response_metadata.get("model"),
            "status": ("error" if additional.get("deerflow_error_fallback") is True else "success"),
            "event_seq": event_sequence,
            "usage": {
                "input_tokens": int(usage.get("input_tokens") or 0),
                "output_tokens": int(usage.get("output_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
        }
        if caller == "lead_agent":
            source_call["lead_tool_receipt"] = _lead_tool_receipt_from_content(
                content,
            )
        source_calls.append(source_call)
    receipt_projection: list[dict[str, Any]] = []
    for call in calls:
        projection = {
            key: call.get(key)
            for key in (
                "llm_call_index",
                "caller",
                "model_name",
                "status",
                "event_seq",
                "usage",
            )
        }
        if call.get("caller") == "lead_agent":
            projection["lead_tool_receipt"] = call.get("lead_tool_receipt")
        receipt_projection.append(projection)
    if source_calls != receipt_projection:
        _fail("PROVIDER_MODEL_RECEIPT_INVALID")

    input_total = sum(int(call["usage"]["input_tokens"]) for call in calls)
    output_total = sum(int(call["usage"]["output_tokens"]) for call in calls)
    lead_total = sum(int(call["usage"]["total_tokens"]) for call in calls if call.get("caller") == "lead_agent")
    middleware_total = sum(int(call["usage"]["total_tokens"]) for call in calls if str(call.get("caller") or "").startswith("middleware:"))
    by_caller = _mapping(raw_token_usage.get("by_caller"))
    by_model = _mapping(raw_token_usage.get("by_model"))
    model_bucket = _mapping(by_model.get(effective_model.get("provider_model"))) if by_model else None
    event_errors = [event for raw_event in raw_events if (event := _mapping(raw_event)) is not None and str(event.get("event_type") or "") in {"run.error", "llm.error", "error"}]
    if (
        event_errors
        or raw_run.get("stop_reason") is not None
        or raw_run.get("llm_call_count") != len(calls)
        or raw_run.get("total_input_tokens") != input_total
        or raw_run.get("total_output_tokens") != output_total
        or raw_run.get("total_tokens") != expected_total
        or raw_run.get("subagent_tokens") != 0
        or raw_run.get("lead_agent_tokens") != lead_total
        or raw_run.get("middleware_tokens") != middleware_total
        or raw_token_usage.get("total_input_tokens") != input_total
        or raw_token_usage.get("total_output_tokens") != output_total
        or by_caller is None
        or by_caller.get("lead_agent") != lead_total
        or by_caller.get("middleware") != middleware_total
        or by_caller.get("subagent") != 0
        or by_model is None
        or set(by_model) != {effective_model.get("provider_model")}
        or model_bucket is None
        or model_bucket.get("tokens") != expected_total
        or model_bucket.get("runs") != 1
    ):
        _fail("PROVIDER_MODEL_RECEIPT_INVALID")


def _positive_usage(value: Any) -> dict[str, int] | None:
    usage = _mapping(value)
    if usage is None:
        return None
    values: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        raw = usage.get(key)
        if type(raw) is not int or raw < 0:
            return None
        values[key] = raw
    if values["total_tokens"] <= 0:
        return None
    if values["total_tokens"] < values["input_tokens"] + values["output_tokens"]:
        return None
    return values


def _provider_model_is_real(model: Mapping[str, Any]) -> bool:
    fields = (
        model.get("configured_name"),
        model.get("provider"),
        model.get("provider_model"),
    )
    if any(not isinstance(value, str) or not value.strip() for value in fields):
        return False
    normalized = " ".join(str(value).casefold() for value in fields)
    return not any(marker in normalized for marker in FORBIDDEN_MODEL_MARKERS) and bool(HEX_64.fullmatch(str(model.get("effective_config_sha256") or "")))


def _derive_lead_recovery_count(
    calls: Sequence[Mapping[str, Any]],
    *,
    internal_calls: Sequence[Mapping[str, Any]],
) -> int:
    lead_calls = [call for call in calls if call.get("caller") == "lead_agent"]
    if len(lead_calls) < 2:
        _fail("LEAD_MODEL_RECEIPT_MISSING")
    if len(lead_calls) not in {2, 3}:
        _fail("LEAD_MODEL_RECOVERY_INVALID")
    valid_receipt = {
        "finish_reason": "tool_calls",
        "valid_tool_call_names": ["ip_content_write"],
        "invalid_tool_calls": [],
        "fallback": False,
    }
    invalid_receipt = {
        "finish_reason": "tool_calls",
        "valid_tool_call_names": [],
        "invalid_tool_calls": [
            {
                "name": "ip_content_write",
                "classification": MALFORMED_TOOL_CLASSIFICATION,
            }
        ],
        "fallback": False,
    }
    final_receipt = {
        "finish_reason": "stop",
        "valid_tool_call_names": [],
        "invalid_tool_calls": [],
        "fallback": False,
    }
    recovery_count = len(lead_calls) - 2
    expected_lead_receipts = [valid_receipt, final_receipt] if recovery_count == 0 else [invalid_receipt, valid_receipt, final_receipt]
    if any(
        call.get("status") != "success" or call.get("lead_tool_receipt") != expected
        for call, expected in zip(
            lead_calls,
            expected_lead_receipts,
            strict=True,
        )
    ):
        _fail("LEAD_MODEL_RECOVERY_INVALID")
    if not internal_calls:
        _fail("WRITER_MODEL_RECEIPT_MISMATCH")
    relevant = [call for call in calls if call.get("caller") == "lead_agent" or call in internal_calls]
    expected_relevant = [
        *lead_calls[: 1 + recovery_count],
        *internal_calls,
        lead_calls[-1],
    ]
    if relevant != expected_relevant:
        _fail("LEAD_MODEL_RECOVERY_INVALID")
    return recovery_count


def validate_live_run_receipt(
    run_receipt: Mapping[str, Any],
    *,
    case_id: str,
    expected_agent_artifact_sha256: str,
) -> dict[str, Any]:
    expected_calls = _expected_writer_calls(case_id)
    runtime = _mapping(run_receipt.get("runtime_metadata"))
    if (
        run_receipt.get("schema_version") != RUN_RECEIPT_SCHEMA
        or run_receipt.get("status") != "success"
        or not isinstance(run_receipt.get("run_id"), str)
        or not run_receipt.get("run_id")
        or not isinstance(run_receipt.get("thread_id"), str)
        or not run_receipt.get("thread_id")
        or runtime is None
        or runtime.get("product_id") != "ip-agent"
        or runtime.get("assistant_id") != "ip-agent"
        or runtime.get("agent_artifact_sha256") != expected_agent_artifact_sha256
        or runtime.get("runtime_profile_agent_artifact_sha256") != expected_agent_artifact_sha256
    ):
        _fail("GATEWAY_PRODUCT_BINDING_MISMATCH")
    effective_model = _mapping(runtime.get("effective_model"))
    if effective_model is None or not _provider_model_is_real(effective_model):
        _fail("PROVIDER_MODEL_RECEIPT_INVALID")

    raw_calls = _sequence(run_receipt.get("llm_calls"))
    if raw_calls is None or not raw_calls:
        _fail("PROVIDER_MODEL_RECEIPT_INVALID")
    calls: list[dict[str, Any]] = []
    seen_indices: set[int] = set()
    seen_event_sequences: set[int] = set()
    for raw in raw_calls:
        call = _mapping(raw)
        if call is None:
            _fail("PROVIDER_MODEL_RECEIPT_INVALID")
        index = call.get("llm_call_index")
        event_sequence = call.get("event_seq")
        usage = _positive_usage(call.get("usage"))
        caller = call.get("caller")
        status = call.get("status")
        if (
            type(index) is not int
            or index < 1
            or index in seen_indices
            or type(event_sequence) is not int
            or event_sequence < 1
            or event_sequence in seen_event_sequences
            or status not in {"success", "error"}
            or (status == "error" and caller != "lead_agent")
            or call.get("model_name") != effective_model.get("provider_model")
            or usage is None
        ):
            _fail("PROVIDER_MODEL_RECEIPT_INVALID")
        normalized = {**dict(call), "usage": usage}
        if caller == "lead_agent":
            normalized["lead_tool_receipt"] = _validated_lead_tool_receipt(
                call.get("lead_tool_receipt"),
            )
        elif call.get("lead_tool_receipt") is not None:
            _fail("PROVIDER_MODEL_RECEIPT_INVALID")
        seen_indices.add(index)
        seen_event_sequences.add(event_sequence)
        calls.append(normalized)
    calls.sort(key=lambda item: item["event_seq"])

    internal_calls = [call for call in calls if isinstance(call.get("caller"), str) and call["caller"].startswith("middleware:ip-agent-")]
    actual_internal_names = [call["caller"].removeprefix("middleware:") for call in internal_calls]
    if actual_internal_names != list(expected_calls):
        _fail("WRITER_MODEL_RECEIPT_MISMATCH")
    lead_recovery_count = _derive_lead_recovery_count(
        calls,
        internal_calls=internal_calls,
    )

    usage_receipt = _mapping(run_receipt.get("usage"))
    expected_total = sum(call["usage"]["total_tokens"] for call in calls)
    if usage_receipt is None or usage_receipt.get("llm_call_count") != len(calls) or usage_receipt.get("total_tokens") != expected_total:
        _fail("PROVIDER_MODEL_RECEIPT_INVALID")
    _validate_embedded_gateway_receipts(
        run_receipt,
        calls=calls,
        effective_model=effective_model,
        expected_total=expected_total,
        expected_agent_artifact_sha256=expected_agent_artifact_sha256,
    )
    writer_trace = [
        {
            "run_name": call["caller"].removeprefix("middleware:"),
            "call_index": local_index,
            "llm_call_index": call["llm_call_index"],
            "status": call["status"],
            "model_name": call["model_name"],
            "usage": call["usage"],
        }
        for local_index, call in enumerate(internal_calls, start=1)
    ]
    return {
        "gateway_binding_verified": True,
        "provider_receipts_verified": True,
        "model_identity_sha256": _model_identity(effective_model),
        "lead_recovery_count": lead_recovery_count,
        "writer_model_trace": writer_trace,
    }


def classify_evidence(
    *,
    execution_source: str,
    case_id: str,
    run_receipt: Mapping[str, Any],
    expected_agent_artifact_sha256: str,
    live_gate_verified: bool,
    owner_baseline_empty: bool,
    behavior_passed: bool,
) -> dict[str, Any]:
    if execution_source in SYNTHETIC_SOURCES:
        return {
            "evidence_class": "synthetic_contract",
            "ledger_eligible": False,
        }
    if execution_source != LIVE_SOURCE:
        return {"evidence_class": "unverified", "ledger_eligible": False}
    try:
        validate_live_run_receipt(
            run_receipt,
            case_id=case_id,
            expected_agent_artifact_sha256=expected_agent_artifact_sha256,
        )
    except AcceptanceError:
        return {"evidence_class": "unverified", "ledger_eligible": False}
    if not (live_gate_verified and owner_baseline_empty and behavior_passed):
        return {"evidence_class": "unverified", "ledger_eligible": False}
    return {"evidence_class": "live_default_agent", "ledger_eligible": True}


def _raw_backup_record_to_lineage(
    dataset_name: str,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    value = dict(record)
    if dataset_name == "editorial_program_versions":
        value["decision"] = value.pop("decision_json", None)
        for key in (
            "owner_user_id",
            "operation_key",
            "operation_digest",
            "created_by_run_id",
            "created_at",
        ):
            value.pop(key, None)
    elif dataset_name == "content_works":
        value["objective"] = value.pop("objective_json", None)
        for key in ("operation_digest", "created_at", "updated_at"):
            value.pop(key, None)
    elif dataset_name == "direction_versions":
        value["breakdown_version_ids"] = value.pop("breakdown_version_ids_json", None)
        value["objective_snapshot"] = value.pop("objective_snapshot_json", None)
        value["direction"] = value.pop("direction_json", None)
        for key in ("commit_key", "commit_digest", "created_at"):
            value.pop(key, None)
    elif dataset_name == "script_versions":
        value["claim_basis"] = value.pop("claim_basis_json", None)
        value["creative_elements"] = value.pop("creative_elements_json", None)
        value["story_engine_seed"] = value.pop("story_engine_seed_json", None)
        value["production_notes"] = value.pop("production_notes_json", None)
        for key in ("commit_key", "commit_digest", "created_at"):
            value.pop(key, None)
    return value


def _canonical_lineage_backup_projection(
    dataset_name: str,
    value: Mapping[str, Any],
) -> dict[str, Any]:
    projected = dict(value)
    projected.pop("created_at", None)
    if dataset_name == "content_works":
        projected.pop("updated_at", None)
    if dataset_name in {"direction_versions", "script_versions"}:
        projected.pop("commit_key", None)
    return projected


def validate_post_run_owner_backup(
    backup: Mapping[str, Any],
    *,
    lineage: Mapping[str, Any],
    gateway_export_receipt: Mapping[str, Any] | None,
    expected_owner_user_id: str,
) -> dict[str, Any]:
    work = _mapping(lineage.get("content_work"))
    program = _mapping(lineage.get("editorial_program_version"))
    directions = _sequence(lineage.get("direction_versions"))
    scripts = _sequence(lineage.get("script_versions"))
    if work is None or program is None or directions is None or scripts is None or len(directions) != 1 or len(scripts) != 1:
        _fail("OWNER_POST_RUN_LINEAGE_MISMATCH")
    owner = work.get("owner_user_id")
    if not isinstance(owner, str) or not owner or owner != expected_owner_user_id:
        _fail("OWNER_POST_RUN_LINEAGE_MISMATCH")
    try:
        records, record_count = _validate_v5_backup_structure(
            backup,
            expected_owner_user_id=owner,
            require_empty=False,
        )
        _validate_gateway_export_receipt(backup, gateway_export_receipt)
    except AcceptanceError as exc:
        if exc.code == "OWNER_BASELINE_OWNER_MISMATCH":
            _fail("OWNER_POST_RUN_LINEAGE_MISMATCH")
        raise

    required = {
        "editorial_program_versions": program,
        "content_works": work,
        "direction_versions": directions[0],
        "script_versions": scripts[0],
    }
    if record_count != 4:
        _fail("OWNER_POST_RUN_LINEAGE_MISMATCH")
    for dataset_name in EXPORT_DATASET_NAMES:
        expected_count = 1 if dataset_name in required else 0
        if len(records.get(dataset_name, [])) != expected_count:
            _fail("OWNER_POST_RUN_LINEAGE_MISMATCH")
    for dataset_name, expected_projection in required.items():
        record = records[dataset_name][0]
        if record.get("owner_user_id") != owner:
            _fail("OWNER_POST_RUN_LINEAGE_MISMATCH")
        actual_projection = _canonical_lineage_backup_projection(
            dataset_name,
            _raw_backup_record_to_lineage(dataset_name, record),
        )
        expected = _canonical_lineage_backup_projection(
            dataset_name,
            expected_projection,
        )
        if actual_projection != expected:
            _fail("OWNER_POST_RUN_LINEAGE_MISMATCH")

    run_id = work.get("created_by_run_id")
    thread_id = work.get("thread_id")
    if not isinstance(run_id, str) or not run_id or not isinstance(thread_id, str) or not thread_id or any(records[name][0].get("created_by_run_id") != run_id for name in required):
        _fail("OWNER_POST_RUN_LINEAGE_MISMATCH")
    return {
        "owner_user_id": owner,
        "record_count": record_count,
        "thread_id": thread_id,
        "run_id": run_id,
        "backup_sha256": _sha256_json(backup),
        "gateway_export_bound": True,
    }


def _writer_trace_without_provider_claim(
    run_receipt: Mapping[str, Any],
) -> list[dict[str, Any]]:
    raw_calls = _sequence(run_receipt.get("llm_calls")) or []
    internal: list[Mapping[str, Any]] = []
    for raw in raw_calls:
        call = _mapping(raw)
        if call is None:
            continue
        caller = call.get("caller")
        if isinstance(caller, str) and caller.startswith("middleware:ip-agent-"):
            internal.append(call)
    internal.sort(key=lambda item: item.get("llm_call_index") if type(item.get("llm_call_index")) is int else 2**63)
    return [
        {
            "run_name": str(call.get("caller")).removeprefix("middleware:"),
            "call_index": index,
            "llm_call_index": call.get("llm_call_index"),
            "status": call.get("status"),
        }
        for index, call in enumerate(internal, start=1)
    ]


def _owner_backup_envelope(
    value: Any,
) -> tuple[Mapping[str, Any], Mapping[str, Any] | None]:
    envelope = _mapping(value)
    if envelope is None:
        _fail("OWNER_POST_RUN_LINEAGE_MISMATCH")
    # The six-artifact contract stores the post-run export.  ``after`` is
    # accepted only for forward compatibility with early private canaries.
    if isinstance(envelope.get("after"), Mapping):
        envelope = envelope["after"]
    backup = _mapping(envelope.get("backup"))
    receipt = _mapping(envelope.get("gateway_export_receipt"))
    if backup is None:
        _fail("OWNER_POST_RUN_LINEAGE_MISMATCH")
    return backup, receipt


def _derive_packet(
    manifest: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    *,
    enforce_success: bool,
) -> dict[str, Any]:
    case_id = manifest.get("case_id")
    if case_id not in {case.case_id for case in _CANONICAL_FROZEN_CASES}:
        _fail("UNKNOWN_CASE")
    expected_artifact = manifest.get("agent_artifact_sha256")
    if not isinstance(expected_artifact, str) or not HEX_64.fullmatch(expected_artifact):
        _fail("GATEWAY_PRODUCT_BINDING_MISMATCH")

    run_receipt = _mapping(artifacts.get("run-receipt.json"))
    tool_receipt = _mapping(artifacts.get("tool-receipt.json"))
    lineage = _mapping(artifacts.get("lineage.json"))
    final_text = artifacts.get("answer.txt")
    if run_receipt is None or tool_receipt is None or lineage is None or not isinstance(final_text, str):
        _fail("BEHAVIOR_ACCEPTANCE_FAILED")

    provider: dict[str, Any] | None = None
    provider_error: AcceptanceError | None = None
    try:
        provider = validate_live_run_receipt(
            run_receipt,
            case_id=case_id,
            expected_agent_artifact_sha256=expected_artifact,
        )
    except AcceptanceError as exc:
        provider_error = exc
        if enforce_success and manifest.get("execution_source") == LIVE_SOURCE:
            raise
    lead_recovery_count = int(provider["lead_recovery_count"]) if provider is not None else 0
    writer_trace = provider["writer_model_trace"] if provider is not None else _writer_trace_without_provider_claim(run_receipt)
    tool_trace = _sequence(tool_receipt.get("tool_trace")) or []
    checkpoint_verified = False
    checkpoint_error: AcceptanceError | None = None
    if provider is not None:
        try:
            _validate_checkpoint_artifacts(
                run_receipt,
                lineage=lineage,
                tool_trace=tool_trace,
                final_text=final_text,
                lead_recovery_count=lead_recovery_count,
            )
            checkpoint_verified = True
        except AcceptanceError as exc:
            checkpoint_error = exc
            if enforce_success:
                raise
    behavior = evaluate_writer_behavior_acceptance(
        scenario_id=case_id,
        lineage=lineage,
        tool_trace=tool_trace,
        writer_model_trace=writer_trace,
        final_text=final_text,
    )
    if enforce_success and not behavior.passed:
        _fail("BEHAVIOR_ACCEPTANCE_FAILED")

    post_backup: dict[str, Any] | None = None
    post_error: AcceptanceError | None = None
    try:
        backup, export_receipt = _owner_backup_envelope(artifacts.get("owner-backup-v5.json"))
        post_backup = validate_post_run_owner_backup(
            backup,
            lineage=lineage,
            gateway_export_receipt=export_receipt,
            expected_owner_user_id="default",
        )
    except AcceptanceError as exc:
        post_error = exc
        if enforce_success:
            raise
    if manifest.get("status") != "passed" or post_backup is None or not checkpoint_verified:
        evidence = {
            "evidence_class": "failed_acceptance",
            "ledger_eligible": False,
        }
    else:
        evidence = classify_evidence(
            execution_source=str(manifest.get("execution_source") or ""),
            case_id=case_id,
            run_receipt=run_receipt,
            expected_agent_artifact_sha256=expected_artifact,
            live_gate_verified=True,
            owner_baseline_empty=True,
            behavior_passed=behavior.passed,
        )
    return {
        **evidence,
        "gateway_binding_verified": provider is not None,
        "provider_receipts_verified": provider is not None,
        "checkpoint_receipts_verified": checkpoint_verified,
        "model_identity_sha256": (provider["model_identity_sha256"] if provider is not None else None),
        "lead_recovery_count": lead_recovery_count,
        "writer_model_trace": writer_trace,
        "behavior_passed": behavior.passed,
        "behavior_failure_codes": list(behavior.failure_codes),
        "route_kind": behavior.route_kind,
        "story_mode": behavior.story_mode,
        "owner_post_run_verified": post_backup is not None,
        "owner_post_run_receipt": post_backup,
        "provider_error": provider_error.code if provider_error else None,
        "checkpoint_error": checkpoint_error.code if checkpoint_error else None,
        "owner_post_run_error": post_error.code if post_error else None,
    }


def _validate_manifest_claims(
    manifest: Mapping[str, Any],
    derived: Mapping[str, Any],
) -> None:
    claim_keys = (
        "evidence_class",
        "ledger_eligible",
        "gateway_binding_verified",
        "provider_receipts_verified",
        "checkpoint_receipts_verified",
        "model_identity_sha256",
        "lead_recovery_count",
        "behavior_passed",
        "owner_post_run_verified",
    )
    if any(key in manifest and manifest.get(key) != derived.get(key) for key in claim_keys):
        _fail("EVIDENCE_CLASSIFICATION_INVALID")


def _artifact_bytes(name: str, value: Any) -> bytes:
    if name == "answer.txt":
        if not isinstance(value, str):
            _fail("LIVE_PACKET_ARTIFACTS_INCOMPLETE")
        return value.encode("utf-8")
    try:
        return _canonical_json_bytes(value) + b"\n"
    except (TypeError, ValueError):
        _fail("LIVE_PACKET_ARTIFACTS_INCOMPLETE")


def _write_private(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def write_result_packet(
    destination: Path,
    *,
    manifest: Mapping[str, Any],
    artifacts: Mapping[str, Any],
) -> Path:
    destination = destination.resolve()
    if destination.exists() or destination.is_symlink():
        _fail("RESULT_DIRECTORY_ALREADY_EXISTS")
    if set(artifacts) != set(LIVE_ARTIFACT_NAMES):
        _fail("LIVE_PACKET_ARTIFACTS_INCOMPLETE")
    status = manifest.get("status")
    if status not in {"passed", "failed"}:
        _fail("EVIDENCE_CLASSIFICATION_INVALID")
    if not HEX_40.fullmatch(str(manifest.get("git_commit", ""))):
        _fail("EVIDENCE_CLASSIFICATION_INVALID")
    enforce_success = status == "passed"
    derived = _derive_packet(
        manifest,
        artifacts,
        enforce_success=enforce_success,
    )
    _validate_manifest_claims(manifest, derived)

    artifact_payloads = {name: _artifact_bytes(name, artifacts[name]) for name in LIVE_ARTIFACT_NAMES}
    artifact_receipts = {
        name: {
            "sha256": _sha256_bytes(content),
            "size_bytes": len(content),
        }
        for name, content in artifact_payloads.items()
    }
    sealed_manifest = {
        **dict(manifest),
        "schema_version": PACKET_SCHEMA,
        **{
            key: value
            for key, value in derived.items()
            if key
            not in {
                "provider_error",
                "checkpoint_error",
                "owner_post_run_error",
            }
        },
        "artifacts": artifact_receipts,
    }
    manifest_bytes = _canonical_json_bytes(sealed_manifest) + b"\n"
    sidecar_bytes = (_sha256_bytes(manifest_bytes) + "\n").encode("ascii")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir(mode=0o700)
        for name, content in artifact_payloads.items():
            _write_private(destination / name, content)
        _write_private(destination / "manifest.json", manifest_bytes)
        _write_private(destination / "manifest.json.sha256", sidecar_bytes)
    except Exception:
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        raise
    return destination


def _read_packet_artifacts(destination: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_files = {
        *LIVE_ARTIFACT_NAMES,
        "manifest.json",
        "manifest.json.sha256",
    }
    if not destination.is_dir() or destination.is_symlink() or {path.name for path in destination.iterdir()} != expected_files or any(path.is_symlink() or not path.is_file() for path in destination.iterdir()):
        _fail("RESULT_DIGEST_MISMATCH")
    manifest_bytes = (destination / "manifest.json").read_bytes()
    sidecar = (destination / "manifest.json.sha256").read_text(encoding="ascii")
    if sidecar != _sha256_bytes(manifest_bytes) + "\n":
        _fail("RESULT_DIGEST_MISMATCH")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeError, json.JSONDecodeError):
        _fail("RESULT_DIGEST_MISMATCH")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != PACKET_SCHEMA:
        _fail("RESULT_DIGEST_MISMATCH")
    inventory = _mapping(manifest.get("artifacts"))
    if inventory is None or set(inventory) != set(LIVE_ARTIFACT_NAMES):
        _fail("RESULT_DIGEST_MISMATCH")

    artifacts: dict[str, Any] = {}
    for name in LIVE_ARTIFACT_NAMES:
        content = (destination / name).read_bytes()
        receipt = _mapping(inventory.get(name))
        if receipt is None or receipt.get("sha256") != _sha256_bytes(content) or receipt.get("size_bytes") != len(content):
            _fail("RESULT_DIGEST_MISMATCH")
        if name == "answer.txt":
            try:
                artifacts[name] = content.decode("utf-8")
            except UnicodeError:
                _fail("RESULT_DIGEST_MISMATCH")
        else:
            try:
                artifacts[name] = json.loads(content)
            except (UnicodeError, json.JSONDecodeError):
                _fail("RESULT_DIGEST_MISMATCH")
    return manifest, artifacts


def verify_result_packet(destination: Path) -> dict[str, Any]:
    manifest, artifacts = _read_packet_artifacts(destination.resolve())
    derived = _derive_packet(
        manifest,
        artifacts,
        enforce_success=manifest.get("status") == "passed",
    )
    _validate_manifest_claims(manifest, derived)
    for key, value in derived.items():
        if key in {
            "provider_error",
            "checkpoint_error",
            "owner_post_run_error",
        }:
            continue
        if manifest.get(key) != value:
            _fail("EVIDENCE_CLASSIFICATION_INVALID")
    return manifest


def verify_matrix(packet_paths: Sequence[Path]) -> dict[str, Any]:
    if len(packet_paths) != len(_CANONICAL_FROZEN_CASES):
        _fail("MATRIX_CASE_SET_INVALID")
    packets = [verify_result_packet(Path(path)) for path in packet_paths]
    by_case: dict[str, dict[str, Any]] = {}
    for packet in packets:
        case_id = packet.get("case_id")
        if not isinstance(case_id, str) or case_id in by_case:
            _fail("MATRIX_CASE_SET_INVALID")
        by_case[case_id] = packet
    expected_ids = tuple(case.case_id for case in _CANONICAL_FROZEN_CASES)
    if set(by_case) != set(expected_ids):
        _fail("MATRIX_CASE_SET_INVALID")
    ordered = [by_case[case_id] for case_id in expected_ids]
    if any(packet.get("status") != "passed" for packet in ordered):
        _fail("MATRIX_CASE_FAILED")
    commits = {packet.get("git_commit") for packet in ordered}
    if len(commits) != 1:
        _fail("MATRIX_COMMIT_MISMATCH")
    artifacts = {packet.get("agent_artifact_sha256") for packet in ordered}
    if len(artifacts) != 1:
        _fail("MATRIX_AGENT_ARTIFACT_MISMATCH")
    models = {packet.get("model_identity_sha256") for packet in ordered}
    if len(models) != 1:
        _fail("MATRIX_MODEL_MISMATCH")
    all_live = all(packet.get("evidence_class") == "live_default_agent" and packet.get("ledger_eligible") is True for packet in ordered)
    return {
        "status": "passed",
        "case_ids": list(expected_ids),
        "git_commit": next(iter(commits)),
        "agent_artifact_sha256": next(iter(artifacts)),
        "model_identity_sha256": next(iter(models)),
        "lead_recovery_count_by_case": {case_id: by_case[case_id]["lead_recovery_count"] for case_id in expected_ids},
        "evidence_class": ("live_default_agent" if all_live else "synthetic_contract"),
        "ledger_eligible": all_live,
    }


def _json_response(response: httpx.Response, code: str) -> Any:
    try:
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, json.JSONDecodeError, UnicodeError):
        _fail(code)


def _gateway_export(
    client: httpx.Client,
    *,
    base_url: str,
    evidence_sink: MutableMapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    response = client.get("/api/personal-ip/data/export")
    failure_receipt = {
        "schema_version": "personal-ip-writer-v2-gateway-export-failure-receipt-v1",
        "method": "GET",
        "base_url": base_url,
        "path": "/api/personal-ip/data/export",
        "status_code": response.status_code,
        "cache_control": response.headers.get("Cache-Control"),
        "content_disposition": response.headers.get("Content-Disposition"),
        "wire_body_sha256": _sha256_bytes(response.content),
        "wire_body_size_bytes": len(response.content),
    }
    try:
        response.raise_for_status()
        value = response.json()
    except (httpx.HTTPError, json.JSONDecodeError, UnicodeError):
        if evidence_sink is not None:
            evidence_sink["gateway_export_failure_receipt"] = failure_receipt
        _fail("OWNER_BACKUP_GATEWAY_RECEIPT_INVALID")
    if not isinstance(value, dict):
        if evidence_sink is not None:
            evidence_sink["gateway_export_failure_receipt"] = failure_receipt
        _fail("OWNER_BACKUP_GATEWAY_RECEIPT_INVALID")
    receipt = {
        "schema_version": EXPORT_RECEIPT_SCHEMA,
        "method": "GET",
        "base_url": base_url,
        "path": "/api/personal-ip/data/export",
        "status_code": response.status_code,
        "cache_control": response.headers.get("Cache-Control"),
        "content_disposition": response.headers.get("Content-Disposition"),
        "body_sha256": _sha256_json(value),
    }
    if evidence_sink is not None:
        evidence_sink.update(
            {
                "backup": value,
                "gateway_export_receipt": receipt,
            }
        )
    return value, receipt


def _gateway_auth_receipt(client: httpx.Client) -> dict[str, Any]:
    response = client.get("/api/v1/auth/me")
    user = _json_response(response, "AUTH_DISABLED_TEST_OWNER_REQUIRED")
    expected = {
        "id": "default",
        "email": "default@test.local",
        "system_role": "admin",
        "needs_setup": False,
        "oauth_provider": None,
    }
    if user != expected:
        _fail("AUTH_DISABLED_TEST_OWNER_REQUIRED")
    return {
        "schema_version": "personal-ip-writer-v2-auth-receipt-v1",
        "method": "GET",
        "path": "/api/v1/auth/me",
        "status_code": response.status_code,
        "user": expected,
    }


def _new_loopback_gateway_client(*, base_url: str, client_factory: Any) -> Any:
    """Build the local evidence client without consulting host proxy settings."""

    return client_factory(
        base_url=base_url,
        timeout=httpx.Timeout(600.0, connect=10.0),
        trust_env=False,
    )


def _iter_sse(lines: Iterable[str]) -> Iterable[tuple[str, Any]]:
    event_name = "message"
    data_lines: list[str] = []
    for line in lines:
        if line.startswith(":"):
            continue
        if line == "":
            if data_lines:
                raw = "\n".join(data_lines)
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = raw
                yield event_name, data
            event_name = "message"
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").lstrip())
    if data_lines:
        raw = "\n".join(data_lines)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = raw
        yield event_name, data


def _run_id_from_location(location: str | None) -> str | None:
    if not location:
        return None
    parts = [part for part in urlsplit(location).path.split("/") if part]
    if len(parts) >= 2 and parts[-2] == "runs" and parts[-1]:
        return parts[-1]
    return None


def _fetch_run_events(
    client: httpx.Client,
    *,
    thread_id: str,
    run_id: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    after_seq: int | None = None
    while True:
        params: dict[str, Any] = {"limit": 2000}
        if after_seq is not None:
            params["after_seq"] = after_seq
        response = client.get(
            f"/api/threads/{thread_id}/runs/{run_id}/events",
            params=params,
        )
        batch = _json_response(response, "GATEWAY_EVENT_RECEIPT_INVALID")
        if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
            _fail("GATEWAY_EVENT_RECEIPT_INVALID")
        events.extend(batch)
        if len(batch) < 2000:
            break
        sequences = [item.get("seq") for item in batch if type(item.get("seq")) is int]
        if not sequences or max(sequences) == after_seq:
            _fail("GATEWAY_EVENT_RECEIPT_INVALID")
        after_seq = max(sequences)
    events.sort(key=lambda item: item.get("seq") if type(item.get("seq")) is int else 2**63)
    return events


def _text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for block in value:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, Mapping) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def _checkpoint_messages(state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = _mapping(state.get("values"))
    messages = _sequence(values.get("messages")) if values else None
    if messages is None:
        _fail("CHECKPOINT_RECEIPT_INVALID")
    result: list[Mapping[str, Any]] = []
    for message in messages:
        mapped = _mapping(message)
        if mapped is None:
            _fail("CHECKPOINT_RECEIPT_INVALID")
        result.append(mapped)
    return result


def _checkpoint_answer(messages: Sequence[Mapping[str, Any]]) -> str:
    answers: list[str] = []
    for message in messages:
        if message.get("type") not in {"ai", "assistant"}:
            continue
        additional = _mapping(message.get("additional_kwargs")) or {}
        if additional.get("hide_from_ui") is True:
            continue
        text = _text_content(message.get("content")).strip()
        if text:
            answers.append(text)
    if not answers:
        _fail("FINAL_ANSWER_MISSING")
    return answers[-1]


def _decode_tool_result(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, Mapping) else None
    return None


def _checkpoint_tool_trace(
    messages: Sequence[Mapping[str, Any]],
    *,
    lineage: Mapping[str, Any],
    run_id: str,
    thread_id: str,
    expected_lead_recovery_count: int,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    call_positions: list[int] = []
    answer_positions: list[int] = []
    results: dict[str, Mapping[str, Any]] = {}
    result_status: dict[str, Any] = {}
    result_names: dict[str, Any] = {}
    tool_message_ids: list[Any] = []
    tool_message_positions: list[int] = []
    for position, message in enumerate(messages):
        if message.get("type") in {"ai", "assistant"}:
            additional = _mapping(message.get("additional_kwargs")) or {}
            raw_calls_value = message.get("tool_calls", [])
            raw_calls = _sequence(raw_calls_value)
            raw_invalid = _sequence(message.get("invalid_tool_calls", []))
            if raw_calls is None or raw_invalid is None or raw_invalid or additional.get("deerflow_error_fallback") is True:
                _fail("TOOL_RECEIPT_INVALID")
            sealed_invalid = _validated_invalid_tool_receipts(
                message.get("acceptance_invalid_tool_calls", []),
            )
            if sealed_invalid:
                _fail("TOOL_RECEIPT_INVALID")
            if _text_content(message.get("content")).strip():
                answer_positions.append(position)
            for raw in raw_calls:
                call = _mapping(raw)
                if call is None:
                    _fail("TOOL_RECEIPT_INVALID")
                call_id = call.get("id")
                name = call.get("name")
                arguments = call.get("args")
                if not isinstance(call_id, str) or not isinstance(name, str) or not isinstance(arguments, Mapping):
                    _fail("TOOL_RECEIPT_INVALID")
                calls.append(
                    {
                        "call_id": call_id,
                        "name": name,
                        "arguments": dict(arguments),
                    }
                )
                call_positions.append(position)
        elif message.get("type") == "tool":
            call_id = message.get("tool_call_id")
            tool_message_ids.append(call_id)
            tool_message_positions.append(position)
            if isinstance(call_id, str):
                decoded = _decode_tool_result(message.get("content"))
                if decoded is not None:
                    results[call_id] = decoded
                    result_status[call_id] = message.get("status")
                    result_names[call_id] = message.get("name")
    if (
        expected_lead_recovery_count not in {0, 1}
        or len(calls) != 1
        or calls[0].get("name") != "ip_content_write"
        or tool_message_ids != [calls[0].get("call_id")]
        or len(call_positions) != 1
        or len(tool_message_positions) != 1
        or not answer_positions
        or not (call_positions[0] < tool_message_positions[0] < answer_positions[-1])
    ):
        _fail("TOOL_RECEIPT_INVALID")
    call = calls[0]
    result = results.get(call["call_id"])
    work = _mapping(lineage.get("content_work"))
    if (
        result is None
        or result.get("operation_status") != "ok"
        or work is None
        or work.get("created_by_run_id") != run_id
        or work.get("thread_id") != thread_id
        or work.get("operation_key") != f"{run_id}:{call['call_id']}"
        or result_names.get(call["call_id"]) != "ip_content_write"
        or result_status.get(call["call_id"]) != "success"
    ):
        _fail("TOOL_RECEIPT_INVALID")
    return [
        {
            **call,
            "status": "ok",
            "owner_user_id": work.get("owner_user_id"),
            "run_id": run_id,
            "thread_id": thread_id,
            "result": dict(result),
        }
    ]


def _validate_checkpoint_artifacts(
    run_receipt: Mapping[str, Any],
    *,
    lineage: Mapping[str, Any],
    tool_trace: Sequence[Mapping[str, Any]],
    final_text: str,
    lead_recovery_count: int,
) -> None:
    try:
        embedded = _mapping(run_receipt.get("gateway_receipts"))
        checkpoint = _mapping(embedded.get("checkpoint")) if embedded else None
        state = _mapping(checkpoint.get("state")) if checkpoint else None
        if state is None or state.get("next") != [] or state.get("tasks") != []:
            _fail("CHECKPOINT_RECEIPT_INVALID")
        messages = _checkpoint_messages(state)
        checkpoint_answer = _checkpoint_answer(messages)
        checkpoint_tool_trace = _checkpoint_tool_trace(
            messages,
            lineage=lineage,
            run_id=str(run_receipt.get("run_id") or ""),
            thread_id=str(run_receipt.get("thread_id") or ""),
            expected_lead_recovery_count=lead_recovery_count,
        )
    except AcceptanceError:
        _fail("CHECKPOINT_RECEIPT_INVALID")
    if checkpoint_answer != final_text or checkpoint_tool_trace != list(tool_trace):
        _fail("CHECKPOINT_RECEIPT_INVALID")


def _provider_name(configured_name: str, provider_model: str) -> str:
    normalized = f"{configured_name} {provider_model}".casefold()
    if "doubao" in normalized or "volcengine" in normalized:
        return "volcengine"
    if "claude" in normalized:
        return "anthropic"
    if any(marker in normalized for marker in ("gpt", "o1", "o3", "o4")):
        return "openai"
    return "provider"


def _event_model_name(event: Mapping[str, Any]) -> str | None:
    content = _mapping(event.get("content"))
    response_metadata = _mapping(content.get("response_metadata")) if content else None
    if response_metadata:
        value = response_metadata.get("model_name") or response_metadata.get("model")
        if isinstance(value, str) and value:
            return value
    return None


def _gateway_model_receipt(
    client: httpx.Client,
    *,
    events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    runtime_model: str | None = None
    for event in events:
        if event.get("event_type") != "run.start":
            continue
        metadata = _mapping(event.get("metadata")) or {}
        candidate = metadata.get("model_name")
        if isinstance(candidate, str) and candidate:
            runtime_model = candidate
            break
    llm_events = [event for event in events if event.get("event_type") == "llm.ai.response"]
    event_models = [_event_model_name(event) for event in llm_events]
    if not llm_events or any(model is None for model in event_models):
        _fail("GATEWAY_MODEL_RECEIPT_INVALID")
    actual_models = {str(model) for model in event_models}
    response = client.get("/api/models")
    payload = _json_response(response, "GATEWAY_MODEL_RECEIPT_INVALID")
    models = payload.get("models") if isinstance(payload, Mapping) else None
    if not isinstance(models, list):
        _fail("GATEWAY_MODEL_RECEIPT_INVALID")
    candidates = [item for item in models if isinstance(item, Mapping)]
    selected = next(
        (item for item in candidates if item.get("name") == runtime_model),
        None,
    )
    if selected is None and len(actual_models) == 1:
        actual = next(iter(actual_models))
        selected = next(
            (item for item in candidates if item.get("model") == actual),
            None,
        )
    if selected is None or not isinstance(selected.get("name"), str) or not isinstance(selected.get("model"), str):
        _fail("GATEWAY_MODEL_RECEIPT_INVALID")
    if actual_models and actual_models != {selected["model"]}:
        _fail("GATEWAY_MODEL_RECEIPT_INVALID")
    effective_digest = selected.get("effective_config_sha256")
    if not HEX_64.fullmatch(str(effective_digest or "")):
        _fail("GATEWAY_MODEL_RECEIPT_INVALID")
    return {
        "schema_version": "personal-ip-writer-v2-gateway-model-receipt-v1",
        "configured_name": selected["name"],
        "provider_model": selected["model"],
        "provider": _provider_name(selected["name"], selected["model"]),
        "effective_config_sha256": effective_digest,
    }


def _build_live_run_receipt(
    *,
    run: Mapping[str, Any],
    state: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    token_usage: Mapping[str, Any],
    model_receipt: Mapping[str, Any],
    thread_id: str,
    run_id: str,
    expected_agent_artifact_sha256: str,
    owner_baseline: Mapping[str, Any],
) -> dict[str, Any]:
    metadata = _mapping(run.get("metadata")) or {}
    product = _mapping(metadata.get("deerflow_product_runtime"))
    if (
        product is None
        or product.get("schema_version") != "product-runtime-binding-v1"
        or product.get("product_id") != "ip-agent"
        or product.get("entrypoint") != "customer_run"
        or product.get("assistant_id") != "ip-agent"
        or product.get("agent_artifact_sha256") != expected_agent_artifact_sha256
        or product.get("declared_capability_digest") != _product_capability_digest(expected_agent_artifact_sha256)
    ):
        _fail("GATEWAY_PRODUCT_BINDING_MISMATCH")
    sealed_events = _seal_gateway_events(events)
    sealed_state = _seal_checkpoint_state(state)
    llm_calls: list[dict[str, Any]] = []
    for event in sealed_events:
        if event.get("event_type") != "llm.ai.response":
            continue
        event_metadata = _mapping(event.get("metadata")) or {}
        usage = _mapping(event_metadata.get("usage")) or {}
        content = _mapping(event.get("content")) or {}
        additional = _mapping(content.get("additional_kwargs")) or {}
        caller = event_metadata.get("caller")
        call = {
            "llm_call_index": event_metadata.get("llm_call_index"),
            "caller": caller,
            "model_name": _event_model_name(event),
            "status": ("error" if additional.get("deerflow_error_fallback") is True else "success"),
            "usage": {
                "input_tokens": int(usage.get("input_tokens") or 0),
                "output_tokens": int(usage.get("output_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
            "event_seq": event.get("seq"),
        }
        if caller == "lead_agent":
            call["lead_tool_receipt"] = _lead_tool_receipt_from_content(content)
        llm_calls.append(call)
    total_tokens = sum(call["usage"]["total_tokens"] for call in llm_calls)
    return {
        "schema_version": RUN_RECEIPT_SCHEMA,
        "run_id": run_id,
        "thread_id": thread_id,
        "status": run.get("status"),
        "runtime_metadata": {
            "product_id": product.get("product_id"),
            "assistant_id": run.get("assistant_id"),
            "agent_artifact_sha256": product.get("agent_artifact_sha256"),
            "runtime_profile_agent_artifact_sha256": expected_agent_artifact_sha256,
            "product_binding": dict(product),
            "effective_model": {
                "configured_name": model_receipt.get("configured_name"),
                "provider": model_receipt.get("provider"),
                "provider_model": model_receipt.get("provider_model"),
                "effective_config_sha256": model_receipt.get("effective_config_sha256"),
            },
        },
        "usage": {
            "llm_call_count": len(llm_calls),
            "total_tokens": total_tokens,
        },
        "llm_calls": llm_calls,
        "gateway_receipts": {
            "run": dict(run),
            "checkpoint": {
                "state": sealed_state,
                "checkpoint": sealed_state.get("checkpoint"),
                "checkpoint_id": sealed_state.get("checkpoint_id"),
                "next": sealed_state.get("next"),
                "values_sha256": _sha256_json(sealed_state.get("values")),
            },
            "events": sealed_events,
            "token_usage": dict(token_usage),
            "model": dict(model_receipt),
            "owner_baseline": dict(owner_baseline),
        },
    }


LIVE_SOURCE_PATHS = (
    "scripts/personal_ip_writer_v2_acceptance.py",
    "scripts/personal_ip_writer_v2_acceptance_oracle.py",
)


def _git_clean_commit(root: Path) -> str:
    try:
        commit_result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        for relative_path in LIVE_SOURCE_PATHS:
            subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", relative_path],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        status_result = subprocess.run(
            [
                "git",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignore-submodules=none",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        if "commit_result" not in locals():
            _fail("GIT_COMMIT_UNAVAILABLE")
        _fail("LIVE_SOURCE_NOT_TRACKED")
    commit = commit_result.stdout.strip()
    if not HEX_40.fullmatch(commit):
        _fail("GIT_COMMIT_UNAVAILABLE")
    if status_result.stdout:
        _fail("LIVE_SOURCE_TREE_NOT_CLEAN")
    return commit


def _failed_artifacts(
    *,
    case: FrozenCase,
    error: BaseException,
    partial: Mapping[str, Any],
) -> dict[str, Any]:
    error_code = getattr(error, "code", type(error).__name__)
    failure_stage = str(partial.get("_failure_stage") or "unknown")
    run_receipt = dict(
        partial.get(
            "run-receipt.json",
            {
                "schema_version": RUN_RECEIPT_SCHEMA,
                "status": "error",
                "runtime_metadata": {},
                "usage": {"llm_call_count": 0, "total_tokens": 0},
                "llm_calls": [],
            },
        )
    )
    run_receipt["acceptance_failure"] = {
        "stage": failure_stage,
        "error_code": error_code,
        "error_type": type(error).__name__,
    }
    return {
        "case-input.json": asdict(case),
        "answer.txt": f"Acceptance failed before a valid final answer: {error_code}",
        "run-receipt.json": run_receipt,
        "tool-receipt.json": partial.get(
            "tool-receipt.json",
            {
                "tool_trace": [],
                "failure_stage": failure_stage,
                "failure_code": error_code,
            },
        ),
        "lineage.json": partial.get("lineage.json", {}),
        "owner-backup-v5.json": partial.get(
            "owner-backup-v5.json",
            {"failure_stage": failure_stage, "failure_code": error_code},
        ),
    }


def run_live(
    *,
    root: Path,
    base_url: str,
    result_dir: Path,
    environment: Mapping[str, str],
    client_factory: Any = httpx.Client,
) -> Path:
    """Run exactly one real default-Agent canary without retrying."""

    case_id = validate_live_gate(environment)
    base_url = validate_loopback_gateway_url(base_url)
    root = root.resolve()
    result_dir = result_dir.resolve()
    if result_dir.exists() or result_dir.is_symlink():
        _fail("RESULT_DIRECTORY_ALREADY_EXISTS")
    commit = _git_clean_commit(root)
    _validate_frozen_catalog()
    artifact_digest, _profile = _validate_product_contract(root)
    clean_state = validate_clean_test_state(root)
    case = next(case for case in _CANONICAL_FROZEN_CASES if case.case_id == case_id)
    partial: dict[str, Any] = {
        "case-input.json": asdict(case),
        "_failure_stage": "gateway_client_construction",
    }

    try:
        client = _new_loopback_gateway_client(
            base_url=base_url,
            client_factory=client_factory,
        )
        manager = client if hasattr(client, "__enter__") else nullcontext(client)
        with manager as active_client:
            partial["_failure_stage"] = "gateway_auth_verification"
            auth_receipt = _gateway_auth_receipt(active_client)
            partial["_failure_stage"] = "pre_run_owner_export"
            baseline_evidence: dict[str, Any] = {"evidence_role": "pre_run_failure_context"}
            partial["owner-backup-v5.json"] = baseline_evidence
            baseline, baseline_export_receipt = _gateway_export(
                active_client,
                base_url=base_url,
                evidence_sink=baseline_evidence,
            )
            baseline_receipt = validate_empty_owner_baseline(
                baseline,
                expected_owner_user_id=str(clean_state["owner_user_id"]),
                gateway_export_receipt=baseline_export_receipt,
            )
            owner_baseline = {
                "backup": baseline,
                "gateway_export_receipt": baseline_export_receipt,
                "validation_receipt": baseline_receipt,
                "auth_receipt": auth_receipt,
            }

            partial["_failure_stage"] = "thread_creation"
            thread_id = str(uuid.uuid4())
            create = active_client.post(
                "/api/threads",
                json={
                    "thread_id": thread_id,
                    "assistant_id": "ip-agent",
                    "metadata": {
                        "acceptance_contract": PACKET_SCHEMA,
                        "acceptance_case": case_id,
                    },
                },
            )
            created = _json_response(create, "GATEWAY_THREAD_CREATE_FAILED")
            if not isinstance(created, Mapping) or created.get("thread_id") != thread_id:
                _fail("GATEWAY_THREAD_CREATE_FAILED")

            partial["_failure_stage"] = "run_stream"
            saw_end = False
            stream_errors: list[Any] = []
            with active_client.stream(
                "POST",
                f"/api/threads/{thread_id}/runs/stream",
                json={
                    "assistant_id": "ip-agent",
                    "input": {"messages": [{"role": "user", "content": case.prompt}]},
                    "context": {"thinking_enabled": False},
                    "stream_mode": ["values"],
                    "on_disconnect": "continue",
                    "on_completion": "keep",
                    "if_not_exists": "reject",
                },
            ) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPError:
                    _fail("GATEWAY_RUN_STREAM_FAILED")
                run_id = _run_id_from_location(response.headers.get("Content-Location"))
                for event_name, data in _iter_sse(response.iter_lines()):
                    if event_name == "end":
                        saw_end = True
                    elif event_name in {"error", "run_error"}:
                        stream_errors.append(data)
            if not saw_end or not run_id or stream_errors:
                _fail("GATEWAY_RUN_STREAM_FAILED")

            partial["_failure_stage"] = "run_receipt_collection"
            run_response = active_client.get(f"/api/threads/{thread_id}/runs/{run_id}")
            run = _json_response(run_response, "GATEWAY_RUN_RECEIPT_INVALID")
            state_response = active_client.get(f"/api/threads/{thread_id}/state")
            state = _json_response(state_response, "CHECKPOINT_RECEIPT_INVALID")
            token_response = active_client.get(f"/api/threads/{thread_id}/token-usage")
            token_usage = _json_response(token_response, "GATEWAY_TOKEN_RECEIPT_INVALID")
            if not all(isinstance(value, Mapping) for value in (run, state, token_usage)):
                _fail("GATEWAY_RUN_RECEIPT_INVALID")
            events = _fetch_run_events(
                active_client,
                thread_id=thread_id,
                run_id=run_id,
            )
            model_receipt = _gateway_model_receipt(
                active_client,
                events=events,
            )
            run_receipt = _build_live_run_receipt(
                run=run,
                state=state,
                events=events,
                token_usage=token_usage,
                model_receipt=model_receipt,
                thread_id=thread_id,
                run_id=run_id,
                expected_agent_artifact_sha256=artifact_digest,
                owner_baseline=owner_baseline,
            )
            partial["run-receipt.json"] = run_receipt
            provider_receipt = validate_live_run_receipt(
                run_receipt,
                case_id=case_id,
                expected_agent_artifact_sha256=artifact_digest,
            )

            partial["_failure_stage"] = "lineage_collection"
            works_response = active_client.get(
                "/api/personal-ip/content-works",
                params={"thread_id": thread_id, "limit": 2},
            )
            works = _json_response(works_response, "CONTENT_LINEAGE_RECEIPT_INVALID")
            if not isinstance(works, list) or len(works) != 1 or not isinstance(works[0], Mapping) or not isinstance(works[0].get("id"), str):
                _fail("CONTENT_LINEAGE_RECEIPT_INVALID")
            lineage_response = active_client.get(f"/api/personal-ip/content-works/{works[0]['id']}")
            lineage = _json_response(lineage_response, "CONTENT_LINEAGE_RECEIPT_INVALID")
            if not isinstance(lineage, Mapping):
                _fail("CONTENT_LINEAGE_RECEIPT_INVALID")
            partial["lineage.json"] = dict(lineage)
            sealed_gateway_receipts = _mapping(run_receipt.get("gateway_receipts"))
            sealed_checkpoint = _mapping(sealed_gateway_receipts.get("checkpoint")) if sealed_gateway_receipts else None
            sealed_state = _mapping(sealed_checkpoint.get("state")) if sealed_checkpoint else None
            if sealed_state is None:
                _fail("CHECKPOINT_RECEIPT_INVALID")
            messages = _checkpoint_messages(sealed_state)
            answer = _checkpoint_answer(messages)
            tool_trace = _checkpoint_tool_trace(
                messages,
                lineage=lineage,
                run_id=run_id,
                thread_id=thread_id,
                expected_lead_recovery_count=int(
                    provider_receipt["lead_recovery_count"],
                ),
            )
            partial["answer.txt"] = answer
            partial["tool-receipt.json"] = {
                "schema_version": "personal-ip-writer-v2-tool-receipt-v1",
                "checkpoint_id": sealed_state.get("checkpoint_id"),
                "tool_trace": tool_trace,
            }

            partial["_failure_stage"] = "post_run_owner_export"
            post_evidence: dict[str, Any] = {}
            partial["owner-backup-v5.json"] = post_evidence
            post_backup, post_export_receipt = _gateway_export(
                active_client,
                base_url=base_url,
                evidence_sink=post_evidence,
            )
            post_validation = validate_post_run_owner_backup(
                post_backup,
                lineage=lineage,
                gateway_export_receipt=post_export_receipt,
                expected_owner_user_id=str(clean_state["owner_user_id"]),
            )
            if post_validation.get("owner_user_id") != clean_state.get("owner_user_id"):
                _fail("OWNER_POST_RUN_LINEAGE_MISMATCH")
        partial["_failure_stage"] = "packet_sealing"
        artifacts = {name: partial[name] for name in LIVE_ARTIFACT_NAMES}
        return write_result_packet(
            result_dir,
            manifest={
                "case_id": case_id,
                "status": "passed",
                "git_commit": commit,
                "agent_artifact_sha256": artifact_digest,
                "execution_source": LIVE_SOURCE,
            },
            artifacts=artifacts,
        )
    except BaseException as exc:
        if not result_dir.exists():
            try:
                write_result_packet(
                    result_dir,
                    manifest={
                        "case_id": case_id,
                        "status": "failed",
                        "git_commit": commit,
                        "agent_artifact_sha256": artifact_digest,
                        "execution_source": LIVE_SOURCE,
                    },
                    artifacts=_failed_artifacts(
                        case=case,
                        error=exc,
                        partial=partial,
                    ),
                )
            except BaseException:
                pass
        raise


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Writer Brain v2 readiness, live canary and packet verifier",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("readiness", "live", "verify-packet", "verify-matrix"),
        default="readiness",
    )
    parser.add_argument("packets", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8001",
        help="Loopback Gateway URL; used only by live",
    )
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=(REPO_ROOT / "backend/.deer-flow-ip-test/evaluations/writer-v2/readiness-not-created"),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    options = _parse_args(argv)
    try:
        if options.command == "readiness":
            result = run_readiness(
                root=options.root,
                result_dir=options.result_dir,
                environment={},
            )
        elif options.command == "live":
            destination = run_live(
                root=options.root,
                base_url=options.base_url,
                result_dir=options.result_dir,
                environment=os.environ,
            )
            result = verify_result_packet(destination)
        elif options.command == "verify-packet":
            if options.packets:
                if len(options.packets) != 1:
                    _fail("EXACTLY_ONE_PACKET_REQUIRED")
                packet = options.packets[0]
            else:
                packet = options.result_dir
            result = verify_result_packet(packet)
        else:
            if not options.packets:
                _fail("MATRIX_CASE_SET_INVALID")
            result = verify_matrix(options.packets)
    except AcceptanceError as exc:
        print(
            json.dumps(
                {"status": "failed", "error_code": exc.code},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
