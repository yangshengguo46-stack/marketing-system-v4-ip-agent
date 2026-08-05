"""Run one operator-approved MediaKit remux -> Chat protocol canary.

This script is deliberately outside the Agent/MCP runtime.  It accepts one
already sealed local reference video, creates one temporary MediaKit HTTPS
derivative, proves that the remux preserved packet payloads, and only then
submits the temporary URL to the fixed Video Understanding Chat profile.

Provider URLs and credentials remain in memory.  The only durable outputs are
a local remuxed MP4 and a secret-free JSON report, both mode ``0600``.
The report is a research observation, not a product Evidence handoff: this
canary still uses path-based byte lifecycle checks and must not be promoted as
cross-run authority.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "backend" / "packages" / "harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from deerflow.ip_agent.mediakit_remux_ingress import (  # noqa: E402
    MediaKitRemuxHTTPSCandidate,
    MediaKitRemuxIngressError,
    create_mediakit_remux_https_candidate,
)
from deerflow.ip_agent.mediakit_remux_materializer import (  # noqa: E402
    PacketEquivalenceResult,
    PacketPayloadFingerprint,
    PacketRecord,
    RemuxMaterializationError,
    compare_packet_payloads,
    download_bounded_runtime_video,
    fingerprint_packet_payloads,
    pinned_ffprobe_path,
    probe_packet_records,
    probe_streams_and_duration,
    run_ffprobe_json,
)
from deerflow.ip_agent.mediakit_video_understanding import (  # noqa: E402
    VideoUnderstandingChatError,
    VideoUnderstandingObservation,
    run_video_understanding_chat,
)

CANARY_CONTRACT_VERSION = "ip-agent-mediakit-remux-chat-canary-v1"
CANARY_PRODUCT_HANDOFF_STATUS = "research_observation_not_product_handoff"
_MAX_SOURCE_BYTES = 512 * 1024 * 1024
_MAX_CONFIG_BYTES = 1024 * 1024
_MAX_SECRET_BYTES = 4096
_DURATION_TOLERANCE_SECONDS = 0.001
_ENV_REFERENCE_RE = re.compile(r"^\$(?:\{(?P<braced>[A-Z][A-Z0-9_]*)\}|(?P<plain>[A-Z][A-Z0-9_]*))$")
_WORK_ID_RE = re.compile(r"^[0-9]{1,64}$")
_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_SAFE_ERROR_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
_URL_VALUE_RE = re.compile(r"(?i)(?:https?|mediakit|tos)://")
_CREDENTIAL_VALUE_RE = re.compile(
    r"(?i)(?:\bbearer\s+\S+|\b(?:api[_-]?key|authorization|access[_-]?token|"
    r"refresh[_-]?token|cookies?|password|passwd|secret|signature|credential)"
    r"\b\s*[:=]\s*\S+)"
)
_SENSITIVE_KEY_FRAGMENTS = (
    "apikey",
    "authorization",
    "accesstoken",
    "refreshtoken",
    "cookie",
    "password",
    "passwd",
    "secret",
    "signature",
    "credential",
    "taskid",
    "fileid",
    "requestid",
    "runtimeurl",
    "clienttoken",
)
_SAFE_SENSITIVE_REPORT_KEYS = frozenset(
    {
        "credential_values_persisted",
        "mediakit_key_source",
        "ark_key_source",
        "runtime_url_persisted",
    }
)


class CanaryError(RuntimeError):
    """An operator-safe failure containing only a stable code."""

    def __init__(self, code: str) -> None:
        self.code = code if _SAFE_ERROR_RE.fullmatch(code) else "INTERNAL_ERROR"
        super().__init__(self.code)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise CanaryError("INVALID_ARGUMENTS")


@dataclass(frozen=True)
class OperatorCanaryOptions:
    execute_paid: bool
    source: Path
    expected_source_sha256: str
    expected_work_id: str
    expected_account: str
    mediakit_key_file: Path
    ark_config: Path
    ark_model: str
    output_dir: Path


RemuxRunner = Callable[..., Awaitable[MediaKitRemuxHTTPSCandidate]]
ChatRunner = Callable[..., Awaitable[VideoUnderstandingObservation]]
DownloadRunner = Callable[[str, Path], Awaitable[None]]
PacketComparator = Callable[[Path, Path], Awaitable[PacketEquivalenceResult]]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _require_regular_file(path: Path, *, code: str, expected_mode: int | None = None) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError:
        raise CanaryError(code) from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise CanaryError(code)
    if expected_mode is not None and stat.S_IMODE(info.st_mode) != expected_mode:
        raise CanaryError(code)
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise CanaryError(code)
    return info


def _read_mediakit_key(path: Path) -> str:
    info = _require_regular_file(path, code="INVALID_MEDIAKIT_KEY_FILE", expected_mode=0o600)
    if info.st_size <= 0 or info.st_size > _MAX_SECRET_BYTES:
        raise CanaryError("INVALID_MEDIAKIT_KEY_FILE")
    try:
        encoded = path.read_bytes()
        value = encoded.decode("utf-8").strip()
    except (OSError, UnicodeDecodeError):
        raise CanaryError("INVALID_MEDIAKIT_KEY_FILE") from None
    if not value or any(character in value for character in "\r\n\x00"):
        raise CanaryError("INVALID_MEDIAKIT_KEY_FILE")
    return value


def _ark_env_name_from_config(
    path: Path,
    *,
    model_name: str,
) -> str:
    info = _require_regular_file(path, code="INVALID_ARK_CONFIG")
    if info.st_size <= 0 or info.st_size > _MAX_CONFIG_BYTES:
        raise CanaryError("INVALID_ARK_CONFIG")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        raise CanaryError("INVALID_ARK_CONFIG") from None
    if not isinstance(payload, Mapping) or not isinstance(payload.get("models"), list):
        raise CanaryError("INVALID_ARK_CONFIG")
    matches = [item for item in payload["models"] if isinstance(item, Mapping) and item.get("name") == model_name]
    if len(matches) != 1:
        raise CanaryError("ARK_MODEL_NOT_FOUND")
    reference = matches[0].get("api_key")
    if not isinstance(reference, str):
        raise CanaryError("ARK_KEY_MUST_BE_ENV_REFERENCE")
    match = _ENV_REFERENCE_RE.fullmatch(reference)
    if match is None:
        raise CanaryError("ARK_KEY_MUST_BE_ENV_REFERENCE")
    return match.group("braced") or match.group("plain")


def _read_ark_key_from_config(
    path: Path,
    *,
    model_name: str,
    environment: Mapping[str, str] | None = None,
) -> str:
    variable = _ark_env_name_from_config(path, model_name=model_name)
    environ = os.environ if environment is None else environment
    value = environ.get(variable, "")
    if not value or value != value.strip() or any(character in value for character in "\r\n\x00"):
        raise CanaryError("ARK_KEY_ENV_NOT_CONFIGURED")
    if _ENV_REFERENCE_RE.fullmatch(value):
        raise CanaryError("ARK_KEY_ENV_NOT_CONFIGURED")
    return value


def _validate_options(options: OperatorCanaryOptions) -> tuple[Path, str, str]:
    source = options.source.expanduser().resolve()
    info = _require_regular_file(source, code="INVALID_SOURCE_FILE")
    if info.st_size <= 0 or info.st_size > _MAX_SOURCE_BYTES:
        raise CanaryError("SOURCE_SIZE_OUT_OF_RANGE")
    expected_sha256 = options.expected_source_sha256.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise CanaryError("INVALID_SOURCE_SHA256")
    if _sha256_file(source) != expected_sha256:
        raise CanaryError("SOURCE_HASH_MISMATCH")
    if not _WORK_ID_RE.fullmatch(options.expected_work_id):
        raise CanaryError("INVALID_EXPECTED_WORK_ID")
    expected_account = options.expected_account.strip()
    if not expected_account or len(expected_account) > 256 or expected_account != options.expected_account or any(ord(character) < 32 or ord(character) == 127 for character in expected_account):
        raise CanaryError("INVALID_EXPECTED_ACCOUNT")
    if not _MODEL_NAME_RE.fullmatch(options.ark_model):
        raise CanaryError("INVALID_ARK_MODEL")
    return source, expected_sha256, expected_account


def validate_dry_run(options: OperatorCanaryOptions) -> None:
    """Validate the sealed input and credential references without reading keys."""

    _validate_options(options)
    key_info = _require_regular_file(
        options.mediakit_key_file.expanduser().resolve(),
        code="INVALID_MEDIAKIT_KEY_FILE",
        expected_mode=0o600,
    )
    if key_info.st_size <= 0 or key_info.st_size > _MAX_SECRET_BYTES:
        raise CanaryError("INVALID_MEDIAKIT_KEY_FILE")
    _ark_env_name_from_config(
        options.ark_config.expanduser().resolve(),
        model_name=options.ark_model,
    )
    _ffprobe_path()


def _ensure_private_output_dir(path: Path) -> Path:
    output_dir = path.expanduser().resolve()
    try:
        output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = output_dir.lstat()
    except OSError:
        raise CanaryError("INVALID_OUTPUT_DIRECTORY") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise CanaryError("INVALID_OUTPUT_DIRECTORY")
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise CanaryError("INVALID_OUTPUT_DIRECTORY")
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise CanaryError("OUTPUT_DIRECTORY_NOT_PRIVATE")
    return output_dir


def _ffprobe_path() -> Path:
    try:
        return pinned_ffprobe_path()
    except RemuxMaterializationError as exc:
        raise CanaryError(exc.code) from None


def _run_ffprobe_json(ffprobe: Path, media: Path, entries: str) -> Mapping[str, Any]:
    try:
        return run_ffprobe_json(ffprobe, media, entries)
    except RemuxMaterializationError as exc:
        raise CanaryError(exc.code) from None


def _probe_streams_and_duration(ffprobe: Path, media: Path) -> tuple[float, dict[int, str]]:
    try:
        return probe_streams_and_duration(
            ffprobe,
            media,
            json_runner=_run_ffprobe_json,
        )
    except RemuxMaterializationError as exc:
        raise CanaryError(exc.code) from None


def _probe_packet_records(ffprobe: Path, media: Path) -> list[PacketRecord]:
    try:
        return probe_packet_records(ffprobe, media, runner=subprocess.run)
    except RemuxMaterializationError as exc:
        raise CanaryError(exc.code) from None


def _fingerprint_packet_payloads(
    media: Path,
    *,
    stream_types: Mapping[int, str],
    packets: Sequence[PacketRecord],
) -> dict[str, PacketPayloadFingerprint]:
    try:
        return fingerprint_packet_payloads(
            media,
            stream_types=stream_types,
            packets=packets,
        )
    except RemuxMaterializationError as exc:
        raise CanaryError(exc.code) from None


async def _compare_packet_payloads(source: Path, candidate: Path) -> PacketEquivalenceResult:
    try:
        return await compare_packet_payloads(source, candidate)
    except RemuxMaterializationError as exc:
        raise CanaryError(exc.code) from None


async def _download_runtime_video(runtime_url: str, destination: Path) -> None:
    try:
        await download_bounded_runtime_video(runtime_url, destination)
    except RemuxMaterializationError as exc:
        raise CanaryError(exc.code) from None


def _packet_equivalence_payload(result: PacketEquivalenceResult) -> dict[str, Any]:
    return {
        "verdict": "equivalent",
        "comparison_key": "codec_type_plus_packet_payload_sequence",
        "stream_index_used_as_content_identity": False,
        "duration_tolerance_seconds": _DURATION_TOLERANCE_SECONDS,
        "source_duration_seconds": result.source_duration_seconds,
        "candidate_duration_seconds": result.candidate_duration_seconds,
        "duration_delta_seconds": result.duration_delta_seconds,
        "codec_types": {
            codec_type: {
                "packet_count": fingerprint.packet_count,
                "total_bytes": fingerprint.total_bytes,
                "payload_sequence_sha256": fingerprint.payload_sequence_sha256,
            }
            for codec_type, fingerprint in result.codec_type_fingerprints.items()
        },
    }


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        raise CanaryError("OUTPUT_DIRECTORY_FSYNC_FAILED") from None
    try:
        os.fsync(descriptor)
    except OSError:
        raise CanaryError("OUTPUT_DIRECTORY_FSYNC_FAILED") from None
    finally:
        os.close(descriptor)


def _publish_private_file_no_clobber(
    staged: Path,
    destination: Path,
    *,
    collision_code: str,
) -> None:
    _require_regular_file(staged, code="INVALID_STAGED_OUTPUT", expected_mode=0o600)
    installed = False
    try:
        os.link(staged, destination, follow_symlinks=False)
        installed = True
        _fsync_directory(destination.parent)
    except FileExistsError:
        raise CanaryError(collision_code) from None
    except CanaryError:
        if installed:
            destination.unlink(missing_ok=True)
        raise
    except OSError:
        if installed:
            destination.unlink(missing_ok=True)
        raise CanaryError(collision_code) from None
    finally:
        staged.unlink(missing_ok=True)


def _write_private_json_once(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = _canonical_json_bytes(payload)
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
    except OSError:
        raise CanaryError("REPORT_OUTPUT_EXISTS_OR_UNWRITABLE") from None
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as target:
            os.fchmod(target.fileno(), 0o600)
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        _publish_private_file_no_clobber(
            temporary,
            path,
            collision_code="REPORT_OUTPUT_EXISTS_OR_UNWRITABLE",
        )
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _runtime_url_forbidden_values(runtime_url: str) -> set[str]:
    values = {runtime_url, unquote(runtime_url)}
    try:
        parsed = urlsplit(runtime_url)
    except ValueError:
        return values
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        decoded_key = unquote(key)
        decoded_value = unquote(value)
        if key or value:
            values.add(f"{key}={value}")
        if decoded_key or decoded_value:
            values.add(f"{decoded_key}={decoded_value}")
        if _report_key_is_sensitive(decoded_key or key):
            values.update(item for item in (value, decoded_value) if item)
        for item in (value, decoded_value):
            if len(item) >= 16:
                values.update(
                    {
                        item,
                        item[:8],
                        item[:12],
                        item[-8:],
                        item[-12:],
                    }
                )
    return {value for value in values if value}


def _report_key_is_sensitive(key: str) -> bool:
    if key in _SAFE_SENSITIVE_REPORT_KEYS:
        return False
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    if normalized.endswith(("sha256", "sha256s")):
        return False
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _assert_report_safe(
    report: Mapping[str, Any],
    *,
    runtime_url: str,
    forbidden_values: Sequence[str],
) -> None:
    forbidden = {
        *(_runtime_url_forbidden_values(runtime_url)),
        *(value for value in forbidden_values if value),
    }

    def inspect(value: Any) -> None:
        if isinstance(value, Mapping):
            for raw_key, child in value.items():
                if not isinstance(raw_key, str) or _report_key_is_sensitive(raw_key):
                    raise CanaryError("REPORT_REDACTION_FAILED")
                if raw_key in {"credential_values_persisted", "runtime_url_persisted"} and child is not False:
                    raise CanaryError("REPORT_REDACTION_FAILED")
                if raw_key == "mediakit_key_source" and child != "owner_only_mode_0600_file":
                    raise CanaryError("REPORT_REDACTION_FAILED")
                if raw_key == "ark_key_source" and child != "environment_reference_from_safe_loaded_config":
                    raise CanaryError("REPORT_REDACTION_FAILED")
                inspect(child)
            return
        if isinstance(value, (list, tuple)):
            for child in value:
                inspect(child)
            return
        if isinstance(value, str):
            if _URL_VALUE_RE.search(value) or _CREDENTIAL_VALUE_RE.search(value):
                raise CanaryError("REPORT_REDACTION_FAILED")
            if any(item in value for item in forbidden):
                raise CanaryError("REPORT_REDACTION_FAILED")
            return
        if value is not None and not isinstance(value, (bool, int, float)):
            raise CanaryError("REPORT_REDACTION_FAILED")

    inspect(report)


def _model_dump(value: Any) -> Mapping[str, Any]:
    if not hasattr(value, "model_dump"):
        raise CanaryError("INVALID_INTERNAL_RECEIPT")
    payload = value.model_dump(mode="json")
    if not isinstance(payload, Mapping):
        raise CanaryError("INVALID_INTERNAL_RECEIPT")
    return payload


async def run_operator_canary(
    options: OperatorCanaryOptions,
    *,
    remux_runner: RemuxRunner | None = None,
    chat_runner: ChatRunner | None = None,
    download_runner: DownloadRunner | None = None,
    packet_comparator: PacketComparator | None = None,
) -> tuple[Path, Path]:
    """Execute exactly one paid remux and one paid Chat request, with no retries."""

    if not options.execute_paid:
        raise CanaryError("PAID_EXECUTION_NOT_CONFIRMED")
    source, source_sha256, expected_account = _validate_options(options)
    _ffprobe_path()
    output_dir = _ensure_private_output_dir(options.output_dir)
    report_name = f"mediakit-remux-canary-{_sha256_text(options.expected_work_id)[:16]}.json"
    report_path = output_dir / report_name
    if report_path.exists() or report_path.is_symlink():
        raise CanaryError("REPORT_OUTPUT_EXISTS_OR_UNWRITABLE")

    mediakit_key = _read_mediakit_key(options.mediakit_key_file.expanduser().resolve())
    ark_key = _read_ark_key_from_config(
        options.ark_config.expanduser().resolve(),
        model_name=options.ark_model,
    )
    client_token = "ipmk-remux-" + _sha256_text(f"{source_sha256}\0{options.expected_work_id}\0{expected_account}")[:48]
    remux = remux_runner or create_mediakit_remux_https_candidate
    chat = chat_runner or run_video_understanding_chat
    download = download_runner or _download_runtime_video
    compare = packet_comparator or _compare_packet_payloads

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".mediakit-remux-candidate-",
        suffix=".mp4",
        dir=output_dir,
    )
    os.close(descriptor)
    temporary_candidate = Path(temporary_name)
    os.chmod(temporary_candidate, 0o600)
    # The shared bounded downloader creates its target with O_EXCL.  Reserve a
    # collision-resistant name inside the private directory, then release the
    # empty placeholder before any network bytes are accepted.
    temporary_candidate.unlink()
    installed_candidate: Path | None = None
    report_installed = False
    try:
        candidate = await remux(
            source_path=source,
            expected_source_sha256=source_sha256,
            mediakit_api_key=mediakit_key,
            client_token=client_token,
        )
        await download(candidate.runtime_url, temporary_candidate)
        _require_regular_file(temporary_candidate, code="INVALID_STAGED_OUTPUT")
        try:
            os.chmod(temporary_candidate, 0o600, follow_symlinks=False)
        except OSError:
            raise CanaryError("INVALID_STAGED_OUTPUT") from None
        candidate_size = temporary_candidate.stat().st_size
        if candidate_size <= 0 or candidate_size > _MAX_SOURCE_BYTES:
            raise CanaryError("CANDIDATE_SIZE_OUT_OF_RANGE")
        candidate_sha256 = await asyncio.to_thread(_sha256_file, temporary_candidate)
        equivalence = await compare(source, temporary_candidate)
        observation = await chat(
            video_url=candidate.runtime_url,
            source_sha256=candidate_sha256,
            duration_seconds=equivalence.candidate_duration_seconds,
            ark_api_key=ark_key,
            mediakit_api_key=mediakit_key,
        )

        final_candidate = output_dir / f"mediakit-remux-candidate-{candidate_sha256[:16]}.mp4"
        _publish_private_file_no_clobber(
            temporary_candidate,
            final_candidate,
            collision_code="CANDIDATE_OUTPUT_EXISTS",
        )
        installed_candidate = final_candidate

        report: dict[str, Any] = {
            "contract_version": CANARY_CONTRACT_VERSION,
            "status": "completed",
            "product_handoff_status": CANARY_PRODUCT_HANDOFF_STATUS,
            "scope": "isolated_operator_only_public_reference_protocol_canary",
            "operator_binding": {
                "binding_basis": "operator_supplied_work_and_account_plus_sealed_source_sha256",
                "expected_work_id_sha256": _sha256_text(options.expected_work_id),
                "expected_account_sha256": _sha256_text(expected_account),
                "source_sha256": source_sha256,
            },
            "candidate": {
                "sha256": candidate_sha256,
                "size_bytes": candidate_size,
                "relative_output_name": final_candidate.name,
                "derived_from_source_sha256": source_sha256,
            },
            "packet_payload_equivalence": _packet_equivalence_payload(equivalence),
            "remux_receipt": _model_dump(candidate.receipt),
            "video_understanding_observation": _model_dump(observation),
            "controls": {
                "execute_paid_explicit": True,
                "automatic_retries": 0,
                "runtime_url_persisted": False,
                "credential_values_persisted": False,
                "mediakit_key_source": "owner_only_mode_0600_file",
                "ark_key_source": "environment_reference_from_safe_loaded_config",
            },
        }
        _assert_report_safe(
            report,
            runtime_url=candidate.runtime_url,
            forbidden_values=(
                mediakit_key,
                ark_key,
                client_token,
                options.expected_work_id,
                expected_account,
            ),
        )
        _write_private_json_once(report_path, report)
        report_installed = True
        return report_path, final_candidate
    finally:
        temporary_candidate.unlink(missing_ok=True)
        if installed_candidate is not None and not report_installed:
            installed_candidate.unlink(missing_ok=True)
            try:
                _fsync_directory(output_dir)
            except CanaryError:
                pass


def _parse_args(argv: Sequence[str] | None = None) -> OperatorCanaryOptions:
    parser = _SafeArgumentParser(
        description="Run one explicitly approved MediaKit remux-to-Chat protocol canary.",
    )
    parser.add_argument("--execute-paid", action="store_true")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--expected-work-id", required=True)
    parser.add_argument("--expected-account", required=True)
    parser.add_argument("--mediakit-key-file", type=Path, required=True)
    parser.add_argument("--ark-config", type=Path, required=True)
    parser.add_argument("--ark-model", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    namespace = parser.parse_args(argv)
    return OperatorCanaryOptions(
        execute_paid=namespace.execute_paid,
        source=namespace.source,
        expected_source_sha256=namespace.expected_source_sha256,
        expected_work_id=namespace.expected_work_id,
        expected_account=namespace.expected_account,
        mediakit_key_file=namespace.mediakit_key_file,
        ark_config=namespace.ark_config,
        ark_model=namespace.ark_model,
        output_dir=namespace.output_dir,
    )


def _safe_error_code(error: BaseException) -> str:
    if isinstance(error, CanaryError):
        return error.code
    if isinstance(error, (MediaKitRemuxIngressError, VideoUnderstandingChatError)):
        code = str(error.code or "")
        return code if _SAFE_ERROR_RE.fullmatch(code) else "PROVIDER_ERROR"
    if isinstance(error, KeyboardInterrupt):
        return "INTERRUPTED"
    return "INTERNAL_ERROR"


def main(argv: Sequence[str] | None = None) -> int:
    try:
        options = _parse_args(argv)
        if not options.execute_paid:
            validate_dry_run(options)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "code": "DRY_RUN_VALIDATED",
                        "provider_calls": 0,
                    },
                    separators=(",", ":"),
                )
            )
            return 0
        report_path, candidate_path = asyncio.run(run_operator_canary(options))
    except BaseException as error:
        if isinstance(error, SystemExit):
            raise
        print(
            json.dumps({"ok": False, "code": _safe_error_code(error)}, separators=(",", ":")),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "code": "CANARY_COMPLETED",
                "report": report_path.name,
                "candidate": candidate_path.name,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
