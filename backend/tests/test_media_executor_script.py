from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "skills" / "public" / "volcengine-stack" / "scripts" / "run_media_executor.py"
SPEC = importlib.util.spec_from_file_location("personal_ip_run_media_executor", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_media_executor_records_known_cost_download_and_resumes_verified_success(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.bin"
    output = tmp_path / "output.bin"
    receipt_path = tmp_path / "receipt.json"
    source.write_bytes(b"input")
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        output.write_bytes(b"downloaded-output")
        return MODULE.subprocess.CompletedProcess(command, 0, stdout='{"request_id":"request-1"}', stderr="")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    receipt = MODULE.run_media_executor(
        command=["fake-executor"],
        input_files=[str(source)],
        output_files=[str(output)],
        output_sources=["https://example.com/output.bin?signature=secret"],
        receipt_file=str(receipt_path),
        provider="local-mock",
        executor="fake-executor",
        capability="image_generation",
        job_kind="asset_generation",
        request_id=None,
        attempt=2,
        retry_of="asset-1:attempt-1",
        cost_status="known",
        cost_amount=0,
        cost_currency="CNY",
        cost_basis="local acceptance",
    )
    replay = MODULE.run_media_executor(
        command=["must-not-run"],
        input_files=[str(source)],
        output_files=[str(output)],
        output_sources=["https://example.com/output.bin?signature=secret"],
        receipt_file=str(receipt_path),
        provider="local-mock",
        executor="fake-executor",
        capability="image_generation",
        job_kind="asset_generation",
        attempt=2,
        retry_of="asset-1:attempt-1",
        resume=True,
        cost_status="known",
        cost_amount=0,
        cost_currency="CNY",
        cost_basis="local acceptance",
    )

    assert receipt["request_id"] == "request-1"
    assert receipt["parameters"]["attempt"] == 2
    assert receipt["parameters"]["retry_of"] == "asset-1:attempt-1"
    assert receipt["outputs"][0]["source_ref"] == "https://example.com/output.bin"
    assert receipt["cost"] == {"status": "known", "amount": 0, "currency": "CNY", "basis": "local acceptance"}
    assert replay == receipt
    assert calls == [["fake-executor"]]


def test_media_executor_refuses_overwrite_and_tampered_resume_input(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.bin"
    output = tmp_path / "output.bin"
    receipt_path = tmp_path / "receipt.json"
    source.write_bytes(b"input-v1")

    def fake_run(command, **_kwargs):
        output.write_bytes(b"output-v1")
        return MODULE.subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    kwargs = {
        "command": ["fake-executor"],
        "input_files": [str(source)],
        "output_files": [str(output)],
        "receipt_file": str(receipt_path),
        "provider": "local-mock",
        "executor": "fake-executor",
    }
    MODULE.run_media_executor(**kwargs)

    with pytest.raises(ValueError, match="receipt already exists"):
        MODULE.run_media_executor(**kwargs)

    source.write_bytes(b"input-v2")
    with pytest.raises(ValueError, match="input verification"):
        MODULE.run_media_executor(**kwargs, resume=True)


def test_paid_checkpoints_are_written_without_executing_provider_calls(tmp_path) -> None:
    runner = SCRIPT_PATH.parents[4] / "scripts" / "personal_ip_video_e2e.py"
    completed = subprocess.run(
        [sys.executable, str(runner), "paid-checkpoints", "--work-dir", str(tmp_path)],
        cwd=SCRIPT_PATH.parents[4] / "backend",
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads((tmp_path / "paid-checkpoints.json").read_text(encoding="utf-8"))
    assert payload["executed"] is False
    assert payload["call_count"] == 4
    assert {item["stage"] for item in payload["checkpoints"]} == {
        "seedream",
        "seedance",
        "speech",
        "mediakit-cloud-submit",
    }
    assert all(item["requires_explicit_user_approval"] is True for item in payload["checkpoints"])
