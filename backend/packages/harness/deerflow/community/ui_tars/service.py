"""Single-step UI-TARS model/operator service.

This module deliberately contains no task loop or planning runtime. DeerFlow
decides the task and calls the service for one bounded visual action at a time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from deerflow.config.ui_tars_config import UITarsConfig

from .audit import append_receipt, build_receipt, ui_tars_state_dir
from .permissions import diagnose_desktop_permissions
from .privacy import (
    contains_secret_material,
    high_impact_categories,
    pixelate_png,
    sanitize_mapping,
    sanitize_text,
)
from .source import verify_vendored_ui_tars

_ACTION_RE = re.compile(r"(?s)^\s*(?:Action[:：]\s*)?(\w+)\((.*)\)\s*$")
_SUPPORTED_ACTIONS = {"click", "left_click", "left_single", "left_double", "double_click", "type", "hotkey", "scroll", "wait", "finished", "call_user"}


class UITarsServiceError(RuntimeError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


class DesktopBackend(Protocol):
    def capture_png(self) -> bytes: ...

    def execute(self, action: dict[str, Any], *, width: int, height: int) -> str: ...


def _run_checked(command: list[str], *, timeout: float = 15.0) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise UITarsServiceError("operator_dependency_missing", f"Required desktop command is missing: {Path(command[0]).name}") from exc
    except subprocess.TimeoutExpired as exc:
        raise UITarsServiceError("operator_timeout", "The local desktop command timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise UITarsServiceError("desktop_permission_or_action_failed", "The desktop action failed; check Screen Recording and Accessibility permissions") from exc


class MacOSDesktopBackend:
    """Source-only macOS backend using operating-system commands, not libnut."""

    _CLICK_SCRIPT = """
on run argv
  set px to item 1 of argv as integer
  set py to item 2 of argv as integer
  tell application "System Events" to click at {px, py}
end run
"""
    _DOUBLE_CLICK_SCRIPT = """
on run argv
  set px to item 1 of argv as integer
  set py to item 2 of argv as integer
  tell application "System Events"
    click at {px, py}
    delay 0.12
    click at {px, py}
  end tell
end run
"""
    _TYPE_SCRIPT = """
on run argv
  tell application "System Events" to keystroke (item 1 of argv)
end run
"""
    _KEY_SCRIPT = """
on run argv
  set requestedKey to item 1 of argv
  tell application "System Events"
    if requestedKey is "escape" then
      key code 53
    else if requestedKey is "tab" then
      key code 48
    else if requestedKey is "cmd+c" then
      keystroke "c" using command down
    else if requestedKey is "cmd+v" then
      keystroke "v" using command down
    else if requestedKey is "cmd+a" then
      keystroke "a" using command down
    else
      error "unsupported hotkey"
    end if
  end tell
end run
"""
    _SCROLL_SCRIPT = """
on run argv
  set requestedDirection to item 1 of argv
  tell application "System Events"
    repeat 5 times
      if requestedDirection is "up" then
        key code 126
      else if requestedDirection is "down" then
        key code 125
      else
        error "unsupported scroll direction"
      end if
    end repeat
  end tell
