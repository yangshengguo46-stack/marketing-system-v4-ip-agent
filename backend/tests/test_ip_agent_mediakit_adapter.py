from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from deerflow.ip_agent import evidence_mcp, mediakit_adapter, reference_evidence


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_cloud_provider_request_digest_is_path_free_and_exact() -> None:
    first = mediakit_adapter.cloud_provider_request_sha256(
        capability="asr",
        source_sha256="a" * 64,
        stage_spec_sha256="b" * 64,
    )
    replay = mediakit_adapter.cloud_provider_request_sha256(
        capability="asr",
        source_sha256="a" * 64,
        stage_spec_sha256="b" * 64,
    )
    changed_source = mediakit_adapter.cloud_provider_request_sha256(
        capability="asr",
        source_sha256="c" * 64,
        stage_spec_sha256="b" * 64,
    )
    changed_stage = mediakit_adapter.cloud_provider_request_sha256(
        capability="asr",
        source_sha256="a" * 64,
        stage_spec_sha256="d" * 64,
    )

    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert replay == first
    assert changed_source != first
    assert changed_stage != first


def test_cloud_capability_specs_follow_real_cli_boolean_argument_protocol() -> None:
    asr_spec = mediakit_adapter.cloud_video_capability_spec("asr")
    asr_args = asr_spec["semantic_args"]
    storyline_args = mediakit_adapter.cloud_video_capability_spec("storyline")["semantic_args"]

    assert asr_spec["provider_endpoint_origin"] == "https://mediakit.cn-beijing.volces.com"
    assert "--enable-confidence=true" in asr_args
    assert "--enable-confidence" not in asr_args
    assert "--enable-snapshot" not in storyline_args
    for arguments in (asr_args, storyline_args):
        assert not any(argument.startswith("--") and index + 1 < len(arguments) and arguments[index + 1] in {"true", "false"} for index, argument in enumerate(arguments))


def test_provider_result_url_is_https_provider_scoped_and_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mediakit_adapter,
        "resolve_host_addresses",
        lambda _hostname: [ipaddress.ip_address("1.1.1.1")],
    )

    valid = "https://result.tos-cn-beijing.volces.com/asr.json?signature=private"
    assert mediakit_adapter._validate_provider_result_url(valid) == valid

    for invalid in (
        "http://result.volces.com/asr.json",
        "https://result.example.com/asr.json",
        "https://user:password@result.volces.com/asr.json",
        "https://result.volces.com:8443/asr.json",
    ):
        with pytest.raises(mediakit_adapter.MediaKitAdapterError):
            mediakit_adapter._validate_provider_result_url(invalid)

    monkeypatch.setattr(
        mediakit_adapter,
        "resolve_host_addresses",
        lambda _hostname: [ipaddress.ip_address("127.0.0.1")],
    )
    with pytest.raises(mediakit_adapter.MediaKitAdapterError, match="public-network"):
        mediakit_adapter._validate_provider_result_url(valid)


def test_real_mediakit_asr_subtitle_text_schema_survives_semantic_boundary() -> None:
    payload, reasons = mediakit_adapter.sanitize_cloud_payload(
        {
            "duration": 3.793,
            "subtitles": [
                {
                    "start_time": 0.44,
                    "end_time": 2.72,
                    "subtitle_text": "每一次生成，都有回执",
                    "confidence": 0.977,
                },
                {
                    "start_time": 2.72,
                    "end_time": 3.842,
                    "subtitle_text": "也能被验证。",
                    "confidence": 1,
                },
            ],
        },
        capability="asr",
    )

    assert reasons == []
    assert payload["subtitles"][0]["subtitle_text"] == "每一次生成，都有回执"
    assert payload["subtitles"][1]["subtitle_text"] == "也能被验证。"
    assert payload.get("truncated") is not True


