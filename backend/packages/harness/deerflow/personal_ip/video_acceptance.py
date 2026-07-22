"""Local verification primitives for recoverable Personal-IP video delivery."""

from __future__ import annotations

import hashlib
import json
import math
import mimetypes
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

DELIVERY_QA_CONTRACT_VERSION = "personal-ip-delivery-qa-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_for_path(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise ValueError(f"delivery artifact not found: {resolved}")
    return {
        "ref": resolved.as_uri(),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
        "mime_type": mimetypes.guess_type(resolved.name)[0] or "application/octet-stream",
    }


def _file_uri_path(ref: str) -> Path | None:
    parsed = urlsplit(ref)
    if parsed.scheme != "file":
        return None
    if parsed.netloc not in {"", "localhost"}:
        raise ValueError("file artifact ref must be local")
    return Path(unquote(parsed.path)).resolve()


def verify_local_receipt_outputs(receipt: dict[str, Any]) -> None:
    """Re-hash local successful outputs before accepting or resuming a receipt."""

    if receipt.get("status") != "succeeded":
        raise ValueError("only succeeded receipts have verifiable local outputs")
    outputs = receipt.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("succeeded receipt has no outputs")
    for index, item in enumerate(outputs):
        if not isinstance(item, dict):
            raise ValueError(f"receipt.outputs[{index}] must be an object")
        path = _file_uri_path(str(item.get("ref") or ""))
        if path is None:
            continue
        if not path.is_file():
            raise ValueError(f"receipt output is missing: {path}")
        size = item.get("size_bytes")
        if size != path.stat().st_size:
            raise ValueError(f"receipt output size mismatch: {path}")
        if item.get("sha256") != _sha256(path):
            raise ValueError(f"receipt output SHA-256 mismatch: {path}")


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _ratio(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    if ":" in text:
        left, right = text.split(":", 1)
        numerator = _number(left)
        denominator = _number(right)
        if numerator is None or denominator in {None, 0}:
            return None
        return numerator / denominator
    return _number(text)


def _check(name: str, passed: bool, *, expected: Any = None, actual: Any = None, detail: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "passed": passed}
    if expected is not None:
        result["expected"] = expected
    if actual is not None:
        result["actual"] = actual
    if detail:
        result["detail"] = detail[:1_000]
    return result


def run_delivery_qa(
    output_file: str | Path,
    *,
    delivery_spec: dict[str, Any],
    ffmpeg_path: str,
    ffprobe_path: str,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Probe and fully decode one local final artifact before delivery."""

    path = Path(output_file).resolve()
    artifact = artifact_for_path(path)
    probe_command = [
        ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    probe_result = command_runner(probe_command, capture_output=True, text=True, check=False, timeout=120)
    if probe_result.returncode != 0:
        raise ValueError(f"ffprobe failed for delivery artifact: {(probe_result.stderr or '').strip()[:500]}")
    try:
        probe_payload = json.loads(probe_result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("ffprobe returned invalid JSON") from exc
    streams = probe_payload.get("streams") if isinstance(probe_payload, dict) else None
    if not isinstance(streams, list):
        streams = []
    video = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"), {})
    format_data = probe_payload.get("format") if isinstance(probe_payload.get("format"), dict) else {}
    duration = _number(format_data.get("duration"))
    width = video.get("width") if isinstance(video.get("width"), int) else None
    height = video.get("height") if isinstance(video.get("height"), int) else None
    actual_ratio = width / height if width and height else None

    decode_command = [ffmpeg_path, "-v", "error", "-i", str(path), "-map", "0", "-f", "null", "-"]
    decode_result = command_runner(decode_command, capture_output=True, text=True, check=False, timeout=600)
    checks = [_check("decode", decode_result.returncode == 0, detail=(decode_result.stderr or "").strip() if decode_result.returncode else None)]

    expected_duration = _number(delivery_spec.get("duration_seconds"))
    if expected_duration is not None:
        tolerance = _number(delivery_spec.get("duration_tolerance_seconds"))
        tolerance = 0.5 if tolerance is None else max(0.0, tolerance)
        duration_passed = duration is not None and abs(duration - expected_duration) <= tolerance
        checks.append(_check("duration", duration_passed, expected=expected_duration, actual=duration))

    expected_aspect = delivery_spec.get("aspect_ratio")
    expected_ratio = _ratio(expected_aspect)
    if expected_ratio is not None:
        aspect_passed = actual_ratio is not None and abs(actual_ratio - expected_ratio) <= 0.01
        checks.append(_check("aspect_ratio", aspect_passed, expected=expected_aspect, actual=f"{width}:{height}" if width and height else None))

    if bool(delivery_spec.get("require_audio")):
        checks.append(_check("audio_stream", bool(audio), expected=True, actual=bool(audio)))

    probe = {
        "format_name": format_data.get("format_name"),
        "duration_seconds": duration,
        "video_codec": video.get("codec_name"),
        "width": width,
        "height": height,
        "frame_rate": video.get("r_frame_rate"),
        "audio_codec": audio.get("codec_name"),
        "audio_channels": audio.get("channels"),
        "audio_sample_rate": audio.get("sample_rate"),
    }
    return {
        "contract_version": DELIVERY_QA_CONTRACT_VERSION,
        "passed": all(item["passed"] for item in checks),
        "artifact": artifact,
        "delivery_spec": json.loads(json.dumps(delivery_spec, ensure_ascii=False, sort_keys=True)),
        "checks": checks,
        "probe": probe,
        "executors": {"ffmpeg": Path(ffmpeg_path).name, "ffprobe": Path(ffprobe_path).name},
    }
