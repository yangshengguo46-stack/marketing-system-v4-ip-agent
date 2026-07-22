#!/usr/bin/env python3
"""Run MediaKit/FFmpeg without a shell and emit a verified media receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import mimetypes
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

CONTRACT_VERSION = "personal-ip-media-execution-v1"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sanitized_source_ref(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("output source cannot contain URL credentials")
    if parsed.scheme not in {"http", "https", "mediakit", "mock"}:
        raise ValueError("output source must use http, https, mediakit or mock")
    if not parsed.netloc:
        raise ValueError("output source must include a host or provider namespace")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _artifact(path: str, *, source_ref: str | None = None, downloaded_at: str | None = None) -> dict[str, Any]:
    resolved = Path(path).resolve()
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    result = {
        "ref": resolved.as_uri(),
        "sha256": digest.hexdigest(),
        "size_bytes": resolved.stat().st_size,
        "mime_type": mimetypes.guess_type(resolved.name)[0] or "application/octet-stream",
    }
    if source_ref is not None:
        result["source_ref"] = _sanitized_source_ref(source_ref)
        result["downloaded_at"] = downloaded_at or _utc_now()
    return result


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


def _cost(
    *,
    status: str,
    amount: float | None,
    currency: str | None,
    basis: str | None,
    unknown_reason: str,
) -> dict[str, Any]:
    if status == "unknown":
        reason = " ".join(unknown_reason.split())
        if not reason:
            raise ValueError("unknown cost requires a reason")
        return {"status": "unknown", "reason": reason}
    if status not in {"known", "estimated"}:
        raise ValueError("cost_status must be known, estimated or unknown")
    if isinstance(amount, bool) or amount is None or not math.isfinite(amount) or amount < 0:
        raise ValueError("known or estimated cost requires a non-negative amount")
    currency_value = str(currency or "").strip().upper()
    if not currency_value:
        raise ValueError("known or estimated cost requires a currency")
    result: dict[str, Any] = {"status": status, "amount": amount, "currency": currency_value}
    if basis:
        result["basis"] = " ".join(basis.split())
    return result


def _path_from_file_ref(value: str) -> Path:
    parsed = urlsplit(value)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise ValueError("resumable output ref must be a local file URI")
    return Path(unquote(parsed.path)).resolve()


def _load_resumable_receipt(
    receipt_file: str,
    *,
    provider: str,
    executor: str,
    capability: str,
    model: str | None,
    job_kind: str,
    attempt: int,
    retry_of: str | None,
    input_files: list[str],
    output_files: list[str],
    output_sources: list[str],
) -> dict[str, Any] | None:
    target = Path(receipt_file).resolve()
    if not target.is_file():
        return None
    try:
        receipt = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("existing receipt cannot be resumed") from exc
    if receipt.get("contract_version") != CONTRACT_VERSION or receipt.get("status") != "succeeded":
        raise ValueError("existing receipt is not a resumable succeeded execution; use a new receipt file for a retry")
    expected_identity = (provider.strip(), executor.strip(), capability, model.strip() if model else None)
    actual_identity = (receipt.get("provider"), receipt.get("executor"), receipt.get("capability"), receipt.get("model"))
    if actual_identity != expected_identity:
        raise ValueError("existing receipt belongs to a different executor request")
    parameters = receipt.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("existing receipt has invalid executor parameters")
    expected_retry_of = " ".join(retry_of.split()) if retry_of else None
    if (parameters.get("job_kind"), parameters.get("attempt"), parameters.get("retry_of")) != (job_kind, attempt, expected_retry_of):
        raise ValueError("existing receipt belongs to a different executor attempt")
    inputs = receipt.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != len(input_files):
        raise ValueError("existing receipt inputs do not match the declared inputs")
    expected_input_paths = [Path(path).resolve() for path in input_files]
    actual_input_paths = [_path_from_file_ref(str(item.get("ref") or "")) for item in inputs if isinstance(item, dict)]
    if actual_input_paths != expected_input_paths:
        raise ValueError("existing receipt inputs do not match the declared inputs")
    for item, path in zip(inputs, actual_input_paths, strict=True):
        current = _artifact(str(path)) if path.is_file() else None
        if current is None or item.get("size_bytes") != current["size_bytes"] or item.get("sha256") != current["sha256"]:
            raise ValueError("existing receipt input verification failed")
    outputs = receipt.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != len(output_files):
        raise ValueError("existing receipt outputs do not match the declared outputs")
    expected_paths = [Path(path).resolve() for path in output_files]
    actual_paths = [_path_from_file_ref(str(item.get("ref") or "")) for item in outputs if isinstance(item, dict)]
    if actual_paths != expected_paths:
        raise ValueError("existing receipt outputs do not match the declared outputs")
    for item, path in zip(outputs, actual_paths, strict=True):
        current = _artifact(str(path)) if path.is_file() else None
        if current is None or item.get("size_bytes") != current["size_bytes"] or item.get("sha256") != current["sha256"]:
            raise ValueError("existing receipt output verification failed")
    if output_sources:
        actual_sources = [item.get("source_ref") for item in outputs]
        expected_sources = [_sanitized_source_ref(source) for source in output_sources]
        if actual_sources != expected_sources:
            raise ValueError("existing receipt download sources do not match the declared outputs")
    return receipt


def run_media_executor(
    *,
    command: list[str],
    input_files: list[str],
    output_files: list[str],
    output_sources: list[str] | None = None,
    receipt_file: str,
    provider: str,
    executor: str,
    model: str | None = None,
    capability: str = "media_processing",
    job_kind: str = "media_processing",
    status_mode: str = "succeeded",
    task_id: str | None = None,
    request_id: str | None = None,
    attempt: int = 1,
    retry_of: str | None = None,
    resume: bool = False,
    failure_category: str = "executor_failed",
    failure_retryable: bool = False,
    cost_status: str = "unknown",
    cost_amount: float | None = None,
    cost_currency: str | None = None,
    cost_basis: str | None = None,
    cost_unknown_reason: str = "executor billing API is not connected",
) -> dict[str, Any]:
    """Execute one command and write a credential-free immutable receipt."""

    if not command:
        raise ValueError("command is required")
    if not provider.strip() or not executor.strip():
        raise ValueError("provider and executor are required")
    if status_mode not in {"succeeded", "running"}:
        raise ValueError("status_mode must be succeeded or running")
    if capability not in {"image_generation", "video_generation", "speech_generation", "media_processing"}:
        raise ValueError("unsupported media execution capability")
    if isinstance(attempt, bool) or attempt < 1:
        raise ValueError("attempt must be a positive integer")
    sources = list(output_sources or [])
    if sources and len(sources) != len(output_files):
        raise ValueError("output_sources must align with output_files")
    receipt_target = Path(receipt_file).resolve()
    if receipt_target.exists() and not resume:
        raise ValueError("receipt already exists; use --resume for a succeeded execution or a new receipt file for a retry")
    if resume:
        replay = _load_resumable_receipt(
            receipt_file,
            provider=provider,
            executor=executor,
            capability=capability,
            model=model,
            job_kind=job_kind,
            attempt=attempt,
            retry_of=retry_of,
            input_files=input_files,
            output_files=output_files,
            output_sources=sources,
        )
        if replay is not None:
            return replay
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
    resolved_request_id = request_id or _find_identifier(parsed, {"request_id", "requestid"})
    base = {
        "contract_version": CONTRACT_VERSION,
        "capability": capability,
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
            "attempt": attempt,
            "retry_of": " ".join(retry_of.split()) if retry_of else None,
        },
        "inputs": inputs,
        "cost": _cost(
            status=cost_status,
            amount=cost_amount,
            currency=cost_currency,
            basis=cost_basis,
            unknown_reason=cost_unknown_reason,
        ),
    }
    if completed.returncode != 0:
        receipt = {
            **base,
            "status": "failed",
            "outputs": [],
            "failure": {
                "category": failure_category,
                "message": f"executor exited with code {completed.returncode}",
                "retryable": failure_retryable,
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
    missing = [str(Path(path).resolve()) for path in output_files if not Path(path).resolve().is_file()]
    if not output_files or missing:
        receipt = {
            **base,
            "status": "failed",
            "outputs": [],
            "failure": {
                "category": "missing_output",
                "message": (f"executor did not create {len(missing)} declared output file(s)" if output_files else "synchronous executor declared no output files"),
                "retryable": False,
            },
        }
        _write_receipt(receipt_file, receipt)
        raise RuntimeError(receipt["failure"]["message"])
    receipt = {
        **base,
        "status": "succeeded",
        "outputs": [
            _artifact(
                path,
                source_ref=sources[index] if sources else None,
                downloaded_at=_utc_now() if sources else None,
            )
            for index, path in enumerate(output_files)
        ],
    }
    _write_receipt(receipt_file, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", default=[], dest="input_files")
    parser.add_argument("--output", action="append", default=[], dest="output_files")
    parser.add_argument("--output-source", action="append", default=[], dest="output_sources")
    parser.add_argument("--receipt-file", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--executor", required=True)
    parser.add_argument("--model")
    parser.add_argument(
        "--capability",
        choices=("image_generation", "video_generation", "speech_generation", "media_processing"),
        default="media_processing",
    )
    parser.add_argument("--job-kind", default="media_processing")
    parser.add_argument("--status-mode", choices=("succeeded", "running"), default="succeeded")
    parser.add_argument("--task-id")
    parser.add_argument("--request-id")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--retry-of")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--failure-category", default="executor_failed")
    parser.add_argument("--failure-retryable", action="store_true")
    parser.add_argument("--cost-status", choices=("known", "estimated", "unknown"), default="unknown")
    parser.add_argument("--cost-amount", type=float)
    parser.add_argument("--cost-currency")
    parser.add_argument("--cost-basis")
    parser.add_argument("--cost-unknown-reason", default="executor billing API is not connected")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        receipt = run_media_executor(
            command=command,
            input_files=args.input_files,
            output_files=args.output_files,
            output_sources=args.output_sources,
            receipt_file=args.receipt_file,
            provider=args.provider,
            executor=args.executor,
            model=args.model,
            capability=args.capability,
            job_kind=args.job_kind,
            status_mode=args.status_mode,
            task_id=args.task_id,
            request_id=args.request_id,
            attempt=args.attempt,
            retry_of=args.retry_of,
            resume=args.resume,
            failure_category=args.failure_category,
            failure_retryable=args.failure_retryable,
            cost_status=args.cost_status,
            cost_amount=args.cost_amount,
            cost_currency=args.cost_currency,
            cost_basis=args.cost_basis,
            cost_unknown_reason=args.cost_unknown_reason,
        )
    except Exception as exc:
        print(f"Media executor failed: {exc}")
        return 1
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