def test_local_metadata_probe_uses_official_cli_and_isolated_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed-video-snapshot")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"official-mediakit-build")
    ffprobe = tmp_path / "toolchain" / "ffprobe"
    ffprobe.parent.mkdir()
    ffprobe.write_bytes(b"ffprobe")
    monkeypatch.setenv("OTHER_SECRET", "must-not-leak")
    monkeypatch.setenv("DEER_FLOW_CONFIG_PATH", "/private/config.yaml")
    monkeypatch.setenv("IP_AGENT_EVIDENCE_BROWSER_PROFILE_DIR", "/private/profile")
    monkeypatch.setenv("MEDIAKIT_API_KEY", "cloud-key-must-not-enter-local-probe")

    observed: list[tuple[list[str], dict[str, str]]] = []
    responses: list[dict[str, Any]] = [
        {
            "name": "probe_video_metadata",
            "input_schema": {
                "type": "object",
                "required": ["video_url"],
                "properties": {"video_url": {"type": "string"}},
            },
            "output_schema": {"type": "object"},
        },
        {
            "format_meta": {
                "container": "mov,mp4,m4a,3gp,3g2,mj2",
                "duration": 8.2,
                "size": source.stat().st_size,
            },
            "video_stream_meta": {
                "codec": "h264",
                "duration": 8,
                "fps": 24,
                "height": 720,
                "width": 1280,
            },
            "audio_stream_meta": {
                "codec": "aac",
                "duration": 8.2,
            },
        },
    ]

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed.append((command, dict(kwargs["env"])))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(responses[len(observed) - 1]),
            stderr="",
        )

    monkeypatch.setattr(mediakit_adapter.subprocess, "run", run)

    result = mediakit_adapter.probe_video_metadata(
        source,
        expected_source_sha256=_sha256(source),
        mediakit=mediakit,
        ffmpeg_bin_dir=ffprobe.parent,
    )

    assert result.metadata == {
        "duration_seconds": 8.0,
        "width": 1280,
        "height": 720,
        "frame_rate": 24.0,
        "video_codec": "h264",
        "has_audio": True,
        "container": "mov,mp4,m4a,3gp,3g2,mj2",
        "size_bytes": source.stat().st_size,
    }
    assert result.receipt["executor"] == "official-mediakit-cli"
    assert result.receipt["execution_mode"] == "local"
    assert result.receipt["source_sha256"] == _sha256(source)
    assert len(result.receipt["schema_sha256"]) == 64
    assert len(result.receipt["result_sha256"]) == 64
    assert len(observed) == 2
    assert observed[0][0][-1] == "--schema"
    assert observed[1][0][-2:] == ["--video-url", str(source.resolve())]
    for _command, environment in observed:
        assert environment["MEDIAKIT_DISABLE_UPDATE_CHECK"] == "1"
        assert environment["MEDIAKIT_SURFACE"] == "agent"
        assert environment["MEDIAKIT_RUNTIME"] == "deerflow-ip-agent"
        assert environment["PATH"].split(os.pathsep, 1)[0] == str(ffprobe.parent)
        assert environment["HOME"] == environment["USERPROFILE"]
        assert environment["MEDIAKIT_OUTPUT_PATH"].startswith(environment["HOME"])
        assert "MEDIAKIT_API_KEY" not in environment
        assert "OTHER_SECRET" not in environment


def test_evidence_capability_probe_treats_configured_key_as_cloud_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ffmpeg = tmp_path / "ffmpeg"
    ffprobe = tmp_path / "ffprobe"
    mediakit = tmp_path / "mediakit-cli"
    for path in (ffmpeg, ffprobe, mediakit):
        path.write_bytes(path.name.encode())
    monkeypatch.setenv("MEDIAKIT_API_KEY", "configured-for-direct-execution")
    monkeypatch.setattr(
        evidence_mcp,
        "_toolchain_paths",
        lambda: (ffmpeg, ffprobe, mediakit),
    )

    availability = evidence_mcp._video_probe()

    assert availability.callable is True
    assert availability.reason_code == "LOCAL_MEDIA_INSPECTION_READY"
    assert "official_mediakit_cli" in availability.evidence_sources
    assert "official_mediakit_cloud" in availability.evidence_sources
    assert not any("paid-call admission" in limitation for limitation in availability.limitations)


def test_evidence_capability_probe_does_not_claim_cloud_without_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ffmpeg = tmp_path / "ffmpeg"
    ffprobe = tmp_path / "ffprobe"
    for path in (ffmpeg, ffprobe):
        path.write_bytes(path.name.encode())
    monkeypatch.setenv("MEDIAKIT_API_KEY", "configured-for-direct-execution")
    monkeypatch.setattr(
        evidence_mcp,
        "_toolchain_paths",
        lambda: (ffmpeg, ffprobe, None),
    )

    availability = evidence_mcp._video_probe()

    assert availability.callable is True
    assert availability.status == "degraded"
    assert "official_mediakit_cloud" not in availability.evidence_sources
    assert any("CLI" in limitation for limitation in availability.limitations)


