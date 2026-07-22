from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from PIL import Image

from deerflow.community.ui_tars.client import UITarsOperatorClient
from deerflow.community.ui_tars.privacy import (
    contains_secret_material,
    high_impact_categories,
    pixelate_png,
    sanitize_mapping,
    sanitize_text,
)
from deerflow.community.ui_tars.service import (
    UITarsServiceError,
    UITarsSingleStepService,
    parse_ui_tars_action,
)
from deerflow.community.ui_tars.source import verify_vendored_ui_tars
from deerflow.config.app_config import AppConfig
from deerflow.config.ui_tars_config import UITarsConfig
from deerflow.tools.builtins import ui_tars_tools
from deerflow.tools.tools import get_available_tools


def _png() -> bytes:
    from io import BytesIO

    image = Image.new("RGB", (240, 120), "white")
    for x in range(20, 220):
        image.putpixel((x, 50), (x % 255, 20, 90))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class FakeDesktop:
    def __init__(self) -> None:
        self.captures = 0
        self.actions: list[dict] = []

    def capture_png(self) -> bytes:
        self.captures += 1
        return _png()

    def execute(self, action: dict, *, width: int, height: int) -> str:
        self.actions.append({"action": action, "width": width, "height": height})
        return "executed"


class FakeModel:
    def __init__(self, prediction: str = "click(start_box='[400,400,600,600]')") -> None:
        self.prediction = prediction
        self.calls: list[dict] = []

    def predict(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return self.prediction


def _config(**updates) -> UITarsConfig:
    return UITarsConfig(
        enabled=True,
        endpoint="http://127.0.0.1:9137",
        model="ui-tars-fixture",
        api_base="http://127.0.0.1:9999/v1",
        pixelation_block_size=24,
        **updates,
    )


def test_vendored_source_pin_is_complete_and_has_no_binary_payload() -> None:
    manifest = verify_vendored_ui_tars()
    assert manifest["upstream_commit"] == "c2ad42e3eb9b27830db41a3e6f51ca7179d9b168"
    assert manifest["package_version"] == "1.2.3"
    assert manifest["license"] == "Apache-2.0"
    assert manifest["source_mode"] == "selected-upstream-source-no-prebuilt-binaries"
    source_root = Path(manifest["source_root"])
    assert not any(path.suffix in {".dll", ".dylib", ".exe", ".node", ".so"} for path in source_root.rglob("*"))


def test_ui_tars_config_is_default_off_and_loopback_only() -> None:
    config = UITarsConfig()
    assert config.enabled is False
    assert config.screenshot_privacy == "pixelated"
    with pytest.raises(ValueError, match="loopback"):
        UITarsConfig(endpoint="https://operator.example.com")
    with pytest.raises(ValueError, match="HTTPS"):
        UITarsConfig(api_base="http://model.example.com/v1")


def test_privacy_redacts_credentials_queries_and_pixelates() -> None:
    text = sanitize_text("Bearer abcdefghijklmnop https://example.com/path?token=raw password=hunter2")
    assert "abcdefghijklmnop" not in text
    assert "token=raw" not in text
    assert "hunter2" not in text
    assert contains_secret_material("api_key=abcdefghijklmnop") is True
    assert high_impact_categories("publish this and pay now") == ["publish_or_send", "payment"]
    sanitized = sanitize_mapping({"cookie": "raw", "nested": {"profile_path": "/secret", "ok": "yes"}})
    assert sanitized == {"nested": {"ok": "yes"}}
    transformed, width, height = pixelate_png(_png(), block_size=24)
    assert (width, height) == (240, 120)
    assert transformed != _png()


def test_action_parser_accepts_upstream_format_and_rejects_unknown() -> None:
    assert parse_ui_tars_action("Thought: hidden\nAction: click(start_box='[1,2,3,4]')") == {
        "type": "click",
        "inputs": {"start_box": "[1,2,3,4]"},
    }
    assert parse_ui_tars_action("type(content='hello, world')")["inputs"]["content"] == "hello, world"
    with pytest.raises(UITarsServiceError, match="outside"):
        parse_ui_tars_action("delete_everything()")


def test_single_step_service_writes_only_transformed_evidence_and_receipt(tmp_path: Path) -> None:
    backend = FakeDesktop()
    model = FakeModel()
    state_dir = tmp_path / "ui-tars"
    service = UITarsSingleStepService(_config(), state_dir=state_dir, backend=backend, model_client=model)

    result = service.step(
        {
            "intent": "click the local preview button",
            "target_app": "Preview",
            "target_window": "Draft",
            "task_id": "run-1",
            "fallback_reason": "native_desktop_required",
            "approved": False,
        }
    )

    assert result["status"] == "ok"
    assert backend.captures == 1
    assert len(backend.actions) == 1
    assert len(model.calls) == 1
    assert model.calls[0]["screenshot_png"] != _png()
    receipt = result["receipt"]
    assert receipt["task_id"] == "run-1"
    assert receipt["model_id"] == "ui-tars-fixture"
    assert receipt["evidence"]["privacy"] == "whole_screen_pixelated_no_raw_text"
    assert not Path(receipt["evidence"]["ref"]).is_absolute()
    assert (state_dir / "evidence" / Path(receipt["evidence"]["ref"]).name).is_file()
    audit = (state_dir / "audit" / "receipts.jsonl").read_text(encoding="utf-8")
    assert "Bearer" not in audit and "profile_path" not in audit


def test_single_step_service_blocks_secrets_and_unapproved_impact_without_capture(tmp_path: Path) -> None:
    backend = FakeDesktop()
    service = UITarsSingleStepService(_config(), state_dir=tmp_path / "ui-tars", backend=backend, model_client=FakeModel())
    secret = service.step(
        {
            "intent": "type password=hunter2",
            "target_app": "App",
            "task_id": "run-secret",
            "fallback_reason": "native_desktop_required",
        }
    )
    publish = service.step(
        {
            "intent": "publish the post",
            "target_app": "App",
            "task_id": "run-publish",
            "fallback_reason": "browser_action_failed",
            "approved": False,
        }
    )
    assert secret["category"] == "sensitive_input_blocked"
    assert publish["category"] == "approval_required"
    assert backend.captures == 0


def test_single_step_service_fails_closed_before_capture_when_model_is_missing(tmp_path: Path) -> None:
    backend = FakeDesktop()
    service = UITarsSingleStepService(
        UITarsConfig(enabled=True),
        state_dir=tmp_path / "ui-tars",
        backend=backend,
        model_client=FakeModel(),
    )

    result = service.step(
        {
            "intent": "click the local preview button",
            "target_app": "Preview",
            "task_id": "run-missing-model",
            "fallback_reason": "native_desktop_required",
        }
    )

    assert result["category"] == "model_configuration"
    assert backend.captures == 0


def test_single_step_service_records_unexpected_capture_failure(tmp_path: Path) -> None:
    class BrokenDesktop(FakeDesktop):
        def capture_png(self) -> bytes:
            raise OSError("fixture raw failure must not enter the receipt")

    state_dir = tmp_path / "ui-tars"
    service = UITarsSingleStepService(_config(), state_dir=state_dir, backend=BrokenDesktop(), model_client=FakeModel())

    result = service.step(
        {
            "intent": "inspect the local preview",
            "target_app": "Preview",
            "task_id": "run-failure",
            "fallback_reason": "native_desktop_required",
        }
    )

    assert result["category"] == "internal_error"
    assert "fixture raw failure" not in json.dumps(result)
    assert "internal_error" in (state_dir / "audit" / "receipts.jsonl").read_text(encoding="utf-8")


def test_operator_client_accepts_connect_mode_token_from_environment(monkeypatch, tmp_path: Path) -> None:
    token = "fixture-token-with-more-than-thirty-two-characters"
    monkeypatch.setenv("UI_TARS_OPERATOR_TOKEN", token)
    client = UITarsOperatorClient("http://127.0.0.1:9137", timeout_seconds=1, state_dir=tmp_path)
    assert client._token() == token  # noqa: SLF001 - token-source contract


class FakeOperatorClient:
    payloads: list[dict] = []

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def step(self, payload: dict) -> dict:
        self.payloads.append(payload)
        return {"status": "ok", "receipt": {"result": "executed"}}


def _runtime(messages: list | None = None):
    return SimpleNamespace(state={"messages": messages or []}, context={"user_id": "owner-1", "thread_id": "thread-1"})


@pytest.mark.asyncio
async def test_native_tool_requires_structured_risk_confirmation(monkeypatch, tmp_path: Path) -> None:
    config = _config()
    monkeypatch.setattr(ui_tars_tools, "get_app_config", lambda: SimpleNamespace(ui_tars=config))
    monkeypatch.setattr(ui_tars_tools, "UITarsOperatorClient", FakeOperatorClient)
    monkeypatch.setattr(ui_tars_tools, "append_receipt", lambda _receipt: "ui-tars/audit/fixture.jsonl")
    request_id = "risk-1"
    request = ToolMessage(
        content="confirm",
        tool_call_id="call-1",
        artifact={
            "human_input": {
                "source": "ask_clarification",
                "request_id": request_id,
                "clarification_type": "risk_confirmation",
            }
        },
    )
    response = HumanMessage(
        content="approved",
        additional_kwargs={
            "human_input_response": {
                "version": 1,
                "kind": "human_input_response",
                "source": "web",
                "request_id": request_id,
                "response_kind": "option",
                "option_id": "option-1",
                "value": "approve",
            }
        },
    )
    browser_call = AIMessage(
        content="",
        tool_calls=[{"name": "browser_click", "args": {"ref": 7}, "id": "browser-1", "type": "tool_call"}],
    )
    browser_failure = ToolMessage(content="Error: fixture control was not clickable", tool_call_id="browser-1", status="error")

    denied = json.loads(
        await ui_tars_tools._ui_tars_desktop_step(
            _runtime([browser_call, browser_failure]),
            "publish the draft",
            "Browser",
            "Editor",
            "run-2",
            "browser_action_failed",
            "",
            "",
        )
    )
    allowed = json.loads(
        await ui_tars_tools._ui_tars_desktop_step(
            _runtime([browser_call, browser_failure, request, response]),
            "publish the draft",
            "Browser",
            "Editor",
            "run-2",
            "browser_action_failed",
            "",
            request_id,
        )
    )
    assert denied["category"] == "approval_required"
    assert allowed["status"] == "ok"
    assert FakeOperatorClient.payloads[-1]["approved"] is True


@pytest.mark.asyncio
async def test_native_tool_requires_observed_browser_control_before_web_fallback(monkeypatch) -> None:
    config = _config()
    monkeypatch.setattr(ui_tars_tools, "get_app_config", lambda: SimpleNamespace(ui_tars=config))
    monkeypatch.setattr(ui_tars_tools, "UITarsOperatorClient", FakeOperatorClient)
    monkeypatch.setattr(ui_tars_tools, "append_receipt", lambda _receipt: "ui-tars/audit/fixture.jsonl")

    no_browser = json.loads(
        await ui_tars_tools._ui_tars_desktop_step(
            _runtime(),
            "inspect a visual web control",
            "Browser",
            "Editor",
            "run-browser-policy",
            "browser_dom_unavailable",
            "",
            "",
        )
    )
    browser_call = AIMessage(
        content="",
        tool_calls=[{"name": "browser_snapshot", "args": {}, "id": "browser-2", "type": "tool_call"}],
    )
    browser_result = ToolMessage(content="No DOM control matched the visual canvas", tool_call_id="browser-2")
    observed = json.loads(
        await ui_tars_tools._ui_tars_desktop_step(
            _runtime([browser_call, browser_result]),
            "inspect a visual web control",
            "Browser",
            "Editor",
            "run-browser-policy",
            "browser_dom_unavailable",
            "",
            "",
        )
    )

    assert no_browser["category"] == "browser_control_required"
    assert observed["status"] == "ok"


def test_tool_registration_is_config_gated() -> None:
    base = {"sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"}}
    disabled = AppConfig.model_validate(base)
    enabled = AppConfig.model_validate({**base, "ui_tars": {"enabled": True}})
    assert "ui_tars_desktop_step" not in {item.name for item in get_available_tools(app_config=disabled, include_mcp=False)}
    assert "ui_tars_desktop_step" in {item.name for item in get_available_tools(app_config=enabled, include_mcp=False)}
