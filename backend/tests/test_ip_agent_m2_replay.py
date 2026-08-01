from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml


def _load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "ip_agent_m2_replay.py"
    spec = importlib.util.spec_from_file_location("ip_agent_m2_replay", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


m2 = _load_module()


def _write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _repo_fixture(tmp_path: Path) -> tuple[Path, Path, bytes]:
    root = (tmp_path / "repo").resolve()
    product_agent = root / "product/defaults/agents/ip-agent"
    product_agent.mkdir(parents=True)
    baseline = {
        "name": "ip-agent",
        "description": "clean test agent",
        "skills": [],
        "tool_allowlist": list(m2.BASE_TOOL_ALLOWLIST),
        "memory_enabled": False,
    }
    _write_yaml(product_agent / "config.yaml", baseline)
    (product_agent / "SOUL.md").write_text("clean soul\n", encoding="utf-8")
    for skill_name in m2.METHOD_SKILLS:
        skill = root / "skills/public" / skill_name / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(f"---\nname: {skill_name}\n---\n", encoding="utf-8")

    state = root / m2.TEST_STATE_RELATIVE
    state.mkdir(parents=True)
    marker = {
        "schema_version": m2.TEST_MODE_SCHEMA_VERSION,
        "root": str(root),
        "state_dir": str(state),
        "profile": m2.TEST_PROFILE_EVIDENCE,
    }
    (state / m2.TEST_MARKER_NAME).write_text(json.dumps(marker), encoding="utf-8")
    _write_yaml(
        state / "config.yaml",
        {
            "tool_search": {
                "enabled": True,
                "auto_promote_top_k": 3,
            }
        },
    )
    (state / m2.TEST_EXTENSIONS_CONFIG_NAME).write_text(
        json.dumps(
            {
                "middlewares": [],
                "mcpInterceptors": [],
                "mcpServers": {
                    m2.EVIDENCE_MCP_SERVER_NAME: {
                        "enabled": True,
                        "type": "stdio",
                        "tools": {
                            "collect_douyin_benchmark_account": {
                                "routing": {
                                    "mode": "prefer",
                                    "priority": 100,
                                    "keywords": ["对标账号"],
                                }
                            },
                            "inspect_reference_videos": {
                                "routing": {
                                    "mode": "prefer",
                                    "priority": 90,
                                    "keywords": ["对标账号"],
                                }
                            },
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    agent = state / "users/default/agents/ip-agent"
    agent.mkdir(parents=True)
    evidence_config = m2._expected_evidence_config(baseline)
    _write_yaml(agent / "config.yaml", evidence_config)
    (agent / "SOUL.md").write_text("clean soul\n", encoding="utf-8")
    original = (agent / "config.yaml").read_bytes()
    return root, agent / "config.yaml", original


def test_matrix_uses_one_agent_and_changes_only_evidence_methods_and_thinking(tmp_path: Path):
    root, _config_path, _original = _repo_fixture(tmp_path)

    matrix = m2.prepare_m2_matrix(root)

    assert list(matrix) == [group.name for group in m2.M2_GROUPS]
    assert {config["name"] for config in matrix.values()} == {"ip-agent"}
    assert matrix["chat_no_thinking"]["tool_allowlist"] == list(m2.BASE_TOOL_ALLOWLIST)
    assert matrix["chat_no_thinking"]["skills"] == []
    assert matrix["evidence_no_thinking"]["tool_allowlist"] == [
        *m2.BASE_TOOL_ALLOWLIST,
        *m2.EVIDENCE_TOOL_ALLOWLIST,
    ]
    assert matrix["evidence_no_thinking"]["skills"] == []
    assert matrix["methods_no_thinking"]["tool_allowlist"][-1] == "describe_skill"
    assert matrix["methods_no_thinking"]["skills"] == list(m2.METHOD_SKILLS)
    assert matrix["methods_thinking"] == matrix["methods_no_thinking"]


def test_matrix_fails_before_provider_use_when_a_required_evidence_route_is_unreachable(tmp_path: Path):
    root, _config_path, _original = _repo_fixture(tmp_path)
    extensions_path = root / m2.TEST_STATE_RELATIVE / m2.TEST_EXTENSIONS_CONFIG_NAME
    extensions = json.loads(extensions_path.read_text(encoding="utf-8"))
    extensions["mcpServers"][m2.EVIDENCE_MCP_SERVER_NAME]["tools"]["inspect_reference_videos"]["routing"]["keywords"] = ["不会命中"]
    extensions_path.write_text(json.dumps(extensions), encoding="utf-8")

    with pytest.raises(RuntimeError, match="inspect_reference_videos"):
        m2.prepare_m2_matrix(root)


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("tool_search_disabled", "tool_search.enabled"),
        ("top_k_too_small", "inspect_reference_videos"),
        ("server_disabled", "server to be enabled"),
        ("wrong_transport", "use stdio"),
        ("routing_not_preferred", "inspect_reference_videos"),
    ],
)
def test_matrix_fails_closed_when_evidence_auto_promotion_is_not_executable(
    tmp_path: Path,
    case: str,
    expected_error: str,
):
    root, _config_path, _original = _repo_fixture(tmp_path)
    state = root / m2.TEST_STATE_RELATIVE
    config_path = state / "config.yaml"
    extensions_path = state / m2.TEST_EXTENSIONS_CONFIG_NAME
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    extensions = json.loads(extensions_path.read_text(encoding="utf-8"))
    server = extensions["mcpServers"][m2.EVIDENCE_MCP_SERVER_NAME]

    if case == "tool_search_disabled":
        config["tool_search"]["enabled"] = False
    elif case == "top_k_too_small":
        config["tool_search"]["auto_promote_top_k"] = 1
    elif case == "server_disabled":
        server["enabled"] = False
    elif case == "wrong_transport":
        server["type"] = "http"
    elif case == "routing_not_preferred":
        server["tools"]["inspect_reference_videos"]["routing"]["mode"] = "off"
    else:  # pragma: no cover - guarded by the fixed parametrization above
        raise AssertionError(case)

    _write_yaml(config_path, config)
    extensions_path.write_text(json.dumps(extensions), encoding="utf-8")

    with pytest.raises(RuntimeError, match=expected_error):
        m2.prepare_m2_matrix(root)


class _Response:
    def __init__(self, payload, *, status_error: Exception | None = None):
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self) -> None:
        if self._status_error is not None:
            raise self._status_error

    def json(self):
        return self._payload


class _Client:
    def __init__(self, state_dir: Path):
        self._state_dir = state_dir

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def get(self, path: str) -> _Response:
        if path.startswith("/api/assistants/m2-probe-"):
            name = path.rsplit("/", 1)[-1]
            config_path = self._state_dir / "users/default/agents" / name / "config.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            return _Response(
                {
                    "assistant_id": name,
                    "description": config["description"],
                }
            )
        assert path == "/api/models"
        return _Response({"models": [{"name": "test-model", "supports_thinking": True}]})


def _result(group, config_sha256: str) -> dict:
    return {
        "group": m2.asdict(group),
        "agent_config_sha256": config_sha256,
        "status": "success",
        "runtime_validation": {"passed": True, "errors": []},
        "usage": {"llm_call_count": 1, "total_tokens": 10},
        "tool_calls": [],
        "final_answer": "ok",
    }


def test_runner_atomically_switches_one_agent_and_restores_the_evidence_config(tmp_path: Path, monkeypatch):
    root, config_path, original = _repo_fixture(tmp_path)
    observed: list[tuple[str, dict]] = []

    def fake_run_group(_client, group, *, timeout_seconds, config_sha256, model_name):
        assert timeout_seconds == 12
        assert model_name is None
        observed.append((group.name, yaml.safe_load(config_path.read_text(encoding="utf-8"))))
        return _result(group, config_sha256)

    state_dir = root / m2.TEST_STATE_RELATIVE
    monkeypatch.setattr(m2.httpx, "Client", lambda *args, **kwargs: _Client(state_dir))
    monkeypatch.setattr(m2, "run_group", fake_run_group)
    output = state_dir / "evaluations/m2/test-output"

    result_path = m2.run_replay(
        root,
        base_url="http://gateway.test",
        group_name="all",
        output_dir=output,
        timeout_seconds=12,
        force=False,
        model_name=None,
    )

    assert [name for name, _config in observed] == [group.name for group in m2.M2_GROUPS]
    assert observed[0][1]["skills"] == []
    assert observed[0][1]["tool_allowlist"] == list(m2.BASE_TOOL_ALLOWLIST)
    assert observed[1][1]["tool_allowlist"][-2:] == list(m2.EVIDENCE_TOOL_ALLOWLIST)
    assert observed[2][1]["skills"] == list(m2.METHOD_SKILLS)
    assert observed[3][1] == observed[2][1]
    assert config_path.read_bytes() == original
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["frozen_prompt"] == m2.FROZEN_PROMPT
    assert payload["recursion_limit"] == m2.M2_RECURSION_LIMIT == 100
    assert len(payload["groups"]) == 4


def test_runner_restores_the_evidence_config_after_failure(tmp_path: Path, monkeypatch):
    root, config_path, original = _repo_fixture(tmp_path)

    def fail_run_group(*_args, **_kwargs):
        raise RuntimeError("provider failed")

    state_dir = root / m2.TEST_STATE_RELATIVE
    monkeypatch.setattr(m2.httpx, "Client", lambda *args, **kwargs: _Client(state_dir))
    monkeypatch.setattr(m2, "run_group", fail_run_group)

    with pytest.raises(RuntimeError, match="provider failed"):
        m2.run_replay(
            root,
            base_url="http://gateway.test",
            group_name="chat_no_thinking",
            output_dir=state_dir / "evaluations/m2/failed-output",
            timeout_seconds=12,
            force=False,
            model_name=None,
        )

    assert config_path.read_bytes() == original


@pytest.mark.parametrize(
    ("gateway_status", "errors", "expected_error"),
    [
        ("error", [], "Gateway run did not succeed"),
        ("cancelled", [], "Gateway run did not succeed"),
        ("success", [{"message": "cookie=sentinel-secret"}], "error events"),
    ],
)
def test_runner_fails_closed_for_unsuccessful_or_error_bearing_gateway_runs(
    tmp_path: Path,
    monkeypatch,
    gateway_status: str,
    errors: list[dict],
    expected_error: str,
):
    root, config_path, original = _repo_fixture(tmp_path)

    def fake_run_group(_client, group, *, timeout_seconds, config_sha256, model_name):
        result = _result(group, config_sha256)
        result["status"] = gateway_status
        result["errors"] = errors
        return result

    state_dir = root / m2.TEST_STATE_RELATIVE
    monkeypatch.setattr(m2.httpx, "Client", lambda *args, **kwargs: _Client(state_dir))
    monkeypatch.setattr(m2, "run_group", fake_run_group)
    output = state_dir / "evaluations/m2" / f"gateway-{gateway_status}-{len(errors)}"

    with pytest.raises(RuntimeError, match=expected_error):
        m2.run_replay(
            root,
            base_url="http://gateway.test",
            group_name="chat_no_thinking",
            output_dir=output,
            timeout_seconds=12,
            force=False,
            model_name=None,
        )

    assert config_path.read_bytes() == original
    serialized = (output / "results.json").read_text(encoding="utf-8")
    assert "sentinel-secret" not in serialized
    failure = json.loads(serialized)["groups"][0]
    assert failure["status"] == "harness_error"
    assert failure["gateway_status"] == gateway_status


def test_sse_and_state_normalization_capture_tools_skills_and_visible_answer():
    events = list(
        m2._iter_sse(
            [
                "event: values",
                'data: {"messages": []}',
                "",
                "event: end",
                "data: null",
                "",
            ]
        )
    )
    assert events == [("values", {"messages": []}), ("end", None)]

    state = {
        "messages": [
            {
                "type": "ai",
                "content": "",
                "tool_calls": [
                    {"name": "describe_skill", "args": {"name": "write-ip-episode"}, "id": "call-1"},
                    {
                        "name": "read_file",
                        "args": {"file_path": "/mnt/skills/public/write-ip-episode/SKILL.md"},
                        "id": "call-2",
                    },
                ],
            },
            {
                "type": "tool",
                "name": "example",
                "tool_call_id": "call-1",
                "status": "success",
                "content": '{"contract":"evidence-v1","access_token":"must-not-survive"}',
            },
            {"type": "ai", "content": "最终方案", "tool_calls": []},
        ]
    }

    normalized = m2._normalize_state(state)

    assert normalized["final_answer"] == "最终方案"
    assert normalized["tool_call_counts"] == {"describe_skill": 1, "read_file": 1}
    assert normalized["skill_description_counts"] == {"write-ip-episode": 1}
    assert normalized["skill_read_counts"] == {"write-ip-episode": 1}
    assert normalized["tool_results"][0]["content"]["access_token"] == "[redacted]"


def test_mcp_text_blocks_and_common_credential_shapes_are_redacted():
    content = [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "accessToken": "sentinel-1",
                    "api_key": "sentinel-2",
                    "cookies": ["sentinel-3"],
                    "session_id": "sentinel-4",
                    "csrf_token": "sentinel-5",
                    "credential": "sentinel-6",
                    "safe": "keep-me",
                }
            ),
        },
        {"type": "text", "text": "Authorization: Bearer sentinel-7\nvisible"},
        {
            "type": "text",
            "text": ("cookie=sentinel-8 session_id=sentinel-9 credential=sentinel-10 Authorization=sentinel-11 signature=sentinel-12"),
        },
        {"type": "text", "text": '{"access_token":"sentinel-13"}'},
        {"type": "text", "text": 'payload={"cookie":"sentinel-14"}'},
    ]

    safe = m2._safe_tool_content(content)
    serialized = json.dumps(safe)

    assert "sentinel" not in serialized
    assert safe[0]["text"]["safe"] == "keep-me"
    assert safe[1]["text"].endswith("\nvisible")