def test_toolchain_paths_finds_project_root_mediakit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backend_root = tmp_path / "backend"
    state_dir = backend_root / ".deer-flow"
    toolchain = tmp_path / ".deer-flow" / "toolchains" / "ffmpeg" / "bin"
    toolchain.mkdir(parents=True)
    for name in ("ffmpeg", "ffprobe"):
        (toolchain / name).write_bytes(name.encode())
    mediakit = tmp_path / ".deer-flow" / "bin" / "mediakit-cli"
    mediakit.parent.mkdir(parents=True)
    mediakit.write_bytes(b"mediakit")
    monkeypatch.setattr(
        reference_evidence,
        "get_paths",
        lambda: SimpleNamespace(base_dir=state_dir),
    )
    monkeypatch.setattr(reference_evidence, "project_root", lambda: backend_root)

    ffmpeg, ffprobe, resolved_mediakit = reference_evidence._toolchain_paths()

    assert ffmpeg == toolchain / "ffmpeg"
    assert ffprobe == toolchain / "ffprobe"
    assert resolved_mediakit == mediakit


def test_local_metadata_probe_rejects_schema_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")

    monkeypatch.setattr(
        mediakit_adapter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout='{"name":"another_tool","input_schema":{}}',
            stderr="",
        ),
    )

    with pytest.raises(mediakit_adapter.MediaKitAdapterError, match="schema"):
        mediakit_adapter.probe_video_metadata(
            source,
            expected_source_sha256=_sha256(source),
            mediakit=mediakit,
            ffmpeg_bin_dir=tmp_path,
        )


def test_local_metadata_probe_rejects_source_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"changed-after-seal")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    called = False

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    monkeypatch.setattr(mediakit_adapter.subprocess, "run", run)

    with pytest.raises(mediakit_adapter.MediaKitAdapterError, match="hash"):
        mediakit_adapter.probe_video_metadata(
            source,
            expected_source_sha256="0" * 64,
            mediakit=mediakit,
            ffmpeg_bin_dir=tmp_path,
        )
    assert called is False


def test_local_metadata_probe_rejects_reported_size_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    responses = iter(
        [
            {
                "name": "probe_video_metadata",
                "input_schema": {"required": ["video_url"]},
            },
            {
                "format_meta": {"duration": 1, "size": 999},
                "video_stream_meta": {"width": 10, "height": 10, "fps": 25},
            },
        ]
    )

    monkeypatch.setattr(
        mediakit_adapter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(next(responses)),
            stderr="",
        ),
    )

    with pytest.raises(mediakit_adapter.MediaKitAdapterError, match="size"):
        mediakit_adapter.probe_video_metadata(
            source,
            expected_source_sha256=_sha256(source),
            mediakit=mediakit,
            ffmpeg_bin_dir=tmp_path,
        )


def test_reference_probe_prefers_mediakit_and_preserves_its_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    ffprobe = tmp_path / "tools" / "ffprobe"
    ffprobe.parent.mkdir()
    ffprobe.write_bytes(b"ffprobe")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    expected_metadata = {
        "duration_seconds": 1.0,
        "width": 10,
        "height": 10,
        "frame_rate": 25.0,
        "video_codec": "h264",
        "has_audio": False,
        "container": "mp4",
        "size_bytes": source.stat().st_size,
    }
    expected_receipt = {
        "adapter_version": "test-v1",
        "executor": "official-mediakit-cli",
        "execution_mode": "local",
        "source_sha256": _sha256(source),
        "mediakit_sha256": "a" * 64,
        "schema_sha256": "b" * 64,
        "result_sha256": "c" * 64,
    }

    monkeypatch.setattr(
        reference_evidence,
        "probe_video_metadata",
        lambda *_args, **_kwargs: mediakit_adapter.MediaKitMetadataProbe(
            metadata=expected_metadata,
            receipt=expected_receipt,
        ),
    )
    monkeypatch.setattr(
        reference_evidence,
        "_probe_video",
        lambda *_args, **_kwargs: pytest.fail("ffprobe fallback should not run"),
    )

    metadata, receipt = reference_evidence._probe_video_with_fallback(
        source,
        ffprobe=ffprobe,
        mediakit=mediakit,
        content_sha256=_sha256(source),
    )

    assert metadata == expected_metadata
    assert receipt == expected_receipt


def test_reference_probe_falls_back_explicitly_when_mediakit_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    ffprobe = tmp_path / "tools" / "ffprobe"
    ffprobe.parent.mkdir()
    ffprobe.write_bytes(b"ffprobe")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    fallback_metadata = {
        "duration_seconds": 1.0,
        "width": 10,
        "height": 10,
        "frame_rate": 25.0,
        "video_codec": "h264",
        "has_audio": False,
        "container": "mp4",
        "size_bytes": source.stat().st_size,
    }

    monkeypatch.setattr(
        reference_evidence,
        "probe_video_metadata",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(mediakit_adapter.MediaKitAdapterError("provider detail must stay private")),
    )
    monkeypatch.setattr(
        reference_evidence,
        "_probe_video",
        lambda *_args, **_kwargs: fallback_metadata,
    )

    metadata, receipt = reference_evidence._probe_video_with_fallback(
        source,
        ffprobe=ffprobe,
        mediakit=mediakit,
        content_sha256=_sha256(source),
    )

    assert metadata == fallback_metadata
    assert receipt["executor"] == "project-ffprobe"
    assert receipt["fallback_reason_code"] == "MEDIAKIT_LOCAL_PROBE_FAILED"
    assert "provider detail" not in json.dumps(receipt)
    assert receipt["source_sha256"] == _sha256(source)
    assert len(receipt["ffprobe_sha256"]) == 64


