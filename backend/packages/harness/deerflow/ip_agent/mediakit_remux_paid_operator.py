"""Operator-only paid execution for the MediaKit managed-HTTPS remux bridge.

This module is deliberately not an Agent tool, MCP server, route, or Chat
orchestrator.  It consumes one already approved/reserved/admitted paid-call
scope for exactly one remux capability, persists provider recovery before and
after submission, and returns a runtime-only URL.  Video Understanding Chat is
a different paid capability and is never authorized or invoked here.

Revision 0026 persists the exact encrypted submission before the paid POST.
An interrupted ``submitting`` task can therefore claim one idempotent replay;
``submitted``/``running`` tasks and completed terminal tasks use GET-only
recovery.  No recovery path obtains another upload URL or uploads bytes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deerflow.ip_agent.mediakit_remux_ingress import (
    MEDIAKIT_ENDPOINT,
    MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION,
    MediaKitRemuxHTTPSCandidate,
    MediaKitRemuxIngressError,
    MediaKitRemuxIngressReceipt,
    MediaKitRemuxRecoveryRequest,
    MediaKitRemuxSubmissionRecord,
    MediaKitRemuxSubmittedTaskRecord,
    MediaKitRemuxTaskObserver,
    create_mediakit_remux_https_candidate,
    recover_mediakit_remux_https_candidate,
)

MEDIAKIT_REMUX_PAID_CAPABILITY = "managed_https_ingress_remux"
MEDIAKIT_REMUX_PAID_PROVIDER = "volcengine-mediakit"
MEDIAKIT_REMUX_PAID_SERVER = "ip-agent-operator"
MEDIAKIT_REMUX_PAID_TOOL = "managed_https_ingress_remux"
MEDIAKIT_REMUX_PAID_SKU = "remux-video"
MEDIAKIT_REMUX_PAID_REQUEST_CONTRACT_VERSION = "ip-mediakit-remux-paid-request-v1"
MEDIAKIT_REMUX_PAID_EXECUTION_CONTRACT_VERSION = "ip-mediakit-remux-paid-execution-v1"
MEDIAKIT_REMUX_TERMINAL_RECOVERY_CONTRACT_VERSION = "ip-mediakit-remux-provider-terminal-recovery-v2"
MEDIAKIT_REMUX_OPERATOR_CAPPED_POLICY_VERSION = "evidence-managed-remux-operator-cap-v1"

_HEX64 = frozenset("0123456789abcdef")
_CLIENT_TOKEN_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MediaKitRemuxPaidExecutionReceipt(_StrictModel):
    """Secret-free public accounting result for one remux authorization."""

    contract_version: Literal["ip-mediakit-remux-paid-execution-v1"]
    provider: Literal["volcengine-mediakit"]
    capability: Literal["managed_https_ingress_remux"]
    paid_call_scope_id: str = Field(min_length=1, max_length=64)
    paid_call_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_run_id: str = Field(min_length=1, max_length=64)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    client_token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_task_id_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_url_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    remux_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_terminal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_task_status: Literal["terminal"]
    provider_terminal_status: Literal["completed"]
    paid_call_status: Literal["reconciliation_required"]
    billing_status: Literal["provider_amount_unavailable"]
    recovered_from_encrypted_state: bool
    chat_authorization: Literal["required_separate_paid_call"]
    chat_capability: Literal["video_understanding_chat"]

    @model_validator(mode="after")
    def validate_hash_bindings(self) -> MediaKitRemuxPaidExecutionReceipt:
        if self.capability == self.chat_capability:
            raise ValueError("remux and Chat capabilities must remain distinct")
        return self


@dataclass(frozen=True)
class MediaKitRemuxPaidExecutionResult:
    """In-process remux URL plus receipts safe for ordinary serialization."""

    runtime_url: str = field(repr=False)
    remux_receipt: MediaKitRemuxIngressReceipt
    paid_execution_receipt: MediaKitRemuxPaidExecutionReceipt


class MediaKitRemuxPaidOperatorError(RuntimeError):
    """Bounded operator failure which never includes provider identifiers."""

    def __init__(self, code: str, *, reconciliation_required: bool) -> None:
        self.code = str(code or "PAID_REMUX_FAILED")[:80]
        self.reconciliation_required = reconciliation_required
        super().__init__(self.code)


class MediaKitRemuxPaidCallRepository(Protocol):
    async def get(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any] | None: ...

    async def begin_provider_task_submission(self, scope_id: str, **kwargs: Any) -> dict[str, Any] | None: ...

    async def claim_provider_task_submission_replay(self, scope_id: str, **kwargs: Any) -> dict[str, Any] | None: ...

    async def record_provider_task_submission_confirmed(self, scope_id: str, **kwargs: Any) -> dict[str, Any] | None: ...

    async def record_provider_task_submitted(self, scope_id: str, **kwargs: Any) -> dict[str, Any] | None: ...

    async def record_provider_task_running(self, scope_id: str, **kwargs: Any) -> dict[str, Any] | None: ...

    async def record_provider_task_terminal(self, scope_id: str, **kwargs: Any) -> dict[str, Any] | None: ...

    async def get_recoverable_provider_task(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any] | None: ...

    async def settle(self, scope_id: str, **kwargs: Any) -> dict[str, Any] | None: ...


MediaKitRemuxIngressRunner = Callable[..., Awaitable[MediaKitRemuxHTTPSCandidate]]
MediaKitRemuxRecoveryRunner = Callable[..., Awaitable[MediaKitRemuxHTTPSCandidate]]


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _required(value: Any, *, field_name: str, limit: int) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized or len(normalized) > limit:
        raise MediaKitRemuxPaidOperatorError(
            f"INVALID_{field_name.upper()}",
            reconciliation_required=False,
        )
    return normalized


def _sha256(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64 or any(character not in _HEX64 for character in normalized):
        raise MediaKitRemuxPaidOperatorError(
            f"INVALID_{field_name.upper()}",
            reconciliation_required=False,
        )
    return normalized


def _client_token(value: Any) -> str:
    if not isinstance(value, str) or not _CLIENT_TOKEN_RE.fullmatch(value):
        raise MediaKitRemuxPaidOperatorError(
            "INVALID_CLIENT_TOKEN",
            reconciliation_required=False,
        )
    return value


def build_mediakit_remux_paid_provider_request_sha256(
    *,
    source_sha256: str,
    client_token: str,
) -> str:
    """Bind approval to the exact source, adapter and deterministic token."""

    source_digest = _sha256(source_sha256, field_name="source_sha256")
    token = _client_token(client_token)
    return _canonical_sha256(
        {
            "contract_version": MEDIAKIT_REMUX_PAID_REQUEST_CONTRACT_VERSION,
            "provider": MEDIAKIT_REMUX_PAID_PROVIDER,
            "capability": MEDIAKIT_REMUX_PAID_CAPABILITY,
            "adapter_version": MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION,
            "endpoint_sha256": _sha256_text(MEDIAKIT_ENDPOINT),
            "source_sha256": source_digest,
            "container_format": "MP4",
            "client_token_sha256": _sha256_text(token),
            "retries": 0,
        }
    )


def _event_key(prefix: str, *values: str) -> str:
    return f"{prefix}:{_canonical_sha256(list(values))[:24]}"


def _assert_static_scope_binding(
    scope: Mapping[str, Any],
    *,
    owner_user_id: str,
    expected_request_digest: str,
    execution_run_id: str,
    source_sha256: str,
) -> None:
    checks = {
        "owner_user_id": owner_user_id,
        "request_digest": expected_request_digest,
        "execution_run_id": execution_run_id,
        "server_name": MEDIAKIT_REMUX_PAID_SERVER,
        "tool_name": MEDIAKIT_REMUX_PAID_TOOL,
        "provider": MEDIAKIT_REMUX_PAID_PROVIDER,
        "capability": MEDIAKIT_REMUX_PAID_CAPABILITY,
        "model": MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION,
        "sku": MEDIAKIT_REMUX_PAID_SKU,
        "source_sha256": source_sha256,
        "price_status": "operator_capped",
        "policy_version": MEDIAKIT_REMUX_OPERATOR_CAPPED_POLICY_VERSION,
    }
    if any(scope.get(field_name) != expected for field_name, expected in checks.items()):
        raise MediaKitRemuxPaidOperatorError(
            "PAID_CALL_BINDING_MISMATCH",
            reconciliation_required=False,
        )


def _assert_scope_binding(
    scope: Mapping[str, Any],
    *,
    owner_user_id: str,
    expected_request_digest: str,
    execution_run_id: str,
    source_sha256: str,
    client_token: str,
    allow_reconciled_terminal: bool = False,
) -> None:
    _assert_static_scope_binding(
        scope,
        owner_user_id=owner_user_id,
        expected_request_digest=expected_request_digest,
        execution_run_id=execution_run_id,
        source_sha256=source_sha256,
    )
    expected_provider_request = build_mediakit_remux_paid_provider_request_sha256(
        source_sha256=source_sha256,
        client_token=client_token,
    )
    if scope.get("provider_request_sha256") != expected_provider_request:
        raise MediaKitRemuxPaidOperatorError(
            "PAID_CALL_BINDING_MISMATCH",
            reconciliation_required=False,
        )
    maximum = scope.get("maximum_amount_micros")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
        raise MediaKitRemuxPaidOperatorError(
            "PAID_CALL_OPERATOR_CAP_REQUIRED",
            reconciliation_required=False,
        )
    if scope.get("provider_input_attested") is not False or scope.get("evidence_coverage") != "partial" or scope.get("warning_code") != "provider_content_hash_unattested":
        raise MediaKitRemuxPaidOperatorError(
            "UNATTESTED_PROVIDER_INPUT_BOUNDARY_REQUIRED",
            reconciliation_required=False,
        )
    accepted_statuses = {"admitted"}
    if allow_reconciled_terminal:
        accepted_statuses.add("reconciliation_required")
    if scope.get("status") not in accepted_statuses:
        raise MediaKitRemuxPaidOperatorError(
            "PAID_CALL_NOT_ADMITTED",
            reconciliation_required=scope.get("status") == "reconciliation_required",
        )


def _validated_terminal_projection(
    *,
    terminal_status: str,
    terminal_envelope: Mapping[str, Any],
    upload_file_id_sha256: str,
    upload_url_sha256: str,
    client_token_sha256: str,
    task_id_sha256: str,
) -> dict[str, Any]:
    if not isinstance(terminal_status, str):
        raise ValueError("provider terminal status must be normalized")
    normalized_terminal = terminal_status.strip().lower()
    if terminal_status != normalized_terminal or normalized_terminal not in {
        "completed",
        "failed",
        "canceled",
    }:
        raise ValueError("provider terminal status must be normalized")
    if not isinstance(terminal_envelope, Mapping):
        raise ValueError("provider terminal recovery must be an object")
    if (
        terminal_envelope.get("contract_version") != MEDIAKIT_REMUX_TERMINAL_RECOVERY_CONTRACT_VERSION
        or terminal_envelope.get("provider") != MEDIAKIT_REMUX_PAID_PROVIDER
        or terminal_envelope.get("capability") != MEDIAKIT_REMUX_PAID_CAPABILITY
        or terminal_envelope.get("upload_file_id_sha256") != upload_file_id_sha256
        or terminal_envelope.get("upload_url_sha256") != upload_url_sha256
        or terminal_envelope.get("client_token_sha256") != client_token_sha256
        or terminal_envelope.get("task_id_sha256") != task_id_sha256
    ):
        raise ValueError("provider terminal recovery binding changed")
    base_fields = {
        "contract_version",
        "provider",
        "capability",
        "upload_file_id_sha256",
        "upload_url_sha256",
        "client_token_sha256",
        "task_id_sha256",
        "provider_terminal_payload_sha256",
    }
    completed_fields = base_fields | {
        "runtime_url_sha256",
        "remux_receipt_sha256",
        "expires_at",
    }
    expected_fields = completed_fields if normalized_terminal == "completed" else base_fields
    if set(terminal_envelope) != expected_fields:
        raise ValueError("provider terminal recovery fields are invalid")
    for digest_field in expected_fields - {
        "contract_version",
        "provider",
        "capability",
        "expires_at",
    }:
        digest = terminal_envelope.get(digest_field)
        if not isinstance(digest, str) or len(digest) != 64 or any(character not in _HEX64 for character in digest):
            raise ValueError("provider terminal recovery fields are invalid")
    projection = {field_name: terminal_envelope[field_name] for field_name in expected_fields}
    if normalized_terminal == "completed":
        expires_raw = projection.get("expires_at")
        if not isinstance(expires_raw, str) or not expires_raw:
            raise ValueError("provider terminal expiry is missing")
        try:
            expires_at = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("provider terminal expiry is invalid") from exc
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("provider terminal expiry must be timezone-aware")
        projection["expires_at"] = expires_at.astimezone(UTC).isoformat()
    return projection


class _PaidRecoveryObserver(MediaKitRemuxTaskObserver):
    def __init__(
        self,
        *,
        repository: MediaKitRemuxPaidCallRepository,
        scope_id: str,
        owner_user_id: str,
        request_digest: str,
        execution_run_id: str,
        source_sha256: str,
        client_token: str,
        submission_record: MediaKitRemuxSubmissionRecord | None = None,
        submitted_task_record: MediaKitRemuxSubmittedTaskRecord | None = None,
        persisted_terminal_status: str | None = None,
        persisted_terminal_projection: Mapping[str, Any] | None = None,
    ) -> None:
        self._repository = repository
        self._scope_id = scope_id
        self._owner_user_id = owner_user_id
        self._request_digest = request_digest
        self._execution_run_id = execution_run_id
        self._source_sha256 = source_sha256
        self._client_token = client_token
        self._client_token_sha256 = _sha256_text(client_token)
        self._submission_record = submission_record
        self._submitted_task_record = submitted_task_record
        self._upload_file_id_sha256 = submission_record.upload_file_id_sha256 if submission_record is not None else None
        self._upload_url_sha256 = submission_record.upload_url_sha256 if submission_record is not None else None
        self._task_id_sha256 = submitted_task_record.task_id_sha256 if submitted_task_record is not None else None
        self._persisted_terminal_status = persisted_terminal_status
        self._persisted_terminal_projection = dict(persisted_terminal_projection) if persisted_terminal_projection is not None else None
        self.submission_started = False
        self.recorded_terminal_projection: dict[str, Any] | None = None

        if self._persisted_terminal_projection is not None:
            if self._persisted_terminal_status is None or self._upload_file_id_sha256 is None or self._upload_url_sha256 is None or self._task_id_sha256 is None:
                raise ValueError("persisted provider terminal recovery is incomplete")
            self._persisted_terminal_projection = _validated_terminal_projection(
                terminal_status=self._persisted_terminal_status,
                terminal_envelope=self._persisted_terminal_projection,
                upload_file_id_sha256=self._upload_file_id_sha256,
                upload_url_sha256=self._upload_url_sha256,
                client_token_sha256=self._client_token_sha256,
                task_id_sha256=self._task_id_sha256,
            )

    @property
    def submission_record(self) -> MediaKitRemuxSubmissionRecord | None:
        return self._submission_record

    @property
    def submitted_task_record(self) -> MediaKitRemuxSubmittedTaskRecord | None:
        return self._submitted_task_record

    async def before_provider_submit(
        self,
        *,
        upload_file_id: str,
        client_token: str,
    ) -> None:
        del upload_file_id, client_token
        raise ValueError("exact provider submission recovery is required")

    async def provider_submission_prepared(
        self,
        *,
        submission_record: MediaKitRemuxSubmissionRecord,
        client_token: str,
    ) -> None:
        record = MediaKitRemuxSubmissionRecord.model_validate(submission_record.model_dump(mode="json"))
        if _sha256_text(client_token) != self._client_token_sha256 or record.client_token_sha256 != self._client_token_sha256 or record.source_sha256 != self._source_sha256:
            raise ValueError("provider submission recovery binding changed")
        submission_digest = _canonical_sha256(record.model_dump(mode="json"))
        result = await self._repository.begin_provider_task_submission(
            self._scope_id,
            owner_user_id=self._owner_user_id,
            event_key=_event_key("remux-provider-submitting", submission_digest),
            expected_request_digest=self._request_digest,
            execution_run_id=self._execution_run_id,
            capability=MEDIAKIT_REMUX_PAID_CAPABILITY,
            source_sha256=self._source_sha256,
            client_token=self._client_token,
            submission_envelope=record.model_dump(mode="json"),
        )
        if result is None or result.get("provider_task_status") != "submitting" or result.get("provider_client_token_sha256") != self._client_token_sha256 or result.get("provider_submission_sha256") != submission_digest:
            raise ValueError("paid-call scope disappeared")
        self._submission_record = record
        self._upload_file_id_sha256 = record.upload_file_id_sha256
        self._upload_url_sha256 = record.upload_url_sha256
        self.submission_started = True

    async def provider_task_submitted(self, *, raw_task_id: str) -> None:
        del raw_task_id
        raise ValueError("exact submitted-task recovery is required")

    async def provider_task_submission_confirmed(
        self,
        *,
        submitted_task_record: MediaKitRemuxSubmittedTaskRecord,
    ) -> None:
        record = MediaKitRemuxSubmittedTaskRecord.model_validate(submitted_task_record.model_dump(mode="json"))
        result = await self._repository.record_provider_task_submission_confirmed(
            self._scope_id,
            owner_user_id=self._owner_user_id,
            event_key=_event_key(
                "remux-provider-submitted",
                record.task_id_sha256,
                record.provider_response_sha256,
            ),
            expected_request_digest=self._request_digest,
            execution_run_id=self._execution_run_id,
            submitted_task_record=record.model_dump(mode="json"),
        )
        if result is None or result.get("provider_task_status") != "submitted" or result.get("provider_task_id_sha256") != record.task_id_sha256:
            raise ValueError("paid-call scope disappeared")
        self._submitted_task_record = record
        self._task_id_sha256 = record.task_id_sha256

    async def provider_task_running(
        self,
        *,
        raw_task_id: str,
        observed_status: str,
    ) -> None:
        task_digest = _sha256_text(_required(raw_task_id, field_name="raw_task_id", limit=1024))
        if self._task_id_sha256 not in {None, task_digest}:
            raise ValueError("provider task binding changed")
        if self._persisted_terminal_projection is not None:
            raise ValueError("completed provider task cannot regress to running")
        status = _required(observed_status, field_name="observed_status", limit=32).lower()
        result = await self._repository.record_provider_task_running(
            self._scope_id,
            owner_user_id=self._owner_user_id,
            event_key=_event_key("remux-provider-running", task_digest, status),
            expected_request_digest=self._request_digest,
            execution_run_id=self._execution_run_id,
            raw_task_id=raw_task_id,
            observed_provider_status=status,
        )
        if result is None:
            raise ValueError("paid-call scope disappeared")
        self._task_id_sha256 = task_digest

    async def provider_task_terminal(
        self,
        *,
        raw_task_id: str,
        terminal_status: str,
        terminal_envelope: dict[str, Any],
    ) -> None:
        task_id = _required(raw_task_id, field_name="raw_task_id", limit=1024)
        task_digest = _sha256_text(task_id)
        if self._task_id_sha256 not in {None, task_digest}:
            raise ValueError("provider task binding changed")
        if self._upload_file_id_sha256 is None or self._upload_url_sha256 is None:
            raise ValueError("provider submission recovery was not prepared")
        projection = _validated_terminal_projection(
            terminal_status=terminal_status,
            terminal_envelope=terminal_envelope,
            upload_file_id_sha256=self._upload_file_id_sha256,
            upload_url_sha256=self._upload_url_sha256,
            client_token_sha256=self._client_token_sha256,
            task_id_sha256=task_digest,
        )
        normalized_terminal = terminal_status
        if self.recorded_terminal_projection is not None:
            if self.recorded_terminal_projection != projection:
                raise ValueError("provider terminal recovery changed within one observation")
            return
        if self._persisted_terminal_projection is not None:
            if self._persisted_terminal_status != "completed" or normalized_terminal != "completed":
                raise ValueError("persisted provider terminal status changed")
            # A completed-task GET may rotate its signed URL and expiry.  The
            # immutable terminal remains stored; this observation is accepted
            # only after all static source/file/token/task bindings match.
            self.recorded_terminal_projection = projection
            return
        result = await self._repository.record_provider_task_terminal(
            self._scope_id,
            owner_user_id=self._owner_user_id,
            event_key=_event_key(
                "remux-provider-terminal",
                task_digest,
                normalized_terminal,
                _canonical_sha256(projection),
            ),
            expected_request_digest=self._request_digest,
            execution_run_id=self._execution_run_id,
            raw_task_id=task_id,
            terminal_status=normalized_terminal,
            terminal_envelope=projection,
        )
        if result is None:
            raise ValueError("paid-call scope disappeared")
        if result.get("provider_task_status") != "terminal" or result.get("provider_terminal_status") != normalized_terminal or result.get("provider_terminal_sha256") != _canonical_sha256(projection):
            raise ValueError("provider terminal recovery was not recorded exactly")
        self._task_id_sha256 = task_digest
        self.recorded_terminal_projection = dict(projection)


async def _recovery_for_scope(
    repository: MediaKitRemuxPaidCallRepository,
    *,
    owner_user_id: str,
    scope_id: str,
) -> Mapping[str, Any] | None:
    return await repository.get_recoverable_provider_task(
        scope_id,
        owner_user_id=owner_user_id,
    )


async def _settle_provider_amount_unknown(
    repository: MediaKitRemuxPaidCallRepository,
    *,
    scope: Mapping[str, Any],
    owner_user_id: str,
    execution_run_id: str,
    provider_receipt_digest: str,
) -> Mapping[str, Any]:
    try:
        result = await repository.settle(
            str(scope["id"]),
            owner_user_id=owner_user_id,
            event_key=_event_key("remux-provider-amount-unknown", provider_receipt_digest),
            expected_request_digest=str(scope["request_digest"]),
            execution_run_id=execution_run_id,
            actual_amount_micros=None,
            provider_receipt_digest=provider_receipt_digest,
        )
    except Exception:
        raise MediaKitRemuxPaidOperatorError(
            "PAID_CALL_RECONCILIATION_NOT_RECORDED",
            reconciliation_required=True,
        ) from None
    if result is None or result.get("status") != "reconciliation_required":
        raise MediaKitRemuxPaidOperatorError(
            "PAID_CALL_RECONCILIATION_NOT_RECORDED",
            reconciliation_required=True,
        )
    return result


async def _record_failed_execution_accounting(
    repository: MediaKitRemuxPaidCallRepository,
    *,
    scope: Mapping[str, Any],
    owner_user_id: str,
    execution_run_id: str,
    error: MediaKitRemuxIngressError,
) -> bool:
    try:
        current = await repository.get(str(scope["id"]), owner_user_id=owner_user_id)
    except Exception:
        raise MediaKitRemuxPaidOperatorError(
            "PAID_CALL_FAILURE_ACCOUNTING_NOT_RECORDED",
            reconciliation_required=True,
        ) from None
    if current is None:
        raise MediaKitRemuxPaidOperatorError(
            "PAID_CALL_SCOPE_DISAPPEARED",
            reconciliation_required=True,
        )
    provider_task_status = current.get("provider_task_status")
    if provider_task_status in {"submitting", "submitted", "running"}:
        # The exact encrypted recovery state is still usable.  A transient
        # provider or process interruption must not consume the admission or
        # turn a retryable GET into manual reconciliation.
        return False
    provider_state_started = provider_task_status is not None
    proof = _canonical_sha256(
        {
            "contract_version": "ip-mediakit-remux-paid-failure-v1",
            "scope_id": scope["id"],
            "request_digest": scope["request_digest"],
            "execution_run_id": execution_run_id,
            "error_code": error.code,
            "billing_outcome": error.billing_outcome,
            "provider_task_status": current.get("provider_task_status"),
        }
    )
    if not provider_state_started and error.billing_outcome == "not_submitted":
        try:
            result = await repository.settle(
                str(scope["id"]),
                owner_user_id=owner_user_id,
                event_key=_event_key("remux-not-submitted-zero", proof),
                expected_request_digest=str(scope["request_digest"]),
                execution_run_id=execution_run_id,
                actual_amount_micros=0,
                provider_receipt_digest=proof,
            )
        except Exception:
            raise MediaKitRemuxPaidOperatorError(
                "PAID_CALL_FAILURE_ACCOUNTING_NOT_RECORDED",
                reconciliation_required=True,
            ) from None
        if result is None or result.get("status") != "settled":
            raise MediaKitRemuxPaidOperatorError(
                "PAID_CALL_ZERO_SETTLEMENT_NOT_RECORDED",
                reconciliation_required=True,
            )
        return False
    await _settle_provider_amount_unknown(
        repository,
        scope=scope,
        owner_user_id=owner_user_id,
        execution_run_id=execution_run_id,
        provider_receipt_digest=proof,
    )
    return True


async def _record_unknown_internal_failure(
    repository: MediaKitRemuxPaidCallRepository,
    *,
    scope: Mapping[str, Any],
    owner_user_id: str,
    execution_run_id: str,
    error_code: str,
) -> bool:
    try:
        current = await repository.get(str(scope["id"]), owner_user_id=owner_user_id)
    except Exception:
        raise MediaKitRemuxPaidOperatorError(
            "PAID_CALL_FAILURE_ACCOUNTING_NOT_RECORDED",
            reconciliation_required=True,
        ) from None
    if current is None:
        raise MediaKitRemuxPaidOperatorError(
            "PAID_CALL_SCOPE_DISAPPEARED",
            reconciliation_required=True,
        )
    if current.get("provider_task_status") in {"submitting", "submitted", "running"}:
        return False
    proof = _canonical_sha256(
        {
            "contract_version": "ip-mediakit-remux-paid-internal-failure-v1",
            "scope_id": scope["id"],
            "request_digest": scope["request_digest"],
            "execution_run_id": execution_run_id,
            "error_code": error_code,
        }
    )
    await _settle_provider_amount_unknown(
        repository,
        scope=scope,
        owner_user_id=owner_user_id,
        execution_run_id=execution_run_id,
        provider_receipt_digest=proof,
    )
    return True


@dataclass(frozen=True)
class _RecoveryMaterial:
    provider_task_status: Literal["submitting", "submitted", "running", "terminal"]
    client_token: str = field(repr=False)
    submission: MediaKitRemuxSubmissionRecord
    submitted_task: MediaKitRemuxSubmittedTaskRecord | None = None
    terminal_status: Literal["completed", "failed", "canceled"] | None = None
    terminal_projection: dict[str, Any] | None = None


def _load_recovery_material(
    *,
    scope: Mapping[str, Any],
    recovery: Mapping[str, Any],
    supplied_token: str | None,
    source_sha256: str,
) -> _RecoveryMaterial:
    status = recovery.get("provider_task_status")
    if status not in {"submitting", "submitted", "running", "terminal"}:
        raise ValueError("provider task recovery status is invalid")
    if scope.get("provider_task_status") != status:
        raise ValueError("provider task recovery status binding changed")
    token = _client_token(recovery.get("client_token"))
    if supplied_token is not None and _sha256_text(supplied_token) != _sha256_text(token):
        raise ValueError("provider recovery client token changed")
    submission = MediaKitRemuxSubmissionRecord.model_validate(recovery.get("submission_envelope"))
    submission_digest = _canonical_sha256(submission.model_dump(mode="json"))
    if (
        submission.source_sha256 != source_sha256
        or submission.client_token_sha256 != _sha256_text(token)
        or recovery.get("provider_client_token_sha256") != _sha256_text(token)
        or recovery.get("provider_submission_sha256") != submission_digest
        or scope.get("provider_client_token_sha256") != _sha256_text(token)
        or scope.get("provider_submission_sha256") != submission_digest
    ):
        raise ValueError("provider submission recovery binding changed")

    submitted_task: MediaKitRemuxSubmittedTaskRecord | None = None
    submitted_raw = recovery.get("submitted_task_record")
    raw_task_id = recovery.get("raw_task_id")
    if status == "submitting":
        if submitted_raw is not None or raw_task_id is not None:
            raise ValueError("submitting recovery contains a premature task identity")
    else:
        submitted_task = MediaKitRemuxSubmittedTaskRecord.model_validate(submitted_raw)
        if raw_task_id != submitted_task.task_id or recovery.get("provider_task_id_sha256") != submitted_task.task_id_sha256 or scope.get("provider_task_id_sha256") != submitted_task.task_id_sha256:
            raise ValueError("provider submitted-task recovery binding changed")

    terminal_status: Literal["completed", "failed", "canceled"] | None = None
    terminal_projection: dict[str, Any] | None = None
    terminal_raw = recovery.get("terminal_envelope")
    if status == "terminal":
        raw_status = recovery.get("provider_terminal_status")
        if raw_status not in {"completed", "failed", "canceled"} or submitted_task is None:
            raise ValueError("provider terminal recovery status is invalid")
        terminal_status = raw_status
        terminal_projection = _validated_terminal_projection(
            terminal_status=terminal_status,
            terminal_envelope=terminal_raw,
            upload_file_id_sha256=submission.upload_file_id_sha256,
            upload_url_sha256=submission.upload_url_sha256,
            client_token_sha256=submission.client_token_sha256,
            task_id_sha256=submitted_task.task_id_sha256,
        )
        terminal_digest = _canonical_sha256(terminal_projection)
        if recovery.get("provider_terminal_sha256") != terminal_digest or scope.get("provider_terminal_status") != terminal_status or scope.get("provider_terminal_sha256") != terminal_digest:
            raise ValueError("provider terminal recovery digest changed")
    elif terminal_raw is not None or recovery.get("provider_terminal_status") is not None or recovery.get("provider_terminal_sha256") is not None:
        raise ValueError("nonterminal provider recovery contains terminal state")

    return _RecoveryMaterial(
        provider_task_status=status,
        client_token=token,
        submission=submission,
        submitted_task=submitted_task,
        terminal_status=terminal_status,
        terminal_projection=terminal_projection,
    )


def _validated_candidate(
    *,
    candidate: MediaKitRemuxHTTPSCandidate,
    observer: _PaidRecoveryObserver,
    source_sha256: str,
    client_token: str,
) -> tuple[MediaKitRemuxHTTPSCandidate, str, str]:
    terminal_projection = observer.recorded_terminal_projection
    submission = observer.submission_record
    submitted_task = observer.submitted_task_record
    if terminal_projection is None or submission is None or submitted_task is None:
        raise ValueError("provider recovery evidence is incomplete")
    receipt = MediaKitRemuxIngressReceipt.model_validate(candidate.receipt.model_dump(mode="json"))
    receipt_digest = _canonical_sha256(receipt.model_dump(mode="json"))
    if (
        not isinstance(candidate.runtime_url, str)
        or _sha256_text(candidate.runtime_url) != receipt.runtime_url_sha256
        or receipt.derived_from_source_sha256 != source_sha256
        or receipt.source_size_bytes != submission.source_size_bytes
        or receipt.client_token_sha256 != _sha256_text(client_token)
        or receipt.client_token_sha256 != submission.client_token_sha256
        or receipt.upload_file_id_sha256 != submission.upload_file_id_sha256
        or receipt.task_id_sha256 != submitted_task.task_id_sha256
        or receipt.request_sha256 != submission.request_sha256
        or receipt.provider_response_sha256s[:2] != submission.provider_response_sha256s
        or receipt.provider_response_sizes_bytes[:2] != submission.provider_response_sizes_bytes
        or len(receipt.provider_response_sha256s) < 4
        or len(receipt.provider_response_sizes_bytes) < 4
        or receipt.provider_response_sha256s[2] != submitted_task.provider_response_sha256
        or receipt.provider_response_sizes_bytes[2] != submitted_task.provider_response_size_bytes
        or receipt.upload_file_id_sha256 != terminal_projection.get("upload_file_id_sha256")
        or receipt.client_token_sha256 != terminal_projection.get("client_token_sha256")
        or receipt.task_id_sha256 != terminal_projection.get("task_id_sha256")
        or receipt.runtime_url_sha256 != terminal_projection.get("runtime_url_sha256")
        or receipt_digest != terminal_projection.get("remux_receipt_sha256")
        or receipt.expires_at.astimezone(UTC).isoformat() != terminal_projection.get("expires_at")
    ):
        raise ValueError("provider candidate binding changed")
    terminal_digest = _canonical_sha256(terminal_projection)
    return (
        MediaKitRemuxHTTPSCandidate(
            runtime_url=candidate.runtime_url,
            receipt=receipt,
        ),
        receipt_digest,
        terminal_digest,
    )


def _paid_execution_result(
    *,
    candidate: MediaKitRemuxHTTPSCandidate,
    settled: Mapping[str, Any],
    execution_run_id: str,
    recovered: bool,
) -> MediaKitRemuxPaidExecutionResult:
    receipt_sha256 = _canonical_sha256(candidate.receipt.model_dump(mode="json"))
    try:
        paid_receipt = MediaKitRemuxPaidExecutionReceipt.model_validate(
            {
                "contract_version": MEDIAKIT_REMUX_PAID_EXECUTION_CONTRACT_VERSION,
                "provider": MEDIAKIT_REMUX_PAID_PROVIDER,
                "capability": MEDIAKIT_REMUX_PAID_CAPABILITY,
                "paid_call_scope_id": settled["id"],
                "paid_call_request_sha256": settled["request_digest"],
                "execution_run_id": execution_run_id,
                "source_sha256": settled["source_sha256"],
                "provider_request_sha256": settled["provider_request_sha256"],
                "client_token_sha256": settled["provider_client_token_sha256"],
                "provider_task_id_sha256": settled["provider_task_id_sha256"],
                "runtime_url_sha256": candidate.receipt.runtime_url_sha256,
                "remux_receipt_sha256": receipt_sha256,
                "provider_terminal_sha256": settled["provider_terminal_sha256"],
                "provider_task_status": settled["provider_task_status"],
                "provider_terminal_status": settled["provider_terminal_status"],
                "paid_call_status": settled["status"],
                "billing_status": "provider_amount_unavailable",
                "recovered_from_encrypted_state": recovered,
                "chat_authorization": "required_separate_paid_call",
                "chat_capability": "video_understanding_chat",
            }
        )
    except Exception:
        raise MediaKitRemuxPaidOperatorError(
            "INVALID_PAID_REMUX_EXECUTION_RECEIPT",
            reconciliation_required=True,
        ) from None
    return MediaKitRemuxPaidExecutionResult(
        runtime_url=candidate.runtime_url,
        remux_receipt=candidate.receipt,
        paid_execution_receipt=paid_receipt,
    )


async def run_paid_mediakit_remux(
    *,
    repository: MediaKitRemuxPaidCallRepository,
    owner_user_id: str,
    scope_id: str,
    expected_request_digest: str,
    execution_run_id: str,
    source_path: str | Path,
    expected_source_sha256: str,
    client_token: str | None,
    mediakit_api_key: str,
    ingress_runner: MediaKitRemuxIngressRunner = create_mediakit_remux_https_candidate,
    recovery_runner: MediaKitRemuxRecoveryRunner = recover_mediakit_remux_https_candidate,
) -> MediaKitRemuxPaidExecutionResult:
    """Execute or resume one admitted remux without authorizing Chat."""

    owner = _required(owner_user_id, field_name="owner_user_id", limit=64)
    scope_key = _required(scope_id, field_name="scope_id", limit=64)
    request_digest = _sha256(expected_request_digest, field_name="request_digest")
    execution = _required(execution_run_id, field_name="execution_run_id", limit=64)
    source_digest = _sha256(expected_source_sha256, field_name="source_sha256")
    scope = await repository.get(scope_key, owner_user_id=owner)
    if scope is None:
        raise MediaKitRemuxPaidOperatorError(
            "PAID_CALL_SCOPE_NOT_FOUND",
            reconciliation_required=False,
        )

    _assert_static_scope_binding(
        scope,
        owner_user_id=owner,
        expected_request_digest=request_digest,
        execution_run_id=execution,
        source_sha256=source_digest,
    )

    try:
        recovery = await _recovery_for_scope(
            repository,
            owner_user_id=owner,
            scope_id=scope_key,
        )
    except MediaKitRemuxPaidOperatorError:
        raise
    except Exception:
        reconciliation_required = False
        if scope.get("provider_task_status") is not None:
            reconciliation_required = await _record_unknown_internal_failure(
                repository,
                scope=scope,
                owner_user_id=owner,
                execution_run_id=execution,
                error_code="PROVIDER_TASK_RECOVERY_READ_FAILED",
            )
        raise MediaKitRemuxPaidOperatorError(
            "PROVIDER_TASK_RECOVERY_READ_FAILED",
            reconciliation_required=reconciliation_required,
        ) from None
    if scope.get("provider_task_status") is not None and recovery is None:
        recovery_proof = _canonical_sha256(
            {
                "contract_version": "ip-mediakit-remux-recovery-not-located-v1",
                "scope_id": scope_key,
                "request_digest": request_digest,
                "execution_run_id": execution,
                "provider_task_status": scope.get("provider_task_status"),
                "provider_task_id_sha256": scope.get("provider_task_id_sha256"),
            }
        )
        await _settle_provider_amount_unknown(
            repository,
            scope=scope,
            owner_user_id=owner,
            execution_run_id=execution,
            provider_receipt_digest=recovery_proof,
        )
        raise MediaKitRemuxPaidOperatorError(
            "PROVIDER_TASK_RECOVERY_NOT_AVAILABLE",
            reconciliation_required=True,
        )
    supplied_token = None if client_token is None else _client_token(client_token)
    recovered = recovery is not None
    material: _RecoveryMaterial | None = None
    if recovery is not None:
        recovered_token = recovery.get("client_token")
        if supplied_token is not None and isinstance(recovered_token, str) and _sha256_text(supplied_token) != _sha256_text(recovered_token):
            raise MediaKitRemuxPaidOperatorError(
                "RECOVERY_CLIENT_TOKEN_CONFLICT",
                reconciliation_required=True,
            )
        try:
            material = _load_recovery_material(
                scope=scope,
                recovery=recovery,
                supplied_token=None,
                source_sha256=source_digest,
            )
        except Exception:
            recovery_proof = _canonical_sha256(
                {
                    "contract_version": "ip-mediakit-remux-recovery-binding-failure-v1",
                    "scope_id": scope_key,
                    "request_digest": request_digest,
                    "execution_run_id": execution,
                    "provider_task_status": scope.get("provider_task_status"),
                    "provider_submission_sha256": scope.get("provider_submission_sha256"),
                    "provider_task_id_sha256": scope.get("provider_task_id_sha256"),
                    "provider_terminal_sha256": scope.get("provider_terminal_sha256"),
                }
            )
            await _settle_provider_amount_unknown(
                repository,
                scope=scope,
                owner_user_id=owner,
                execution_run_id=execution,
                provider_receipt_digest=recovery_proof,
            )
            raise MediaKitRemuxPaidOperatorError(
                "PROVIDER_TASK_RECOVERY_BINDING_MISMATCH",
                reconciliation_required=True,
            ) from None
        token = material.client_token
    elif supplied_token is not None:
        token = supplied_token
    else:
        raise MediaKitRemuxPaidOperatorError(
            "CLIENT_TOKEN_REQUIRED",
            reconciliation_required=False,
        )

    _assert_scope_binding(
        scope,
        owner_user_id=owner,
        expected_request_digest=request_digest,
        execution_run_id=execution,
        source_sha256=source_digest,
        client_token=token,
        allow_reconciled_terminal=(material is not None and material.provider_task_status == "terminal" and material.terminal_status == "completed"),
    )

    if material is not None and material.terminal_status in {"failed", "canceled"}:
        failure_proof = _canonical_sha256(
            {
                "contract_version": "ip-mediakit-remux-terminal-failure-v1",
                "scope_id": scope_key,
                "request_digest": request_digest,
                "provider_terminal_sha256": scope.get("provider_terminal_sha256"),
                "provider_terminal_status": material.terminal_status,
            }
        )
        await _settle_provider_amount_unknown(
            repository,
            scope=scope,
            owner_user_id=owner,
            execution_run_id=execution,
            provider_receipt_digest=failure_proof,
        )
        raise MediaKitRemuxPaidOperatorError(
            "REMUX_TASK_FAILED",
            reconciliation_required=True,
        )

    observer = _PaidRecoveryObserver(
        repository=repository,
        scope_id=scope_key,
        owner_user_id=owner,
        request_digest=request_digest,
        execution_run_id=execution,
        source_sha256=source_digest,
        client_token=token,
        submission_record=material.submission if material is not None else None,
        submitted_task_record=material.submitted_task if material is not None else None,
        persisted_terminal_status=material.terminal_status if material is not None else None,
        persisted_terminal_projection=(material.terminal_projection if material is not None else None),
    )
    provider_runner: MediaKitRemuxIngressRunner | MediaKitRemuxRecoveryRunner
    provider_kwargs: dict[str, Any]
    if material is None:
        provider_runner = ingress_runner
        provider_kwargs = {
            "source_path": source_path,
            "expected_source_sha256": source_digest,
            "mediakit_api_key": mediakit_api_key,
            "client_token": token,
            "task_observer": observer,
        }
    else:
        action: Literal["replay_submission_once", "query_existing_task"]
        if material.provider_task_status == "submitting":
            try:
                replay_claim = await repository.claim_provider_task_submission_replay(
                    scope_key,
                    owner_user_id=owner,
                    expected_request_digest=request_digest,
                    execution_run_id=execution,
                    expected_submission_sha256=_canonical_sha256(material.submission.model_dump(mode="json")),
                )
            except Exception:
                raise MediaKitRemuxPaidOperatorError(
                    "PROVIDER_SUBMISSION_REPLAY_CLAIM_FAILED",
                    reconciliation_required=False,
                ) from None
            if replay_claim is None:
                raise MediaKitRemuxPaidOperatorError(
                    "PAID_CALL_SCOPE_DISAPPEARED",
                    reconciliation_required=True,
                )
            if replay_claim.get("provider_submission_replay_claimed") is not True:
                # Another process may still be executing the one durable
                # replay.  Never issue a second POST and do not race it by
                # settling the scope underneath it.
                raise MediaKitRemuxPaidOperatorError(
                    "PROVIDER_SUBMISSION_REPLAY_ALREADY_CLAIMED",
                    reconciliation_required=True,
                )
            action = "replay_submission_once"
        else:
            if material.submitted_task is None:
                raise MediaKitRemuxPaidOperatorError(
                    "PROVIDER_TASK_RECOVERY_BINDING_MISMATCH",
                    reconciliation_required=True,
                )
            action = "query_existing_task"
        try:
            recovery_request = MediaKitRemuxRecoveryRequest(
                contract_version="ip-mediakit-remux-recovery-request-v1",
                action=action,
                submission=material.submission,
                client_token=token,
                submitted_task=(material.submitted_task if action == "query_existing_task" else None),
            )
        except Exception:
            await _record_unknown_internal_failure(
                repository,
                scope=scope,
                owner_user_id=owner,
                execution_run_id=execution,
                error_code="INVALID_REMUX_RECOVERY_REQUEST",
            )
            raise MediaKitRemuxPaidOperatorError(
                "INVALID_REMUX_RECOVERY_REQUEST",
                reconciliation_required=True,
            ) from None
        provider_runner = recovery_runner
        provider_kwargs = {
            "source_path": source_path,
            "expected_source_sha256": source_digest,
            "mediakit_api_key": mediakit_api_key,
            "recovery_request": recovery_request,
            "task_observer": observer,
        }
    try:
        candidate = await provider_runner(**provider_kwargs)
    except MediaKitRemuxIngressError as exc:
        reconciliation_required = await _record_failed_execution_accounting(
            repository,
            scope=scope,
            owner_user_id=owner,
            execution_run_id=execution,
            error=exc,
        )
        raise MediaKitRemuxPaidOperatorError(
            exc.code,
            reconciliation_required=reconciliation_required,
        ) from None
    except Exception:
        reconciliation_required = await _record_unknown_internal_failure(
            repository,
            scope=scope,
            owner_user_id=owner,
            execution_run_id=execution,
            error_code="REMUX_OPERATOR_INTERNAL_FAILURE",
        )
        raise MediaKitRemuxPaidOperatorError(
            "REMUX_OPERATOR_INTERNAL_FAILURE",
            reconciliation_required=reconciliation_required,
        ) from None
    try:
        validated_candidate, receipt_digest, observed_terminal_digest = _validated_candidate(
            candidate=candidate,
            observer=observer,
            source_sha256=source_digest,
            client_token=token,
        )
    except Exception:
        await _record_unknown_internal_failure(
            repository,
            scope=scope,
            owner_user_id=owner,
            execution_run_id=execution,
            error_code="REMUX_RECEIPT_BINDING_MISMATCH",
        )
        raise MediaKitRemuxPaidOperatorError(
            "REMUX_RECEIPT_BINDING_MISMATCH",
            reconciliation_required=True,
        ) from None
    accounting_digest = _canonical_sha256(
        {
            "contract_version": "ip-mediakit-remux-accounting-evidence-v1",
            "remux_receipt_sha256": receipt_digest,
            "observed_terminal_sha256": observed_terminal_digest,
            "persisted_terminal_sha256": (scope.get("provider_terminal_sha256") if material is not None and material.provider_task_status == "terminal" else observed_terminal_digest),
        }
    )
    if scope.get("status") == "reconciliation_required":
        settled = scope
    else:
        settled = await _settle_provider_amount_unknown(
            repository,
            scope=scope,
            owner_user_id=owner,
            execution_run_id=execution,
            provider_receipt_digest=accounting_digest,
        )
    return _paid_execution_result(
        candidate=validated_candidate,
        settled=settled,
        execution_run_id=execution,
        recovered=recovered,
    )


__all__ = [
    "MEDIAKIT_REMUX_PAID_CAPABILITY",
    "MEDIAKIT_REMUX_PAID_EXECUTION_CONTRACT_VERSION",
    "MEDIAKIT_REMUX_PAID_PROVIDER",
    "MEDIAKIT_REMUX_PAID_REQUEST_CONTRACT_VERSION",
    "MEDIAKIT_REMUX_OPERATOR_CAPPED_POLICY_VERSION",
    "MEDIAKIT_REMUX_PAID_SERVER",
    "MEDIAKIT_REMUX_PAID_SKU",
    "MEDIAKIT_REMUX_PAID_TOOL",
    "MediaKitRemuxPaidExecutionReceipt",
    "MediaKitRemuxPaidExecutionResult",
    "MediaKitRemuxPaidOperatorError",
    "build_mediakit_remux_paid_provider_request_sha256",
    "run_paid_mediakit_remux",
]
