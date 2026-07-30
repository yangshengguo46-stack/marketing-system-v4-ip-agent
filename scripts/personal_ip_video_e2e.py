#!/usr/bin/env python3
"""Run or resume a receipt-backed Personal-IP video acceptance production."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "backend" / "packages" / "harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from deerflow.config.database_config import DatabaseConfig  # noqa: E402
from deerflow.persistence.engine import (  # noqa: E402
    close_engine,
    get_session_factory,
    init_engine_from_config,
)
from deerflow.persistence.personal_ip_video_productions import (  # noqa: E402
    PersonalIPVideoProductionRepository,
)
from deerflow.personal_ip.media_execution import normalize_media_execution_receipt  # noqa: E402
from deerflow.personal_ip.video_acceptance import (  # noqa: E402
    artifact_for_path,
    run_delivery_qa,
    verify_local_receipt_outputs,
)

MEDIA_EXECUTOR = (
    ROOT
    / "skills"
    / "public"
    / "volcengine-stack"
    / "scripts"
    / "run_media_executor.py"
)
PROJECT_MEDIAKIT = (
    ROOT
    / ".deer-flow"
    / "bin"
    / ("mediakit-cli.exe" if os.name == "nt" else "mediakit-cli")
)
PROJECT_FFMPEG_DIR = ROOT / ".deer-flow" / "toolchains" / "ffmpeg" / "bin"
KNOWN_ZERO_COST = {
    "status": "known",
    "amount": 0,
    "currency": "CNY",
    "basis": "local acceptance execution",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_json_once(path: Path, value: Any) -> None:
    serialized = _canonical_json(value)
    if path.is_file():
        if path.read_text(encoding="utf-8") != serialized:
            raise RuntimeError(f"recoverable acceptance input changed: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(serialized, encoding="utf-8")
    os.replace(temporary, path)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object: {path}")
    return value


def _tool_path(explicit: str | None, project_name: str, system_name: str) -> str:
    if explicit:
        path = Path(explicit).resolve()
        if not path.is_file():
            raise RuntimeError(f"media tool not found: {path}")
        return str(path)
    project = PROJECT_FFMPEG_DIR / project_name
    if project.is_file():
        return str(project)
    resolved = shutil.which(system_name)
    if resolved:
        return resolved
    raise RuntimeError(f"{system_name} is required; run make ffmpeg-toolchain")


def _executor_environment(ffmpeg: str) -> dict[str, str]:
    environment = os.environ.copy()
    ffmpeg_dir = str(Path(ffmpeg).resolve().parent)
    environment["PATH"] = os.pathsep.join([ffmpeg_dir, environment.get("PATH", "")])
    return environment


def _run_receipt_command(
    *,
    receipt_file: Path,
    input_files: list[Path],
    output_files: list[Path],
    output_sources: list[str],
    provider: str,
    executor: str,
    capability: str,
    job_kind: str,
    command: list[str],
    environment: dict[str, str],
    task_id: str | None = None,
    request_id: str | None = None,
    attempt: int = 1,
    retry_of: str | None = None,
    expect_failure: bool = False,
) -> dict[str, Any]:
    if receipt_file.is_file():
        existing = _load_json(receipt_file)
        if existing.get("status") == "failed":
            if not expect_failure:
                raise RuntimeError(
                    f"failed receipt requires a new retry receipt: {receipt_file}"
                )
            return existing
    argv = [
        sys.executable,
        str(MEDIA_EXECUTOR),
        *[item for path in input_files for item in ("--input", str(path))],
        *[item for path in output_files for item in ("--output", str(path))],
        *[item for source in output_sources for item in ("--output-source", source)],
        "--receipt-file",
        str(receipt_file),
        "--provider",
        provider,
        "--executor",
        executor,
        "--capability",
        capability,
        "--job-kind",
        job_kind,
        "--attempt",
        str(attempt),
    ]
    if task_id:
        argv.extend(["--task-id", task_id])
    if request_id:
        argv.extend(["--request-id", request_id])
    if retry_of:
        argv.extend(["--retry-of", retry_of])
    if expect_failure:
        argv.extend(
            [
                "--failure-category",
                "simulated_provider_timeout",
                "--failure-retryable",
                "--cost-status",
                "unknown",
                "--cost-unknown-reason",
                "simulated provider billing is unavailable",
            ]
        )
    else:
        argv.extend(
            [
                "--cost-status",
                "known",
                "--cost-amount",
                "0",
                "--cost-currency",
                "CNY",
                "--cost-basis",
                "local acceptance execution",
            ]
        )
    if receipt_file.is_file():
        argv.append("--resume")
    argv.extend(["--", *command])
    completed = subprocess.run(
        argv, cwd=ROOT, env=environment, capture_output=True, text=True, check=False
    )
    if expect_failure:
        if completed.returncode == 0:
            raise RuntimeError("simulated failed attempt unexpectedly succeeded")
    elif completed.returncode != 0:
        raise RuntimeError(
            f"media executor failed: {(completed.stdout or completed.stderr).strip()[:1_000]}"
        )
    receipt = _load_json(receipt_file)
    if not expect_failure:
        verify_local_receipt_outputs(receipt)
    return receipt


async def _append_business_event(
    repository: PersonalIPVideoProductionRepository,
    production_id: str,
    *,
    owner_user_id: str,
    event_key: str,
    event_type: str,
    status: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    input_refs: list[str],
    output_refs: list[str],
    provider: str = "deerflow-local-acceptance",
) -> dict[str, Any]:
    result = await repository.append_event(
        production_id,
        owner_user_id=owner_user_id,
        event_key=event_key,
        event_type=event_type,
        status=status,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        input_refs=input_refs,
        output_refs=output_refs,
        provider=provider,
        model=None,
        provider_task_id=None,
        cost=KNOWN_ZERO_COST,
    )
    if result is None:
        raise RuntimeError("video production disappeared while appending an event")
    return result


async def _ingest_receipt(
    repository: PersonalIPVideoProductionRepository,
    production_id: str,
    *,
    owner_user_id: str,
    event_key: str,
    entity_type: str,
    entity_id: str,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_media_execution_receipt(receipt, entity_type=entity_type)
    result = await repository.append_event(
        production_id,
        owner_user_id=owner_user_id,
        event_key=event_key,
        event_type=normalized["event_type"],
        status=normalized["event_status"],
        entity_type=entity_type,
        entity_id=entity_id,
        payload=normalized["payload"],
        input_refs=normalized["input_refs"],
        output_refs=normalized["output_refs"],
        provider=normalized["provider"],
        model=normalized["model"],
        provider_task_id=normalized["provider_task_id"],
        cost=normalized["cost"],
        occurred_at=normalized["occurred_at"],
    )
    if result is None:
        raise RuntimeError("video production disappeared while ingesting a receipt")
    return result


def _acceptance_documents(work_dir: Path) -> dict[str, Path]:
    inputs = work_dir / "inputs"
    paths = {
        "source": inputs / "source-script.json",
        "blueprint": inputs / "blueprint.json",
        "asset_prompt": inputs / "asset-prompt.json",
        "storyboard": inputs / "storyboard.json",
        "video_prompt": inputs / "video-prompt.json",
        "voice_script": inputs / "voice-script.json",
    }
    _write_json_once(
        paths["source"],
        {
            "title": "Agent receipt acceptance",
            "script": "A receipt card becomes a finished vertical video while every execution step remains auditable.",
        },
    )
    _write_json_once(
        paths["blueprint"],
        {
            "beats": ["script enters", "provider retry", "verified delivery"],
            "duration_seconds": 2,
            "aspect_ratio": "9:16",
        },
    )
    _write_json_once(
        paths["asset_prompt"],
        {
            "prompt": "A clean cobalt-blue receipt card on a dark studio background, centered, vertical composition",
            "style": "minimal cinematic product illustration",
            "negative_prompt": "text, watermark, logo",
        },
    )
    _write_json_once(
        paths["storyboard"],
        {
            "shots": [
                {
                    "id": "shot-01",
                    "duration_seconds": 2,
                    "description": "The blue receipt card moves forward while verification marks illuminate.",
                }
            ]
        },
    )
    _write_json_once(
        paths["video_prompt"],
        {
            "title": "Receipt acceptance shot",
            "subject": "blue receipt card",
            "camera": {"movement": "slow push in"},
            "duration_seconds": 2,
            "audio": [],
        },
    )
    _write_json_once(
        paths["voice_script"],
        {
            "title": "Receipt acceptance",
            "locale": "en",
            "lines": [
                {
                    "speaker": "male",
                    "paragraph": "Hello Deer. Every output is verified before delivery.",
                }
            ],
        },
    )
    return paths


async def _run_local(args: argparse.Namespace) -> dict[str, Any]:
    work_dir = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    documents = _acceptance_documents(work_dir)
    outputs = work_dir / "outputs"
    receipts = work_dir / "receipts"
    outputs.mkdir(exist_ok=True)
    receipts.mkdir(exist_ok=True)
    ffmpeg = _tool_path(
        args.ffmpeg, "ffmpeg.exe" if os.name == "nt" else "ffmpeg", "ffmpeg"
    )
    ffprobe = _tool_path(
        args.ffprobe, "ffprobe.exe" if os.name == "nt" else "ffprobe", "ffprobe"
    )
    environment = _executor_environment(ffmpeg)

    await init_engine_from_config(
        DatabaseConfig(backend="sqlite", sqlite_dir=str(work_dir / "ledger"))
    )
    session_factory = get_session_factory()
    if session_factory is None:
        raise RuntimeError("acceptance ledger is unavailable")
    repository = PersonalIPVideoProductionRepository(session_factory)
    source = _load_json(documents["source"])
    delivery_spec = {
        "aspect_ratio": "9:16",
        "duration_seconds": 2,
        "duration_tolerance_seconds": 0.25,
        "require_audio": True,
    }
    production = await repository.begin(
        owner_user_id=args.owner_user_id,
        operation_key=args.operation_key,
        title=source["title"],
        subject_id=None,
        target_account_ids=[],
        source_kind="script",
        source=source,
        delivery_spec=delivery_spec,
        provider_policy={
            "image": ["seedream"],
            "video": ["seedance"],
            "speech": ["doubao-speech"],
            "finishing": ["mediakit-cli", "ffmpeg"],
        },
        budget={
            "currency": "CNY",
            "paid_calls_require_explicit_approval": True,
            "local_acceptance_limit": 0,
        },
    )
    production_id = production["id"]
    source_ref = artifact_for_path(documents["source"])["ref"]
    blueprint_artifact = artifact_for_path(documents["blueprint"])
    await _append_business_event(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="blueprint:v1",
        event_type="blueprint_sealed",
        status="succeeded",
        entity_type="production",
        entity_id=production_id,
        payload={"artifact": blueprint_artifact},
        input_refs=[source_ref],
        output_refs=[blueprint_artifact["ref"]],
    )

    asset = outputs / "asset.png"
    asset_receipt = _run_receipt_command(
        receipt_file=receipts / "asset-attempt-1.json",
        input_files=[documents["asset_prompt"]],
        output_files=[asset],
        output_sources=["mock://seedream/tasks/mock-seedream-request-1/output"],
        provider="volcengine-simulated",
        executor="ffmpeg-local-seedream-simulator",
        capability="image_generation",
        job_kind="seedream_asset",
        command=[
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x246BFD:s=360x640",
            "-frames:v",
            "1",
            "-y",
            str(asset),
        ],
        environment=environment,
        request_id="mock-seedream-request-1",
    )
    await _ingest_receipt(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="asset-01:attempt-1",
        entity_type="scene",
        entity_id="asset-01",
        receipt=asset_receipt,
    )

    storyboard_artifact = artifact_for_path(documents["storyboard"])
    await _append_business_event(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="storyboard:v1",
        event_type="storyboard_sealed",
        status="succeeded",
        entity_type="production",
        entity_id=production_id,
        payload={"artifact": storyboard_artifact, "shot_count": 1},
        input_refs=[blueprint_artifact["ref"], asset_receipt["outputs"][0]["ref"]],
        output_refs=[storyboard_artifact["ref"]],
    )

    failed_shot_receipt = _run_receipt_command(
        receipt_file=receipts / "shot-01-attempt-1.json",
        input_files=[documents["video_prompt"], asset],
        output_files=[outputs / "shot-01-attempt-1.mp4"],
        output_sources=[],
        provider="volcengine-simulated",
        executor="seedance-timeout-simulator",
        capability="video_generation",
        job_kind="seedance_shot",
        command=[sys.executable, "-c", "raise SystemExit(75)"],
        environment=environment,
        task_id="mock-seedance-task-attempt-1",
        request_id="mock-seedance-request-attempt-1",
        attempt=1,
        expect_failure=True,
    )
    await _ingest_receipt(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="shot-01:attempt-1",
        entity_type="shot",
        entity_id="shot-01",
        receipt=failed_shot_receipt,
    )

    shot = outputs / "shot-01-attempt-2.mp4"
    shot_receipt = _run_receipt_command(
        receipt_file=receipts / "shot-01-attempt-2.json",
        input_files=[documents["video_prompt"], asset],
        output_files=[shot],
        output_sources=["mock://seedance/tasks/mock-seedance-task-attempt-2/output"],
        provider="volcengine-simulated",
        executor="ffmpeg-local-seedance-simulator",
        capability="video_generation",
        job_kind="seedance_shot",
        command=[
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x10182F:s=360x640:d=2:r=25",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(shot),
        ],
        environment=environment,
        task_id="mock-seedance-task-attempt-2",
        request_id="mock-seedance-request-attempt-2",
        attempt=2,
        retry_of="shot-01:attempt-1",
    )
    await _ingest_receipt(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="shot-01:attempt-2",
        entity_type="candidate",
        entity_id="shot-01:candidate-2",
        receipt=shot_receipt,
    )
    await _append_business_event(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="shot-01:consistency:v1",
        event_type="consistency_checked",
        status="succeeded",
        entity_type="candidate",
        entity_id="shot-01:candidate-2",
        payload={"checks": {"aspect_ratio": True, "reference_asset_present": True}},
        input_refs=[
            asset_receipt["outputs"][0]["ref"],
            shot_receipt["outputs"][0]["ref"],
        ],
        output_refs=[shot_receipt["outputs"][0]["ref"]],
    )
    await _append_business_event(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="shot-01:selection:v1",
        event_type="candidate_selected",
        status="succeeded",
        entity_type="candidate",
        entity_id="shot-01:candidate-2",
        payload={
            "selected": True,
            "reason": "only retry passed local consistency checks",
        },
        input_refs=[shot_receipt["outputs"][0]["ref"]],
        output_refs=[shot_receipt["outputs"][0]["ref"]],
    )

    voice = outputs / "voice.wav"
    voice_receipt = _run_receipt_command(
        receipt_file=receipts / "voice-attempt-1.json",
        input_files=[documents["voice_script"]],
        output_files=[voice],
        output_sources=["mock://doubao-speech/requests/mock-speech-request-1/output"],
        provider="volcengine-simulated",
        executor="ffmpeg-local-speech-simulator",
        capability="speech_generation",
        job_kind="voiceover",
        command=[
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(voice),
        ],
        environment=environment,
        request_id="mock-speech-request-1",
    )
    await _ingest_receipt(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="voice:attempt-1",
        entity_type="audio",
        entity_id="voice-01",
        receipt=voice_receipt,
    )

    final = outputs / "final.mp4"
    use_mediakit = args.finisher == "mediakit" or (
        args.finisher == "auto" and PROJECT_MEDIAKIT.is_file()
    )
    if use_mediakit:
        if not PROJECT_MEDIAKIT.is_file():
            raise RuntimeError(
                "official MediaKit CLI is not built; run make mediakit-build"
            )
        finisher_executor = "mediakit-cli"
        finish_command = [
            str(PROJECT_MEDIAKIT),
            "--local",
            "editing",
            "mux-audio-video",
            "--video-url",
            str(shot),
            "--audio-url",
            str(voice),
            "--is-audio-reserve=false",
            "--is-video-audio-sync=true",
            "--sync-mode",
            "video",
            "--sync-method",
            "trim",
            "--output-path",
            str(final),
        ]
    else:
        finisher_executor = "ffmpeg"
        finish_command = [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(shot),
            "-i",
            str(voice),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-y",
            str(final),
        ]
    final_receipt = _run_receipt_command(
        receipt_file=receipts / "finishing-attempt-1.json",
        input_files=[shot, voice],
        output_files=[final],
        output_sources=[],
        provider="volcengine-local" if use_mediakit else "local",
        executor=finisher_executor,
        capability="media_processing",
        job_kind="final_mux",
        command=finish_command,
        environment=environment,
        request_id="local-finishing-request-1",
    )
    await _ingest_receipt(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="finishing:attempt-1",
        entity_type="timeline",
        entity_id="timeline-final-v1",
        receipt=final_receipt,
    )

    qa = run_delivery_qa(
        final, delivery_spec=delivery_spec, ffmpeg_path=ffmpeg, ffprobe_path=ffprobe
    )
    final_ref = final_receipt["outputs"][0]["ref"]
    await _append_business_event(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="delivery:qa:v1",
        event_type="delivery_qa_completed",
        status="succeeded" if qa["passed"] else "failed",
        entity_type="delivery",
        entity_id="delivery-v1",
        payload=qa,
        input_refs=[final_ref],
        output_refs=[final_ref],
        provider="ffmpeg_ffprobe",
    )
    if not qa["passed"]:
        raise RuntimeError("delivery QA failed; production remains blocked")
    completed = await _append_business_event(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="delivery:v1",
        event_type="delivery_completed",
        status="succeeded",
        entity_type="delivery",
        entity_id="delivery-v1",
        payload={
            "accepted": True,
            "qa_event_key": "delivery:qa:v1",
            "artifact": qa["artifact"],
        },
        input_refs=[final_ref],
        output_refs=[final_ref],
        provider=finisher_executor,
    )
    summary = {
        "contract_version": "personal-ip-video-e2e-acceptance-v1",
        "mode": "local-simulated-paid-providers",
        "production_id": production_id,
        "operation_key": args.operation_key,
        "status": completed["status"],
        "current_stage": completed["current_stage"],
        "event_count": completed["event_count"],
        "event_types": [event["event_type"] for event in completed["events"]],
        "task_ids": sorted(
            {
                event["provider_task_id"]
                for event in completed["events"]
                if event.get("provider_task_id")
            }
        ),
        "final_artifact": qa["artifact"],
        "qa_passed": qa["passed"],
        "finisher": finisher_executor,
        "ledger": str((work_dir / "ledger" / "deerflow.db").resolve()),
        "recovery": "rerun the identical command; succeeded receipts are re-hashed and immutable event keys replay idempotently",
        "paid_calls_executed": 0,
    }
    summary_path = work_dir / "acceptance-summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _paid_checkpoints(args: argparse.Namespace) -> dict[str, Any]:
    work_dir = args.work_dir.resolve()
    documents = _acceptance_documents(work_dir)
    outputs = work_dir / "paid-outputs"
    receipts = work_dir / "paid-receipts"
    outputs.mkdir(parents=True, exist_ok=True)
    receipts.mkdir(parents=True, exist_ok=True)
    python_prefix = ["uv", "run", "python"]
    checkpoints = [
        {
            "stage": "seedream",
            "paid": True,
            "argv": [
                *python_prefix,
                "../skills/public/image-generation/scripts/generate.py",
                "--prompt-file",
                str(documents["asset_prompt"]),
                "--output-file",
                str(outputs / "asset.png"),
                "--aspect-ratio",
                "9:16",
                "--receipt-file",
                str(receipts / "asset.json"),
            ],
        },
        {
            "stage": "seedance",
            "paid": True,
            "argv": [
                *python_prefix,
                "../skills/public/video-generation/scripts/generate.py",
                "--prompt-file",
                str(documents["video_prompt"]),
                "--reference-images",
                str(outputs / "asset.png"),
                "--output-file",
                str(outputs / "shot.mp4"),
                "--aspect-ratio",
                "9:16",
                "--receipt-file",
                str(receipts / "shot.json"),
            ],
        },
        {
            "stage": "speech",
            "paid": True,
            "argv": [
                *python_prefix,
                "../skills/public/podcast-generation/scripts/generate.py",
                "--script-file",
                str(documents["voice_script"]),
                "--output-file",
                str(outputs / "voice.mp3"),
                "--transcript-file",
                str(outputs / "voice-transcript.md"),
                "--receipt-file",
                str(receipts / "voice.json"),
            ],
        },
        {
            "stage": "mediakit-cloud-submit",
            "paid": True,
            "argv": [
                *python_prefix,
                "../skills/public/volcengine-stack/scripts/run_media_executor.py",
                "--input",
                str(outputs / "shot.mp4"),
                "--input",
                str(outputs / "voice.mp3"),
                "--receipt-file",
                str(receipts / "mediakit-submit.json"),
                "--provider",
                "volcengine",
                "--executor",
                "mediakit-cli",
                "--job-kind",
                "final_mux",
                "--status-mode",
                "running",
                "--",
                str(PROJECT_MEDIAKIT),
                "--cloud",
                "editing",
                "mux-audio-video",
                "--video-url",
                str(outputs / "shot.mp4"),
                "--audio-url",
                str(outputs / "voice.mp3"),
                "--client-token",
                "replace-with-stable-production-key",
            ],
        },
    ]
    for checkpoint in checkpoints:
        checkpoint["cwd"] = str((ROOT / "backend").resolve())
        checkpoint["requires_explicit_user_approval"] = True
        checkpoint["command"] = shlex.join(checkpoint["argv"])
    payload = {
        "contract_version": "personal-ip-paid-media-checkpoints-v1",
        "executed": False,
        "call_count": len(checkpoints),
        "target": {
            "aspect_ratio": "9:16",
            "duration_seconds": 2,
            "resolution": "provider default preview",
        },
        "prerequisites": [
            "explicit approval in the active user session",
            "provider credentials",
            "make volcengine-install for MediaKit",
        ],
        "checkpoints": checkpoints,
        "after_each_call": "ingest the emitted receipt with personal_ip_ingest_media_execution; never reconstruct provider evidence from stdout",
    }
    path = work_dir / "paid-checkpoints.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"path": str(path), **payload}


async def _ingest_real_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    """Seal already-executed provider receipts into one recoverable ledger."""

    work_dir = args.work_dir.resolve()
    inputs = work_dir / "inputs"
    outputs = work_dir / "paid-outputs"
    receipts = work_dir / "paid-receipts"
    documents = {
        "source": inputs / "source-script.json",
        "blueprint": inputs / "blueprint.json",
        "storyboard": inputs / "storyboard.json",
    }
    required = [
        *documents.values(),
        receipts / "asset.json",
        receipts / "shot.json",
        receipts / "voice.json",
        receipts / "finishing.json",
        receipts / "finishing-attempt-2.json",
        receipts / "finishing-attempt-3.json",
        receipts / "delivery-normalize.json",
        work_dir / "qa" / "delivery" / "acceptance-report.json",
        outputs / "delivery.mp4",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(
            f"real acceptance is missing {len(missing)} artifact(s): {missing[0]}"
        )

    await init_engine_from_config(
        DatabaseConfig(backend="sqlite", sqlite_dir=str(work_dir / "real-ledger"))
    )
    session_factory = get_session_factory()
    if session_factory is None:
        raise RuntimeError("real acceptance ledger is unavailable")
    repository = PersonalIPVideoProductionRepository(session_factory)
    source = _load_json(documents["source"])
    production = await repository.begin(
        owner_user_id=args.owner_user_id,
        operation_key=args.operation_key,
        title=str(source.get("title") or "Volcengine minimal real acceptance"),
        subject_id=None,
        target_account_ids=[],
        source_kind="script",
        source=source,
        delivery_spec={
            "aspect_ratio": "9:16",
            "duration_seconds": 4,
            "duration_tolerance_seconds": 0.25,
            "require_audio": True,
        },
        provider_policy={
            "image": ["seedream"],
            "video": ["seedance"],
            "speech": ["doubao-speech"],
            "finishing": ["mediakit-cli", "ffmpeg"],
        },
        budget={
            "currency": "CNY",
            "paid_calls_require_explicit_approval": True,
            "approval_ref": args.approval_ref,
        },
    )
    production_id = production["id"]
    source_ref = artifact_for_path(documents["source"])["ref"]
    blueprint = artifact_for_path(documents["blueprint"])
    await _append_business_event(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="real:blueprint:v1",
        event_type="blueprint_sealed",
        status="succeeded",
        entity_type="production",
        entity_id=production_id,
        payload={"artifact": blueprint, "acceptance": "minimal-real-provider-loop"},
        input_refs=[source_ref],
        output_refs=[blueprint["ref"]],
    )

    receipt_specs_before_storyboard = [
        ("asset.json", "real:asset:attempt-1", "scene", "asset-01"),
    ]
    receipt_specs_after_storyboard = [
        ("shot.json", "real:shot-01:attempt-1", "candidate", "shot-01:candidate-1"),
        ("voice.json", "real:voice:attempt-1", "audio", "voice-01"),
        ("finishing.json", "real:finishing:attempt-1", "timeline", "timeline-v1"),
        (
            "finishing-attempt-2.json",
            "real:finishing:attempt-2",
            "timeline",
            "timeline-v1",
        ),
        (
            "finishing-attempt-3.json",
            "real:finishing:attempt-3",
            "timeline",
            "timeline-v1",
        ),
        (
            "delivery-normalize.json",
            "real:delivery-normalize:attempt-1",
            "delivery",
            "delivery-v1",
        ),
    ]
    ingested_receipts: list[dict[str, Any]] = []
    for filename, event_key, entity_type, entity_id in receipt_specs_before_storyboard:
        receipt = _load_json(receipts / filename)
        if receipt.get("status") == "succeeded":
            verify_local_receipt_outputs(receipt)
        await _ingest_receipt(
            repository,
            production_id,
            owner_user_id=args.owner_user_id,
            event_key=event_key,
            entity_type=entity_type,
            entity_id=entity_id,
            receipt=receipt,
        )
        ingested_receipts.append(receipt)

    storyboard = artifact_for_path(documents["storyboard"])
    await _append_business_event(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="real:storyboard:v1",
        event_type="storyboard_sealed",
        status="succeeded",
        entity_type="production",
        entity_id=production_id,
        payload={"artifact": storyboard, "shot_count": 1},
        input_refs=[blueprint["ref"]],
        output_refs=[storyboard["ref"]],
    )
    for filename, event_key, entity_type, entity_id in receipt_specs_after_storyboard:
        receipt = _load_json(receipts / filename)
        if receipt.get("status") == "succeeded":
            verify_local_receipt_outputs(receipt)
        await _ingest_receipt(
            repository,
            production_id,
            owner_user_id=args.owner_user_id,
            event_key=event_key,
            entity_type=entity_type,
            entity_id=entity_id,
            receipt=receipt,
        )
        ingested_receipts.append(receipt)

    qa_path = work_dir / "qa" / "delivery" / "acceptance-report.json"
    qa = _load_json(qa_path)
    delivery_qa = qa.get("delivery")
    if not isinstance(delivery_qa, dict):
        raise RuntimeError("real acceptance report has no delivery QA object")
    final_artifact = artifact_for_path(outputs / "delivery.mp4")
    qa_artifact = artifact_for_path(qa_path)
    await _append_business_event(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="real:delivery:qa:v1",
        event_type="delivery_qa_completed",
        status="succeeded" if delivery_qa.get("passed") is True else "failed",
        entity_type="delivery",
        entity_id="delivery-v1",
        payload={**delivery_qa, "report_artifact": qa_artifact},
        input_refs=[final_artifact["ref"], qa_artifact["ref"]],
        output_refs=[final_artifact["ref"]],
        provider="ffmpeg_ffprobe",
    )
    if delivery_qa.get("passed") is not True:
        raise RuntimeError("real delivery QA did not pass")
    completed = await _append_business_event(
        repository,
        production_id,
        owner_user_id=args.owner_user_id,
        event_key="real:delivery:v1",
        event_type="delivery_completed",
        status="succeeded",
        entity_type="delivery",
        entity_id="delivery-v1",
        payload={
            "accepted": True,
            "qa_event_key": "real:delivery:qa:v1",
            "artifact": final_artifact,
        },
        input_refs=[qa_artifact["ref"]],
        output_refs=[final_artifact["ref"]],
        provider="project-ffmpeg-8.1.2",
    )
    summary = {
        "contract_version": "personal-ip-video-e2e-real-acceptance-v1",
        "mode": "real-volcengine-minimal",
        "production_id": production_id,
        "operation_key": args.operation_key,
        "status": completed["status"],
        "current_stage": completed["current_stage"],
        "event_count": completed["event_count"],
        "event_types": [event["event_type"] for event in completed["events"]],
        "provider_task_ids": sorted(
            {
                str(receipt["task_id"])
                for receipt in ingested_receipts
                if receipt.get("task_id")
            }
        ),
        "provider_request_ids": sorted(
            {
                str(receipt["request_id"])
                for receipt in ingested_receipts
                if receipt.get("request_id")
            }
        ),
        "paid_calls_executed": 3,
        "paid_cost": {
            "status": "unknown",
            "reason": "provider billing API is not connected",
        },
        "failed_local_attempts_preserved": sum(
            receipt.get("status") == "failed" for receipt in ingested_receipts
        ),
        "qa_passed": True,
        "final_artifact": final_artifact,
        "ledger": str((work_dir / "real-ledger" / "deerflow.db").resolve()),
        "approval_ref": args.approval_ref,
    }
    summary_path = work_dir / "real-acceptance-summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


async def _async_main(args: argparse.Namespace) -> int:
    try:
        if args.command == "local":
            result = await _run_local(args)
        elif args.command == "ingest-real":
            result = await _ingest_real_acceptance(args)
        else:
            result = _paid_checkpoints(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"Personal-IP video E2E failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if args.command in {"local", "ingest-real"}:
            await close_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    local = subparsers.add_parser(
        "local", help="Run/resume the free local acceptance production"
    )
    local.add_argument("--work-dir", type=Path, required=True)
    local.add_argument("--owner-user-id", default="video-e2e-local")
    local.add_argument("--operation-key", default="video:e2e:local-v1")
    local.add_argument("--ffmpeg")
    local.add_argument("--ffprobe")
    local.add_argument(
        "--finisher", choices=("auto", "mediakit", "ffmpeg"), default="auto"
    )
    paid = subparsers.add_parser(
        "paid-checkpoints",
        help="Write, but never execute, paid provider checkpoint commands",
    )
    paid.add_argument("--work-dir", type=Path, required=True)
    real = subparsers.add_parser(
        "ingest-real",
        help="Seal already-executed real provider receipts into a recovery ledger",
    )
    real.add_argument("--work-dir", type=Path, required=True)
    real.add_argument("--owner-user-id", default="video-e2e-real")
    real.add_argument("--operation-key", default="video:e2e:real-minimal-v3")
    real.add_argument(
        "--approval-ref",
        default="active-user-session:2026-07-23:direct-use",
    )
    return asyncio.run(_async_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
