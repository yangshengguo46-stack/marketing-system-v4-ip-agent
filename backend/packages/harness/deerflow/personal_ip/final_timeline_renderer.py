"""Deterministic local rendering for one locked Personal-IP video timeline."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from deerflow.personal_ip.video_acceptance import artifact_for_path, run_delivery_qa

LOCAL_DELIVERY_RENDER_CONTRACT_VERSION = "personal-ip-local-delivery-render-v1"


def _latest_event(production: dict[str, Any], event_type: str) -> dict[str, Any]:
    matching = [event for event in production.get("events") or [] if isinstance(event, dict) and event.get("event_type") == event_type and event.get("status") == "succeeded"]
    if not matching:
        raise ValueError(f"Video production has no successful {event_type} event")
    return matching[-1]


def _number(value: Any, *, field: str, minimum: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return result


def _local_file(ref: str) -> Path:
    parsed = urlsplit(str(ref or "").strip())
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise ValueError("Locked timeline delivery only accepts local file artifacts")
    path = Path(unquote(parsed.path)).resolve()
    if not path.is_file():
        raise ValueError(f"Recorded local artifact is missing: {path}")
    return path


def _successful_artifacts(production: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_ref: dict[str, dict[str, Any]] = {}
    by_entity: dict[str, list[dict[str, Any]]] = {}
    for event in production.get("events") or []:
        if not isinstance(event, dict) or event.get("status") != "succeeded":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        outputs = payload.get("outputs") if isinstance(payload.get("outputs"), list) else []
        artifact = payload.get("artifact")
        candidates = [item for item in outputs if isinstance(item, dict)]
        if isinstance(artifact, dict):
            candidates.append(artifact)
        verified: list[dict[str, Any]] = []
        for item in candidates:
            ref = str(item.get("ref") or "").strip()
            digest = str(item.get("sha256") or "").strip().lower()
            size = item.get("size_bytes")
            if not ref or len(digest) != 64 or not isinstance(size, int):
                continue
            snapshot = {
                "ref": ref,
                "sha256": digest,
                "size_bytes": size,
                "mime_type": str(item.get("mime_type") or "application/octet-stream"),
            }
            by_ref[ref] = snapshot
            verified.append(snapshot)
        entity_id = str(event.get("entity_id") or "").strip()
        if entity_id and verified:
            by_entity.setdefault(entity_id, []).extend(verified)
    return by_ref, by_entity


def _verified_path(artifact: dict[str, Any], *, expected_sha256: str | None = None) -> Path:
    path = _local_file(str(artifact.get("ref") or ""))
    actual = artifact_for_path(path)
    if actual["sha256"] != artifact.get("sha256") or actual["size_bytes"] != artifact.get("size_bytes"):
        raise ValueError(f"Recorded artifact no longer matches its immutable receipt: {path}")
    if expected_sha256 and actual["sha256"] != expected_sha256:
        raise ValueError(f"Timeline source SHA-256 does not match its recorded artifact: {path}")
    return path


def _resolve_clip_source(
    clip: dict[str, Any],
    *,
    artifacts_by_ref: dict[str, dict[str, Any]],
    artifacts_by_entity: dict[str, list[dict[str, Any]]],
) -> tuple[Path, dict[str, Any]]:
    source_ref = str(clip.get("source_ref") or "").strip()
    expected_sha = str(clip.get("source_sha256") or "").strip().lower() or None
    artifact = artifacts_by_ref.get(source_ref) if source_ref else None
    if artifact is None:
        candidate_id = str(clip.get("selected_candidate_id") or "").strip()
        candidates = artifacts_by_entity.get(candidate_id, [])
        artifact = next((item for item in reversed(candidates) if str(item.get("mime_type") or "").startswith("video/")), None)
    if artifact is None:
        raise ValueError(f"No verified local video artifact is recorded for timeline clip {clip.get('id')}")
    return _verified_path(artifact, expected_sha256=expected_sha), artifact


def _latest_voice_artifact(
    production: dict[str, Any],
    *,
    artifacts_by_ref: dict[str, dict[str, Any]],
) -> tuple[Path, dict[str, Any]] | None:
    for event in reversed(production.get("events") or []):
        if not isinstance(event, dict) or event.get("event_type") != "voice_generated" or event.get("status") != "succeeded":
            continue
        for ref in reversed(event.get("output_refs") or []):
            artifact = artifacts_by_ref.get(str(ref))
            if artifact and str(artifact.get("mime_type") or "").startswith("audio/"):
                return _verified_path(artifact), artifact
    return None


def _probe_video_size(path: Path, *, ffprobe_path: str) -> tuple[int, int]:
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
    if result.returncode != 0:
        raise ValueError(f"ffprobe could not inspect timeline video: {(result.stderr or '').strip()[:500]}")
    try:
        stream = (json.loads(result.stdout or "{}").get("streams") or [])[0]
        width = int(stream["width"])
        height = int(stream["height"])
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("ffprobe returned no usable video dimensions") from exc
    if width <= 0 or height <= 0:
        raise ValueError("Timeline video has invalid dimensions")
    return width - (width % 2), height - (height % 2)


def _format_seconds(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def _render_command(
    *,
    clips: list[tuple[dict[str, Any], Path]],
    audio: tuple[Path, dict[str, Any]] | None,
    output: Path,
    ffmpeg_path: str,
    width: int,
    height: int,
    fps: int,
    duration_seconds: float,
) -> list[str]:
    command = [ffmpeg_path, "-hide_banner", "-loglevel", "error"]
    for clip, source in clips:
        command.extend(
            [
                "-ss",
                _format_seconds(_number(clip.get("source_in_sec"), field="clip.source_in_sec")),
                "-t",
                _format_seconds(_number(clip.get("duration_sec"), field="clip.duration_sec", minimum=0.001)),
                "-i",
                str(source),
            ]
        )
    if audio is not None:
        command.extend(["-i", str(audio[0])])

    filters = [f"color=c=black:s={width}x{height}:r={fps}:d={_format_seconds(duration_seconds)}[base]"]
    previous = "base"
    ordered = sorted(enumerate(clips), key=lambda item: (_number(item[1][0].get("start_sec"), field="clip.start_sec"), item[0]))
    for overlay_index, (input_index, (clip, _source)) in enumerate(ordered):
        start = _number(clip.get("start_sec"), field="clip.start_sec")
        duration = _number(clip.get("duration_sec"), field="clip.duration_sec", minimum=0.001)
        end = min(duration_seconds, start + duration)
        if end <= start:
            raise ValueError("Timeline clip lies outside the locked duration")
        filters.append(
            f"[{input_index}:v:0]"
            f"trim=duration={_format_seconds(duration)},"
            "setpts=PTS-STARTPTS,"
            f"fps={fps},"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
            "setsar=1,format=yuv420p,"
            f"setpts=PTS+{_format_seconds(start)}/TB[v{overlay_index}]"
        )
        output_label = f"ov{overlay_index}"
        filters.append(f"[{previous}][v{overlay_index}]overlay=eof_action=pass:shortest=0:enable='between(t,{_format_seconds(start)},{_format_seconds(end)})'[{output_label}]")
        previous = output_label
    filters.append(f"[{previous}]format=yuv420p[vout]")

    audio_label: str | None = None
    if audio is not None:
        audio_index = len(clips)
        fade = min(0.03, duration_seconds / 4)
        fade_out = max(0.0, duration_seconds - fade)
        filters.append(
            f"[{audio_index}:a:0]"
            f"atrim=start=0:duration={_format_seconds(duration_seconds)},"
            "asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={_format_seconds(fade)},"
            f"afade=t=out:st={_format_seconds(fade_out)}:d={_format_seconds(fade)},"
            f"apad=pad_dur={_format_seconds(duration_seconds)},"
            f"atrim=duration={_format_seconds(duration_seconds)}[aout]"
        )
        audio_label = "aout"

    command.extend(["-filter_complex", ";".join(filters), "-map", "[vout]"])
    if audio_label:
        command.extend(["-map", f"[{audio_label}]"])
    command.extend(
        [
            "-c:v",
            "mpeg4",
            "-q:v",
            "3",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
        ]
    )
    if audio_label:
        command.extend(["-c:a", "aac", "-b:a", "192k"])
    command.extend(["-movflags", "+faststart", "-t", _format_seconds(duration_seconds), "-y", str(output)])
    return command


def render_locked_timeline_delivery(
    production: dict[str, Any],
    *,
    output_root: str | Path,
    ffmpeg_path: str,
    ffprobe_path: str,
) -> dict[str, Any]:
    """Render and fully decode-QA the latest locked timeline using local tools only."""

    timeline_event = _latest_event(production, "timeline_revision_compiled")
    lock_event = _latest_event(production, "final_edit_locked")
    timeline = timeline_event.get("payload") if isinstance(timeline_event.get("payload"), dict) else {}
    lock = lock_event.get("payload") if isinstance(lock_event.get("payload"), dict) else {}
    if lock.get("source_revision_id") != timeline.get("revision_id") or lock.get("source_timeline_sha256") != timeline.get("sha256"):
        raise ValueError("Latest final-edit lock does not freeze the latest timeline revision")
    if lock.get("ready_for_delivery_qa") is not True:
        raise ValueError("Latest final-edit lock is not ready for delivery QA")

    tracks = timeline.get("tracks") if isinstance(timeline.get("tracks"), list) else []
    video_track = next((track for track in tracks if isinstance(track, dict) and track.get("type") == "video"), None)
    video_clips = video_track.get("clips") if isinstance(video_track, dict) and isinstance(video_track.get("clips"), list) else []
    if not video_clips:
        raise ValueError("Locked timeline has no video clips")

    artifacts_by_ref, artifacts_by_entity = _successful_artifacts(production)
    resolved_clips: list[tuple[dict[str, Any], Path]] = []
    input_artifacts: list[dict[str, Any]] = []
    for clip in video_clips:
        if not isinstance(clip, dict):
            raise ValueError("Locked timeline video clip must be an object")
        source, artifact = _resolve_clip_source(
            clip,
            artifacts_by_ref=artifacts_by_ref,
            artifacts_by_entity=artifacts_by_entity,
        )
        resolved_clips.append((clip, source))
        input_artifacts.append(artifact)

    duration_seconds = _number(lock.get("duration_seconds"), field="lock.duration_seconds", minimum=0.001)
    fps_value = int(_number(lock.get("fps"), field="lock.fps", minimum=1))
    width, height = _probe_video_size(resolved_clips[0][1], ffprobe_path=ffprobe_path)
    delivery_spec = dict(production.get("delivery_spec") or {})
    delivery_spec["duration_seconds"] = duration_seconds
    delivery_spec.setdefault("duration_tolerance_seconds", max(0.05, 1 / fps_value * 2))
    require_audio = bool(delivery_spec.get("require_audio"))
    audio = _latest_voice_artifact(production, artifacts_by_ref=artifacts_by_ref)
    if require_audio and audio is None:
        raise ValueError("Delivery requires audio but no verified local voice artifact is recorded")
    if audio is not None:
        input_artifacts.append(audio[1])

    production_id = str(production.get("id") or "").strip()
    revision_id = str(timeline.get("revision_id") or "").strip()
    revision_sha = str(timeline.get("sha256") or "").strip().lower()
    if not production_id or not revision_id or len(revision_sha) != 64:
        raise ValueError("Locked timeline identity is incomplete")
    bucket = hashlib.sha256(f"{production_id}\0{revision_id}".encode()).hexdigest()[:24]
    output_dir = Path(output_root).resolve() / bucket
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"delivery-{revision_sha[:16]}.mp4"
    if output.exists():
        raise ValueError("Deterministic delivery output already exists without a matching ledger receipt")
    temporary = output_dir / f".{output.name}.{uuid.uuid4().hex}.partial.mp4"

    command = _render_command(
        clips=resolved_clips,
        audio=audio,
        output=temporary,
        ffmpeg_path=ffmpeg_path,
        width=width,
        height=height,
        fps=fps_value,
        duration_seconds=duration_seconds,
    )
    started_at = datetime.now(UTC)
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=3_600)
        if result.returncode != 0:
            raise ValueError(f"Local FFmpeg timeline render failed: {(result.stderr or '').strip()[:1_000]}")
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise ValueError("Local FFmpeg timeline render produced no output")
        os.link(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    completed_at = datetime.now(UTC)
    output_artifact = artifact_for_path(output)
    receipt = {
        "contract_version": "personal-ip-media-execution-v1",
        "capability": "media_processing",
        "provider": "local",
        "executor": "project-ffmpeg",
        "model": None,
        "task_id": None,
        "request_id": f"locked-timeline-{revision_sha[:20]}",
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "status": "succeeded",
        "parameters": {
            "contract_version": LOCAL_DELIVERY_RENDER_CONTRACT_VERSION,
            "job_kind": "locked_timeline_delivery",
            "production_id": production_id,
            "revision_id": revision_id,
            "timeline_sha256": revision_sha,
            "lock_id": lock.get("lock_id"),
            "fps": fps_value,
            "duration_seconds": duration_seconds,
            "resolution": f"{width}x{height}",
            "video_clip_count": len(resolved_clips),
            "audio_source": "latest_verified_voice_receipt" if audio else "none",
            "command": command[:-1] + [output.name],
        },
        "inputs": input_artifacts,
        "outputs": [output_artifact],
        "cost": {
            "status": "known",
            "amount": 0.0,
            "currency": "CNY",
            "basis": "project-local FFmpeg execution",
        },
        "failure": None,
    }
    qa = run_delivery_qa(
        output,
        delivery_spec=delivery_spec,
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
    )
    return {
        "contract_version": LOCAL_DELIVERY_RENDER_CONTRACT_VERSION,
        "production_id": production_id,
        "revision_id": revision_id,
        "timeline_sha256": revision_sha,
        "lock_id": lock.get("lock_id"),
        "output_path": str(output),
        "receipt": receipt,
        "qa": qa,
    }
