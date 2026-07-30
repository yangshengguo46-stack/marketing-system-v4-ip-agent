"""Pinned, project-local HyperFrames preparation, checking and rendering."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deerflow.personal_ip.video_acceptance import artifact_for_path

HYPERFRAMES_SCENE_CONTRACT_VERSION = "personal-ip-render-scene-v1"
HYPERFRAMES_RECEIPT_VERSION = "personal-ip-hyperframes-receipt-v1"
HYPERFRAMES_VERSION = "0.7.57"
GSAP_VERSION = "3.14.2"


def default_renderer_root() -> Path:
    """Resolve the source-owned renderer package in this checkout."""

    return Path(__file__).resolve().parents[5] / "product" / "video-renderers"


def _run(
    command_runner: Callable[..., subprocess.CompletedProcess[str]],
    command: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    label: str,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    result = command_runner(
        command,
        cwd=cwd,
        env=dict(env) if env is not None else None,
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


def _json_output(result: subprocess.CompletedProcess[str], *, label: str) -> dict[str, Any]:
    output = (result.stdout or "").strip()
    try:
        whole = json.loads(output)
    except json.JSONDecodeError:
        whole = None
    if isinstance(whole, dict):
        return whole
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    decoder = json.JSONDecoder()
    for index, character in enumerate(output):
        if character != "{":
            continue
        try:
            value, _end = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError(f"{label} did not return a JSON object")


def _require_file(path: str | Path, *, label: str) -> Path:
    result = Path(path).resolve()
    if not result.is_file():
        raise ValueError(f"{label} was not found")
    return result


def _node_major(node_path: Path, *, command_runner: Callable[..., subprocess.CompletedProcess[str]]) -> int:
    result = _run(
        command_runner,
        [str(node_path), "--version"],
        cwd=node_path.parent,
        label="Node.js version check",
        timeout=30,
    )
    value = (result.stdout or "").strip().lstrip("v").split(".", 1)[0]
    if not value.isdigit():
        raise ValueError("Node.js returned an invalid version")
    return int(value)


def _tool_environment(
    *,
    ffmpeg_path: Path,
    ffprobe_path: Path,
    browser_path: Path,
) -> dict[str, str]:
    return {
        **os.environ,
        "HYPERFRAMES_FFMPEG_PATH": str(ffmpeg_path),
        "HYPERFRAMES_FFPROBE_PATH": str(ffprobe_path),
        "PRODUCER_HEADLESS_SHELL_PATH": str(browser_path),
        "HYPERFRAMES_SKIP_SKILLS": "1",
        "NO_UPDATE_NOTIFIER": "1",
    }


def verify_hyperframes_install(
    *,
    renderer_root: str | Path | None = None,
    node_path: str | Path | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Verify exact source, lockfile and installed dependency versions."""

    root = Path(renderer_root or default_renderer_root()).resolve()
    node = _require_file(node_path or shutil.which("node") or "", label="Node.js")
    if _node_major(node, command_runner=command_runner) < 22:
        raise ValueError("HyperFrames requires Node.js 22 or newer")
    required = (
        root / "package.json",
        root / "package-lock.json",
        root / "version-policy.json",
        root / "verify-pins.mjs",
        root / "prepare-hyperframes.mjs",
        root / "node_modules" / "hyperframes" / "dist" / "cli.js",
        root / "node_modules" / "gsap" / "dist" / "gsap.min.js",
    )
    for path in required:
        _require_file(path, label=path.name)
    result = _run(
        command_runner,
        [str(node), str(root / "verify-pins.mjs")],
        cwd=root,
        label="HyperFrames pin verification",
        timeout=60,
    )
    return {
        "renderer": "hyperframes",
        "renderer_version": HYPERFRAMES_VERSION,
        "animation_runtime": "gsap",
        "animation_runtime_version": GSAP_VERSION,
        "node_major": _node_major(node, command_runner=command_runner),
        "verification": " ".join((result.stdout or "").split()),
    }


def _artifact(path: Path, *, ref: str) -> dict[str, Any]:
    value = artifact_for_path(path)
    value["ref"] = ref
    return value