def test_visual_analysis_spec_binds_mediakit_probe_receipt(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg"
    ffprobe = tmp_path / "ffprobe"
    ffmpeg.write_bytes(b"ffmpeg")
    ffprobe.write_bytes(b"ffprobe")
    receipt = {
        "executor": "official-mediakit-cli",
        "mediakit_sha256": "a" * 64,
        "schema_sha256": "b" * 64,
        "result_sha256": "c" * 64,
        "source_sha256": "d" * 64,
    }

    first = reference_evidence._visual_analysis_spec(
        content_sha256="d" * 64,
        duration_seconds=8.0,
        analysis_depth="mechanical",
        max_frames=4,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        metadata_probe_receipt=receipt,
    )
    second = reference_evidence._visual_analysis_spec(
        content_sha256="d" * 64,
        duration_seconds=8.0,
        analysis_depth="mechanical",
        max_frames=4,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        metadata_probe_receipt={**receipt, "schema_sha256": "e" * 64},
    )

    assert first["metadata_probe_receipt"] == receipt
    assert first["toolchain_sha256"]["mediakit"] == "a" * 64
    assert first["spec_sha256"] != second["spec_sha256"]


def test_cloud_capability_submits_sealed_snapshot_with_bounded_polling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"the exact downloaded snapshot")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"official-mediakit-build")
    session_root = tmp_path / "isolated-session"
    observed: list[tuple[list[str], dict[str, str]]] = []
    responses = iter(
        [
            {"task_id": "task-123", "request_id": "submit-request", "success": True},
            {
                "task_id": "task-123",
                "request_id": "query-request",
                "status": "completed",
                "result_file": {"segments": [{"text": "真实台词"}]},
            },
        ]
    )
    monkeypatch.setenv("OTHER_SECRET", "must-not-leak")

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed.append((command, dict(kwargs["env"])))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(next(responses), ensure_ascii=False),
            stderr="",
        )

    monkeypatch.setattr(mediakit_adapter.subprocess, "run", run)

    result = mediakit_adapter.run_cloud_video_capability(
        source,
        expected_source_sha256=_sha256(source),
        mediakit=mediakit,
        api_key="test-key",
        capability="asr",
        client_token="client-token",
        stage_spec_sha256="a" * 64,
        session_root=session_root,
    )

    assert result.payload["segments"][0]["text"] == "真实台词"
    assert "status" not in result.payload
    assert "task_id" not in result.payload
    assert "request_id" not in result.payload
    assert result.receipt["source_sha256"] == _sha256(source)
    assert result.receipt["stage_spec_sha256"] == "a" * 64
    assert result.receipt["provider_input_attestation"] == "not_provided"
    assert len(result.receipt["task_id_sha256"]) == 64
    assert len(observed) == 2

    submit_command, submit_environment = observed[0]
    poll_command, poll_environment = observed[1]
    assert submit_command[:4] == [
        str(mediakit.resolve()),
        "--cloud",
        "video",
        "asr-subtitles",
    ]
    assert submit_command[submit_command.index("--video-url") + 1] == str(source.resolve())
    assert "http" not in " ".join(submit_command)
    assert "--poll-complete" not in poll_command
    assert "--max-poll-attempts" not in poll_command
    assert submit_environment == poll_environment
    assert submit_environment["MEDIAKIT_API_KEY"] == "test-key"
    assert submit_environment["MEDIAKIT_ENDPOINT"] == "https://mediakit.cn-beijing.volces.com"
    assert submit_environment["HOME"] == submit_environment["USERPROFILE"]
    assert submit_environment["HOME"].startswith(str(session_root.resolve()))
    assert submit_environment["MEDIAKIT_OUTPUT_PATH"].startswith(submit_environment["HOME"])
    assert "OTHER_SECRET" not in submit_environment
    assert "DEER_FLOW_CONFIG_PATH" not in submit_environment
    assert "IP_AGENT_EVIDENCE_BROWSER_PROFILE_DIR" not in submit_environment
    assert (session_root / "home").stat().st_mode & 0o777 == 0o700
    serialized_receipt = json.dumps(result.receipt, ensure_ascii=False)
    assert "test-key" not in serialized_receipt
    assert "task-123" not in serialized_receipt
    assert str(source.resolve()) not in serialized_receipt


