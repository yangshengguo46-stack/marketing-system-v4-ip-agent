#!/usr/bin/env python3
"""Install, manage, and diagnose the optional local UI-TARS operator."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "backend" / "packages" / "harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from deerflow.community.ui_tars.client import UITarsOperatorClient, UITarsOperatorError  # noqa: E402
from deerflow.community.ui_tars.permissions import diagnose_desktop_permissions  # noqa: E402
from deerflow.community.ui_tars.service import build_http_server  # noqa: E402
from deerflow.community.ui_tars.source import verify_vendored_ui_tars  # noqa: E402
from deerflow.config import get_app_config  # noqa: E402
from deerflow.config.runtime_paths import runtime_home  # noqa: E402


def _state_dir() -> Path:
    return runtime_home() / "ui-tars"


def _paths() -> tuple[Path, Path, Path]:
    state = _state_dir()
    return state / "operator.pid", state / "operator.token", state / "operator.log"


def _pid() -> int | None:
    pid_path, _, _ = _paths()
    try:
        value = int(pid_path.read_text(encoding="ascii").strip())
        os.kill(value, 0)
        return value
    except (OSError, TypeError, ValueError):
        return None


def _pid_is_ours(pid: int) -> bool:
    if sys.platform != "darwin" and not sys.platform.startswith("linux"):
        return True
    try:
        command = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "ui_tars_operator.py serve" in command


def _write_private(path: Path, value: str) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, value.encode("utf-8"))
    finally:
        os.close(descriptor)


def install() -> dict[str, Any]:
    manifest = verify_vendored_ui_tars()
    state = _state_dir()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    installed = {
        "contract_version": "deerflow-ui-tars-install-v1",
        "installed_at": datetime.now(UTC).isoformat(),
        "source_commit": manifest["upstream_commit"],
        "source_tree_sha256": manifest["source_tree_sha256"],
        "operator_backend": "deerflow-source-only-macos-system-api",
        "precompiled_native_binaries": False,
        "deerflow_is_only_brain": True,
    }
    _write_private(state / "installed.json", json.dumps(installed, sort_keys=True, separators=(",", ":")) + "\n")
    return installed


def _health_sync(timeout: float = 2.0) -> dict[str, Any]:
    config = get_app_config().ui_tars
    client = UITarsOperatorClient(config.endpoint, timeout_seconds=timeout)
    return client._request("/health", payload=None, authenticated=False)  # noqa: SLF001 - lifecycle probe


def start() -> dict[str, Any]:
    config = get_app_config().ui_tars
    if not config.enabled:
        raise RuntimeError("UI-TARS is disabled; set config.yaml -> ui_tars.enabled: true first")
    if not config.model or not config.api_base:
        raise RuntimeError("UI-TARS model/api_base is missing; configure it before starting the operator")
    model_host = urlsplit(config.api_base).hostname
    if model_host not in {"127.0.0.1", "localhost", "::1"} and not os.environ.get(config.api_key_env, "").strip():
        raise RuntimeError(f"UI-TARS remote model credential is missing; export {config.api_key_env}")
    install()
    if config.mode == "connect":
        UITarsOperatorClient(config.endpoint, timeout_seconds=2.0)._token()  # noqa: SLF001 - lifecycle readiness check
        health = _health_sync()
        return {"status": "connected", "health": health}
    current = _pid()
    if current is not None and _pid_is_ours(current):
        return {"status": "already_running", "pid": current, "health": _health_sync()}

    state = _state_dir()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    pid_path, token_path, log_path = _paths()
    token = secrets.token_urlsafe(48)
    _write_private(token_path, token + "\n")
    environment = os.environ.copy()
    environment["UI_TARS_OPERATOR_TOKEN"] = token
    log = open(log_path, "ab", buffering=0)  # noqa: SIM115 - descriptor is transferred to the child
    try:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "serve"],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    finally:
        log.close()
    _write_private(pid_path, f"{process.pid}\n")
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            return {"status": "started", "pid": process.pid, "health": _health_sync()}
        except (UITarsOperatorError, RuntimeError):
            time.sleep(0.2)
    if process.poll() is None:
        process.terminate()
    pid_path.unlink(missing_ok=True)
    token_path.unlink(missing_ok=True)
    raise RuntimeError("UI-TARS operator did not become healthy; inspect make ui-tars-doctor")


def serve() -> None:
    config = get_app_config().ui_tars
    token = os.environ.get("UI_TARS_OPERATOR_TOKEN", "")
    if not config.enabled or config.mode != "managed" or len(token) < 32:
        raise RuntimeError("Managed UI-TARS service requires enabled config and a lifecycle token")
    server = build_http_server(config, token=token, state_dir=_state_dir())

    def stop_server(_signum: int, _frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()


def stop() -> dict[str, Any]:
    pid_path, token_path, _ = _paths()
    pid = _pid()
    if pid is None:
        pid_path.unlink(missing_ok=True)
        token_path.unlink(missing_ok=True)
        return {"status": "not_running"}
    if not _pid_is_ours(pid):
        raise RuntimeError("Refusing to stop a stale PID that is not the UI-TARS operator")
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("UI-TARS operator did not stop within the timeout")
    pid_path.unlink(missing_ok=True)
    token_path.unlink(missing_ok=True)
    return {"status": "stopped", "pid": pid}


def status() -> dict[str, Any]:
    config = get_app_config().ui_tars
    try:
        health = _health_sync()
    except (UITarsOperatorError, RuntimeError):
        health = None
    return {
        "contract_version": "deerflow-ui-tars-lifecycle-v1",
        "enabled": config.enabled,
        "mode": config.mode,
        "process_running": _pid() is not None if config.mode == "managed" else None,
        "connected": health is not None,
        "health": health,
    }


def doctor() -> dict[str, Any]:
    config = get_app_config().ui_tars
    result = status()
    model_host = urlsplit(config.api_base).hostname if config.api_base else None
    remote_model = bool(model_host and model_host not in {"127.0.0.1", "localhost", "::1"})
    api_key_configured = bool(os.environ.get(config.api_key_env, "").strip())
    try:
        UITarsOperatorClient(config.endpoint, timeout_seconds=2.0)._token()  # noqa: SLF001 - readiness only
        operator_token_configured = True
    except UITarsOperatorError:
        operator_token_configured = False
    try:
        manifest = verify_vendored_ui_tars()
        source = {
            "status": "ok",
            "commit": manifest["upstream_commit"],
            "license": manifest["license"],
            "source_mode": manifest["source_mode"],
            "precompiled_native_binaries": False,
        }
    except RuntimeError as exc:
        source = {"status": "error", "detail": str(exc)}
    result.update(
        {
            "source": source,
            "permissions": diagnose_desktop_permissions(),
            "model_configured": bool(config.model and config.api_base and (api_key_configured or not remote_model)),
            "api_key_env": config.api_key_env,
            "api_key_configured": api_key_configured,
            "operator_token_configured": operator_token_configured,
            "fix": (
                "Set ui_tars.enabled/model/api_base, export the named API key for a remote model, "
                "run make ui-tars-install and make ui-tars-start, then grant Screen Recording and "
                "Accessibility to the launching Python executable. Connect mode also requires "
                "UI_TARS_OPERATOR_TOKEN."
            ),
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "start", "serve", "stop", "status", "doctor"))
    args = parser.parse_args()
    try:
        if args.command == "serve":
            serve()
            return 0
        operation = {
            "install": install,
            "start": start,
            "stop": stop,
            "status": status,
            "doctor": doctor,
        }[args.command]
        result = operation()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        if args.command == "status" and not result.get("connected"):
            return 1
        return 0
    except (FileNotFoundError, RuntimeError, UITarsOperatorError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
