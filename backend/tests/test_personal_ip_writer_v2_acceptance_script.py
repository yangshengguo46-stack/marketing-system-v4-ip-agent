"""Red contracts for the default-Agent Writer Brain v2 acceptance harness.

The production script is intentionally absent while these tests are first
landed.  The suite fixes the safety boundary before any live Gateway or paid
model execution is implemented.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import importlib.util
import json
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from deerflow.config.agents_config import agent_artifact_sha256

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "personal_ip_writer_v2_acceptance.py"
FROZEN_CASE_IDS = (
    "urgent_fruit_offer",
    "long_term_person_semantic_story",
    "mcn_brand_explanation",
    "drummer_mom_demonstration",
)
LIVE_ACK = "RUN_REAL_DEFAULT_AGENT"
BACKUP_SIGNING_KEY = b"writer-v2-acceptance-backup-signing-key-v1"
LIVE_PACKET_ARTIFACT_NAMES = (
    "case-input.json",
    "answer.txt",
    "run-receipt.json",
    "tool-receipt.json",
    "lineage.json",
    "owner-backup-v5.json",
)
DIRECT_WRITER_CALLS = (
    "ip-agent-script-writer-v2",
    "ip-agent-script-boundary-verifier-v2",
)
SEMANTIC_WRITER_CALLS = (
    "ip-agent-story-engine-v2",
    *DIRECT_WRITER_CALLS,
)
MALFORMED_TOOL_ARGS = '{"direction":{"route_kind":"offer","script":"private-truncated-value'
MALFORMED_TOOL_ERROR = "invalid JSON at private/provider/path: private-truncated-value"


def _load_acceptance_module():
    assert SCRIPT_PATH.is_file(), "TDD red: scripts/personal_ip_writer_v2_acceptance.py has not been implemented yet"
    spec = importlib.util.spec_from_file_location(
        "personal_ip_writer_v2_acceptance",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _assert_error_code(error: pytest.ExceptionInfo[BaseException], code: str) -> None:
    assert getattr(error.value, "code", None) == code
    assert str(error.value) == code


def _case_field(case: Any, name: str) -> Any:
    if isinstance(case, Mapping):
        return case[name]
    return getattr(case, name)


def _repo_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    default_agent = root / "product/defaults/agents/ip-agent"
    default_agent.parent.mkdir(parents=True)
    shutil.copytree(
        REPO_ROOT / "product/defaults/agents/ip-agent",
        default_agent,
    )
    runtime_profile = root / "product/defaults/product-runtime-profile.yaml"
    shutil.copy2(
        REPO_ROOT / "product/defaults/product-runtime-profile.yaml",
        runtime_profile,
    )
    (root / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "models": [
                    {
                        "name": "writer-v2-acceptance-model",
                        "use": "langchain_openai:ChatOpenAI",
                        "model": "writer-v2-acceptance-model-v1",
                        "api_base": "https://models.invalid/v1",
                        "api_key": "$PAID_ACCEPTANCE_MODEL_KEY",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return root


def _install_clean_test_state(root: Path, *, profile: str = "clean") -> Path:
    state_dir = (root / "backend/.deer-flow-ip-test").resolve()
    installed_agent = state_dir / "users/default/agents/ip-agent"
    installed_agent.parent.mkdir(parents=True)
    shutil.copytree(
        root / "product/defaults/agents/ip-agent",
        installed_agent,
    )
    shutil.copy2(
        root / "product/defaults/product-runtime-profile.yaml",
        state_dir / "product-runtime-profile.yaml",
    )
    marker = {
        "schema_version": "ip-agent-test-mode-v1",
        "root": str(root.resolve()),
        "state_dir": str(state_dir),
        "database_dir": str(state_dir / "data"),
        "profile": profile,
    }
    (state_dir / ".ip-agent-test-mode.json").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return state_dir


def _tree_snapshot(root: Path) -> dict[str, tuple[int, bytes]]:
    return {
        str(path.relative_to(root)): (
            stat.S_IMODE(path.lstat().st_mode),
            path.read_bytes(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _committed_acceptance_repo(tmp_path: Path) -> Path:
    root = tmp_path / "git-repo"
    scripts_dir = root / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy2(SCRIPT_PATH, scripts_dir / SCRIPT_PATH.name)
    shutil.copy2(
        REPO_ROOT / "scripts/personal_ip_writer_v2_acceptance_oracle.py",
        scripts_dir / "personal_ip_writer_v2_acceptance_oracle.py",
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "acceptance@test.local")
    _git(root, "config", "user.name", "Acceptance Test")
    _git(root, "add", "scripts")
    _git(root, "commit", "-qm", "acceptance source")
    return root


class _PoisonEnvironment(Mapping[str, str]):
    """A mapping that records even swallowed credential-value reads."""

    def __init__(self) -> None:
        self.reads = 0

    def _forbidden(self) -> None:
        self.reads += 1
        raise AssertionError("readiness must not read environment values")

    def __getitem__(self, _key: str) -> str:
        self._forbidden()
        raise AssertionError("unreachable")

    def __iter__(self) -> Iterator[str]:
        self._forbidden()
        return iter(())

    def __len__(self) -> int:
        self._forbidden()
        return 0

    def get(self, _key: str, _default: Any = None) -> Any:
        self._forbidden()
        raise AssertionError("unreachable")


def _owner_backup(
    owner_user_id: str = "default",
    *,
    records_by_name: Mapping[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    from deerflow.personal_ip.data_lifecycle import EXPORT_DATASET_NAMES

    schema_version = "personal-ip-owner-backup-v5"
    exported_at = "2026-08-05T08:00:00Z"
    credential_policy = {
        "credentials_included": False,
        "oauth_states_included": False,
        "paid_call_admissions_included": False,
        "platform_reauthorization_required_after_restore": True,
        "paid_call_reapproval_required_after_restore": True,
    }
    artifact_policy = {
        "metadata_included": True,
        "binary_files_included": False,
        "content_must_be_downloaded_separately": True,
    }
    records_by_name = records_by_name or {}
    datasets = [
        {
            "name": name,
            "count": len(records_by_name.get(name, [])),
            "records": records_by_name.get(name, []),
            "digest": hashlib.sha256(_canonical_json_bytes({"name": name, "records": records_by_name.get(name, [])})).hexdigest(),
        }
        for name in EXPORT_DATASET_NAMES
    ]
    data_digest = hashlib.sha256(_canonical_json_bytes([{"name": dataset["name"], "records": dataset["records"]} for dataset in datasets])).hexdigest()
    derived_key = hashlib.sha256(b"personal-ip-owner-backup-signing-v1\0" + BACKUP_SIGNING_KEY).digest()
    key_id = hashlib.sha256(b"personal-ip-owner-backup-key-id-v1\0" + derived_key).hexdigest()[:16]
    verification_algorithm = "hmac-sha256-canonical-json-v1"
    manifest = {
        "schema_version": schema_version,
        "owner_user_id": owner_user_id,
        "exported_at": exported_at,
        "dataset_digests": [
            {
                "name": dataset["name"],
                "count": dataset["count"],
                "digest": dataset["digest"],
            }
            for dataset in datasets
        ],
        "data_digest": data_digest,
        "credential_policy": credential_policy,
        "artifact_policy": artifact_policy,
        "verification_algorithm": verification_algorithm,
        "signing_key_id": key_id,
    }
    manifest_digest = hmac.new(
        derived_key,
        schema_version.encode("utf-8") + b"\0" + _canonical_json_bytes(manifest),
        hashlib.sha256,
    ).hexdigest()
    return {
        "schema_version": schema_version,
        "owner_user_id": owner_user_id,
        "exported_at": exported_at,
        "credential_policy": credential_policy,
        "artifact_policy": artifact_policy,
        "datasets": datasets,
        "verification": {
            "algorithm": verification_algorithm,
            "key_id": key_id,
            "data_digest": data_digest,
            "manifest_digest": manifest_digest,
        },
    }


def _empty_owner_backup(owner_user_id: str = "default") -> dict[str, Any]:
    return _owner_backup(owner_user_id)


def _post_run_owner_backup(lineage: Mapping[str, Any]) -> dict[str, Any]:
    work = dict(lineage["content_work"])
    program = dict(lineage["editorial_program_version"])
    direction = dict(lineage["direction_versions"][0])
    script = dict(lineage["script_versions"][0])
    owner_user_id = str(work["owner_user_id"])
    operation_key = str(work["operation_key"])
    created_at = "2026-08-05T08:01:00Z"
    decision = program.pop("decision")
    objective = work.pop("objective")
    breakdown_version_ids = direction.pop("breakdown_version_ids")
    objective_snapshot = direction.pop("objective_snapshot")
    direction_value = direction.pop("direction")
    claim_basis = script.pop("claim_basis")
    creative_elements = script.pop("creative_elements")
    story_engine_seed = script.pop("story_engine_seed")
    production_notes = script.pop("production_notes")

    program_record = {
        **program,
        "owner_user_id": owner_user_id,
        "operation_key": operation_key,
        "operation_digest": hashlib.sha256(_canonical_json_bytes(decision)).hexdigest(),
        "decision_json": decision,
        "created_by_run_id": work["created_by_run_id"],
        "created_at": created_at,
    }
    work_record = {
        **work,
        "operation_digest": "3" * 64,
        "objective_json": objective,
        "created_at": created_at,
        "updated_at": created_at,
    }
    direction_record = {
        **direction,
        "commit_key": operation_key,
        "commit_digest": "4" * 64,
        "breakdown_version_ids_json": breakdown_version_ids,
        "objective_snapshot_json": objective_snapshot,
        "direction_json": direction_value,
        "created_at": created_at,
    }
    script_record = {
        **script,
        "commit_key": operation_key,
        "commit_digest": "5" * 64,
        "claim_basis_json": claim_basis,
        "creative_elements_json": creative_elements,
        "story_engine_seed_json": story_engine_seed,
        "production_notes_json": production_notes,
        "created_at": created_at,
    }
    return _owner_backup(
        owner_user_id,
        records_by_name={
            "editorial_program_versions": [program_record],
            "content_works": [work_record],
            "direction_versions": [direction_record],
            "script_versions": [script_record],
        },
    )


def _resign_owner_backup(backup: Mapping[str, Any]) -> dict[str, Any]:
    return _owner_backup(
        str(backup["owner_user_id"]),
        records_by_name={str(dataset["name"]): list(dataset["records"]) for dataset in backup["datasets"]},
    )


def _gateway_export_receipt(
    backup: Mapping[str, Any],
    *,
    base_url: str = "http://127.0.0.1:8001",
) -> dict[str, Any]:
    return {
        "schema_version": "personal-ip-owner-backup-export-receipt-v1",
        "method": "GET",
        "base_url": base_url,
        "path": "/api/personal-ip/data/export",
        "status_code": 200,
        "cache_control": "no-store",
        "content_disposition": ('attachment; filename="personal-ip-backup-2026-08-05.json"'),
        "body_sha256": hashlib.sha256(_canonical_json_bytes(backup)).hexdigest(),
    }


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _model_descriptor(model_name: str) -> dict[str, str]:
    return {
        "configured_name": model_name,
        "provider": "volcengine" if "doubao" in model_name else "synthetic",
        "provider_model": model_name,
        "effective_config_sha256": "6" * 64,
    }


def _model_identity_sha256(model_name: str) -> str:
    return hashlib.sha256(_canonical_json_bytes(_model_descriptor(model_name))).hexdigest()


def _expected_writer_calls(case_id: str) -> tuple[str, ...]:
    if case_id == "long_term_person_semantic_story":
        return SEMANTIC_WRITER_CALLS
    return DIRECT_WRITER_CALLS


def _run_receipt(
    case_id: str,
    *,
    agent_artifact_sha256: str = "2" * 64,
    model_name: str = "doubao-seed-2-0-pro-260215",
    status: str = "passed",
    lead_recovery: bool = False,
) -> dict[str, Any]:
    from _personal_ip_v2_behavior_fixtures import CASES

    behavior_case = next(item for item in CASES if item.scenario_id == case_id)
    model = _model_descriptor(model_name)
    calls: list[dict[str, Any]] = []
    if lead_recovery:
        calls.append(
            {
                "llm_call_index": 1,
                "caller": "lead_agent",
                "model_name": model["provider_model"],
                "status": "success",
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 7,
                    "total_tokens": 27,
                },
                "lead_tool_receipt": {
                    "finish_reason": "tool_calls",
                    "valid_tool_call_names": [],
                    "invalid_tool_calls": [
                        {
                            "name": "ip_content_write",
                            "classification": "malformed_tool_arguments",
                        }
                    ],
                    "fallback": False,
                },
            }
        )
    calls.append(
        {
            "llm_call_index": len(calls) + 1,
            "caller": "lead_agent",
            "model_name": model["provider_model"],
            "status": "success",
            "usage": {
                "input_tokens": 20,
                "output_tokens": 10,
                "total_tokens": 30,
            },
            "lead_tool_receipt": {
                "finish_reason": "tool_calls",
                "valid_tool_call_names": ["ip_content_write"],
                "invalid_tool_calls": [],
                "fallback": False,
            },
        }
    )
    for llm_call_index, run_name in enumerate(
        _expected_writer_calls(case_id),
        start=len(calls) + 1,
    ):
        calls.append(
            {
                "llm_call_index": llm_call_index,
                "caller": f"middleware:{run_name}",
                "model_name": model["provider_model"],
                "status": "success",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                },
            }
        )
    calls.append(
        {
            "llm_call_index": len(calls) + 1,
            "caller": "lead_agent",
            "model_name": model["provider_model"],
            "status": "success",
            "usage": {
                "input_tokens": 12,
                "output_tokens": 8,
                "total_tokens": 20,
            },
            "lead_tool_receipt": {
                "finish_reason": "stop",
                "valid_tool_call_names": [],
                "invalid_tool_calls": [],
                "fallback": False,
            },
        }
    )
    for event_seq, call in enumerate(calls, start=1):
        call["event_seq"] = event_seq
    total_input = sum(call["usage"]["input_tokens"] for call in calls)
    total_output = sum(call["usage"]["output_tokens"] for call in calls)
    total_tokens = sum(call["usage"]["total_tokens"] for call in calls)
    lead_tokens = sum(call["usage"]["total_tokens"] for call in calls if call["caller"] == "lead_agent")
    middleware_tokens = total_tokens - lead_tokens
    profile = yaml.safe_load((REPO_ROOT / "product/defaults/product-runtime-profile.yaml").read_text(encoding="utf-8"))
    capability_digest = hashlib.sha256(
        _canonical_json_bytes(
            {
                "schema_version": "ip-agent-runtime-profile-v1",
                "product_id": "ip-agent",
                "assistant_id": "ip-agent",
                "agent_artifact_sha256": agent_artifact_sha256,
                "capability_contract": profile["capability_contract"],
            }
        )
    ).hexdigest()
    backup = _empty_owner_backup()
    run_id = f"run-{case_id}"
    thread_id = f"thread-{case_id}"
    gateway_receipts = {
        "run": {
            "run_id": run_id,
            "thread_id": thread_id,
            "assistant_id": "ip-agent",
            "status": "success" if status == "passed" else "error",
            "metadata": {
                "deerflow_product_runtime": {
                    "schema_version": "product-runtime-binding-v1",
                    "product_id": "ip-agent",
                    "entrypoint": "customer_run",
                    "assistant_id": "ip-agent",
                    "agent_artifact_sha256": agent_artifact_sha256,
                    "declared_capability_digest": capability_digest,
                }
            },
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_tokens,
            "llm_call_count": len(calls),
            "lead_agent_tokens": lead_tokens,
            "subagent_tokens": 0,
            "middleware_tokens": middleware_tokens,
            "stop_reason": None,
        },
        "events": [],
        "checkpoint": {
            "state": {
                "values": {
                    "messages": [
                        {
                            "type": "human",
                            "content": behavior_case.prompt,
                            "additional_kwargs": {"run_id": run_id},
                        },
                        {
                            "type": "ai",
                            "content": "",
                            "additional_kwargs": {},
                            "tool_calls": [
                                {
                                    "name": "ip_content_write",
                                    "args": behavior_case.tool_trace[0]["arguments"],
                                    "id": behavior_case.tool_trace[0]["call_id"],
                                    "type": "tool_call",
                                }
                            ],
                        },
                        {
                            "type": "tool",
                            "name": "ip_content_write",
                            "tool_call_id": behavior_case.tool_trace[0]["call_id"],
                            "content": json.dumps(
                                behavior_case.tool_trace[0]["result"],
                                ensure_ascii=False,
                            ),
                            "status": "success",
                            "additional_kwargs": {},
                        },
                        {
                            "type": "ai",
                            "content": behavior_case.final_text,
                            "additional_kwargs": {},
                            "tool_calls": [],
                        },
                    ]
                },
                "next": [],
                "tasks": [],
                "checkpoint": {"id": "checkpoint-1"},
                "checkpoint_id": "checkpoint-1",
            }
        },
        "token_usage": {
            "thread_id": thread_id,
            "total_tokens": total_tokens,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_runs": 1,
            "by_model": {model["provider_model"]: {"tokens": total_tokens, "runs": 1}},
            "by_caller": {
                "lead_agent": lead_tokens,
                "subagent": 0,
                "middleware": middleware_tokens,
            },
        },
        "model": {
            "schema_version": "personal-ip-writer-v2-gateway-model-receipt-v1",
            **model,
            "effective_config_sha256": "6" * 64,
        },
        "owner_baseline": {
            "backup": backup,
            "gateway_export_receipt": _gateway_export_receipt(backup),
            "auth_receipt": {
                "schema_version": "personal-ip-writer-v2-auth-receipt-v1",
                "method": "GET",
                "path": "/api/v1/auth/me",
                "status_code": 200,
                "user": {
                    "id": "default",
                    "email": "default@test.local",
                    "system_role": "admin",
                    "needs_setup": False,
                    "oauth_provider": None,
                },
            },
        },
    }
    for index, call in enumerate(calls, start=1):
        caller = call["caller"]
        lead_receipt = call.get("lead_tool_receipt")
        content: dict[str, Any] = {
            "type": "ai",
            "additional_kwargs": {},
            "response_metadata": {
                "model_name": model["provider_model"],
            },
            "tool_calls": [],
            "invalid_tool_calls": [],
        }
        if caller == "lead_agent":
            content["response_metadata"]["finish_reason"] = lead_receipt["finish_reason"]
            if lead_receipt["valid_tool_call_names"]:
                content["tool_calls"] = [
                    {
                        "name": "ip_content_write",
                        "args": behavior_case.tool_trace[0]["arguments"],
                        "id": behavior_case.tool_trace[0]["call_id"],
                        "type": "tool_call",
                    }
                ]
            if lead_receipt["invalid_tool_calls"]:
                content["acceptance_invalid_tool_calls"] = copy.deepcopy(
                    lead_receipt["invalid_tool_calls"],
                )
        gateway_receipts["events"].append(
            {
                "seq": index,
                "thread_id": thread_id,
                "run_id": run_id,
                "event_type": "llm.ai.response",
                "content": content,
                "metadata": {
                    "caller": caller,
                    "usage": call["usage"],
                    "llm_call_index": call["llm_call_index"],
                },
            }
        )
    return {
        "schema_version": "personal-ip-writer-v2-run-receipt-v1",
        "run_id": run_id,
        "thread_id": thread_id,
        "status": "success" if status == "passed" else "error",
        "runtime_metadata": {
            "product_id": "ip-agent",
            "assistant_id": "ip-agent",
            "agent_artifact_sha256": agent_artifact_sha256,
            "runtime_profile_agent_artifact_sha256": agent_artifact_sha256,
            "effective_model": model,
        },
        "usage": {
            "llm_call_count": len(calls),
            "total_tokens": total_tokens,
        },
        "llm_calls": calls,
        "gateway_receipts": gateway_receipts,
    }


def _business_artifacts(
    case_id: str,
    *,
    agent_artifact_sha256: str = "2" * 64,
    model_name: str = "doubao-seed-2-0-pro-260215",
    status: str = "passed",
    lead_recovery: bool = False,
) -> dict[str, Any]:
    from _personal_ip_v2_behavior_fixtures import CASES

    case = next(item for item in CASES if item.scenario_id == case_id)
    lineage = copy.deepcopy(case.lineage)
    lineage["content_work"]["owner_user_id"] = "default"
    for record in (*lineage["direction_versions"], *lineage["script_versions"]):
        record["owner_user_id"] = "default"
    tool_trace = copy.deepcopy(case.tool_trace)
    tool_trace[0]["owner_user_id"] = "default"
    backup = _post_run_owner_backup(lineage)
    return {
        "case-input.json": {
            "case_id": case.scenario_id,
            "prompt": case.prompt,
            "expected_route": case.expected_route,
            "expected_story_mode": case.expected_story_mode,
        },
        "answer.txt": case.final_text,
        "run-receipt.json": _run_receipt(
            case_id,
            agent_artifact_sha256=agent_artifact_sha256,
            model_name=model_name,
            status=status,
            lead_recovery=lead_recovery,
        ),
        "tool-receipt.json": {"tool_trace": tool_trace},
        "lineage.json": lineage,
        "owner-backup-v5.json": {
            "backup": backup,
            "gateway_export_receipt": _gateway_export_receipt(backup),
        },
    }


def _manifest(
    case_id: str,
    *,
    status: str = "passed",
    git_commit: str = "1" * 40,
    agent_artifact_sha256: str = "2" * 64,
    execution_source: str = "live_gateway",
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "status": status,
        "git_commit": git_commit,
        "agent_artifact_sha256": agent_artifact_sha256,
        "execution_source": execution_source,
    }


def _write_packet(
    acceptance: Any,
    destination: Path,
    case_id: str,
    *,
    model_name: str = "doubao-seed-2-0-pro-260215",
    lead_recovery: bool = False,
    **manifest_overrides: Any,
) -> Path:
    manifest = _manifest(case_id, **manifest_overrides)
    artifacts = _business_artifacts(
        case_id,
        agent_artifact_sha256=manifest["agent_artifact_sha256"],
        model_name=model_name,
        status=manifest["status"],
        lead_recovery=lead_recovery,
    )
    return acceptance.write_result_packet(
        destination,
        manifest=manifest,
        artifacts=artifacts,
    )


def test_script_is_a_production_harness_and_never_imports_backend_tests() -> None:
    _load_acceptance_module()
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "_personal_ip_v2_behavior_fixtures" not in source
    assert "backend/tests" not in source
    assert "backend.tests" not in source


def test_frozen_catalog_reuses_the_exact_four_behavior_cases() -> None:
    acceptance = _load_acceptance_module()
    from _personal_ip_v2_behavior_fixtures import CASES

    production_cases = tuple(acceptance.FROZEN_CASES)

    assert tuple(_case_field(case, "case_id") for case in production_cases) == (tuple(case.scenario_id for case in CASES)) == FROZEN_CASE_IDS
    assert tuple(_case_field(case, "prompt") for case in production_cases) == tuple(case.prompt for case in CASES)
    assert tuple(_case_field(case, "expected_route") for case in production_cases) == tuple(case.expected_route for case in CASES)
    assert tuple(_case_field(case, "expected_story_mode") for case in production_cases) == tuple(case.expected_story_mode for case in CASES)


def test_default_cli_command_is_readiness() -> None:
    acceptance = _load_acceptance_module()

    options = acceptance._parse_args([])

    assert options.command == "readiness"


def test_readiness_validates_contracts_with_zero_external_or_durable_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acceptance = _load_acceptance_module()
    root = _repo_fixture(tmp_path)
    result_dir = root / "backend/.deer-flow-ip-test/evaluations/writer-v2/not-created"
    environment = _PoisonEnvironment()
    network_attempts: list[str] = []
    database_attempts: list[str] = []

    def forbidden_socket(*_args: Any, **_kwargs: Any) -> None:
        network_attempts.append("socket")
        raise AssertionError("readiness must not access the Gateway or a model")

    def forbidden_http(*_args: Any, **_kwargs: Any) -> None:
        network_attempts.append("http")
        raise AssertionError("readiness must not access the Gateway or a model")

    async def forbidden_async_http(*_args: Any, **_kwargs: Any) -> None:
        network_attempts.append("async-http")
        raise AssertionError("readiness must not access the Gateway or a model")

    def forbidden_database(*_args: Any, **_kwargs: Any) -> None:
        database_attempts.append("sqlite")
        raise AssertionError("readiness must not open a database")

    monkeypatch.setattr(socket.socket, "connect", forbidden_socket)
    monkeypatch.setattr(httpx.Client, "request", forbidden_http)
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden_async_http)
    monkeypatch.setattr(sqlite3, "connect", forbidden_database)
    before = _tree_snapshot(root)

    result = acceptance.run_readiness(
        root=root,
        result_dir=result_dir,
        environment=environment,
    )

    assert result["status"] == "ready"
    assert result["mode"] == "readiness"
    assert tuple(result["case_ids"]) == FROZEN_CASE_IDS
    assert result["gateway_requests"] == 0
    assert result["model_calls"] == 0
    assert result["database_writes"] == 0
    assert result["credential_value_reads"] == 0
    assert result["result_directory_created"] is False
    assert result["evidence_class"] == "synthetic_contract"
    assert result["ledger_eligible"] is False
    assert result["agent_artifact_sha256"] == agent_artifact_sha256(root / "product/defaults/agents/ip-agent")
    assert environment.reads == 0
    assert network_attempts == []
    assert database_attempts == []
    assert _tree_snapshot(root) == before
    assert not result_dir.exists()


def test_readiness_rejects_a_missing_frozen_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acceptance = _load_acceptance_module()
    root = _repo_fixture(tmp_path)
    monkeypatch.setattr(
        acceptance,
        "FROZEN_CASES",
        tuple(acceptance.FROZEN_CASES)[:-1],
    )

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.run_readiness(
            root=root,
            result_dir=root / "must-not-exist",
            environment=_PoisonEnvironment(),
        )

    _assert_error_code(error, "FROZEN_CASE_CATALOG_INVALID")
    assert not (root / "must-not-exist").exists()


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ("artifact_digest", "AGENT_ARTIFACT_DIGEST_MISMATCH"),
        ("capability_contract", "RUNTIME_CAPABILITY_CONTRACT_MISMATCH"),
    ),
)
def test_readiness_fails_closed_on_product_runtime_drift(
    tmp_path: Path,
    mutation: str,
    code: str,
) -> None:
    acceptance = _load_acceptance_module()
    root = _repo_fixture(tmp_path)
    profile_path = root / "product/defaults/product-runtime-profile.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    if mutation == "artifact_digest":
        profile["agent_artifact_sha256"] = "0" * 64
    else:
        profile["capability_contract"]["memory_enabled"] = True
    profile_path.write_text(
        yaml.safe_dump(profile, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.run_readiness(
            root=root,
            result_dir=root / "must-not-exist",
            environment=_PoisonEnvironment(),
        )

    _assert_error_code(error, code)
    assert not (root / "must-not-exist").exists()


@pytest.mark.parametrize(
    ("environment", "code"),
    (
        ({"CASE": FROZEN_CASE_IDS[0], "ACK": LIVE_ACK}, "LIVE_OPT_IN_REQUIRED"),
        (
            {"LIVE": "true", "CASE": FROZEN_CASE_IDS[0], "ACK": LIVE_ACK},
            "LIVE_OPT_IN_REQUIRED",
        ),
        ({"LIVE": "1", "ACK": LIVE_ACK}, "EXACTLY_ONE_CASE_REQUIRED"),
        (
            {"LIVE": "1", "CASE": "all", "ACK": LIVE_ACK},
            "EXACTLY_ONE_CASE_REQUIRED",
        ),
        (
            {
                "LIVE": "1",
                "CASE": f"{FROZEN_CASE_IDS[0]},{FROZEN_CASE_IDS[1]}",
                "ACK": LIVE_ACK,
            },
            "EXACTLY_ONE_CASE_REQUIRED",
        ),
        (
            {"LIVE": "1", "CASE": "unknown-case", "ACK": LIVE_ACK},
            "UNKNOWN_CASE",
        ),
        (
            {"LIVE": "1", "CASE": FROZEN_CASE_IDS[0], "ACK": "yes"},
            "LIVE_ACK_REQUIRED",
        ),
    ),
)
def test_live_gate_requires_three_exact_operator_inputs(
    environment: Mapping[str, str],
    code: str,
) -> None:
    acceptance = _load_acceptance_module()

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.validate_live_gate(environment)

    _assert_error_code(error, code)


def test_live_gate_accepts_one_known_case_only() -> None:
    acceptance = _load_acceptance_module()

    selected = acceptance.validate_live_gate(
        {
            "LIVE": "1",
            "CASE": FROZEN_CASE_IDS[2],
            "ACK": LIVE_ACK,
        }
    )

    assert selected == FROZEN_CASE_IDS[2]


def test_loopback_gateway_client_ignores_system_proxy_settings() -> None:
    acceptance = _load_acceptance_module()
    captured: dict[str, Any] = {}

    def client_factory(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    client = acceptance._new_loopback_gateway_client(
        base_url="http://127.0.0.1:8001",
        client_factory=client_factory,
    )

    assert type(client) is object
    assert captured == {
        "base_url": "http://127.0.0.1:8001",
        "timeout": httpx.Timeout(600.0, connect=10.0),
        "trust_env": False,
    }


def test_invalid_live_gate_fails_before_gateway_construction(tmp_path: Path) -> None:
    acceptance = _load_acceptance_module()
    gateway_constructions = 0
    result_dir = tmp_path / "result"

    def forbidden_client(*_args: Any, **_kwargs: Any) -> None:
        nonlocal gateway_constructions
        gateway_constructions += 1
        raise AssertionError("invalid live opt-in must fail before Gateway access")

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.run_live(
            root=tmp_path,
            base_url="http://127.0.0.1:8001",
            result_dir=result_dir,
            environment={
                "LIVE": "1",
                "CASE": FROZEN_CASE_IDS[0],
                "ACK": "not-the-exact-ack",
            },
            client_factory=forbidden_client,
        )

    _assert_error_code(error, "LIVE_ACK_REQUIRED")
    assert gateway_constructions == 0
    assert not result_dir.exists()


def test_dirty_live_source_tree_fails_before_gateway_construction(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    root = _committed_acceptance_repo(tmp_path)
    (root / "untracked-runtime-change.py").write_text(
        "# must block paid evidence attribution\n",
        encoding="utf-8",
    )
    gateway_constructions = 0

    def forbidden_client(*_args: Any, **_kwargs: Any) -> None:
        nonlocal gateway_constructions
        gateway_constructions += 1
        raise AssertionError("dirty source must fail before Gateway access")

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.run_live(
            root=root,
            base_url="http://127.0.0.1:8001",
            result_dir=root / "result-must-not-exist",
            environment={
                "LIVE": "1",
                "CASE": FROZEN_CASE_IDS[0],
                "ACK": LIVE_ACK,
            },
            client_factory=forbidden_client,
        )

    _assert_error_code(error, "LIVE_SOURCE_TREE_NOT_CLEAN")
    assert gateway_constructions == 0
    assert not (root / "result-must-not-exist").exists()


def test_live_source_files_must_be_tracked_even_when_ignored(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    root = tmp_path / "ignored-source-repo"
    root.mkdir()
    (root / ".gitignore").write_text("scripts/\n", encoding="utf-8")
    scripts_dir = root / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(SCRIPT_PATH, scripts_dir / SCRIPT_PATH.name)
    shutil.copy2(
        REPO_ROOT / "scripts/personal_ip_writer_v2_acceptance_oracle.py",
        scripts_dir / "personal_ip_writer_v2_acceptance_oracle.py",
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "acceptance@test.local")
    _git(root, "config", "user.name", "Acceptance Test")
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-qm", "ignore acceptance source")

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance._git_clean_commit(root)

    _assert_error_code(error, "LIVE_SOURCE_NOT_TRACKED")


@pytest.mark.parametrize(
    "base_url",
    (
        "http://127.0.0.1:8001",
        "http://localhost:8001",
        "http://[::1]:8001",
    ),
)
def test_gateway_url_accepts_only_explicit_loopback_hosts(base_url: str) -> None:
    acceptance = _load_acceptance_module()

    assert acceptance.validate_loopback_gateway_url(base_url) == base_url


@pytest.mark.parametrize(
    "base_url",
    (
        "https://gateway.example.com",
        "http://0.0.0.0:8001",
        "http://localhost.evil.example:8001",
        "http://127.0.0.1.nip.io:8001",
        "http://user:secret@127.0.0.1:8001",
        "file:///tmp/gateway.sock",
        "http://127.0.0.1:8001?token=secret",
        "http://127.0.0.1:8001/#fragment",
    ),
)
def test_gateway_url_rejects_external_ambiguous_or_secret_bearing_targets(
    base_url: str,
) -> None:
    acceptance = _load_acceptance_module()

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.validate_loopback_gateway_url(base_url)

    _assert_error_code(error, "GATEWAY_MUST_BE_LOOPBACK")


def test_live_state_must_be_the_marked_clean_profile_with_exact_agent_artifact(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    root = _repo_fixture(tmp_path)
    state_dir = _install_clean_test_state(root)

    receipt = acceptance.validate_clean_test_state(root)

    assert receipt["profile"] == "clean"
    assert receipt["state_dir"] == str(state_dir)
    assert receipt["agent_artifact_sha256"] == agent_artifact_sha256(root / "product/defaults/agents/ip-agent")


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ("evidence_profile", "CLEAN_TEST_PROFILE_REQUIRED"),
        ("installed_agent", "TEST_AGENT_ARTIFACT_MISMATCH"),
    ),
)
def test_live_state_rejects_non_clean_or_drifted_test_installations(
    tmp_path: Path,
    mutation: str,
    code: str,
) -> None:
    acceptance = _load_acceptance_module()
    root = _repo_fixture(tmp_path)
    state_dir = _install_clean_test_state(
        root,
        profile="evidence" if mutation == "evidence_profile" else "clean",
    )
    if mutation == "installed_agent":
        (state_dir / "users/default/agents/ip-agent/SOUL.md").write_text(
            "drifted test Agent\n",
            encoding="utf-8",
        )

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.validate_clean_test_state(root)

    _assert_error_code(error, code)


def test_owner_baseline_requires_every_dataset_to_be_empty() -> None:
    acceptance = _load_acceptance_module()
    backup = _empty_owner_backup()

    receipt = acceptance.validate_empty_owner_baseline(
        backup,
        expected_owner_user_id="default",
        gateway_export_receipt=_gateway_export_receipt(backup),
    )

    assert receipt["owner_user_id"] == "default"
    assert receipt["record_count"] == 0
    assert receipt["schema_version"] == "personal-ip-owner-backup-v5"
    assert receipt["verification_algorithm"] == ("hmac-sha256-canonical-json-v1")
    assert receipt["gateway_export_bound"] is True


@pytest.mark.parametrize("mutation", ("record", "count", "owner"))
def test_owner_baseline_rejects_any_existing_or_cross_owner_data(
    mutation: str,
) -> None:
    acceptance = _load_acceptance_module()
    backup = _empty_owner_backup()
    expected_code = "OWNER_BASELINE_NOT_EMPTY"
    if mutation == "record":
        backup["datasets"][0]["records"] = [{"id": "existing"}]
        backup["datasets"][0]["count"] = 1
    elif mutation == "count":
        backup["datasets"][0]["count"] = 1
    else:
        backup["owner_user_id"] = "another-owner"
        expected_code = "OWNER_BASELINE_OWNER_MISMATCH"

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.validate_empty_owner_baseline(
            backup,
            expected_owner_user_id="default",
            gateway_export_receipt=_gateway_export_receipt(backup),
        )

    _assert_error_code(error, expected_code)


@pytest.mark.parametrize(
    "mutation",
    (
        "handmade_minimal",
        "missing_verification",
        "unsigned_algorithm",
        "missing_key_id",
        "missing_manifest_digest",
        "bad_dataset_digest",
        "bad_data_digest",
    ),
)
def test_owner_baseline_rejects_incomplete_unsigned_or_digest_invalid_v5(
    mutation: str,
) -> None:
    acceptance = _load_acceptance_module()
    backup = _empty_owner_backup()
    if mutation == "handmade_minimal":
        backup = {
            "schema_version": "personal-ip-owner-backup-v5",
            "owner_user_id": "default",
            "datasets": [],
        }
    elif mutation == "missing_verification":
        del backup["verification"]
    elif mutation == "unsigned_algorithm":
        backup["verification"]["algorithm"] = "sha256-canonical-json-v1"
    elif mutation == "missing_key_id":
        del backup["verification"]["key_id"]
    elif mutation == "missing_manifest_digest":
        del backup["verification"]["manifest_digest"]
    elif mutation == "bad_dataset_digest":
        backup["datasets"][0]["digest"] = "0" * 64
    else:
        backup["verification"]["data_digest"] = "0" * 64

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.validate_empty_owner_baseline(
            backup,
            expected_owner_user_id="default",
            gateway_export_receipt=_gateway_export_receipt(backup),
        )

    _assert_error_code(error, "OWNER_BACKUP_V5_INVALID")


@pytest.mark.parametrize(
    "mutation",
    ("missing", "external", "wrong_path", "wrong_status", "wrong_body_digest"),
)
def test_owner_baseline_requires_an_exact_loopback_gateway_export_receipt(
    mutation: str,
) -> None:
    acceptance = _load_acceptance_module()
    backup = _empty_owner_backup()
    receipt: dict[str, Any] | None = _gateway_export_receipt(backup)
    if mutation == "missing":
        receipt = None
    elif mutation == "external":
        receipt["base_url"] = "https://gateway.example.com"
    elif mutation == "wrong_path":
        receipt["path"] = "/api/personal-ip/data/delete-preview"
    elif mutation == "wrong_status":
        receipt["status_code"] = 404
    else:
        receipt["body_sha256"] = "0" * 64

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.validate_empty_owner_baseline(
            backup,
            expected_owner_user_id="default",
            gateway_export_receipt=receipt,
        )

    _assert_error_code(error, "OWNER_BACKUP_GATEWAY_RECEIPT_INVALID")


@pytest.mark.parametrize("execution_source", ("mock", "replay", "fixture"))
def test_non_live_sources_are_always_synthetic_and_never_ledger_eligible(
    execution_source: str,
) -> None:
    acceptance = _load_acceptance_module()

    result = acceptance.classify_evidence(
        execution_source=execution_source,
        case_id=FROZEN_CASE_IDS[0],
        run_receipt=_run_receipt(FROZEN_CASE_IDS[0]),
        expected_agent_artifact_sha256="2" * 64,
        live_gate_verified=True,
        owner_baseline_empty=True,
        behavior_passed=True,
    )

    assert result == {
        "evidence_class": "synthetic_contract",
        "ledger_eligible": False,
    }


def test_unknown_execution_source_can_never_become_live_evidence() -> None:
    acceptance = _load_acceptance_module()

    result = acceptance.classify_evidence(
        execution_source="operator_claimed_real",
        case_id=FROZEN_CASE_IDS[0],
        run_receipt=_run_receipt(FROZEN_CASE_IDS[0]),
        expected_agent_artifact_sha256="2" * 64,
        live_gate_verified=True,
        owner_baseline_empty=True,
        behavior_passed=True,
    )

    assert result["ledger_eligible"] is False
    assert result["evidence_class"] != "live_default_agent"


@pytest.mark.parametrize(
    "case_id",
    (FROZEN_CASE_IDS[0], FROZEN_CASE_IDS[1]),
    ids=("direct-two-internal-calls", "semantic-three-internal-calls"),
)
def test_live_run_receipt_derives_provider_binding_and_reindexes_writer_calls(
    case_id: str,
) -> None:
    acceptance = _load_acceptance_module()
    receipt = _run_receipt(case_id)

    result = acceptance.validate_live_run_receipt(
        receipt,
        case_id=case_id,
        expected_agent_artifact_sha256="2" * 64,
    )

    expected_names = _expected_writer_calls(case_id)
    assert result["gateway_binding_verified"] is True
    assert result["provider_receipts_verified"] is True
    assert result["model_identity_sha256"] == _model_identity_sha256("doubao-seed-2-0-pro-260215")
    assert result["lead_recovery_count"] == 0
    assert [item["run_name"] for item in result["writer_model_trace"]] == list(expected_names)
    assert [item["call_index"] for item in result["writer_model_trace"]] == list(range(1, len(expected_names) + 1))
    assert [item["llm_call_index"] for item in result["writer_model_trace"]] == list(range(2, len(expected_names) + 2))


@pytest.mark.parametrize(
    "case_id",
    (FROZEN_CASE_IDS[0], FROZEN_CASE_IDS[1]),
    ids=("direct-recovered-once", "semantic-recovered-once"),
)
def test_live_run_receipt_accepts_exactly_one_malformed_lead_tool_call_then_one_repair(
    case_id: str,
) -> None:
    acceptance = _load_acceptance_module()
    receipt = _run_receipt(case_id, lead_recovery=True)

    result = acceptance.validate_live_run_receipt(
        receipt,
        case_id=case_id,
        expected_agent_artifact_sha256="2" * 64,
    )

    expected_names = _expected_writer_calls(case_id)
    assert result["lead_recovery_count"] == 1
    assert [item["run_name"] for item in result["writer_model_trace"]] == list(expected_names)
    assert [item["call_index"] for item in result["writer_model_trace"]] == list(
        range(1, len(expected_names) + 1),
    )
    assert [item["llm_call_index"] for item in result["writer_model_trace"]] == list(
        range(3, len(expected_names) + 3),
    )
    checkpoint_messages = receipt["gateway_receipts"]["checkpoint"]["state"]["values"]["messages"]
    assert all(not message.get("acceptance_invalid_tool_calls") for message in checkpoint_messages)
    assert all(not message.get("invalid_tool_calls") for message in checkpoint_messages)


def test_live_run_receipt_builder_seals_malformed_args_and_error_before_persistence() -> None:
    acceptance = _load_acceptance_module()
    fixture = _run_receipt(FROZEN_CASE_IDS[0], lead_recovery=True)
    embedded = fixture["gateway_receipts"]
    raw_events = copy.deepcopy(embedded["events"])
    raw_first_content = raw_events[0]["content"]
    del raw_first_content["acceptance_invalid_tool_calls"]
    raw_first_content["invalid_tool_calls"] = [
        {
            "name": "ip_content_write",
            "args": MALFORMED_TOOL_ARGS,
            "error": MALFORMED_TOOL_ERROR,
            "type": "invalid_tool_call",
        }
    ]
    raw_first_content["additional_kwargs"]["tool_calls"] = [
        {
            "id": "raw-provider-tool-call",
            "type": "function",
            "function": {
                "name": "ip_content_write",
                "arguments": MALFORMED_TOOL_ARGS,
            },
        }
    ]
    raw_state = copy.deepcopy(embedded["checkpoint"]["state"])
    raw_events.append(
        {
            "seq": len(raw_events) + 1,
            "thread_id": fixture["thread_id"],
            "run_id": fixture["run_id"],
            "event_type": "run.end",
            "content": {
                "messages": [
                    {
                        "type": "ai",
                        "content": "",
                        "additional_kwargs": copy.deepcopy(
                            raw_first_content["additional_kwargs"],
                        ),
                        "tool_calls": [],
                        "invalid_tool_calls": copy.deepcopy(
                            raw_first_content["invalid_tool_calls"],
                        ),
                    }
                ]
            },
            "metadata": {},
        },
    )

    built = acceptance._build_live_run_receipt(
        run=embedded["run"],
        state=raw_state,
        events=raw_events,
        token_usage=embedded["token_usage"],
        model_receipt=embedded["model"],
        thread_id=fixture["thread_id"],
        run_id=fixture["run_id"],
        expected_agent_artifact_sha256="2" * 64,
        owner_baseline=embedded["owner_baseline"],
    )

    sealed_json = json.dumps(built, ensure_ascii=False, sort_keys=True)
    assert MALFORMED_TOOL_ARGS not in sealed_json
    assert MALFORMED_TOOL_ERROR not in sealed_json
    assert "private-truncated-value" not in sealed_json
    first_call = built["llm_calls"][0]
    assert first_call["lead_tool_receipt"] == {
        "finish_reason": "tool_calls",
        "valid_tool_call_names": [],
        "invalid_tool_calls": [
            {
                "name": "ip_content_write",
                "classification": "malformed_tool_arguments",
            }
        ],
        "fallback": False,
    }
    assert (
        acceptance.validate_live_run_receipt(
            built,
            case_id=FROZEN_CASE_IDS[0],
            expected_agent_artifact_sha256="2" * 64,
        )["lead_recovery_count"]
        == 1
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "second_invalid",
        "fallback",
        "other_tool",
        "duplicate_valid_tool",
        "invalid_after_internal",
    ),
)
def test_lead_tool_recovery_fails_closed_for_every_non_bounded_sequence(
    mutation: str,
) -> None:
    acceptance = _load_acceptance_module()
    receipt = _run_receipt(FROZEN_CASE_IDS[0], lead_recovery=True)
    calls = receipt["llm_calls"]
    events = receipt["gateway_receipts"]["events"]
    if mutation == "second_invalid":
        calls[1]["lead_tool_receipt"] = copy.deepcopy(calls[0]["lead_tool_receipt"])
        events[1]["content"] = copy.deepcopy(events[0]["content"])
    elif mutation == "fallback":
        calls[0]["lead_tool_receipt"]["fallback"] = True
        calls[0]["status"] = "error"
        events[0]["content"]["additional_kwargs"]["deerflow_error_fallback"] = True
    elif mutation == "other_tool":
        calls[0]["lead_tool_receipt"]["invalid_tool_calls"][0]["name"] = "web_search"
        events[0]["content"]["acceptance_invalid_tool_calls"][0]["name"] = "web_search"
    elif mutation == "duplicate_valid_tool":
        calls[1]["lead_tool_receipt"]["valid_tool_call_names"].append("ip_content_write")
        events[1]["content"]["tool_calls"].append(
            copy.deepcopy(events[1]["content"]["tool_calls"][0]),
        )
    else:
        calls[1]["event_seq"], calls[2]["event_seq"] = (
            calls[2]["event_seq"],
            calls[1]["event_seq"],
        )
        events[1]["metadata"], events[2]["metadata"] = (
            events[2]["metadata"],
            events[1]["metadata"],
        )
        events[1]["content"], events[2]["content"] = (
            events[2]["content"],
            events[1]["content"],
        )

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.validate_live_run_receipt(
            receipt,
            case_id=FROZEN_CASE_IDS[0],
            expected_agent_artifact_sha256="2" * 64,
        )

    _assert_error_code(error, "LEAD_MODEL_RECOVERY_INVALID")


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ("mock_model", "PROVIDER_MODEL_RECEIPT_INVALID"),
        ("zero_tokens", "PROVIDER_MODEL_RECEIPT_INVALID"),
        ("missing_lead", "LEAD_MODEL_RECEIPT_MISSING"),
        ("missing_internal", "WRITER_MODEL_RECEIPT_MISMATCH"),
        ("artifact", "GATEWAY_PRODUCT_BINDING_MISMATCH"),
        ("assistant", "GATEWAY_PRODUCT_BINDING_MISMATCH"),
    ),
)
def test_live_run_receipt_cannot_self_report_provider_or_product_binding(
    mutation: str,
    code: str,
) -> None:
    acceptance = _load_acceptance_module()
    receipt = _run_receipt(FROZEN_CASE_IDS[0])
    receipt["provider_receipts_verified"] = True
    receipt["gateway_binding_verified"] = True
    calls = receipt["llm_calls"]
    if mutation == "mock_model":
        receipt["runtime_metadata"]["effective_model"] = _model_descriptor("mock-writer-model")
        for call in calls:
            call["model_name"] = "mock-writer-model"
    elif mutation == "zero_tokens":
        for call in calls:
            call["usage"] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
    elif mutation == "missing_lead":
        receipt["llm_calls"] = [call for call in calls if call["caller"] != "lead_agent"]
    elif mutation == "missing_internal":
        receipt["llm_calls"] = calls[:-2] + calls[-1:]
    elif mutation == "artifact":
        receipt["runtime_metadata"]["agent_artifact_sha256"] = "9" * 64
        receipt["runtime_metadata"]["runtime_profile_agent_artifact_sha256"] = "9" * 64
    else:
        receipt["runtime_metadata"]["assistant_id"] = "not-ip-agent"
    receipt["usage"] = {
        "llm_call_count": len(receipt["llm_calls"]),
        "total_tokens": sum(call["usage"]["total_tokens"] for call in receipt["llm_calls"]),
    }

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.validate_live_run_receipt(
            receipt,
            case_id=FROZEN_CASE_IDS[0],
            expected_agent_artifact_sha256="2" * 64,
        )

    _assert_error_code(error, code)


def test_only_a_fully_bound_live_default_agent_run_is_ledger_eligible() -> None:
    acceptance = _load_acceptance_module()
    verified = acceptance.classify_evidence(
        execution_source="live_gateway",
        case_id=FROZEN_CASE_IDS[0],
        run_receipt=_run_receipt(FROZEN_CASE_IDS[0]),
        expected_agent_artifact_sha256="2" * 64,
        live_gate_verified=True,
        owner_baseline_empty=True,
        behavior_passed=True,
    )
    invalid_receipt = _run_receipt(FROZEN_CASE_IDS[0])
    for call in invalid_receipt["llm_calls"]:
        call["usage"] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
    invalid_receipt["provider_receipts_verified"] = True
    unverified = acceptance.classify_evidence(
        execution_source="live_gateway",
        case_id=FROZEN_CASE_IDS[0],
        run_receipt=invalid_receipt,
        expected_agent_artifact_sha256="2" * 64,
        live_gate_verified=True,
        owner_baseline_empty=True,
        behavior_passed=True,
    )

    assert verified == {
        "evidence_class": "live_default_agent",
        "ledger_eligible": True,
    }
    assert unverified["ledger_eligible"] is False
    assert unverified["evidence_class"] != "live_default_agent"


def test_live_claim_without_embedded_gateway_receipts_cannot_promote() -> None:
    acceptance = _load_acceptance_module()
    receipt = _run_receipt(FROZEN_CASE_IDS[0])
    del receipt["gateway_receipts"]

    result = acceptance.classify_evidence(
        execution_source="live_gateway",
        case_id=FROZEN_CASE_IDS[0],
        run_receipt=receipt,
        expected_agent_artifact_sha256="2" * 64,
        live_gate_verified=True,
        owner_baseline_empty=True,
        behavior_passed=True,
    )

    assert result["ledger_eligible"] is False
    assert result["evidence_class"] != "live_default_agent"
    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.validate_live_run_receipt(
            receipt,
            case_id=FROZEN_CASE_IDS[0],
            expected_agent_artifact_sha256="2" * 64,
        )
    _assert_error_code(error, "GATEWAY_PRODUCT_BINDING_MISMATCH")


@pytest.mark.parametrize(
    "missing_receipt",
    ("run", "checkpoint", "events", "token_usage", "model", "owner_baseline"),
)
def test_live_claim_requires_every_raw_gateway_receipt(
    missing_receipt: str,
) -> None:
    acceptance = _load_acceptance_module()
    receipt = _run_receipt(FROZEN_CASE_IDS[0])
    del receipt["gateway_receipts"][missing_receipt]

    result = acceptance.classify_evidence(
        execution_source="live_gateway",
        case_id=FROZEN_CASE_IDS[0],
        run_receipt=receipt,
        expected_agent_artifact_sha256="2" * 64,
        live_gate_verified=True,
        owner_baseline_empty=True,
        behavior_passed=True,
    )

    assert result["ledger_eligible"] is False
    assert result["evidence_class"] != "live_default_agent"


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ("event_thread", "GATEWAY_EVENT_RECEIPT_INVALID"),
        ("event_run", "GATEWAY_EVENT_RECEIPT_INVALID"),
        ("event_seq", "GATEWAY_EVENT_RECEIPT_INVALID"),
        ("call_event_seq", "PROVIDER_MODEL_RECEIPT_INVALID"),
        ("token_thread", "GATEWAY_PRODUCT_BINDING_MISMATCH"),
    ),
)
def test_raw_gateway_receipts_are_bound_to_one_ordered_run(
    mutation: str,
    code: str,
) -> None:
    acceptance = _load_acceptance_module()
    receipt = _run_receipt(FROZEN_CASE_IDS[0])
    if mutation == "event_thread":
        receipt["gateway_receipts"]["events"][0]["thread_id"] = "another-thread"
    elif mutation == "event_run":
        receipt["gateway_receipts"]["events"][0]["run_id"] = "another-run"
    elif mutation == "event_seq":
        receipt["gateway_receipts"]["events"][1]["seq"] = receipt["gateway_receipts"]["events"][0]["seq"]
    elif mutation == "call_event_seq":
        receipt["llm_calls"][0]["event_seq"] = receipt["llm_calls"][1]["event_seq"]
    else:
        receipt["gateway_receipts"]["token_usage"]["thread_id"] = "another-thread"

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.validate_live_run_receipt(
            receipt,
            case_id=FROZEN_CASE_IDS[0],
            expected_agent_artifact_sha256="2" * 64,
        )

    _assert_error_code(error, code)


def test_raw_and_flattened_effective_model_config_must_match() -> None:
    acceptance = _load_acceptance_module()
    receipt = _run_receipt(FROZEN_CASE_IDS[0])
    receipt["gateway_receipts"]["model"]["effective_config_sha256"] = "7" * 64

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.validate_live_run_receipt(
            receipt,
            case_id=FROZEN_CASE_IDS[0],
            expected_agent_artifact_sha256="2" * 64,
        )

    _assert_error_code(error, "GATEWAY_PRODUCT_BINDING_MISMATCH")


def test_raw_owner_baseline_is_bound_to_the_authenticated_default_owner() -> None:
    acceptance = _load_acceptance_module()
    receipt = _run_receipt(FROZEN_CASE_IDS[0])
    other_owner_backup = _empty_owner_backup("another-owner")
    baseline = receipt["gateway_receipts"]["owner_baseline"]
    baseline["backup"] = other_owner_backup
    baseline["gateway_export_receipt"] = _gateway_export_receipt(
        other_owner_backup,
    )

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.validate_live_run_receipt(
            receipt,
            case_id=FROZEN_CASE_IDS[0],
            expected_agent_artifact_sha256="2" * 64,
        )

    _assert_error_code(error, "OWNER_BACKUP_V5_INVALID")


@pytest.mark.parametrize(
    "response",
    (
        httpx.Response(
            500,
            json={"secret": "must-not-enter-the-failure-packet"},
            request=httpx.Request(
                "GET",
                "http://127.0.0.1:8001/api/personal-ip/data/export",
            ),
        ),
        httpx.Response(
            200,
            content=b"not-json: must-not-enter-the-failure-packet",
            request=httpx.Request(
                "GET",
                "http://127.0.0.1:8001/api/personal-ip/data/export",
            ),
        ),
    ),
)
def test_bad_gateway_export_retains_a_safe_raw_receipt_before_validation(
    response: httpx.Response,
) -> None:
    acceptance = _load_acceptance_module()
    evidence: dict[str, Any] = {}

    class Client:
        def get(self, _path: str) -> httpx.Response:
            return response

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance._gateway_export(
            Client(),
            base_url="http://127.0.0.1:8001",
            evidence_sink=evidence,
        )

    _assert_error_code(error, "OWNER_BACKUP_GATEWAY_RECEIPT_INVALID")
    assert evidence == {
        "gateway_export_failure_receipt": {
            "schema_version": "personal-ip-writer-v2-gateway-export-failure-receipt-v1",
            "method": "GET",
            "base_url": "http://127.0.0.1:8001",
            "path": "/api/personal-ip/data/export",
            "status_code": response.status_code,
            "cache_control": response.headers.get("Cache-Control"),
            "content_disposition": response.headers.get("Content-Disposition"),
            "wire_body_sha256": hashlib.sha256(response.content).hexdigest(),
            "wire_body_size_bytes": len(response.content),
        }
    }
    assert "must-not-enter-the-failure-packet" not in json.dumps(evidence)


def test_passed_packet_post_run_owner_cannot_drift_from_authenticated_owner(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    artifacts = _business_artifacts(FROZEN_CASE_IDS[0])
    lineage = artifacts["lineage.json"]
    lineage["content_work"]["owner_user_id"] = "another-owner"
    for record in (*lineage["direction_versions"], *lineage["script_versions"]):
        record["owner_user_id"] = "another-owner"
    artifacts["tool-receipt.json"]["tool_trace"][0]["owner_user_id"] = "another-owner"
    post_backup = _post_run_owner_backup(lineage)
    artifacts["owner-backup-v5.json"] = {
        "backup": post_backup,
        "gateway_export_receipt": _gateway_export_receipt(post_backup),
    }

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.write_result_packet(
            tmp_path / "cross-owner-packet",
            manifest=_manifest(FROZEN_CASE_IDS[0]),
            artifacts=artifacts,
        )

    _assert_error_code(error, "OWNER_POST_RUN_LINEAGE_MISMATCH")


def test_result_packet_refuses_directory_reuse_without_mutating_it(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    destination = tmp_path / "existing-result"
    destination.mkdir()
    sentinel = destination / "operator-note.txt"
    sentinel.write_text("preserve me\n", encoding="utf-8")
    before = _tree_snapshot(destination)

    with pytest.raises(acceptance.AcceptanceError) as error:
        _write_packet(
            acceptance,
            destination,
            FROZEN_CASE_IDS[0],
        )

    _assert_error_code(error, "RESULT_DIRECTORY_ALREADY_EXISTS")
    assert _tree_snapshot(destination) == before


def test_early_live_failure_still_seals_six_non_promotable_artifacts(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    destination = tmp_path / "early-live-failure"
    artifacts = {
        "case-input.json": {
            "case_id": FROZEN_CASE_IDS[0],
            "prompt": "frozen prompt was selected",
        },
        "answer.txt": "Acceptance failed before a valid final answer",
        "run-receipt.json": {
            "schema_version": "personal-ip-writer-v2-run-receipt-v1",
            "status": "error",
            "runtime_metadata": {},
            "usage": {"llm_call_count": 0, "total_tokens": 0},
            "llm_calls": [],
            "failure_stage": "pre_run_export",
        },
        "tool-receipt.json": {"tool_trace": []},
        "lineage.json": {},
        "owner-backup-v5.json": {"failure_stage": "pre_run_export"},
    }

    acceptance.write_result_packet(
        destination,
        manifest=_manifest(FROZEN_CASE_IDS[0], status="failed"),
        artifacts=artifacts,
    )

    assert tuple(sorted(path.name for path in destination.iterdir())) == tuple(sorted((*LIVE_PACKET_ARTIFACT_NAMES, "manifest.json", "manifest.json.sha256")))
    verified = acceptance.verify_result_packet(destination)
    assert verified["status"] == "failed"
    assert verified["ledger_eligible"] is False
    assert verified["evidence_class"] != "live_default_agent"
    assert verified["owner_post_run_verified"] is False


def test_late_live_failure_with_valid_receipts_still_cannot_promote(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    destination = acceptance.write_result_packet(
        tmp_path / "late-live-failure",
        manifest=_manifest(FROZEN_CASE_IDS[0], status="failed"),
        artifacts=_business_artifacts(FROZEN_CASE_IDS[0], status="passed"),
    )

    verified = acceptance.verify_result_packet(destination)

    assert verified["status"] == "failed"
    assert verified["owner_post_run_verified"] is True
    assert verified["provider_receipts_verified"] is True
    assert verified["evidence_class"] == "failed_acceptance"
    assert verified["ledger_eligible"] is False


def test_live_result_packet_seals_the_complete_six_artifact_business_record(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()

    destination = _write_packet(
        acceptance,
        tmp_path / "live-result",
        FROZEN_CASE_IDS[0],
    )

    assert tuple(sorted(path.name for path in destination.iterdir())) == tuple(sorted((*LIVE_PACKET_ARTIFACT_NAMES, "manifest.json", "manifest.json.sha256")))
    verified = acceptance.verify_result_packet(destination)
    assert verified["evidence_class"] == "live_default_agent"
    assert verified["ledger_eligible"] is True
    assert verified["model_identity_sha256"] == _model_identity_sha256("doubao-seed-2-0-pro-260215")


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_state",
        "unfinished_checkpoint",
        "answer_mismatch",
        "tool_arguments_mismatch",
        "tool_message_name",
        "tool_message_status",
    ),
)
def test_passed_packet_rederives_artifacts_from_the_raw_checkpoint(
    tmp_path: Path,
    mutation: str,
) -> None:
    acceptance = _load_acceptance_module()
    artifacts = _business_artifacts(FROZEN_CASE_IDS[0])
    checkpoint = artifacts["run-receipt.json"]["gateway_receipts"]["checkpoint"]
    if mutation == "missing_state":
        del checkpoint["state"]
    else:
        state = checkpoint["state"]
        messages = state["values"]["messages"]
        if mutation == "unfinished_checkpoint":
            state["next"] = ["writer_brain"]
        elif mutation == "answer_mismatch":
            messages[-1]["content"] = "checkpoint answer does not match answer.txt"
        elif mutation == "tool_arguments_mismatch":
            messages[1]["tool_calls"][0]["args"] = {
                **messages[1]["tool_calls"][0]["args"],
                "expected_route": "semantic_story",
            }
        elif mutation == "tool_message_name":
            messages[2]["name"] = "another_tool"
        else:
            messages[2]["status"] = None

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.write_result_packet(
            tmp_path / f"checkpoint-{mutation}",
            manifest=_manifest(FROZEN_CASE_IDS[0]),
            artifacts=artifacts,
        )

    _assert_error_code(error, "CHECKPOINT_RECEIPT_INVALID")


def test_checkpoint_verification_is_sealed_as_a_rederived_claim(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()

    packet = _write_packet(
        acceptance,
        tmp_path / "checkpoint-verified",
        FROZEN_CASE_IDS[0],
    )

    verified = acceptance.verify_result_packet(packet)
    assert verified["checkpoint_receipts_verified"] is True


def test_lead_recovery_count_is_rederived_and_sealed_instead_of_trusting_manifest(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    recovered = _write_packet(
        acceptance,
        tmp_path / "recovered-once",
        FROZEN_CASE_IDS[0],
        lead_recovery=True,
    )

    verified = acceptance.verify_result_packet(recovered)
    assert verified["lead_recovery_count"] == 1

    forged_manifest = _manifest(FROZEN_CASE_IDS[0])
    forged_manifest["lead_recovery_count"] = 0
    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.write_result_packet(
            tmp_path / "forged-recovery-count",
            manifest=forged_manifest,
            artifacts=_business_artifacts(
                FROZEN_CASE_IDS[0],
                lead_recovery=True,
            ),
        )

    _assert_error_code(error, "EVIDENCE_CLASSIFICATION_INVALID")


@pytest.mark.parametrize(
    "mutation",
    (
        "acceptance_invalid_marker",
        "second_acceptance_invalid_marker",
        "invalid_after_tool",
        "fallback",
        "other_tool",
        "raw_invalid_payload",
        "extra_tool_message",
    ),
)
def test_recovered_run_checkpoint_allows_only_one_invalid_attempt_and_one_real_execution(
    tmp_path: Path,
    mutation: str,
) -> None:
    acceptance = _load_acceptance_module()
    artifacts = _business_artifacts(
        FROZEN_CASE_IDS[0],
        lead_recovery=True,
    )
    messages = artifacts["run-receipt.json"]["gateway_receipts"]["checkpoint"]["state"]["values"]["messages"]
    invalid_message = {
        "type": "ai",
        "content": "",
        "additional_kwargs": {},
        "tool_calls": [],
        "invalid_tool_calls": [],
        "acceptance_invalid_tool_calls": [
            {
                "name": "ip_content_write",
                "classification": "malformed_tool_arguments",
            }
        ],
    }
    if mutation == "acceptance_invalid_marker":
        messages.insert(1, invalid_message)
    elif mutation == "second_acceptance_invalid_marker":
        messages.insert(1, invalid_message)
        messages.insert(2, copy.deepcopy(invalid_message))
    elif mutation == "invalid_after_tool":
        messages.insert(3, invalid_message)
    elif mutation == "fallback":
        messages[1]["additional_kwargs"]["deerflow_error_fallback"] = True
    elif mutation == "other_tool":
        invalid_message["acceptance_invalid_tool_calls"][0]["name"] = "web_search"
        messages.insert(1, invalid_message)
    elif mutation == "raw_invalid_payload":
        invalid_message["invalid_tool_calls"] = [
            {
                "name": "ip_content_write",
                "args": MALFORMED_TOOL_ARGS,
                "error": MALFORMED_TOOL_ERROR,
            }
        ]
        del invalid_message["acceptance_invalid_tool_calls"]
        messages.insert(1, invalid_message)
    else:
        messages.insert(3, copy.deepcopy(messages[2]))

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.write_result_packet(
            tmp_path / f"recovery-checkpoint-{mutation}",
            manifest=_manifest(FROZEN_CASE_IDS[0]),
            artifacts=artifacts,
        )

    _assert_error_code(error, "CHECKPOINT_RECEIPT_INVALID")


@pytest.mark.parametrize(
    "mutation",
    ("empty", "extra", "cross_owner", "cross_thread", "cross_id"),
)
def test_live_result_packet_requires_exact_post_run_backup_lineage(
    tmp_path: Path,
    mutation: str,
) -> None:
    acceptance = _load_acceptance_module()
    destination = tmp_path / f"invalid-post-run-{mutation}"
    artifacts = _business_artifacts(FROZEN_CASE_IDS[0])
    envelope = artifacts["owner-backup-v5.json"]
    backup = envelope["backup"]
    if mutation == "empty":
        backup = _empty_owner_backup("owner-acceptance")
    else:
        datasets = {dataset["name"]: dataset for dataset in backup["datasets"]}
        if mutation == "extra":
            datasets["content_works"]["records"].append(
                {
                    **datasets["content_works"]["records"][0],
                    "id": "unexpected-work",
                    "objective_id": "unexpected-objective",
                    "operation_key": "unexpected-operation",
                }
            )
        elif mutation == "cross_owner":
            datasets["script_versions"]["records"][0]["owner_user_id"] = "another-owner"
        elif mutation == "cross_thread":
            datasets["content_works"]["records"][0]["thread_id"] = "another-thread"
        else:
            datasets["script_versions"]["records"][0]["content_work_id"] = "another-work"
        backup = _resign_owner_backup(backup)
    envelope["backup"] = backup
    envelope["gateway_export_receipt"] = _gateway_export_receipt(backup)

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.write_result_packet(
            destination,
            manifest=_manifest(FROZEN_CASE_IDS[0]),
            artifacts=artifacts,
        )

    _assert_error_code(error, "OWNER_POST_RUN_LINEAGE_MISMATCH")
    assert not destination.exists()


@pytest.mark.parametrize("missing_name", LIVE_PACKET_ARTIFACT_NAMES)
def test_live_result_packet_refuses_any_missing_business_artifact(
    tmp_path: Path,
    missing_name: str,
) -> None:
    acceptance = _load_acceptance_module()
    destination = tmp_path / f"missing-{missing_name}"
    artifacts = _business_artifacts(FROZEN_CASE_IDS[0])
    del artifacts[missing_name]

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.write_result_packet(
            destination,
            manifest=_manifest(FROZEN_CASE_IDS[0]),
            artifacts=artifacts,
        )

    _assert_error_code(error, "LIVE_PACKET_ARTIFACTS_INCOMPLETE")
    assert not destination.exists()


def test_synthetic_packet_cannot_self_declare_live_or_ledger_eligible(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    destination = tmp_path / "forged-live-claim"
    manifest = _manifest(FROZEN_CASE_IDS[0], execution_source="fixture")
    manifest.update(
        {
            "evidence_class": "live_default_agent",
            "ledger_eligible": True,
            "provider_receipts_verified": True,
            "gateway_binding_verified": True,
        }
    )

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.write_result_packet(
            destination,
            manifest=manifest,
            artifacts=_business_artifacts(FROZEN_CASE_IDS[0]),
        )

    _assert_error_code(error, "EVIDENCE_CLASSIFICATION_INVALID")
    assert not destination.exists()


def test_live_packet_cannot_self_report_provider_verification_over_invalid_events(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    destination = tmp_path / "forged-provider-claim"
    manifest = _manifest(FROZEN_CASE_IDS[0])
    manifest.update(
        {
            "evidence_class": "live_default_agent",
            "ledger_eligible": True,
            "provider_receipts_verified": True,
            "gateway_binding_verified": True,
        }
    )
    artifacts = _business_artifacts(FROZEN_CASE_IDS[0])
    run_receipt = artifacts["run-receipt.json"]
    for call in run_receipt["llm_calls"]:
        call["usage"] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
    run_receipt["usage"]["total_tokens"] = 0
    run_receipt["provider_receipts_verified"] = True

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.write_result_packet(
            destination,
            manifest=manifest,
            artifacts=artifacts,
        )

    _assert_error_code(error, "PROVIDER_MODEL_RECEIPT_INVALID")
    assert not destination.exists()


def test_live_packet_rederives_behavior_from_answer_tools_and_lineage(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    destination = tmp_path / "forged-behavior-claim"
    manifest = _manifest(FROZEN_CASE_IDS[0])
    manifest["behavior_passed"] = True
    artifacts = _business_artifacts(FROZEN_CASE_IDS[0])
    artifacts["lineage.json"]["content_work"]["editorial_program_version_id"] = "forged-program-version"

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.write_result_packet(
            destination,
            manifest=manifest,
            artifacts=artifacts,
        )

    _assert_error_code(error, "BEHAVIOR_ACCEPTANCE_FAILED")
    assert not destination.exists()


def test_packet_verifier_rederives_evidence_after_manifest_and_sidecar_resigning(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    destination = _write_packet(
        acceptance,
        tmp_path / "synthetic-result",
        FROZEN_CASE_IDS[0],
        execution_source="fixture",
    )
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "evidence_class": "live_default_agent",
            "ledger_eligible": True,
            "provider_receipts_verified": True,
            "gateway_binding_verified": True,
        }
    )
    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    (destination / "manifest.json.sha256").write_text(
        hashlib.sha256(manifest_path.read_bytes()).hexdigest() + "\n",
        encoding="ascii",
    )

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.verify_result_packet(destination)

    _assert_error_code(error, "EVIDENCE_CLASSIFICATION_INVALID")


@pytest.mark.parametrize("tamper_target", ("artifact", "manifest"))
def test_result_packet_verification_detects_digest_tampering(
    tmp_path: Path,
    tamper_target: str,
) -> None:
    acceptance = _load_acceptance_module()
    destination = _write_packet(
        acceptance,
        tmp_path / "result",
        FROZEN_CASE_IDS[0],
    )
    verified = acceptance.verify_result_packet(destination)
    assert verified["case_id"] == FROZEN_CASE_IDS[0]

    if tamper_target == "artifact":
        (destination / "answer.txt").write_text(
            "tampered answer\n",
            encoding="utf-8",
        )
    else:
        manifest_path = destination / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "failed"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.verify_result_packet(destination)

    _assert_error_code(error, "RESULT_DIGEST_MISMATCH")


def test_verify_matrix_accepts_exactly_four_bound_passing_live_packets(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    recovered_case = FROZEN_CASE_IDS[1]
    packets = [
        _write_packet(
            acceptance,
            tmp_path / case_id,
            case_id,
            lead_recovery=case_id == recovered_case,
        )
        for case_id in reversed(FROZEN_CASE_IDS)
    ]

    result = acceptance.verify_matrix(packets)

    assert result["status"] == "passed"
    assert tuple(result["case_ids"]) == FROZEN_CASE_IDS
    assert result["git_commit"] == "1" * 40
    assert result["agent_artifact_sha256"] == "2" * 64
    assert result["model_identity_sha256"] == _model_identity_sha256("doubao-seed-2-0-pro-260215")
    assert list(result["lead_recovery_count_by_case"]) == list(FROZEN_CASE_IDS)
    assert result["lead_recovery_count_by_case"] == {case_id: int(case_id == recovered_case) for case_id in FROZEN_CASE_IDS}
    assert result["evidence_class"] == "live_default_agent"
    assert result["ledger_eligible"] is True


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ("missing_case", "MATRIX_CASE_SET_INVALID"),
        ("duplicate_case", "MATRIX_CASE_SET_INVALID"),
        ("failed_case", "MATRIX_CASE_FAILED"),
        ("git_commit", "MATRIX_COMMIT_MISMATCH"),
        ("agent_artifact", "MATRIX_AGENT_ARTIFACT_MISMATCH"),
        ("model", "MATRIX_MODEL_MISMATCH"),
        ("effective_model_config", "MATRIX_MODEL_MISMATCH"),
    ),
)
def test_verify_matrix_fails_closed_on_incomplete_failed_or_mixed_identity_runs(
    tmp_path: Path,
    mutation: str,
    code: str,
) -> None:
    acceptance = _load_acceptance_module()
    packets: list[Path] = []
    for index, case_id in enumerate(FROZEN_CASE_IDS):
        overrides: dict[str, Any] = {}
        model_name = "doubao-seed-2-0-pro-260215"
        if index == 3 and mutation == "failed_case":
            overrides["status"] = "failed"
        elif index == 3 and mutation == "git_commit":
            overrides["git_commit"] = "a" * 40
        elif index == 3 and mutation == "agent_artifact":
            overrides["agent_artifact_sha256"] = "b" * 64
        elif index == 3 and mutation == "model":
            model_name = "doubao-seed-2-0-lite-260215"
        destination = tmp_path / f"packet-{index}"
        if index == 3 and mutation == "effective_model_config":
            manifest = _manifest(case_id, **overrides)
            artifacts = _business_artifacts(case_id, model_name=model_name)
            effective_digest = "7" * 64
            artifacts["run-receipt.json"]["runtime_metadata"]["effective_model"]["effective_config_sha256"] = effective_digest
            artifacts["run-receipt.json"]["gateway_receipts"]["model"]["effective_config_sha256"] = effective_digest
            packets.append(
                acceptance.write_result_packet(
                    destination,
                    manifest=manifest,
                    artifacts=artifacts,
                )
            )
        else:
            packets.append(
                _write_packet(
                    acceptance,
                    destination,
                    case_id,
                    model_name=model_name,
                    **overrides,
                )
            )
    if mutation == "missing_case":
        packets.pop()
    elif mutation == "duplicate_case":
        packets[-1] = packets[0]

    with pytest.raises(acceptance.AcceptanceError) as error:
        acceptance.verify_matrix(packets)

    _assert_error_code(error, code)


def test_synthetic_matrix_can_pass_contract_checks_but_cannot_promote_ledger_evidence(
    tmp_path: Path,
) -> None:
    acceptance = _load_acceptance_module()
    packets = [
        _write_packet(
            acceptance,
            tmp_path / case_id,
            case_id,
            execution_source="fixture",
        )
        for case_id in FROZEN_CASE_IDS
    ]

    result = acceptance.verify_matrix(packets)

    assert result["status"] == "passed"
    assert result["evidence_class"] == "synthetic_contract"
    assert result["ledger_eligible"] is False
