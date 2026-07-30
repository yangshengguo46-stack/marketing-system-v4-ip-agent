"""Local frame-grounded inspection evidence for rights-cleared source video."""

from __future__ import annotations

import json
import math
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from deerflow.personal_ip.video_acceptance import artifact_for_path

LOCAL_MATERIAL_INSPECTION_VERSION = "personal-ip-local-material-inspection-evidence-v1"


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _ratio(value: Any) -> float | None:
    text = str(value or "").strip()
    if "/" not in text:
        return _number(text)
    numerator, denominator = text.split("/", 1)
    left = _number(numerator)
    right = _number(denominator)
    if left is None or right in {None, 0}:
        return None
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
        detail = " ".join((result.stderr or "").strip().split())[:500]
        raise ValueError(f"{label} failed" + (f": {detail}" if detail else ""))
    return result


def _artifact(path: Path, *, ref: str | None = None) -> dict[str, Any]:
    value = artifact_for_path(path)
    if ref:
        value["ref"] = ref
    return value


def inspect_local_video_material(
    source_file: str | Path,
    review_dir: str | Path,
    *,
    source_in_seconds: float,
    source_out_seconds: float,
    ffmpeg_path: str,
    ffprobe_path: str,
    source_ref: str | None = None,
    review_ref_prefix: str | None = None,
    max_frames: int = 12,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Extract timestamp-grounded frames without making a semantic judgment."""

    source_path = Path(source_file).resolve()
    if not source_path.is_file():
        raise ValueError("material source was not found")
    output_dir = Path(review_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    probe_result = _run(
        command_runner,
        [
            ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(source_path),
        ],
        label="material ffprobe",
        timeout=120,
    )
    try:
        probe = json.loads(probe_result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("material ffprobe returned invalid JSON") from exc
    streams = probe.get("streams") if isinstance(probe, dict) else None
    if not isinstance(streams, list):
        streams = []
    video = next(
        (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"),
        None,
    )
    if video is None:
        raise ValueError("material source has no video stream")
    format_data = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    duration = _number(format_data.get("duration")) or _number(video.get("duration"))
    fps = _ratio(video.get("avg_frame_rate")) or _ratio(video.get("r_frame_rate"))
    width = video.get("width")
    height = video.get("height")
    if duration is None or duration <= 0 or fps is None or fps <= 0:
        raise ValueError("material source duration or frame rate is unavailable")
    if not isinstance(width, int) or width <= 0 or not isinstance(height, int) or height <= 0:
        raise ValueError("material source resolution is unavailable")
    start = float(source_in_seconds)
    end = float(source_out_seconds)
    if start < 0 or end <= start or end > duration + 0.05:
        raise ValueError("material source range is outside the local video")
    window = end - start
    sample_count = min(max(4, int(max_frames)), max(4, math.ceil(window)), 24)
    sample_fps = sample_count / window
    frame_pattern = output_dir / "frame-%03d.jpg"
    _run(
        command_runner,
        [
            ffmpeg_path,
            "-y",
            "-v",
            "error",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(source_path),
            "-t",
            f"{window:.3f}",
            "-vf",
            f"fps={sample_fps:.8f},scale=512:-2",
            "-frames:v",
            str(sample_count),
            "-q:v",
            "3",
            str(frame_pattern),
        ],
        label="material frame extraction",
        timeout=300,
    )
    frame_paths = sorted(output_dir.glob("frame-*.jpg"))
    if not frame_paths:
        raise ValueError("material frame extraction produced no frames")
    contact_sheet = output_dir / "contact-sheet.jpg"
    _run(
        command_runner,
        [
            ffmpeg_path,
            "-y",
            "-v",
            "error",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(source_path),
            "-t",
            f"{window:.3f}",
            "-vf",
            f"fps={sample_fps:.8f},scale=320:-2,tile=4x3:nb_frames={len(frame_paths)}",
            "-frames:v",
            "1",
            str(contact_sheet),
        ],
        label="material contact-sheet extraction",
        timeout=300,
    )

    prefix = (review_ref_prefix or "").rstrip("/")
    frames: list[dict[str, Any]] = []
    for index, frame_path in enumerate(frame_paths):
        ref = f"{prefix}/{frame_path.name}" if prefix else frame_path.as_uri()
        frames.append(
            {
                "timestamp_seconds": round(
                    min(end, start + index / sample_fps),
                    3,
                ),
                "artifact": _artifact(frame_path, ref=ref),
            }
        )
    contact_ref = f"{prefix}/{contact_sheet.name}" if prefix else contact_sheet.as_uri()
    source = _artifact(source_path, ref=source_ref)
    evidence = {
        "source": source,
        "source_in_seconds": round(start, 3),
        "source_out_seconds": round(end, 3),
        "probe": {
            "duration_seconds": duration,
            "width": width,
            "height": height,
            "fps": fps,
            "audio_stream_count": sum(1 for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"),
        },
        "frames": frames,
        "contact_sheet": _artifact(contact_sheet, ref=contact_ref),
    }
    report_path = output_dir / "inspection-report.json"
    report_ref = f"{prefix}/{report_path.name}" if prefix else report_path.as_uri()
    report = {
        "contract_version": LOCAL_MATERIAL_INSPECTION_VERSION,
        "mechanical_only": True,
        "semantic_assessment_required": True,
        **evidence,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return {
        "contract_version": LOCAL_MATERIAL_INSPECTION_VERSION,
        "mechanical_only": True,
        "semantic_assessment_required": True,
        **evidence,
        "report": _artifact(report_path, ref=report_ref),
        "executors": {
            "ffmpeg": Path(ffmpeg_path).name,
            "ffprobe": Path(ffprobe_path).name,
        },
    }
