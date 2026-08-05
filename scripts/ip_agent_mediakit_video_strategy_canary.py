"""Run one isolated AI MediaKit video-understanding strategy canary.

This is a research-only operator harness.  It is not imported by the Gateway,
the reusable harness, or the default IP Agent.  A provider submission requires
both ``--authorize-paid-call`` and an explicit local CNY risk cap.  The cap can
gate the published MediaKit input-minute estimate, but it is not enforced by
the provider and cannot bound the separately billed Ark tokens.

The redacted receipt is not a recovery authority.  Exact submit intent, the
deterministic client token and the provider task ID are encrypted in a private,
canary-local SQLite database.  ``--resume`` may replay one uncertain submit
with the identical body/token, or query an already submitted task without
uploading or submitting again.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "backend" / "packages" / "harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from deerflow.config.database_config import DatabaseConfig  # noqa: E402
from deerflow.persistence.channel_connections.sql import (  # noqa: E402
    ChannelCredentialCipher,
)
from deerflow.persistence.engine import (  # noqa: E402
    close_engine,
    get_session_factory,
    init_engine_from_config,
)
from deerflow.persistence.personal_ip_paid_calls import (  # noqa: E402
    EVIDENCE_VIDEO_STRATEGY_OPERATOR_CAP_POLICY_VERSION,
    MEDIAKIT_VIDEO_STRATEGY_PROVIDER_SUBMISSION_CONTRACT_VERSION,
    MEDIAKIT_VIDEO_STRATEGY_PROVIDER_SUBMITTED_TASK_CONTRACT_VERSION,
    PersonalIPPaidCallRepository,
)

CONTRACT_VERSION = "ip-agent-mediakit-video-strategy-canary-v1"
ENDPOINT = "https://mediakit.cn-beijing.volces.com"
UPLOAD_TARGET_PATH = "/api/v1/tools-sync/request-media-upload-url"
SUBMIT_PATH = "/api/v1/tools/video-understand-router"
TASK_PATH_PREFIX = "/api/v1/tasks/"
DEFAULT_API_KEY_ENV = "MEDIAKIT_API_KEY"
DEFAULT_OUTPUT_ROOT = ROOT / ".deer-flow" / "acceptance"

FIXED_PROMPT = "请仅基于可见画面和可听音频，按时间顺序描述可供剪辑核验的场景变化、人物动作、对白或环境声与转场线索；不要推断身份、意图、因果或传播效果，不确定处明确标注。"
LEVEL = "Quality"
SCENE = "editing"
MEDIAKIT_CNY_PER_INPUT_MINUTE = Decimal("0.01")
STRATEGY_ADAPTER_VERSION = "volcengine-mediakit-video-strategy-research-v1"
STRATEGY_PROFILE_VERSION = "ip-editing-audiovisual-research-observation-v1"
STRATEGY_REQUEST_CONTRACT_VERSION = "ip-mediakit-video-strategy-request-v1"
STRATEGY_PROVIDER_TOOL_NAME = "video-understand-router"
STRATEGY_CAPABILITY = "video_understanding_smart_strategy"
RECOVERY_OWNER = "operator-mediakit-video-strategy"
RECOVERY_THREAD = "mediakit-video-strategy-canary"
RECOVERY_KEY_NAME = "paid-recovery.key"
RECOVERY_DATABASE_DIR_NAME = "recovery-db"

_MAX_SOURCE_BYTES = 5 * 1024 * 1024 * 1024
_MAX_KEY_BYTES = 4096
_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_RECEIPT_BYTES = 256 * 1024
_MAX_CONTENT_TEXT_BYTES = 32 * 1024
_MAX_CONTENT_TOTAL_BYTES = 64 * 1024
_MAX_POLL_ATTEMPTS = 60
_POLL_INTERVAL_SECONDS = 3.0
_REQUEST_TIMEOUT_SECONDS = 120.0
_TOTAL_TIMEOUT_SECONDS = 600.0
_FFPROBE_TIMEOUT_SECONDS = 20.0
_CHUNK_BYTES = 1024 * 1024
_PROVIDER_HOST_SUFFIXES = (
    "volces.com",
    "volccdn.com",
    "volcvideo.com",
    "volcvod.com",
    "bytevod.com",
)
_SAFE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
_URL_RE = re.compile(r"(?i)\b(?:https?|mediakit|tos)://[^\s<>\"']+")
_SAFE_PROVIDER_ERROR_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
_SAFE_PROVIDER_ERROR_PARAM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:(?:\.[A-Za-z_][A-Za-z0-9_]*)|(?:\[[0-9]{1,6}\])){0,15}$")
_PROVIDER_ERROR_FIELDS = ("code", "type", "param")
_FAILURE_STAGES = frozenset({"upload_target", "media_upload", "submit", "poll"})
_FAILURE_CLASSIFICATIONS = frozenset(
    {
        "terminal_provider_rejection",
        "terminal_provider_submission_rejection",
        "terminal_provider_task_rejection",
        "transport_unknown",
    }
)
_REQUEST_STAGE_NAMES = {
    "UPLOAD_TARGET": "upload_target",
    "MEDIA_UPLOAD": "media_upload",
    "SUBMIT": "submit",
    "POLL": "poll",
}
_TERMINAL_FAILURE_STATUSES = frozenset({"failed"})
_TERMINAL_CANCELLED_STATUSES = frozenset({"canceled", "cancelled"})
_PENDING_STATUSES = frozenset({"queued", "running"})

BillingOutcome = Literal["not_submitted", "provider_rejected", "unknown", "usage_returned"]


class CanaryError(RuntimeError):
    """One bounded operator-safe failure without a provider payload."""

    def __init__(
        self,
        code: str,
        *,
        billing_outcome: BillingOutcome = "not_submitted",
        receipt_status: str = "failed_safe",
        failure_classification: str | None = None,
        failure_stage: str | None = None,
        provider_error: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code if _SAFE_CODE_RE.fullmatch(code) else "INTERNAL_ERROR"
        self.billing_outcome = billing_outcome
        self.receipt_status = receipt_status
        self.failure: dict[str, Any] | None = None
        if failure_classification is not None or failure_stage is not None or provider_error is not None:
            if failure_classification not in _FAILURE_CLASSIFICATIONS or failure_stage not in _FAILURE_STAGES:
                self.code = "INTERNAL_ERROR"
                self.billing_outcome = "unknown"
                self.receipt_status = "failed_safe"
            else:
                self.failure = {
                    "classification": failure_classification,
                    "stage": failure_stage,
                    "provider_error": dict(provider_error) if provider_error is not None else None,
                }
        super().__init__(self.code)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise CanaryError("INVALID_ARGUMENTS")


@dataclass(frozen=True)
class CanaryOptions:
    video_path: Path
    authorize_paid_call: bool
    maximum_cny: Decimal
    output_dir: Path | None
    api_key_env: str
    mediakit_key_file: Path | None
    resume: bool = False


@dataclass(frozen=True)
class Preflight:
    source_path: Path
    source_sha256: str
    source_size_bytes: int
    local_duration_seconds: Decimal
    mediakit_public_estimate_cny: Decimal
    maximum_cny: Decimal
    output_dir: Path
    client_token: str


class _PathByteStream(httpx.AsyncByteStream):
    def __init__(self, source_descriptor: int) -> None:
        self._source_descriptor = source_descriptor
        self._sha256 = hashlib.sha256()
        self._size_bytes = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        descriptor = os.dup(self._source_descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        with os.fdopen(descriptor, "rb") as source:
            while chunk := await asyncio.to_thread(source.read, _CHUNK_BYTES):
                self._sha256.update(chunk)
                self._size_bytes += len(chunk)
                yield chunk

    def require_expected(self, *, expected_sha256: str, expected_size_bytes: int) -> None:
        if self._size_bytes != expected_size_bytes or self._sha256.hexdigest() != expected_sha256:
            raise CanaryError("UPLOADED_SOURCE_INTEGRITY_MISMATCH")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _monotonic() -> float:
    return time.monotonic()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            for chunk in iter(lambda: source.read(_CHUNK_BYTES), b""):
                digest.update(chunk)
    except OSError:
        raise CanaryError("SOURCE_READ_FAILED") from None
    return digest.hexdigest()


def _sha256_descriptor(source_descriptor: int) -> str:
    digest = hashlib.sha256()
    descriptor = os.dup(source_descriptor)
    os.lseek(descriptor, 0, os.SEEK_SET)
    with os.fdopen(descriptor, "rb") as source:
        for chunk in iter(lambda: source.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_bound_source(preflight: Preflight) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(preflight.source_path, flags)
        info = os.fstat(descriptor)
    except OSError:
        raise CanaryError("SOURCE_BINDING_FAILED") from None
    if not stat.S_ISREG(info.st_mode) or info.st_size != preflight.source_size_bytes:
        os.close(descriptor)
        raise CanaryError("SOURCE_CHANGED_BEFORE_UPLOAD")
    try:
        opened_sha256 = _sha256_descriptor(descriptor)
    except OSError:
        os.close(descriptor)
        raise CanaryError("SOURCE_BINDING_FAILED") from None
    if opened_sha256 != preflight.source_sha256:
        os.close(descriptor)
        raise CanaryError("SOURCE_CHANGED_BEFORE_UPLOAD")
    return descriptor


def _decimal_text(value: Decimal, *, places: int = 6) -> str:
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum, rounding=ROUND_HALF_UP), "f")


def _parse_positive_decimal(value: str, *, code: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise CanaryError(code) from None
    quantum = Decimal("0.000001")
    if not parsed.is_finite() or parsed < quantum or parsed > Decimal(10000) or parsed != parsed.quantize(quantum):
        raise CanaryError(code)
    return parsed


def _published_mediakit_estimate(duration_seconds: Decimal) -> Decimal:
    if not duration_seconds.is_finite() or duration_seconds <= 0:
        raise CanaryError("INVALID_VIDEO_DURATION")
    exact = duration_seconds / Decimal(60) * MEDIAKIT_CNY_PER_INPUT_MINUTE
    return exact.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)


def _absolute_lexical_path(path: Path) -> Path:
    """Make a path absolute without resolving away a symlink leaf."""

    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _regular_source(path: Path) -> tuple[Path, os.stat_result]:
    source = _absolute_lexical_path(path)
    try:
        info = source.lstat()
    except OSError:
        raise CanaryError("SOURCE_NOT_FOUND") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise CanaryError("SOURCE_NOT_REGULAR_FILE")
    if source.suffix.lower() != ".mp4":
        raise CanaryError("SOURCE_MUST_BE_MP4")
    if info.st_size <= 0 or info.st_size > _MAX_SOURCE_BYTES:
        raise CanaryError("SOURCE_SIZE_OUT_OF_RANGE")
    return source, info


def _probe_duration_seconds(path: Path) -> Decimal:
    project_ffprobe = ROOT / ".deer-flow" / "toolchains" / "ffmpeg" / "bin" / "ffprobe"
    ffprobe = str(project_ffprobe) if project_ffprobe.is_file() and os.access(project_ffprobe, os.X_OK) else None
    if not ffprobe:
        ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise CanaryError("FFPROBE_NOT_FOUND")
    safe_environment = {
        "PATH": os.environ.get("PATH", ""),
        "LC_ALL": "C",
    }
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration,format_name",
                "-of",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            timeout=_FFPROBE_TIMEOUT_SECONDS,
            env=safe_environment,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise CanaryError("FFPROBE_FAILED") from None
    if completed.returncode != 0 or len(completed.stdout) > 64 * 1024:
        raise CanaryError("FFPROBE_FAILED")
    try:
        payload = json.loads(completed.stdout)
        format_payload = payload["format"]
        duration = Decimal(str(format_payload["duration"]))
        format_names = {item.strip().lower() for item in str(format_payload["format_name"]).split(",")}
    except (KeyError, TypeError, ValueError, InvalidOperation, json.JSONDecodeError):
        raise CanaryError("FFPROBE_INVALID_RESULT") from None
    if not ({"mp4", "mov"} & format_names):
        raise CanaryError("SOURCE_MUST_BE_MP4")
    if not duration.is_finite() or duration <= 0 or duration > Decimal(7200):
        raise CanaryError("INVALID_VIDEO_DURATION")
    return duration


def _is_git_ignored(path: Path) -> bool:
    path = _absolute_lexical_path(path)
    try:
        path.relative_to(ROOT)
    except ValueError:
        return False
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "check-ignore",
                "--quiet",
                "--no-index",
                "--",
                str(path),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _require_no_symlink_ancestors(path: Path, *, code: str) -> None:
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        raise CanaryError(code) from None
    current = ROOT
    for component in relative.parts[:-1]:
        current = current / component
        try:
            info = current.lstat()
        except OSError:
            raise CanaryError(code) from None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise CanaryError(code)


def _validate_output_dir(path: Path, *, resume: bool = False) -> Path:
    output_dir = _absolute_lexical_path(path)
    try:
        output_dir.relative_to(ROOT)
    except ValueError:
        raise CanaryError("OUTPUT_DIR_OUTSIDE_REPOSITORY") from None
    _require_no_symlink_ancestors(output_dir, code="OUTPUT_PARENT_INVALID")
    if not _is_git_ignored(output_dir):
        raise CanaryError("OUTPUT_DIR_NOT_GIT_IGNORED")
    try:
        parent_info = output_dir.parent.lstat()
    except OSError:
        raise CanaryError("OUTPUT_PARENT_NOT_FOUND") from None
    if stat.S_ISLNK(parent_info.st_mode) or not stat.S_ISDIR(parent_info.st_mode):
        raise CanaryError("OUTPUT_PARENT_INVALID")
    if resume:
        try:
            info = output_dir.lstat()
        except OSError:
            raise CanaryError("RESUME_STATE_NOT_FOUND") from None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
            raise CanaryError("RESUME_STATE_INVALID")
    elif output_dir.exists() or output_dir.is_symlink():
        raise CanaryError("OUTPUT_DIR_ALREADY_EXISTS")
    return output_dir


def _ensure_private_output_dir(path: Path) -> None:
    try:
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
        os.chmod(path, 0o700)
    except OSError:
        raise CanaryError("OUTPUT_DIR_CREATE_FAILED") from None
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        raise CanaryError("OUTPUT_DIR_NOT_PRIVATE")


def _write_private_once(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        raise CanaryError("PRIVATE_STATE_WRITE_FAILED") from None
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
        raise CanaryError("PRIVATE_STATE_WRITE_FAILED")


def _new_recovery_key(path: Path) -> str:
    value = secrets.token_urlsafe(48)
    _write_private_once(path, (value + "\n").encode("utf-8"))
    return value


def _read_owner_private_text(path: Path, *, code: str) -> str:
    try:
        info = path.lstat()
    except OSError:
        raise CanaryError(code) from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid() or not 0 < info.st_size <= _MAX_KEY_BYTES:
        raise CanaryError(code)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            os.close(descriptor)
            raise CanaryError(code)
        with os.fdopen(descriptor, "rb") as source:
            raw = source.read(_MAX_KEY_BYTES + 1)
        value = raw.decode("utf-8").strip()
    except CanaryError:
        raise
    except (OSError, UnicodeError):
        raise CanaryError(code) from None
    return _validate_secret(value, code=code)


def _ensure_private_database_dir(path: Path, *, resume: bool) -> None:
    if resume:
        try:
            info = path.lstat()
        except OSError:
            raise CanaryError("RECOVERY_DATABASE_NOT_FOUND") from None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
            raise CanaryError("RECOVERY_DATABASE_INVALID")
        return
    try:
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
        os.chmod(path, 0o700)
    except OSError:
        raise CanaryError("RECOVERY_DATABASE_CREATE_FAILED") from None


def _secure_database_files(database_dir: Path) -> None:
    for path in database_dir.iterdir():
        try:
            info = path.lstat()
        except OSError:
            raise CanaryError("RECOVERY_DATABASE_INVALID") from None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise CanaryError("RECOVERY_DATABASE_INVALID")
        os.chmod(path, 0o600)


async def _schema_head() -> str:
    from sqlalchemy import text

    session_factory = get_session_factory()
    if session_factory is None:
        raise CanaryError("RECOVERY_DATABASE_UNAVAILABLE")
    async with session_factory() as session:
        value = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    return str(value)


def _validate_secret(value: str, *, code: str) -> str:
    if not value or len(value.encode("utf-8")) > _MAX_KEY_BYTES:
        raise CanaryError(code)
    if value.strip() != value or any(character.isspace() for character in value) or len(value) < 8:
        raise CanaryError(code)
    return value


def _read_key_file(path: Path) -> str:
    key_path = _absolute_lexical_path(path)
    try:
        key_path.relative_to(ROOT)
    except ValueError:
        raise CanaryError("MEDIAKIT_KEY_FILE_OUTSIDE_REPOSITORY") from None
    _require_no_symlink_ancestors(key_path, code="MEDIAKIT_KEY_FILE_INVALID")
    if not _is_git_ignored(key_path):
        raise CanaryError("MEDIAKIT_KEY_FILE_NOT_GIT_IGNORED")
    try:
        info = key_path.lstat()
    except OSError:
        raise CanaryError("MEDIAKIT_KEY_FILE_INVALID") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid() or info.st_size <= 0 or info.st_size > _MAX_KEY_BYTES:
        raise CanaryError("MEDIAKIT_KEY_FILE_INVALID")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(key_path, flags)
        opened_info = os.fstat(descriptor)
        if (opened_info.st_dev, opened_info.st_ino) != (info.st_dev, info.st_ino):
            os.close(descriptor)
            raise CanaryError("MEDIAKIT_KEY_FILE_INVALID")
        with os.fdopen(descriptor, "rb") as key_input:
            raw = key_input.read(_MAX_KEY_BYTES + 1)
        if len(raw) > _MAX_KEY_BYTES:
            raise CanaryError("MEDIAKIT_KEY_FILE_INVALID")
        value = raw.decode("utf-8").strip()
    except CanaryError:
        raise
    except (OSError, UnicodeError):
        raise CanaryError("MEDIAKIT_KEY_FILE_INVALID") from None
    return _validate_secret(value, code="MEDIAKIT_KEY_FILE_INVALID")


def _load_api_key(options: CanaryOptions) -> tuple[str, str]:
    environment_value = os.environ.get(options.api_key_env)
    if options.mediakit_key_file is not None and environment_value:
        raise CanaryError("AMBIGUOUS_MEDIAKIT_KEY_SOURCE")
    if options.mediakit_key_file is not None:
        return _read_key_file(options.mediakit_key_file), "owner_0600_gitignored_file"
    if environment_value:
        return _validate_secret(environment_value, code="MEDIAKIT_KEY_ENV_INVALID"), "environment"
    raise CanaryError("MEDIAKIT_KEY_NOT_CONFIGURED")


def _client_token(*, source_sha256: str, source_size_bytes: int) -> str:
    digest = _canonical_sha256(
        {
            "contract_version": CONTRACT_VERSION,
            "source_sha256": source_sha256,
            "source_size_bytes": source_size_bytes,
            "prompt_sha256": _sha256_text(FIXED_PROMPT),
            "level": LEVEL,
            "scene": SCENE,
            "manual_option": {"need_audio": True},
        }
    )
    token = f"ipmk-vus-{digest[:55]}"
    if len(token) > 64 or not token.isascii() or not token.isprintable():
        raise CanaryError("INVALID_CLIENT_TOKEN")
    return token


def _prepare_preflight(options: CanaryOptions, *, duration_seconds: Decimal) -> Preflight:
    if not options.authorize_paid_call:
        raise CanaryError("PAID_CALL_NOT_AUTHORIZED")
    source, info = _regular_source(options.video_path)
    maximum_cny = options.maximum_cny
    quantum = Decimal("0.000001")
    if not maximum_cny.is_finite() or maximum_cny < quantum or maximum_cny > Decimal(10000) or maximum_cny != maximum_cny.quantize(quantum):
        raise CanaryError("INVALID_MAXIMUM_CNY")
    estimate = _published_mediakit_estimate(duration_seconds)
    if estimate > maximum_cny:
        raise CanaryError("MEDIAKIT_ESTIMATE_EXCEEDS_MAXIMUM_CNY")
    source_sha256 = _sha256_file(source)
    output_dir = options.output_dir or (DEFAULT_OUTPUT_ROOT / f"mediakit-video-strategy-{source_sha256[:16]}")
    output_dir = _validate_output_dir(output_dir, resume=options.resume)
    return Preflight(
        source_path=source,
        source_sha256=source_sha256,
        source_size_bytes=info.st_size,
        local_duration_seconds=duration_seconds,
        mediakit_public_estimate_cny=estimate,
        maximum_cny=maximum_cny,
        output_dir=output_dir,
        client_token=_client_token(source_sha256=source_sha256, source_size_bytes=info.st_size),
    )


def _base_receipt(preflight: Preflight, *, key_source: str) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "provider": "volcengine-mediakit",
        "capability": "video_understanding_smart_strategy",
        "exposure": "isolated_research_canary_only",
        "created_at": _utcnow().isoformat(),
        "status": "prepared",
        "billing_outcome": "not_submitted",
        "safe_error_code": None,
        "failure": None,
        "source": {
            "sha256": preflight.source_sha256,
            "size_bytes": preflight.source_size_bytes,
            "local_duration_seconds": _decimal_text(preflight.local_duration_seconds),
            "hash_checks": 1,
        },
        "credential_source": key_source,
        "authorization": {
            "explicit_paid_call_authorization": True,
            "maximum_cny_cap": _decimal_text(preflight.maximum_cny),
            "cap_scope": "local_admission_against_known_mediakit_public_estimate_only",
            "provider_enforced": False,
            "cap_is_provider_quote": False,
            "cap_is_invoice": False,
            "ark_token_charge_is_not_bounded_by_this_cap": True,
            "postflight_mediakit_estimate_exceeds_cap": None,
        },
        "request_projection": {
            "endpoint_sha256": _sha256_text(ENDPOINT),
            "video_urls_sha256": [],
            "prompt": FIXED_PROMPT,
            "prompt_sha256": _sha256_text(FIXED_PROMPT),
            "level": LEVEL,
            "scene": SCENE,
            "manual_option": {"need_audio": True},
            "client_token_sha256": _sha256_text(preflight.client_token),
            "callback_fields_included": False,
            "prefer_models_included": False,
            "prefer_endpoints_included": False,
            "submit_retries": 0,
            "provider_request_sha256": None,
            "idempotency_scope": "same_source_and_fixed_projection_reuse_the_same_client_token",
        },
        "provider_identifier_sha256": {
            "file_id": None,
            "upload_url": None,
            "task_id": None,
            "request_ids_by_stage": {
                "upload_target": [],
                "media_upload": [],
                "submit": [],
                "poll": [],
            },
        },
        "execution": {
            "upload_target_attempts": 0,
            "media_upload_attempts": 0,
            "submit_attempts": 0,
            "poll_attempts": 0,
            "maximum_poll_attempts": _MAX_POLL_ATTEMPTS,
            "request_timeout_seconds": _REQUEST_TIMEOUT_SECONDS,
            "total_timeout_seconds": _TOTAL_TIMEOUT_SECONDS,
        },
        "recovery": {
            "encrypted_exact_submission_persisted": False,
            "raw_task_authority_persisted": False,
            "maximum_exact_submit_replays": 1,
            "upload_replayed_on_resume": False,
            "query_only_after_task_id": True,
            "can_count_as_recoverable_execution": False,
        },
        "provider_response_sha256_by_stage": {
            "upload_target": [],
            "media_upload": [],
            "submit": [],
            "poll": [],
        },
        "provider_reported_duration_seconds": None,
        "token_usage": None,
        "contents": None,
        "pricing": {
            "status": "public_tariff_estimate_not_provider_quote_or_invoice",
            "mediakit": {
                "unit_price_cny_per_input_minute": "0.01",
                "preflight_input_duration_seconds": _decimal_text(preflight.local_duration_seconds),
                "preflight_public_estimate_cny": _decimal_text(preflight.mediakit_public_estimate_cny),
                "provider_reported_duration_seconds": None,
                "postflight_public_estimate_cny": None,
                "actual_cny_returned_by_api": False,
            },
            "ark_tokens": {
                "billed_separately": True,
                "preflight_usage": "unknown_until_provider_usage",
                "returned_aggregate_usage": None,
                "cny_estimate_status": "unavailable",
                "cny_estimate_unavailable_reasons": [
                    "provider_selected_model_not_attested",
                    "audio_vs_non_audio_input_token_split_not_returned",
                ],
                "actual_cny_returned_by_api": False,
            },
            "combined_total_cny": "unknown",
        },
    }


def _assert_redacted(payload: Mapping[str, Any], *, forbidden: Sequence[str]) -> bytes:
    encoded = _canonical_bytes(payload) + b"\n"
    if len(encoded) > _MAX_RECEIPT_BYTES:
        raise CanaryError("RECEIPT_TOO_LARGE", billing_outcome="unknown")
    text = encoded.decode("utf-8")
    for value in forbidden:
        if value and value in text:
            raise CanaryError("RECEIPT_REDACTION_FAILED", billing_outcome="unknown")
    if _URL_RE.search(text):
        raise CanaryError("RECEIPT_REDACTION_FAILED", billing_outcome="unknown")
    return encoded


def _write_receipt(path: Path, payload: Mapping[str, Any], *, forbidden: Sequence[str]) -> None:
    encoded = _assert_redacted(payload, forbidden=forbidden)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        if path.exists():
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise CanaryError("RECEIPT_PATH_INVALID", billing_outcome="unknown")
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except CanaryError:
        temporary.unlink(missing_ok=True)
        raise
    except OSError:
        temporary.unlink(missing_ok=True)
        raise CanaryError("RECEIPT_WRITE_FAILED", billing_outcome="unknown") from None


def _read_receipt(path: Path, *, options: CanaryOptions) -> dict[str, Any]:
    try:
        info = path.lstat()
    except OSError:
        raise CanaryError("RECOVERY_RECEIPT_NOT_FOUND") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid() or not 0 < info.st_size <= _MAX_RECEIPT_BYTES:
        raise CanaryError("RECOVERY_RECEIPT_INVALID")
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise CanaryError("RECOVERY_RECEIPT_INVALID") from None
    if (
        not isinstance(payload, dict)
        or payload.get("contract_version") != CONTRACT_VERSION
        or payload.get("provider") != "volcengine-mediakit"
        or payload.get("capability") != STRATEGY_CAPABILITY
        or not isinstance(payload.get("source"), dict)
        or not isinstance(payload.get("authorization"), dict)
        or payload["authorization"].get("maximum_cny_cap") != _decimal_text(options.maximum_cny)
    ):
        raise CanaryError("RECOVERY_RECEIPT_BINDING_MISMATCH")
    _assert_redacted(payload, forbidden=())
    return payload


def _strategy_request_projection(submit_body: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": STRATEGY_REQUEST_CONTRACT_VERSION,
        "adapter_version": STRATEGY_ADAPTER_VERSION,
        "profile_version": STRATEGY_PROFILE_VERSION,
        "provider_tool_name": STRATEGY_PROVIDER_TOOL_NAME,
        "method": "POST",
        "endpoint_sha256": _sha256_text(f"{ENDPOINT}{SUBMIT_PATH}"),
        "body": dict(submit_body),
        "automatic_retries": 0,
        "callback_url_mode": "omitted",
    }


def _strategy_submission_envelope(
    *,
    preflight: Preflight,
    submit_body: Mapping[str, Any],
) -> dict[str, Any]:
    body = dict(submit_body)
    video_urls = body.get("video_urls")
    if not isinstance(video_urls, list) or len(video_urls) != 1 or not isinstance(video_urls[0], str):
        raise CanaryError("INVALID_STRATEGY_SUBMISSION")
    request_projection = _strategy_request_projection(body)
    return {
        "contract_version": MEDIAKIT_VIDEO_STRATEGY_PROVIDER_SUBMISSION_CONTRACT_VERSION,
        "provider": "volcengine-mediakit",
        "capability": STRATEGY_CAPABILITY,
        "adapter_version": STRATEGY_ADAPTER_VERSION,
        "profile_version": STRATEGY_PROFILE_VERSION,
        "endpoint_sha256": request_projection["endpoint_sha256"],
        "source_sha256": preflight.source_sha256,
        "provider_input_ref_sha256": _sha256_text(video_urls[0]),
        "request_sha256": _canonical_sha256(request_projection),
        "submit_body_sha256": _canonical_sha256(body),
        "submit_body": body,
        "automatic_retries": 0,
        "callback_url_mode": "omitted",
    }


def _strategy_submitted_task_record(
    *,
    task_id: str,
    client_token: str,
    request_sha256: str,
    response_encoded: bytes,
    request_ids: Sequence[str],
) -> dict[str, Any]:
    return {
        "contract_version": MEDIAKIT_VIDEO_STRATEGY_PROVIDER_SUBMITTED_TASK_CONTRACT_VERSION,
        "provider": "volcengine-mediakit",
        "capability": STRATEGY_CAPABILITY,
        "task_id": task_id,
        "task_id_sha256": _sha256_text(task_id),
        "request_sha256": request_sha256,
        "client_token_sha256": _sha256_text(client_token),
        "provider_response_sha256": hashlib.sha256(response_encoded).hexdigest(),
        "provider_response_size_bytes": len(response_encoded),
        "provider_request_id_sha256s": [_sha256_text(value) for value in request_ids],
    }


def _maximum_amount_micros(value: Decimal) -> int:
    micros = value * Decimal(1_000_000)
    if micros != micros.to_integral_value():
        raise CanaryError("INVALID_MAXIMUM_CNY")
    return int(micros)


def _duration_millis(value: Decimal) -> int:
    return int((value * Decimal(1000)).to_integral_value(rounding=ROUND_CEILING))


async def _create_admitted_scope(
    repository: PersonalIPPaidCallRepository,
    *,
    preflight: Preflight,
    submission_envelope: Mapping[str, Any],
    recovery_key: str,
) -> dict[str, Any]:
    request_sha256 = str(submission_envelope["request_sha256"])
    maximum_micros = _maximum_amount_micros(preflight.maximum_cny)
    execution_run_id = f"strategy-run-{preflight.source_sha256[:24]}"
    proof_seed = {
        "contract_version": "ip-mediakit-video-strategy-canary-consent-v1",
        "source_sha256": preflight.source_sha256,
        "request_sha256": request_sha256,
        "maximum_amount_micros": maximum_micros,
        "authorization": "explicit-cli-flag",
    }
    now = _utcnow()
    requested = await repository.request_call(
        owner_user_id=RECOVERY_OWNER,
        request_key=f"strategy:{preflight.source_sha256[:32]}",
        scope_kind="run",
        thread_id=RECOVERY_THREAD,
        origin_run_id=f"strategy-origin-{preflight.source_sha256[:24]}",
        server_name="ip-agent-mediakit-video-strategy-canary",
        tool_name="video-understand-router",
        tool_args_sha256=_canonical_sha256(
            {
                "source_sha256": preflight.source_sha256,
                "request_sha256": request_sha256,
                "maximum_amount_micros": maximum_micros,
            }
        ),
        provider="volcengine-mediakit",
        capability=STRATEGY_CAPABILITY,
        model=STRATEGY_ADAPTER_VERSION,
        sku="video-understand-router",
        provider_label="MediaKit",
        capability_label="Video understanding smart strategy",
        object_ref_label=f"reference {preflight.source_sha256[:12]}...{preflight.source_sha256[-12:]}",
        source_duration_millis=_duration_millis(preflight.local_duration_seconds),
        source_sha256=preflight.source_sha256,
        stage_digest=_canonical_sha256(
            {
                "contract_version": "ip-mediakit-video-strategy-stage-v1",
                "source_sha256": preflight.source_sha256,
                "request_sha256": request_sha256,
            }
        ),
        provider_request_sha256=request_sha256,
        maximum_amount_micros=maximum_micros,
        currency="CNY",
        billing_basis=("operator cap for published MediaKit preprocessing estimate only; separately billed Ark model usage amount remains unknown"),
        policy_version=EVIDENCE_VIDEO_STRATEGY_OPERATOR_CAP_POLICY_VERSION,
        price_version="mediakit-video-strategy-public-tariff-reviewed-2026-08-03",
        provider_input_attested=False,
        evidence_coverage="partial",
        warning_code="provider_content_hash_unattested",
        expires_at=now + timedelta(minutes=30),
        price_status="operator_capped",
        now=now,
    )
    approved = await repository.approve(
        requested["id"],
        owner_user_id=RECOVERY_OWNER,
        event_key="operator-approved-strategy-canary",
        expected_request_digest=requested["request_digest"],
        approval_digest=_canonical_sha256(proof_seed),
        expected_event_count=requested["event_count"],
    )
    if approved is None:
        raise CanaryError("RECOVERY_SCOPE_NOT_FOUND")
    reserved = await repository.reserve(
        requested["id"],
        owner_user_id=RECOVERY_OWNER,
        event_key="operator-capped-strategy-reservation",
        expected_request_digest=requested["request_digest"],
        execution_run_id=execution_run_id,
        amount_micros=maximum_micros,
        expected_event_count=approved["event_count"],
    )
    if reserved is None or reserved.get("status") != "reserved":
        raise CanaryError("RECOVERY_SCOPE_NOT_RESERVED")
    jti = "strategy-jti-" + hashlib.sha256(f"{recovery_key}\0{preflight.source_sha256}\0admission".encode()).hexdigest()
    admitted = await repository.admit(
        requested["id"],
        owner_user_id=RECOVERY_OWNER,
        event_key="operator-capped-strategy-admission",
        expected_request_digest=requested["request_digest"],
        execution_run_id=execution_run_id,
        admission_jti=jti,
        admission_proof_digest=_canonical_sha256({**proof_seed, "transition": "admitted"}),
        expected_event_count=reserved["event_count"],
    )
    if admitted is None or admitted.get("status") != "admitted":
        raise CanaryError("RECOVERY_SCOPE_NOT_ADMITTED")
    return admitted


async def _load_recoverable_scope(
    repository: PersonalIPPaidCallRepository,
    *,
    receipt: Mapping[str, Any],
    options: CanaryOptions,
) -> dict[str, Any]:
    rows = await repository.list_recoverable_provider_tasks(
        owner_user_id=RECOVERY_OWNER,
        limit=2,
    )
    if len(rows) != 1:
        raise CanaryError("RECOVERABLE_SCOPE_NOT_UNIQUE")
    scope = rows[0]
    source = receipt.get("source")
    if (
        not isinstance(source, Mapping)
        or scope.get("provider") != "volcengine-mediakit"
        or scope.get("capability") != STRATEGY_CAPABILITY
        or scope.get("source_sha256") != source.get("sha256")
        or scope.get("maximum_amount_micros") != _maximum_amount_micros(options.maximum_cny)
        or scope.get("provider_task_status") not in {"submitting", "submitted", "running", "terminal"}
        or not isinstance(scope.get("submission_envelope"), dict)
        or not isinstance(scope.get("client_token"), str)
    ):
        raise CanaryError("RECOVERY_SCOPE_BINDING_MISMATCH")
    return scope


def _provider_headers(api_key: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _require_identifier(value: Any, *, code: str, billing_outcome: BillingOutcome) -> str:
    if not isinstance(value, str) or not value or value.strip() != value or len(value) > 1024:
        raise CanaryError(code, billing_outcome=billing_outcome)
    if any(character in value for character in "\r\n\x00"):
        raise CanaryError(code, billing_outcome=billing_outcome)
    return value


def _require_mediakit_uri(value: Any) -> str:
    identifier = _require_identifier(value, code="INVALID_UPLOAD_FILE_ID", billing_outcome="not_submitted")
    try:
        parsed = urlsplit(identifier)
    except ValueError:
        raise CanaryError("INVALID_UPLOAD_FILE_ID") from None
    if parsed.scheme.lower() != "mediakit" or not parsed.netloc or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise CanaryError("INVALID_UPLOAD_FILE_ID")
    return identifier


def _is_provider_host(hostname: str) -> bool:
    normalized = hostname.rstrip(".").lower()
    return any(normalized == suffix or normalized.endswith(f".{suffix}") for suffix in _PROVIDER_HOST_SUFFIXES)


def _validate_upload_url(value: Any) -> str:
    # Signed TOS upload URLs are intentionally much longer than ordinary
    # provider identifiers (the live MediaKit response is currently ~6 KiB).
    # Keep the identifier limit for task/request IDs, but validate upload URLs
    # against their own bounded contract.
    if not isinstance(value, str) or not value or value.strip() != value:
        raise CanaryError("INVALID_UPLOAD_URL")
    candidate = value
    if len(candidate) > 8192 or any(character in candidate for character in "\r\n\x00"):
        raise CanaryError("INVALID_UPLOAD_URL")
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        raise CanaryError("INVALID_UPLOAD_URL") from None
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None or port not in {None, 443} or parsed.fragment or not _is_provider_host(parsed.hostname):
        raise CanaryError("INVALID_UPLOAD_URL")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise CanaryError("INVALID_UPLOAD_URL")
    return candidate


def _parse_upload_headers(value: Any, *, api_key: str) -> dict[str, str]:
    if value is None:
        items: Sequence[tuple[Any, Any]] = ()
    elif isinstance(value, list):
        pairs: list[tuple[Any, Any]] = []
        for item in value:
            if not isinstance(item, Mapping):
                raise CanaryError("INVALID_UPLOAD_HEADERS")
            pairs.append(
                (
                    item.get("key", item.get("name", item.get("header"))),
                    item.get("value", item.get("val")),
                )
            )
        items = pairs
    elif isinstance(value, Mapping):
        items = list(value.items())
    else:
        raise CanaryError("INVALID_UPLOAD_HEADERS")
    headers: dict[str, str] = {}
    seen_names: set[str] = set()
    forbidden_names = {
        "authorization",
        "connection",
        "content-length",
        "content-type",
        "cookie",
        "host",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
    for raw_key, raw_value in items:
        key = str(raw_key or "").strip()
        header_value = str(raw_value or "").strip()
        normalized_key = key.lower()
        allowed_signed_name = normalized_key.startswith(("x-tos-", "x-amz-")) or normalized_key == "content-md5"
        if not key or normalized_key in forbidden_names or normalized_key in seen_names or not allowed_signed_name or any(character in key + header_value for character in "\r\n\x00") or api_key in header_value:
            raise CanaryError("INVALID_UPLOAD_HEADERS")
        seen_names.add(normalized_key)
        headers[key] = header_value
    headers["Content-Type"] = "video/mp4"
    return headers


def _request_ids(payload: Mapping[str, Any], response: httpx.Response) -> list[str]:
    candidates: list[Any] = [payload.get("request_id"), payload.get("requestId")]
    candidates.extend(response.headers.get(name) for name in ("x-request-id", "x-tos-request-id"))
    identifiers: list[str] = []
    for candidate in candidates:
        if candidate is None or candidate == "":
            continue
        if not isinstance(candidate, str):
            continue
        try:
            identifier = _require_identifier(
                candidate,
                code="INVALID_PROVIDER_REQUEST_ID",
                billing_outcome="unknown",
            )
        except CanaryError:
            continue
        if identifier not in identifiers:
            identifiers.append(identifier)
    return identifiers


def _untrusted_value_sha256(value: Any) -> str:
    """Hash an untrusted JSON value without ever serializing it into a receipt."""

    try:
        encoded = _canonical_bytes(value)
    except (TypeError, ValueError, UnicodeError):
        encoded = f"{type(value).__name__}:".encode() + repr(value).encode(
            "utf-8",
            errors="surrogatepass",
        )
    return hashlib.sha256(encoded).hexdigest()


def _provider_payload_sensitive_values(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Collect known locator/credential values only for in-memory redaction checks."""

    sensitive_names = {
        "api_key",
        "authorization",
        "client_token",
        "cookie",
        "file_id",
        "request_id",
        "requestid",
        "secret",
        "task_id",
        "token",
        "upload_url",
        "url",
    }
    found: list[str] = []
    pending: list[Any] = [payload]
    visited: set[int] = set()
    inspected = 0
    while pending and inspected < 2048:
        current = pending.pop()
        inspected += 1
        if isinstance(current, Mapping):
            identity = id(current)
            if identity in visited:
                continue
            visited.add(identity)
            for raw_key, raw_value in current.items():
                normalized_key = str(raw_key).strip().lower()
                if normalized_key in sensitive_names and isinstance(raw_value, str) and raw_value:
                    found.append(raw_value)
                if isinstance(raw_value, (Mapping, list, tuple)):
                    pending.append(raw_value)
        elif isinstance(current, (list, tuple)):
            identity = id(current)
            if identity in visited:
                continue
            visited.add(identity)
            pending.extend(current)
    return tuple(found)