def test_private_artifact_writer_redacts_sensitive_embedded_json(tmp_path: Path):
    destination = tmp_path / "artifact.json"
    m2._write_private_json(
        destination,
        {
            "assistant": '{"access_token":"sentinel-json"}',
            "error": 'payload={"cookie":"sentinel-cookie"}',
            "plain": "keep-me",
        },
    )

    serialized = destination.read_text(encoding="utf-8")
    assert "sentinel" not in serialized
    assert "keep-me" in serialized


def test_gateway_probe_proves_the_server_reads_the_marked_test_owner(tmp_path: Path):
    root, _config_path, _original = _repo_fixture(tmp_path)
    state_dir = root / m2.TEST_STATE_RELATIVE
    client = _Client(state_dir)

    m2._verify_gateway_uses_test_state(client, state_dir)

    assert not list((state_dir / "users/default/agents").glob("m2-probe-*"))


def test_replay_lock_rejects_a_second_writer(tmp_path: Path):
    root, _config_path, _original = _repo_fixture(tmp_path)
    state_dir = root / m2.TEST_STATE_RELATIVE

    with m2._exclusive_replay_lock(state_dir):
        with pytest.raises(RuntimeError, match="another M2 replay"):
            with m2._exclusive_replay_lock(state_dir):
                pass


