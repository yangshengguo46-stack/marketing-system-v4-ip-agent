"""Project-local motion-compensated frame interpolation for video candidates."""

from __future__ import annotations

import json
import math
import subprocess
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deerflow.personal_ip.video_acceptance import artifact_for_path

LOCAL_FRAME_INTERPOLATION_VERSION = "personal-ip-local-frame-interpolation-v1"


def _required_file(path: str | Path, *, label: str) -> Path:
    result = Path(path).resolve()
    if not result.is_file():
        raise ValueError(f"{label} was not found")
    return result


def _number(value: Any, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _ratio(value: Any, *, field: str) -> float:
    text = str(value or "").strip()
    if "/" not in text:
        return _number(text, field=field)
    numerator, denominator = text.split("/", 1)
    left = _number(numerator, field=field)
    right = _number(denominator, field=field)
    return left / right


def _run(
    command_runner: Callable[..., subprocess.CompletedProcess[str]],
    command: list[str],
    *,
    label: str,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    result = command_runner(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = " ".join(((result.stderr or "") + " " + (result.stdout or "")).strip().split())[:1_000]
        suffix = f": {detail}" if detail else ""
        raise ValueError(f"{label} failed{suffix}")
    return result


def _probe(
    path: Path,
    *,
    ffprobe_path: Path,
    command_runner: Callable[..., subprocess.CompletedProcess[str]],
) -> tuple[dict[str, Any], dict[str, Any], float, float]:
    result = _run(
        command_runner,
        [
            str(ffprobe_path),
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "format=duration,size:stream=index,codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,r_frame_rate,nb_frames,nb_read_frames",
            "-of",
            "json",
            str(path),
        ],
        label="frame-interpolation probe",
        timeout=120,
    )
    try:
        probe = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("frame-interpolation probe returned invalid JSON") from exc
    streams = probe.get("streams") if isinstance(probe, dict) else None
    if not isinstance(streams, list):
        streams = []
    video = next(
        (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"),
        None,
    )
    if video is None:
        raise ValueError("frame-interpolation input has no video stream")
    fps = _ratio(
        video.get("avg_frame_rate") or video.get("r_frame_rate"),
        field="video frame rate",
    )
    format_data = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    duration = _number(
        format_data.get("duration") or video.get("duration"),
        field="video duration",
    )
    return probe, video, fps, duration


def _artifact(path: Path, *, ref: str) -> dict[str, Any]:
    artifact = artifact_for_path(path)
    artifact["ref"] = ref
    return artifact


def interpolate_video_candidate(
    source_path: str | Path,
    output_path: str | Path,
    *,
    source_ref: str,
    output_ref: str,
    target_fps: int,
    ffmpeg_path: str | Path,
    ffprobe_path: str | Path,
    task_id: str,
    expected_source_sha256: str | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Create a new candidate with FFmpeg motion compensation and verify it."""

    source = _required_file(source_path, label="source video")
    source_artifact = _artifact(source, ref=source_ref)
    if expected_source_sha256 is not None and source_artifact["sha256"] != expected_source_sha256:
        raise ValueError("source video no longer matches its immutable candidate receipt")
    ffmpeg = _required_file(ffmpeg_path, label="project-local FFmpeg")
    ffprobe = _required_file(ffprobe_path, label="project-local FFprobe")
    if isinstance(target_fps, bool) or not isinstance(target_fps, int) or not 1 <= target_fps <= 120:
        raise ValueError("target_fps must be an integer between 1 and 120")
    source_probe, source_video, source_fps, source_duration = _probe(
        source,
        ffprobe_path=ffprobe,
        command_runner=command_runner,
    )
    if target_fps <= source_fps + 0.01:
        raise ValueError("target_fps must be higher than the source frame rate")
    width = source_video.get("width")
    height = source_video.get("height")
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise ValueError("source video width is invalid")
    if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
        raise ValueError("source video height is invalid")

    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError("frame-interpolation output already exists; use a new candidate id")
    temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.partial.mp4"
    video_bitrate = min(
        30_000_000,
        max(2_000_000, round(width * height * target_fps * 0.12)),
    )
    interpolation_filter = f"minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:me=epzs:vsbmc=1:scd=fdiff:scd_threshold=10,format=yuv420p"
    started_at = datetime.now(UTC)
    try:
        _run(
            command_runner,
            [
                str(ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-vf",
                interpolation_filter,
                "-c:v",
                "libopenh264",
                "-b:v",
                str(video_bitrate),
                "-pix_fmt",
                "yuv420p",
                "-fps_mode",
                "cfr",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-movflags",
                "+faststart",
                "-y",
                str(temporary),
            ],
            label="motion-compensated frame interpolation",
            timeout=3_600,
        )
        _required_file(temporary, label="frame-interpolation output")
        output_probe, output_video, output_fps, output_duration = _probe(
            temporary,
            ffprobe_path=ffprobe,
            command_runner=command_runner,
        )
        if abs(output_fps - target_fps) >= 0.01:
            raise ValueError("frame-interpolation output frame rate does not match target_fps")
        duration_tolerance = max(0.1, 2 / source_fps)
        if abs(output_duration - source_duration) > duration_tolerance:
            raise ValueError("frame-interpolation output duration drifted from the source")
        _run(
            command_runner,
            [
                str(ffmpeg),
                "-v",
                "error",
                "-i",
                str(temporary),
                "-map",
                "0:v:0",
                "-f",
                "null",
                "-",
            ],
            label="frame-interpolation full decode",
            timeout=600,
        )
        verified_source_artifact = _artifact(source, ref=source_ref)
        if verified_source_artifact["sha256"] != source_artifact["sha256"]:
            raise ValueError("source video changed during frame interpolation")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    completed_at = datetime.now(UTC)
    return {
        "contract_version": "personal-ip-media-execution-v1",
        "capability": "video_generation",
        "provider": "ffmpeg",
        "executor": "project-ffmpeg-minterpolate",
        "model": LOCAL_FRAME_INTERPOLATION_VERSION,
        "status": "succeeded",
        "task_id": task_id,
        "request_id": None,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "parameters": {
            "operation": "motion_compensated_frame_interpolation",
            "source_fps": source_fps,
            "target_fps": target_fps,
            "source_duration_seconds": source_duration,
            "output_duration_seconds": output_duration,
            "duration_preserved": True,
            "motion_compensated": True,
            "duplicate_frame_conversion": False,
            "creates_new_candidate": True,
            "filter": interpolation_filter,
            "source_probe": source_probe,
            "output_probe": output_probe,
            "output_video_stream": output_video,
        },
        "inputs": [verified_source_artifact],
        "outputs": [_artifact(target, ref=output_ref)],
        "cost": {
            "status": "known",
            "amount": 0,
            "currency": "CNY",
            "basis": "local project-pinned FFmpeg motion interpolation",
        },
        "failure": None,
    }
