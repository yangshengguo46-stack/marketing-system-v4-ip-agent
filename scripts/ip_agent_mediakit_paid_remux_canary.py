"""Run one isolated, operator-capped MediaKit Remux paid-path canary.

The command is a dry-run unless ``--execute-paid`` is supplied.  Its SQLite
database, encrypted recovery material and public receipts live in one private
acceptance directory; neither the normal nor IP-test DeerFlow database is
opened.  The current Remux operator must explicitly advertise support for the
operator-capped policy before this script will create any state or read a
credential.  This prevents a published unit price from being misrepresented
as a provider quote.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import stat
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "backend" / "packages" / "harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from deerflow.config.database_config import DatabaseConfig  # noqa: E402
from deerflow.ip_agent import mediakit_remux_paid_operator as paid_operator  # noqa: E402
from deerflow.persistence.channel_connections.sql import (  # noqa: E402
    ChannelCredentialCipher,
)
from deerflow.persistence.engine import (  # noqa: E402
    close_engine,
    get_session_factory,
    init_engine_from_config,
)
from deerflow.persistence.personal_ip_paid_calls import (  # noqa: E402
    PersonalIPPaidCallRepository,
)

CONTRACT_VERSION = "ip-agent-mediakit-paid-remux-canary-v1"
MANIFEST_VERSION = "ip-agent-mediakit-paid-remux-canary-state-v1"
OPERATOR_CAPPED_POLICY_VERSION = "evidence-managed-remux-operator-cap-v1"

Q157_SOURCE = ROOT / ".deer-flow" / "acceptance" / "mediakit-remux-ingress-2026-08-03" / "q157-work-7658501922794432731.mp4"
Q157_SOURCE_SHA256 = "8e098c16f3634f27bbd8ca6bd30e41ed5c9816d6ff4654922d115198a4ec10fc"
Q157_SOURCE_SIZE_BYTES = 13_436_953
Q157_SOURCE_DURATION_MILLIS = 70_867
Q157_WORK_ID = "7658501922794432731"
Q157_ACCOUNT = "云沐荟足道官方号"

PUBLISHED_PRICE_CNY_PER_OUTPUT_MINUTE = "0.007"
PUBLISHED_PRICE_REVIEWED_AT = "2026-08-03"
PUBLISHED_PRICE_DOCUMENT_ID = "volcengine-doc-6448-2486473"
PUBLISHED_PRICE_DOCUMENT_UPDATED_AT = "2026-07-22T16:52:35+08:00"
PUBLISHED_PRICE_FORMULA_VERSION = "mediakit-remux-output-milliseconds-tariff-v1"
CANARY_CEILING_MICROS = 20_000
ACCEPTANCE_ROOT = ROOT / ".deer-flow" / "acceptance"

_ATTEMPT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
_SAFE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_URL_RE = re.compile(r"(?i)(?:https?|mediakit|tos)://")
_MAX_KEY_BYTES = 4096
_CHUNK = 1024 * 1024


class CanaryError(RuntimeError):
    """An operator-safe error containing no external payload."""

    def __init__(self, code: str, *, reconciliation_required: bool = False) -> None:
        self.code = code if _SAFE_CODE_RE.fullmatch(code) else "INTERNAL_ERROR"
        self.reconciliation_required = bool(reconciliation_required)
        super().__init__(self.code)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise CanaryError("INVALID_ARGUMENTS")


@dataclass(frozen=True)
class PaidRemuxCanaryOptions:
    execute_paid: bool
    resume: bool
    attempt_id: str
    state_dir: Path
    mediakit_key_file: Path


PaidOperatorRunner = Callable[..., Awaitable[Any]]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _published_tariff_estimate_micros(duration_millis: int) -> int:
    """Ceil the public-list tariff without calling it a provider quote."""

    if isinstance(duration_millis, bool) or not isinstance(duration_millis, int) or duration_millis <= 0:
        raise CanaryError("INVALID_SOURCE_DURATION")
    micros_per_minute = 7_000
    return (duration_millis * micros_per_minute + 60_000 - 1) // 60_000


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(path: Path, *, code: str, mode: int | None = None) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError:
        raise CanaryError(code) from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise CanaryError(code)
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise CanaryError(code)
    return info


def _validate_source() -> Path:
    source = Q157_SOURCE
    info = _regular_file(source, code="Q157_SOURCE_INVALID")
    if info.st_size != Q157_SOURCE_SIZE_BYTES:
        raise CanaryError("Q157_SOURCE_SIZE_MISMATCH")
    first = _sha256_file(source)
    second = _sha256_file(source)
    if first != Q157_SOURCE_SHA256 or second != first:
        raise CanaryError("Q157_SOURCE_HASH_MISMATCH")
    return source


def _validate_key_file(path: Path, *, read_value: bool) -> str | None:
    key_path = path.expanduser().resolve()
    info = _regular_file(
        key_path,
        code="INVALID_MEDIAKIT_KEY_FILE",
        mode=0o600,
    )
    if info.st_size <= 0 or info.st_size > _MAX_KEY_BYTES:
        raise CanaryError("INVALID_MEDIAKIT_KEY_FILE")
    if not read_value:
        return None
    try:
        raw = key_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise CanaryError("INVALID_MEDIAKIT_KEY_FILE") from None
    value = raw.strip()
    if not value or any(character.isspace() for character in value):
        raise CanaryError("INVALID_MEDIAKIT_KEY_FILE")
    return value


def _resolved_state_dir(options: PaidRemuxCanaryOptions) -> Path:
    if not _ATTEMPT_RE.fullmatch(options.attempt_id):
        raise CanaryError("INVALID_ATTEMPT_ID")
    root = ACCEPTANCE_ROOT.resolve()
    state = options.state_dir.expanduser().resolve(strict=False)
    if state.parent != root or state == root:
        raise CanaryError("STATE_DIR_OUTSIDE_ACCEPTANCE_ROOT")
    return state


def _operator_capped_runtime_available() -> bool:
    return (
        getattr(
            paid_operator,
            "MEDIAKIT_REMUX_OPERATOR_CAPPED_POLICY_VERSION",
            None,
        )
        == OPERATOR_CAPPED_POLICY_VERSION
    )


def validate_dry_run(options: PaidRemuxCanaryOptions) -> None:
    if options.resume:
        raise CanaryError("RESUME_REQUIRES_PAID_EXECUTION")
    _resolved_state_dir(options)
    _validate_source()
    _validate_key_file(options.mediakit_key_file, read_value=False)


def _ensure_new_private_state_dir(path: Path) -> None:
    try:
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
    except OSError:
        raise CanaryError("STATE_DIR_EXISTS_OR_UNWRITABLE") from None
    if stat.S_IMODE(path.lstat().st_mode) != 0o700:
        raise CanaryError("STATE_DIR_NOT_PRIVATE")


def _require_private_state_dir(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError:
        raise CanaryError("RESUME_STATE_NOT_FOUND") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise CanaryError("RESUME_STATE_INVALID")
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise CanaryError("STATE_DIR_NOT_PRIVATE")


def _write_private_once(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        raise CanaryError("PRIVATE_STATE_WRITE_FAILED") from None


def _replace_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        _write_private_once(temporary, _canonical_bytes(payload) + b"\n")
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
        raise CanaryError("PRIVATE_STATE_WRITE_FAILED") from None


def _read_private_text(path: Path, *, code: str) -> str:
    info = _regular_file(path, code=code, mode=0o600)
    if info.st_size <= 0 or info.st_size > _MAX_KEY_BYTES:
        raise CanaryError(code)
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise CanaryError(code) from None
    if not value:
        raise CanaryError(code)
    return value


def _stage_source(source: Path, destination: Path) -> None:
    before = _sha256_file(source)
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with source.open("rb") as input_stream, os.fdopen(descriptor, "wb") as output:
            for chunk in iter(lambda: input_stream.read(_CHUNK), b""):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        destination.unlink(missing_ok=True)
        raise CanaryError("SOURCE_STAGING_FAILED") from None
    if destination.stat().st_size != Q157_SOURCE_SIZE_BYTES or _sha256_file(destination) != Q157_SOURCE_SHA256 or _sha256_file(source) != before or before != Q157_SOURCE_SHA256:
        destination.unlink(missing_ok=True)
        raise CanaryError("SOURCE_STAGING_HASH_MISMATCH")


def _new_cipher_key(path: Path) -> str:
    value = secrets.token_urlsafe(48)
    _write_private_once(path, (value + "\n").encode("utf-8"))
    return value


def _manifest_base(options: PaidRemuxCanaryOptions) -> dict[str, Any]:
    execution_run_id = f"q157-paid-{_sha256_text(options.attempt_id)[:24]}"
    client_token = (
        "ipmk-paid-v1-"
        + _sha256_text(
            "\0".join(
                (
                    Q157_SOURCE_SHA256,
                    Q157_WORK_ID,
                    Q157_ACCOUNT,
                    options.attempt_id,
                )
            )
        )[:48]
    )
    return {
        "contract_version": MANIFEST_VERSION,
        "attempt_id": options.attempt_id,
        "source_sha256": Q157_SOURCE_SHA256,
        "source_size_bytes": Q157_SOURCE_SIZE_BYTES,
        "source_duration_millis": Q157_SOURCE_DURATION_MILLIS,
        "work_id_sha256": _sha256_text(Q157_WORK_ID),
        "account_sha256": _sha256_text(Q157_ACCOUNT),
        "price_status": "operator_capped",
        "maximum_amount_micros": CANARY_CEILING_MICROS,
        "published_tariff_estimate_micros": _published_tariff_estimate_micros(
            Q157_SOURCE_DURATION_MILLIS,
        ),
        "published_price_formula_version": PUBLISHED_PRICE_FORMULA_VERSION,
        "currency": "CNY",
        "execution_run_id": execution_run_id,
        "client_token_sha256": _sha256_text(client_token),
        "scope_id": None,
        "request_digest": None,
        "scope_status": "initialized",
        "provider_task_status": None,
        "result_sha256": None,
    }


def _client_token(options: PaidRemuxCanaryOptions) -> str:
    return (
        "ipmk-paid-v1-"
        + _sha256_text(
            "\0".join(
                (
                    Q157_SOURCE_SHA256,
                    Q157_WORK_ID,
                    Q157_ACCOUNT,
                    options.attempt_id,
                )
            )
        )[:48]
    )


def _load_manifest(path: Path, options: PaidRemuxCanaryOptions) -> dict[str, Any]:
    raw = _read_private_text(path, code="RESUME_MANIFEST_INVALID")
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError:
        raise CanaryError("RESUME_MANIFEST_INVALID") from None
    expected = _manifest_base(options)
    if not isinstance(manifest, dict) or set(manifest) != set(expected):
        raise CanaryError("RESUME_MANIFEST_INVALID")
    for field in (
        "contract_version",
        "attempt_id",
        "source_sha256",
        "source_size_bytes",
        "source_duration_millis",
        "work_id_sha256",
        "account_sha256",
        "price_status",
        "maximum_amount_micros",
        "published_tariff_estimate_micros",
        "published_price_formula_version",
        "currency",
        "execution_run_id",
        "client_token_sha256",
    ):
        if manifest.get(field) != expected[field]:
            raise CanaryError("RESUME_MANIFEST_BINDING_MISMATCH")
    if manifest.get("scope_id") is not None and not isinstance(manifest["scope_id"], str):
        raise CanaryError("RESUME_MANIFEST_INVALID")
    if manifest.get("request_digest") is not None and not _HEX64_RE.fullmatch(str(manifest["request_digest"])):
        raise CanaryError("RESUME_MANIFEST_INVALID")
    return manifest


def _scope_hashes(options: PaidRemuxCanaryOptions, client_token: str) -> tuple[str, str]:
    tool_args = _canonical_sha256(
        {
            "contract_version": CONTRACT_VERSION,
            "attempt_id": options.attempt_id,
            "source_sha256": Q157_SOURCE_SHA256,
            "source_duration_millis": Q157_SOURCE_DURATION_MILLIS,
            "container_format": "MP4",
            "maximum_amount_micros": CANARY_CEILING_MICROS,
            "published_tariff_estimate_micros": _published_tariff_estimate_micros(
                Q157_SOURCE_DURATION_MILLIS,
            ),
            "published_price_formula_version": PUBLISHED_PRICE_FORMULA_VERSION,
        }
    )
    stage = _canonical_sha256(
        {
            "contract_version": "ip-agent-mediakit-paid-remux-stage-v1",
            "source_sha256": Q157_SOURCE_SHA256,
            "container_format": "MP4",
        }
    )
    assert _sha256_text(client_token) == _manifest_base(options)["client_token_sha256"]
    return tool_args, stage


def _assert_scope(scope: Mapping[str, Any], options: PaidRemuxCanaryOptions) -> None:
    client_token = _client_token(options)
    tool_args, stage = _scope_hashes(options, client_token)
    expected = {
        "owner_user_id": "operator-q157-paid-remux",
        "request_key": f"q157-paid-remux:{options.attempt_id}",
        "thread_id": "q157-paid-remux-canary",
        "server_name": paid_operator.MEDIAKIT_REMUX_PAID_SERVER,
        "tool_name": paid_operator.MEDIAKIT_REMUX_PAID_TOOL,
        "tool_args_sha256": tool_args,
        "provider": paid_operator.MEDIAKIT_REMUX_PAID_PROVIDER,
        "capability": paid_operator.MEDIAKIT_REMUX_PAID_CAPABILITY,
        "model": paid_operator.MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION,
        "sku": paid_operator.MEDIAKIT_REMUX_PAID_SKU,
        "source_sha256": Q157_SOURCE_SHA256,
        "source_duration_millis": Q157_SOURCE_DURATION_MILLIS,
        "stage_digest": stage,
        "provider_request_sha256": paid_operator.build_mediakit_remux_paid_provider_request_sha256(
            source_sha256=Q157_SOURCE_SHA256,
            client_token=client_token,
        ),
        "maximum_amount_micros": CANARY_CEILING_MICROS,
        "currency": "CNY",
        "price_status": "operator_capped",
        "billing_basis": ("operator cap from published 0.007 CNY/output-minute; provider actual amount unavailable"),
        "policy_version": OPERATOR_CAPPED_POLICY_VERSION,
        "price_version": (f"{PUBLISHED_PRICE_FORMULA_VERSION}-reviewed-{PUBLISHED_PRICE_REVIEWED_AT}"),
        "provider_input_attested": False,
        "evidence_coverage": "partial",
        "warning_code": "provider_content_hash_unattested",
    }
    if any(scope.get(key) != value for key, value in expected.items()):
        raise CanaryError("CANARY_SCOPE_BINDING_MISMATCH")


async def _schema_head() -> str:
    from sqlalchemy import text

    session_factory = get_session_factory()
    if session_factory is None:
        raise CanaryError("CANARY_DATABASE_UNAVAILABLE")
    async with session_factory() as session:
        value = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    return str(value)


async def _prepare_scope(
    repository: PersonalIPPaidCallRepository,
    options: PaidRemuxCanaryOptions,
    manifest: dict[str, Any],
    manifest_path: Path,
) -> dict[str, Any]:
    owner = "operator-q157-paid-remux"
    thread = "q157-paid-remux-canary"
    client_token = _client_token(options)
    tool_args, stage = _scope_hashes(options, client_token)
    scope: dict[str, Any] | None = None
    scope_id = manifest.get("scope_id")
    if isinstance(scope_id, str):
        scope = await repository.get(scope_id, owner_user_id=owner)
    elif options.resume:
        matches = [item for item in await repository.list_thread(owner_user_id=owner, thread_id=thread) if item.get("request_key") == f"q157-paid-remux:{options.attempt_id}"]
        if len(matches) != 1:
            raise CanaryError("RESUME_SCOPE_NOT_FOUND")
        scope = matches[0]
    else:
        now = datetime.now(UTC)
        scope = await repository.request_call(
            owner_user_id=owner,
            request_key=f"q157-paid-remux:{options.attempt_id}",
            scope_kind="run",
            thread_id=thread,
            origin_run_id=f"q157-origin-{_sha256_text(options.attempt_id)[:24]}",
            server_name=paid_operator.MEDIAKIT_REMUX_PAID_SERVER,
            tool_name=paid_operator.MEDIAKIT_REMUX_PAID_TOOL,
            tool_args_sha256=tool_args,
            provider=paid_operator.MEDIAKIT_REMUX_PAID_PROVIDER,
            capability=paid_operator.MEDIAKIT_REMUX_PAID_CAPABILITY,
            model=paid_operator.MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION,
            sku=paid_operator.MEDIAKIT_REMUX_PAID_SKU,
            provider_label="MediaKit",
            capability_label="Managed HTTPS remux",
            object_ref_label=f"public benchmark {Q157_SOURCE_SHA256[:12]}...{Q157_SOURCE_SHA256[-12:]}",
            source_duration_millis=Q157_SOURCE_DURATION_MILLIS,
            source_sha256=Q157_SOURCE_SHA256,
            stage_digest=stage,
            provider_request_sha256=paid_operator.build_mediakit_remux_paid_provider_request_sha256(
                source_sha256=Q157_SOURCE_SHA256,
                client_token=client_token,
            ),
            maximum_amount_micros=CANARY_CEILING_MICROS,
            currency="CNY",
            billing_basis=("operator cap from published 0.007 CNY/output-minute; provider actual amount unavailable"),
            policy_version=OPERATOR_CAPPED_POLICY_VERSION,
            price_version=(f"{PUBLISHED_PRICE_FORMULA_VERSION}-reviewed-{PUBLISHED_PRICE_REVIEWED_AT}"),
            provider_input_attested=False,
            evidence_coverage="partial",
            warning_code="provider_content_hash_unattested",
            expires_at=now + timedelta(minutes=30),
            price_status="operator_capped",
            now=now,
        )
    if scope is None:
        raise CanaryError("CANARY_SCOPE_NOT_FOUND")
    _assert_scope(scope, options)
    manifest.update(
        {
            "scope_id": scope["id"],
            "request_digest": scope["request_digest"],
            "scope_status": scope["status"],
            "provider_task_status": scope.get("provider_task_status"),
        }
    )
    _replace_private_json(manifest_path, manifest)

    proof_seed = {
        "contract_version": "ip-agent-mediakit-paid-remux-operator-consent-v1",
        "attempt_id": options.attempt_id,
        "request_digest": scope["request_digest"],
        "maximum_amount_micros": CANARY_CEILING_MICROS,
        "execute_paid": True,
    }
    if scope["status"] == "requested":
        scope = await repository.approve(
            scope["id"],
            owner_user_id=owner,
            event_key="operator-approved-canary",
            expected_request_digest=scope["request_digest"],
            approval_digest=_canonical_sha256(proof_seed),
            expected_event_count=scope["event_count"],
        )
    if scope is not None and scope["status"] == "approved":
        scope = await repository.reserve(
            scope["id"],
            owner_user_id=owner,
            event_key="operator-capped-canary-reservation",
            expected_request_digest=scope["request_digest"],
            execution_run_id=manifest["execution_run_id"],
            amount_micros=CANARY_CEILING_MICROS,
            expected_event_count=scope["event_count"],
        )
    if scope is not None and scope["status"] == "reserved":
        cipher_key = _read_private_text(
            manifest_path.parent / "paid-recovery.key",
            code="RECOVERY_CIPHER_KEY_INVALID",
        )
        jti = "canary-jti-" + hashlib.sha256(f"{cipher_key}\0{options.attempt_id}\0admission".encode()).hexdigest()
        scope = await repository.admit(
            scope["id"],
            owner_user_id=owner,
            event_key="operator-capped-canary-admission",
            expected_request_digest=scope["request_digest"],
            execution_run_id=manifest["execution_run_id"],
            admission_jti=jti,
            admission_proof_digest=_canonical_sha256({**proof_seed, "transition": "admitted"}),
            expected_event_count=scope["event_count"],
        )
    if scope is None or scope.get("status") not in {"admitted", "reconciliation_required"}:
        raise CanaryError("CANARY_SCOPE_NOT_ADMITTED")
    _assert_scope(scope, options)
    manifest.update(
        {
            "scope_status": scope["status"],
            "provider_task_status": scope.get("provider_task_status"),
        }
    )
    _replace_private_json(manifest_path, manifest)
    return scope


def _dump_model(value: Any) -> dict[str, Any]:
    try:
        payload = value.model_dump(mode="json")
    except Exception:
        raise CanaryError("INVALID_OPERATOR_RECEIPT") from None
    if not isinstance(payload, dict):
        raise CanaryError("INVALID_OPERATOR_RECEIPT")
    return payload


def _assert_secret_free(value: Any, *, forbidden: Sequence[str]) -> None:
    def inspect(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                normalized = re.sub(r"[^a-z0-9]", "", str(key).casefold())
                if any(
                    fragment in normalized
                    for fragment in (
                        "apikey",
                        "runtimeurl",
                        "uploadurl",
                        "rawtaskid",
                        "rawfileid",
                        "encryptedprovider",
                    )
                ) and not normalized.endswith(("sha256", "sha256s", "persisted")):
                    raise CanaryError("REPORT_REDACTION_FAILED")
                inspect(child)
            return
        if isinstance(item, (list, tuple)):
            for child in item:
                inspect(child)
            return
        if isinstance(item, str):
            if _URL_RE.search(item) or any(secret and secret in item for secret in forbidden):
                raise CanaryError("REPORT_REDACTION_FAILED")
            return
        if item is not None and not isinstance(item, (bool, int, float)):
            raise CanaryError("REPORT_REDACTION_FAILED")

    inspect(value)


async def run_paid_canary(
    options: PaidRemuxCanaryOptions,
    *,
    operator_runner: PaidOperatorRunner | None = None,
) -> dict[str, Any]:
    if not options.execute_paid:
        raise CanaryError("PAID_EXECUTION_NOT_CONFIRMED")
    if not _operator_capped_runtime_available():
        raise CanaryError("OPERATOR_CAPPED_REMUX_RUNTIME_NOT_SUPPORTED")

    state_dir = _resolved_state_dir(options)
    source = _validate_source()
    _validate_key_file(options.mediakit_key_file, read_value=False)
    if options.resume:
        _require_private_state_dir(state_dir)
    else:
        _ensure_new_private_state_dir(state_dir)

    manifest_path = state_dir / "state.json"
    cipher_path = state_dir / "paid-recovery.key"
    staged_source = state_dir / "q157-source.mp4"
    result_path = state_dir / "result.json"
    database_dir = state_dir / "db"

    if options.resume:
        if result_path.exists():
            raise CanaryError("CANARY_ALREADY_COMPLETED")
        manifest = _load_manifest(manifest_path, options)
        cipher_key = _read_private_text(
            cipher_path,
            code="RECOVERY_CIPHER_KEY_INVALID",
        )
        _regular_file(staged_source, code="STAGED_SOURCE_INVALID", mode=0o600)
        if staged_source.stat().st_size != Q157_SOURCE_SIZE_BYTES or _sha256_file(staged_source) != Q157_SOURCE_SHA256:
            raise CanaryError("STAGED_SOURCE_INVALID")
    else:
        cipher_key = _new_cipher_key(cipher_path)
        _stage_source(source, staged_source)
        manifest = _manifest_base(options)
        _replace_private_json(manifest_path, manifest)

    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(database_dir)))
    database_path = database_dir / "deerflow.db"
    if database_path.exists():
        os.chmod(database_path, 0o600)
    try:
        if await _schema_head() != "0030_personal_ip_editorial_program_versions":
            raise CanaryError("CANARY_DATABASE_REVISION_MISMATCH")
        session_factory = get_session_factory()
        if session_factory is None:
            raise CanaryError("CANARY_DATABASE_UNAVAILABLE")
        repository = PersonalIPPaidCallRepository(
            session_factory,
            provider_task_cipher=ChannelCredentialCipher.from_key(cipher_key),
        )
        scope = await _prepare_scope(
            repository,
            options,
            manifest,
            manifest_path,
        )
        mediakit_key = _validate_key_file(
            options.mediakit_key_file,
            read_value=True,
        )
        assert mediakit_key is not None
        runner = operator_runner or paid_operator.run_paid_mediakit_remux
        try:
            result = await runner(
                repository=repository,
                owner_user_id="operator-q157-paid-remux",
                scope_id=scope["id"],
                expected_request_digest=scope["request_digest"],
                execution_run_id=manifest["execution_run_id"],
                source_path=staged_source,
                expected_source_sha256=Q157_SOURCE_SHA256,
                client_token=_client_token(options),
                mediakit_api_key=mediakit_key,
            )
        except paid_operator.MediaKitRemuxPaidOperatorError as error:
            raise CanaryError(
                error.code,
                reconciliation_required=error.reconciliation_required,
            ) from None

        remux_receipt = _dump_model(result.remux_receipt)
        paid_receipt = _dump_model(result.paid_execution_receipt)
        report: dict[str, Any] = {
            "contract_version": CONTRACT_VERSION,
            "status": "completed",
            "product_promoted": False,
            "operator_binding": {
                "attempt_id_sha256": _sha256_text(options.attempt_id),
                "work_id_sha256": _sha256_text(Q157_WORK_ID),
                "account_sha256": _sha256_text(Q157_ACCOUNT),
                "source_sha256": Q157_SOURCE_SHA256,
                "source_size_bytes": Q157_SOURCE_SIZE_BYTES,
                "source_duration_millis": Q157_SOURCE_DURATION_MILLIS,
            },
            "pricing": {
                "price_status": "operator_capped",
                "published_unit_price_cny_per_output_minute": PUBLISHED_PRICE_CNY_PER_OUTPUT_MINUTE,
                "published_price_reviewed_at": PUBLISHED_PRICE_REVIEWED_AT,
                "published_price_document_id": PUBLISHED_PRICE_DOCUMENT_ID,
                "published_price_document_updated_at": PUBLISHED_PRICE_DOCUMENT_UPDATED_AT,
                "published_price_formula_version": PUBLISHED_PRICE_FORMULA_VERSION,
                "published_tariff_estimate_micros": _published_tariff_estimate_micros(
                    Q157_SOURCE_DURATION_MILLIS,
                ),
                "maximum_amount_micros": CANARY_CEILING_MICROS,
                "currency": "CNY",
                "provider_actual_amount_micros": None,
            },
            "remux_receipt": remux_receipt,
            "paid_execution_receipt": paid_receipt,
            "controls": {
                "execute_paid_explicit": True,
                "resume_explicit": options.resume,
                "isolated_database": True,
                "runtime_url_persisted": False,
                "credential_values_persisted_in_report": False,
                "automatic_retries": 0,
            },
        }
        _assert_secret_free(
            report,
            forbidden=(
                mediakit_key,
                cipher_key,
                _client_token(options),
                str(result.runtime_url),
            ),
        )
        _write_private_once(result_path, _canonical_bytes(report) + b"\n")
        report_digest = _canonical_sha256(report)
        current = await repository.get(
            scope["id"],
            owner_user_id="operator-q157-paid-remux",
        )
        manifest.update(
            {
                "scope_status": current.get("status") if current else "unknown",
                "provider_task_status": (current.get("provider_task_status") if current else None),
                "result_sha256": report_digest,
            }
        )
        _replace_private_json(manifest_path, manifest)
        return {
            "ok": True,
            "code": "PAID_REMUX_CANARY_COMPLETED",
            "report_sha256": report_digest,
            "paid_call_status": paid_receipt.get("paid_call_status"),
        }
    finally:
        await close_engine()
        if database_path.exists():
            os.chmod(database_path, 0o600)


def _parse_args(argv: Sequence[str] | None = None) -> PaidRemuxCanaryOptions:
    parser = _SafeArgumentParser(
        description="Run the isolated Q157 paid Remux operator canary.",
    )
    parser.add_argument("--execute-paid", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--mediakit-key-file", type=Path, required=True)
    namespace = parser.parse_args(argv)
    if namespace.resume and not namespace.execute_paid:
        raise CanaryError("RESUME_REQUIRES_PAID_EXECUTION")
    return PaidRemuxCanaryOptions(
        execute_paid=namespace.execute_paid,
        resume=namespace.resume,
        attempt_id=namespace.attempt_id,
        state_dir=namespace.state_dir,
        mediakit_key_file=namespace.mediakit_key_file,
    )


def _safe_error(error: BaseException) -> tuple[str, bool]:
    if isinstance(error, CanaryError):
        return error.code, error.reconciliation_required
    if isinstance(error, KeyboardInterrupt):
        return "INTERRUPTED", False
    return "INTERNAL_ERROR", False


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
                        "database_writes": 0,
                        "operator_capped_runtime_available": _operator_capped_runtime_available(),
                    },
                    separators=(",", ":"),
                )
            )
            return 0
        old_umask = os.umask(0o077)
        try:
            result = asyncio.run(run_paid_canary(options))
        finally:
            os.umask(old_umask)
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except BaseException as error:
        if isinstance(error, SystemExit):
            raise
        code, reconciliation = _safe_error(error)
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": code,
                    "reconciliation_required": reconciliation,
                },
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
