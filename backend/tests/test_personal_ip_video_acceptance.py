from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from deerflow.personal_ip.video_acceptance import run_delivery_qa, verify_local_receipt_outputs


def _completed(stdout: str = "", *, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["tool"], returncode, stdout=stdout, stderr=stderr)


def test_verify_local_receipt_outputs_detects_download_tampering(tmp_path: Path) -> None:
    output = tmp_path / "shot.mp4"
    output.write_bytes(b"downloaded-video")
    receipt = {
        "status": "succeeded",
        "outputs": [
            {
                "ref": output.resolve().as_uri(),
                "sha256": "0" * 64,
                "size_bytes": output.stat().st_size,
            }
        ],
    }

    with pytest.raises(ValueError, match="SHA-256"):
        verify_local_receipt_outputs(receipt)


def test_run_delivery_qa_probes_decodes_and_checks_delivery_spec(tmp_path: Path) -> None:
    output = tmp_path / "final.mp4"
    output.write_bytes(b"local-final-video")
    probe = {
        "format": {"duration": "2.000000", "format_name": "mov,mp4"},
        "streams": [
            {"codec_type": "video", "codec_name": "mpeg4", "width": 360, "height": 640, "r_frame_rate": "25/1"},
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100", "channels": 1},
        ],
    }
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if "-show_format" in command:
            return _completed(json.dumps(probe))
        return _completed()

    result = run_delivery_qa(
        output,
        delivery_spec={
            "aspect_ratio": "9:16",
            "duration_seconds": 2,
            "duration_tolerance_seconds": 0.1,
            "require_audio": True,
        },
        ffmpeg_path="/tools/ffmpeg",
        ffprobe_path="/tools/ffprobe",
        command_runner=fake_run,
    )

    assert result["contract_version"] == "personal-ip-delivery-qa-v1"
    assert result["passed"] is True
    assert result["artifact"]["sha256"]
    assert result["probe"]["width"] == 360
    assert {check["name"] for check in result["checks"] if check["passed"]} >= {
        "decode",
        "duration",
        "aspect_ratio",
        "audio_stream",
    }
    assert calls[0][0] == "/tools/ffprobe"
    assert calls[1][0] == "/tools/ffmpeg"


def test_run_delivery_qa_reports_failed_checks_without_claiming_delivery(tmp_path: Path) -> None:
    output = tmp_path / "final.mp4"
    output.write_bytes(b"bad-final-video")
    probe = {
        "format": {"duration": "1.0", "format_name": "mov,mp4"},
        "streams": [{"codec_type": "video", "codec_name": "mpeg4", "width": 640, "height": 360, "r_frame_rate": "25/1"}],
    }

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        if "-show_format" in command:
            return _completed(json.dumps(probe))
        return _completed(returncode=1, stderr="decode failed")

    result = run_delivery_qa(
        output,
        delivery_spec={"aspect_ratio": "9:16", "duration_seconds": 2, "require_audio": True},
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        command_runner=fake_run,
    )

    assert result["passed"] is False
    failed = {check["name"] for check in result["checks"] if not check["passed"]}
    assert failed == {"decode", "duration", "aspect_ratio", "audio_stream"}