def _safe_provider_error_component(
    field: str,
    value: Any,
    *,
    forbidden: Sequence[str],
) -> dict[str, str]:
    digest = _untrusted_value_sha256(value)
    pattern = _SAFE_PROVIDER_ERROR_PARAM_RE if field == "param" else _SAFE_PROVIDER_ERROR_IDENTIFIER_RE
    safe_plaintext = isinstance(value, str) and pattern.fullmatch(value) is not None and _URL_RE.search(value) is None and not any(secret and secret in value for secret in forbidden)
    if safe_plaintext:
        return {"storage": "allowlisted_value", "value": value}
    return {"storage": "sha256_only", "sha256": digest}


def _safe_provider_error_projection(
    payload: Mapping[str, Any],
    *,
    forbidden: Sequence[str],
) -> dict[str, Any] | None:
    """Keep a useful private debug projection without copying credentials or URLs."""

    raw_error = payload.get("error")
    if not isinstance(raw_error, Mapping):
        return None
    effective_forbidden = (*forbidden, *_provider_payload_sensitive_values(payload))
    fields = {
        field: _safe_provider_error_component(
            field,
            raw_error[field],
            forbidden=effective_forbidden,
        )
        for field in _PROVIDER_ERROR_FIELDS
        if field in raw_error
    }
    projection: dict[str, Any] = {"fields": fields}
    raw_message = raw_error.get("message")
    if isinstance(raw_message, str) and raw_message:
        message = raw_message
        for secret in effective_forbidden:
            if secret:
                message = message.replace(secret, "[redacted]")
        message = _URL_RE.sub("[redacted-url]", message)
        projection["message"] = message[:4096]
        projection["message_truncated"] = len(message) > 4096
    return projection if fields or "message" in projection else None


