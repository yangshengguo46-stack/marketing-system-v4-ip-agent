#!/usr/bin/env python3
"""Prepare, reset and launch an isolated local IP-Agent test environment."""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from deerflow.config.agents_config import agent_artifact_sha256

TEST_MODE_SCHEMA_VERSION = "ip-agent-test-mode-v1"
TEST_STATE_RELATIVE = Path("backend/.deer-flow-ip-test")
TEST_SNAPSHOTS_RELATIVE = Path("backend/.deer-flow-ip-test-snapshots")
TEST_MARKER_NAME = ".ip-agent-test-mode.json"
TEST_CONFIG_NAME = "config.yaml"
TEST_EXTENSIONS_CONFIG_NAME = "extensions_config.json"
TEST_MEDIAKIT_API_KEY_RELATIVE = Path("secrets/mediakit-api-key")
PRODUCT_RUNTIME_PROFILE_NAME = "product-runtime-profile.yaml"
TEST_PROFILE_CLEAN = "clean"
TEST_PROFILE_EVIDENCE = "evidence"
EVIDENCE_MCP_SERVER_NAME = "ip_evidence"
TestProfile = Literal["clean", "evidence"]


@dataclass(frozen=True)
class TestModePaths:
    root: Path
    state_dir: Path
    snapshots_dir: Path
    marker: Path
    config: Path
    extensions_config: Path
    runtime_profile: Path
    database_dir: Path
    evidence_browser_profile_dir: Path
    mediakit_api_key_file: Path


def _utc_stamp(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    return value.astimezone(UTC).strftime("%Y%m%d-%H%M%S")


def resolve_test_mode_paths(root: Path) -> TestModePaths:
    resolved_root = root.expanduser().resolve()
    state_dir = (resolved_root / TEST_STATE_RELATIVE).resolve()
    snapshots_dir = (resolved_root / TEST_SNAPSHOTS_RELATIVE).resolve()
    return TestModePaths(
        root=resolved_root,
        state_dir=state_dir,
        snapshots_dir=snapshots_dir,
        marker=state_dir / TEST_MARKER_NAME,
        config=state_dir / TEST_CONFIG_NAME,
        extensions_config=state_dir / TEST_EXTENSIONS_CONFIG_NAME,
        runtime_profile=state_dir / PRODUCT_RUNTIME_PROFILE_NAME,
        database_dir=state_dir / "data",
        evidence_browser_profile_dir=state_dir
        / "evidence-mcp"
        / "browser-profile"
        / "douyin",
        mediakit_api_key_file=state_dir / TEST_MEDIAKIT_API_KEY_RELATIVE,
    )


def _write_private_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _validated_mediakit_api_key(value: str) -> str:
    key = str(value or "").strip()
    if not re.fullmatch(r"AKLT[A-Za-z0-9_-]{32,252}", key):
        raise ValueError("MediaKit API Key format is invalid")
    return key


def configure_mediakit_api_key(paths: TestModePaths, value: str) -> None:
    """Store one test-only provider key outside runtime configuration."""

    _validate_marker(paths, expected_profile=TEST_PROFILE_EVIDENCE)
    _write_private_text(
        paths.mediakit_api_key_file,
        _validated_mediakit_api_key(value) + "\n",
    )


def _read_mediakit_api_key(paths: TestModePaths) -> str | None:
    path = paths.mediakit_api_key_file
    if not path.is_file():
        return None
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise RuntimeError("test MediaKit API Key file permissions are too broad")
    try:
        return _validated_mediakit_api_key(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("test MediaKit API Key file is invalid") from exc


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"required configuration file is missing: {path}")
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"configuration root must be an object: {path}")
    return value


def _source_extensions_config(root: Path) -> Path:
    configured = root / "extensions_config.json"
    if configured.is_file():
        return configured
    example = root / "extensions_config.example.json"
    if example.is_file():
        return example
    raise FileNotFoundError(
        "extensions_config.json and extensions_config.example.json are both missing"
    )