def test_cloud_capability_downloads_bounded_result_without_exposing_signed_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"the exact downloaded snapshot")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"official-mediakit-build")
    signed_url = "https://result.volces.com/asr.json?signature=private-sentinel"
    responses = iter(
        [
            {"task_id": "task-123", "success": True},
            {
                "task_id": "task-123",
                "status": "completed",
                "subtitle_url": signed_url,
            },
        ]
    )
    downloaded = json.dumps(
        {"segments": [{"text": "真实台词"}]},
        ensure_ascii=False,
    ).encode()
    observed_urls: list[str] = []

    monkeypatch.setattr(
        mediakit_adapter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(next(responses)),
            stderr="",
        ),
    )

    def download(url: str) -> tuple[bytes, str]:
        observed_urls.append(url)
        return downloaded, "application/json"

    monkeypatch.setattr(mediakit_adapter, "_download_provider_result", download)

    result = mediakit_adapter.run_cloud_video_capability(
        source,
        expected_source_sha256=_sha256(source),
        mediakit=mediakit,
        api_key="test-key",
        capability="asr",
        client_token="client-token",
        stage_spec_sha256="a" * 64,
        session_root=tmp_path / "isolated-session",
    )

    assert observed_urls == [signed_url]
    assert result.payload["segments"][0]["text"] == "真实台词"
    assert result.receipt["result_transport"] == "bounded_provider_https"
    assert result.receipt["result_file_sha256"] == hashlib.sha256(downloaded).hexdigest()
    assert result.receipt["result_file_size_bytes"] == len(downloaded)
    assert result.receipt["result_file_content_type"] == "application/json"
    serialized = json.dumps(
        {"payload": result.payload, "receipt": result.receipt},
        ensure_ascii=False,
    )
    assert signed_url not in serialized
    assert "private-sentinel" not in serialized


def test_cloud_capability_rejects_completed_envelope_without_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"video")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    responses = iter(
        [
            {"task_id": "task-123", "success": True},
            {"task_id": "task-123", "status": "completed"},
        ]
    )
    monkeypatch.setattr(
        mediakit_adapter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(next(responses)),
            stderr="",
        ),
    )

    with pytest.raises(mediakit_adapter.MediaKitAdapterError, match="without a semantic result"):
        mediakit_adapter.run_cloud_video_capability(
            source,
            expected_source_sha256=_sha256(source),
            mediakit=mediakit,
            api_key="test-key",
            capability="asr",
            client_token="client-token",
            stage_spec_sha256="a" * 64,
            session_root=tmp_path / "isolated-session",
        )


@pytest.mark.parametrize("downloaded", [b"{}", b"null"])
def test_cloud_capability_rejects_empty_downloaded_semantic_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    downloaded: bytes,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"video")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    responses = iter(
        [
            {"task_id": "task-123", "success": True},
            {
                "task_id": "task-123",
                "status": "completed",
                "subtitle_url": "https://result.volces.com/asr.json",
            },
        ]
    )
    monkeypatch.setattr(
        mediakit_adapter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(next(responses)),
            stderr="",
        ),
    )
    monkeypatch.setattr(
        mediakit_adapter,
        "_download_provider_result",
        lambda _url: (downloaded, "application/json"),
    )

    with pytest.raises(mediakit_adapter.MediaKitAdapterError, match="without a semantic result"):
        mediakit_adapter.run_cloud_video_capability(
            source,
            expected_source_sha256=_sha256(source),
            mediakit=mediakit,
            api_key="test-key",
            capability="asr",
            client_token="client-token",
            stage_spec_sha256="a" * 64,
            session_root=tmp_path / "isolated-session",
        )


def test_cloud_capability_rejects_conflicting_result_urls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"video")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    responses = iter(
        [
            {"task_id": "task-123", "success": True},
            {
                "task_id": "task-123",
                "status": "completed",
                "subtitle_url": "https://one.volces.com/asr.json",
                "result_url": "https://two.volces.com/asr.json",
            },
        ]
    )
    monkeypatch.setattr(
        mediakit_adapter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(next(responses)),
            stderr="",
        ),
    )

    with pytest.raises(mediakit_adapter.MediaKitAdapterError, match="conflicting"):
        mediakit_adapter.run_cloud_video_capability(
            source,
            expected_source_sha256=_sha256(source),
            mediakit=mediakit,
            api_key="test-key",
            capability="asr",
            client_token="client-token",
            stage_spec_sha256="a" * 64,
            session_root=tmp_path / "isolated-session",
        )