def _cli_failure_payload(error: CanaryError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "failed_safe",
        "safe_error_code": error.code,
        "billing_outcome": error.billing_outcome,
        "automatic_submit_retries": 0,
    }
    provider_error = (error.failure or {}).get("provider_error")
    if isinstance(provider_error, Mapping) and isinstance(provider_error.get("message"), str):
        payload["provider_error_message"] = provider_error["message"]
    return payload


def _provider_rejection_error(
    code: str,
    *,
    payload: Mapping[str, Any],
    stage: str,
    billing_outcome: BillingOutcome,
    forbidden: Sequence[str],
) -> CanaryError:
    if stage not in _FAILURE_STAGES:
        return CanaryError("INTERNAL_ERROR", billing_outcome="unknown")
    classification = "terminal_provider_rejection"
    receipt_status = "provider_rejected"
    effective_billing_outcome = billing_outcome
    if stage == "submit":
        classification = "terminal_provider_submission_rejection"
        effective_billing_outcome = "provider_rejected"
        receipt_status = "provider_submission_rejected"
    elif stage == "poll":
        classification = "terminal_provider_task_rejection"
        receipt_status = "provider_task_rejected"
    return CanaryError(
        code,
        billing_outcome=effective_billing_outcome,
        receipt_status=receipt_status,
        failure_classification=classification,
        failure_stage=stage,
        provider_error=_safe_provider_error_projection(payload, forbidden=forbidden),
    )


