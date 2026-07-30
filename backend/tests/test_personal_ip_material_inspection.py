from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.config.paths import Paths
from deerflow.personal_ip.material_inspection import inspect_local_video_material
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.personal_ip.video_contracts import (
    compile_asset_manifest,
    compile_material_inspection,
    compile_storyboard,
)
from deerflow.tools.builtins.personal_ip_tools import (
    _personal_ip_inspect_local_video_material,
)


def _completed(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["tool"], 0, stdout=stdout, stderr="")


def test_local_material_inspection_extracts_timestamped_mechanical_evidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    probe = {
        "format": {"duration": "10.0"},
        "streams": [
            {
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "25/1",
            }
        ],
    }

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        if command[0] == "/tools/ffprobe":
            return _completed(json.dumps(probe))
        if command[-1].endswith("frame-%03d.jpg"):
            pattern = Path(command[-1])
            for index in range(1, 5):
                Path(str(pattern).replace("%03d", f"{index:03d}")).write_bytes(f"frame-{index}".encode())
        elif command[-1].endswith("contact-sheet.jpg"):
            Path(command[-1]).write_bytes(b"contact-sheet")
        return _completed()

    result = inspect_local_video_material(
        source,
        tmp_path / "review",
        source_in_seconds=2,
        source_out_seconds=6,
        ffmpeg_path="/tools/ffmpeg",
        ffprobe_path="/tools/ffprobe",
        source_ref="/mnt/user-data/uploads/source.mp4",
        review_ref_prefix="/mnt/user-data/outputs/material-inspection/one",
        command_runner=fake_run,
    )
    contract = compile_material_inspection(
        production_id="video-production-1",
        shot_id="shot-1",
        asset_id="asset-1",
        evidence=result,
    )

    assert result["mechanical_only"] is True
    assert result["semantic_assessment_required"] is True
    assert [item["timestamp_seconds"] for item in result["frames"]] == [
        2,
        3,
        4,
        5,
    ]
    assert contract["contract_version"] == "personal-ip-video-material-inspection-v1"
    assert contract["validation"]["passed"] is True
    assert contract["source"]["ref"] == "/mnt/user-data/uploads/source.mp4"


@pytest.mark.asyncio
async def test_native_material_inspection_seals_existing_video_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    paths.ensure_thread_dirs("thread-1", user_id="user-1")
    source = paths.sandbox_uploads_dir("thread-1", user_id="user-1") / "source.mp4"
    source.write_bytes(b"source-video")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    toolchain = paths.base_dir / "toolchains" / "ffmpeg" / "bin"
    toolchain.mkdir(parents=True)
    (toolchain / "ffmpeg").write_text("binary", encoding="utf-8")
    (toolchain / "ffprobe").write_text("binary", encoding="utf-8")
    assets = compile_asset_manifest(
        production_id="video-production-1",
        production_mode="faceless_material",
        assets=[
            {
                "id": "asset-1",
                "type": "owned_video",
                "name": "本人素材",
                "source_ref": "/mnt/user-data/uploads/source.mp4",
                "license": "owner-provided",
                "allowed_for_use": True,
                "sha256": source_sha,
            }
        ],
    )
    storyboard = compile_storyboard(
        production_id="video-production-1",
        production_mode="faceless_material",
        shots=[
            {
                "id": "shot-1",
                "order": 1,
                "duration_seconds": 4,
                "narration_text": "展示经营数据。",
                "visual_subject": "数据看板",
                "visual_query": "dashboard",
                "composition_strategy": "full_bleed",
                "claim_evidence_refs": [],
                "claim_evidence_quotes": {},
                "negative_conditions": [],
                "pass_criteria": ["画面匹配"],
            }
        ],
    )
    production = {
        "id": "video-production-1",
        "production_mode": "faceless_material",
        "events": [
            {"event_type": "asset_manifest_compiled", "payload": assets},
            {"event_type": "storyboard_compiled", "payload": storyboard},
        ],
    }
    repository = SimpleNamespace(
        get=AsyncMock(return_value=production),
        append_event=AsyncMock(return_value={"id": "video-production-1", "events": []}),
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            video_productions=repository,
        )
    )
    monkeypatch.setattr("deerflow.tools.builtins.personal_ip_tools.get_paths", lambda: paths)

    def fake_inspection(*_args, **kwargs) -> dict:
        review_dir = Path(_args[1])
        review_dir.mkdir(parents=True, exist_ok=True)
        frame = review_dir / "frame-001.jpg"
        frame.write_bytes(b"frame")
        digest = hashlib.sha256(frame.read_bytes()).hexdigest()
        return {
            "source": {
                "ref": kwargs["source_ref"],
                "sha256": source_sha,
            },
            "source_in_seconds": 2,
            "source_out_seconds": 6,
            "probe": {
                "duration_seconds": 10,
                "width": 1920,
                "height": 1080,
                "fps": 25,
                "audio_stream_count": 0,
            },
            "frames": [
                {
                    "timestamp_seconds": 2,
                    "artifact": {
                        "ref": f"{kwargs['review_ref_prefix']}/frame-001.jpg",
                        "sha256": digest,
                    },
                },
                {
                    "timestamp_seconds": 5,
                    "artifact": {
                        "ref": f"{kwargs['review_ref_prefix']}/frame-002.jpg",
                        "sha256": "b" * 64,
                    },
                },
            ],
            "contact_sheet": {
                "ref": f"{kwargs['review_ref_prefix']}/contact-sheet.jpg",
                "sha256": "c" * 64,
            },
            "report": {
                "ref": f"{kwargs['review_ref_prefix']}/inspection-report.json",
                "sha256": "d" * 64,
            },
        }

    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_tools.inspect_local_video_material",
        fake_inspection,
    )
    payload = json.loads(
        await _personal_ip_inspect_local_video_material(
            SimpleNamespace(context={"user_id": "user-1", "thread_id": "thread-1"}),
            production_id="video-production-1",
            event_key="inspect:asset-1:shot-1",
            shot_id="shot-1",
            asset_id="asset-1",
            source_path="/mnt/user-data/uploads/source.mp4",
            source_in_seconds=2,
            source_out_seconds=6,
        )
    )

    assert payload["operation_status"] == "ok"
    kwargs = repository.append_event.await_args.kwargs
    assert kwargs["event_type"] == "material_inspection_compiled"
    assert kwargs["entity_type"] == "asset"
    assert kwargs["provider"] == "ffmpeg_ffprobe"
    assert kwargs["payload"]["semantic_assessment_required"] is True
