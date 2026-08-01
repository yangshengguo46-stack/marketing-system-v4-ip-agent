#!/usr/bin/env python3
"""Prepare and run the isolated M2 IP-Agent model/Skill comparison."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import sys
import uuid
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import httpx
import yaml

M2_REPLAY_SCHEMA_VERSION = "ip-agent-m2-replay-v2"
M2_RECURSION_LIMIT = 100
TEST_MODE_SCHEMA_VERSION = "ip-agent-test-mode-v1"
TEST_STATE_RELATIVE = Path("backend/.deer-flow-ip-test")
TEST_MARKER_NAME = ".ip-agent-test-mode.json"
TEST_EXTENSIONS_CONFIG_NAME = "extensions_config.json"
TEST_PROFILE_EVIDENCE = "evidence"
EVIDENCE_MCP_SERVER_NAME = "ip_evidence"
M2_LOCK_NAME = ".ip-agent-m2-replay.lock"
MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

FROZEN_PROMPT = (
    "我的产品是黄金礼品，重点是礼品，不是黄金本身。目标是做一个能长期积累影响力并带来成交的 IP。"
    "请参考这个对标账号：https://v.douyin.com/Q157NhQ4X1Q/ ，基于你实际取得的证据，给出我的 IP "
    "主体、表现形式、长期内容/冲突引擎、哪些机制可迁移和不可照搬，并完成第一条可拍剧情脚本。"
    "缺少的产品事实可以明确作为创作假设，但不要提问停摆，也不要把假设写成事实。"
)

BASE_TOOL_ALLOWLIST = (
    "web_search",
    "image_search",
    "ls",
    "read_file",
    "glob",
    "grep",
    "view_image",
    "ask_clarification",
)
EVIDENCE_TOOL_ALLOWLIST = (
    "ip_evidence_collect_douyin_benchmark_account",
    "ip_evidence_inspect_reference_videos",
)
METHOD_SKILLS = (
    "ip-strategy-director",
    "video-pattern-learning",
    "engineer-audience-response",
    "engineer-desire-behavior",
    "write-ip-episode",
    "write-scenes-dialogue",
    "coach-ip-screen-performance",
)

_SENSITIVE_KEY_FRAGMENTS = (
    "accesstoken",
    "refreshtoken",
    "apikey",
    "cookie",
    "password",
    "passwd",
    "secret",
    "authorization",
    "setcookie",
    "rawresponse",
    "signature",
    "sessionid",
    "csrftoken",
    "credential",
    "mstoken",
    "abogus",
)
_INLINE_SENSITIVE_VALUE = re.compile(
    r"(?i)(?P<key_quote>[\"']?)\b(?P<key>access[_-]?token|refresh[_-]?token|api[_-]?key|client[_-]?secret|password|passwd|secret|"
    r"authorization|cookies?|set[_-]?cookie|session[_-]?id|csrf[_-]?token|credential|signature|"
    r"raw[_-]?response|ms[_-]?token|a[_-]?bogus)\b(?P=key_quote)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;}\]]+)"
)
_INLINE_SENSITIVE_HEADER = re.compile(
    r"(?im)\b(authorization|cookie|set-cookie)(\s*:\s*)[^\r\n]+"
)
_RUNTIME_METADATA_KEYS = frozenset(
    {
        "agent_name",
        "available_skills",
        "assembled_tool_names",
        "indexed_skill_names",
        "is_plan_mode",
        "memory_enabled",
        "model_name",
        "reasoning_effort",
        "subagent_enabled",
        "thinking_enabled",
        "tool_allowlist",
        "tool_groups",
    }
)


@dataclass(frozen=True)
class M2Group:
    name: str
    agent_name: str
    evidence_enabled: bool
    methods_enabled: bool
    thinking_enabled: bool


M2_GROUPS = (
    M2Group(
        name="chat_no_thinking",
        agent_name="ip-agent",
        evidence_enabled=False,
        methods_enabled=False,
        thinking_enabled=False,
    ),
    M2Group(
        name="evidence_no_thinking",
        agent_name="ip-agent",
        evidence_enabled=True,
        methods_enabled=False,
        thinking_enabled=False,
    ),
    M2Group(
        name="methods_no_thinking",
        agent_name="ip-agent",
        evidence_enabled=True,
        methods_enabled=True,
        thinking_enabled=False,
    ),
    M2Group(
        name="methods_thinking",
        agent_name="ip-agent",
        evidence_enabled=True,
        methods_enabled=True,
        thinking_enabled=True,
    ),
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_stamp(value: datetime | None = None) -> str:
    return (value or _utc_now()).strftime("%Y%m%d-%H%M%S")


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"required file is missing: {path}")
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"configuration root must be an object: {path}")
    return value


def _write_private_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _write_private_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(value)
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    safe_value = _redact_sensitive(value)
    _write_private_text(
        path,
        json.dumps(safe_value, ensure_ascii=False, indent=2) + "\n",
    )


def _validate_evidence_test_state(root: Path) -> Path:
    state_dir = (root / TEST_STATE_RELATIVE).resolve()
    marker_path = state_dir / TEST_MARKER_NAME
    if not marker_path.is_file():
        raise RuntimeError(
            "M2 requires the prepared, marked evidence test space; run make ip-test-evidence-start first"
        )
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": TEST_MODE_SCHEMA_VERSION,
        "root": str(root.resolve()),
        "state_dir": str(state_dir),
        "profile": TEST_PROFILE_EVIDENCE,
    }
    for key, expected_value in expected.items():
        if marker.get(key) != expected_value:
            raise RuntimeError(
                f"M2 test-space marker mismatch for {key}: expected {expected_value!r}"
            )

    extensions_path = state_dir / TEST_EXTENSIONS_CONFIG_NAME
    extensions = json.loads(extensions_path.read_text(encoding="utf-8"))
    servers = extensions.get("mcpServers")
    if not isinstance(servers, dict) or list(servers) != [EVIDENCE_MCP_SERVER_NAME]:
        raise RuntimeError(
            "M2 requires the isolated extensions config with only the Evidence MCP server"
        )
    if extensions.get("middlewares") != [] or extensions.get("mcpInterceptors") != []:
        raise RuntimeError("M2 refuses extensions middleware or MCP interceptors")
    return state_dir


@contextmanager
def _exclusive_replay_lock(state_dir: Path):
    lock_path = state_dir / M2_LOCK_NAME
    lock_path.touch(mode=0o600, exist_ok=True)
    lock_path.chmod(0o600)
    with lock_path.open("r+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "another M2 replay is already using this isolated test space"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _verify_gateway_uses_test_state(client: httpx.Client, state_dir: Path) -> None:
    """Prove that ``base_url`` resolves agents from the marked test home.

    A unique, read-only probe Agent is created only in the isolated test owner.
    The compatibility endpoint must observe its nonce before any model run or
    customer thread is created.  A normal Gateway cannot see this directory and
    therefore fails closed.
    """

    nonce = uuid.uuid4().hex
    probe_name = f"m2-probe-{nonce[:16]}"
    probe_description = f"M2 isolated Gateway probe {nonce}"
    probe_dir = state_dir / "users" / "default" / "agents" / probe_name
    probe_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    config_path = probe_dir / "config.yaml"
    try:
        _write_private_text(
            config_path,
            yaml.safe_dump(
                {
                    "name": probe_name,
                    "description": probe_description,
                    "skills": [],
                    "tool_allowlist": [],
                    "memory_enabled": False,
                },
                allow_unicode=True,
                sort_keys=False,
            ),
        )
        response = client.get(f"/api/assistants/{probe_name}")
        response.raise_for_status()
        payload = response.json()
        if (
            not isinstance(payload, dict)
            or payload.get("assistant_id") != probe_name
            or payload.get("description") != probe_description
        ):
            raise RuntimeError(
                "Gateway Agent probe did not resolve from the marked M2 test space"
            )
    finally:
        config_path.unlink(missing_ok=True)
        probe_dir.rmdir()


def _validate_product_baseline(root: Path) -> tuple[dict[str, Any], str]:
    default_dir = root / "product" / "defaults" / "agents" / "ip-agent"
    config = _load_mapping(default_dir / "config.yaml")
    soul = (default_dir / "SOUL.md").read_text(encoding="utf-8")
    if config.get("skills") != []:
        raise RuntimeError(
            "M2 refuses to run because the product Chat baseline no longer has skills: []"
        )
    if config.get("memory_enabled") is not False:
        raise RuntimeError(
            "M2 refuses to run because the product Chat baseline no longer disables memory"
        )
    if tuple(config.get("tool_allowlist") or ()) != BASE_TOOL_ALLOWLIST:
        raise RuntimeError(
            "M2 refuses to run because the product Chat baseline tool allowlist has drifted"
        )
    return config, soul


def _validate_frozen_prompt_evidence_routes(state_dir: Path) -> None:
    app_config = _load_mapping(state_dir / "config.yaml")
    tool_search = app_config.get("tool_search")
    if not isinstance(tool_search, dict) or tool_search.get("enabled") is not True:
        raise RuntimeError(
            "M2 requires tool_search.enabled=true in the evidence test config"
        )
    raw_top_k = tool_search.get("auto_promote_top_k", 3)
    if isinstance(raw_top_k, bool):
        raise RuntimeError("M2 requires an integer tool_search.auto_promote_top_k")
    try:
        top_k = max(1, min(5, int(raw_top_k)))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "M2 requires an integer tool_search.auto_promote_top_k"
        ) from exc

    extensions = json.loads(
        (state_dir / TEST_EXTENSIONS_CONFIG_NAME).read_text(encoding="utf-8")
    )
    server = (extensions.get("mcpServers") or {}).get(EVIDENCE_MCP_SERVER_NAME)
    if not isinstance(server, dict) or server.get("enabled", True) is not True:
        raise RuntimeError("M2 requires the Evidence MCP server to be enabled")
    transport = server.get("type") or server.get("transport") or "stdio"
    if transport != "stdio":
        raise RuntimeError("M2 requires the Evidence MCP server to use stdio")
    tools = server.get("tools") if isinstance(server, dict) else None
    if not isinstance(tools, dict):
        raise RuntimeError("Evidence MCP routing metadata is missing")

    haystack = FROZEN_PROMPT.casefold()
    matched: list[tuple[int, str]] = []
    for tool_name, tool_config in tools.items():
        routing = tool_config.get("routing") if isinstance(tool_config, dict) else None
        if not isinstance(routing, dict) or routing.get("mode", "off") != "prefer":
            continue
        keywords = routing.get("keywords") if isinstance(routing, dict) else None
        if not isinstance(keywords, list) or not any(
            isinstance(keyword, str) and keyword.casefold() in haystack
            for keyword in keywords
        ):
            continue
        try:
            priority = int(routing.get("priority", 0))
        except (TypeError, ValueError):
            priority = 0
        matched.append((max(0, min(100, priority)), str(tool_name)))

    matched.sort(key=lambda item: (-item[0], item[1]))
    promoted = {name for _priority, name in matched[:top_k]}
    required = {
        "collect_douyin_benchmark_account",
        "inspect_reference_videos",
    }
    missing = sorted(required - promoted)
    if missing:
        raise RuntimeError(
            "frozen M2 prompt does not auto-promote required Evidence MCP tool(s): "
            + ", ".join(missing)
        )


def _validate_method_assets(root: Path) -> None:
    for skill_name in METHOD_SKILLS:
        skill_file = root / "skills" / "public" / skill_name / "SKILL.md"
        if not skill_file.is_file():
            raise FileNotFoundError(f"M2 method asset is missing: {skill_file}")


def _config_for_group(baseline: dict[str, Any], group: M2Group) -> dict[str, Any]:
    allowlist = list(BASE_TOOL_ALLOWLIST)
    if group.evidence_enabled:
        allowlist.extend(EVIDENCE_TOOL_ALLOWLIST)
    if group.methods_enabled:
        allowlist.append("describe_skill")
    return {
        "name": "ip-agent",
        "description": baseline.get("description", ""),
        "skills": list(METHOD_SKILLS) if group.methods_enabled else [],
        "tool_allowlist": allowlist,
        "memory_enabled": False,
    }


def prepare_m2_matrix(root: Path) -> dict[str, dict[str, Any]]:
    root = root.resolve()
    state_dir = _validate_evidence_test_state(root)
    _validate_frozen_prompt_evidence_routes(state_dir)
    baseline, _soul = _validate_product_baseline(root)
    _validate_method_assets(root)
    return {group.name: _config_for_group(baseline, group) for group in M2_GROUPS}


def prepare_comparison_model_config(root: Path, model_name: str) -> Path:
    root = root.resolve()
    if not MODEL_NAME_PATTERN.fullmatch(model_name):
        raise ValueError("comparison model name contains unsupported characters")
    state_dir = _validate_evidence_test_state(root)
    config_path = state_dir / "config.yaml"
    config = _load_mapping(config_path)
    models = config.get("models")
    if not isinstance(models, list) or not models:
        raise RuntimeError("the evidence test config has no model template")
    if any(
        isinstance(model, dict) and model.get("name") == model_name for model in models
    ):
        comparison = config
    else:
        template = next((model for model in models if isinstance(model, dict)), None)
        if template is None:
            raise RuntimeError("the evidence test config has no usable model template")
        comparison_model = dict(template)
        comparison_model.update(
            {
                "name": model_name,
                "model": model_name,
                "display_name": f"Volcengine comparison / {model_name}",
            }
        )
        comparison = dict(config)
        comparison["models"] = [*models, comparison_model]
    destination = state_dir / "config-m2-model.yaml"
    _write_private_text(
        destination, yaml.safe_dump(comparison, allow_unicode=True, sort_keys=False)
    )
    return destination


def _expected_evidence_config(baseline: dict[str, Any]) -> dict[str, Any]:
    return _config_for_group(baseline, M2_GROUPS[1])


def _iter_sse(lines: Iterable[str]) -> Iterable[tuple[str, Any]]:
    event_name = "message"
    data_lines: list[str] = []
    for line in lines:
        if line.startswith(":"):
            continue
        if not line:
            if data_lines:
                raw = "\n".join(data_lines)
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {"_invalid_json": raw[:500]}
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
            data = {"_invalid_json": raw[:500]}
        yield event_name, data


def _text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def _is_sensitive_key(key: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _redact_inline_sensitive_text(value: str) -> str:
    value = _INLINE_SENSITIVE_HEADER.sub(r"\1\2[redacted]", value)

    def replace_sensitive_value(match: re.Match[str]) -> str:
        key_quote = match.group("key_quote")
        raw_value = match.group("value")
        value_quote = (
            raw_value[0]
            if len(raw_value) >= 2
            and raw_value[0] in {'"', "'"}
            and raw_value[-1] == raw_value[0]
            else ""
        )
        redacted = f"{value_quote}[redacted]{value_quote}"
        return (
            f"{key_quote}{match.group('key')}{key_quote}"
            f"{match.group('separator')}{redacted}"
        )

    return _INLINE_SENSITIVE_VALUE.sub(replace_sensitive_value, value)


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            redacted[str(key)] = (
                "[redacted]" if _is_sensitive_key(key) else _redact_sensitive(child)
            )
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return _redact_inline_sensitive_text(value)
    return value


def _safe_tool_string(content: str) -> Any:
    if len(content) > 500_000:
        return {
            "truncated": True,
            "characters": len(content),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
    bounded = content
    try:
        decoded = json.loads(bounded)
    except json.JSONDecodeError:
        return _redact_inline_sensitive_text(bounded)
    return _safe_tool_content(decoded)


def _safe_tool_content(content: Any) -> Any:
    """Normalize tool payloads while redacting nested MCP text blocks.

    MCP tool results commonly arrive as ``[{"type": "text", "text":
    "{...json...}"}]``.  A key-only recursive walk leaves the JSON string
    untouched, so every string that parses as JSON is decoded and sanitized
    recursively before it is persisted in a replay artifact.
    """

    if isinstance(content, str):
        return _safe_tool_string(content)
    if isinstance(content, dict):
        safe: dict[str, Any] = {}
        for key, child in content.items():
            safe[str(key)] = (
                "[redacted]" if _is_sensitive_key(key) else _safe_tool_content(child)
            )
        return safe
    if isinstance(content, list):
        return [_safe_tool_content(item) for item in content]
    return content


def _normalize_state(values: dict[str, Any]) -> dict[str, Any]:
    messages = values.get("messages")
    if not isinstance(messages, list):
        messages = []
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    assistant_messages: list[str] = []
    skill_descriptions: list[str] = []
    skill_reads: list[str] = []

    for message in messages:
        if not isinstance(message, dict):
            continue
        message_type = message.get("type") or message.get("role")
        if message_type in {"ai", "assistant"}:
            calls = message.get("tool_calls")
            if isinstance(calls, list):
                for call in calls:
                    if not isinstance(call, dict):
                        continue
                    normalized_call = {
                        "name": call.get("name"),
                        "args": _redact_sensitive(call.get("args")),
                        "id": call.get("id"),
                    }
                    tool_calls.append(normalized_call)
                    name = normalized_call["name"]
                    args = normalized_call["args"]
                    if name == "describe_skill" and isinstance(args, dict):
                        described_name = args.get("name") or args.get("skill_name")
                        if isinstance(described_name, str):
                            skill_descriptions.append(described_name)
                    if name == "read_file" and isinstance(args, dict):
                        path = args.get("file_path") or args.get("path")
                        if isinstance(path, str):
                            for skill_name in METHOD_SKILLS:
                                if f"/{skill_name}/SKILL.md" in path:
                                    skill_reads.append(skill_name)
            additional_kwargs = message.get("additional_kwargs")
            hidden = (
                isinstance(additional_kwargs, dict)
                and additional_kwargs.get("hide_from_ui") is True
            )
            text = _text_content(message.get("content"))
            if text and not hidden:
                assistant_messages.append(_redact_inline_sensitive_text(text))
        elif message_type == "tool":
            tool_results.append(
                {
                    "name": message.get("name"),
                    "tool_call_id": message.get("tool_call_id"),
                    "status": message.get("status"),
                    "content": _safe_tool_content(message.get("content")),
                }
            )

    return {
        "final_answer": assistant_messages[-1] if assistant_messages else "",
        "assistant_messages": assistant_messages,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "tool_call_counts": dict(Counter(str(call.get("name")) for call in tool_calls)),
        "skill_descriptions": skill_descriptions,
        "skill_description_counts": dict(Counter(skill_descriptions)),
        "skill_reads": skill_reads,
        "skill_read_counts": dict(Counter(skill_reads)),
    }


def _run_id_from_location(location: str | None) -> str | None:
    if not location:
        return None
    parts = [part for part in location.split("/") if part]
    if len(parts) >= 2 and parts[-2] == "runs":
        return parts[-1]
    return None


def _select_run_record(records: Any, run_id: str | None) -> dict[str, Any]:
    if not isinstance(records, list):
        raise RuntimeError("Gateway returned a non-list run inventory")
    if run_id:
        for record in records:
            if isinstance(record, dict) and record.get("run_id") == run_id:
                return record
    if len(records) == 1 and isinstance(records[0], dict):
        return records[0]
    raise RuntimeError(f"Could not resolve run record {run_id!r}")


def _summarize_run_events(
    run_events: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(run_events, list):
        return {}, [], []
    runtime_metadata: dict[str, Any] = {}
    llm_calls: list[dict[str, Any]] = []
    model_tool_bindings: list[dict[str, Any]] = []
    for event in run_events:
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        if event.get("event_type") == "run.start":
            runtime_metadata = {
                key: _redact_sensitive(value)
                for key, value in metadata.items()
                if key in _RUNTIME_METADATA_KEYS
            }
        elif event.get("event_type") == "llm.ai.response":
            llm_calls.append(
                {
                    "call_index": metadata.get("llm_call_index"),
                    "caller": metadata.get("caller"),
                    "latency_ms": metadata.get("latency_ms"),
                    "usage": _redact_sensitive(metadata.get("usage")),
                }
            )
        elif event.get("event_type") == "llm.tools.bound":
            content = event.get("content")
            if isinstance(content, dict):
                model_tool_bindings.append(_redact_sensitive(content))
    return runtime_metadata, llm_calls, model_tool_bindings


def _runtime_validation(
    group: M2Group,
    runtime_metadata: dict[str, Any],
    llm_calls: list[dict[str, Any]],
    model_tool_bindings: list[dict[str, Any]],
    *,
    model_name: str | None,
) -> dict[str, Any]:
    expected_allowlist = list(BASE_TOOL_ALLOWLIST)
    if group.evidence_enabled:
        expected_allowlist.extend(EVIDENCE_TOOL_ALLOWLIST)
    if group.methods_enabled:
        expected_allowlist.append("describe_skill")
    expected_skills = sorted(METHOD_SKILLS) if group.methods_enabled else []
    expected = {
        "agent_name": group.agent_name,
        "available_skills": expected_skills,
        "indexed_skill_names": expected_skills,
        "tool_allowlist": expected_allowlist,
        "assembled_tool_names": sorted(expected_allowlist),
        "memory_enabled": False,
        "thinking_enabled": group.thinking_enabled,
        "is_plan_mode": False,
        "subagent_enabled": False,
        "model_name": model_name,
    }
    errors: list[str] = []
    for key in (
        "agent_name",
        "memory_enabled",
        "thinking_enabled",
        "is_plan_mode",
        "subagent_enabled",
    ):
        if runtime_metadata.get(key) != expected[key]:
            errors.append(f"{key} mismatch")
    for key in (
        "available_skills",
        "indexed_skill_names",
        "tool_allowlist",
        "assembled_tool_names",
    ):
        actual_value = runtime_metadata.get(key)
        if not isinstance(actual_value, list) or sorted(actual_value) != sorted(
            expected[key]
        ):
            errors.append(f"{key} mismatch")
    actual_model = runtime_metadata.get("model_name")
    if not isinstance(actual_model, str) or not actual_model:
        errors.append("model_name is missing")
    elif model_name is not None and actual_model != model_name:
        errors.append("model_name mismatch")
    if group.evidence_enabled:
        if not model_tool_bindings:
            errors.append("per-call model tool bindings are missing")
        call_indices = {
            call.get("call_index")
            for call in llm_calls
            if isinstance(call.get("call_index"), int)
        }
        binding_indices = {
            binding.get("call_index")
            for binding in model_tool_bindings
            if isinstance(binding.get("call_index"), int)
        }
        if call_indices != binding_indices:
            errors.append("per-call model tool binding coverage mismatch")
        required_tools = set(EVIDENCE_TOOL_ALLOWLIST)
        if group.methods_enabled:
            required_tools.add("describe_skill")
        for binding in model_tool_bindings:
            bound_names = binding.get("bound_tool_names")
            missing_tools = (
                sorted(required_tools - set(bound_names))
                if isinstance(bound_names, list)
                else sorted(required_tools)
            )
            if missing_tools:
                errors.append(
                    "required schemas were not bound on model call "
                    f"{binding.get('call_index')}: {', '.join(missing_tools)}"
                )
    return {
        "passed": not errors,
        "expected": expected,
        "actual": runtime_metadata,
        "errors": errors,
    }


def run_group(
    client: httpx.Client,
    group: M2Group,
    *,
    timeout_seconds: float,
    config_sha256: str,
    model_name: str | None,
) -> dict[str, Any]:
    thread_id = str(uuid.uuid4())
    created = client.post(
        "/api/threads",
        json={
            "thread_id": thread_id,
            "metadata": {
                "test_contract": M2_REPLAY_SCHEMA_VERSION,
                "m2_group": group.name,
            },
        },
    )
    created.raise_for_status()

    context = {
        "agent_name": group.agent_name,
        "mode": "thinking" if group.thinking_enabled else "flash",
        "thinking_enabled": group.thinking_enabled,
        "is_plan_mode": False,
        "subagent_enabled": False,
    }
    if model_name is not None:
        context["model_name"] = model_name
    body = {
        "assistant_id": "lead_agent",
        "input": {"messages": [{"role": "user", "content": FROZEN_PROMPT}]},
        "config": {"recursion_limit": M2_RECURSION_LIMIT},
        "context": context,
        "stream_mode": ["values"],
        "on_disconnect": "cancel",
    }
    latest_values: dict[str, Any] = {}
    event_counts: Counter[str] = Counter()
    errors: list[Any] = []
    started_at = _utc_now()
    with client.stream(
        "POST",
        f"/api/threads/{thread_id}/runs/stream",
        json=body,
        timeout=timeout_seconds,
    ) as response:
        response.raise_for_status()
        run_id = _run_id_from_location(response.headers.get("Content-Location"))
        for event_name, data in _iter_sse(response.iter_lines()):
            event_counts[event_name] += 1
            if event_name == "values" and isinstance(data, dict):
                latest_values = data
            elif event_name in {"error", "run_error"}:
                errors.append(_redact_sensitive(data))

    records_response = client.get(f"/api/threads/{thread_id}/runs")
    records_response.raise_for_status()
    record = _select_run_record(records_response.json(), run_id)
    state_response = client.get(f"/api/threads/{thread_id}/state")
    state_response.raise_for_status()
    checkpoint_values = state_response.json().get("values")
    if isinstance(checkpoint_values, dict):
        latest_values = checkpoint_values
    token_response = client.get(f"/api/threads/{thread_id}/token-usage")
    token_response.raise_for_status()
    events_response = client.get(
        f"/api/threads/{thread_id}/runs/{record.get('run_id')}/events"
    )
    events_response.raise_for_status()
    run_events = events_response.json()
    if not isinstance(run_events, list):
        run_events = []
    runtime_metadata, llm_calls, model_tool_bindings = _summarize_run_events(run_events)
    normalized = _normalize_state(latest_values)
    completed_at = _utc_now()
    return {
        "group": asdict(group),
        "requested_model": model_name,
        "agent_config_sha256": config_sha256,
        "thread_id": thread_id,
        "run_id": record.get("run_id"),
        "status": record.get("status"),
        "stop_reason": _redact_sensitive(record.get("stop_reason")),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "wall_seconds": round((completed_at - started_at).total_seconds(), 3),
        "recursion_limit": M2_RECURSION_LIMIT,
        "event_counts": dict(event_counts),
        "run_event_count": len(run_events),
        "runtime_metadata": runtime_metadata,
        "model_tool_bindings": model_tool_bindings,
        "runtime_validation": _runtime_validation(
            group,
            runtime_metadata,
            llm_calls,
            model_tool_bindings,
            model_name=model_name,
        ),
        "llm_calls": llm_calls,
        "errors": errors,
        "usage": {
            "input_tokens": record.get("total_input_tokens", 0),
            "output_tokens": record.get("total_output_tokens", 0),
            "total_tokens": record.get("total_tokens", 0),
            "llm_call_count": record.get("llm_call_count", 0),
            "lead_agent_tokens": record.get("lead_agent_tokens", 0),
            "subagent_tokens": record.get("subagent_tokens", 0),
            "middleware_tokens": record.get("middleware_tokens", 0),
            "by_model": token_response.json().get("by_model", {}),
        },
        **normalized,
    }


def _selected_groups(name: str) -> list[M2Group]:
    if name == "all":
        return list(M2_GROUPS)
    return [group for group in M2_GROUPS if group.name == name]


def _resolve_output_directory(state_dir: Path, output_dir: Path | None) -> Path:
    evaluation_root = (state_dir / "evaluations" / "m2").resolve()
    evaluation_root.mkdir(parents=True, exist_ok=True)
    destination = (
        output_dir.expanduser().resolve()
        if output_dir
        else evaluation_root / _utc_stamp()
    )
    if not destination.is_relative_to(evaluation_root):
        raise RuntimeError(
            f"M2 output must stay under the isolated evaluation root: {evaluation_root}"
        )
    existed = destination.exists()
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise RuntimeError(f"M2 output is not a directory: {destination}")
    if not existed:
        destination.chmod(0o700)
    return destination


def _run_replay_locked(
    root: Path,
    *,
    base_url: str,
    group_name: str,
    output_dir: Path | None,
    timeout_seconds: float,
    force: bool,
    model_name: str | None,
) -> Path:
    root = root.resolve()
    state_dir = _validate_evidence_test_state(root)
    baseline, product_soul = _validate_product_baseline(root)
    matrix = prepare_m2_matrix(root)
    agent_dir = state_dir / "users" / "default" / "agents" / "ip-agent"
    agent_config_path = agent_dir / "config.yaml"
    agent_soul_path = agent_dir / "SOUL.md"
    if agent_soul_path.read_text(encoding="utf-8") != product_soul:
        raise RuntimeError(
            "M2 refuses to run because the test IP Agent SOUL differs from the frozen product baseline"
        )
    original_config_bytes = agent_config_path.read_bytes()
    original_config = _load_mapping(agent_config_path)
    if original_config != _expected_evidence_config(baseline):
        raise RuntimeError(
            "M2 requires the ordinary evidence test config before it starts; run make ip-test-evidence-start without reset"
        )
    selected = _selected_groups(group_name)
    if not selected:
        raise ValueError(f"unknown M2 group: {group_name}")

    destination = _resolve_output_directory(state_dir, output_dir)
    result_path = destination / "results.json"
    if result_path.exists():
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != M2_REPLAY_SCHEMA_VERSION:
            raise RuntimeError(f"refusing incompatible M2 replay result: {result_path}")
    else:
        payload = {
            "schema_version": M2_REPLAY_SCHEMA_VERSION,
            "created_at": _utc_now().isoformat(),
            "base_url": base_url,
            "requested_model": model_name,
            "recursion_limit": M2_RECURSION_LIMIT,
            "frozen_prompt": FROZEN_PROMPT,
            "frozen_user_facts": [
                "产品是黄金礼品",
                "重点是礼品，不是黄金本身",
                "目标是长期影响力与成交",
            ],
            "groups": [],
        }

    completed_names = {
        item.get("group", {}).get("name")
        for item in payload.get("groups", [])
        if (
            isinstance(item, dict)
            and isinstance(item.get("group"), dict)
            and item.get("status") == "success"
            and isinstance(item.get("runtime_validation"), dict)
            and item["runtime_validation"].get("passed") is True
        )
    }
    timeout = httpx.Timeout(timeout_seconds, connect=15.0)
    try:
        with httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Accept": "text/event-stream"},
        ) as client:
            _verify_gateway_uses_test_state(client, state_dir)
            models = client.get("/api/models")
            models.raise_for_status()
            available_models = models.json().get("models", [])
            payload["available_models"] = _redact_sensitive(available_models)
            available_names = {
                item.get("name")
                for item in available_models
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
            if model_name is not None and model_name not in available_names:
                raise RuntimeError(
                    f"comparison model is not configured in the running Gateway: {model_name}"
                )
            existing_requested_model = payload.get("requested_model")
            if existing_requested_model != model_name:
                raise RuntimeError(
                    f"result directory belongs to model {existing_requested_model!r}, not {model_name!r}"
                )
            for group in selected:
                if group.name in completed_names and not force:
                    print(f"[M2] skip completed group: {group.name}", flush=True)
                    continue
                if force:
                    payload["groups"] = [
                        item
                        for item in payload.get("groups", [])
                        if not (
                            isinstance(item, dict)
                            and item.get("group", {}).get("name") == group.name
                        )
                    ]
                config_text = yaml.safe_dump(
                    matrix[group.name], allow_unicode=True, sort_keys=False
                )
                config_bytes = config_text.encode("utf-8")
                config_sha256 = hashlib.sha256(config_bytes).hexdigest()
                _write_private_bytes(agent_config_path, config_bytes)
                print(f"[M2] start group: {group.name}", flush=True)
                result: dict[str, Any] | None = None
                try:
                    result = run_group(
                        client,
                        group,
                        timeout_seconds=timeout_seconds,
                        config_sha256=config_sha256,
                        model_name=model_name,
                    )
                    if agent_config_path.read_bytes() != config_bytes:
                        raise RuntimeError("test Agent config changed during an M2 run")
                    runtime_model = result.get("runtime_metadata", {}).get("model_name")
                    previous_runtime_models = {
                        item.get("runtime_metadata", {}).get("model_name")
                        for item in payload.get("groups", [])
                        if isinstance(item, dict)
                        and item.get("runtime_validation", {}).get("passed") is True
                    }
                    previous_runtime_models.discard(None)
                    if (
                        model_name is None
                        and previous_runtime_models
                        and runtime_model not in previous_runtime_models
                    ):
                        validation = result["runtime_validation"]
                        validation["passed"] = False
                        validation["errors"].append(
                            "model_name drifted between M2 groups"
                        )
                    gateway_status = result.get("status")
                    if gateway_status != "success":
                        raise RuntimeError(
                            f"Gateway run did not succeed: {gateway_status!r}"
                        )
                    if result.get("errors"):
                        raise RuntimeError(
                            "Gateway run emitted one or more error events"
                        )
                    if not str(result.get("final_answer") or "").strip():
                        raise RuntimeError(
                            "Gateway run completed without a visible final answer"
                        )
                    if result.get("runtime_validation", {}).get("passed") is not True:
                        raise RuntimeError(
                            "runtime capability validation failed: "
                            + ", ".join(
                                result.get("runtime_validation", {}).get("errors", [])
                            )
                        )
                except Exception as exc:
                    failure = result or {
                        "group": asdict(group),
                        "agent_config_sha256": config_sha256,
                        "completed_at": _utc_now().isoformat(),
                    }
                    failure["gateway_status"] = failure.get("status")
                    failure["status"] = "harness_error"
                    failure["error_type"] = type(exc).__name__
                    failure["error"] = _redact_inline_sensitive_text(str(exc))
                    payload.setdefault("groups", []).append(failure)
                    payload["updated_at"] = _utc_now().isoformat()
                    _write_private_json(result_path, payload)
                    raise
                payload.setdefault("groups", []).append(result)
                payload["updated_at"] = _utc_now().isoformat()
                _write_private_json(result_path, payload)
                print(
                    f"[M2] complete group: {group.name}; status={result['status']}; "
                    f"calls={result['usage']['llm_call_count']}; tokens={result['usage']['total_tokens']}; "
                    f"tools={len(result['tool_calls'])}",
                    flush=True,
                )
    finally:
        _write_private_bytes(agent_config_path, original_config_bytes)
    print(f"[M2] results: {result_path}", flush=True)
    return result_path


def run_replay(
    root: Path,
    *,
    base_url: str,
    group_name: str,
    output_dir: Path | None,
    timeout_seconds: float,
    force: bool,
    model_name: str | None,
) -> Path:
    resolved_root = root.resolve()
    state_dir = _validate_evidence_test_state(resolved_root)
    with _exclusive_replay_lock(state_dir):
        return _run_replay_locked(
            resolved_root,
            base_url=base_url,
            group_name=group_name,
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
            force=force,
            model_name=model_name,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "prepare-model", "run"))
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument(
        "--group",
        choices=("all", *(group.name for group in M2_GROUPS)),
        default="all",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model-name")
    return parser


def main() -> None:
    args = _parser().parse_args()
    root = args.root.resolve()
    if args.command == "prepare":
        matrix = prepare_m2_matrix(root)
        print(json.dumps(matrix, ensure_ascii=False, indent=2))
        return
    if args.command == "prepare-model":
        if not args.model_name:
            raise ValueError("prepare-model requires --model-name")
        print(prepare_comparison_model_config(root, args.model_name))
        return
    run_replay(
        root,
        base_url=args.base_url,
        group_name=args.group,
        output_dir=args.output_dir,
        timeout_seconds=args.timeout_seconds,
        force=args.force,
        model_name=args.model_name,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"M2 replay failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