async def _bounded_response_bytes(response: httpx.Response, *, billing_outcome: BillingOutcome) -> bytes:
    declared_length = response.headers.get("content-length")
    if declared_length:
        try:
            declared = int(declared_length)
        except ValueError:
            raise CanaryError("INVALID_RESPONSE_LENGTH", billing_outcome=billing_outcome) from None
        if declared < 0 or declared > _MAX_RESPONSE_BYTES:
            raise CanaryError("RESPONSE_TOO_LARGE", billing_outcome=billing_outcome)
    chunks: list[bytes] = []
    observed = 0
    async for chunk in response.aiter_bytes(64 * 1024):
        observed += len(chunk)
        if observed > _MAX_RESPONSE_BYTES:
            raise CanaryError("RESPONSE_TOO_LARGE", billing_outcome=billing_outcome)
        chunks.append(chunk)
    return b"".join(chunks)


async def _request_bytes(
    client: httpx.AsyncClient,
    *,
    method: str,
    url: str,
    stage: str,
    billing_outcome: BillingOutcome,
    deadline: float,
    headers: Mapping[str, str] | None = None,
    json_body: Mapping[str, Any] | None = None,
    content: httpx.AsyncByteStream | None = None,
    forbidden: Sequence[str] = (),
) -> tuple[httpx.Response, bytes]:
    failure_stage = _REQUEST_STAGE_NAMES.get(stage)
    if failure_stage is None:
        raise CanaryError("INTERNAL_ERROR", billing_outcome="unknown")
    remaining = deadline - _monotonic()
    if remaining <= 0:
        raise CanaryError(
            "TOTAL_TIMEOUT",
            billing_outcome=billing_outcome,
            receipt_status="poll_timeout",
        )
    timeout = min(_REQUEST_TIMEOUT_SECONDS, remaining)
    try:
        async with client.stream(
            method,
            url,
            headers=headers,
            json=json_body,
            content=content,
            timeout=timeout,
        ) as response:
            encoded = await _bounded_response_bytes(response, billing_outcome=billing_outcome)
    except CanaryError:
        raise
    except httpx.TimeoutException:
        status = "submit_outcome_unknown" if stage == "SUBMIT" else "poll_timeout" if stage == "POLL" else "failed_safe"
        raise CanaryError(
            f"{stage}_TIMEOUT",
            billing_outcome=billing_outcome,
            receipt_status=status,
            failure_classification="transport_unknown",
            failure_stage=failure_stage,
        ) from None
    except httpx.HTTPError:
        status = "submit_outcome_unknown" if stage == "SUBMIT" else "transport_unknown"
        raise CanaryError(
            f"{stage}_TRANSPORT_UNKNOWN",
            billing_outcome=billing_outcome,
            receipt_status=status,
            failure_classification="transport_unknown",
            failure_stage=failure_stage,
        ) from None
    if not 200 <= response.status_code < 300:
        decoded: Any = None
        try:
            decoded = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        if isinstance(decoded, Mapping) and (decoded.get("success") is False or decoded.get("error") is not None):
            raise _provider_rejection_error(
                f"{stage}_HTTP_ERROR",
                payload=decoded,
                stage=failure_stage,
                billing_outcome=billing_outcome,
                forbidden=forbidden,
            )
        rejected_outcome = billing_outcome
        if stage == "SUBMIT" and response.status_code < 500:
            rejected_outcome = "provider_rejected"
        if response.status_code < 500:
            classification = "terminal_provider_submission_rejection" if failure_stage == "submit" else "terminal_provider_task_rejection" if failure_stage == "poll" else "terminal_provider_rejection"
            receipt_status = "provider_submission_rejected" if failure_stage == "submit" else "provider_task_rejected" if failure_stage == "poll" else "provider_rejected"
        else:
            classification = "transport_unknown"
            receipt_status = "transport_unknown"
        raise CanaryError(
            f"{stage}_HTTP_ERROR",
            billing_outcome=rejected_outcome,
            receipt_status=receipt_status,
            failure_classification=classification,
            failure_stage=failure_stage,
        )
    return response, encoded


