"""Source-owned deterministic Remotion scene rendering."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from deerflow.personal_ip.hyperframes_renderer import (
    default_renderer_root,
    verify_hyperframes_install,
)
from deerflow.personal_ip.video_acceptance import artifact_for_path

REMOTION_VERSION = "4.0.488"
REMOTION_SCENE_CONTRACT_VERSION = "personal-ip-render-scene-v1"


def _required_file(path: str | Path, *, label: str) -> Path:
    result = Path(path).resolve()
    if not result.is_file():
        raise ValueError(f"{label} was not found")
    return result


def _run(
    command_runner: Callable[..., subprocess.CompletedProcess[str]],
    command: list[str],
    *,
    cwd: Path,
    label: str,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    result = command_runner(
        command,
        cwd=cwd,
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


def _artifact(path: Path, *, ref: str) -> dict[str, Any]:
    value = artifact_for_path(path)
    value["ref"] = ref
    return value


def _virtual_media_ref(spec_ref: str, media_file: str) -> str:
    base = PurePosixPath(spec_ref)
    relative = PurePosixPath(media_file)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("scene media paths must be safe relative paths")
    return str(base.parent / relative)


def render_remotion_scene(
    scene_spec_path: str | Path,
    output_path: str | Path,
    *,
    scene_spec_ref: str,
    output_ref: str,
    ffmpeg_path: str | Path,
    ffprobe_path: str | Path,
    browser_path: str | Path,
    task_id: str,
    renderer_root: str | Path | None = None,
    node_path: str | Path | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Render one local scene and return a validated media-execution receipt."""

    root = Path(renderer_root or default_renderer_root()).resolve()
    node = _required_file(node_path or shutil.which("node") or "", label="Node.js")
    ffmpeg = _required_file(ffmpeg_path, label="project-local FFmpeg")
    ffprobe = _required_file(ffprobe_path, label="project-local FFprobe")
    browser = _required_file(browser_path, label="Chromium browser")
    spec_path = _required_file(scene_spec_path, label="Remotion scene spec")
    render_script = _required_file(root / "render-remotion.mjs", label="Remotion render script")
    for required in (
        root / "remotion" / "index.ts",
        root / "remotion" / "root.tsx",
        root / "remotion" / "scene.tsx",
        root / "node_modules" / "@remotion" / "cli" / "remotion-cli.js",
        root / "node_modules" / "remotion" / "package.json",
    ):
        _required_file(required, label=required.name)
    runtime = verify_hyperframes_install(
        renderer_root=root,
        node_path=node,
        command_runner=command_runner,
    )
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or spec.get("contract_version") != REMOTION_SCENE_CONTRACT_VERSION:
        raise ValueError(f"scene spec contract_version must be {REMOTION_SCENE_CONTRACT_VERSION}")
    media = spec.get("media")
    if not isinstance(media, list):
        raise ValueError("scene spec media must be an array")
    inputs = [_artifact(spec_path, ref=scene_spec_ref)]
    for index, item in enumerate(media):
        if not isinstance(item, dict):
            raise ValueError(f"media[{index}] must be an object")
        relative = str(item.get("file") or "").strip()
        source = (spec_path.parent / relative).resolve()
        if source != spec_path.parent and not str(source).startswith(f"{spec_path.parent}{os.sep}"):
            raise ValueError(f"media[{index}].file escapes the current task directory")
        inputs.append(
            _artifact(
                _required_file(source, label=f"media[{index}]"),
                ref=_virtual_media_ref(scene_spec_ref, relative),
            )
        )

    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    _run(
        command_runner,
        [
            str(node),
            str(render_script),
            str(spec_path),
            str(target),
            str(browser),
            str(ffmpeg),
        ],
        cwd=root,
        label="deterministic Remotion render",
        timeout=3_600,
    )
    completed_at = datetime.now(UTC)
    _required_file(target, label="Remotion output")
    probe_result = _run(
        command_runner,
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames",
            "-of",
            "json",
            str(target),
        ],
        cwd=root,
        label="Remotion output probe",
        timeout=120,
    )
    probe = json.loads(probe_result.stdout or "{}")
    video_stream = next(
        (item for item in probe.get("streams", []) if isinstance(item, dict) and item.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise ValueError("Remotion output has no video stream")
    runtime["remotion_version"] = REMOTION_VERSION
    return {
        "contract_version": "personal-ip-media-execution-v1",
        "capability": "video_generation",
        "provider": "remotion",
        "executor": "source-owned-remotion-image-sequence-project-ffmpeg",
        "model": f"remotion-{REMOTION_VERSION}",
        "status": "succeeded",
        "task_id": task_id,
        "request_id": None,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "parameters": {
            "scene_contract_version": REMOTION_SCENE_CONTRACT_VERSION,
            "canvas": spec.get("canvas"),
            "duration_seconds": spec.get("duration_seconds"),
            "deterministic_mode": True,
            "browser_graphics_backend": "swiftshader",
            "renderer_runtime": runtime,
            "probe": probe,
        },
        "inputs": inputs,
        "outputs": [_artifact(target, ref=output_ref)],
        "cost": {
            "status": "known",
            "amount": 0,
            "currency": "CNY",
            "basis": "local source-owned render",
        },
        "failure": None,
    }
