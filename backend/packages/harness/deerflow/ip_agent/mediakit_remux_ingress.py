"""Operator-only MediaKit remux bridge for a temporary HTTPS input.

This module is intentionally not registered as an Agent tool.  It proves one
narrow provider contract: upload a sealed local video, request an MP4 remux,
and return the provider's temporary HTTPS result to the in-process caller.

The URL is runtime-only.  Receipts contain hashes of provider identifiers and
the URL, never the raw values.  A remux result is a derivative candidate; the
provider does not attest that its bytes equal the sealed source.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from deerflow.community.url_safety import resolve_host_addresses, validate_public_http_url

MEDIAKIT_REMUX_INGRESS_CONTRACT_VERSION = "ip-mediakit-remux-https-candidate-v1"
MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION = "volcengine-mediakit-remux-https-ingress-v1"
MEDIAKIT_REMUX_SUBMISSION_RECOVERY_CONTRACT_VERSION = "ip-mediakit-remux-submission-recovery-v1"
MEDIAKIT_REMUX_SUBMITTED_TASK_CONTRACT_VERSION = "ip-mediakit-remux-submitted-task-recovery-v1"
MEDIAKIT_REMUX_RECOVERY_REQUEST_CONTRACT_VERSION = "ip-mediakit-remux-recovery-request-v1"
MEDIAKIT_ENDPOINT = "https://mediakit.cn-beijing.volces.com"

_UPLOAD_TARGET_PATH = "/api/v1/tools-sync/request-media-upload-url"
_REMUX_PATH = "/api/v1/tools/remux-video"
_TASK_PATH_PREFIX = "/api/v1/tasks/"
_CONTAINER_FORMAT = "MP4"
_MAX_SOURCE_BYTES = 512 * 1024 * 1024
_MAX_RESPONSE_BYTES = 1024 * 1024
_REQUEST_TIMEOUT_SECONDS = 120
_TOTAL_TIMEOUT_SECONDS = 600
_MAX_POLL_ATTEMPTS = 80
_POLL_INTERVAL_SECONDS = 3.0
_MIN_TTL_SECONDS = 23 * 60 * 60
_MAX_TTL_SECONDS = 25 * 60 * 60
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CLIENT_TOKEN_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_PROVIDER_HOST_SUFFIXES = (
    "volces.com",
    "volccdn.com",
    "volcvideo.com",
    "volcvod.com",
    "bytevod.com",
)
_TERMINAL_FAILURE_STATUSES = frozenset({"failed", "canceled", "cancelled"})
_PENDING_STATUSES = frozenset({"queued", "running"})


class MediaKitRemuxTaskObserver(Protocol):
    """Persist provider-task recovery without exposing it in public receipts."""

    async def before_provider_submit(
        self,
        *,
        upload_file_id: str,
        client_token: str,
    ) -> None: ...

    async def provider_task_submitted(
        self,
        *,
        raw_task_id: str,
    ) -> None: ...

    async def provider_task_running(
        self,
        *,
        raw_task_id: str,
        observed_status: str,
    ) -> None: ...

    async def provider_task_terminal(
        self,
        *,
        raw_task_id: str,
        terminal_status: str,
        terminal_envelope: dict[str, Any],
    ) -> None: ...


class MediaKitRemuxSubmissionObserver(MediaKitRemuxTaskObserver, Protocol):
    """Observer extension which can persist an exact replay-safe submission."""

    async def provider_submission_prepared(
        self,
        *,
        submission_record: MediaKitRemuxSubmissionRecord,
        client_token: str,
    ) -> None: ...

    async def provider_task_submission_confirmed(
        self,
        *,
        submitted_task_record: MediaKitRemuxSubmittedTaskRecord,
    ) -> None: ...


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MediaKitRemuxSubmissionRecord(_StrictModel):
    """Exact pre-submit state needed to resume without uploading again.

    The MediaKit file id is intentionally present because the operator-side
    observer must encrypt it for exact replay.  It is hidden from ``repr`` and
    must never enter normal receipts, logs, exports, or model context.
    """

    contract_version: Literal["ip-mediakit-remux-submission-recovery-v1"]
    provider: Literal["volcengine-mediakit"]
    capability: Literal["managed_https_ingress_remux"]
    adapter_version: Literal["volcengine-mediakit-remux-https-ingress-v1"]
    endpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_size_bytes: int = Field(strict=True, gt=0, le=_MAX_SOURCE_BYTES)
    upload_file_id: str = Field(min_length=1, max_length=1024, repr=False)
    upload_file_id_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    upload_url_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    client_token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    container_format: Literal["MP4"]
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    submit_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_response_sha256s: list[str] = Field(min_length=2, max_length=2)
    provider_response_sizes_bytes: list[int] = Field(min_length=2, max_length=2)
    provider_request_id_sha256s: list[str] = Field(default_factory=list, max_length=2)
    retries: Literal[0]

    @model_validator(mode="after")
    def validate_submission_record(self) -> MediaKitRemuxSubmissionRecord:
        try:
            file_id = _require_mediakit_uri(self.upload_file_id)
        except MediaKitRemuxIngressError as exc:
            raise ValueError("submission record contains an invalid MediaKit file id") from exc
        if self.endpoint_sha256 != _sha256_text(MEDIAKIT_ENDPOINT):
            raise ValueError("submission record endpoint binding is invalid")
        if self.upload_file_id_sha256 != _sha256_text(file_id):
            raise ValueError("submission record file-id binding is invalid")
        if len(self.provider_response_sha256s) != len(self.provider_response_sizes_bytes):
            raise ValueError("submission response hashes and sizes are inconsistent")
        if any(not _SHA256_RE.fullmatch(item) for item in self.provider_response_sha256s):
            raise ValueError("submission record contains an invalid response digest")
        if any(not _SHA256_RE.fullmatch(item) for item in self.provider_request_id_sha256s):
            raise ValueError("submission record contains an invalid request-id digest")
        if any(size < 0 or size > _MAX_RESPONSE_BYTES for size in self.provider_response_sizes_bytes):
            raise ValueError("submission record contains an invalid response size")
        return self


class MediaKitRemuxSubmittedTaskRecord(_StrictModel):
    """Safe submit-response digest plus the encrypted-at-rest task identity."""

    contract_version: Literal["ip-mediakit-remux-submitted-task-recovery-v1"]
    provider: Literal["volcengine-mediakit"]
    capability: Literal["managed_https_ingress_remux"]
    task_id: str = Field(min_length=1, max_length=1024, repr=False)
    task_id_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_response_size_bytes: int = Field(strict=True, ge=0, le=_MAX_RESPONSE_BYTES)
    provider_request_id_sha256s: list[str] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def validate_submitted_task_record(self) -> MediaKitRemuxSubmittedTaskRecord:
        try:
            task_id = _require_identifier(
                self.task_id,
                code="INVALID_RECOVERY_TASK_ID",
                billing_outcome="unknown",
            )
        except MediaKitRemuxIngressError as exc:
            raise ValueError("submitted-task record contains an invalid task id") from exc
        if self.task_id_sha256 != _sha256_text(task_id):
            raise ValueError("submitted-task record task-id binding is invalid")
        if any(not _SHA256_RE.fullmatch(item) for item in self.provider_request_id_sha256s):
            raise ValueError("submitted-task record contains an invalid request-id digest")
        return self


class MediaKitRemuxRecoveryRequest(_StrictModel):
    """One explicit recovery action over an already uploaded MediaKit file."""

    contract_version: Literal["ip-mediakit-remux-recovery-request-v1"]
    action: Literal["replay_submission_once", "query_existing_task"]
    submission: MediaKitRemuxSubmissionRecord
    client_token: str = Field(min_length=1, max_length=64, repr=False)
    submitted_task: MediaKitRemuxSubmittedTaskRecord | None = None

    @model_validator(mode="after")
    def validate_recovery_request(self) -> MediaKitRemuxRecoveryRequest:
        try:
            token = _require_client_token(self.client_token)
        except MediaKitRemuxIngressError as exc:
            raise ValueError("recovery request contains an invalid client token") from exc
        if self.submission.client_token_sha256 != _sha256_text(token):
            raise ValueError("recovery request client-token binding is invalid")
        submit_body = _remux_submit_body(
            file_id=self.submission.upload_file_id,
            client_token=token,
        )
        if self.submission.submit_body_sha256 != _canonical_sha256(submit_body):
            raise ValueError("recovery request submit-body binding is invalid")
        expected_request_sha256 = _remux_request_sha256(
            source_sha256=self.submission.source_sha256,
            source_size_bytes=self.submission.source_size_bytes,
            file_id=self.submission.upload_file_id,
            client_token=token,
        )
        if self.submission.request_sha256 != expected_request_sha256:
            raise ValueError("recovery request projection binding is invalid")
        if self.action == "query_existing_task":
            if self.submitted_task is None:
                raise ValueError("query recovery requires a submitted-task record")
        elif self.submitted_task is not None:
            raise ValueError("submission replay must not carry a submitted-task record")
        return self


class MediaKitRemuxIngressReceipt(_StrictModel):
    contract_version: Literal["ip-mediakit-remux-https-candidate-v1"]
    adapter_version: Literal["volcengine-mediakit-remux-https-ingress-v1"]
    provider: Literal["volcengine-mediakit"]
    endpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    derived_from_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_size_bytes: int = Field(strict=True, gt=0, le=_MAX_SOURCE_BYTES)
    source_hash_checks: Literal[2]
    source_hash_unchanged: Literal[True]
    container_format: Literal["MP4"]
    candidate_kind: Literal["provider_remux_derivative"]
    candidate_byte_identity: Literal["not_attested_equal_to_source"]
    provider_content_attestation: Literal["unavailable"]
    upload_file_id_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    client_token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_id_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_request_id_sha256s: list[str] = Field(default_factory=list, max_length=_MAX_POLL_ATTEMPTS + 2)
    runtime_url_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_response_sha256s: list[str] = Field(min_length=3, max_length=_MAX_POLL_ATTEMPTS + 3)
    provider_response_sizes_bytes: list[int] = Field(min_length=3, max_length=_MAX_POLL_ATTEMPTS + 3)
    status: Literal["completed"]
    completed_at: datetime
    expires_at: datetime
    observed_ttl_seconds: int = Field(strict=True, ge=_MIN_TTL_SECONDS, le=_MAX_TTL_SECONDS)
    expiry_basis: Literal["provider_reported"]
    poll_attempts: int = Field(strict=True, ge=1, le=_MAX_POLL_ATTEMPTS)
    max_poll_attempts: Literal[80]
    poll_interval_seconds: Literal[3.0]
    response_size_limit_bytes: Literal[1048576]
    request_timeout_seconds: Literal[120]
    total_timeout_seconds: Literal[600]
    retries: Literal[0]
    billing_status: Literal["provider_amount_unavailable"]

    @model_validator(mode="after")
    def validate_receipt(self) -> MediaKitRemuxIngressReceipt:
        if self.completed_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("remux receipt timestamps must be timezone-aware")
        observed_ttl = round((self.expires_at - self.completed_at).total_seconds())
        if observed_ttl != self.observed_ttl_seconds:
            raise ValueError("remux receipt TTL does not match its timestamps")
        if len(self.provider_response_sha256s) != len(self.provider_response_sizes_bytes):
            raise ValueError("remux receipt response hashes and sizes are inconsistent")
        if any(not _SHA256_RE.fullmatch(item) for item in self.provider_request_id_sha256s):
            raise ValueError("remux receipt contains an invalid request-id digest")
        if any(size < 0 or size > _MAX_RESPONSE_BYTES for size in self.provider_response_sizes_bytes):
            raise ValueError("remux receipt contains an invalid response size")
        return self


@dataclass(frozen=True)
class MediaKitRemuxHTTPSCandidate:
    """A temporary provider URL plus a secret-free receipt.

    ``runtime_url`` is excluded from ``repr`` so ordinary logging cannot expose
    its query signature.  The caller must keep it in memory and pass it only to
    the intended provider consumer.
    """

    runtime_url: str = field(repr=False)
    receipt: MediaKitRemuxIngressReceipt


class MediaKitRemuxIngressError(RuntimeError):
    """Bounded error that never includes provider payloads or credentials."""

    def __init__(
        self,
        code: str,
        *,
        billing_outcome: Literal["not_submitted", "provider_rejected", "unknown"],
        http_status: int | None = None,
    ) -> None:
        self.code = code[:80]
        self.billing_outcome = billing_outcome
        self.http_status = http_status
        super().__init__(self.code)


class _PathByteStream(httpx.AsyncByteStream):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._sha256 = hashlib.sha256()
        self._size_bytes = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        with self._path.open("rb") as source:
            while chunk := await asyncio.to_thread(source.read, 1024 * 1024):
                self._sha256.update(chunk)
                self._size_bytes += len(chunk)
                yield chunk

    def require_expected_bytes(
        self,
        *,
        expected_sha256: str,
        expected_size_bytes: int,
    ) -> None:
        """Fail before paid submission unless the PUT consumed sealed bytes."""

        if self._size_bytes != expected_size_bytes or self._sha256.hexdigest() != expected_sha256:
            raise MediaKitRemuxIngressError(
                "UPLOADED_SOURCE_INTEGRITY_MISMATCH",
                billing_outcome="not_submitted",
            )


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _monotonic() -> float:
    return time.monotonic()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _remux_submit_body(*, file_id: str, client_token: str) -> dict[str, str]:
    return {
        "video_url": file_id,
        "container_format": _CONTAINER_FORMAT,
        "client_token": client_token,
    }


def _remux_request_sha256(
    *,
    source_sha256: str,
    source_size_bytes: int,
    file_id: str,
    client_token: str,
) -> str:
    return _canonical_sha256(
        {
            "contract_version": MEDIAKIT_REMUX_INGRESS_CONTRACT_VERSION,
            "adapter_version": MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION,
            "endpoint": MEDIAKIT_ENDPOINT,
            "derived_from_source_sha256": source_sha256,
            "source_size_bytes": source_size_bytes,
            "upload_file_id_sha256": _sha256_text(file_id),
            "container_format": _CONTAINER_FORMAT,
            "client_token_sha256": _sha256_text(client_token),
            "retries": 0,
        }
    )


def _provider_headers(api_key: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Amk-Cli-Runtime": "deerflow-ip-agent",
        "X-Amk-Task-Source": "cli",
        "x-surface": "agent",
    }


def _is_provider_host(hostname: str) -> bool:
    normalized = hostname.rstrip(".").lower()
    return any(normalized == suffix or normalized.endswith(f".{suffix}") for suffix in _PROVIDER_HOST_SUFFIXES)


def _validate_runtime_https_url(
    value: Any,
    *,
    purpose: str,
    billing_outcome: Literal["not_submitted", "unknown"],
) -> str:
    candidate = str(value or "").strip()
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        raise MediaKitRemuxIngressError("INVALID_PROVIDER_HTTPS_URL", billing_outcome=billing_outcome) from None
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None or port not in {None, 443} or parsed.fragment or not _is_provider_host(parsed.hostname):
        raise MediaKitRemuxIngressError("INVALID_PROVIDER_HTTPS_URL", billing_outcome=billing_outcome)
    safety_error = validate_public_http_url(
        candidate,
        action=purpose,
        allow_proxy_fake_ip=True,
        resolver=resolve_host_addresses,
    )
    if safety_error:
        raise MediaKitRemuxIngressError("UNSAFE_PROVIDER_HTTPS_URL", billing_outcome=billing_outcome)
    return candidate


def validate_mediakit_runtime_https_url(value: Any) -> str:
    """Revalidate one ephemeral MediaKit result URL at its consumption boundary.

    A URL accepted when the provider task completes can still be stale or have
    been substituted before a downstream consumer uses it.  Consumers must
    therefore repeat the same fixed-host/public-address check and must not
    implement a second, weaker URL policy.
    """

    return _validate_runtime_https_url(
        value,
        purpose="download a MediaKit remux derivative",
        billing_outcome="unknown",
    )


def _parse_upload_headers(value: Any, *, api_key: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    if value is None:
        return parsed
    if isinstance(value, Mapping):
        items = value.items()
    elif isinstance(value, list):
        pairs: list[tuple[Any, Any]] = []
        for item in value:
            if not isinstance(item, Mapping):
                raise MediaKitRemuxIngressError("INVALID_UPLOAD_HEADERS", billing_outcome="not_submitted")
            key = item.get("key", item.get("name", item.get("header")))
            pairs.append((key, item.get("value", item.get("val"))))
        items = pairs
    else:
        raise MediaKitRemuxIngressError("INVALID_UPLOAD_HEADERS", billing_outcome="not_submitted")
    for raw_key, raw_value in items:
        key = str(raw_key or "").strip()
        header_value = str(raw_value or "").strip()
        if not key or "\r" in key or "\n" in key or "\r" in header_value or "\n" in header_value:
            raise MediaKitRemuxIngressError("INVALID_UPLOAD_HEADERS", billing_outcome="not_submitted")
        if api_key in header_value:
            raise MediaKitRemuxIngressError("MEDIAKIT_KEY_IN_UPLOAD_TARGET", billing_outcome="not_submitted")
        parsed[key] = header_value
    return parsed


async def _bounded_response_bytes(response: httpx.Response) -> bytes:
    length = response.headers.get("content-length")
    if length:
        try:
            declared = int(length)
        except ValueError as exc:
            raise MediaKitRemuxIngressError("INVALID_RESPONSE_LENGTH", billing_outcome="unknown") from exc
        if declared < 0 or declared > _MAX_RESPONSE_BYTES:
            raise MediaKitRemuxIngressError("RESPONSE_TOO_LARGE", billing_outcome="unknown")
    chunks: list[bytes] = []
    observed = 0
    async for chunk in response.aiter_bytes(64 * 1024):
        observed += len(chunk)
        if observed > _MAX_RESPONSE_BYTES:
            raise MediaKitRemuxIngressError("RESPONSE_TOO_LARGE", billing_outcome="unknown")
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_mapping(encoded: bytes, *, code: str, billing_outcome: Literal["not_submitted", "unknown"]) -> Mapping[str, Any]:
    try:
        payload = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MediaKitRemuxIngressError(code, billing_outcome=billing_outcome) from exc
    if not isinstance(payload, Mapping):
        raise MediaKitRemuxIngressError(code, billing_outcome=billing_outcome)
    return payload


def _require_provider_success(
    payload: Mapping[str, Any],
    *,
    code: str,
    billing_outcome: Literal["not_submitted", "unknown"],
) -> None:
    if payload.get("success") is False or payload.get("error") is not None:
        raise MediaKitRemuxIngressError(code, billing_outcome=billing_outcome)


def _require_identifier(value: Any, *, code: str, billing_outcome: Literal["not_submitted", "unknown"]) -> str:
    if not isinstance(value, str) or value.strip() != value:
        raise MediaKitRemuxIngressError(code, billing_outcome=billing_outcome)
    identifier = value
    if not identifier or len(identifier) > 1024 or any(character in identifier for character in "\r\n"):
        raise MediaKitRemuxIngressError(code, billing_outcome=billing_outcome)
    return identifier


def _require_client_token(value: Any) -> str:
    if not isinstance(value, str) or not _CLIENT_TOKEN_RE.fullmatch(value):
        raise MediaKitRemuxIngressError("INVALID_CLIENT_TOKEN", billing_outcome="not_submitted")
    return value


def _require_mediakit_uri(value: Any) -> str:
    identifier = _require_identifier(
        value,
        code="MISSING_UPLOAD_FILE_ID",
        billing_outcome="not_submitted",
    )
    try:
        parsed = urlsplit(identifier)
    except ValueError:
        raise MediaKitRemuxIngressError("INVALID_MEDIAKIT_FILE_URI", billing_outcome="not_submitted") from None
    if parsed.scheme.lower() != "mediakit" or not parsed.netloc or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise MediaKitRemuxIngressError("INVALID_MEDIAKIT_FILE_URI", billing_outcome="not_submitted")
    return identifier


def _request_ids(payload: Mapping[str, Any]) -> list[str]:
    identifiers: list[str] = []
    for key in ("request_id", "requestId"):
        value = str(payload.get(key) or "").strip()
        if value and len(value) <= 1024 and "\r" not in value and "\n" not in value:
            identifiers.append(value)
    return identifiers


def _parse_expires_at(value: Any, *, completed_at: datetime) -> tuple[datetime, int]:
    if value is None:
        raise MediaKitRemuxIngressError("MISSING_PROVIDER_EXPIRY", billing_outcome="unknown")
    if isinstance(value, bool):
        raise MediaKitRemuxIngressError("INVALID_PROVIDER_EXPIRY", billing_outcome="unknown")
    if isinstance(value, int):
        if value <= 0:
            raise MediaKitRemuxIngressError("INVALID_PROVIDER_EXPIRY", billing_outcome="unknown")
        try:
            expires_at = datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            raise MediaKitRemuxIngressError("INVALID_PROVIDER_EXPIRY", billing_outcome="unknown") from None
    elif isinstance(value, str) and value.strip() == value and value:
        try:
            expires_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise MediaKitRemuxIngressError("INVALID_PROVIDER_EXPIRY", billing_outcome="unknown") from None
    else:
        raise MediaKitRemuxIngressError("INVALID_PROVIDER_EXPIRY", billing_outcome="unknown")
    if expires_at.tzinfo is None:
        raise MediaKitRemuxIngressError("INVALID_PROVIDER_EXPIRY", billing_outcome="unknown")
    expires_at = expires_at.astimezone(UTC)
    ttl_seconds_float = (expires_at - completed_at).total_seconds()
    if not math.isfinite(ttl_seconds_float):
        raise MediaKitRemuxIngressError("INVALID_PROVIDER_EXPIRY", billing_outcome="unknown")
    ttl_seconds = round(ttl_seconds_float)
    if not _MIN_TTL_SECONDS <= ttl_seconds <= _MAX_TTL_SECONDS:
        raise MediaKitRemuxIngressError("PROVIDER_EXPIRY_OUT_OF_RANGE", billing_outcome="unknown")
    return expires_at, ttl_seconds


async def _request_bytes(
    client: httpx.AsyncClient,
    *,
    method: str,
    url: str,
    deadline: float,
    stage: str,
    billing_outcome: Literal["not_submitted", "unknown"],
    headers: Mapping[str, str] | None = None,
    json_body: Mapping[str, Any] | None = None,
    content: httpx.AsyncByteStream | None = None,
) -> tuple[httpx.Response, bytes]:
    remaining = deadline - _monotonic()
    if remaining <= 0:
        raise MediaKitRemuxIngressError("TOTAL_TIMEOUT", billing_outcome=billing_outcome)
    request_timeout = min(float(_REQUEST_TIMEOUT_SECONDS), remaining)
    try:
        async with client.stream(
            method,
            url,
            headers=headers,
            json=json_body,
            content=content,
            timeout=request_timeout,
        ) as response:
            try:
                encoded = await _bounded_response_bytes(response)
            except MediaKitRemuxIngressError as exc:
                raise MediaKitRemuxIngressError(exc.code, billing_outcome=billing_outcome) from exc
    except MediaKitRemuxIngressError:
        raise
    except httpx.TimeoutException:
        raise MediaKitRemuxIngressError(f"{stage}_TIMEOUT", billing_outcome=billing_outcome) from None
    except httpx.HTTPError:
        raise MediaKitRemuxIngressError(f"{stage}_TRANSPORT_UNKNOWN", billing_outcome=billing_outcome) from None
    if not 200 <= response.status_code < 300:
        rejected: Literal["not_submitted", "provider_rejected", "unknown"] = billing_outcome
        if stage == "REMUX_SUBMIT" and response.status_code < 500:
            rejected = "provider_rejected"
        raise MediaKitRemuxIngressError(
            f"{stage}_HTTP_{response.status_code}",
            billing_outcome=rejected,
            http_status=response.status_code,
        )
    return response, encoded


async def _notify_task_observer(
    observer: MediaKitRemuxTaskObserver | None,
    method: str,
    *,
    billing_outcome: Literal["not_submitted", "unknown"],
    **kwargs: Any,
) -> None:
    if observer is None:
        return
    try:
        await getattr(observer, method)(**kwargs)
    except Exception:
        # The observer may be writing encrypted recovery state.  Its raw error
        # must never escape through the provider adapter or include identifiers.
        raise MediaKitRemuxIngressError(
            "PROVIDER_TASK_RECOVERY_FAILED",
            billing_outcome=billing_outcome,
        ) from None


async def _notify_submission_observer(
    observer: MediaKitRemuxTaskObserver | None,
    *,
    submission_record: MediaKitRemuxSubmissionRecord,
    client_token: str,
) -> bool:
    """Send the richer checkpoint when the observer supports it.

    Returning ``False`` preserves compatibility with the already shipped
    observer contract.  A recovery-capable operator must implement the richer
    callback and encrypt the raw file id and client token before returning.
    """

    if observer is None:
        return False
    callback = getattr(observer, "provider_submission_prepared", None)
    if callback is None or not callable(callback):
        return False
    try:
        await callback(
            submission_record=submission_record,
            client_token=client_token,
        )
    except Exception:
        raise MediaKitRemuxIngressError(
            "PROVIDER_TASK_RECOVERY_FAILED",
            billing_outcome="not_submitted",
        ) from None
    return True


def _build_submitted_task_record(
    *,
    task_id: str,
    submit_encoded: bytes,
    submit_payload: Mapping[str, Any],
) -> MediaKitRemuxSubmittedTaskRecord:
    try:
        return MediaKitRemuxSubmittedTaskRecord.model_validate(
            {
                "contract_version": MEDIAKIT_REMUX_SUBMITTED_TASK_CONTRACT_VERSION,
                "provider": "volcengine-mediakit",
                "capability": "managed_https_ingress_remux",
                "task_id": task_id,
                "task_id_sha256": _sha256_text(task_id),
                "provider_response_sha256": hashlib.sha256(submit_encoded).hexdigest(),
                "provider_response_size_bytes": len(submit_encoded),
                "provider_request_id_sha256s": [_sha256_text(item) for item in _request_ids(submit_payload)],
            }
        )
    except ValidationError:
        raise MediaKitRemuxIngressError(
            "INVALID_REMUX_SUBMITTED_TASK_RECORD",
            billing_outcome="unknown",
        ) from None


async def _notify_submitted_task_observer(
    observer: MediaKitRemuxTaskObserver | None,
    *,
    submitted_task_record: MediaKitRemuxSubmittedTaskRecord,
) -> None:
    if observer is not None:
        callback = getattr(observer, "provider_task_submission_confirmed", None)
        if callback is not None and callable(callback):
            try:
                await callback(submitted_task_record=submitted_task_record)
            except Exception:
                raise MediaKitRemuxIngressError(
                    "PROVIDER_TASK_RECOVERY_FAILED",
                    billing_outcome="unknown",
                ) from None
            return
    await _notify_task_observer(
        observer,
        "provider_task_submitted",
        billing_outcome="unknown",
        raw_task_id=submitted_task_record.task_id,
    )


def _build_submission_record(
    *,
    source_sha256: str,
    source_size_bytes: int,
    file_id: str,
    upload_url: str,
    client_token: str,
    response_hashes: list[str],
    response_sizes: list[int],
    provider_request_id_sha256s: list[str],
) -> MediaKitRemuxSubmissionRecord:
    submit_body = _remux_submit_body(file_id=file_id, client_token=client_token)
    try:
        return MediaKitRemuxSubmissionRecord.model_validate(
            {
                "contract_version": MEDIAKIT_REMUX_SUBMISSION_RECOVERY_CONTRACT_VERSION,
                "provider": "volcengine-mediakit",
                "capability": "managed_https_ingress_remux",
                "adapter_version": MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION,
                "endpoint_sha256": _sha256_text(MEDIAKIT_ENDPOINT),
                "source_sha256": source_sha256,
                "source_size_bytes": source_size_bytes,
                "upload_file_id": file_id,
                "upload_file_id_sha256": _sha256_text(file_id),
                "upload_url_sha256": _sha256_text(upload_url),
                "client_token_sha256": _sha256_text(client_token),
                "container_format": _CONTAINER_FORMAT,
                "request_sha256": _remux_request_sha256(
                    source_sha256=source_sha256,
                    source_size_bytes=source_size_bytes,
                    file_id=file_id,
                    client_token=client_token,
                ),
                "submit_body_sha256": _canonical_sha256(submit_body),
                "provider_response_sha256s": list(response_hashes),
                "provider_response_sizes_bytes": list(response_sizes),
                "provider_request_id_sha256s": list(provider_request_id_sha256s),
                "retries": 0,
            }
        )
    except ValidationError:
        raise MediaKitRemuxIngressError(
            "INVALID_REMUX_SUBMISSION_RECORD",
            billing_outcome="not_submitted",
        ) from None


def _strict_task_status(value: Any) -> str:
    if not isinstance(value, str) or value != value.lower() or value.strip() != value:
        raise MediaKitRemuxIngressError("UNKNOWN_REMUX_TASK_STATUS", billing_outcome="unknown")
    if value not in _PENDING_STATUSES and value != "completed" and value not in _TERMINAL_FAILURE_STATUSES:
        raise MediaKitRemuxIngressError("UNKNOWN_REMUX_TASK_STATUS", billing_outcome="unknown")
    return value


async def _poll_mediakit_remux_task(
    *,
    client: httpx.AsyncClient,
    provider_headers: Mapping[str, str],
    deadline: float,
    source: Path,
    source_sha256: str,
    source_size_bytes: int,
    file_id: str,
    upload_url_sha256: str,
    client_token: str,
    task_id: str,
    request_sha256: str,
    response_hashes: list[str],
    response_sizes: list[int],
    provider_request_id_sha256s: list[str],
    task_observer: MediaKitRemuxTaskObserver | None,
    poll_immediately: bool,
) -> MediaKitRemuxHTTPSCandidate:
    endpoint = MEDIAKIT_ENDPOINT.rstrip("/")
    completed_payload: Mapping[str, Any] | None = None
    poll_attempts = 0
    for poll_attempts in range(1, _MAX_POLL_ATTEMPTS + 1):
        remaining = deadline - _monotonic()
        if remaining <= 0:
            raise MediaKitRemuxIngressError("TOTAL_TIMEOUT", billing_outcome="unknown")
        if not (poll_immediately and poll_attempts == 1):
            await asyncio.sleep(min(_POLL_INTERVAL_SECONDS, remaining))
        _, poll_encoded = await _request_bytes(
            client,
            method="GET",
            url=f"{endpoint}{_TASK_PATH_PREFIX}{quote(task_id, safe='')}",
            deadline=deadline,
            stage="REMUX_POLL",
            billing_outcome="unknown",
            headers=provider_headers,
        )
        response_hashes.append(hashlib.sha256(poll_encoded).hexdigest())
        response_sizes.append(len(poll_encoded))
        poll_payload = _decode_mapping(
            poll_encoded,
            code="INVALID_REMUX_POLL_JSON",
            billing_outcome="unknown",
        )
        _require_provider_success(poll_payload, code="REMUX_TASK_REJECTED", billing_outcome="unknown")
        provider_request_id_sha256s.extend(_sha256_text(item) for item in _request_ids(poll_payload))
        observed_task_id = _require_identifier(
            poll_payload.get("task_id"),
            code="MISSING_REMUX_POLL_TASK_ID",
            billing_outcome="unknown",
        )
        if observed_task_id != task_id:
            raise MediaKitRemuxIngressError("REMUX_TASK_ID_MISMATCH", billing_outcome="unknown")
        status = _strict_task_status(poll_payload.get("status"))
        if status == "completed":
            completed_payload = poll_payload
            break
        if status in _TERMINAL_FAILURE_STATUSES:
            terminal_status = status.replace("cancelled", "canceled")
            await _notify_task_observer(
                task_observer,
                "provider_task_terminal",
                billing_outcome="unknown",
                raw_task_id=task_id,
                terminal_status=terminal_status,
                terminal_envelope={
                    "contract_version": "ip-mediakit-remux-provider-terminal-recovery-v2",
                    "provider": "volcengine-mediakit",
                    "capability": "managed_https_ingress_remux",
                    "upload_file_id_sha256": _sha256_text(file_id),
                    "upload_url_sha256": upload_url_sha256,
                    "client_token_sha256": _sha256_text(client_token),
                    "task_id_sha256": _sha256_text(task_id),
                    "provider_terminal_payload_sha256": _canonical_sha256(dict(poll_payload)),
                },
            )
            if await asyncio.to_thread(_sha256_file, source) != source_sha256:
                raise MediaKitRemuxIngressError(
                    "SOURCE_HASH_CHANGED_AFTER_UPLOAD",
                    billing_outcome="unknown",
                )
            raise MediaKitRemuxIngressError("REMUX_TASK_FAILED", billing_outcome="unknown")
        await _notify_task_observer(
            task_observer,
            "provider_task_running",
            billing_outcome="unknown",
            raw_task_id=task_id,
            observed_status=status,
        )
    if completed_payload is None:
        raise MediaKitRemuxIngressError("REMUX_POLL_LIMIT_REACHED", billing_outcome="unknown")

    completed_result = completed_payload.get("result")
    if not isinstance(completed_result, Mapping):
        raise MediaKitRemuxIngressError("MISSING_REMUX_RESULT", billing_outcome="unknown")
    runtime_url = _validate_runtime_https_url(
        completed_result.get("video_url"),
        purpose="send a MediaKit remux derivative to Video Understanding Chat",
        billing_outcome="unknown",
    )
    completed_at = _utcnow().astimezone(UTC)
    expires_at, observed_ttl_seconds = _parse_expires_at(
        completed_payload.get("expires_at"),
        completed_at=completed_at,
    )
    if await asyncio.to_thread(_sha256_file, source) != source_sha256:
        raise MediaKitRemuxIngressError("SOURCE_HASH_CHANGED_AFTER_UPLOAD", billing_outcome="unknown")

    try:
        receipt = MediaKitRemuxIngressReceipt.model_validate(
            {
                "contract_version": MEDIAKIT_REMUX_INGRESS_CONTRACT_VERSION,
                "adapter_version": MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION,
                "provider": "volcengine-mediakit",
                "endpoint_sha256": _sha256_text(MEDIAKIT_ENDPOINT),
                "derived_from_source_sha256": source_sha256,
                "source_size_bytes": source_size_bytes,
                "source_hash_checks": 2,
                "source_hash_unchanged": True,
                "container_format": _CONTAINER_FORMAT,
                "candidate_kind": "provider_remux_derivative",
                "candidate_byte_identity": "not_attested_equal_to_source",
                "provider_content_attestation": "unavailable",
                "upload_file_id_sha256": _sha256_text(file_id),
                "client_token_sha256": _sha256_text(client_token),
                "task_id_sha256": _sha256_text(task_id),
                "provider_request_id_sha256s": provider_request_id_sha256s,
                "runtime_url_sha256": _sha256_text(runtime_url),
                "request_sha256": request_sha256,
                "provider_response_sha256s": response_hashes,
                "provider_response_sizes_bytes": response_sizes,
                "status": "completed",
                "completed_at": completed_at,
                "expires_at": expires_at,
                "observed_ttl_seconds": observed_ttl_seconds,
                "expiry_basis": "provider_reported",
                "poll_attempts": poll_attempts,
                "max_poll_attempts": _MAX_POLL_ATTEMPTS,
                "poll_interval_seconds": _POLL_INTERVAL_SECONDS,
                "response_size_limit_bytes": _MAX_RESPONSE_BYTES,
                "request_timeout_seconds": _REQUEST_TIMEOUT_SECONDS,
                "total_timeout_seconds": _TOTAL_TIMEOUT_SECONDS,
                "retries": 0,
                "billing_status": "provider_amount_unavailable",
            }
        )
    except ValidationError as exc:
        raise MediaKitRemuxIngressError("INVALID_REMUX_RECEIPT", billing_outcome="unknown") from exc
    await _notify_task_observer(
        task_observer,
        "provider_task_terminal",
        billing_outcome="unknown",
        raw_task_id=task_id,
        terminal_status="completed",
        terminal_envelope={
            "contract_version": "ip-mediakit-remux-provider-terminal-recovery-v2",
            "provider": "volcengine-mediakit",
            "capability": "managed_https_ingress_remux",
            "upload_file_id_sha256": _sha256_text(file_id),
            "upload_url_sha256": upload_url_sha256,
            "client_token_sha256": _sha256_text(client_token),
            "task_id_sha256": _sha256_text(task_id),
            "runtime_url_sha256": _sha256_text(runtime_url),
            "provider_terminal_payload_sha256": _canonical_sha256(dict(completed_payload)),
            "remux_receipt_sha256": _canonical_sha256(receipt.model_dump(mode="json")),
            "expires_at": expires_at.isoformat(),
        },
    )
    return MediaKitRemuxHTTPSCandidate(runtime_url=runtime_url, receipt=receipt)


async def create_mediakit_remux_https_candidate(
    *,
    source_path: str | Path,
    expected_source_sha256: str,
    mediakit_api_key: str,
    client_token: str,
    client: httpx.AsyncClient | None = None,
    task_observer: MediaKitRemuxTaskObserver | None = None,
) -> MediaKitRemuxHTTPSCandidate:
    """Create one temporary MP4 remux candidate without automatic retries."""

    source_digest = str(expected_source_sha256 or "").strip().lower()
    if not _SHA256_RE.fullmatch(source_digest):
        raise MediaKitRemuxIngressError("INVALID_SOURCE_SHA256", billing_outcome="not_submitted")
    api_key = str(mediakit_api_key or "").strip()
    if not api_key or "\r" in api_key or "\n" in api_key:
        raise MediaKitRemuxIngressError("PROVIDER_NOT_CONFIGURED", billing_outcome="not_submitted")
    idempotency_token = _require_client_token(client_token)
    try:
        source = Path(source_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise MediaKitRemuxIngressError("SOURCE_NOT_FOUND", billing_outcome="not_submitted") from exc
    if not source.is_file():
        raise MediaKitRemuxIngressError("SOURCE_NOT_FILE", billing_outcome="not_submitted")
    source_size = source.stat().st_size
    if source_size <= 0 or source_size > _MAX_SOURCE_BYTES:
        raise MediaKitRemuxIngressError("SOURCE_SIZE_OUT_OF_RANGE", billing_outcome="not_submitted")
    if await asyncio.to_thread(_sha256_file, source) != source_digest:
        raise MediaKitRemuxIngressError("SOURCE_HASH_MISMATCH", billing_outcome="not_submitted")

    endpoint = MEDIAKIT_ENDPOINT.rstrip("/")
    provider_headers = _provider_headers(api_key)
    deadline = _monotonic() + _TOTAL_TIMEOUT_SECONDS
    response_hashes: list[str] = []
    response_sizes: list[int] = []
    provider_request_id_sha256s: list[str] = []
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(follow_redirects=False, trust_env=False)
    try:
        _, upload_target_encoded = await _request_bytes(
            client,
            method="POST",
            url=f"{endpoint}{_UPLOAD_TARGET_PATH}",
            deadline=deadline,
            stage="UPLOAD_TARGET",
            billing_outcome="not_submitted",
            headers=provider_headers,
            json_body={"tool_name": "remux-video"},
        )
        response_hashes.append(hashlib.sha256(upload_target_encoded).hexdigest())
        response_sizes.append(len(upload_target_encoded))
        upload_payload = _decode_mapping(
            upload_target_encoded,
            code="INVALID_UPLOAD_TARGET_JSON",
            billing_outcome="not_submitted",
        )
        _require_provider_success(upload_payload, code="UPLOAD_TARGET_REJECTED", billing_outcome="not_submitted")
        provider_request_id_sha256s.extend(_sha256_text(item) for item in _request_ids(upload_payload))
        upload_result = upload_payload.get("result")
        if not isinstance(upload_result, Mapping):
            raise MediaKitRemuxIngressError("INVALID_UPLOAD_TARGET", billing_outcome="not_submitted")
        file_id = _require_mediakit_uri(upload_result.get("file_id"))
        upload_url_raw = str(upload_result.get("upload_url") or "").strip()
        if api_key in upload_url_raw:
            raise MediaKitRemuxIngressError("MEDIAKIT_KEY_IN_UPLOAD_TARGET", billing_outcome="not_submitted")
        upload_url = _validate_runtime_https_url(
            upload_url_raw,
            purpose="upload a sealed video to MediaKit",
            billing_outcome="not_submitted",
        )
        upload_method = str(upload_result.get("method") or "PUT").strip().upper()
        if upload_method != "PUT":
            raise MediaKitRemuxIngressError("UNSUPPORTED_UPLOAD_METHOD", billing_outcome="not_submitted")
        upload_headers = _parse_upload_headers(upload_result.get("upload_headers"), api_key=api_key)
        upload_headers.setdefault("Content-Length", str(source_size))

        upload_stream = _PathByteStream(source)
        _, upload_encoded = await _request_bytes(
            client,
            method="PUT",
            url=upload_url,
            deadline=deadline,
            stage="MEDIA_UPLOAD",
            billing_outcome="not_submitted",
            headers=upload_headers,
            content=upload_stream,
        )
        upload_stream.require_expected_bytes(
            expected_sha256=source_digest,
            expected_size_bytes=source_size,
        )
        response_hashes.append(hashlib.sha256(upload_encoded).hexdigest())
        response_sizes.append(len(upload_encoded))

        submission_record = _build_submission_record(
            source_sha256=source_digest,
            source_size_bytes=source_size,
            file_id=file_id,
            upload_url=upload_url,
            client_token=idempotency_token,
            response_hashes=response_hashes,
            response_sizes=response_sizes,
            provider_request_id_sha256s=provider_request_id_sha256s,
        )
        rich_observer_notified = await _notify_submission_observer(
            task_observer,
            submission_record=submission_record,
            client_token=idempotency_token,
        )
        if not rich_observer_notified:
            await _notify_task_observer(
                task_observer,
                "before_provider_submit",
                billing_outcome="not_submitted",
                upload_file_id=file_id,
                client_token=idempotency_token,
            )
        submit_body = _remux_submit_body(file_id=file_id, client_token=idempotency_token)
        _, submit_encoded = await _request_bytes(
            client,
            method="POST",
            url=f"{endpoint}{_REMUX_PATH}",
            deadline=deadline,
            stage="REMUX_SUBMIT",
            billing_outcome="unknown",
            headers=provider_headers,
            json_body=submit_body,
        )
        response_hashes.append(hashlib.sha256(submit_encoded).hexdigest())
        response_sizes.append(len(submit_encoded))
        submit_payload = _decode_mapping(
            submit_encoded,
            code="INVALID_REMUX_SUBMIT_JSON",
            billing_outcome="unknown",
        )
        _require_provider_success(submit_payload, code="REMUX_SUBMIT_REJECTED", billing_outcome="unknown")
        provider_request_id_sha256s.extend(_sha256_text(item) for item in _request_ids(submit_payload))
        task_id = _require_identifier(
            submit_payload.get("task_id"),
            code="MISSING_REMUX_TASK_ID",
            billing_outcome="unknown",
        )
        submitted_task_record = _build_submitted_task_record(
            task_id=task_id,
            submit_encoded=submit_encoded,
            submit_payload=submit_payload,
        )
        await _notify_submitted_task_observer(
            task_observer,
            submitted_task_record=submitted_task_record,
        )

        return await _poll_mediakit_remux_task(
            client=client,
            provider_headers=provider_headers,
            deadline=deadline,
            source=source,
            source_sha256=source_digest,
            source_size_bytes=source_size,
            file_id=file_id,
            upload_url_sha256=submission_record.upload_url_sha256,
            client_token=idempotency_token,
            task_id=task_id,
            request_sha256=submission_record.request_sha256,
            response_hashes=response_hashes,
            response_sizes=response_sizes,
            provider_request_id_sha256s=provider_request_id_sha256s,
            task_observer=task_observer,
            poll_immediately=False,
        )
    finally:
        if owns_client:
            await client.aclose()


async def recover_mediakit_remux_https_candidate(
    *,
    source_path: str | Path,
    expected_source_sha256: str,
    mediakit_api_key: str,
    recovery_request: MediaKitRemuxRecoveryRequest | Mapping[str, Any],
    client: httpx.AsyncClient | None = None,
    task_observer: MediaKitRemuxTaskObserver | None = None,
) -> MediaKitRemuxHTTPSCandidate:
    """Resume one remux without obtaining an upload URL or uploading bytes.

    ``replay_submission_once`` performs exactly one idempotent POST with the
    previously sealed MediaKit file id and client token.  The caller must own
    the durable one-shot replay claim. ``query_existing_task`` performs only
    task GETs starting from the already persisted task id.
    """

    try:
        request = MediaKitRemuxRecoveryRequest.model_validate(recovery_request)
    except ValidationError:
        raise MediaKitRemuxIngressError(
            "INVALID_REMUX_RECOVERY_REQUEST",
            billing_outcome="unknown",
        ) from None
    source_digest = str(expected_source_sha256 or "").strip().lower()
    if not _SHA256_RE.fullmatch(source_digest):
        raise MediaKitRemuxIngressError("INVALID_SOURCE_SHA256", billing_outcome="not_submitted")
    if request.submission.source_sha256 != source_digest:
        raise MediaKitRemuxIngressError("RECOVERY_SOURCE_BINDING_MISMATCH", billing_outcome="unknown")
    api_key = str(mediakit_api_key or "").strip()
    if not api_key or "\r" in api_key or "\n" in api_key:
        raise MediaKitRemuxIngressError("PROVIDER_NOT_CONFIGURED", billing_outcome="not_submitted")
    try:
        source = Path(source_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise MediaKitRemuxIngressError("SOURCE_NOT_FOUND", billing_outcome="not_submitted") from exc
    if not source.is_file():
        raise MediaKitRemuxIngressError("SOURCE_NOT_FILE", billing_outcome="not_submitted")
    source_size = source.stat().st_size
    if source_size != request.submission.source_size_bytes:
        raise MediaKitRemuxIngressError("RECOVERY_SOURCE_SIZE_MISMATCH", billing_outcome="unknown")
    if await asyncio.to_thread(_sha256_file, source) != source_digest:
        raise MediaKitRemuxIngressError("SOURCE_HASH_MISMATCH", billing_outcome="unknown")

    provider_headers = _provider_headers(api_key)
    endpoint = MEDIAKIT_ENDPOINT.rstrip("/")
    deadline = _monotonic() + _TOTAL_TIMEOUT_SECONDS
    response_hashes = list(request.submission.provider_response_sha256s)
    response_sizes = list(request.submission.provider_response_sizes_bytes)
    provider_request_id_sha256s = list(request.submission.provider_request_id_sha256s)
    task_id: str
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(follow_redirects=False, trust_env=False)
    try:
        if request.action == "replay_submission_once":
            submit_body = _remux_submit_body(
                file_id=request.submission.upload_file_id,
                client_token=request.client_token,
            )
            _, submit_encoded = await _request_bytes(
                client,
                method="POST",
                url=f"{endpoint}{_REMUX_PATH}",
                deadline=deadline,
                stage="REMUX_SUBMIT",
                billing_outcome="unknown",
                headers=provider_headers,
                json_body=submit_body,
            )
            response_hashes.append(hashlib.sha256(submit_encoded).hexdigest())
            response_sizes.append(len(submit_encoded))
            submit_payload = _decode_mapping(
                submit_encoded,
                code="INVALID_REMUX_SUBMIT_JSON",
                billing_outcome="unknown",
            )
            _require_provider_success(
                submit_payload,
                code="REMUX_SUBMIT_REJECTED",
                billing_outcome="unknown",
            )
            provider_request_id_sha256s.extend(_sha256_text(item) for item in _request_ids(submit_payload))
            task_id = _require_identifier(
                submit_payload.get("task_id"),
                code="MISSING_REMUX_TASK_ID",
                billing_outcome="unknown",
            )
            submitted_task_record = _build_submitted_task_record(
                task_id=task_id,
                submit_encoded=submit_encoded,
                submit_payload=submit_payload,
            )
            await _notify_submitted_task_observer(
                task_observer,
                submitted_task_record=submitted_task_record,
            )
            poll_immediately = False
        else:
            submitted_task_record = request.submitted_task
            if submitted_task_record is None:  # covered by the strict request model
                raise MediaKitRemuxIngressError(
                    "INVALID_REMUX_RECOVERY_REQUEST",
                    billing_outcome="unknown",
                )
            task_id = submitted_task_record.task_id
            response_hashes.append(submitted_task_record.provider_response_sha256)
            response_sizes.append(submitted_task_record.provider_response_size_bytes)
            provider_request_id_sha256s.extend(submitted_task_record.provider_request_id_sha256s)
            poll_immediately = True

        return await _poll_mediakit_remux_task(
            client=client,
            provider_headers=provider_headers,
            deadline=deadline,
            source=source,
            source_sha256=source_digest,
            source_size_bytes=source_size,
            file_id=request.submission.upload_file_id,
            upload_url_sha256=request.submission.upload_url_sha256,
            client_token=request.client_token,
            task_id=task_id,
            request_sha256=request.submission.request_sha256,
            response_hashes=response_hashes,
            response_sizes=response_sizes,
            provider_request_id_sha256s=provider_request_id_sha256s,
            task_observer=task_observer,
            poll_immediately=poll_immediately,
        )
    finally:
        if owns_client:
            await client.aclose()


__all__ = [
    "MEDIAKIT_ENDPOINT",
    "MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION",
    "MEDIAKIT_REMUX_INGRESS_CONTRACT_VERSION",
    "MEDIAKIT_REMUX_RECOVERY_REQUEST_CONTRACT_VERSION",
    "MEDIAKIT_REMUX_SUBMISSION_RECOVERY_CONTRACT_VERSION",
    "MEDIAKIT_REMUX_SUBMITTED_TASK_CONTRACT_VERSION",
    "MediaKitRemuxHTTPSCandidate",
    "MediaKitRemuxIngressError",
    "MediaKitRemuxIngressReceipt",
    "MediaKitRemuxRecoveryRequest",
    "MediaKitRemuxSubmissionObserver",
    "MediaKitRemuxSubmissionRecord",
    "MediaKitRemuxSubmittedTaskRecord",
    "MediaKitRemuxTaskObserver",
    "create_mediakit_remux_https_candidate",
    "recover_mediakit_remux_https_candidate",
    "validate_mediakit_runtime_https_url",
]