def _decode_payload(encoded: bytes, *, code: str, billing_outcome: BillingOutcome) -> Mapping[str, Any]:
    try:
        payload = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CanaryError(code, billing_outcome=billing_outcome) from None
    if not isinstance(payload, Mapping):
        raise CanaryError(code, billing_outcome=billing_outcome)
    return payload


def _require_success(
    payload: Mapping[str, Any],
    *,
    code: str,
    billing_outcome: BillingOutcome,
    stage: str,
    forbidden: Sequence[str],
) -> None:
    if payload.get("success") is not True or payload.get("error") is not None:
        raise _provider_rejection_error(
            code,
            payload=payload,
            stage=stage,
            billing_outcome=billing_outcome,
            forbidden=forbidden,
        )


def _submit_body(*, file_id: str, client_token: str) -> dict[str, Any]:
    return {
        "video_urls": [file_id],
        "prompt": FIXED_PROMPT,
        "level": LEVEL,
        "scene": SCENE,
        "manual_option": {"need_audio": True},
        "client_token": client_token,
    }


def _strict_task_status(value: Any) -> str:
    if not isinstance(value, str) or value.strip() != value or value.lower() != value:
        raise CanaryError("UNKNOWN_TASK_STATUS", billing_outcome="unknown", receipt_status="unknown")
    allowed = _PENDING_STATUSES | _TERMINAL_FAILURE_STATUSES | _TERMINAL_CANCELLED_STATUSES | {"completed"}
    if value not in allowed:
        raise CanaryError("UNKNOWN_TASK_STATUS", billing_outcome="unknown", receipt_status="unknown")
    return value