def _write_isolated_config(paths: TestModePaths, source_config: Path) -> None:
    config = _load_mapping(source_config)
    database = config.get("database")
    if not isinstance(database, dict):
        database = {}
    database.update(
        {
            "backend": "sqlite",
            "sqlite_dir": str(paths.database_dir),
            "postgres_url": "",
        }
    )
    config["database"] = database

    scheduler = config.get("scheduler")
    if not isinstance(scheduler, dict):
        scheduler = {}
    scheduler["enabled"] = False
    config["scheduler"] = scheduler

    channel_connections = config.get("channel_connections")
    if not isinstance(channel_connections, dict):
        channel_connections = {}
    channel_connections["enabled"] = False
    for provider, value in list(channel_connections.items()):
        if provider == "enabled":
            continue
        if isinstance(value, dict):
            value["enabled"] = False
    config["channel_connections"] = channel_connections

    _write_private_text(
        paths.config,
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
    )


def _install_product_defaults(paths: TestModePaths, *, profile: TestProfile) -> None:
    defaults = paths.root / "product" / "defaults"
    user_source = defaults / "USER.md"
    agent_source = defaults / "agents" / "ip-agent"
    runtime_profile_source = defaults / PRODUCT_RUNTIME_PROFILE_NAME
    if not user_source.is_file():
        raise FileNotFoundError(f"product default is missing: {user_source}")
    if (
        not (agent_source / "config.yaml").is_file()
        or not (agent_source / "SOUL.md").is_file()
    ):
        raise FileNotFoundError(
            f"product agent defaults are incomplete: {agent_source}"
        )
    if not runtime_profile_source.is_file():
        raise FileNotFoundError(
            f"product runtime profile is missing: {runtime_profile_source}"
        )

    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.state_dir.chmod(0o700)
    user_target = paths.state_dir / "USER.md"
    if not user_target.exists():
        shutil.copy2(user_source, user_target)
        user_target.chmod(0o600)

    agent_target = paths.state_dir / "users" / "default" / "agents" / "ip-agent"
    agent_target.mkdir(parents=True, exist_ok=True)
    agent_target.chmod(0o700)
    for name in ("config.yaml", "SOUL.md"):
        target = agent_target / name
        shutil.copy2(agent_source / name, target)
        target.chmod(0o600)
    shutil.copy2(runtime_profile_source, paths.runtime_profile)
    paths.runtime_profile.chmod(0o600)

    config_target = agent_target / "config.yaml"
    config = _load_mapping(config_target)
    runtime_profile = _load_mapping(paths.runtime_profile)
    source_artifact_sha256 = agent_artifact_sha256(agent_source)
    if runtime_profile.get("agent_artifact_sha256") != source_artifact_sha256:
        raise ValueError(
            "IP Agent default files and product runtime profile artifact digest drifted"
        )
    capability_contract = runtime_profile.get("capability_contract")
    if not isinstance(capability_contract, dict):
        raise ValueError("IP Agent runtime profile must define capability_contract")
    expected_contract = {
        "tool_allowlist": config.get("tool_allowlist"),
        "skills": config.get("skills"),
        "memory_enabled": config.get("memory_enabled"),
    }
    if capability_contract != expected_contract:
        raise ValueError(
            "IP Agent default config and product runtime profile capability_contract drifted"
        )
    if profile == TEST_PROFILE_EVIDENCE:
        allowlist = config.get("tool_allowlist")
        if not isinstance(allowlist, list):
            raise ValueError("IP Agent test config must define a tool_allowlist")
        for tool_name in (
            "ip_evidence_collect_douyin_benchmark_account",
            "ip_evidence_inspect_reference_videos",
        ):
            if tool_name not in allowlist:
                allowlist.append(tool_name)
        _write_private_text(
            config_target,
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        )
        capability_contract["tool_allowlist"] = list(allowlist)
        runtime_profile["agent_artifact_sha256"] = agent_artifact_sha256(agent_target)
        _write_private_text(
            paths.runtime_profile,
            yaml.safe_dump(
                runtime_profile,
                allow_unicode=True,
                sort_keys=False,
            ),
        )