def test_cloud_capability_rejects_snapshot_changed_during_provider_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"before")
    original_sha256 = _sha256(source)
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"official-mediakit-build")
    responses = iter(
        [
            {"task_id": "task-123", "success": True},
            {"task_id": "task-123", "status": "completed", "result_file": {"segments": []}},
        ]
    )

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        payload = next(responses)
        if command[2:4] == ["shared", "query-task"]:
            source.write_bytes(b"after")
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(mediakit_adapter.subprocess, "run", run)

    with pytest.raises(mediakit_adapter.MediaKitAdapterError, match="changed"):
        mediakit_adapter.run_cloud_video_capability(
            source,
            expected_source_sha256=original_sha256,
            mediakit=mediakit,
            api_key="test-key",
            capability="ocr",
            client_token="client-token",
            stage_spec_sha256="b" * 64,
            session_root=tmp_path / "isolated-session",
        )


def test_cloud_payload_is_allowlisted_and_receipt_binds_exposed_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"video")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    responses = iter(
        [
            {"task_id": "task-123", "success": True},
            {
                "task_id": "task-123",
                "status": "completed",
                "result_file": {
                    "segments": [
                        {
                            "text": "保留真实台词",
                            "taskId": "nested-task-sentinel",
                            "localPath": "/private/provider/result.json",
                        }
                    ],
                    "taskId": "camel-task-sentinel",
                    "fileId": "camel-file-sentinel",
                    "uploadUrl": "https://upload.example/private?token=sentinel",
                    "url": "https://result.example/private",
                    "apiKeyEcho": "test-key",
                    "content": (f"safe text {source.resolve()} https://provider.example/private task-123 test-key"),
                },
            },
        ]
    )
    monkeypatch.setattr(
        mediakit_adapter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(next(responses), ensure_ascii=False),
            stderr="",
        ),
    )

    result = mediakit_adapter.run_cloud_video_capability(
        source,
        expected_source_sha256=_sha256(source),
        mediakit=mediakit,
        api_key="test-key",
        capability="asr",
        client_token="client-token",
        stage_spec_sha256="b" * 64,
        session_root=tmp_path / "isolated-session",
    )

    serialized = json.dumps(result.payload, ensure_ascii=False)
    assert "保留真实台词" in serialized
    for sentinel in (
        "nested-task-sentinel",
        "/private/provider/result.json",
        "camel-task-sentinel",
        "camel-file-sentinel",
        "upload.example",
        "result.example",
        "test-key",
        str(source.resolve()),
        "task-123",
    ):
        assert sentinel not in serialized
    assert result.receipt["result_sha256"] == _canonical_sha256(result.payload)


def test_scene_result_url_redaction_does_not_downgrade_semantic_coverage() -> None:
    payload, reason_codes = mediakit_adapter.sanitize_cloud_payload(
        {
            "duration": 3.648,
            "segments": [
                {
                    "start_time": 0.0,
                    "end_time": 3.648,
                    "segment_video_url": "https://result.example/segment.mp4",
                }
            ],
        },
        capability="scene_segmentation",
    )

    assert payload == {
        "duration": 3.648,
        "segments": [{"start_time": 0.0, "end_time": 3.648}],
    }
    assert reason_codes == ["PROVIDER_OPERATIONAL_FIELDS_REMOVED"]


def test_storyline_official_result_fields_are_preserved_without_source_url() -> None:
    payload, reason_codes = mediakit_adapter.sanitize_cloud_payload(
        {
            "duration": 3.648,
            "source_video_info": [
                {
                    "source_video_index": 0,
                    "source_video_summary": "人物完成一次可验证的生成。",
                    "source_video_tag": "演示",
                    "source_video_title": "测试片段",
                    "source_video_url": "https://result.example/source.mp4",
                }
            ],
            "storyline_clips": [
                {
                    "clip_dialogue": "每一次生成都有回执。",
                    "clip_end_time": 3.648,
                    "clip_index": 0,
                    "clip_score": 0.9,
                    "clip_start_time": 0.0,
                    "clip_summary": "生成结果可验证。",
                    "clip_title": "回执",
                    "source_video_index": 0,
                }
            ],
            "storyline_highlights": [
                {
                    "highlight_clips_index": [0],
                    "highlight_index": 0,
                    "highlight_summary": "一次完整演示。",
                    "highlight_title": "生成与验证",
                }
            ],
        },
        capability="storyline",
    )

    assert payload["source_video_info"][0]["source_video_summary"] == "人物完成一次可验证的生成。"
    assert payload["storyline_clips"][0]["clip_dialogue"] == "每一次生成都有回执。"
    assert payload["storyline_highlights"][0]["highlight_clips_index"] == [0]
    assert "source_video_url" not in payload["source_video_info"][0]
    assert "truncated" not in payload
    assert reason_codes == ["PROVIDER_OPERATIONAL_FIELDS_REMOVED"]


