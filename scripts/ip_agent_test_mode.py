#!/usr/bin/env python3
"""Prepare, reset and launch an isolated local IP-Agent test environment."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

TEST_MODE_SCHEMA_VERSION = "ip-agent-test-mode-v1"
TEST_STATE_RELATIVE = Path("backend/.deer-flow-ip-test")
TEST_SNAPSHOTS_RELATIVE = Path("backend/.deer-flow-ip-test-snapshots")
TEST_MARKER_NAME = ".ip-agent-test-mode.json"
TEST_CONFIG_NAME = "config.yaml"
TEST_EXTENSIONS_CONFIG_NAME = "extensions_config.json"


@dataclass(frozen=True)
class TestModePaths:
    root: Path
    state_dir: Path
    snapshots_dir: Path
    marker: Path
    config: Path
    extensions_config: Path
    database_dir: Path


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
        database_dir=state_dir / "data",
    )


def _write_private_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


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
    raise FileNotFoundError("extensions_config.json and extensions_config.example.json are both missing")


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


def _install_product_defaults(paths: TestModePaths) -> None:
    defaults = paths.root / "product" / "defaults"
    user_source = defaults / "USER.md"
    agent_source = defaults / "agents" / "ip-agent"
    if not user_source.is_file():
        raise FileNotFoundError(f"product default is missing: {user_source}")
    if not (agent_source / "config.yaml").is_file() or not (agent_source / "SOUL.md").is_file():
        raise FileNotFoundError(f"product agent defaults are incomplete: {agent_source}")

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


def _write_marker(paths: TestModePaths, *, now: datetime | None = None) -> None:
    marker = {
        "schema_version": TEST_MODE_SCHEMA_VERSION,
        "created_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
        "root": str(paths.root),
        "state_dir": str(paths.state_dir),
        "database_dir": str(paths.database_dir),
    }
    _write_private_text(paths.marker, json.dumps(marker, ensure_ascii=False, indent=2) + "\n")


def _validate_marker(paths: TestModePaths) -> dict[str, Any]:
    expected_state = (paths.root / TEST_STATE_RELATIVE).resolve()
    if paths.state_dir != expected_state:
        raise RuntimeError("refusing test reset outside the repository's fixed test-state directory")
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
    return marker


def prepare_test_mode(
    root: Path,
    *,
    source_config: Path | None = None,
    now: datetime | None = None,
) -> TestModePaths:
    paths = resolve_test_mode_paths(root)
    if paths.state_dir.exists():
        has_contents = any(paths.state_dir.iterdir())
        if has_contents and not paths.marker.is_file():
            raise RuntimeError(f"refusing to prepare an unmarked non-empty directory: {paths.state_dir}")
        if paths.marker.is_file():
            _validate_marker(paths)
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.state_dir.chmod(0o700)
    _write_isolated_config(paths, (source_config or (paths.root / "config.yaml")).resolve())

    if not paths.extensions_config.exists():
        source = _source_extensions_config(paths.root)
        shutil.copy2(source, paths.extensions_config)
        paths.extensions_config.chmod(0o600)

    _install_product_defaults(paths)
    if not paths.marker.exists():
        _write_marker(paths, now=now)
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

    fresh = prepare_test_mode(paths.root, source_config=source_config, now=now)
    return fresh, snapshot


def test_mode_environment(paths: TestModePaths) -> dict[str, str]:
    _validate_marker(paths)
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
        }
    )
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
    snapshots = len(list(paths.snapshots_dir.iterdir())) if paths.snapshots_dir.is_dir() else 0
    return {
        "schema_version": TEST_MODE_SCHEMA_VERSION,
        "prepared": prepared,
        "marker_valid": marker_valid,
        "state_dir": str(paths.state_dir),
        "database": str(paths.database_dir / "deerflow.db"),
        "database_exists": (paths.database_dir / "deerflow.db").is_file(),
        "snapshots": snapshots,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("prepare", "reset", "start", "status", "stop"),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--daemon", action="store_true", help="start services in the background")
    parser.add_argument("--with-nginx", action="store_true", help="use the nginx-backed local profile")
    parser.add_argument("--install", action="store_true", help="sync dependencies before starting")
    return parser


def main() -> None:
    args = _parser().parse_args()
    root = args.root.resolve()
    paths = resolve_test_mode_paths(root)

    if args.command == "prepare":
        paths = prepare_test_mode(root)
        print(json.dumps(_status(paths), ensure_ascii=False, indent=2))
        return
    if args.command == "reset":
        paths, snapshot = reset_test_mode(root)
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

    paths = prepare_test_mode(root)
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