end run
"""

    def capture_png(self) -> bytes:
        with tempfile.NamedTemporaryFile(prefix="deerflow-ui-tars-", suffix=".png", delete=False) as temporary:
            path = Path(temporary.name)
        try:
            path.chmod(0o600)
            _run_checked(["/usr/sbin/screencapture", "-x", "-t", "png", str(path)], timeout=20.0)
            return path.read_bytes()
        finally:
            path.unlink(missing_ok=True)

    @staticmethod
    def _coords(action: dict[str, Any], *, width: int, height: int) -> tuple[int, int]:
        raw = str(action.get("inputs", {}).get("start_box") or "")
        numbers = [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", raw)]
        if len(numbers) not in {2, 4}:
            raise UITarsServiceError("invalid_model_action", "UI-TARS click action has no valid start_box")
        if len(numbers) == 2:
            x, y = numbers
        else:
            x, y = (numbers[0] + numbers[2]) / 2, (numbers[1] + numbers[3]) / 2
        # DeerFlow's single-step prompt fixes the UI-TARS action space to 0..1000.
        x = max(0.0, min(1000.0, x)) / 1000.0 * width
        y = max(0.0, min(1000.0, y)) / 1000.0 * height
        return round(x), round(y)

    def execute(self, action: dict[str, Any], *, width: int, height: int) -> str:
        action_type = str(action.get("type") or "")
        inputs = action.get("inputs") if isinstance(action.get("inputs"), dict) else {}
        if action_type in {"finished", "call_user"}:
            return "completed" if action_type == "finished" else "requires_user"
        if action_type == "wait":
            time.sleep(2.0)
            return "executed"
        if action_type in {"click", "left_click", "left_single", "left_double", "double_click"}:
            x, y = self._coords(action, width=width, height=height)
            script = self._DOUBLE_CLICK_SCRIPT if action_type in {"left_double", "double_click"} else self._CLICK_SCRIPT
            _run_checked(["/usr/bin/osascript", "-e", script, str(x), str(y)])
            return "executed"
        if action_type == "type":
            content = str(inputs.get("content") or "")
            if not content or contains_secret_material(content):
                raise UITarsServiceError("sensitive_input_blocked", "UI-TARS refused to type empty or credential-like content")
            if content.endswith("\n") or content.endswith("\\n"):
                raise UITarsServiceError("approval_boundary", "UI-TARS typing cannot submit forms; use a separately approved action")
            _run_checked(["/usr/bin/osascript", "-e", self._TYPE_SCRIPT, content])
            return "executed"
        if action_type == "hotkey":
            key = str(inputs.get("key") or inputs.get("hotkey") or "").strip().lower().replace("command", "cmd")
            if key not in {"escape", "tab", "cmd+c", "cmd+v", "cmd+a"}:
                raise UITarsServiceError("unsupported_action", "UI-TARS requested a hotkey outside the reversible allowlist")
            _run_checked(["/usr/bin/osascript", "-e", self._KEY_SCRIPT, key])
            return "executed"
        if action_type == "scroll":
            direction = str(inputs.get("direction") or "").strip().lower()
            if direction not in {"up", "down"}:
                raise UITarsServiceError("unsupported_action", "UI-TARS requested an unsupported scroll direction")
            _run_checked(["/usr/bin/osascript", "-e", self._SCROLL_SCRIPT, direction])
            return "executed"
        raise UITarsServiceError("unsupported_action", "UI-TARS requested an unsupported desktop action")


def _split_arguments(value: str) -> list[str]:
    result: list[str] = []
    current: list[str] = []
    quote: str | None = None
    depth = 0
    for character in value:
        if quote:
            current.append(character)
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
            current.append(character)
        elif character in "([{":
            depth += 1
            current.append(character)
        elif character in ")]}":
            depth = max(0, depth - 1)
            current.append(character)
        elif character == "," and depth == 0:
            result.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if current:
        result.append("".join(current).strip())
    return result


def parse_ui_tars_action(prediction: str) -> dict[str, Any]:
    """Parse the upstream UI-TARS function-call action format without thoughts."""
    action_line = prediction.strip().split("Action:")[-1].strip().splitlines()[0]
    match = _ACTION_RE.match(action_line)
    if not match:
        raise UITarsServiceError("invalid_model_action", "UI-TARS model did not return a function-call action")
    action_type, raw_arguments = match.groups()
    if action_type not in _SUPPORTED_ACTIONS:
        raise UITarsServiceError("unsupported_action", "UI-TARS model returned an action outside the local allowlist")
    inputs: dict[str, str] = {}
    for pair in _split_arguments(raw_arguments):
        if not pair:
            continue
        key, separator, raw_value = pair.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()):
            raise UITarsServiceError("invalid_model_action", "UI-TARS model returned malformed action arguments")
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        inputs[key.strip()] = value
    return {"type": action_type, "inputs": inputs}


@dataclass(slots=True)
class UITarsModelClient:
    api_base: str
    api_key: str
    model: str
    timeout_seconds: float

    def _endpoint(self) -> str:
        if self.api_base.endswith("/chat/completions"):
            return self.api_base
        return f"{self.api_base.rstrip('/')}/chat/completions"

    def predict(
        self,
        *,
        intent: str,
        target_app: str,
        target_window: str,
        screenshot_png: bytes,
        approved_high_impact: bool,
    ) -> str:
        system_prompt = """You are a bounded UI-TARS computer operator controlled by DeerFlow.
