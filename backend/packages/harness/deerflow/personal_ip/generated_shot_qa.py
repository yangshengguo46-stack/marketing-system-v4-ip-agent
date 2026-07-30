"""Project-local mechanical QA for one generated video-shot candidate."""

from __future__ import annotations

import json
import math
import statistics
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from deerflow.personal_ip.video_acceptance import artifact_for_path

LOCAL_GENERATED_SHOT_QA_EVIDENCE_VERSION = "personal-ip-generated-shot-local-evidence-v1"
_MOTION_EXPECTATIONS = {"unspecified", "static", "natural", "continuous"}


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
        suffix = f": {detail}" if detail else ""
        raise ValueError(f"{label} failed{suffix}")
    return result


def _parse_ssim(text: str, *, label: str) -> float:
    for token in reversed(text.replace("\n", " ").split()):
        if token.startswith("All:"):
            value = _number(token.removeprefix("All:"))
            if value is not None and 0 <= value <= 1:
                return value
    raise ValueError(f"{label} did not produce an All SSIM score")


def _parse_ssim_stats(path: Path) -> list[float]:
    scores: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        for token in line.split():
            if not token.startswith("All:"):
                continue
            value = _number(token.removeprefix("All:"))
            if value is not None and 0 <= value <= 1:
                scores.append(value)
            break
    if not scores:
        raise ValueError("consecutive-frame SSIM did not produce any scores")
    return scores


def _policy_number(
    policy: Mapping[str, Any],
    key: str,
    *,
    default: float,
    minimum: float,
    maximum: float | None = None,
) -> float:
    raw = policy.get(key)
    value = default if raw is None else _number(raw)
    if value is None or value < minimum or (maximum is not None and value > maximum):
        upper = f" and at most {maximum}" if maximum is not None else ""
        raise ValueError(f"policy.{key} must be at least {minimum}{upper}")
    return value


