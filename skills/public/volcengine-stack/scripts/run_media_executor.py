#!/usr/bin/env python3
"""Run MediaKit/FFmpeg without a shell and emit a verified media receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "personal-ip-media-execution-v1"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _artifact(path: str) -> dict[str, Any]:
    resolved = Path(path).resolve()
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "ref": resolved.as_uri(),
        "sha256": digest.hexdigest(),
        "size_bytes": resolved.stat().st_size,
        "mime_type": mimetypes.guess_type(resolved.name)[0]
        or "application/octet-stream",
    }


def _write_receipt(path: str, receipt: dict[str, Any]) -> None:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, target)


def _parse_json_output(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return None
    candidates = [
        text,
        *reversed([line.strip() for line in text.splitlines() if line.strip()]),
    ]
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return None


def _find_identifier(value: Any, names: set[str]) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in names and item is not None and item != "":
                return str(item)
        for item in value.values():
            found = _find_identifier(item, names)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_identifier(item, names)
            if found:
                return found
    return None


def run_media_executor(
    *,
    command: list[str],
    input_files: list[str],
    output_files: list[str],
    receipt_file: str,
    provider: str,
    executor: str,
    model: str | None = None,
    job_kind: str = "media_processing",
    status_mode: str = "succeeded",
    task_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute one command and write a credential-free immutable receipt."""

    if not command:
        raise ValueError("command is required")
    if not provider.strip() or not executor.strip():
        raise ValueError("provider and executor are required")
    if status_mode not in {"succeeded", "running"}:
        raise ValueError("status_mode must be succeeded or running")
    started_at = _utc_now()
    inputs = [_artifact(path) for path in input_files]
    environment = os.environ.copy()
    if "mediakit" in executor.lower():
        environment["MEDIAKIT_SURFACE"] = "skill"
        environment["MEDIAKIT_RUNTIME"] = "deerflow"
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    parsed = _parse_json_output(completed.stdout)
    resolved_task_id = task_id or _find_identifier(parsed, {"task_id", "taskid"})
    resolved_request_id = request_id or _find_identifier(
        parsed, {"request_id", "requestid"}
    )
    base = {
        "contract_version": CONTRACT_VERSION,
        "capability": "media_processing",
        "provider": provider.strip(),
        "executor": executor.strip(),
        "model": model.strip() if model else None,
        "task_id": resolved_task_id,
        "request_id": resolved_request_id,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "parameters": {
            "job_kind": job_kind,
            "command": Path(command[0]).name,
            "argument_count": max(0, len(command) - 1),
        },
        "inputs": inputs,
        "cost": {
            "status": "unknown",
            "reason": "executor billing API is not connected",
        },
    }
    if completed.returncode != 0:
        receipt = {
            **base,
            "status": "failed",
            "outputs": [],
            "failure": {
                "category": "executor_failed",
                "message": f"executor exited with code {completed.returncode}",
                "retryable": False,
            },
        }
        _write_receipt(receipt_file, receipt)
        raise RuntimeError(receipt["failure"]["message"])
    if status_mode == "running":
        if not (resolved_task_id or resolved_request_id):
            receipt = {
                **base,
                "status": "failed",
                "outputs": [],
                "failure": {
                    "category": "missing_provider_identifier",
                    "message": "asynchronous executor returned no task or request id",
                    "retryable": False,
                },
            }
            _write_receipt(receipt_file, receipt)
            raise RuntimeError(receipt["failure"]["message"])
        receipt = {**base, "status": "running", "completed_at": None, "outputs": []}
        _write_receipt(receipt_file, receipt)
        return receipt
    missing = [
        str(Path(path).resolve())
        for path in output_files
        if not Path(path).resolve().is_file()
    ]
    if not output_files or missing:
        receipt = {
            **base,
            "status": "failed",
            "outputs": [],
            "failure": {
                "category": "missing_output",
                "message": (
                    f"executor did not create {len(missing)} declared output file(s)"
                    if output_files
                    else "synchronous executor declared no output files"
                ),
                "retryable": False,
            },
        }
        _write_receipt(receipt_file, receipt)
        raise RuntimeError(receipt["failure"]["message"])
    receipt = {
        **base,
        "status": "succeeded",
        "outputs": [_artifact(path) for path in output_files],
    }
    _write_receipt(receipt_file, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", default=[], dest="input_files")
    parser.add_argument("--output", action="append", default=[], dest="output_files")
    parser.add_argument("--receipt-file", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--executor", required=True)
    parser.add_argument("--model")
    parser.add_argument("--job-kind", default="media_processing")
    parser.add_argument(
        "--status-mode", choices=("succeeded", "running"), default="succeeded"
    )
    parser.add_argument("--task-id")
    parser.add_argument("--request-id")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        receipt = run_media_executor(
            command=command,
            input_files=args.input_files,
            output_files=args.output_files,
            receipt_file=args.receipt_file,
            provider=args.provider,
            executor=args.executor,
            model=args.model,
            job_kind=args.job_kind,
            status_mode=args.status_mode,
            task_id=args.task_id,
            request_id=args.request_id,
        )
    except Exception as exc:
        print(f"Media executor failed: {exc}")
        return 1
    print(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
