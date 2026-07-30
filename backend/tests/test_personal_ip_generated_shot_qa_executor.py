from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.config.paths import Paths
from deerflow.personal_ip.generated_shot_qa import run_generated_shot_qa
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins.personal_ip_tools import _personal_ip_run_local_generated_shot_qa


def _completed(
    stdout: str = "",
    *,
    returncode: int = 0,
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["tool"], returncode, stdout=stdout, stderr=stderr)


def test_local_generated_shot_qa_measures_and_writes_reproducible_review_pack(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "candidate.mp4"
    anchor = tmp_path / "anchor.png"
    review_dir = tmp_path / "review"
    artifact.write_bytes(b"candidate-video")
    anchor.write_bytes(b"anchor-image")
    probe = {
        "format": {
            "duration": "2.000000",
            "format_name": "mov,mp4",
            "bit_rate": "1200000",
        },
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 360,
                "height": 640,
                "pix_fmt": "yuv420p",
                "avg_frame_rate": "25/1",
                "r_frame_rate": "25/1",
                "nb_read_frames": "50",
            }
        ],
    }
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        joined = " ".join(command)
        if command[0] == "/tools/ffprobe":
            return _completed(json.dumps(probe))
        if command[-1].endswith("frame-0000.png"):
            Path(command[-1]).write_bytes(b"first-frame")
            return _completed()
        if command[-1].endswith("contact-sheet-2fps.jpg"):
            Path(command[-1]).write_bytes(b"contact-sheet")
            return _completed()
        if "stats_file=" in joined:
            match = re.search(r"stats_file='([^']+)'", joined)
            assert match is not None
            Path(match.group(1)).write_text(
                "n:1 Y:0.98 U:0.98 V:0.98 All:0.98\nn:2 Y:0.55 U:0.55 V:0.55 All:0.55\nn:3 Y:0.97 U:0.97 V:0.97 All:0.97\n",
                encoding="utf-8",
            )
            return _completed()
        if "[reference][candidate]ssim" in joined:
            return _completed(stderr="SSIM Y:0.93 U:0.93 V:0.93 All:0.93")
        return _completed()

    result = run_generated_shot_qa(
        artifact,
        anchor,
        review_dir,
        policy={
            "expected_width": 360,
            "expected_height": 640,
            "expected_fps": 25,
            "expected_duration_seconds": 2,
            "hard_cut_ssim_threshold": 0.85,
            "hard_cut_outlier_margin": 0.1,
        },
        ffmpeg_path="/tools/ffmpeg",
        ffprobe_path="/tools/ffprobe",
        review_ref_prefix="/mnt/user-data/outputs/video-qa/candidate-1",
        command_runner=fake_run,
    )

    assert result["contract_version"] == "personal-ip-generated-shot-local-evidence-v1"
    assert result["artifact"]["sha256"]
    assert result["anchor"]["sha256"]
    assert result["evidence"]["width"] == 360
    assert result["evidence"]["height"] == 640
    assert result["evidence"]["fps"] == 25
    assert result["evidence"]["duration_seconds"] == 2
    assert result["evidence"]["audio_stream_count"] == 0
    assert result["evidence"]["decode_error_count"] == 0
    assert result["evidence"]["first_frame_ssim"] == 0.93
    assert result["evidence"]["internal_cut_transitions"] == [1]
    assert result["evidence"]["motion_cadence"]["classification"] == "active_motion"
    assert result["evidence"]["motion_cadence"]["near_duplicate_transition_ratio"] == 0
    assert result["evidence"]["motion_cadence"]["interpolation_recommended"] is False
    refs = [item["ref"] for item in result["evidence"]["review_artifacts"]]
    assert refs == [
        "/mnt/user-data/outputs/video-qa/candidate-1/frame-0000.png",
        "/mnt/user-data/outputs/video-qa/candidate-1/contact-sheet-2fps.jpg",
        "/mnt/user-data/outputs/video-qa/candidate-1/qa-report.json",
    ]
    report = json.loads((review_dir / "qa-report.json").read_text(encoding="utf-8"))
    assert report["mechanical_only"] is True
    assert report["final_approval"] is False
    assert {check["evidence_type"] for check in report["checks"]} == {"empirical_observation"}
    assert {check["name"] for check in report["checks"]} == {
        "ffprobe_and_full_decode",
        "first_frame_anchor_ssim",
        "consecutive_frame_ssim",
        "motion_cadence",
    }
    assert calls[0][0] == "/tools/ffprobe"
    assert any("scale=360:640:flags=lanczos" in " ".join(command) for command in calls)