def test_runtime_events_prove_the_effective_capability_surface():
    group = m2.M2_GROUPS[2]
    expected_allowlist = [*m2.BASE_TOOL_ALLOWLIST, *m2.EVIDENCE_TOOL_ALLOWLIST, "describe_skill"]
    events = [
        {
            "event_type": "run.start",
            "metadata": {
                "agent_name": "ip-agent",
                "available_skills": list(m2.METHOD_SKILLS),
                "indexed_skill_names": list(m2.METHOD_SKILLS),
                "tool_allowlist": expected_allowlist,
                "assembled_tool_names": expected_allowlist,
                "memory_enabled": False,
                "thinking_enabled": False,
                "is_plan_mode": False,
                "subagent_enabled": False,
                "model_name": "test-model",
                "authorization": "must-not-survive",
            },
        },
        {
            "event_type": "llm.ai.response",
            "metadata": {
                "llm_call_index": 1,
                "caller": "lead_agent",
                "latency_ms": 123,
                "usage": {"total_tokens": 456},
            },
        },
        {
            "event_type": "llm.tools.bound",
            "content": {
                "call_index": 1,
                "bound_tool_names": expected_allowlist,
                "deferred_tool_names": list(m2.EVIDENCE_TOOL_ALLOWLIST),
                "promoted_tool_names": list(m2.EVIDENCE_TOOL_ALLOWLIST),
                "hidden_tool_names": [],
                "catalog_hash": "catalog",
            },
        },
    ]

    runtime, calls, bindings = m2._summarize_run_events(events)
    validation = m2._runtime_validation(
        group,
        runtime,
        calls,
        bindings,
        model_name="test-model",
    )

    assert validation["passed"] is True
    assert calls == [
        {
            "call_index": 1,
            "caller": "lead_agent",
            "latency_ms": 123,
            "usage": {"total_tokens": 456},
        }
    ]
    assert "authorization" not in runtime
    assert bindings[0]["promoted_tool_names"] == list(m2.EVIDENCE_TOOL_ALLOWLIST)

    runtime["indexed_skill_names"] = []
    bindings[0]["bound_tool_names"] = list(m2.EVIDENCE_TOOL_ALLOWLIST)
    invalid = m2._runtime_validation(
        group,
        runtime,
        calls,
        bindings,
        model_name="test-model",
    )
    assert invalid["passed"] is False
    assert "indexed_skill_names mismatch" in invalid["errors"]
    assert any("required schemas were not bound on model call 1: describe_skill" in error for error in invalid["errors"])

    bindings.clear()
    missing_binding = m2._runtime_validation(
        group,
        runtime,
        calls,
        bindings,
        model_name="test-model",
    )
    assert "per-call model tool binding coverage mismatch" in missing_binding["errors"]


def test_comparison_model_config_clones_the_isolated_provider_without_touching_normal_config(tmp_path: Path):
    root, _config_path, _original = _repo_fixture(tmp_path)
    test_config = root / m2.TEST_STATE_RELATIVE / "config.yaml"
    test_config.write_text(
        yaml.safe_dump(
            {
                "models": [
                    {
                        "name": "model-a",
                        "model": "model-a",
                        "use": "provider:ChatModel",
                        "api_key": "$PROVIDER_API_KEY",
                        "supports_thinking": True,
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    original = test_config.read_bytes()

    destination = m2.prepare_comparison_model_config(root, "model-b")

    prepared = yaml.safe_load(destination.read_text(encoding="utf-8"))
    assert [item["name"] for item in prepared["models"]] == ["model-a", "model-b"]
    assert prepared["models"][1]["model"] == "model-b"
    assert prepared["models"][1]["api_key"] == "$PROVIDER_API_KEY"
    assert test_config.read_bytes() == original
