#!/usr/bin/env python3
"""Run one paid, research-only IP director route or story A/B arm.

The original direct Ark transport remains available as the control path.  The
Gateway transport exercises the real DeerFlow Agent API while keeping the
contract and method in a short-lived, zero-capability Agent SOUL.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seed-evolving"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8001"
TEST_STATE_RELATIVE = Path("backend/.deer-flow-ip-test")
TEST_MARKER_NAME = ".ip-agent-test-mode.json"
PRODUCT_RUNTIME_PROFILE_NAME = "product-runtime-profile.yaml"
GATEWAY_AGENT_PREFIX = "ip-director-loop"
GATEWAY_RECURSION_LIMIT = 20
OUTPUT_CONTRACT_VERSION = "v2"
TREATMENT_METHOD_VERSIONS = {"route": "v3", "story": "v2"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("route", "story"), required=True)
    parser.add_argument("--arm", choices=("placebo", "method"), required=True)
    parser.add_argument("--transport", choices=("ark", "gateway"), default="gateway")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--route-result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--thinking", choices=("enabled", "disabled"), default="enabled")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--timeout", type=float, default=360.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _prompt_paths(asset_root: Path, *, stage: str, arm: str) -> tuple[Path, Path]:
    """Resolve one shared output contract and the arm-specific method text."""

    contract_path = asset_root / (
        f"director-{stage}-output-contract-{OUTPUT_CONTRACT_VERSION}.md"
    )
    method_version = TREATMENT_METHOD_VERSIONS[stage] if arm == "method" else "v1"
    arm_path = asset_root / f"director-{stage}-{arm}-{method_version}.md"
    return contract_path, arm_path


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_bytes(path: Path) -> bytes:
    return path.resolve(strict=True).read_bytes()


def _load_repo_env(path: Path) -> None:
    """Load simple KEY=VALUE entries without adding a runtime dependency."""

    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def _load_case(path: Path, case_id: str) -> dict[str, Any]:
    suite = json.loads(_read_bytes(path).decode("utf-8"))
    matches = [case for case in suite.get("cases", []) if case.get("case_id") == case_id]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one scenario for {case_id!r}, found {len(matches)}")
    return matches[0]


def _load_validator(module_path: Path):
    spec = importlib.util.spec_from_file_location("ip_director_loop", module_path)
    if spec is None or spec.loader is None:
        raise SystemExit("could not load director loop validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_route_result(path: Path) -> dict[str, Any]:
    payload = json.loads(_read_bytes(path).decode("utf-8"))
    if payload.get("schema_version") == "ip-director-loop-ab-result-v1":
        payload = (payload.get("response") or {}).get("content")
    if not isinstance(payload, dict):
        raise SystemExit("route result must be a route JSON object or a director A/B artifact")
    return payload


def _compose_system(contract_text: str, arm_text: str) -> str:
    return f"{contract_text.rstrip()}\n\n---\n\n{arm_text.rstrip()}\n"


def _parse_json_content(content: Any) -> tuple[Any, str | None, str | None]:
    """Parse raw JSON or one complete provider-added Markdown JSON fence."""

    if not isinstance(content, str):
        return None, None, "TypeError: response content is not text"
    candidate = content.strip()
    normalization: str | None = None
    if candidate.startswith("```json\n") and candidate.endswith("```"):
        candidate = candidate[len("```json\n") : -len("```")].strip()
        normalization = "single_json_markdown_fence_removed"
    try:
        return json.loads(candidate), normalization, None
    except json.JSONDecodeError as exc:
        return None, normalization, f"{type(exc).__name__}: {exc}"


def _request(
    *,
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout: float,
) -> tuple[dict[str, Any], bytes, float]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw_body = response.read()
    body = json.loads(raw_body.decode("utf-8"))
    return body, raw_body, time.monotonic() - started


def _http_json(
    *,
    method: str,
    url: str,
    timeout: float,
    payload: dict[str, Any] | None = None,
) -> tuple[Any, bytes]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_body = response.read()
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gateway HTTP {exc.code} for {method} {url}: {error_body[:1000]}") from exc
    if not raw_body:
        return {}, raw_body
    try:
        return json.loads(raw_body.decode("utf-8")), raw_body
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gateway returned non-JSON for {method} {url}") from exc


def _top_level_yaml_bool(text: str, key: str) -> bool | None:
    match = re.search(rf"(?m)^{re.escape(key)}\s*:\s*(true|false)\s*(?:#.*)?$", text, re.IGNORECASE)
    if match is None:
        return None
    return match.group(1).lower() == "true"


def _validate_gateway_test_state(repo_root: Path) -> Path:
    """Require the fixed marked test home and an explicitly disabled pin.

    A product runtime profile pins customer runs to the product-owned Agent.
    The director canary needs a different temporary Agent, so this runner
    refuses to proceed while the isolated profile is enabled.  It never edits
    that operator-owned profile on the caller's behalf.
    """

    root = repo_root.resolve()
    state_dir = (root / TEST_STATE_RELATIVE).resolve()
    if not state_dir.is_relative_to(root):
        raise RuntimeError("Gateway director test state escaped the repository")
    marker_path = state_dir / TEST_MARKER_NAME
    if not marker_path.is_file():
        raise RuntimeError(
            "Gateway transport requires the prepared, marked backend/.deer-flow-ip-test state"
        )
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": "ip-agent-test-mode-v1",
        "root": str(root),
        "state_dir": str(state_dir),
    }
    for key, expected_value in expected.items():
        if marker.get(key) != expected_value:
            raise RuntimeError(
                f"Gateway test-state marker mismatch for {key}: expected {expected_value!r}"
            )
    profile_path = state_dir / PRODUCT_RUNTIME_PROFILE_NAME
    if not profile_path.is_file():
        raise RuntimeError(f"Gateway test state is missing {PRODUCT_RUNTIME_PROFILE_NAME}")
    enabled = _top_level_yaml_bool(profile_path.read_text(encoding="utf-8"), "enabled")
    if enabled is not False:
        raise RuntimeError(
            "Gateway director canary is blocked because the isolated product runtime profile is enabled; "
            "disable it explicitly in backend/.deer-flow-ip-test/product-runtime-profile.yaml before the run. "
            "The runner will not patch or bypass product Agent pinning."
        )
    return state_dir


def _write_private(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_bytes(content)
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _temporary_gateway_agent(
    state_dir: Path,
    *,
    agent_name: str,
    model: str,
    soul_text: str,
) -> Iterator[dict[str, Any]]:
    agents_root = (state_dir / "users" / "default" / "agents").resolve()
    agent_dir = (agents_root / agent_name).resolve()
    if not agent_dir.is_relative_to(agents_root):
        raise RuntimeError("temporary Gateway Agent path escaped the isolated owner")
    if agent_dir.exists():
        raise RuntimeError(f"temporary Gateway Agent already exists: {agent_dir}")
    config_text = (
        f"name: {agent_name}\n"
        "description: Isolated IP director Gateway canary\n"
        f"model: {model}\n"
        "skills: []\n"
        "tool_allowlist: []\n"
        "memory_enabled: false\n"
    )
    config_bytes = config_text.encode("utf-8")
    soul_bytes = soul_text.encode("utf-8")
    agent_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    agent_dir.chmod(0o700)
    config_path = agent_dir / "config.yaml"
    soul_path = agent_dir / "SOUL.md"
    try:
        _write_private(config_path, config_bytes)
        _write_private(soul_path, soul_bytes)
        yield {
            "agent_name": agent_name,
            "agent_dir": agent_dir,
            "config_sha256": _sha256_bytes(config_bytes),
            "soul_sha256": _sha256_bytes(soul_bytes),
        }
    finally:
        for path, expected in ((config_path, config_bytes), (soul_path, soul_bytes)):
            if path.is_file() and path.read_bytes() != expected:
                raise RuntimeError(f"refusing to remove modified temporary Gateway Agent file: {path}")
        entries = {path.name for path in agent_dir.iterdir()}
        if entries != {"config.yaml", "SOUL.md"}:
            raise RuntimeError(
                f"refusing to remove temporary Gateway Agent with unexpected files: {sorted(entries)!r}"
            )
        config_path.unlink()
        soul_path.unlink()
        agent_dir.rmdir()


def _gateway_run_body(
    *,
    agent_name: str,
    model: str,
    user_text: str,
    thinking: str,
) -> dict[str, Any]:
    thinking_enabled = thinking == "enabled"
    return {
        "assistant_id": agent_name,
        "input": {"messages": [{"role": "user", "content": user_text}]},
        "config": {"recursion_limit": GATEWAY_RECURSION_LIMIT},
        "context": {
            "agent_name": agent_name,
            "model_name": model,
            "mode": "thinking" if thinking_enabled else "flash",
            "thinking_enabled": thinking_enabled,
            "is_plan_mode": False,
            "subagent_enabled": False,
        },
        "on_disconnect": "continue",
    }


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _normalize_gateway_state(values: Any) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    messages = values.get("messages") if isinstance(values, dict) else None
    if not isinstance(messages, list):
        messages = []
    answers: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        message_type = message.get("type") or message.get("role")
        if message_type in {"ai", "assistant"}:
            calls = message.get("tool_calls")
            if isinstance(calls, list):
                tool_calls.extend(call for call in calls if isinstance(call, dict))
            hidden = isinstance(message.get("additional_kwargs"), dict) and message["additional_kwargs"].get(
                "hide_from_ui"
            ) is True
            answer = _message_text(message.get("content"))
            if answer and not hidden:
                answers.append(answer)
        elif message_type == "tool":
            tool_results.append(message)
    return (answers[-1] if answers else ""), tool_calls, tool_results


def _gateway_runtime_summary(events: Any) -> dict[str, Any]:
    if not isinstance(events, list):
        events = []
    runtime_metadata: dict[str, Any] = {}
    llm_calls: list[dict[str, Any]] = []
    tool_result_events = 0
    event_receipts: list[dict[str, Any]] = []
    actual_models: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type")
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        event_receipts.append(
            {
                "seq": event.get("seq"),
                "event_type": event_type,
                "category": event.get("category"),
                "caller": metadata.get("caller"),
                "llm_call_index": metadata.get("llm_call_index"),
            }
        )
        if event_type == "run.start":
            runtime_metadata = dict(metadata)
        elif event_type == "llm.ai.response":
            content = event.get("content") if isinstance(event.get("content"), dict) else {}
            response_metadata = (
                content.get("response_metadata") if isinstance(content.get("response_metadata"), dict) else {}
            )
            actual_model = response_metadata.get("model_name") or response_metadata.get("model")
            if isinstance(actual_model, str) and actual_model:
                actual_models.append(actual_model)
            llm_calls.append(
                {
                    "call_index": metadata.get("llm_call_index"),
                    "caller": metadata.get("caller"),
                    "latency_ms": metadata.get("latency_ms"),
                    "usage": metadata.get("usage"),
                    "actual_model": actual_model,
                }
            )
        elif event_type == "llm.tool.result":
            tool_result_events += 1
    return {
        "runtime_metadata": runtime_metadata,
        "llm_calls": llm_calls,
        "tool_result_event_count": tool_result_events,
        "event_receipts": event_receipts,
        "actual_models": actual_models,
    }


def _gateway_validation_issues(
    *,
    agent_name: str,
    model: str,
    thinking: str,
    run_record: Any,
    runtime_summary: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    final_answer: str,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def add(code: str, message: str) -> None:
        issues.append({"code": code, "message": message})

    record = run_record if isinstance(run_record, dict) else {}
    runtime = runtime_summary.get("runtime_metadata")
    runtime = runtime if isinstance(runtime, dict) else {}
    llm_calls = runtime_summary.get("llm_calls")
    llm_calls = llm_calls if isinstance(llm_calls, list) else []
    if record.get("status") != "success":
        add("gateway.run_status", "Gateway run did not finish successfully")
    if record.get("assistant_id") != agent_name:
        add("gateway.assistant_id", "persisted run assistant_id differs from the temporary Agent")
    if runtime.get("agent_name") != agent_name:
        add("gateway.runtime_agent", "runtime agent_name differs from assistant_id")
    if runtime.get("model_name") != model:
        add("gateway.runtime_model", "runtime model is not the explicitly requested model")
    expected_thinking = thinking == "enabled"
    if runtime.get("thinking_enabled") is not expected_thinking:
        add("gateway.runtime_thinking", "runtime thinking mode differs from the requested mode")
    for key, expected in {
        "available_skills": [],
        "indexed_skill_names": [],
        "tool_allowlist": [],
        "assembled_tool_names": [],
    }.items():
        if runtime.get(key) != expected:
            add(f"gateway.runtime_{key}", f"runtime {key} is not empty")
    if runtime.get("memory_enabled") is not False:
        add("gateway.runtime_memory", "runtime memory is not disabled")
    if len(llm_calls) != 1 or record.get("llm_call_count") != 1:
        add("gateway.llm_count", "expected exactly one lead-Agent LLM call")
    elif llm_calls[0].get("caller") != "lead_agent":
        add("gateway.llm_caller", "the only LLM call was not attributed to the lead Agent")
    if tool_calls or tool_results or runtime_summary.get("tool_result_event_count") != 0:
        add("gateway.tool_call", "zero-tool director canary emitted a tool call or tool result")
    if not final_answer.strip():
        add("gateway.final_answer", "Gateway run has no visible final answer")
    return issues


def _request_gateway(
    *,
    gateway_url: str,
    state_dir: Path,
    model: str,
    thinking: str,
    system_text: str,
    user_text: str,
    timeout: float,
) -> tuple[dict[str, Any], float]:
    base_url = gateway_url.rstrip("/")
    nonce = uuid.uuid4().hex
    agent_name = f"{GATEWAY_AGENT_PREFIX}-{nonce[:12]}"
    started = time.monotonic()
    with _temporary_gateway_agent(
        state_dir,
        agent_name=agent_name,
        model=model,
        soul_text=system_text,
    ) as surface:
        models, _ = _http_json(method="GET", url=f"{base_url}/api/models", timeout=timeout)
        available = models.get("models") if isinstance(models, dict) else None
        model_surface = next(
            (
                item
                for item in available or []
                if isinstance(item, dict) and item.get("name") == model
            ),
            None,
        )
        if model_surface is None:
            raise RuntimeError(f"Gateway does not expose the explicitly requested model {model!r}")
        assistant, _ = _http_json(
            method="GET",
            url=f"{base_url}/api/assistants/{agent_name}",
            timeout=timeout,
        )
        if not isinstance(assistant, dict) or assistant.get("assistant_id") != agent_name:
            raise RuntimeError("Gateway cannot resolve the temporary Agent from the marked test state")
        thread_id = str(uuid.uuid4())
        thread_body = {
            "thread_id": thread_id,
            "assistant_id": agent_name,
            "metadata": {"test_contract": "ip-director-loop-gateway-v1"},
        }
        _http_json(
            method="POST",
            url=f"{base_url}/api/threads",
            timeout=timeout,
            payload=thread_body,
        )
        run_body = _gateway_run_body(
            agent_name=agent_name,
            model=model,
            user_text=user_text,
            thinking=thinking,
        )
        created_run, _ = _http_json(
            method="POST",
            url=f"{base_url}/api/threads/{thread_id}/runs",
            timeout=timeout,
            payload=run_body,
        )
        run_id = created_run.get("run_id") if isinstance(created_run, dict) else None
        if not isinstance(run_id, str) or not run_id:
            raise RuntimeError("Gateway asynchronous run creation returned no run_id")

        deadline = started + timeout
        record: dict[str, Any] = created_run
        while record.get("status") in {"pending", "running"}:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                try:
                    _http_json(
                        method="POST",
                        url=(
                            f"{base_url}/api/threads/{thread_id}/runs/{run_id}/cancel"
                            "?action=interrupt&wait=true"
                        ),
                        timeout=min(30.0, timeout),
                    )
                except RuntimeError:
                    pass
                raise RuntimeError(
                    f"Gateway Agent run {run_id} exceeded the {timeout:g}s experiment timeout and was interrupted"
                )
            time.sleep(min(2.0, remaining))
            refreshed, _ = _http_json(
                method="GET",
                url=f"{base_url}/api/threads/{thread_id}/runs/{run_id}",
                timeout=min(30.0, max(1.0, remaining)),
            )
            if not isinstance(refreshed, dict):
                raise RuntimeError("Gateway run status response is not an object")
            record = refreshed

        state, _ = _http_json(
            method="GET",
            url=f"{base_url}/api/threads/{thread_id}/state",
            timeout=min(30.0, timeout),
        )
        state_values = state.get("values") if isinstance(state, dict) else None
        events, events_raw = _http_json(
            method="GET",
            url=f"{base_url}/api/threads/{thread_id}/runs/{run_id}/events",
            timeout=timeout,
        )
        token_usage, _ = _http_json(
            method="GET",
            url=f"{base_url}/api/threads/{thread_id}/token-usage",
            timeout=timeout,
        )
        final_answer, tool_calls, tool_results = _normalize_gateway_state(state_values)
        runtime_summary = _gateway_runtime_summary(events)
        issues = _gateway_validation_issues(
            agent_name=agent_name,
            model=model,
            thinking=thinking,
            run_record=record,
            runtime_summary=runtime_summary,
            tool_calls=tool_calls,
            tool_results=tool_results,
            final_answer=final_answer,
        )
        return (
            {
                "thread_id": thread_id,
                "run_id": run_id,
                "agent_name": agent_name,
                "surface": {
                    "config_sha256": surface["config_sha256"],
                    "soul_sha256": surface["soul_sha256"],
                    "skills": [],
                    "tool_allowlist": [],
                    "memory_enabled": False,
                },
                "model_surface": model_surface,
                "thread_request_sha256": _sha256_bytes(
                    json.dumps(
                        thread_body,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ),
                "run_request_sha256": _sha256_bytes(
                    json.dumps(
                        run_body,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ),
                "run_record": record,
                "token_usage": token_usage,
                "events_sha256": _sha256_bytes(events_raw),
                "events": runtime_summary["event_receipts"],
                "runtime_metadata": runtime_summary["runtime_metadata"],
                "llm_calls": runtime_summary["llm_calls"],
                "tool_calls": tool_calls,
                "tool_results": tool_results,
                "content": final_answer,
                "transport_validation_issues": issues,
            },
            time.monotonic() - started,
        )


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    asset_root = repo_root / "product" / "research" / "ip-agent" / "director-core"
    scenarios_path = asset_root / "director-loop-scenarios-v1.json"
    # Both A/B arms must answer the same epistemic contract.  Only the method
    # text changes between arms; mixing a v2 method with the legacy v1 contract
    # makes the experiment uninterpretable and previously caused schema drift.
    contract_path, arm_path = _prompt_paths(
        asset_root,
        stage=args.stage,
        arm=args.arm,
    )
    validator_path = repo_root / "product" / "research" / "ip-agent" / "python" / "ip_director_loop.py"

    case = _load_case(scenarios_path, args.case_id)
    validator = _load_validator(validator_path)
    brief_issues = validator.validate_brief(case)
    if brief_issues:
        raise SystemExit(f"invalid frozen brief: {json.dumps(brief_issues, ensure_ascii=False)}")

    contract_bytes = _read_bytes(contract_path)
    arm_bytes = _read_bytes(arm_path)
    case_bytes = json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    system_text = _compose_system(contract_bytes.decode("utf-8"), arm_bytes.decode("utf-8"))
    route_result: dict[str, Any] | None = None
    route_result_bytes: bytes | None = None
    if args.stage == "route":
        if args.route_result is not None:
            raise SystemExit("--route-result is only valid for the story stage")
        model_input: dict[str, Any] = {"brief": case}
    else:
        if args.route_result is None:
            raise SystemExit("story stage requires --route-result")
        route_result = _load_route_result(args.route_result)
        route_issues = validator.validate_route_result(route_result, case)
        if route_issues:
            raise SystemExit(f"invalid frozen route: {json.dumps(route_issues, ensure_ascii=False)}")
        route_result_bytes = json.dumps(
            route_result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        model_input = {
            "brief": case,
            "source_route_sha256": validator.canonical_sha256(route_result),
            "frozen_route": route_result,
        }
    exact_schema = (
        "ip-director-route-result-v2"
        if args.stage == "route"
        else "ip-director-story-result-v2"
    )
    user_text = (
        "以下是冻结的隔离研究输入。只返回本阶段合同规定的 JSON。"
        f"schema_version 必须逐字等于 {exact_schema}：\n"
    ) + json.dumps(
        model_input,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        "stream": False,
        "temperature": 0,
        "max_tokens": args.max_tokens,
        "thinking": {"type": args.thinking},
        "response_format": {"type": "json_object"},
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    request_evidence = {
        "transport": args.transport,
        "stage": args.stage,
        "arm": args.arm,
        "case_id": args.case_id,
        "model": args.model,
        "thinking": args.thinking,
        "contract_path": str(contract_path.relative_to(repo_root)),
        "contract_sha256": _sha256_bytes(contract_bytes),
        "arm_path": str(arm_path.relative_to(repo_root)),
        "arm_sha256": _sha256_bytes(arm_bytes),
        "brief_path": str(scenarios_path.relative_to(repo_root)),
        "brief_sha256": _sha256_bytes(case_bytes),
        "system_bytes": len(system_text.encode("utf-8")),
        "user_bytes": len(user_text.encode("utf-8")),
    }
    if args.transport == "ark":
        request_evidence.update(
            {
                "temperature": 0,
                "max_tokens": args.max_tokens,
                "response_format": "json_object",
                "ark_payload_sha256": _sha256_bytes(payload_bytes),
            }
        )
    else:
        request_evidence["gateway_run_controls"] = {
            "thinking_enabled": args.thinking == "enabled",
            "recursion_limit": GATEWAY_RECURSION_LIMIT,
        }
    if route_result_bytes is not None and args.route_result is not None:
        request_evidence.update(
            {
                "route_result_path": str(args.route_result),
                "route_result_sha256": _sha256_bytes(route_result_bytes),
            }
        )
    if args.dry_run:
        if args.transport == "gateway":
            state_dir = _validate_gateway_test_state(repo_root)
            request_evidence.update(
                {
                    "gateway_url": args.gateway_url,
                    "test_state_dir": str(state_dir),
                    "gateway_agent_capabilities": {
                        "skills": [],
                        "tool_allowlist": [],
                        "memory_enabled": False,
                    },
                }
            )
        print(json.dumps(request_evidence, ensure_ascii=False, indent=2))
        return 0

    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing result: {args.output}")
    gateway_result: dict[str, Any] | None = None
    if args.transport == "ark":
        _load_repo_env(repo_root / ".env")
        api_key = os.environ.get("VOLCENGINE_API_KEY")
        if not api_key:
            raise SystemExit("VOLCENGINE_API_KEY is not configured")
        try:
            body, raw_body, elapsed = _request(
                base_url=args.base_url,
                api_key=api_key,
                payload=payload,
                timeout=args.timeout,
            )
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"Ark HTTP {exc.code}: {error_body[:1000]}") from exc
        choices = body.get("choices") or []
        choice = choices[0] if choices else {}
        message = choice.get("message") or {}
        content = message.get("content") or ""
    else:
        try:
            state_dir = _validate_gateway_test_state(repo_root)
            gateway_result, elapsed = _request_gateway(
                gateway_url=args.gateway_url,
                state_dir=state_dir,
                model=args.model,
                thinking=args.thinking,
                system_text=system_text,
                user_text=user_text,
                timeout=args.timeout,
            )
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        content = gateway_result["content"]
        body = {}
        raw_body = json.dumps(gateway_result, ensure_ascii=False, sort_keys=True).encode("utf-8")
        choice = {}
    parsed, parse_normalization, parse_error = _parse_json_content(content)
    if parse_error is not None:
        validation_issues = [{"code": "response.json", "message": parse_error}]
    elif args.stage == "route":
        validation_issues = validator.validate_route_result(parsed, case)
    else:
        assert route_result is not None
        validation_issues = validator.validate_story_result(parsed, case, route_result)

    if gateway_result is not None:
        validation_issues = [*gateway_result["transport_validation_issues"], *validation_issues]
    response = {
        "id": body.get("id"),
        "actual_model": body.get("model"),
        "elapsed_seconds": round(elapsed, 3),
        "finish_reason": choice.get("finish_reason"),
        "usage": body.get("usage"),
        "provider_response_sha256": _sha256_bytes(raw_body),
        "parse_normalization": parse_normalization,
        "json_parse_error": parse_error,
        "content": parsed if parse_error is None else content,
    }
    if gateway_result is not None:
        llm_calls = gateway_result.get("llm_calls") or []
        model_surface = gateway_result.get("model_surface") or {}
        actual_model = (
            llm_calls[0].get("actual_model")
            if len(llm_calls) == 1 and llm_calls[0].get("actual_model")
            else model_surface.get("model")
        )
        response.update(
            {
                "id": gateway_result.get("run_id"),
                "actual_model": actual_model,
                "finish_reason": gateway_result.get("run_record", {}).get("stop_reason"),
                "usage": gateway_result.get("token_usage"),
                "gateway": {
                    key: value
                    for key, value in gateway_result.items()
                    if key not in {"content", "transport_validation_issues"}
                },
            }
        )
    result = {
        "schema_version": "ip-director-loop-ab-result-v1",
        "scope": (
            "research_direct_provider_only"
            if args.transport == "ark"
            else "research_isolated_gateway_agent"
        ),
        "product_capability": False,
        "request": request_evidence,
        "response": response,
        "mechanical_validation": {
            "passed": not validation_issues,
            "issues": validation_issues,
        },
        "quality_verdict": "pending_blind_review",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "elapsed_seconds": result["response"]["elapsed_seconds"],
                "actual_model": result["response"]["actual_model"],
                "finish_reason": result["response"]["finish_reason"],
                "usage": result["response"]["usage"],
                "json_parse_error": parse_error,
                "mechanical_validation": result["mechanical_validation"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