def _normalize_duration(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise CanaryError("INVALID_PROVIDER_DURATION", billing_outcome="unknown")
    try:
        duration = Decimal(str(value))
    except InvalidOperation:
        raise CanaryError("INVALID_PROVIDER_DURATION", billing_outcome="unknown") from None
    if not duration.is_finite() or duration <= 0 or duration > Decimal(72000):
        raise CanaryError("INVALID_PROVIDER_DURATION", billing_outcome="unknown")
    return duration


def _normalize_token_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise CanaryError("INVALID_TOKEN_USAGE", billing_outcome="unknown")
    normalized: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        item = value.get(key)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0 or item > 1_000_000_000:
            raise CanaryError("INVALID_TOKEN_USAGE", billing_outcome="unknown")
        normalized[key] = item
    if normalized["total_tokens"] != normalized["input_tokens"] + normalized["output_tokens"]:
        raise CanaryError("INVALID_TOKEN_USAGE", billing_outcome="unknown")
    return normalized


def _truncate_utf8(value: str, maximum_bytes: int) -> tuple[str, int, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return value, len(encoded), False
    truncated = encoded[:maximum_bytes]
    while truncated:
        try:
            return truncated.decode("utf-8"), len(truncated), True
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return "", 0, True


def _normalize_contents(value: Any, *, forbidden: Sequence[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != 1:
        raise CanaryError("INVALID_CONTENTS", billing_outcome="unknown")
    normalized: list[dict[str, Any]] = []
    remaining = _MAX_CONTENT_TOTAL_BYTES
    for item in value:
        if not isinstance(item, str):
            raise CanaryError("INVALID_CONTENTS", billing_outcome="unknown")
        original_bytes = item.encode("utf-8")
        redacted = item
        for secret in forbidden:
            if secret:
                redacted = redacted.replace(secret, "[redacted-provider-identifier]")
        redacted = _URL_RE.sub("[redacted-url]", redacted)
        maximum = min(_MAX_CONTENT_TEXT_BYTES, remaining)
        stored, stored_bytes, truncated = _truncate_utf8(redacted, maximum)
        remaining -= stored_bytes
        normalized.append(
            {
                "text": stored,
                "original_sha256": hashlib.sha256(original_bytes).hexdigest(),
                "original_utf8_bytes": len(original_bytes),
                "stored_utf8_bytes": stored_bytes,
                "truncated": truncated or stored != redacted,
            }
        )
    return normalized


def _record_response(
    receipt: dict[str, Any],
    *,
    stage: str,
    encoded: bytes,
    payload: Mapping[str, Any],
    response: httpx.Response,
    raw_identifiers: list[str],
) -> None:
    receipt["provider_response_sha256_by_stage"][stage].append(hashlib.sha256(encoded).hexdigest())
    request_ids = _request_ids(payload, response)
    raw_identifiers.extend(request_ids)
    receipt["provider_identifier_sha256"]["request_ids_by_stage"][stage].extend(_sha256_text(identifier) for identifier in request_ids)


async def _persist_submitted_task(
    repository: PersonalIPPaidCallRepository,
    *,
    scope: Mapping[str, Any],
    task_id: str,
    client_token: str,
    request_sha256: str,
    response_encoded: bytes,
    request_ids: Sequence[str],
) -> dict[str, Any]:
    persisted = await repository.record_provider_task_submission_confirmed(
        str(scope["id"]),
        owner_user_id=RECOVERY_OWNER,
        event_key="strategy-provider-submitted",
        expected_request_digest=str(scope["request_digest"]),
        execution_run_id=str(scope["execution_run_id"]),
        submitted_task_record=_strategy_submitted_task_record(
            task_id=task_id,
            client_token=client_token,
            request_sha256=request_sha256,
            response_encoded=response_encoded,
            request_ids=tuple(request_ids)[:2],
        ),
    )
    if persisted is None:
        raise CanaryError("RECOVERY_SCOPE_NOT_FOUND", billing_outcome="unknown")
    return persisted


async def _record_terminal_and_reconciliation(
    repository: PersonalIPPaidCallRepository,
    *,
    scope: Mapping[str, Any],
    task_id: str,
    status: str,
    payload: Mapping[str, Any],
) -> None:
    terminal_digest = _canonical_sha256(payload)
    persisted = await repository.record_provider_task_terminal(
        str(scope["id"]),
        owner_user_id=RECOVERY_OWNER,
        event_key=f"strategy-provider-terminal:{status}:{terminal_digest[:32]}",
        expected_request_digest=str(scope["request_digest"]),
        execution_run_id=str(scope["execution_run_id"]),
        raw_task_id=task_id,
        terminal_status=status,
        terminal_envelope=dict(payload),
    )
    if persisted is None:
        raise CanaryError("RECOVERY_SCOPE_NOT_FOUND", billing_outcome="unknown")
    reconciled = await repository.settle(
        str(scope["id"]),
        owner_user_id=RECOVERY_OWNER,
        event_key="strategy-provider-actual-amount-unknown",
        expected_request_digest=str(scope["request_digest"]),
        execution_run_id=str(scope["execution_run_id"]),
        actual_amount_micros=None,
        provider_receipt_digest=terminal_digest,
    )
    if reconciled is None:
        raise CanaryError("RECOVERY_SCOPE_NOT_FOUND", billing_outcome="unknown")


async def execute_canary(
    options: CanaryOptions,
    *,
    client: httpx.AsyncClient | None = None,
    duration_probe: Callable[[Path], Decimal] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Execute or explicitly resume one recoverable paid Strategy task."""

    if not options.authorize_paid_call:
        raise CanaryError("PAID_CALL_NOT_AUTHORIZED")
    if options.resume and options.output_dir is None:
        raise CanaryError("RESUME_REQUIRES_OUTPUT_DIR")

    owns_client = client is None
    source_descriptor: int | None = None
    engine_initialized = False
    database_dir: Path | None = None
    receipt: dict[str, Any] | None = None
    receipt_path: Path | None = None
    raw_identifiers: list[str] = []
    repository: PersonalIPPaidCallRepository | None = None
    scope: dict[str, Any] | None = None
    preflight: Preflight | None = None
    task_id: str | None = None
    completed_payload: Mapping[str, Any] | None = None
    try:
        if options.resume:
            assert options.output_dir is not None
            output_dir = _validate_output_dir(options.output_dir, resume=True)
            receipt_path = output_dir / "receipt.json"
            receipt = _read_receipt(receipt_path, options=options)
            recovery_key = _read_owner_private_text(
                output_dir / RECOVERY_KEY_NAME,
                code="RECOVERY_KEY_INVALID",
            )
            database_dir = output_dir / RECOVERY_DATABASE_DIR_NAME
            _ensure_private_database_dir(database_dir, resume=True)
            api_key, _ = _load_api_key(options)
            raw_identifiers.append(api_key)
        else:
            source, _ = _regular_source(options.video_path)
            probe = duration_probe or _probe_duration_seconds
            duration = await asyncio.to_thread(probe, source)
            if not isinstance(duration, Decimal):
                try:
                    duration = Decimal(str(duration))
                except InvalidOperation:
                    raise CanaryError("INVALID_VIDEO_DURATION") from None
            preflight = _prepare_preflight(options, duration_seconds=duration)
            api_key, key_source = _load_api_key(options)
            raw_identifiers.extend([api_key, preflight.client_token])
            _ensure_private_output_dir(preflight.output_dir)
            receipt_path = preflight.output_dir / "receipt.json"
            receipt = _base_receipt(preflight, key_source=key_source)
            recovery_key = _new_recovery_key(preflight.output_dir / RECOVERY_KEY_NAME)
            database_dir = preflight.output_dir / RECOVERY_DATABASE_DIR_NAME
            _ensure_private_database_dir(database_dir, resume=False)
            _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)

        await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(database_dir)))
        engine_initialized = True
        _secure_database_files(database_dir)
        if await _schema_head() != "0029_personal_ip_final_artifacts":
            raise CanaryError("RECOVERY_DATABASE_REVISION_MISMATCH")
        session_factory = get_session_factory()
        if session_factory is None:
            raise CanaryError("RECOVERY_DATABASE_UNAVAILABLE")
        repository = PersonalIPPaidCallRepository(
            session_factory,
            provider_task_cipher=ChannelCredentialCipher.from_key(recovery_key),
        )
        if client is None:
            client = httpx.AsyncClient(follow_redirects=False, trust_env=False)
        deadline = _monotonic() + _TOTAL_TIMEOUT_SECONDS

        if options.resume:
            assert receipt is not None
            scope = await _load_recoverable_scope(
                repository,
                receipt=receipt,
                options=options,
            )
            client_token = str(scope["client_token"])
            submission_envelope = scope["submission_envelope"]
            submit_body = submission_envelope["submit_body"]
            video_ref = submit_body["video_urls"][0]
            raw_identifiers.extend([client_token, video_ref])
            receipt["safe_error_code"] = None
            receipt["failure"] = None
            receipt["recovery"]["encrypted_exact_submission_persisted"] = True
            receipt["recovery"]["can_count_as_recoverable_execution"] = True
            receipt["recovery"]["resume_explicit"] = True
            provider_task_status = scope["provider_task_status"]
            if provider_task_status == "submitting":
                replay = await repository.claim_provider_task_submission_replay(
                    str(scope["id"]),
                    owner_user_id=RECOVERY_OWNER,
                    expected_request_digest=str(scope["request_digest"]),
                    execution_run_id=str(scope["execution_run_id"]),
                    expected_submission_sha256=str(scope["provider_submission_sha256"]),
                )
                if replay is None or not replay.get("provider_submission_replay_claimed"):
                    raise CanaryError(
                        "EXACT_SUBMIT_REPLAY_NOT_GRANTED",
                        billing_outcome="unknown",
                        receipt_status="reconciliation_required",
                    )
                receipt["recovery"]["exact_submit_replay_claimed"] = True
                receipt["request_projection"]["submit_retries"] = 1
                receipt["execution"]["submit_attempts"] = int(receipt["execution"].get("submit_attempts", 0)) + 1
                receipt["status"] = "submitting"
                receipt["billing_outcome"] = "unknown"
                _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)
                submit_response, submit_encoded = await _request_bytes(
                    client,
                    method="POST",
                    url=f"{ENDPOINT}{SUBMIT_PATH}",
                    stage="SUBMIT",
                    billing_outcome="unknown",
                    deadline=deadline,
                    headers=_provider_headers(api_key),
                    json_body=submit_body,
                    forbidden=raw_identifiers,
                )
                submit_payload = _decode_payload(
                    submit_encoded,
                    code="INVALID_SUBMIT_JSON",
                    billing_outcome="unknown",
                )
                submit_request_ids = _request_ids(submit_payload, submit_response)
                _record_response(
                    receipt,
                    stage="submit",
                    encoded=submit_encoded,
                    payload=submit_payload,
                    response=submit_response,
                    raw_identifiers=raw_identifiers,
                )
                _require_success(
                    submit_payload,
                    code="SUBMIT_REJECTED",
                    billing_outcome="unknown",
                    stage="submit",
                    forbidden=raw_identifiers,
                )
                task_id = _require_identifier(
                    submit_payload.get("task_id"),
                    code="MISSING_TASK_ID",
                    billing_outcome="unknown",
                )
                raw_identifiers.append(task_id)
                await _persist_submitted_task(
                    repository,
                    scope=scope,
                    task_id=task_id,
                    client_token=client_token,
                    request_sha256=str(submission_envelope["request_sha256"]),
                    response_encoded=submit_encoded,
                    request_ids=submit_request_ids,
                )
                receipt["provider_identifier_sha256"]["task_id"] = _sha256_text(task_id)
                receipt["recovery"]["raw_task_authority_persisted"] = True
                receipt["status"] = "submitted"
                _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)
            elif provider_task_status in {"submitted", "running"}:
                task_id = str(scope["raw_task_id"])
                raw_identifiers.append(task_id)
                receipt["provider_identifier_sha256"]["task_id"] = _sha256_text(task_id)
                receipt["recovery"]["raw_task_authority_persisted"] = True
                receipt["recovery"]["resumed_with_query_only"] = True
                _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)
            elif provider_task_status == "terminal":
                task_id = str(scope["raw_task_id"])
                raw_identifiers.append(task_id)
                terminal = scope.get("terminal_envelope")
                if not isinstance(terminal, Mapping):
                    raise CanaryError(
                        "RECOVERY_TERMINAL_ENVELOPE_MISSING",
                        billing_outcome="unknown",
                    )
                completed_payload = terminal
                receipt["provider_identifier_sha256"]["task_id"] = _sha256_text(task_id)
                receipt["recovery"]["raw_task_authority_persisted"] = True
                receipt["recovery"]["resumed_from_encrypted_terminal"] = True
        else:
            assert preflight is not None and receipt is not None
            source_descriptor = await asyncio.to_thread(_open_bound_source, preflight)
            receipt["source"]["hash_checks"] = 2
            _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)
            receipt["execution"]["upload_target_attempts"] = 1
            upload_response, upload_encoded = await _request_bytes(
                client,
                method="POST",
                url=f"{ENDPOINT}{UPLOAD_TARGET_PATH}",
                stage="UPLOAD_TARGET",
                billing_outcome="not_submitted",
                deadline=deadline,
                headers=_provider_headers(api_key),
                json_body={"tool_name": STRATEGY_PROVIDER_TOOL_NAME},
                forbidden=raw_identifiers,
            )
            upload_payload = _decode_payload(
                upload_encoded,
                code="INVALID_UPLOAD_TARGET_JSON",
                billing_outcome="not_submitted",
            )
            _record_response(
                receipt,
                stage="upload_target",
                encoded=upload_encoded,
                payload=upload_payload,
                response=upload_response,
                raw_identifiers=raw_identifiers,
            )
            _require_success(
                upload_payload,
                code="UPLOAD_TARGET_REJECTED",
                billing_outcome="not_submitted",
                stage="upload_target",
                forbidden=raw_identifiers,
            )
            upload_result = upload_payload.get("result")
            if not isinstance(upload_result, Mapping):
                raise CanaryError("INVALID_UPLOAD_TARGET")
            file_id = _require_mediakit_uri(upload_result.get("file_id"))
            upload_url = _validate_upload_url(upload_result.get("upload_url"))
            raw_identifiers.extend([file_id, upload_url])
            if upload_result.get("method") != "PUT":
                raise CanaryError("UNSUPPORTED_UPLOAD_METHOD")
            upload_headers = _parse_upload_headers(upload_result.get("upload_headers"), api_key=api_key)
            upload_headers["Content-Length"] = str(preflight.source_size_bytes)
            raw_identifiers.extend(value for key, value in upload_headers.items() if key.lower() not in {"content-type", "content-length"} and len(value) >= 8)
            receipt["provider_identifier_sha256"]["file_id"] = _sha256_text(file_id)
            receipt["provider_identifier_sha256"]["upload_url"] = _sha256_text(upload_url)
            receipt["request_projection"]["video_urls_sha256"] = [_sha256_text(file_id)]
            receipt["status"] = "upload_target_received"
            _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)

            receipt["execution"]["media_upload_attempts"] = 1
            upload_stream = _PathByteStream(source_descriptor)
            put_response, put_encoded = await _request_bytes(
                client,
                method="PUT",
                url=upload_url,
                stage="MEDIA_UPLOAD",
                billing_outcome="not_submitted",
                deadline=deadline,
                headers=upload_headers,
                content=upload_stream,
                forbidden=raw_identifiers,
            )
            upload_stream.require_expected(
                expected_sha256=preflight.source_sha256,
                expected_size_bytes=preflight.source_size_bytes,
            )
            put_payload: Mapping[str, Any] = {}
            if put_encoded.strip():
                try:
                    decoded_put = json.loads(put_encoded)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    decoded_put = {}
                if isinstance(decoded_put, Mapping):
                    put_payload = decoded_put
            _record_response(
                receipt,
                stage="media_upload",
                encoded=put_encoded,
                payload=put_payload,
                response=put_response,
                raw_identifiers=raw_identifiers,
            )
            if await asyncio.to_thread(_sha256_descriptor, source_descriptor) != preflight.source_sha256:
                raise CanaryError("SOURCE_CHANGED_AFTER_UPLOAD")
            receipt["source"]["hash_checks"] = 3
            receipt["status"] = "uploaded"

            client_token = preflight.client_token
            submit_body = _submit_body(
                file_id=file_id,
                client_token=client_token,
            )
            submission_envelope = _strategy_submission_envelope(
                preflight=preflight,
                submit_body=submit_body,
            )
            scope = await _create_admitted_scope(
                repository,
                preflight=preflight,
                submission_envelope=submission_envelope,
                recovery_key=recovery_key,
            )
            submitting = await repository.begin_provider_task_submission(
                str(scope["id"]),
                owner_user_id=RECOVERY_OWNER,
                event_key="strategy-provider-submitting",
                expected_request_digest=str(scope["request_digest"]),
                execution_run_id=str(scope["execution_run_id"]),
                capability=STRATEGY_CAPABILITY,
                source_sha256=preflight.source_sha256,
                client_token=client_token,
                submission_envelope=submission_envelope,
            )
            if submitting is None:
                raise CanaryError("RECOVERY_SCOPE_NOT_FOUND")
            receipt["request_projection"]["provider_request_sha256"] = submission_envelope["request_sha256"]
            receipt["execution"]["submit_attempts"] = 1
            receipt["status"] = "submitting"
            receipt["billing_outcome"] = "unknown"
            receipt["recovery"]["encrypted_exact_submission_persisted"] = True
            receipt["recovery"]["can_count_as_recoverable_execution"] = True
            _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)

            submit_response, submit_encoded = await _request_bytes(
                client,
                method="POST",
                url=f"{ENDPOINT}{SUBMIT_PATH}",
                stage="SUBMIT",
                billing_outcome="unknown",
                deadline=deadline,
                headers=_provider_headers(api_key),
                json_body=submit_body,
                forbidden=raw_identifiers,
            )
            submit_payload = _decode_payload(
                submit_encoded,
                code="INVALID_SUBMIT_JSON",
                billing_outcome="unknown",
            )
            submit_request_ids = _request_ids(submit_payload, submit_response)
            _record_response(
                receipt,
                stage="submit",
                encoded=submit_encoded,
                payload=submit_payload,
                response=submit_response,
                raw_identifiers=raw_identifiers,
            )
            _require_success(
                submit_payload,
                code="SUBMIT_REJECTED",
                billing_outcome="unknown",
                stage="submit",
                forbidden=raw_identifiers,
            )
            task_id = _require_identifier(
                submit_payload.get("task_id"),
                code="MISSING_TASK_ID",
                billing_outcome="unknown",
            )
            raw_identifiers.append(task_id)
            await _persist_submitted_task(
                repository,
                scope=scope,
                task_id=task_id,
                client_token=client_token,
                request_sha256=str(submission_envelope["request_sha256"]),
                response_encoded=submit_encoded,
                request_ids=submit_request_ids,
            )
            receipt["provider_identifier_sha256"]["task_id"] = _sha256_text(task_id)
            receipt["recovery"]["raw_task_authority_persisted"] = True
            receipt["status"] = "submitted"
            _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)

        assert receipt is not None and receipt_path is not None and scope is not None
        if completed_payload is not None:
            recovered_status = _strict_task_status(completed_payload.get("status"))
            if recovered_status != "completed":
                if recovered_status in _TERMINAL_CANCELLED_STATUSES:
                    raise CanaryError(
                        "PROVIDER_TASK_CANCELLED",
                        billing_outcome="unknown",
                        receipt_status="cancelled",
                    )
                raise CanaryError(
                    "PROVIDER_TASK_FAILED",
                    billing_outcome="unknown",
                    receipt_status="provider_task_rejected",
                    failure_classification="terminal_provider_task_rejection",
                    failure_stage="poll",
                )
        else:
            assert task_id is not None
            for poll_attempt in range(1, _MAX_POLL_ATTEMPTS + 1):
                remaining = deadline - _monotonic()
                if remaining <= 0:
                    raise CanaryError(
                        "TOTAL_TIMEOUT",
                        billing_outcome="unknown",
                        receipt_status="poll_timeout",
                    )
                await asyncio.sleep(min(_POLL_INTERVAL_SECONDS, remaining))
                poll_response, poll_encoded = await _request_bytes(
                    client,
                    method="GET",
                    url=f"{ENDPOINT}{TASK_PATH_PREFIX}{quote(task_id, safe='')}",
                    stage="POLL",
                    billing_outcome="unknown",
                    deadline=deadline,
                    headers=_provider_headers(api_key),
                    forbidden=raw_identifiers,
                )
                poll_payload = _decode_payload(
                    poll_encoded,
                    code="INVALID_POLL_JSON",
                    billing_outcome="unknown",
                )
                _record_response(
                    receipt,
                    stage="poll",
                    encoded=poll_encoded,
                    payload=poll_payload,
                    response=poll_response,
                    raw_identifiers=raw_identifiers,
                )
                receipt["execution"]["poll_attempts"] = poll_attempt
                if poll_payload.get("success") is not True:
                    _require_success(
                        poll_payload,
                        code="POLL_REJECTED",
                        billing_outcome="unknown",
                        stage="poll",
                        forbidden=raw_identifiers,
                    )
                observed_task_id = _require_identifier(
                    poll_payload.get("task_id"),
                    code="MISSING_POLL_TASK_ID",
                    billing_outcome="unknown",
                )
                raw_identifiers.append(observed_task_id)
                if observed_task_id != task_id:
                    raise CanaryError(
                        "TASK_ID_MISMATCH",
                        billing_outcome="unknown",
                        receipt_status="unknown",
                    )
                status = _strict_task_status(poll_payload.get("status"))
                if status in _TERMINAL_CANCELLED_STATUSES:
                    await _record_terminal_and_reconciliation(
                        repository,
                        scope=scope,
                        task_id=task_id,
                        status=status,
                        payload=poll_payload,
                    )
                    raise CanaryError(
                        "PROVIDER_TASK_CANCELLED",
                        billing_outcome="unknown",
                        receipt_status="cancelled",
                    )
                if status in _TERMINAL_FAILURE_STATUSES:
                    await _record_terminal_and_reconciliation(
                        repository,
                        scope=scope,
                        task_id=task_id,
                        status=status,
                        payload=poll_payload,
                    )
                    raise _provider_rejection_error(
                        "PROVIDER_TASK_FAILED",
                        payload=poll_payload,
                        stage="poll",
                        billing_outcome="unknown",
                        forbidden=raw_identifiers,
                    )
                _require_success(
                    poll_payload,
                    code="POLL_REJECTED",
                    billing_outcome="unknown",
                    stage="poll",
                    forbidden=raw_identifiers,
                )
                if status == "completed":
                    completed_payload = poll_payload
                    break
                running = await repository.record_provider_task_running(
                    str(scope["id"]),
                    owner_user_id=RECOVERY_OWNER,
                    event_key=(f"strategy-provider-running:{hashlib.sha256(poll_encoded).hexdigest()[:32]}"),
                    expected_request_digest=str(scope["request_digest"]),
                    execution_run_id=str(scope["execution_run_id"]),
                    raw_task_id=task_id,
                    observed_provider_status=status,
                )
                if running is None:
                    raise CanaryError("RECOVERY_SCOPE_NOT_FOUND", billing_outcome="unknown")
                receipt["status"] = status
                _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)
            if completed_payload is None:
                raise CanaryError(
                    "POLL_LIMIT_REACHED",
                    billing_outcome="unknown",
                    receipt_status="poll_timeout",
                )

        assert task_id is not None
        await _record_terminal_and_reconciliation(
            repository,
            scope=scope,
            task_id=task_id,
            status="completed",
            payload=completed_payload,
        )
        result = completed_payload.get("result")
        if not isinstance(result, Mapping):
            raise CanaryError("MISSING_COMPLETED_RESULT", billing_outcome="unknown")
        provider_duration = _normalize_duration(result.get("duration"))
        token_usage = _normalize_token_usage(result.get("token_usage"))
        normalized_contents = _normalize_contents(result.get("contents"), forbidden=raw_identifiers)
        receipt["provider_reported_duration_seconds"] = _decimal_text(provider_duration)
        receipt["token_usage"] = token_usage
        receipt["contents"] = normalized_contents
        receipt["pricing"]["mediakit"]["provider_reported_duration_seconds"] = _decimal_text(provider_duration)
        postflight_estimate = _published_mediakit_estimate(provider_duration)
        receipt["pricing"]["mediakit"]["postflight_public_estimate_cny"] = _decimal_text(postflight_estimate)
        receipt["pricing"]["ark_tokens"]["returned_aggregate_usage"] = token_usage
        postflight_cap_exceeded = postflight_estimate > options.maximum_cny
        receipt["authorization"]["postflight_mediakit_estimate_exceeds_cap"] = postflight_cap_exceeded
        receipt["status"] = "completed_reconciliation_required" if postflight_cap_exceeded else "completed"
        receipt["billing_outcome"] = "usage_returned"
        receipt["completed_at"] = _utcnow().isoformat()
        _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)
        return receipt, receipt_path
    except asyncio.CancelledError:
        if receipt is not None and receipt_path is not None:
            receipt["status"] = "local_cancelled"
            receipt["billing_outcome"] = "unknown" if receipt["execution"].get("submit_attempts") else "not_submitted"
            receipt["safe_error_code"] = "LOCAL_CANCELLED"
            _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)
        raise
    except CanaryError as exc:
        if receipt is not None and receipt_path is not None:
            receipt["status"] = exc.receipt_status
            receipt["billing_outcome"] = exc.billing_outcome
            receipt["safe_error_code"] = exc.code
            receipt["failure"] = exc.failure
            _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)
        raise
    except Exception:  # noqa: BLE001 - fail closed on any unexpected provider value
        billing_outcome: BillingOutcome = "unknown" if receipt is not None and receipt.get("execution", {}).get("submit_attempts") else "not_submitted"
        if receipt is not None and receipt_path is not None:
            receipt["status"] = "failed_safe"
            receipt["billing_outcome"] = billing_outcome
            receipt["safe_error_code"] = "INTERNAL_ERROR"
            try:
                _write_receipt(receipt_path, receipt, forbidden=raw_identifiers)
            except CanaryError:
                pass
        raise CanaryError(
            "INTERNAL_ERROR",
            billing_outcome=billing_outcome,
            receipt_status="failed_safe",
        ) from None
    finally:
        if owns_client and client is not None:
            await client.aclose()
        if source_descriptor is not None:
            os.close(source_descriptor)
        if engine_initialized:
            await close_engine()
        if database_dir is not None and database_dir.exists():
            _secure_database_files(database_dir)


def _parse_args(argv: Sequence[str] | None) -> CanaryOptions:
    parser = _SafeArgumentParser(description=__doc__)
    parser.add_argument("video_path", type=Path)
    parser.add_argument("--authorize-paid-call", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--maximum-cny",
        required=True,
        help=("Local admission cap for the published MediaKit input-minute estimate only; not provider-enforced and does not cap separately billed Ark tokens."),
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    parser.add_argument("--mediakit-key-file", type=Path)
    namespace = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", namespace.api_key_env):
        raise CanaryError("INVALID_API_KEY_ENV_NAME")
    maximum_cny = _parse_positive_decimal(namespace.maximum_cny, code="INVALID_MAXIMUM_CNY")
    if namespace.resume and namespace.output_dir is None:
        raise CanaryError("RESUME_REQUIRES_OUTPUT_DIR")
    return CanaryOptions(
        video_path=namespace.video_path,
        authorize_paid_call=bool(namespace.authorize_paid_call),
        maximum_cny=maximum_cny,
        output_dir=namespace.output_dir,
        api_key_env=namespace.api_key_env,
        mediakit_key_file=namespace.mediakit_key_file,
        resume=bool(namespace.resume),
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        options = _parse_args(argv)
        receipt, receipt_path = asyncio.run(execute_canary(options))
    except CanaryError as exc:
        print(
            json.dumps(_cli_failure_payload(exc), sort_keys=True),
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        print(
            json.dumps(
                {
                    "status": "local_cancelled",
                    "billing_outcome": "unknown",
                    "automatic_submit_retries": 0,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 130
    except Exception:  # noqa: BLE001 - CLI must never expose an unexpected traceback
        print(
            json.dumps(
                {
                    "status": "failed_safe",
                    "safe_error_code": "INTERNAL_ERROR",
                    "billing_outcome": "unknown",
                    "automatic_submit_retries": 0,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "receipt": str(receipt_path),
                "automatic_submit_retries": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