def _relative_artifacts(root: Path, *, ref_prefix: str, suffixes: set[str]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in suffixes:
            relative = path.relative_to(root).as_posix()
            artifacts.append(_artifact(path, ref=f"{ref_prefix.rstrip('/')}/{relative}"))
    return artifacts


def prepare_and_check_hyperframes_scene(
    scene_spec_path: str | Path,
    project_dir: str | Path,
    *,
    scene_spec_ref: str,
    output_ref_prefix: str,
    ffmpeg_path: str | Path,
    ffprobe_path: str | Path,
    browser_path: str | Path,
    renderer_root: str | Path | None = None,
    node_path: str | Path | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Compile one scene, run the full browser gate and write a preview pack."""

    root = Path(renderer_root or default_renderer_root()).resolve()
    node = _require_file(node_path or shutil.which("node") or "", label="Node.js")
    ffmpeg = _require_file(ffmpeg_path, label="project-local FFmpeg")
    ffprobe = _require_file(ffprobe_path, label="project-local FFprobe")
    browser = _require_file(browser_path, label="Chromium browser")
    spec = _require_file(scene_spec_path, label="HyperFrames scene spec")
    output = Path(project_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    runtime = verify_hyperframes_install(
        renderer_root=root,
        node_path=node,
        command_runner=command_runner,
    )

    prepared_result = _run(
        command_runner,
        [str(node), str(root / "prepare-hyperframes.mjs"), str(spec), str(output)],
        cwd=root,
        label="HyperFrames scene preparation",
        timeout=120,
    )
    prepared = _json_output(prepared_result, label="HyperFrames scene preparation")
    cli = root / "node_modules" / "hyperframes" / "dist" / "cli.js"
    environment = _tool_environment(
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        browser_path=browser,
    )
    check_result = _run(
        command_runner,
        [
            str(node),
            str(cli),
            "check",
            str(output),
            "--json",
            "--snapshots",
            "--at-transitions",
            "--frame-check",
        ],
        cwd=root,
        env=environment,
        label="HyperFrames browser check",
        timeout=600,
    )
    check = _json_output(check_result, label="HyperFrames browser check")
    if check.get("ok") is not True:
        raise ValueError("HyperFrames browser check did not pass")
    check_report = output / "hyperframes-check.json"
    check_report.write_text(
        json.dumps(check, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    artifacts = [
        _artifact(output / "index.html", ref=f"{output_ref_prefix.rstrip('/')}/index.html"),
        _artifact(
            output / "index.motion.json",
            ref=f"{output_ref_prefix.rstrip('/')}/index.motion.json",
        ),
        _artifact(check_report, ref=f"{output_ref_prefix.rstrip('/')}/hyperframes-check.json"),
    ]
    artifacts.extend(
        _relative_artifacts(
            output,
            ref_prefix=output_ref_prefix,
            suffixes={".png"},
        )
    )
    return {
        "contract_version": HYPERFRAMES_RECEIPT_VERSION,
        "status": "preview_ready",
        "renderer": runtime,
        "source_spec": _artifact(spec, ref=scene_spec_ref),
        "compiled": prepared,
        "check": {
            "ok": True,
            "lint_errors": len((check.get("lint") or {}).get("errors") or []),
            "runtime_errors": len((check.get("runtime") or {}).get("errors") or []),
        },
        "artifacts": artifacts,
        "render_requires_preview_approval": True,
    }


def render_approved_hyperframes_scene(
    project_dir: str | Path,
    output_path: str | Path,
    *,
    output_ref: str,
    approval_ref: str,
    ffmpeg_path: str | Path,
    ffprobe_path: str | Path,
    browser_path: str | Path,
    renderer_root: str | Path | None = None,
    node_path: str | Path | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Render an already checked scene after an explicit preview approval."""

    approval = " ".join(str(approval_ref or "").split())
    if not approval or len(approval) > 2_048:
        raise ValueError("approval_ref is required before HyperFrames rendering")
    root = Path(renderer_root or default_renderer_root()).resolve()
    node = _require_file(node_path or shutil.which("node") or "", label="Node.js")
    ffmpeg = _require_file(ffmpeg_path, label="project-local FFmpeg")
    ffprobe = _require_file(ffprobe_path, label="project-local FFprobe")
    browser = _require_file(browser_path, label="Chromium browser")
    project = Path(project_dir).resolve()
    _require_file(project / "index.html", label="checked HyperFrames scene")
    check_report = _require_file(project / "hyperframes-check.json", label="HyperFrames check report")
    check = json.loads(check_report.read_text(encoding="utf-8"))
    if not isinstance(check, dict) or check.get("ok") is not True:
        raise ValueError("HyperFrames check report is not passing")
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    runtime = verify_hyperframes_install(
        renderer_root=root,
        node_path=node,
        command_runner=command_runner,
    )
    cli = root / "node_modules" / "hyperframes" / "dist" / "cli.js"
    started_at = datetime.now(UTC)
    _run(
        command_runner,
        [
            str(node),
            str(cli),
            "render",
            str(project),
            "--output",
            str(target),
            "--workers",
            "1",
            "--quality",
            "high",
            "--strict",
            "--no-best-effort",
        ],
        cwd=root,
        env=_tool_environment(
            ffmpeg_path=ffmpeg,
            ffprobe_path=ffprobe,
            browser_path=browser,
        ),
        label="HyperFrames render",
        timeout=3_600,
    )
    _require_file(target, label="HyperFrames render output")
    completed_at = datetime.now(UTC)
    return {
        "contract_version": HYPERFRAMES_RECEIPT_VERSION,
        "status": "succeeded",
        "renderer": runtime,
        "approval_ref": approval,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "output": _artifact(target, ref=output_ref),
        "cost": {"status": "known", "amount": 0, "currency": "CNY", "basis": "local render"},
    }