def test_cloud_capability_rejects_missing_task_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"video")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    monkeypatch.setattr(
        mediakit_adapter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout='{"success":true}',
            stderr="",
        ),
    )

    with pytest.raises(mediakit_adapter.MediaKitAdapterError, match="task_id"):
        mediakit_adapter.run_cloud_video_capability(
            source,
            expected_source_sha256=_sha256(source),
            mediakit=mediakit,
            api_key="test-key",
            capability="asr",
            client_token="client-token",
            stage_spec_sha256="c" * 64,
            session_root=tmp_path / "isolated-session",
        )


@pytest.mark.parametrize(
    ("final_payload", "expected_error"),
    [
        ({"task_id": "another-task", "status": "completed"}, "different task_id"),
        ({"task_id": "task-123", "status": "failed"}, "failed terminal"),
        ({"task_id": "task-123", "status": "success"}, "unknown task status"),
    ],
)
def test_cloud_capability_rejects_invalid_provider_task_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    final_payload: dict[str, Any],
    expected_error: str,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"video")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    responses = iter(
        [
            {"task_id": "task-123", "success": True},
            final_payload,
        ]
    )
    monkeypatch.setattr(
        mediakit_adapter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(next(responses)),
            stderr="",
        ),
    )

    with pytest.raises(mediakit_adapter.MediaKitAdapterError, match=expected_error):
        mediakit_adapter.run_cloud_video_capability(
            source,
            expected_source_sha256=_sha256(source),
            mediakit=mediakit,
            api_key="test-key",
            capability="asr",
            client_token="client-token",
            stage_spec_sha256="d" * 64,
            session_root=tmp_path / "isolated-session",
        )


def test_cloud_capability_polling_is_caller_bounded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"video")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    responses = iter(
        [
            {"task_id": "task-123", "success": True},
            {"task_id": "task-123", "status": "running"},
            {"task_id": "task-123", "status": "completed", "result_file": {"segments": []}},
        ]
    )
    observed_commands: list[list[str]] = []
    observed_sleeps: list[float] = []

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed_commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(next(responses)),
            stderr="",
        )

    monkeypatch.setattr(mediakit_adapter.subprocess, "run", run)
    monkeypatch.setattr(mediakit_adapter.time, "sleep", observed_sleeps.append)

    result = mediakit_adapter.run_cloud_video_capability(
        source,
        expected_source_sha256=_sha256(source),
        mediakit=mediakit,
        api_key="test-key",
        capability="asr",
        client_token="client-token",
        stage_spec_sha256="e" * 64,
        session_root=tmp_path / "isolated-session",
    )

    assert result.payload == {"segments": []}
    assert observed_sleeps == [3]
    assert len(observed_commands) == 3
    for command in observed_commands[1:]:
        assert "--poll-complete" not in command
        assert "--max-poll-attempts" not in command


def test_cloud_capability_rejects_nonterminal_after_attempt_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"video")
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    responses = iter(
        [
            {"task_id": "task-123", "success": True},
            {"task_id": "task-123", "status": "running"},
        ]
    )
    observed_commands: list[list[str]] = []
    monkeypatch.setattr(mediakit_adapter, "_MAX_POLL_ATTEMPTS", 1)
    monkeypatch.setattr(mediakit_adapter.time, "sleep", lambda _seconds: None)

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed_commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(next(responses)),
            stderr="",
        )

    monkeypatch.setattr(mediakit_adapter.subprocess, "run", run)

    with pytest.raises(mediakit_adapter.MediaKitAdapterError, match="did not reach completed"):
        mediakit_adapter.run_cloud_video_capability(
            source,
            expected_source_sha256=_sha256(source),
            mediakit=mediakit,
            api_key="test-key",
            capability="asr",
            client_token="client-token",
            stage_spec_sha256="f" * 64,
            session_root=tmp_path / "isolated-session",
        )
    assert len(observed_commands) == 2