def _longest_true_run(values: list[bool]) -> int:
    longest = 0
    current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def _motion_cadence(
    consecutive_scores: list[float],
    *,
    fps: float,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive explainable cadence evidence without pretending to judge aesthetics."""

    threshold = _policy_number(
        policy,
        "near_duplicate_ssim_threshold",
        default=0.999,
        minimum=0,
        maximum=1,
    )
    expectation = str(policy.get("motion_expectation") or "unspecified").strip().lower()
    if expectation not in _MOTION_EXPECTATIONS:
        allowed = ", ".join(sorted(_MOTION_EXPECTATIONS))
        raise ValueError(f"policy.motion_expectation must be one of: {allowed}")
    target_fps_raw = policy.get("target_playback_fps")
    target_fps = None
    if target_fps_raw is not None:
        target_fps = _policy_number(
            policy,
            "target_playback_fps",
            default=fps,
            minimum=1,
            maximum=120,
        )
    elif expectation == "continuous" and fps <= 24.01:
        target_fps = min(120.0, fps * 2)

    deltas = [max(0.0, 1.0 - score) for score in consecutive_scores]
    median_delta = statistics.median(deltas)
    mean_delta = statistics.mean(deltas)
    stdev_delta = statistics.pstdev(deltas) if len(deltas) > 1 else 0.0
    delta_cv = stdev_delta / mean_delta if mean_delta > 1e-9 else 0.0
    near_duplicate_flags = [score >= threshold for score in consecutive_scores]
    near_duplicate_count = sum(near_duplicate_flags)
    near_duplicate_ratio = near_duplicate_count / len(consecutive_scores)
    longest_run_frames = _longest_true_run(near_duplicate_flags)
    longest_run_seconds = longest_run_frames / fps
    if near_duplicate_ratio >= 0.8 or median_delta <= 0.001:
        classification = "static"
    elif median_delta <= 0.01:
        classification = "low_motion"
    else:
        classification = "active_motion"

    cadence_outlier_ratio = 0.0
    if median_delta > 1e-9:
        cadence_outlier_ratio = sum(delta < median_delta * 0.25 or delta > median_delta * 4 for delta in deltas) / len(deltas)
    severe_repeats = near_duplicate_ratio > 0.1 or longest_run_seconds > max(
        0.125,
        3 / fps,
    )
    low_fps_motion = bool(target_fps is not None and target_fps > fps + 0.01 and classification == "active_motion")
    irregular_motion = classification == "active_motion" and (delta_cv > 1.0 or cadence_outlier_ratio > 0.2)
    if severe_repeats and expectation == "continuous":
        risk = "high"
        action = "regenerate_source"
    elif low_fps_motion:
        risk = "medium"
        action = "motion_interpolation" if not severe_repeats else "regenerate_source"
    elif irregular_motion:
        risk = "medium"
        action = "review_source_motion"
    else:
        risk = "low"
        action = "none"
    interpolation_recommended = action == "motion_interpolation"
    return {
        "available": True,
        "mechanical_only": True,
        "source_fps": fps,
        "target_playback_fps": target_fps,
        "motion_expectation": expectation,
        "classification": classification,
        "near_duplicate_ssim_threshold": threshold,
        "near_duplicate_transition_count": near_duplicate_count,
        "near_duplicate_transition_ratio": near_duplicate_ratio,
        "longest_near_duplicate_run_frames": longest_run_frames,
        "longest_near_duplicate_run_seconds": longest_run_seconds,
        "motion_delta_mean": mean_delta,
        "motion_delta_median": median_delta,
        "motion_delta_cv": delta_cv,
        "cadence_outlier_ratio": cadence_outlier_ratio,
        "risk": risk,
        "recommended_action": action,
        "interpolation_recommended": interpolation_recommended,
    }


def _review_ref(prefix: str | None, filename: str, path: Path) -> str:
    if prefix:
        return f"{prefix.rstrip('/')}/{filename}"
    return path.resolve().as_uri()


def _review_artifact(path: Path, *, ref: str) -> dict[str, Any]:
    artifact = artifact_for_path(path)
    artifact["ref"] = ref
    return artifact


def _source_artifact(path: Path, *, ref: str | None) -> dict[str, Any]:
    artifact = artifact_for_path(path)
    if ref:
        artifact["ref"] = ref
    return artifact


def run_generated_shot_qa(
    artifact_file: str | Path,
    anchor_file: str | Path,
    review_dir: str | Path,
    *,
    policy: Mapping[str, Any],
    ffmpeg_path: str,
    ffprobe_path: str,
    review_ref_prefix: str | None = None,
    artifact_ref: str | None = None,
    anchor_ref: str | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Measure one local candidate and write a deterministic mechanical review pack."""

    artifact_path = Path(artifact_file).resolve()
    anchor_path = Path(anchor_file).resolve()
    if not artifact_path.is_file():
        raise ValueError("generated-shot artifact was not found")
    if not anchor_path.is_file():
        raise ValueError("generated-shot anchor was not found")
    if not str(ffmpeg_path).strip() or not str(ffprobe_path).strip():
        raise ValueError("project-local ffmpeg and ffprobe paths are required")

    output_dir = Path(review_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    first_frame_path = output_dir / "frame-0000.png"
    contact_sheet_path = output_dir / "contact-sheet-2fps.jpg"
    stats_path = output_dir / "consecutive-frame-ssim.log"
    report_path = output_dir / "qa-report.json"

    probe_result = _run(
        command_runner,
        [
            ffprobe_path,
            "-v",
            "error",
            "-count_frames",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(artifact_path),
        ],
        label="ffprobe",
        timeout=120,
    )
    try:
        probe = json.loads(probe_result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("ffprobe returned invalid JSON") from exc
    streams = probe.get("streams") if isinstance(probe, dict) else None
    if not isinstance(streams, list):
        streams = []
    video_stream = next(
        (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise ValueError("generated-shot artifact has no video stream")
    format_data = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    width = video_stream.get("width")
    height = video_stream.get("height")
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise ValueError("ffprobe did not return a valid video width")
    if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
        raise ValueError("ffprobe did not return a valid video height")
    fps = _ratio(video_stream.get("avg_frame_rate")) or _ratio(video_stream.get("r_frame_rate"))
    duration = _number(format_data.get("duration")) or _number(video_stream.get("duration"))
    if fps is None or fps <= 0:
        raise ValueError("ffprobe did not return a valid frame rate")
    if duration is None or duration <= 0:
        raise ValueError("ffprobe did not return a valid duration")
    frame_count_value = _number(video_stream.get("nb_read_frames") or video_stream.get("nb_frames"))
    frame_count = int(frame_count_value) if frame_count_value else round(duration * fps)
    if frame_count < 2:
        raise ValueError("generated-shot artifact must contain at least two frames")

    decode_result = command_runner(
        [
            ffmpeg_path,
            "-v",
            "error",
            "-i",
            str(artifact_path),
            "-map",
            "0:v:0",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    decode_error_count = 0 if decode_result.returncode == 0 else 1

    contact_sample_count = min(8, max(2, round(duration * 2)))
    contact_sample_fps = contact_sample_count / duration
    _run(
        command_runner,
        [
            ffmpeg_path,
            "-y",
            "-v",
            "error",
            "-i",
            str(artifact_path),
            "-frames:v",
            "1",
            str(first_frame_path),
        ],
        label="first-frame extraction",
        timeout=120,
    )
    _run(
        command_runner,
        [
            ffmpeg_path,
            "-y",
            "-v",
            "error",
            "-i",
            str(artifact_path),
            "-vf",
            f"fps={contact_sample_fps:.8f},scale=360:-2,tile=4x2:nb_frames={contact_sample_count}",
            "-frames:v",
            "1",
            str(contact_sheet_path),
        ],
        label="contact-sheet extraction",
        timeout=180,
    )
    first_frame_ssim_result = _run(
        command_runner,
        [
            ffmpeg_path,
            "-v",
            "info",
            "-i",
            str(anchor_path),
            "-i",
            str(artifact_path),
            "-filter_complex",
            f"[0:v]scale={width}:{height}:flags=lanczos,setpts=PTS-STARTPTS[reference];[1:v]select=eq(n\\,0),setpts=PTS-STARTPTS[candidate];[reference][candidate]ssim",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ],
        label="first-frame SSIM",
        timeout=180,
    )
    first_frame_ssim = _parse_ssim(
        f"{first_frame_ssim_result.stdout}\n{first_frame_ssim_result.stderr}",
        label="first-frame SSIM",
    )

    stats_filter = f"[0:v]split=2[previous][current];[previous]trim=end_frame={frame_count - 1},setpts=PTS-STARTPTS[a];[current]trim=start_frame=1,setpts=PTS-STARTPTS[b];[a][b]ssim=stats_file='{stats_path}'"
    _run(
        command_runner,
        [
            ffmpeg_path,
            "-v",
            "error",
            "-i",
            str(artifact_path),
            "-filter_complex",
            stats_filter,
            "-f",
            "null",
            "-",
        ],
        label="consecutive-frame SSIM",
        timeout=600,
    )
    consecutive_scores = _parse_ssim_stats(stats_path)
    median_ssim = statistics.median(consecutive_scores)
    hard_cut_threshold = _number(policy.get("hard_cut_ssim_threshold"))
    hard_cut_threshold = 0.85 if hard_cut_threshold is None else hard_cut_threshold
    outlier_margin = _number(policy.get("hard_cut_outlier_margin"))
    outlier_margin = 0.1 if outlier_margin is None else outlier_margin
    internal_cut_transitions = [index for index, score in enumerate(consecutive_scores) if score < hard_cut_threshold and score <= median_ssim - outlier_margin]
    motion_cadence = _motion_cadence(
        consecutive_scores,
        fps=fps,
        policy=policy,
    )

    first_ref = _review_ref(review_ref_prefix, first_frame_path.name, first_frame_path)
    contact_ref = _review_ref(review_ref_prefix, contact_sheet_path.name, contact_sheet_path)
    report_ref = _review_ref(review_ref_prefix, report_path.name, report_path)
    first_artifact = _review_artifact(first_frame_path, ref=first_ref)
    contact_artifact = _review_artifact(contact_sheet_path, ref=contact_ref)
    audio_stream_count = sum(1 for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio")
    evidence = {
        "width": width,
        "height": height,
        "fps": fps,
        "duration_seconds": duration,
        "audio_stream_count": audio_stream_count,
        "decode_error_count": decode_error_count,
        "first_frame_ssim": first_frame_ssim,
        "internal_cut_transitions": internal_cut_transitions,
        "consecutive_frame_ssim": {
            "sample_count": len(consecutive_scores),
            "median": median_ssim,
            "minimum": min(consecutive_scores),
            "hard_cut_threshold": hard_cut_threshold,
            "outlier_margin": outlier_margin,
        },
        "motion_cadence": motion_cadence,
        "review_artifacts": [first_artifact, contact_artifact],
    }
    report = {
        "contract_version": LOCAL_GENERATED_SHOT_QA_EVIDENCE_VERSION,
        "mechanical_only": True,
        "final_approval": False,
        "artifact": _source_artifact(artifact_path, ref=artifact_ref),
        "anchor": _source_artifact(anchor_path, ref=anchor_ref),
        "checks": [
            {
                "name": "ffprobe_and_full_decode",
                "evidence_type": "empirical_observation",
                "passed": decode_error_count == 0,
            },
            {
                "name": "first_frame_anchor_ssim",
                "evidence_type": "empirical_observation",
                "actual": first_frame_ssim,
            },
            {
                "name": "consecutive_frame_ssim",
                "evidence_type": "empirical_observation",
                "internal_cut_transitions": internal_cut_transitions,
            },
            {
                "name": "motion_cadence",
                "evidence_type": "empirical_observation",
                "classification": motion_cadence["classification"],
                "risk": motion_cadence["risk"],
                "recommended_action": motion_cadence["recommended_action"],
            },
        ],
        "evidence": evidence,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    evidence["review_artifacts"].append(_review_artifact(report_path, ref=report_ref))
    return {
        "contract_version": LOCAL_GENERATED_SHOT_QA_EVIDENCE_VERSION,
        "mechanical_only": True,
        "final_approval": False,
        "artifact": _source_artifact(artifact_path, ref=artifact_ref),
        "anchor": _source_artifact(anchor_path, ref=anchor_ref),
        "evidence": evidence,
        "executors": {
            "ffmpeg": Path(ffmpeg_path).name,
            "ffprobe": Path(ffprobe_path).name,
        },
    }