def _write_test_extensions(paths: TestModePaths, *, profile: TestProfile) -> None:
    if paths.extensions_config.is_file():
        try:
            payload = json.loads(paths.extensions_config.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("test extensions configuration is invalid JSON") from exc
    else:
        source = _source_extensions_config(paths.root)
        payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("test extensions configuration root must be an object")
    existing_servers = payload.get("mcpServers")
    existing_server = (
        existing_servers.get(EVIDENCE_MCP_SERVER_NAME)
        if isinstance(existing_servers, dict)
        else None
    )
    previous_env = (
        existing_server.get("env")
        if isinstance(existing_server, dict)
        and isinstance(existing_server.get("env"), dict)
        else {}
    )
    if profile == TEST_PROFILE_EVIDENCE:
        payload["middlewares"] = []
        payload["mcpInterceptors"] = []
        payload.pop("mcpInterceptorsRequired", None)
        payload["mcpServers"] = {}
        payload["skills"] = {}
    servers = payload.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
        payload["mcpServers"] = servers
    binding_keys_json = previous_env.get("IP_AGENT_EVIDENCE_BINDING_KEYS_JSON")
    if not isinstance(
        binding_keys_json, str
    ) or not binding_keys_json.strip().startswith("{"):
        encoded_key = (
            base64.urlsafe_b64encode(secrets.token_bytes(32))
            .decode("ascii")
            .rstrip("=")
        )
        binding_keys_json = json.dumps({"test-v1": encoded_key}, separators=(",", ":"))
    servers.pop(EVIDENCE_MCP_SERVER_NAME, None)
    if profile == TEST_PROFILE_EVIDENCE:
        servers[EVIDENCE_MCP_SERVER_NAME] = {
            "enabled": True,
            "required": True,
            "type": "stdio",
            "command": "uv",
            "args": [
                "run",
                "--project",
                str(paths.root / "backend"),
                "python",
                "-m",
                "deerflow.ip_agent.evidence_mcp",
            ],
            "env": {
                "DEER_FLOW_HOME": str(paths.state_dir),
                "DEER_FLOW_CONFIG_PATH": str(paths.config),
                "DEER_FLOW_PROJECT_ROOT": str(paths.root),
                "IP_AGENT_TEST_MODE": "1",
                "IP_AGENT_EVIDENCE_BROWSER_PROFILE_DIR": str(
                    paths.evidence_browser_profile_dir
                ),
                "IP_AGENT_EVIDENCE_BROWSER_HEADLESS": "1",
                "IP_AGENT_EVIDENCE_BINDING_ACTIVE_KID": "test-v1",
                "IP_AGENT_EVIDENCE_BINDING_KEYS_JSON": binding_keys_json,
                "IP_AGENT_EVIDENCE_BINDING_TTL_SECONDS": "1800",
                "IP_AGENT_EVIDENCE_MCP_CLIENT_NAME": EVIDENCE_MCP_SERVER_NAME,
                "MEDIAKIT_API_KEY": "$MEDIAKIT_API_KEY",
            },
            "tool_call_timeout": 3600,
            "description": "Test-only grounded Douyin account and reference-video evidence.",
            "result_policy": {
                "trust": "untrusted_external",
                "semantic_class": "evidence",
                "outcome_contract": "ip-evidence-operation-status-v1",
            },
            "tools": {
                "collect_douyin_benchmark_account": {
                    "required": True,
                    "routing": {
                        "mode": "prefer",
                        "priority": 100,
                        "keywords": [
                            "抖音主页",
                            "抖音账号",
                            "对标账号",
                            "v.douyin.com",
                            "douyin.com/user/",
                            "profile URL",
                            "benchmark account",
                        ],
                    },
                },
                "inspect_reference_videos": {
                    "required": True,
                    "routing": {
                        "mode": "prefer",
                        "priority": 90,
                        "keywords": [
                            "作品链接",
                            "代表作品",
                            "作品拆解",
                            "拆解作品",
                            "参考视频",
                            "视频",
                            "上传",
                            "/mnt/user-data/uploads/",
                            "对标账号",
                            "v.douyin.com",
                            "douyin.com/user/",
                            "douyin.com/video/",
                            "video URL",
                            "reference video",
                            "benchmark account",
                        ],
                    },
                },
            },
        }
    _write_private_text(
        paths.extensions_config,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def _write_marker(
    paths: TestModePaths, *, profile: TestProfile, now: datetime | None = None
) -> None:
    marker = {
        "schema_version": TEST_MODE_SCHEMA_VERSION,
        "created_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
        "root": str(paths.root),
        "state_dir": str(paths.state_dir),
        "database_dir": str(paths.database_dir),
        "profile": profile,
    }
    _write_private_text(
        paths.marker, json.dumps(marker, ensure_ascii=False, indent=2) + "\n"
    )


def _validate_marker(
    paths: TestModePaths, *, expected_profile: TestProfile | None = None
) -> dict[str, Any]:
    expected_state = (paths.root / TEST_STATE_RELATIVE).resolve()
    if paths.state_dir != expected_state:
        raise RuntimeError(
            "refusing test reset outside the repository's fixed test-state directory"
        )
    if not paths.marker.is_file():
        raise RuntimeError(f"refusing to rotate unmarked directory: {paths.state_dir}")
    try:
        marker = json.loads(paths.marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("test-mode marker is unreadable") from exc
    expected = {
        "schema_version": TEST_MODE_SCHEMA_VERSION,
        "root": str(paths.root),
        "state_dir": str(paths.state_dir),
        "database_dir": str(paths.database_dir),
    }
    for key, value in expected.items():
        if marker.get(key) != value:
            raise RuntimeError(f"test-mode marker mismatch for {key}")
    profile = marker.get("profile", TEST_PROFILE_CLEAN)
    if profile not in {TEST_PROFILE_CLEAN, TEST_PROFILE_EVIDENCE}:
        raise RuntimeError("test-mode marker contains an unknown profile")
    if expected_profile is not None and profile != expected_profile:
        raise RuntimeError(
            f"test mode is prepared as profile '{profile}', not '{expected_profile}'; reset before switching profiles"
        )
    return marker


def prepare_test_mode(
    root: Path,
    *,
    source_config: Path | None = None,
    profile: TestProfile = TEST_PROFILE_CLEAN,
    now: datetime | None = None,
) -> TestModePaths:
    paths = resolve_test_mode_paths(root)
    if paths.state_dir.exists():
        has_contents = any(paths.state_dir.iterdir())
        if has_contents and not paths.marker.is_file():
            raise RuntimeError(
                f"refusing to prepare an unmarked non-empty directory: {paths.state_dir}"
            )
        if paths.marker.is_file():
            _validate_marker(paths, expected_profile=profile)
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.state_dir.chmod(0o700)
    _write_isolated_config(
        paths, (source_config or (paths.root / "config.yaml")).resolve()
    )

    _write_test_extensions(paths, profile=profile)
    _install_product_defaults(paths, profile=profile)
    if not paths.marker.exists():
        _write_marker(paths, profile=profile, now=now)
    return paths


def stop_services(root: Path) -> None:
    subprocess.run(
        ["bash", str(root / "scripts" / "serve.sh"), "--stop"],
        cwd=root,
        check=True,
    )


def reset_test_mode(
    root: Path,
    *,
    source_config: Path | None = None,
    profile: TestProfile = TEST_PROFILE_CLEAN,
    now: datetime | None = None,
    stop_running_services: bool = True,
) -> tuple[TestModePaths, Path | None]:
    paths = resolve_test_mode_paths(root)
    if stop_running_services:
        stop_services(paths.root)

    snapshot: Path | None = None
    if paths.state_dir.exists():
        _validate_marker(paths)
        paths.snapshots_dir.mkdir(parents=True, exist_ok=True)
        paths.snapshots_dir.chmod(0o700)
        snapshot = paths.snapshots_dir / _utc_stamp(now)
        suffix = 1
        while snapshot.exists():
            snapshot = paths.snapshots_dir / f"{_utc_stamp(now)}-{suffix}"
            suffix += 1
        paths.state_dir.rename(snapshot)

    fresh = prepare_test_mode(
        paths.root, source_config=source_config, profile=profile, now=now
    )
    return fresh, snapshot


def test_mode_environment(paths: TestModePaths) -> dict[str, str]:
    marker = _validate_marker(paths)
    environment = dict(os.environ)
    environment.update(
        {
            "DEER_FLOW_HOME": str(paths.state_dir),
            "DEER_FLOW_CONFIG_PATH": str(paths.config),
            "DEER_FLOW_EXTENSIONS_CONFIG_PATH": str(paths.extensions_config),
            "DEER_FLOW_PROJECT_ROOT": str(paths.root),
            "DEER_FLOW_AUTH_DISABLED": "1",
            "IP_AGENT_TEST_MODE": "1",
            "NEXT_PUBLIC_IP_AGENT_TEST_MODE": "1",
            "DEER_FLOW_MCP_STDIO_COMMAND_ALLOWLIST": "npx,uvx,uv",
        }
    )
    if marker.get("profile") == TEST_PROFILE_EVIDENCE:
        if mediakit_api_key := _read_mediakit_api_key(paths):
            environment["MEDIAKIT_API_KEY"] = mediakit_api_key
    return environment


def _status(paths: TestModePaths) -> dict[str, Any]:
    prepared = paths.state_dir.is_dir() and paths.marker.is_file()
    marker_valid = False
    if prepared:
        try:
            _validate_marker(paths)
            marker_valid = True
        except RuntimeError:
            marker_valid = False
    snapshots = (
        len(list(paths.snapshots_dir.iterdir())) if paths.snapshots_dir.is_dir() else 0
    )
    profile = None
    if prepared and marker_valid:
        profile = _validate_marker(paths).get("profile", TEST_PROFILE_CLEAN)
    return {
        "schema_version": TEST_MODE_SCHEMA_VERSION,
        "prepared": prepared,
        "marker_valid": marker_valid,
        "state_dir": str(paths.state_dir),
        "database": str(paths.database_dir / "deerflow.db"),
        "database_exists": (paths.database_dir / "deerflow.db").is_file(),
        "snapshots": snapshots,
        "profile": profile,
        "mediakit_api_key_configured": bool(
            prepared
            and marker_valid
            and profile == TEST_PROFILE_EVIDENCE
            and _read_mediakit_api_key(paths)
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "prepare",
            "reset",
            "start",
            "status",
            "stop",
            "login-douyin",
            "configure-mediakit",
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--daemon", action="store_true", help="start services in the background"
    )
    parser.add_argument(
        "--with-nginx", action="store_true", help="use the nginx-backed local profile"
    )
    parser.add_argument(
        "--install", action="store_true", help="sync dependencies before starting"
    )
    parser.add_argument(
        "--profile",
        choices=(TEST_PROFILE_CLEAN, TEST_PROFILE_EVIDENCE),
        default=TEST_PROFILE_CLEAN,
        help="clean keeps the permanent Chat baseline; evidence adds only the two test MCP tools",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    root = args.root.resolve()
    paths = resolve_test_mode_paths(root)

    if args.command == "prepare":
        paths = prepare_test_mode(root, profile=args.profile)
        print(json.dumps(_status(paths), ensure_ascii=False, indent=2))
        return
    if args.command == "reset":
        paths, snapshot = reset_test_mode(root, profile=args.profile)
        payload = _status(paths)
        payload["snapshot"] = str(snapshot) if snapshot else None
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if args.command == "status":
        print(json.dumps(_status(paths), ensure_ascii=False, indent=2))
        return
    if args.command == "stop":
        stop_services(root)
        return

    if args.command == "configure-mediakit":
        _validate_marker(paths, expected_profile=TEST_PROFILE_EVIDENCE)
        value = (
            getpass.getpass("MediaKit API Key: ")
            if sys.stdin.isatty()
            else sys.stdin.read()
        )
        configure_mediakit_api_key(paths, value)
        print("MediaKit API Key configured for isolated IP-Agent test mode.")
        return

    if args.command == "login-douyin":
        _validate_marker(paths, expected_profile=TEST_PROFILE_EVIDENCE)
        environment = test_mode_environment(paths)
        environment["IP_AGENT_EVIDENCE_BROWSER_PROFILE_DIR"] = str(
            paths.evidence_browser_profile_dir
        )
        command = [
            "uv",
            "run",
            "--project",
            str(root / "backend"),
            "python",
            "-m",
            "deerflow.ip_agent.evidence_mcp",
            "login-douyin",
        ]
        os.execvpe(command[0], command, environment)

    paths = prepare_test_mode(root, profile=args.profile)
    command = ["bash", str(root / "scripts" / "serve.sh"), "--dev"]
    if not args.with_nginx:
        command.append("--no-nginx")
    if not args.install:
        command.append("--skip-install")
    if args.daemon:
        command.append("--daemon")
    print("IP-Agent TEST MODE")
    print(f"  isolated state: {paths.state_dir}")
    print(f"  isolated database: {paths.database_dir / 'deerflow.db'}")
    print("  reset command: make ip-test-reset")
    sys.stdout.flush()
    os.execvpe(command[0], command, test_mode_environment(paths))


if __name__ == "__main__":
    main()