@pytest.mark.asyncio
async def test_provider_evidence_uses_local_snapshot_without_claiming_provider_hash_attestation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"one sealed snapshot")
    source_sha256 = _sha256(source)
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"official-mediakit-build")
    observed_sources: list[Path] = []
    observed_sessions: list[Path] = []
    monkeypatch.setenv("MEDIAKIT_API_KEY", "test-key")

    def run_provider(path: Path, **kwargs: Any) -> mediakit_adapter.MediaKitCloudExecution:
        observed_sources.append(path)
        observed_sessions.append(kwargs["session_root"])
        capability = kwargs["capability"]
        payload = {"segments": [{"text": capability}]}
        return mediakit_adapter.MediaKitCloudExecution(
            payload=payload,
            receipt={
                "adapter_version": "official-mediakit-cloud-video-v1",
                "result_normalization_version": "mediakit-cloud-semantic-allowlist-v2",
                "executor": "official-mediakit-cli",
                "execution_mode": "cloud",
                "capability": capability,
                "source_sha256": source_sha256,
                "mediakit_sha256": _sha256(mediakit),
                "stage_spec_sha256": kwargs["stage_spec_sha256"],
                "submission_sha256": "1" * 64,
                "result_sha256": _canonical_sha256(payload),
                "task_id_sha256": "3" * 64,
                "provider_input_attestation": "not_provided",
                "polling_mode": "caller_deadline_single_query",
                "result_transport": "inline",
            },
        )

    monkeypatch.setattr(reference_evidence, "run_cloud_video_capability", run_provider)

    evidence, coverage, _specs = await reference_evidence._provider_evidence(
        source=source,
        content_sha256=source_sha256,
        analysis_depth="full",
        mediakit=mediakit,
    )

    assert observed_sources == [source.resolve()] * 4
    assert len({path.resolve() for path in observed_sessions}) == 4
    assert len({path.parent.parent.resolve() for path in observed_sessions}) == 1
    assert {path.parent.name for path in observed_sessions} == {
        "asr",
        "ocr",
        "scene_segmentation",
        "storyline",
    }
    assert {path.name for path in observed_sessions} == {"attempt-1"}
    assert coverage == {
        "asr": "completed",
        "ocr": "completed",
        "provider_scene_segmentation": "completed",
        "storyline": "completed",
    }
    assert evidence["asr"]["input_binding"] == "sealed_local_snapshot_provider_unattested"
    assert evidence["asr"]["input_content_sha256"] == source_sha256
    assert evidence["asr"]["execution_receipt"]["source_sha256"] == source_sha256


@pytest.mark.asyncio
async def test_provider_evidence_removes_operational_ids_paths_and_urls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"one sealed snapshot")
    source_sha256 = _sha256(source)
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"official-mediakit-build")
    monkeypatch.setenv("MEDIAKIT_API_KEY", "test-key")

    def run_provider(
        _path: Path,
        **kwargs: Any,
    ) -> mediakit_adapter.MediaKitCloudExecution:
        capability = kwargs["capability"]
        payload, _reasons = mediakit_adapter.sanitize_cloud_payload(
            {
                "transcript": "保留真实台词",
                "taskId": "raw-task-sentinel",
                "requestId": "raw-request-sentinel",
                "fileId": "raw-file-sentinel",
                "uploadUrl": "https://upload.example/signed?secret=raw-url-sentinel",
                "clipSnapshotUrl": "https://snapshot.example/a?token=raw-snapshot-sentinel",
            },
            capability=capability,
        )
        return mediakit_adapter.MediaKitCloudExecution(
            payload=payload,
            receipt={
                "adapter_version": "official-mediakit-cloud-video-v1",
                "result_normalization_version": "mediakit-cloud-semantic-allowlist-v2",
                "executor": "official-mediakit-cli",
                "execution_mode": "cloud",
                "capability": capability,
                "source_sha256": source_sha256,
                "mediakit_sha256": _sha256(mediakit),
                "stage_spec_sha256": kwargs["stage_spec_sha256"],
                "submission_sha256": "1" * 64,
                "result_sha256": _canonical_sha256(payload),
                "task_id_sha256": "3" * 64,
                "provider_input_attestation": "not_provided",
                "polling_mode": "caller_deadline_single_query",
                "result_transport": "inline",
            },
        )

    monkeypatch.setattr(reference_evidence, "run_cloud_video_capability", run_provider)

    evidence, _coverage, _specs = await reference_evidence._provider_evidence(
        source=source,
        content_sha256=source_sha256,
        analysis_depth="speech_text",
        mediakit=mediakit,
    )

    serialized = json.dumps(evidence, ensure_ascii=False)
    assert "保留真实台词" in serialized
    for sentinel in (
        "raw-task-sentinel",
        "raw-request-sentinel",
        "raw-file-sentinel",
        "raw-url-sentinel",
        "raw-snapshot-sentinel",
    ):
        assert sentinel not in serialized
