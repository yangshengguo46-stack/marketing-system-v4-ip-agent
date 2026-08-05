from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def _load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "ip_agent_mediakit_remux_canary.py"
    spec = importlib.util.spec_from_file_location("ip_agent_mediakit_remux_canary", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


canary = _load_module()


class _Dumpable:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_key(path: Path, value: str = "mediakit-secret-value") -> None:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def _write_ark_config(path: Path, reference: str = "$TEST_ARK_CANARY_KEY") -> None:
    path.write_text(
        f"models:\n  - name: doubao-seed-2-0-pro-260215\n    api_key: {reference}\n",
        encoding="utf-8",
    )


def _options(
    tmp_path: Path,
    *,
    execute_paid: bool,
) -> tuple[Any, bytes, Path, Path]:
    source_bytes = b"sealed-source-video"
    source = tmp_path / "source.mp4"
    source.write_bytes(source_bytes)
    key_file = tmp_path / "mediakit-key"
    _write_key(key_file)
    ark_config = tmp_path / "config.yaml"
    _write_ark_config(ark_config)
    options = canary.OperatorCanaryOptions(
        execute_paid=execute_paid,
        source=source,
        expected_source_sha256=_sha256_bytes(source_bytes),
        expected_work_id="7658501922794432731",
        expected_account="account-sec-uid",
        mediakit_key_file=key_file,
        ark_config=ark_config,
        ark_model="doubao-seed-2-0-pro-260215",
        output_dir=tmp_path / "output",
    )
    return options, source_bytes, key_file, ark_config


def test_default_cli_mode_is_a_zero_provider_call_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    options, _source, _key_file, _config = _options(tmp_path, execute_paid=False)
    monkeypatch.setattr(canary, "_parse_args", lambda _argv: options)

    def forbidden_key_read(_path):
        raise AssertionError("dry run must not read the MediaKit key value")

    monkeypatch.setattr(canary, "_read_mediakit_key", forbidden_key_read)

    async def forbidden(_options):
        raise AssertionError("provider execution must not run in dry-run mode")

    monkeypatch.setattr(canary, "run_operator_canary", forbidden)

    assert canary.main([]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "ok": True,
        "code": "DRY_RUN_VALIDATED",
        "provider_calls": 0,
    }
    assert not options.output_dir.exists()


def test_run_operator_canary_refuses_missing_execute_paid_before_provider_use(tmp_path: Path) -> None:
    options, _source, _key_file, _config = _options(tmp_path, execute_paid=False)
    provider_calls = 0

    async def forbidden(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider must not run")

    with pytest.raises(canary.CanaryError) as error:
        asyncio.run(canary.run_operator_canary(options, remux_runner=forbidden))
    assert error.value.code == "PAID_EXECUTION_NOT_CONFIRMED"
    assert provider_calls == 0


def test_dry_run_fails_on_missing_ffprobe_without_reading_keys_or_calling_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    options, _source, _key_file, _config = _options(tmp_path, execute_paid=False)
    monkeypatch.setattr(canary, "_parse_args", lambda _argv: options)

    def missing_ffprobe():
        raise canary.CanaryError("PINNED_FFPROBE_UNAVAILABLE")

    def forbidden_key_read(_path):
        raise AssertionError("dry run must not read the MediaKit key value")

    async def forbidden_provider(_options):
        raise AssertionError("provider must not run")

    monkeypatch.setattr(canary, "_ffprobe_path", missing_ffprobe)
    monkeypatch.setattr(canary, "_read_mediakit_key", forbidden_key_read)
    monkeypatch.setattr(canary, "run_operator_canary", forbidden_provider)

    assert canary.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "ok": False,
        "code": "PINNED_FFPROBE_UNAVAILABLE",
    }
    assert not options.output_dir.exists()


def test_paid_path_preflights_ffprobe_before_credentials_output_or_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options, _source, _key_file, _config = _options(tmp_path, execute_paid=True)
    provider_calls = 0

    def missing_ffprobe():
        raise canary.CanaryError("PINNED_FFPROBE_UNAVAILABLE")

    def forbidden_key_read(_path):
        raise AssertionError("credentials must not be read before ffprobe preflight")

    async def forbidden_provider(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider must not run")

    monkeypatch.setattr(canary, "_ffprobe_path", missing_ffprobe)
    monkeypatch.setattr(canary, "_read_mediakit_key", forbidden_key_read)
    with pytest.raises(canary.CanaryError) as error:
        asyncio.run(canary.run_operator_canary(options, remux_runner=forbidden_provider))
    assert error.value.code == "PINNED_FFPROBE_UNAVAILABLE"
    assert provider_calls == 0
    assert not options.output_dir.exists()


def test_mediakit_key_must_be_owner_regular_mode_0600(tmp_path: Path) -> None:
    key_file = tmp_path / "mediakit-key"
    key_file.write_text("secret-value", encoding="utf-8")
    key_file.chmod(0o644)

    with pytest.raises(canary.CanaryError) as error:
        canary._read_mediakit_key(key_file)
    assert error.value.code == "INVALID_MEDIAKIT_KEY_FILE"

    key_file.chmod(0o600)
    assert canary._read_mediakit_key(key_file) == "secret-value"

    link = tmp_path / "key-link"
    link.symlink_to(key_file)
    with pytest.raises(canary.CanaryError) as error:
        canary._read_mediakit_key(link)
    assert error.value.code == "INVALID_MEDIAKIT_KEY_FILE"


@pytest.mark.parametrize("reference", ["$ARK_CANARY_KEY", "${ARK_CANARY_KEY}"])
def test_ark_key_is_resolved_only_from_a_safe_config_environment_reference(
    tmp_path: Path,
    reference: str,
) -> None:
    config = tmp_path / "config.yaml"
    _write_ark_config(config, reference=reference)

    assert (
        canary._read_ark_key_from_config(
            config,
            model_name="doubao-seed-2-0-pro-260215",
            environment={"ARK_CANARY_KEY": "ark-secret-value"},
        )
        == "ark-secret-value"
    )


def test_ark_config_rejects_literal_credentials_and_unresolved_placeholders(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _write_ark_config(config, reference="literal-secret-must-not-be-accepted")
    with pytest.raises(canary.CanaryError) as error:
        canary._read_ark_key_from_config(
            config,
            model_name="doubao-seed-2-0-pro-260215",
            environment={},
        )
    assert error.value.code == "ARK_KEY_MUST_BE_ENV_REFERENCE"

    _write_ark_config(config, reference="$ARK_CANARY_KEY")
    with pytest.raises(canary.CanaryError) as error:
        canary._read_ark_key_from_config(
            config,
            model_name="doubao-seed-2-0-pro-260215",
            environment={},
        )
    assert error.value.code == "ARK_KEY_ENV_NOT_CONFIGURED"


def test_packet_payload_identity_uses_codec_type_not_stream_index(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    candidate = tmp_path / "candidate.mp4"
    source.write_bytes(b"vvvAAwwBBB")
    candidate.write_bytes(b"AAvvvBBBww")

    source_fingerprints = canary._fingerprint_packet_payloads(
        source,
        stream_types={0: "video", 1: "audio"},
        packets=[
            canary.PacketRecord(stream_index=0, position=0, size=3),
            canary.PacketRecord(stream_index=1, position=3, size=2),
            canary.PacketRecord(stream_index=0, position=5, size=2),
            canary.PacketRecord(stream_index=1, position=7, size=3),
        ],
    )
    candidate_fingerprints = canary._fingerprint_packet_payloads(
        candidate,
        stream_types={0: "audio", 1: "video"},
        packets=[
            canary.PacketRecord(stream_index=0, position=0, size=2),
            canary.PacketRecord(stream_index=1, position=2, size=3),
            canary.PacketRecord(stream_index=0, position=5, size=3),
            canary.PacketRecord(stream_index=1, position=8, size=2),
        ],
    )

    assert source_fingerprints == candidate_fingerprints
    assert source_fingerprints["audio"].packet_count == 2
    assert source_fingerprints["video"].packet_count == 2


def test_duplicate_same_codec_type_streams_fail_closed() -> None:
    payload = {
        "format": {"duration": "1.0"},
        "streams": [
            {"index": 0, "codec_type": "audio"},
            {"index": 1, "codec_type": "audio"},
        ],
    }
    original = canary._run_ffprobe_json
    canary._run_ffprobe_json = lambda *_args, **_kwargs: payload
    try:
        with pytest.raises(canary.CanaryError) as error:
            canary._probe_streams_and_duration(Path("ffprobe"), Path("video.mp4"))
    finally:
        canary._run_ffprobe_json = original
    assert error.value.code == "AMBIGUOUS_CODEC_TYPE_STREAMS"


def test_packet_probe_timeout_is_bounded_and_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")

    def timeout(*_args, **_kwargs):
        raise canary.subprocess.TimeoutExpired(["ffprobe"], 180)

    monkeypatch.setattr(canary.subprocess, "run", timeout)
    with pytest.raises(canary.CanaryError) as error:
        canary._probe_packet_records(Path("ffprobe"), media)
    assert error.value.code == "FFPROBE_TIMEOUT"


def test_success_writes_only_private_secret_free_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options, source_bytes, _key_file, _config = _options(tmp_path, execute_paid=True)
    monkeypatch.setenv("TEST_ARK_CANARY_KEY", "ark-secret-value")
    runtime_url = "https://output.volcvideo.com/candidate.mp4?signature=runtime-secret"
    candidate_bytes = b"provider-remux-candidate"
    candidate_sha256 = _sha256_bytes(candidate_bytes)
    calls: list[str] = []

    async def fake_remux(**kwargs):
        calls.append("remux")
        assert kwargs["expected_source_sha256"] == _sha256_bytes(source_bytes)
        assert kwargs["mediakit_api_key"] == "mediakit-secret-value"
        assert kwargs["client_token"].startswith("ipmk-remux-")
        return SimpleNamespace(
            runtime_url=runtime_url,
            receipt=_Dumpable(
                {
                    "contract_version": "ip-mediakit-remux-https-candidate-v1",
                    "task_id_sha256": "a" * 64,
                    "runtime_url_sha256": hashlib.sha256(runtime_url.encode()).hexdigest(),
                    "retries": 0,
                }
            ),
        )

    async def fake_download(url: str, destination: Path) -> None:
        calls.append("download")
        assert url == runtime_url
        destination.write_bytes(candidate_bytes)
        destination.chmod(0o600)

    async def fake_compare(source: Path, candidate: Path):
        calls.append("compare")
        assert source.read_bytes() == source_bytes
        assert candidate.read_bytes() == candidate_bytes
        return canary.PacketEquivalenceResult(
            source_duration_seconds=70.867,
            candidate_duration_seconds=70.867,
            duration_delta_seconds=0.0,
            codec_type_fingerprints={
                "audio": canary.PacketPayloadFingerprint(
                    packet_count=2,
                    total_bytes=5,
                    payload_sequence_sha256="b" * 64,
                ),
                "video": canary.PacketPayloadFingerprint(
                    packet_count=2,
                    total_bytes=5,
                    payload_sequence_sha256="c" * 64,
                ),
            },
        )

    async def fake_chat(**kwargs):
        calls.append("chat")
        assert kwargs == {
            "video_url": runtime_url,
            "source_sha256": candidate_sha256,
            "duration_seconds": 70.867,
            "ark_api_key": "ark-secret-value",
            "mediakit_api_key": "mediakit-secret-value",
        }
        return _Dumpable(
            {
                "contract_version": "ip-mediakit-video-visual-observation-v1",
                "source_sha256": candidate_sha256,
                "receipt": {"provider_input_ref_sha256": hashlib.sha256(runtime_url.encode()).hexdigest()},
            }
        )

    report_path, candidate_path = asyncio.run(
        canary.run_operator_canary(
            options,
            remux_runner=fake_remux,
            chat_runner=fake_chat,
            download_runner=fake_download,
            packet_comparator=fake_compare,
        )
    )

    assert calls == ["remux", "download", "compare", "chat"]
    assert candidate_path.read_bytes() == candidate_bytes
    assert stat.S_IMODE(candidate_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes)
    assert report["product_handoff_status"] == "research_observation_not_product_handoff"
    assert report["controls"] == {
        "execute_paid_explicit": True,
        "automatic_retries": 0,
        "runtime_url_persisted": False,
        "credential_values_persisted": False,
        "mediakit_key_source": "owner_only_mode_0600_file",
        "ark_key_source": "environment_reference_from_safe_loaded_config",
    }
    assert report["packet_payload_equivalence"]["comparison_key"] == "codec_type_plus_packet_payload_sequence"
    assert report["packet_payload_equivalence"]["stream_index_used_as_content_identity"] is False
    assert report["candidate"]["sha256"] == candidate_sha256
    for forbidden in (
        runtime_url,
        "runtime-secret",
        "mediakit-secret-value",
        "ark-secret-value",
        "7658501922794432731",
        "account-sec-uid",
    ):
        assert forbidden.encode() not in report_bytes


def test_existing_report_is_rejected_before_credentials_or_provider_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options, _source, _key_file, _config = _options(tmp_path, execute_paid=True)
    options.output_dir.mkdir(mode=0o700)
    report = options.output_dir / ("mediakit-remux-canary-" + hashlib.sha256(options.expected_work_id.encode()).hexdigest()[:16] + ".json")
    report.write_text("existing", encoding="utf-8")
    provider_calls = 0

    def forbidden_key_read(_path):
        raise AssertionError("credentials must not be read when output already exists")

    async def forbidden_provider(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider must not run")

    monkeypatch.setattr(canary, "_read_mediakit_key", forbidden_key_read)
    with pytest.raises(canary.CanaryError) as error:
        asyncio.run(canary.run_operator_canary(options, remux_runner=forbidden_provider))
    assert error.value.code == "REPORT_OUTPUT_EXISTS_OR_UNWRITABLE"
    assert provider_calls == 0
    assert report.read_text(encoding="utf-8") == "existing"


def test_existing_non_private_output_directory_is_rejected_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options, _source, _key_file, _config = _options(tmp_path, execute_paid=True)
    options.output_dir.mkdir(mode=0o755)
    options.output_dir.chmod(0o755)
    provider_calls = 0

    def forbidden_key_read(_path):
        raise AssertionError("credentials must not be read for an unsafe output directory")

    async def forbidden_provider(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider must not run")

    monkeypatch.setattr(canary, "_read_mediakit_key", forbidden_key_read)
    with pytest.raises(canary.CanaryError) as error:
        asyncio.run(canary.run_operator_canary(options, remux_runner=forbidden_provider))
    assert error.value.code == "OUTPUT_DIRECTORY_NOT_PRIVATE"
    assert provider_calls == 0


def test_failure_after_candidate_download_removes_all_partial_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options, _source, _key_file, _config = _options(tmp_path, execute_paid=True)
    monkeypatch.setenv("TEST_ARK_CANARY_KEY", "ark-secret-value")
    runtime_url = "https://output.volcvideo.com/video.mp4?signature=runtime-secret"

    async def fake_remux(**_kwargs):
        return SimpleNamespace(
            runtime_url=runtime_url,
            receipt=_Dumpable({"runtime_url_sha256": hashlib.sha256(runtime_url.encode()).hexdigest()}),
        )

    async def fake_download(_url: str, destination: Path) -> None:
        destination.write_bytes(b"candidate")

    async def fake_compare(_source: Path, _candidate: Path):
        return canary.PacketEquivalenceResult(
            source_duration_seconds=1.0,
            candidate_duration_seconds=1.0,
            duration_delta_seconds=0.0,
            codec_type_fingerprints={
                "video": canary.PacketPayloadFingerprint(
                    packet_count=1,
                    total_bytes=9,
                    payload_sequence_sha256="d" * 64,
                )
            },
        )

    async def failing_chat(**_kwargs):
        raise RuntimeError("provider payload and signed URL must not escape")

    with pytest.raises(RuntimeError):
        asyncio.run(
            canary.run_operator_canary(
                options,
                remux_runner=fake_remux,
                chat_runner=failing_chat,
                download_runner=fake_download,
                packet_comparator=fake_compare,
            )
        )
    assert options.output_dir.is_dir()
    assert list(options.output_dir.iterdir()) == []


def test_redaction_failure_after_candidate_move_removes_candidate_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options, _source, _key_file, _config = _options(tmp_path, execute_paid=True)
    monkeypatch.setenv("TEST_ARK_CANARY_KEY", "ark-secret-value")
    runtime_url = "https://output.volcvideo.com/video.mp4?signature=runtime-secret"

    async def fake_remux(**_kwargs):
        return SimpleNamespace(
            runtime_url=runtime_url,
            receipt=_Dumpable({"runtime_url_sha256": hashlib.sha256(runtime_url.encode()).hexdigest()}),
        )

    async def fake_download(_url: str, destination: Path) -> None:
        destination.write_bytes(b"candidate")

    async def fake_compare(_source: Path, _candidate: Path):
        return canary.PacketEquivalenceResult(
            source_duration_seconds=1.0,
            candidate_duration_seconds=1.0,
            duration_delta_seconds=0.0,
            codec_type_fingerprints={
                "video": canary.PacketPayloadFingerprint(
                    packet_count=1,
                    total_bytes=9,
                    payload_sequence_sha256="e" * 64,
                )
            },
        )

    async def leaking_chat(**_kwargs):
        return _Dumpable({"nested": [{"provider_echo": "runtime-secret"}]})

    with pytest.raises(canary.CanaryError) as error:
        asyncio.run(
            canary.run_operator_canary(
                options,
                remux_runner=fake_remux,
                chat_runner=leaking_chat,
                download_runner=fake_download,
                packet_comparator=fake_compare,
            )
        )
    assert error.value.code == "REPORT_REDACTION_FAILED"
    assert list(options.output_dir.iterdir()) == []


def test_report_redaction_does_not_treat_short_runtime_query_values_as_secrets() -> None:
    runtime_url = "https://output.volcvideo.com/video.mp4?service_tier=default&signed_headers=host&expires=86400&signature=0123456789abcdef0123456789abcdef"
    report = {
        "contract_version": "ip-agent-mediakit-remux-chat-canary-v1",
        "video_understanding_observation": {
            "receipt": {
                "service_tier": "default",
                "max_completion_tokens": 3000,
                "billing_status": "ark_tokens_reported_amount_unavailable",
            },
            "coverage": {
                "observation_scope": "provider_sampled_visual_frames_unknown",
            },
        },
    }

    canary._assert_report_safe(
        report,
        runtime_url=runtime_url,
        forbidden_values=(),
    )


@pytest.mark.parametrize(
    "leaked_value",
    [
        "service_tier=default",
        "0123456789abcdef0123456789abcdef",
        "01234567",
        "89abcdef",
    ],
)
def test_report_redaction_still_rejects_runtime_query_pairs_and_long_secret_fragments(
    leaked_value: str,
) -> None:
    runtime_url = "https://output.volcvideo.com/video.mp4?service_tier=default&signature=0123456789abcdef0123456789abcdef"

    with pytest.raises(canary.CanaryError) as error:
        canary._assert_report_safe(
            {"provider_echo": leaked_value},
            runtime_url=runtime_url,
            forbidden_values=(),
        )

    assert error.value.code == "REPORT_REDACTION_FAILED"


def test_candidate_collision_never_deletes_the_preexisting_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options, _source, _key_file, _config = _options(tmp_path, execute_paid=True)
    monkeypatch.setenv("TEST_ARK_CANARY_KEY", "ark-secret-value")
    options.output_dir.mkdir(mode=0o700)
    runtime_url = "https://output.volcvideo.com/video.mp4?signature=runtime-secret"
    candidate_bytes = b"candidate"
    candidate_sha256 = _sha256_bytes(candidate_bytes)
    existing = options.output_dir / f"mediakit-remux-candidate-{candidate_sha256[:16]}.mp4"
    existing.write_bytes(b"preexisting-do-not-delete")
    existing.chmod(0o600)

    async def fake_remux(**_kwargs):
        return SimpleNamespace(
            runtime_url=runtime_url,
            receipt=_Dumpable({"runtime_url_sha256": hashlib.sha256(runtime_url.encode()).hexdigest()}),
        )

    async def fake_download(_url: str, destination: Path) -> None:
        destination.write_bytes(candidate_bytes)

    async def fake_compare(_source: Path, _candidate: Path):
        return canary.PacketEquivalenceResult(
            source_duration_seconds=1.0,
            candidate_duration_seconds=1.0,
            duration_delta_seconds=0.0,
            codec_type_fingerprints={
                "video": canary.PacketPayloadFingerprint(
                    packet_count=1,
                    total_bytes=9,
                    payload_sequence_sha256="f" * 64,
                )
            },
        )

    async def fake_chat(**_kwargs):
        return _Dumpable({"status": "safe"})

    with pytest.raises(canary.CanaryError) as error:
        asyncio.run(
            canary.run_operator_canary(
                options,
                remux_runner=fake_remux,
                chat_runner=fake_chat,
                download_runner=fake_download,
                packet_comparator=fake_compare,
            )
        )
    assert error.value.code == "CANDIDATE_OUTPUT_EXISTS"
    assert existing.read_bytes() == b"preexisting-do-not-delete"
    assert sorted(path.name for path in options.output_dir.iterdir()) == [existing.name]


def test_report_publish_race_preserves_existing_report_and_cleans_owned_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options, _source, _key_file, _config = _options(tmp_path, execute_paid=True)
    monkeypatch.setenv("TEST_ARK_CANARY_KEY", "ark-secret-value")
    runtime_url = "https://output.volcvideo.com/video.mp4?signature=runtime-secret"

    async def fake_remux(**_kwargs):
        return SimpleNamespace(
            runtime_url=runtime_url,
            receipt=_Dumpable({"runtime_url_sha256": hashlib.sha256(runtime_url.encode()).hexdigest()}),
        )

    async def fake_download(_url: str, destination: Path) -> None:
        destination.write_bytes(b"candidate")

    async def fake_compare(_source: Path, _candidate: Path):
        return canary.PacketEquivalenceResult(
            source_duration_seconds=1.0,
            candidate_duration_seconds=1.0,
            duration_delta_seconds=0.0,
            codec_type_fingerprints={
                "video": canary.PacketPayloadFingerprint(
                    packet_count=1,
                    total_bytes=9,
                    payload_sequence_sha256="1" * 64,
                )
            },
        )

    async def fake_chat(**_kwargs):
        return _Dumpable({"status": "safe"})

    original_writer = canary._write_private_json_once

    def racing_writer(path: Path, payload):
        path.write_text("concurrent-report", encoding="utf-8")
        path.chmod(0o600)
        original_writer(path, payload)

    monkeypatch.setattr(canary, "_write_private_json_once", racing_writer)
    with pytest.raises(canary.CanaryError) as error:
        asyncio.run(
            canary.run_operator_canary(
                options,
                remux_runner=fake_remux,
                chat_runner=fake_chat,
                download_runner=fake_download,
                packet_comparator=fake_compare,
            )
        )
    assert error.value.code == "REPORT_OUTPUT_EXISTS_OR_UNWRITABLE"
    entries = list(options.output_dir.iterdir())
    assert len(entries) == 1
    assert entries[0].suffix == ".json"
    assert entries[0].read_text(encoding="utf-8") == "concurrent-report"


def test_failure_output_contains_only_a_safe_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    options, _source, _key_file, _config = _options(tmp_path, execute_paid=True)
    monkeypatch.setattr(canary, "_parse_args", lambda _argv: options)

    async def fail_with_secret(_options):
        raise RuntimeError("https://secret.example/path?token=do-not-print")

    monkeypatch.setattr(canary, "run_operator_canary", fail_with_secret)

    assert canary.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"ok": False, "code": "INTERNAL_ERROR"}
    assert "do-not-print" not in captured.err


def test_cli_requires_source_hash_work_account_and_key_references(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert canary.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"ok": False, "code": "INVALID_ARGUMENTS"}
