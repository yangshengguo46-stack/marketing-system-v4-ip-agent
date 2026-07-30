from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.personal_ip.frame_interpolation import interpolate_video_candidate
from deerflow.personal_ip.media_execution import normalize_media_execution_receipt
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins.personal_ip_tools import (
    _personal_ip_interpolate_video_candidate,
    personal_ip_interpolate_video_candidate_tool,
)
from deerflow.tools.tools import BUILTIN_TOOLS


def _touch(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _probe(*, fps: str, duration: str, frames: str) -> str:
    return json.dumps(
        {
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 640,
                    "height": 360,
                    "pix_fmt": "yuv420p",
                    "avg_frame_rate": fps,
                    "r_frame_rate": fps,
                    "nb_frames": frames,
                    "nb_read_frames": frames,
                }
            ],
            "format": {"duration": duration, "size": "1024"},
        }
    )


def test_frame_interpolation_uses_motion_compensation_and_returns_verified_candidate(
    tmp_path: Path,
) -> None:
    source = _touch(tmp_path / "source.mp4", b"source-video")
    ffmpeg = _touch(tmp_path / "ffmpeg")
    ffprobe = _touch(tmp_path / "ffprobe")
    output = tmp_path / "output" / "candidate.mp4"
    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0] == str(ffprobe):
            is_output = ".partial.mp4" in command[-1]
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=_probe(
                    fps="48/1" if is_output else "24/1",
                    duration="4.000000",
                    frames="192" if is_output else "96",
                ),
                stderr="",
            )
        if "-vf" in command:
            Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(command[-1]).write_bytes(b"interpolated-video")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[-1] == "-":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(command)

    receipt = interpolate_video_candidate(
        source,
        output,
        source_ref="/mnt/user-data/outputs/source.mp4",
        output_ref="/mnt/user-data/outputs/video-interpolations/run/candidate.mp4",
        target_fps=48,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        task_id="local-frame-interpolation-run",
        command_runner=runner,
    )
    normalized = normalize_media_execution_receipt(receipt, entity_type="candidate")

    render_command = next(command for command in calls if "-vf" in command)
    filter_value = render_command[render_command.index("-vf") + 1]
    assert "minterpolate=fps=48" in filter_value
    assert "mi_mode=mci" in filter_value
    assert "mc_mode=aobmc" in filter_value
    assert "mi_mode=dup" not in filter_value
    assert receipt["parameters"]["motion_compensated"] is True
    assert receipt["parameters"]["duplicate_frame_conversion"] is False
    assert receipt["parameters"]["source_fps"] == 24
    assert receipt["parameters"]["target_fps"] == 48
    assert receipt["outputs"][0]["sha256"]
    assert normalized["event_type"] == "shot_generation_completed"
    assert normalized["provider"] == "ffmpeg"
    assert output.read_bytes() == b"interpolated-video"


def test_frame_interpolation_rejects_non_increasing_fps(tmp_path: Path) -> None:
    source = _touch(tmp_path / "source.mp4")
    ffmpeg = _touch(tmp_path / "ffmpeg")
    ffprobe = _touch(tmp_path / "ffprobe")

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=_probe(fps="24/1", duration="4", frames="96"),
            stderr="",
        )

    with pytest.raises(ValueError, match="higher than the source"):
        interpolate_video_candidate(
            source,
            tmp_path / "output.mp4",
            source_ref="/mnt/user-data/outputs/source.mp4",
            output_ref="/mnt/user-data/outputs/output.mp4",
            target_fps=24,
            ffmpeg_path=ffmpeg,
            ffprobe_path=ffprobe,
            task_id="same-fps",
            command_runner=runner,
        )


@pytest.mark.asyncio
async def test_native_interpolation_tool_records_new_candidate_and_followup_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _touch(tmp_path / "source.mp4", b"source")
    output = _touch(tmp_path / "candidate.mp4", b"enhanced")
    source_sha = "a" * 64
    repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "video-production-1",
                "production_mode": "generative_cinematic",
                "source": {"production_mode": "generative_cinematic"},
                "events": [
                    {
                        "event_type": "shot_generation_completed",
                        "status": "succeeded",
                        "entity_type": "candidate",
                        "entity_id": "shot-1:candidate-1",
                        "payload": {
                            "outputs": [
                                {
                                    "ref": "/mnt/user-data/outputs/source.mp4",
                                    "sha256": source_sha,
                                    "size_bytes": 6,
                                }
                            ]
                        },
                    }
                ],
            }
        ),
        append_event=AsyncMock(
            return_value={
                "id": "video-production-1",
                "events": [{"event_type": "shot_generation_completed"}],
            }
        ),
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            video_productions=repository,
        )
    )
    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_tools._local_frame_interpolation_paths",
        lambda **_kwargs: (
            source,
            output,
            "/mnt/user-data/outputs/video-interpolations/run/candidate.mp4",
            "local-frame-interpolation-run",
            str(tmp_path / "ffmpeg"),
            str(tmp_path / "ffprobe"),
        ),
    )
    receipt = {
        "contract_version": "personal-ip-media-execution-v1",
        "capability": "video_generation",
        "provider": "ffmpeg",
        "executor": "project-ffmpeg-minterpolate",
        "model": "personal-ip-local-frame-interpolation-v1",
        "status": "succeeded",
        "task_id": "local-frame-interpolation-run",
        "request_id": None,
        "started_at": "2026-07-24T01:00:00Z",
        "completed_at": "2026-07-24T01:00:10Z",
        "parameters": {
            "source_fps": 24,
            "target_fps": 48,
            "motion_compensated": True,
        },
        "inputs": [
            {
                "ref": "/mnt/user-data/outputs/source.mp4",
                "sha256": source_sha,
                "size_bytes": 6,
            }
        ],
        "outputs": [
            {
                "ref": "/mnt/user-data/outputs/video-interpolations/run/candidate.mp4",
                "sha256": "b" * 64,
                "size_bytes": 8,
            }
        ],
        "cost": {"status": "known", "amount": 0, "currency": "CNY"},
        "failure": None,
    }
    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_tools.interpolate_video_candidate",
        lambda *_args, **_kwargs: json.loads(json.dumps(receipt)),
    )

    result = json.loads(
        await _personal_ip_interpolate_video_candidate(
            SimpleNamespace(context={"user_id": "user-1", "thread_id": "thread-1"}),
            production_id="video-production-1",
            event_key="interpolate:shot-1:candidate-2",
            shot_id="shot-1",
            source_candidate_id="shot-1:candidate-1",
            output_candidate_id="shot-1:candidate-2",
            artifact_path="/mnt/user-data/outputs/source.mp4",
            target_fps=48,
        )
    )

    assert result["operation_status"] == "ok"
    assert result["next_required_actions"] == ["generated_shot_qa", "human_selection"]
    kwargs = repository.append_event.await_args.kwargs
    assert kwargs["event_type"] == "shot_generation_completed"
    assert kwargs["entity_id"] == "shot-1:candidate-2"
    assert kwargs["payload"]["parameters"]["source_candidate_id"] == "shot-1:candidate-1"
    assert kwargs["payload"]["parameters"]["requires_fresh_qa"] is True
    assert personal_ip_interpolate_video_candidate_tool.name in {tool.name for tool in BUILTIN_TOOLS}