Return exactly one action and no prose. Coordinates use a 0..1000 screen.
Allowed actions:
click(start_box='[x1,y1,x2,y2]')
left_double(start_box='[x1,y1,x2,y2]')
type(content='non-sensitive text')
hotkey(key='escape|tab|cmd+c|cmd+v|cmd+a')
scroll(direction='up|down')
wait()
finished()
call_user()
Never type credentials or solve authentication challenges. Submit, publish,
send, delete, setting-change and payment actions are allowed only when the user
text explicitly says that DeerFlow verified high-impact approval."""
        user_text = sanitize_text(
            f"Intent: {intent}\nTarget application: {target_app}\nTarget window: {target_window}\nDeerFlow verified high-impact approval: {'yes' if approved_high_impact else 'no'}",
            max_chars=1_000,
        )
        image_url = "data:image/png;base64," + base64.b64encode(screenshot_png).decode("ascii")
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 256,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self._endpoint(),
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(2_097_153)
        except urllib.error.HTTPError as exc:
            category = "model_auth" if exc.code in {401, 403} else "model_rejected"
            raise UITarsServiceError(category, f"UI-TARS model request failed (HTTP {exc.code})") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UITarsServiceError("model_unavailable", "UI-TARS model endpoint is unavailable") from exc
        if len(raw) > 2_097_152:
            raise UITarsServiceError("invalid_model_response", "UI-TARS model response exceeded the safety limit")
        try:
            decoded = json.loads(raw)
            content = decoded["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise UITarsServiceError("invalid_model_response", "UI-TARS model returned an invalid response") from exc
        if not isinstance(content, str) or not content.strip():
            raise UITarsServiceError("invalid_model_response", "UI-TARS model returned no action")
        return content


class UITarsSingleStepService:
    def __init__(
        self,
        config: UITarsConfig,
        *,
        state_dir: Path | None = None,
        backend: DesktopBackend | None = None,
        model_client: UITarsModelClient | None = None,
    ) -> None:
        self.config = config
        self.state_dir = state_dir or ui_tars_state_dir()
        self.backend = backend or MacOSDesktopBackend()
        api_key = os.environ.get(config.api_key_env, "").strip()
        self.model_client = model_client or UITarsModelClient(
            api_base=config.api_base,
            api_key=api_key,
            model=config.model,
            timeout_seconds=config.request_timeout_seconds,
        )

    def health(self) -> dict[str, Any]:
        parsed = urlsplit(self.config.api_base) if self.config.api_base else None
        remote_model = bool(parsed and parsed.hostname not in {"127.0.0.1", "localhost", "::1"})
        api_key_configured = bool(os.environ.get(self.config.api_key_env, "").strip())
        source: dict[str, Any]
        try:
            verified = verify_vendored_ui_tars()
            source = {
                "status": "ok",
                "commit": verified["upstream_commit"],
                "license": verified["license"],
                "source_mode": verified["source_mode"],
            }
        except RuntimeError as exc:
            source = {"status": "error", "detail": str(exc)}
        model_ready = bool(self.config.model and self.config.api_base and (api_key_configured or not remote_model))
        return sanitize_mapping(
            {
                "contract_version": "deerflow-ui-tars-health-v1",
                "status": "ok" if source.get("status") == "ok" and model_ready else "degraded",
                "deerflow_is_only_brain": True,
                "max_steps_per_call": 1,
                "model_id": self.config.model,
                "model_configured": model_ready,
                "api_key_configured": api_key_configured,
                "screenshot_privacy": self.config.screenshot_privacy,
                "permissions": diagnose_desktop_permissions(),
                "source": source,
            }
        )

    def _write_evidence(self, image: bytes) -> dict[str, str]:
        evidence_dir = self.state_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = f"evidence-{uuid.uuid4().hex}.png"
        path = evidence_dir / name
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, image)
        finally:
            os.close(descriptor)
        return {
            "kind": "privacy_transformed_screenshot",
            "ref": f"ui-tars/evidence/{name}",
            "sha256": hashlib.sha256(image).hexdigest(),
            "privacy": "whole_screen_pixelated_no_raw_text",
        }

    def step(self, request: dict[str, Any]) -> dict[str, Any]:
        intent = str(request.get("intent") or "").strip()
        target_app = str(request.get("target_app") or "").strip()
        target_window = str(request.get("target_window") or "").strip()
        task_id = str(request.get("task_id") or "").strip()
        fallback_reason = str(request.get("fallback_reason") or "").strip()
        account_id = str(request.get("account_id") or "").strip() or None
        approval_request_id = str(request.get("approval_request_id") or "").strip() or None
        approved = request.get("approved") is True
        evidence: dict[str, Any] = {}
        action_type: str | None = None
        try:
            if not intent or not target_app or not task_id:
                raise UITarsServiceError("invalid_request", "intent, target_app, and task_id are required")
            if fallback_reason not in {"browser_dom_unavailable", "browser_action_failed", "native_desktop_required"}:
                raise UITarsServiceError("fallback_policy", "UI-TARS requires a documented Browser Control failure or native desktop reason")
            if contains_secret_material(intent):
                raise UITarsServiceError("sensitive_input_blocked", "UI-TARS refuses instructions containing credential-like material")
            risks = high_impact_categories(intent)
            if risks and not approved:
                raise UITarsServiceError("approval_required", "High-impact UI-TARS work requires a verified DeerFlow risk confirmation")
            if not self.config.model or not self.config.api_base:
                raise UITarsServiceError("model_configuration", "UI-TARS model and API base must be configured before desktop capture")
            model_host = urlsplit(self.config.api_base).hostname
            if model_host not in {"127.0.0.1", "localhost", "::1"} and not os.environ.get(self.config.api_key_env, "").strip():
                raise UITarsServiceError("model_auth_missing", "UI-TARS remote model credential is missing")
            if self.config.screenshot_privacy == "blocked":
                raise UITarsServiceError("privacy_blocked", "UI-TARS screenshot model access is blocked by configuration")
            raw = self.backend.capture_png()
            transformed, width, height = pixelate_png(raw, block_size=self.config.pixelation_block_size)
            raw = b""
            evidence = self._write_evidence(transformed)
            prediction = self.model_client.predict(
                intent=sanitize_text(intent),
                target_app=sanitize_text(target_app, max_chars=160),
                target_window=sanitize_text(target_window, max_chars=240),
                screenshot_png=transformed,
                approved_high_impact=approved,
            )
            action = parse_ui_tars_action(prediction)
            action_type = action["type"]
            result = self.backend.execute(action, width=width, height=height)
            receipt = build_receipt(
                intent=intent,
                target_app=target_app,
                target_window=target_window,
                task_id=task_id,
                model_id=self.config.model,
                result=result,
                fallback_reason=fallback_reason,
                account_id=account_id,
                action_type=action_type,
                evidence=evidence,
                approval_request_id=approval_request_id,
            )
            audit_ref = append_receipt(receipt, base_dir=self.state_dir.parent)
            return {"status": "ok", "receipt": receipt, "audit_ref": audit_ref}
        except UITarsServiceError as exc:
            receipt = build_receipt(
                intent=intent,
                target_app=target_app,
                target_window=target_window,
                task_id=task_id,
                model_id=self.config.model,
                result="failed",
                fallback_reason=fallback_reason,
                account_id=account_id,
                action_type=action_type,
                evidence=evidence,
                failure_category=exc.category,
                approval_request_id=approval_request_id,
            )
            audit_ref = append_receipt(receipt, base_dir=self.state_dir.parent)
            return {
                "status": "error",
                "category": exc.category,
                "message": str(exc),
                "receipt": receipt,
                "audit_ref": audit_ref,
            }
        except Exception:
            receipt = build_receipt(
                intent=intent,
                target_app=target_app,
                target_window=target_window,
                task_id=task_id,
                model_id=self.config.model,
                result="failed",
                fallback_reason=fallback_reason,
                account_id=account_id,
                action_type=action_type,
                evidence=evidence,
                failure_category="internal_error",
                approval_request_id=approval_request_id,
            )
            audit_ref = append_receipt(receipt, base_dir=self.state_dir.parent)
            return {
                "status": "error",
                "category": "internal_error",
                "message": "The local UI-TARS operator failed safely; inspect its private diagnostics",
                "receipt": receipt,
                "audit_ref": audit_ref,
            }


def build_http_server(
    config: UITarsConfig,
    *,
    token: str,
    state_dir: Path | None = None,
    service: UITarsSingleStepService | None = None,
) -> ThreadingHTTPServer:
    endpoint = urlsplit(config.endpoint)
    host = endpoint.hostname or "127.0.0.1"
    port = endpoint.port or 80
    operator = service or UITarsSingleStepService(config, state_dir=state_dir)

    class Handler(BaseHTTPRequestHandler):
        server_version = "DeerFlowUITars/1"

        def log_message(self, _format: str, *_args: object) -> None:
            # Request bodies can include sensitive user intent. Never access-log them.
            return

        def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            raw = json.dumps(sanitize_mapping(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/health":
                self._json(HTTPStatus.NOT_FOUND, {"status": "error", "category": "not_found"})
                return
            self._json(HTTPStatus.OK, operator.health())

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/step":
                self._json(HTTPStatus.NOT_FOUND, {"status": "error", "category": "not_found"})
                return
            supplied = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if not hmac.compare_digest(supplied, token):
                self._json(HTTPStatus.UNAUTHORIZED, {"status": "error", "category": "authorization"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length < 2 or length > 65_536:
                self._json(HTTPStatus.BAD_REQUEST, {"status": "error", "category": "invalid_request"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except (TypeError, ValueError):
                self._json(HTTPStatus.BAD_REQUEST, {"status": "error", "category": "invalid_request"})
                return
            if not isinstance(payload, dict):
                self._json(HTTPStatus.BAD_REQUEST, {"status": "error", "category": "invalid_request"})
                return
            result = operator.step(payload)
            status = HTTPStatus.OK if result.get("status") == "ok" else HTTPStatus.UNPROCESSABLE_ENTITY
            self._json(status, result)

    return ThreadingHTTPServer((host, port), Handler)