@pytest.mark.asyncio
async def test_native_local_qa_tool_resolves_only_current_thread_files_and_seals_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    paths.ensure_thread_dirs("thread-1", user_id="user-1")
    artifact = paths.sandbox_outputs_dir("thread-1", user_id="user-1") / "candidate.mp4"
    anchor = paths.sandbox_uploads_dir("thread-1", user_id="user-1") / "anchor.png"
    artifact.write_bytes(b"candidate")
    anchor.write_bytes(b"anchor")
    toolchain = paths.base_dir / "toolchains" / "ffmpeg" / "bin"
    toolchain.mkdir(parents=True)
    (toolchain / "ffmpeg").write_text("binary", encoding="utf-8")
    (toolchain / "ffprobe").write_text("binary", encoding="utf-8")

    repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "video-production-1",
                "production_mode": "generative_cinematic",
                "source": {"production_mode": "generative_cinematic"},
            }
        ),
        append_event=AsyncMock(
            return_value={
                "id": "video-production-1",
                "status": "running",
                "events": [],
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
        "deerflow.tools.builtins.personal_ip_tools.get_paths",
        lambda: paths,
    )

    def fake_executor(
        artifact_path: Path,
        anchor_path: Path,
        review_dir: Path,
        **_kwargs,
    ) -> dict:
        review_dir.mkdir(parents=True, exist_ok=True)
        report = review_dir / "qa-report.json"
        report.write_text("{}", encoding="utf-8")
        return {
            "contract_version": "personal-ip-generated-shot-local-evidence-v1",
            "artifact": {"ref": artifact_path.as_uri(), "sha256": "a" * 64},
            "anchor": {"ref": anchor_path.as_uri(), "sha256": "b" * 64},
            "evidence": {
                "width": 360,
                "height": 640,
                "fps": 25,
                "duration_seconds": 2,
                "audio_stream_count": 0,
                "decode_error_count": 0,
                "first_frame_ssim": 0.92,
                "internal_cut_transitions": [],
                "review_artifacts": [
                    {
                        "ref": "/mnt/user-data/outputs/video-qa/review/qa-report.json",
                        "sha256": "c" * 64,
                    }
                ],
            },
        }

    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_tools.run_generated_shot_qa",
        fake_executor,
    )
    runtime = SimpleNamespace(context={"user_id": "user-1", "thread_id": "thread-1"})

    result = json.loads(
        await _personal_ip_run_local_generated_shot_qa(
            runtime,
            production_id="video-production-1",
            event_key="qa:shot-1:candidate-1",
            shot_id="shot-1",
            candidate_id="shot-1:candidate-1",
            artifact_path="/mnt/user-data/outputs/candidate.mp4",
            anchor_path="/mnt/user-data/uploads/anchor.png",
            policy={
                "expected_width": 360,
                "expected_height": 640,
                "expected_fps": 25,
                "expected_duration_seconds": 2,
            },
        )
    )

    assert result["operation_status"] == "ok"
    kwargs = repository.append_event.await_args.kwargs
    assert kwargs["event_type"] == "generated_shot_qa_compiled"
    assert kwargs["status"] == "succeeded"
    assert kwargs["entity_type"] == "candidate"
    assert kwargs["entity_id"] == "shot-1:candidate-1"
    assert kwargs["provider"] == "ffmpeg_ffprobe"
    assert kwargs["input_refs"] == [
        "/mnt/user-data/outputs/candidate.mp4",
        "/mnt/user-data/uploads/anchor.png",
    ]
    assert kwargs["payload"]["artifact"]["ref"] == "/mnt/user-data/outputs/candidate.mp4"
    assert kwargs["payload"]["anchor"]["ref"] == "/mnt/user-data/uploads/anchor.png"
    assert kwargs["payload"]["artifact"]["sha256"] == "a" * 64


@pytest.mark.asyncio
async def test_native_local_qa_tool_rejects_paths_outside_current_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    paths.ensure_thread_dirs("thread-1", user_id="user-1")
    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_tools.get_paths",
        lambda: paths,
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            video_productions=SimpleNamespace(
                get=AsyncMock(
                    return_value={
                        "id": "video-production-1",
                        "production_mode": "generative_cinematic",
                    }
                )
            ),
        )
    )
    runtime = SimpleNamespace(context={"user_id": "user-1", "thread_id": "thread-1"})

    result = json.loads(
        await _personal_ip_run_local_generated_shot_qa(
            runtime,
            production_id="video-production-1",
            event_key="qa:escape",
            shot_id="shot-1",
            candidate_id="candidate-1",
            artifact_path="/tmp/candidate.mp4",
            anchor_path="/mnt/user-data/uploads/anchor.png",
            policy={},
        )
    )

    assert result["status"] == "error"
    assert result["category"] == "invalid_request"
    assert "must start with /mnt/user-data" in result["message"]
