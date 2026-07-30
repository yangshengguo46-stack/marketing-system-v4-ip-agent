from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.personal_ip.media_execution import normalize_media_execution_receipt
from deerflow.personal_ip.remotion_renderer import render_remotion_scene
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins.personal_ip_tools import _personal_ip_render_local_remotion_scene


def _touch(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _renderer_root(tmp_path: Path) -> Path:
    root = tmp_path / "renderers"
    for relative in (
        "package.json",
        "package-lock.json",
        "version-policy.json",
        "verify-pins.mjs",
        "prepare-hyperframes.mjs",
        "render-remotion.mjs",
        "remotion/index.ts",
        "remotion/root.tsx",
        "remotion/scene.tsx",
        "node_modules/hyperframes/dist/cli.js",
        "node_modules/gsap/dist/gsap.min.js",
        "node_modules/@remotion/cli/remotion-cli.js",
        "node_modules/remotion/package.json",
    ):
        _touch(root / relative)
    return root


def test_remotion_renderer_returns_normalizable_verified_receipt(tmp_path: Path) -> None:
    root = _renderer_root(tmp_path)
    node = _touch(tmp_path / "node")
    ffmpeg = _touch(tmp_path / "ffmpeg")
    ffprobe = _touch(tmp_path / "ffprobe")
    browser = _touch(tmp_path / "chromium")
    media = _touch(tmp_path / "scene" / "background.png", "image")
    spec = _touch(
        tmp_path / "scene" / "scene.json",
        json.dumps(
            {
                "contract_version": "personal-ip-render-scene-v1",
                "canvas": {"width": 1280, "height": 720, "fps": 30},
                "duration_seconds": 3,
                "headline": "Scene",
                "media": [{"file": media.name, "kind": "image"}],
            }
        ),
    )
    output = tmp_path / "output" / "candidate.mp4"

    def runner(command, **_kwargs):
        if command[1] == "--version":
            return subprocess.CompletedProcess(command, 0, stdout="v26.4.0\n", stderr="")
        if str(command[1]).endswith("verify-pins.mjs"):
            return subprocess.CompletedProcess(command, 0, stdout="pins verified\n", stderr="")
        if str(command[1]).endswith("render-remotion.mjs"):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"deterministic-mp4")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[0] == str(ffprobe):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "streams": [
                            {
                                "index": 0,
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 1280,
                                "height": 720,
                                "r_frame_rate": "30/1",
                                "nb_frames": "90",
                            }
                        ],
                        "format": {"duration": "3.0", "size": "17"},
                    }
                ),
                stderr="",
            )
        raise AssertionError(command)

    receipt = render_remotion_scene(
        spec,
        output,
        scene_spec_ref="/mnt/user-data/workspace/scene/scene.json",
        output_ref="/mnt/user-data/outputs/video-renders/run/candidate.mp4",
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        browser_path=browser,
        task_id="local-remotion-run",
        renderer_root=root,
        node_path=node,
        command_runner=runner,
    )
    normalized = normalize_media_execution_receipt(receipt, entity_type="candidate")

    assert normalized["event_type"] == "shot_generation_completed"
    assert receipt["parameters"]["deterministic_mode"] is True
    assert receipt["parameters"]["browser_graphics_backend"] == "swiftshader"
    assert receipt["inputs"][1]["ref"] == "/mnt/user-data/workspace/scene/background.png"
    assert receipt["outputs"][0]["sha256"]
    assert receipt["cost"]["amount"] == 0


def test_remotion_renderer_rejects_media_escape(tmp_path: Path) -> None:
    root = _renderer_root(tmp_path)
    node = _touch(tmp_path / "node")
    ffmpeg = _touch(tmp_path / "ffmpeg")
    ffprobe = _touch(tmp_path / "ffprobe")
    browser = _touch(tmp_path / "chromium")
    _touch(tmp_path / "outside.png", "image")
    spec = _touch(
        tmp_path / "scene" / "scene.json",
        json.dumps(
            {
                "contract_version": "personal-ip-render-scene-v1",
                "canvas": {"width": 1280, "height": 720, "fps": 30},
                "duration_seconds": 3,
                "headline": "Scene",
                "media": [{"file": "../outside.png", "kind": "image"}],
            }
        ),
    )

    def runner(command, **_kwargs):
        if command[1] == "--version":
            return subprocess.CompletedProcess(command, 0, stdout="v26.4.0\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="pins verified\n", stderr="")

    with pytest.raises(ValueError, match="safe relative paths|escapes"):
        render_remotion_scene(
            spec,
            tmp_path / "output.mp4",
            scene_spec_ref="/mnt/user-data/workspace/scene/scene.json",
            output_ref="/mnt/user-data/outputs/output.mp4",
            ffmpeg_path=ffmpeg,
            ffprobe_path=ffprobe,
            browser_path=browser,
            task_id="local-remotion-run",
            renderer_root=root,
            node_path=node,
            command_runner=runner,
        )


@pytest.mark.asyncio
async def test_remotion_native_tool_seals_render_as_candidate_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = _touch(tmp_path / "candidate.mp4", "rendered")
    video_productions = SimpleNamespace(
        append_event=AsyncMock(
            return_value={
                "id": "video-production-1",
                "events": [{"event_type": "shot_generation_completed"}],
            }
        )
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            video_productions=video_productions,
        )
    )
    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_tools._video_production_mode",
        AsyncMock(return_value=("video-production-1", "faceless_material")),
    )
    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_tools._local_remotion_render_paths",
        lambda **_kwargs: (
            tmp_path / "scene.json",
            output,
            "/mnt/user-data/outputs/video-renders/run/candidate.mp4",
            "local-remotion-run",
            str(tmp_path / "ffmpeg"),
            str(tmp_path / "ffprobe"),
            str(tmp_path / "chromium"),
        ),
    )
    receipt = {
        "contract_version": "personal-ip-media-execution-v1",
        "capability": "video_generation",
        "provider": "remotion",
        "executor": "source-owned-remotion-image-sequence-project-ffmpeg",
        "model": "remotion-4.0.488",
        "status": "succeeded",
        "task_id": "local-remotion-run",
        "request_id": None,
        "started_at": "2026-07-23T01:00:00Z",
        "completed_at": "2026-07-23T01:00:10Z",
        "parameters": {"deterministic_mode": True},
        "inputs": [{"ref": "/mnt/user-data/workspace/scene.json"}],
        "outputs": [
            {
                "ref": "/mnt/user-data/outputs/video-renders/run/candidate.mp4",
                "sha256": "a" * 64,
                "size_bytes": 8,
            }
        ],
        "cost": {"status": "known", "amount": 0, "currency": "CNY"},
        "failure": None,
    }
    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_tools.render_remotion_scene",
        lambda *_args, **_kwargs: json.loads(json.dumps(receipt)),
    )

    payload = json.loads(
        await _personal_ip_render_local_remotion_scene(
            SimpleNamespace(context={"user_id": "user-1", "thread_id": "thread-1"}),
            production_id="video-production-1",
            event_key="render-shot-1",
            shot_id="shot-1",
            candidate_id="candidate-1",
            scene_spec_path="/mnt/user-data/workspace/scene.json",
        )
    )

    assert payload["operation_status"] == "ok"
    kwargs = video_productions.append_event.await_args.kwargs
    assert kwargs["event_type"] == "shot_generation_completed"
    assert kwargs["entity_type"] == "candidate"
    assert kwargs["entity_id"] == "candidate-1"
    assert kwargs["provider"] == "remotion"
    assert kwargs["payload"]["parameters"]["shot_id"] == "shot-1"
