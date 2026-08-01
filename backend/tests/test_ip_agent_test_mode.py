from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml


def _load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "ip_agent_test_mode.py"
    spec = importlib.util.spec_from_file_location("ip_agent_test_mode", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


test_mode = _load_module()


def _repo_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "product/defaults/agents/ip-agent").mkdir(parents=True)
    (root / "product/defaults/USER.md").write_text("default user\n", encoding="utf-8")
    (root / "product/defaults/agents/ip-agent/config.yaml").write_text("name: ip-agent\n", encoding="utf-8")
    (root / "product/defaults/agents/ip-agent/SOUL.md").write_text("test soul\n", encoding="utf-8")
    (root / "extensions_config.example.json").write_text('{"mcpServers": {}, "skills": {}}\n', encoding="utf-8")
    (root / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "database": {
                    "backend": "postgres",
                    "postgres_url": "$DATABASE_URL",
                },
                "scheduler": {"enabled": True},
                "channel_connections": {
                    "enabled": True,
                    "slack": {"enabled": True},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return root


def test_prepare_uses_an_isolated_database_and_product_defaults(tmp_path: Path):
    root = _repo_fixture(tmp_path)
    paths = test_mode.prepare_test_mode(
        root,
        now=datetime(2026, 7, 31, 5, 0, tzinfo=UTC),
    )

    config = yaml.safe_load(paths.config.read_text(encoding="utf-8"))
    assert config["database"] == {
        "backend": "sqlite",
        "postgres_url": "",
        "sqlite_dir": str(paths.database_dir),
    }
    assert config["scheduler"]["enabled"] is False
    assert config["channel_connections"]["enabled"] is False
    assert config["channel_connections"]["slack"]["enabled"] is False
    assert (paths.state_dir / "USER.md").read_text(encoding="utf-8") == "default user\n"
    assert (paths.state_dir / "users/default/agents/ip-agent/SOUL.md").read_text(encoding="utf-8") == "test soul\n"
    marker = json.loads(paths.marker.read_text(encoding="utf-8"))
    assert marker["schema_version"] == test_mode.TEST_MODE_SCHEMA_VERSION
    assert marker["state_dir"] == str(paths.state_dir)


def test_prepare_refreshes_product_files_without_erasing_test_memory(tmp_path: Path):
    root = _repo_fixture(tmp_path)
    paths = test_mode.prepare_test_mode(root)
    memory = paths.state_dir / "users/default/agents/ip-agent/memory.json"
    memory.write_text('{"facts":["test"]}\n', encoding="utf-8")
    (root / "product/defaults/agents/ip-agent/SOUL.md").write_text("new soul\n", encoding="utf-8")

    test_mode.prepare_test_mode(root)

    assert memory.read_text(encoding="utf-8") == '{"facts":["test"]}\n'
    assert (paths.state_dir / "users/default/agents/ip-agent/SOUL.md").read_text(encoding="utf-8") == "new soul\n"


def test_reset_rotates_only_marked_test_state_and_creates_fresh_state(tmp_path: Path):
    root = _repo_fixture(tmp_path)
    paths = test_mode.prepare_test_mode(root)
    database = paths.database_dir / "deerflow.db"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"old test database")
    now = datetime(2026, 7, 31, 5, 1, 2, tzinfo=UTC)

    fresh, snapshot = test_mode.reset_test_mode(
        root,
        now=now,
        stop_running_services=False,
    )

    assert snapshot == fresh.snapshots_dir / "20260731-050102"
    assert (snapshot / "data/deerflow.db").read_bytes() == b"old test database"
    assert not (fresh.database_dir / "deerflow.db").exists()
    assert fresh.marker.is_file()
    assert not (root / "backend/.deer-flow").exists()


def test_reset_refuses_an_unmarked_or_tampered_directory(tmp_path: Path):
    root = _repo_fixture(tmp_path)
    paths = test_mode.resolve_test_mode_paths(root)
    paths.state_dir.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="unmarked"):
        test_mode.reset_test_mode(root, stop_running_services=False)

    paths.marker.write_text(
        json.dumps(
            {
                "schema_version": test_mode.TEST_MODE_SCHEMA_VERSION,
                "root": str(root.resolve()),
                "state_dir": str(root / "somewhere-else"),
                "database_dir": str(paths.database_dir),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="state_dir"):
        test_mode.reset_test_mode(root, stop_running_services=False)


def test_environment_marks_frontend_and_backend_as_test_mode(tmp_path: Path):
    root = _repo_fixture(tmp_path)
    paths = test_mode.prepare_test_mode(root)

    environment = test_mode.test_mode_environment(paths)

    assert environment["DEER_FLOW_HOME"] == str(paths.state_dir)
    assert environment["DEER_FLOW_CONFIG_PATH"] == str(paths.config)
    assert environment["DEER_FLOW_EXTENSIONS_CONFIG_PATH"] == str(paths.extensions_config)
    assert environment["DEER_FLOW_PROJECT_ROOT"] == str(root.resolve())
    assert environment["DEER_FLOW_AUTH_DISABLED"] == "1"
    assert environment["IP_AGENT_TEST_MODE"] == "1"
    assert environment["NEXT_PUBLIC_IP_AGENT_TEST_MODE"] == "1"
    assert "uv" in environment["DEER_FLOW_MCP_STDIO_COMMAND_ALLOWLIST"]


def test_evidence_profile_adds_only_the_two_mcp_tools_to_the_clean_agent(tmp_path: Path):
    root = _repo_fixture(tmp_path)
    (root / "extensions_config.example.json").write_text(
        json.dumps(
            {
                "middlewares": ["legacy.middleware"],
                "mcpInterceptors": ["legacy.interceptor"],
                "mcpServers": {"legacy": {"enabled": False}},
                "skills": {"legacy": {"enabled": False}},
            }
        ),
        encoding="utf-8",
    )
    default_config = root / "product/defaults/agents/ip-agent/config.yaml"
    default_config.write_text(
        yaml.safe_dump(
            {
                "name": "ip-agent",
                "skills": [],
                "memory_enabled": False,
                "tool_allowlist": ["web_search", "read_file"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    paths = test_mode.prepare_test_mode(root, profile=test_mode.TEST_PROFILE_EVIDENCE)

    installed = yaml.safe_load((paths.state_dir / "users/default/agents/ip-agent/config.yaml").read_text(encoding="utf-8"))
    assert installed["skills"] == []
    assert installed["memory_enabled"] is False
    assert installed["tool_allowlist"] == [
        "web_search",
        "read_file",
        "ip_evidence_collect_douyin_benchmark_account",
        "ip_evidence_inspect_reference_videos",
    ]
    extensions = json.loads(paths.extensions_config.read_text(encoding="utf-8"))
    assert extensions["middlewares"] == []
    assert extensions["mcpInterceptors"] == []
    assert list(extensions["mcpServers"]) == [test_mode.EVIDENCE_MCP_SERVER_NAME]
    assert extensions["skills"] == {}
    server = extensions["mcpServers"][test_mode.EVIDENCE_MCP_SERVER_NAME]
    assert server["command"] == "uv"
    assert server["env"]["IP_AGENT_EVIDENCE_BROWSER_PROFILE_DIR"] == str(paths.evidence_browser_profile_dir)
    assert server["tools"]["collect_douyin_benchmark_account"]["routing"] == {
        "mode": "prefer",
        "priority": 100,
        "keywords": ["抖音主页", "抖音账号", "对标账号", "profile URL", "benchmark account"],
    }
    assert server["tools"]["inspect_reference_videos"]["routing"]["mode"] == "prefer"
    marker = json.loads(paths.marker.read_text(encoding="utf-8"))
    assert marker["profile"] == test_mode.TEST_PROFILE_EVIDENCE


def test_profile_switch_requires_a_reset(tmp_path: Path):
    root = _repo_fixture(tmp_path)
    test_mode.prepare_test_mode(root, profile=test_mode.TEST_PROFILE_CLEAN)

    with pytest.raises(RuntimeError, match="reset before switching"):
        test_mode.prepare_test_mode(root, profile=test_mode.TEST_PROFILE_EVIDENCE)
