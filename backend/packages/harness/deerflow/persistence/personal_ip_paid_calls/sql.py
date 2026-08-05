"""Atomic append-only repository for exact one-shot paid provider calls.

This module does not execute a provider.  It only records the server-owned
request, human decision, budget reservation, one-time admission consumption,
and final accounting receipt.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.channel_connections.sql import ChannelCredentialCipher
from deerflow.persistence.personal_ip_paid_calls.model import (
    PersonalIPPaidCallEventRow,
    PersonalIPPaidCallScopeRow,
)
from deerflow.persistence.personal_ip_platform_observations.sql import validate_credential_free_payload
from deerflow.utils.time import coerce_iso

PAID_CALL_SCOPE_CONTRACT_VERSION = "personal-ip-paid-call-scope-v1"
PAID_CALL_EVENT_CONTRACT_VERSION = "personal-ip-paid-call-event-v1"
EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION = "evidence-asr-direct-pay-v1"
EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION = "evidence-managed-remux-operator-cap-v1"
EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION = "evidence-video-understanding-chat-operator-cap-v1"
EVIDENCE_VIDEO_STRATEGY_OPERATOR_CAP_POLICY_VERSION = "evidence-video-strategy-operator-cap-v1"
MEDIAKIT_PROVIDER_TASK_CONTRACT_VERSION = "personal-ip-mediakit-provider-task-v1"
MEDIAKIT_PROVIDER_SUBMISSION_CONTRACT_VERSION = "ip-mediakit-remux-submission-recovery-v1"
MEDIAKIT_PROVIDER_SUBMITTED_TASK_CONTRACT_VERSION = "ip-mediakit-remux-submitted-task-recovery-v1"
MEDIAKIT_VIDEO_STRATEGY_PROVIDER_SUBMISSION_CONTRACT_VERSION = "ip-mediakit-video-strategy-submission-recovery-v1"
MEDIAKIT_VIDEO_STRATEGY_PROVIDER_SUBMITTED_TASK_CONTRACT_VERSION = "ip-mediakit-video-strategy-submitted-task-recovery-v1"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_SAFE_OBJECT_REF_FORBIDDEN = re.compile(
    r"(?:[/\\]|://|\b(?:file|https?|s3|gs):|\b(?:token|cookie|password|secret|api[_ -]?key)\b)",
    re.IGNORECASE,
)
_SAFE_SUMMARY_FORBIDDEN = re.compile(
    r"(?:://|\b(?:token|cookie|password|secret|api[_ -]?key)\b)",
    re.IGNORECASE,
)
_MAX_PROVIDER_TERMINAL_BYTES = 2 * 1024 * 1024
_MAX_PROVIDER_SUBMISSION_BYTES = 64 * 1024
_MAX_MEDIAKIT_SOURCE_BYTES = 512 * 1024 * 1024
_MAX_MEDIAKIT_RESPONSE_BYTES = 1024 * 1024
_MEDIAKIT_REMUX_ADAPTER_VERSION = "volcengine-mediakit-remux-https-ingress-v1"
_MEDIAKIT_REMUX_CAPABILITY = "managed_https_ingress_remux"
_MEDIAKIT_REMUX_ENDPOINT = "https://mediakit.cn-beijing.volces.com"
_MEDIAKIT_VIDEO_STRATEGY_ADAPTER_VERSION = "volcengine-mediakit-video-strategy-research-v1"
_MEDIAKIT_VIDEO_STRATEGY_PROFILE_VERSION = "ip-editing-audiovisual-research-observation-v1"
_MEDIAKIT_VIDEO_STRATEGY_CAPABILITY = "video_understanding_smart_strategy"
_MEDIAKIT_VIDEO_STRATEGY_ENDPOINT = "https://mediakit.cn-beijing.volces.com/api/v1/tools/video-understand-router"
_MEDIAKIT_VIDEO_STRATEGY_TOOL_NAME = "video-understand-router"
_OPERATOR_CAPPED_MEDIAKIT_POLICY_BY_CAPABILITY = {
    "asr": EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
    "managed_https_ingress_remux": EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION,
    "video_understanding_chat": EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION,
    "video_understanding_smart_strategy": EVIDENCE_VIDEO_STRATEGY_OPERATOR_CAP_POLICY_VERSION,
}
_MEDIAKIT_REMUX_SUBMISSION_FIELDS = frozenset(
    {
        "contract_version",
        "provider",
        "capability",
        "adapter_version",
        "endpoint_sha256",
        "source_sha256",
        "source_size_bytes",
        "upload_file_id",
        "upload_file_id_sha256",
        "upload_url_sha256",
        "client_token_sha256",
        "container_format",
        "request_sha256",
        "submit_body_sha256",
        "provider_response_sha256s",
        "provider_response_sizes_bytes",
        "provider_request_id_sha256s",
        "retries",
    }
)
_MEDIAKIT_REMUX_SUBMITTED_TASK_FIELDS = frozenset(
    {
        "contract_version",
        "provider",
        "capability",
        "task_id",
        "task_id_sha256",
        "provider_response_sha256",
        "provider_response_size_bytes",
        "provider_request_id_sha256s",
    }
)
_MEDIAKIT_VIDEO_STRATEGY_SUBMISSION_FIELDS = frozenset(
    {
        "contract_version",
        "provider",
        "capability",
        "adapter_version",
        "profile_version",
        "endpoint_sha256",
        "source_sha256",
        "provider_input_ref_sha256",
        "request_sha256",
        "submit_body_sha256",
        "submit_body",
        "automatic_retries",
        "callback_url_mode",
    }
)
_MEDIAKIT_VIDEO_STRATEGY_SUBMIT_BODY_FIELDS = frozenset(
    {
        "video_urls",
        "prompt",
        "level",
        "scene",
        "manual_option",
        "client_token",
    }
)
_MEDIAKIT_VIDEO_STRATEGY_SUBMITTED_TASK_FIELDS = frozenset(
    {
        "contract_version",
        "provider",
        "capability",
        "task_id",
        "task_id_sha256",
        "request_sha256",
        "client_token_sha256",
        "provider_response_sha256",
        "provider_response_size_bytes",
        "provider_request_id_sha256s",
    }
)


@dataclass(frozen=True, slots=True)
class OperatorCappedEvidenceStagePolicy:
    """Trusted operator limit for one allowlisted MediaKit evidence stage."""

    capability: str
    policy_version: str
    local_admission_limit_micros: int
    max_source_duration_millis: int


class AmbiguousOperatorCappedEvidenceStages(ValueError):
    """More than one exact approved stage matched before any transition."""

    def __init__(self, matched_capabilities: Iterable[str]) -> None:
        self.matched_capabilities = tuple(str(value) for value in matched_capabilities)
        super().__init__("multiple approved operator-capped evidence stages match the exact invocation")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _clean_required(value: Any, *, field: str, limit: int) -> str:
    result = " ".join(str(value or "").split())
    if not result or len(result) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return result


def _clean_optional(value: Any, *, field: str, limit: int) -> str | None:
    if value is None:
        return None
    result = " ".join(str(value).split())
    if not result:
        return None
    if len(result) > limit:
        raise ValueError(f"{field} must contain at most {limit} characters")
    return result


def _safe_summary(value: Any, *, field: str, limit: int, object_ref: bool = False) -> str:
    result = _clean_required(value, field=field, limit=limit)
    forbidden = _SAFE_OBJECT_REF_FORBIDDEN if object_ref else _SAFE_SUMMARY_FORBIDDEN
    if forbidden.search(result):
        raise ValueError(f"{field} must not contain a path, URL, or sensitive field name")
    return result


def _hex_digest(value: Any, *, field: str) -> str:
    result = str(value or "").strip().lower()
    if not _HEX64.fullmatch(result):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return result


def _micros(value: Any, *, field: str, positive: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer number of micro-units")
    minimum = 1 if positive else 0
    if value < minimum or value > 9_000_000_000_000_000:
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{field} must be a {qualifier} integer number of micro-units")
    return value


def _utc(value: datetime | None, *, field: str) -> datetime:
    if value is None or not isinstance(value, datetime):
        raise ValueError(f"{field} must be a datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return coerce_iso(_utc(value, field="datetime"))


def _trusted_operator_capped_stage_policies(
    values: Iterable[OperatorCappedEvidenceStagePolicy],
) -> tuple[OperatorCappedEvidenceStagePolicy, ...]:
    try:
        supplied = tuple(values)
    except TypeError as exc:
        raise ValueError("trusted_stage_policies must be an iterable") from exc
    if not supplied or len(supplied) > len(_OPERATOR_CAPPED_MEDIAKIT_POLICY_BY_CAPABILITY):
        raise ValueError("trusted_stage_policies must contain an allowlisted evidence stage")

    normalized: list[OperatorCappedEvidenceStagePolicy] = []
    seen_capabilities: set[str] = set()
    for value in supplied:
        if not isinstance(value, OperatorCappedEvidenceStagePolicy):
            raise ValueError("trusted_stage_policies contains an invalid stage policy")
        capability = _clean_required(
            value.capability,
            field="capability",
            limit=80,
        ).lower()
        policy_version = _clean_required(
            value.policy_version,
            field="policy_version",
            limit=80,
        )
        if _OPERATOR_CAPPED_MEDIAKIT_POLICY_BY_CAPABILITY.get(capability) != policy_version:
            raise ValueError("trusted_stage_policies contains an unsupported capability policy")
        if capability in seen_capabilities:
            raise ValueError("trusted_stage_policies capabilities must be unique")
        seen_capabilities.add(capability)
        normalized.append(
            OperatorCappedEvidenceStagePolicy(
                capability=capability,
                policy_version=policy_version,
                local_admission_limit_micros=_micros(
                    value.local_admission_limit_micros,
                    field="local_admission_limit_micros",
                    positive=True,
                ),
                max_source_duration_millis=_micros(
                    value.max_source_duration_millis,
                    field="max_source_duration_millis",
                    positive=True,
                ),
            )
        )
    return tuple(normalized)


class PersonalIPPaidCallRepository:
    """Persist and atomically consume exact, Owner-scoped paid-call approval."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        provider_task_cipher: ChannelCredentialCipher | None = None,
    ) -> None:
        self._sf = session_factory
        self._provider_task_cipher = provider_task_cipher

    @staticmethod
    def _scope_dict(row: PersonalIPPaidCallScopeRow) -> dict[str, Any]:
        result = row.to_dict(
            exclude={
                "encrypted_provider_client_token",
                "encrypted_provider_submission_json",
                "encrypted_provider_task_id",
                "encrypted_provider_terminal_json",
            }
        )
        for field in ("expires_at", "created_at", "updated_at"):
            if isinstance(result.get(field), datetime):
                result[field] = coerce_iso(result[field])
        result["version"] = result["event_count"]
        return result

    @staticmethod
    def _event_dict(row: PersonalIPPaidCallEventRow) -> dict[str, Any]:
        result = row.to_dict()
        result["payload"] = result.pop("payload_json") or {}
        for field in ("occurred_at", "created_at"):
            if isinstance(result.get(field), datetime):
                result[field] = coerce_iso(result[field])
        return result

    async def _events(self, session: AsyncSession, scope_id: str) -> list[dict[str, Any]]:
        rows = (await session.execute(select(PersonalIPPaidCallEventRow).where(PersonalIPPaidCallEventRow.scope_id == scope_id).order_by(PersonalIPPaidCallEventRow.sequence.asc()))).scalars().all()
        return [self._event_dict(row) for row in rows]

    async def _result(
        self,
        session: AsyncSession,
        row: PersonalIPPaidCallScopeRow,
        *,
        operation_event: PersonalIPPaidCallEventRow,
        idempotent_replay: bool,
    ) -> dict[str, Any]:
        result = self._scope_dict(row)
        result["events"] = await self._events(session, row.id)
        result["operation_event"] = self._event_dict(operation_event)
        result["idempotent_replay"] = idempotent_replay
        return result

    @staticmethod
    async def _begin_request_lock(session: AsyncSession, *, owner_user_id: str, request_key: str) -> None:
        dialect = session.get_bind().dialect.name
        if dialect == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))
        elif dialect == "postgresql":
            raw = hashlib.sha256(f"paid-call-request:{owner_user_id}:{request_key}".encode()).digest()[:8]
            lock_key = int.from_bytes(raw, "big") & ((1 << 63) - 1)
            await session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    @staticmethod
    async def _lock_scope(
        session: AsyncSession,
        *,
        owner_user_id: str,
        scope_id: str,
    ) -> PersonalIPPaidCallScopeRow | None:
        dialect = session.get_bind().dialect.name
        if dialect == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))
        statement = select(PersonalIPPaidCallScopeRow).where(
            PersonalIPPaidCallScopeRow.id == scope_id,
            PersonalIPPaidCallScopeRow.owner_user_id == owner_user_id,
        )
        if dialect != "sqlite":
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    def _requested_payload(values: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "contract_version": PAID_CALL_SCOPE_CONTRACT_VERSION,
            "object_ref_label": values["object_ref_label"],
            "source_duration_millis": values["source_duration_millis"],
            "provider": {"id": values["provider"], "label": values["provider_label"]},
            "capability": {"id": values["capability"], "label": values["capability_label"]},
            "model": values["model"],
            "sku": values["sku"],
            "billing": {
                "maximum_amount_micros": values["maximum_amount_micros"],
                "currency": values["currency"],
                "basis": values["billing_basis"],
                "price_status": values["price_status"],
                "price_version": values["price_version"],
            },
            "expires_at": _iso(values["expires_at"]),
            "provider_input_attested": values["provider_input_attested"],
            "evidence_coverage": values["evidence_coverage"],
            "warning_code": values["warning_code"],
        }
        validate_credential_free_payload(payload, field="paid_call_requested_payload")
        return payload

    @staticmethod
    def _event_digest(
        *,
        scope_id: str,
        request_digest: str,
        event_key: str,
        event_type: str,
        execution_run_id: str | None,
        amount_micros: int | None,
        proof_digest: str | None,
        admission_jti_hash: str | None,
        reason_code: str | None,
        payload: dict[str, Any],
    ) -> str:
        return _digest(
            {
                "contract_version": PAID_CALL_EVENT_CONTRACT_VERSION,
                "scope_id": scope_id,
                "request_digest": request_digest,
                "event_key": event_key,
                "event_type": event_type,
                "execution_run_id": execution_run_id,
                "amount_micros": amount_micros,
                "proof_digest": proof_digest,
                "admission_jti_hash": admission_jti_hash,
                "reason_code": reason_code,
                "payload": payload,
            }
        )

    @classmethod
    def _event_row(
        cls,
        row: PersonalIPPaidCallScopeRow,
        *,
        event_key: str,
        event_type: str,
        execution_run_id: str | None,
        amount_micros: int | None = None,
        proof_digest: str | None = None,
        admission_jti_hash: str | None = None,
        reason_code: str | None = None,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime,
    ) -> PersonalIPPaidCallEventRow:
        safe_payload = payload or {}
        validate_credential_free_payload(safe_payload, field="paid_call_event_payload")
        event_digest = cls._event_digest(
            scope_id=row.id,
            request_digest=row.request_digest,
            event_key=event_key,
            event_type=event_type,
            execution_run_id=execution_run_id,
            amount_micros=amount_micros,
            proof_digest=proof_digest,
            admission_jti_hash=admission_jti_hash,
            reason_code=reason_code,
            payload=safe_payload,
        )
        return PersonalIPPaidCallEventRow(
            id=f"paid-call-event-{uuid.uuid4().hex}",
            owner_user_id=row.owner_user_id,
            scope_id=row.id,
            event_key=event_key,
            event_digest=event_digest,
            request_digest=row.request_digest,
            sequence=row.event_count + 1,
            event_type=event_type,
            execution_run_id=execution_run_id,
            amount_micros=amount_micros,
            proof_digest=proof_digest,
            admission_jti_hash=admission_jti_hash,
            reason_code=reason_code,
            payload_json=safe_payload,
            occurred_at=occurred_at,
        )

    @staticmethod
    async def _existing_event(
        session: AsyncSession,
        *,
        scope_id: str,
        event_key: str,
    ) -> PersonalIPPaidCallEventRow | None:
        return (
            await session.execute(
                select(PersonalIPPaidCallEventRow).where(
                    PersonalIPPaidCallEventRow.scope_id == scope_id,
                    PersonalIPPaidCallEventRow.event_key == event_key,
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    def _assert_request_binding(row: PersonalIPPaidCallScopeRow, expected_request_digest: str) -> None:
        expected = _hex_digest(expected_request_digest, field="expected_request_digest")
        if row.request_digest != expected:
            raise ValueError("paid-call action does not match the immutable request digest")

    @staticmethod
    def _assert_version(row: PersonalIPPaidCallScopeRow, expected_event_count: int | None) -> None:
        if expected_event_count is None:
            return
        expected = _micros(expected_event_count, field="expected_event_count", positive=True)
        if row.event_count != expected:
            raise ValueError("paid-call scope version changed; reload before deciding")

    @staticmethod
    def _assert_execution_binding(row: PersonalIPPaidCallScopeRow, execution_run_id: str) -> None:
        if row.execution_run_id != execution_run_id:
            raise ValueError("paid-call action does not match the reserved execution run")

    def _provider_cipher(self) -> ChannelCredentialCipher:
        if self._provider_task_cipher is None:
            raise RuntimeError("provider task encryption key is required")
        return self._provider_task_cipher

    def _encrypt_provider_value(self, value: str) -> str:
        encrypted = self._provider_cipher().encrypt_text(value)
        if encrypted is None:
            raise RuntimeError("provider task encryption failed")
        return encrypted

    def _decrypt_provider_value(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self._provider_cipher().decrypt_text(value)

    @staticmethod
    def _provider_task_event(
        row: PersonalIPPaidCallScopeRow,
        *,
        event_key: str,
        payload: dict[str, Any],
        occurred_at: datetime,
    ) -> PersonalIPPaidCallEventRow:
        return PersonalIPPaidCallRepository._event_row(
            row,
            event_key=event_key,
            event_type="provider_task",
            execution_run_id=row.execution_run_id,
            payload={
                "contract_version": MEDIAKIT_PROVIDER_TASK_CONTRACT_VERSION,
                **payload,
            },
            occurred_at=occurred_at,
        )

    @staticmethod
    def _provider_task_id(raw_task_id: str) -> tuple[str, str]:
        task_id = _clean_required(raw_task_id, field="raw_task_id", limit=1024)
        return task_id, hashlib.sha256(task_id.encode("utf-8")).hexdigest()

    @staticmethod
    def _provider_remux_submission(
        value: dict[str, Any],
        *,
        capability: str,
        source_sha256: str,
        client_token: str,
    ) -> tuple[dict[str, Any], str, str]:
        """Validate the one exact remux POST that may be replayed after a crash."""

        if not isinstance(value, dict) or set(value) != _MEDIAKIT_REMUX_SUBMISSION_FIELDS:
            raise ValueError("provider_submission must match the exact recovery contract")
        projection = dict(value)
        if (
            projection.get("contract_version") != MEDIAKIT_PROVIDER_SUBMISSION_CONTRACT_VERSION
            or projection.get("provider") != "volcengine-mediakit"
            or projection.get("capability") != _MEDIAKIT_REMUX_CAPABILITY
            or projection.get("adapter_version") != _MEDIAKIT_REMUX_ADAPTER_VERSION
            or projection.get("container_format") != "MP4"
            or projection.get("retries") != 0
        ):
            raise ValueError("provider_submission contract binding is invalid")
        if capability != _MEDIAKIT_REMUX_CAPABILITY:
            raise ValueError("provider_submission is only valid for managed remux")
        source_digest = _hex_digest(
            projection.get("source_sha256"),
            field="provider_submission.source_sha256",
        )
        if source_digest != source_sha256:
            raise ValueError("provider_submission source binding changed")
        source_size = projection.get("source_size_bytes")
        if isinstance(source_size, bool) or not isinstance(source_size, int) or not 1 <= source_size <= _MAX_MEDIAKIT_SOURCE_BYTES:
            raise ValueError("provider_submission source_size_bytes is invalid")
        upload_file_id = _clean_required(
            projection.get("upload_file_id"),
            field="provider_submission.upload_file_id",
            limit=1024,
        )
        try:
            parsed_file_id = urlsplit(upload_file_id)
        except ValueError:
            raise ValueError("provider_submission upload_file_id is invalid") from None
        if parsed_file_id.scheme.lower() != "mediakit" or not parsed_file_id.netloc or parsed_file_id.username is not None or parsed_file_id.password is not None or parsed_file_id.query or parsed_file_id.fragment:
            raise ValueError("provider_submission upload_file_id is invalid")
        file_id_digest = hashlib.sha256(upload_file_id.encode("utf-8")).hexdigest()
        if (
            _hex_digest(
                projection.get("upload_file_id_sha256"),
                field="provider_submission.upload_file_id_sha256",
            )
            != file_id_digest
        ):
            raise ValueError("provider_submission upload file binding changed")
        token_digest = hashlib.sha256(client_token.encode("utf-8")).hexdigest()
        if (
            _hex_digest(
                projection.get("client_token_sha256"),
                field="provider_submission.client_token_sha256",
            )
            != token_digest
        ):
            raise ValueError("provider_submission client token binding changed")
        endpoint_digest = hashlib.sha256(_MEDIAKIT_REMUX_ENDPOINT.encode("utf-8")).hexdigest()
        if (
            _hex_digest(
                projection.get("endpoint_sha256"),
                field="provider_submission.endpoint_sha256",
            )
            != endpoint_digest
        ):
            raise ValueError("provider_submission endpoint binding changed")
        for field_name in (
            "upload_url_sha256",
            "submit_body_sha256",
        ):
            _hex_digest(
                projection.get(field_name),
                field=f"provider_submission.{field_name}",
            )
        exact_submit_body = {
            "video_url": upload_file_id,
            "container_format": "MP4",
            "client_token": client_token,
        }
        if projection["submit_body_sha256"] != _digest(exact_submit_body):
            raise ValueError("provider_submission exact POST body binding changed")
        request_projection = {
            "contract_version": "ip-mediakit-remux-https-candidate-v1",
            "adapter_version": _MEDIAKIT_REMUX_ADAPTER_VERSION,
            "endpoint": _MEDIAKIT_REMUX_ENDPOINT,
            "derived_from_source_sha256": source_digest,
            "source_size_bytes": source_size,
            "upload_file_id_sha256": file_id_digest,
            "container_format": "MP4",
            "client_token_sha256": token_digest,
            "retries": 0,
        }
        if _hex_digest(
            projection.get("request_sha256"),
            field="provider_submission.request_sha256",
        ) != _digest(request_projection):
            raise ValueError("provider_submission request projection binding changed")
        response_digests = projection.get("provider_response_sha256s")
        response_sizes = projection.get("provider_response_sizes_bytes")
        if not isinstance(response_digests, list) or not isinstance(response_sizes, list) or len(response_digests) != 2 or len(response_sizes) != 2:
            raise ValueError("provider_submission requires the two pre-submit responses")
        for index, digest in enumerate(response_digests):
            _hex_digest(
                digest,
                field=f"provider_submission.provider_response_sha256s[{index}]",
            )
        if any(isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= _MAX_MEDIAKIT_RESPONSE_BYTES for size in response_sizes):
            raise ValueError("provider_submission response size is invalid")
        request_ids = projection.get("provider_request_id_sha256s")
        if not isinstance(request_ids, list) or len(request_ids) > 2:
            raise ValueError("provider_submission request-id list is invalid")
        for index, digest in enumerate(request_ids):
            _hex_digest(
                digest,
                field=f"provider_submission.provider_request_id_sha256s[{index}]",
            )
        try:
            encoded = json.dumps(
                projection,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("provider_submission must be canonical JSON") from exc
        if len(encoded.encode("utf-8")) > _MAX_PROVIDER_SUBMISSION_BYTES:
            raise ValueError("provider_submission exceeds the encrypted snapshot limit")
        return projection, encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _provider_video_strategy_submission(
        value: dict[str, Any],
        *,
        capability: str,
        source_sha256: str,
        client_token: str,
    ) -> tuple[dict[str, Any], str, str]:
        """Validate the exact Smart Strategy POST persisted before submission."""

        if not isinstance(value, dict) or set(value) != _MEDIAKIT_VIDEO_STRATEGY_SUBMISSION_FIELDS:
            raise ValueError("provider_submission must match the exact recovery contract")
        projection = dict(value)
        dispatch = (
            projection.get("provider"),
            projection.get("capability"),
            projection.get("contract_version"),
        )
        if dispatch != (
            "volcengine-mediakit",
            _MEDIAKIT_VIDEO_STRATEGY_CAPABILITY,
            MEDIAKIT_VIDEO_STRATEGY_PROVIDER_SUBMISSION_CONTRACT_VERSION,
        ):
            raise ValueError("provider_submission contract binding is invalid")
        if capability != _MEDIAKIT_VIDEO_STRATEGY_CAPABILITY:
            raise ValueError("provider_submission capability binding changed")
        if (
            projection.get("adapter_version") != _MEDIAKIT_VIDEO_STRATEGY_ADAPTER_VERSION
            or projection.get("profile_version") != _MEDIAKIT_VIDEO_STRATEGY_PROFILE_VERSION
            or projection.get("automatic_retries") != 0
            or projection.get("callback_url_mode") != "omitted"
        ):
            raise ValueError("provider_submission contract binding is invalid")
        source_digest = _hex_digest(
            projection.get("source_sha256"),
            field="provider_submission.source_sha256",
        )
        if source_digest != source_sha256:
            raise ValueError("provider_submission source binding changed")
        endpoint_digest = hashlib.sha256(_MEDIAKIT_VIDEO_STRATEGY_ENDPOINT.encode("utf-8")).hexdigest()
        if (
            _hex_digest(
                projection.get("endpoint_sha256"),
                field="provider_submission.endpoint_sha256",
            )
            != endpoint_digest
        ):
            raise ValueError("provider_submission endpoint binding changed")

        body = projection.get("submit_body")
        if not isinstance(body, dict) or set(body) != _MEDIAKIT_VIDEO_STRATEGY_SUBMIT_BODY_FIELDS:
            raise ValueError("provider_submission exact POST body is invalid")
        video_urls = body.get("video_urls")
        if not isinstance(video_urls, list) or len(video_urls) != 1:
            raise ValueError("provider_submission requires one exact video reference")
        video_ref = video_urls[0]
        if not isinstance(video_ref, str) or not video_ref or video_ref != video_ref.strip():
            raise ValueError("provider_submission video reference is invalid")
        try:
            video_ref_bytes = video_ref.encode("utf-8")
            parsed_ref = urlsplit(video_ref)
        except (UnicodeError, ValueError):
            raise ValueError("provider_submission video reference is invalid") from None
        if (
            len(video_ref_bytes) > 8 * 1024
            or parsed_ref.scheme.lower() not in {"http", "https", "mediakit", "vod", "tos"}
            or parsed_ref.fragment
            or (parsed_ref.scheme.lower() in {"http", "https"} and (not parsed_ref.netloc or parsed_ref.username is not None or parsed_ref.password is not None))
            or (parsed_ref.scheme.lower() in {"mediakit", "vod", "tos"} and not parsed_ref.netloc and not parsed_ref.path)
        ):
            raise ValueError("provider_submission video reference is invalid")
        input_ref_digest = hashlib.sha256(video_ref_bytes).hexdigest()
        if (
            _hex_digest(
                projection.get("provider_input_ref_sha256"),
                field="provider_submission.provider_input_ref_sha256",
            )
            != input_ref_digest
        ):
            raise ValueError("provider_submission video reference binding changed")

        if not isinstance(client_token, str) or not 1 <= len(client_token) <= 64 or any(ord(character) < 32 or ord(character) > 126 for character in client_token) or body.get("client_token") != client_token:
            raise ValueError("provider_submission client token binding changed")
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt or len(prompt.encode("utf-8")) > 32 * 1024:
            raise ValueError("provider_submission prompt is invalid")
        if body.get("level") not in {"Economy", "Balanced", "Quality"} or body.get("scene") != "editing" or body.get("manual_option") != {"need_audio": True}:
            raise ValueError("provider_submission fixed Strategy profile changed")
        submit_body_digest = _digest(body)
        if (
            _hex_digest(
                projection.get("submit_body_sha256"),
                field="provider_submission.submit_body_sha256",
            )
            != submit_body_digest
        ):
            raise ValueError("provider_submission exact POST body binding changed")
        request_projection = {
            "contract_version": "ip-mediakit-video-strategy-request-v1",
            "adapter_version": _MEDIAKIT_VIDEO_STRATEGY_ADAPTER_VERSION,
            "profile_version": _MEDIAKIT_VIDEO_STRATEGY_PROFILE_VERSION,
            "provider_tool_name": _MEDIAKIT_VIDEO_STRATEGY_TOOL_NAME,
            "method": "POST",
            "endpoint_sha256": endpoint_digest,
            "body": body,
            "automatic_retries": 0,
            "callback_url_mode": "omitted",
        }
        if _hex_digest(
            projection.get("request_sha256"),
            field="provider_submission.request_sha256",
        ) != _digest(request_projection):
            raise ValueError("provider_submission request projection binding changed")
        try:
            encoded = json.dumps(
                projection,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("provider_submission must be canonical JSON") from exc
        if len(encoded.encode("utf-8")) > _MAX_PROVIDER_SUBMISSION_BYTES:
            raise ValueError("provider_submission exceeds the encrypted snapshot limit")
        return projection, encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _provider_submission(
        value: dict[str, Any],
        *,
        capability: str,
        source_sha256: str,
        client_token: str,
    ) -> tuple[dict[str, Any], str, str]:
        """Strictly dispatch an encrypted provider request by its exact contract."""

        if not isinstance(value, dict):
            raise ValueError("provider_submission must match the exact recovery contract")
        dispatch = (
            value.get("provider"),
            value.get("capability"),
            value.get("contract_version"),
        )
        if dispatch == (
            "volcengine-mediakit",
            _MEDIAKIT_REMUX_CAPABILITY,
            MEDIAKIT_PROVIDER_SUBMISSION_CONTRACT_VERSION,
        ):
            return PersonalIPPaidCallRepository._provider_remux_submission(
                value,
                capability=capability,
                source_sha256=source_sha256,
                client_token=client_token,
            )
        if dispatch == (
            "volcengine-mediakit",
            _MEDIAKIT_VIDEO_STRATEGY_CAPABILITY,
            MEDIAKIT_VIDEO_STRATEGY_PROVIDER_SUBMISSION_CONTRACT_VERSION,
        ):
            return PersonalIPPaidCallRepository._provider_video_strategy_submission(
                value,
                capability=capability,
                source_sha256=source_sha256,
                client_token=client_token,
            )
        raise ValueError("provider_submission contract dispatch is unsupported")

    @staticmethod
    def _provider_remux_submitted_task_record(
        value: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validate submit-response evidence and remove its raw task id.

        The full record is returned only to the encrypted recovery path.  The
        second projection is safe for the append-only event ledger.
        """

        if (
            not isinstance(value, dict)
            or set(value) != _MEDIAKIT_REMUX_SUBMITTED_TASK_FIELDS
            or value.get("contract_version") != MEDIAKIT_PROVIDER_SUBMITTED_TASK_CONTRACT_VERSION
            or value.get("provider") != "volcengine-mediakit"
            or value.get("capability") != _MEDIAKIT_REMUX_CAPABILITY
        ):
            raise ValueError("submitted_task_record must match the exact recovery contract")
        record = dict(value)
        task_id, task_id_digest = PersonalIPPaidCallRepository._provider_task_id(record.get("task_id"))
        if (
            _hex_digest(
                record.get("task_id_sha256"),
                field="submitted_task_record.task_id_sha256",
            )
            != task_id_digest
        ):
            raise ValueError("submitted_task_record task identifier binding changed")
        _hex_digest(
            record.get("provider_response_sha256"),
            field="submitted_task_record.provider_response_sha256",
        )
        size = record.get("provider_response_size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= _MAX_MEDIAKIT_RESPONSE_BYTES:
            raise ValueError("submitted_task_record response size is invalid")
        request_ids = record.get("provider_request_id_sha256s")
        if not isinstance(request_ids, list) or len(request_ids) > 2:
            raise ValueError("submitted_task_record request-id list is invalid")
        for index, digest in enumerate(request_ids):
            _hex_digest(
                digest,
                field=(f"submitted_task_record.provider_request_id_sha256s[{index}]"),
            )
        record["task_id"] = task_id
        safe_projection = {key: item for key, item in record.items() if key != "task_id"}
        validate_credential_free_payload(
            safe_projection,
            field="submitted_task_record_event_projection",
        )
        return record, safe_projection

    @staticmethod
    def _provider_video_strategy_submitted_task_record(
        value: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validate Strategy submit evidence and redact its raw task id."""

        if (
            not isinstance(value, dict)
            or set(value) != _MEDIAKIT_VIDEO_STRATEGY_SUBMITTED_TASK_FIELDS
            or value.get("contract_version") != MEDIAKIT_VIDEO_STRATEGY_PROVIDER_SUBMITTED_TASK_CONTRACT_VERSION
            or value.get("provider") != "volcengine-mediakit"
            or value.get("capability") != _MEDIAKIT_VIDEO_STRATEGY_CAPABILITY
        ):
            raise ValueError("submitted_task_record must match the exact recovery contract")
        record = dict(value)
        task_id, task_id_digest = PersonalIPPaidCallRepository._provider_task_id(record.get("task_id"))
        if (
            _hex_digest(
                record.get("task_id_sha256"),
                field="submitted_task_record.task_id_sha256",
            )
            != task_id_digest
        ):
            raise ValueError("submitted_task_record task identifier binding changed")
        for field_name in (
            "request_sha256",
            "client_token_sha256",
            "provider_response_sha256",
        ):
            _hex_digest(
                record.get(field_name),
                field=f"submitted_task_record.{field_name}",
            )
        size = record.get("provider_response_size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= _MAX_MEDIAKIT_RESPONSE_BYTES:
            raise ValueError("submitted_task_record response size is invalid")
        request_ids = record.get("provider_request_id_sha256s")
        if not isinstance(request_ids, list) or len(request_ids) > 2:
            raise ValueError("submitted_task_record request-id list is invalid")
        for index, digest in enumerate(request_ids):
            _hex_digest(
                digest,
                field=f"submitted_task_record.provider_request_id_sha256s[{index}]",
            )
        record["task_id"] = task_id
        safe_projection = {key: item for key, item in record.items() if key != "task_id"}
        validate_credential_free_payload(
            safe_projection,
            field="submitted_task_record_event_projection",
        )
        return record, safe_projection

    @staticmethod
    def _provider_submitted_task_record(
        value: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Strictly dispatch submit evidence by provider, capability and contract."""

        if not isinstance(value, dict):
            raise ValueError("submitted_task_record must match the exact recovery contract")
        dispatch = (
            value.get("provider"),
            value.get("capability"),
            value.get("contract_version"),
        )
        if dispatch == (
            "volcengine-mediakit",
            _MEDIAKIT_REMUX_CAPABILITY,
            MEDIAKIT_PROVIDER_SUBMITTED_TASK_CONTRACT_VERSION,
        ):
            return PersonalIPPaidCallRepository._provider_remux_submitted_task_record(value)
        if dispatch == (
            "volcengine-mediakit",
            _MEDIAKIT_VIDEO_STRATEGY_CAPABILITY,
            MEDIAKIT_VIDEO_STRATEGY_PROVIDER_SUBMITTED_TASK_CONTRACT_VERSION,
        ):
            return PersonalIPPaidCallRepository._provider_video_strategy_submitted_task_record(value)
        raise ValueError("submitted_task_record contract dispatch is unsupported")

    async def _replay_or_none(
        self,
        session: AsyncSession,
        row: PersonalIPPaidCallScopeRow,
        *,
        expected_event: PersonalIPPaidCallEventRow,
    ) -> dict[str, Any] | None:
        existing = await self._existing_event(
            session,
            scope_id=row.id,
            event_key=expected_event.event_key,
        )
        if existing is None:
            return None
        if existing.event_digest != expected_event.event_digest:
            raise ValueError("event_key already records a different paid-call transition")
        return await self._result(
            session,
            row,
            operation_event=existing,
            idempotent_replay=True,
        )

    async def _replay_matching_fields_or_none(
        self,
        session: AsyncSession,
        row: PersonalIPPaidCallScopeRow,
        *,
        event_key: str,
        event_types: set[str],
        execution_run_id: str | None,
        amount_micros: int | None,
        proof_digest: str | None,
        admission_jti_hash: str | None,
        reason_code: str | None = None,
    ) -> dict[str, Any] | None:
        """Replay a transition whose original amount depended on prior state."""

        existing = await self._existing_event(session, scope_id=row.id, event_key=event_key)
        if existing is None:
            return None
        if (
            existing.request_digest != row.request_digest
            or existing.event_type not in event_types
            or existing.execution_run_id != execution_run_id
            or existing.amount_micros != amount_micros
            or existing.proof_digest != proof_digest
            or existing.admission_jti_hash != admission_jti_hash
            or (reason_code is not None and existing.reason_code != reason_code)
        ):
            raise ValueError("event_key already records a different paid-call transition")
        return await self._result(
            session,
            row,
            operation_event=existing,
            idempotent_replay=True,
        )

    async def request_call(
        self,
        *,
        owner_user_id: str,
        request_key: str,
        scope_kind: str,
        thread_id: str,
        origin_run_id: str,
        server_name: str,
        tool_name: str,
        tool_args_sha256: str,
        provider: str,
        capability: str,
        model: str,
        sku: str,
        provider_label: str,
        capability_label: str,
        object_ref_label: str,
        source_duration_millis: int,
        source_sha256: str,
        stage_digest: str,
        provider_request_sha256: str,
        maximum_amount_micros: int | None,
        currency: str,
        billing_basis: str,
        policy_version: str,
        price_version: str,
        provider_input_attested: bool,
        evidence_coverage: str,
        warning_code: str | None,
        expires_at: datetime,
        price_status: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Create or replay one immutable exact-call request."""

        occurred_at = _utc(now or datetime.now(UTC), field="now")
        expiry = _utc(expires_at, field="expires_at")
        if expiry <= occurred_at:
            raise ValueError("paid-call request must expire in the future")
        if scope_kind != "run":
            raise ValueError("scope_kind must be run")
        if not isinstance(provider_input_attested, bool):
            raise ValueError("provider_input_attested must be a boolean")
        coverage = str(evidence_coverage or "").strip().lower()
        if coverage not in {"partial", "complete"}:
            raise ValueError("evidence_coverage must be partial or complete")
        warning = _clean_optional(warning_code, field="warning_code", limit=80)
        if not provider_input_attested and coverage != "partial":
            raise ValueError("unattested provider input must remain partial evidence")
        if not provider_input_attested and warning is None:
            raise ValueError("unattested provider input requires a warning_code")

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        key = _clean_required(request_key, field="request_key", limit=256)
        maximum_micros = None
        if maximum_amount_micros is not None:
            maximum_micros = _micros(
                maximum_amount_micros,
                field="maximum_amount_micros",
                positive=True,
            )
        price_state = str(price_status or "").strip().lower()
        if not price_state:
            price_state = "quoted" if maximum_micros is not None else "unknown"
        if price_state == "unknown" and maximum_micros is not None:
            raise ValueError("unknown provider price cannot be represented as a quote")
        if price_state in {"quoted", "operator_capped"} and maximum_micros is None:
            raise ValueError(f"{price_state} paid-call request requires a positive maximum")
        if price_state not in {"unknown", "quoted", "operator_capped"}:
            raise ValueError("price_status must be unknown, quoted, or operator_capped")

        normalized_provider = _clean_required(provider, field="provider", limit=80).lower()
        normalized_capability = _clean_required(capability, field="capability", limit=80).lower()
        normalized_policy = _clean_required(
            policy_version,
            field="policy_version",
            limit=80,
        )
        if price_state == "operator_capped" and (normalized_provider != "volcengine-mediakit" or _OPERATOR_CAPPED_MEDIAKIT_POLICY_BY_CAPABILITY.get(normalized_capability) != normalized_policy):
            raise ValueError("operator-capped provider-charge admission is restricted to explicit MediaKit ASR or allowlisted evidence-stage policies")

        values = {
            "owner_user_id": owner,
            "request_key": key,
            "scope_kind": "run",
            "thread_id": _clean_required(thread_id, field="thread_id", limit=64),
            "origin_run_id": _clean_required(origin_run_id, field="origin_run_id", limit=64),
            "execution_run_id": None,
            "server_name": _clean_required(server_name, field="server_name", limit=128).lower(),
            "tool_name": _clean_required(tool_name, field="tool_name", limit=128),
            "tool_args_sha256": _hex_digest(tool_args_sha256, field="tool_args_sha256"),
            "provider": normalized_provider,
            "capability": normalized_capability,
            "model": _clean_required(model, field="model", limit=160),
            "sku": _clean_required(sku, field="sku", limit=160).lower(),
            "provider_label": _safe_summary(provider_label, field="provider_label", limit=120),
            "capability_label": _safe_summary(capability_label, field="capability_label", limit=120),
            "object_ref_label": _safe_summary(
                object_ref_label,
                field="object_ref_label",
                limit=96,
                object_ref=True,
            ),
            "source_duration_millis": _micros(
                source_duration_millis,
                field="source_duration_millis",
                positive=True,
            ),
            "source_sha256": _hex_digest(source_sha256, field="source_sha256"),
            "stage_digest": _hex_digest(stage_digest, field="stage_digest"),
            "provider_request_sha256": _hex_digest(
                provider_request_sha256,
                field="provider_request_sha256",
            ),
            "maximum_amount_micros": maximum_micros,
            "currency": str(currency or "").strip().upper(),
            "billing_basis": _safe_summary(billing_basis, field="billing_basis", limit=160),
            "price_status": price_state,
            "policy_version": normalized_policy,
            "price_version": _clean_required(price_version, field="price_version", limit=80),
            "provider_input_attested": provider_input_attested,
            "evidence_coverage": coverage,
            "warning_code": warning,
            "expires_at": expiry,
        }
        if not _CURRENCY.fullmatch(values["currency"]):
            raise ValueError("currency must be a three-letter uppercase code")
        digest_input = {
            "contract_version": PAID_CALL_SCOPE_CONTRACT_VERSION,
            **{key: value for key, value in values.items() if key != "expires_at"},
            "expires_at": _iso(expiry),
        }
        request_digest = _digest(digest_input)
        requested_payload = self._requested_payload(values)

        async with self._sf() as session:
            try:
                await self._begin_request_lock(session, owner_user_id=owner, request_key=key)
                existing = (
                    await session.execute(
                        select(PersonalIPPaidCallScopeRow).where(
                            PersonalIPPaidCallScopeRow.owner_user_id == owner,
                            PersonalIPPaidCallScopeRow.request_key == key,
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    if existing.request_digest != request_digest:
                        raise ValueError("request_key already records a different paid-call request")
                    requested = await self._existing_event(session, scope_id=existing.id, event_key="requested")
                    if requested is None:
                        raise RuntimeError("paid-call scope is missing its requested event")
                    return await self._result(
                        session,
                        existing,
                        operation_event=requested,
                        idempotent_replay=True,
                    )

                row = PersonalIPPaidCallScopeRow(
                    id=f"paid-call-scope-{uuid.uuid4().hex}",
                    request_digest=request_digest,
                    status="requested",
                    event_count=0,
                    reserved_amount_micros=0,
                    settled_amount_micros=None,
                    admission_jti_hash=None,
                    created_at=occurred_at,
                    updated_at=occurred_at,
                    **values,
                )
                requested = self._event_row(
                    row,
                    event_key="requested",
                    event_type="requested",
                    execution_run_id=None,
                    amount_micros=values["maximum_amount_micros"],
                    payload=requested_payload,
                    occurred_at=occurred_at,
                )
                row.event_count = 1
                # These deliberately relationship-free audit rows need an
                # explicit dependency flush so SQLite cannot insert the child
                # before its scope while foreign keys are enabled.
                session.add(row)
                await session.flush()
                session.add(requested)
                await session.commit()
                return await self._result(
                    session,
                    row,
                    operation_event=requested,
                    idempotent_replay=False,
                )
            except Exception:
                await session.rollback()
                raise

    async def get(self, scope_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        scope = _clean_required(scope_id, field="scope_id", limit=64)
        async with self._sf() as session:
            row = (
                await session.execute(
                    select(PersonalIPPaidCallScopeRow).where(
                        PersonalIPPaidCallScopeRow.id == scope,
                        PersonalIPPaidCallScopeRow.owner_user_id == owner,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            result = self._scope_dict(row)
            result["events"] = await self._events(session, row.id)
            return result

    async def list_thread(self, *, owner_user_id: str, thread_id: str) -> list[dict[str, Any]]:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        thread = _clean_required(thread_id, field="thread_id", limit=64)
        async with self._sf() as session:
            rows = (
                (
                    await session.execute(
                        select(PersonalIPPaidCallScopeRow)
                        .where(
                            PersonalIPPaidCallScopeRow.owner_user_id == owner,
                            PersonalIPPaidCallScopeRow.thread_id == thread,
                        )
                        .order_by(PersonalIPPaidCallScopeRow.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [self._scope_dict(row) for row in rows]

    async def find_approved_for_invocation(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
        server_name: str,
        tool_name: str,
        tool_args_sha256: str,
        provider: str,
        capability: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Resolve one exact unexpired approval without reserving or admitting it."""

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        thread = _clean_required(thread_id, field="thread_id", limit=64)
        server = _clean_required(server_name, field="server_name", limit=128).lower()
        tool = _clean_required(tool_name, field="tool_name", limit=128)
        args_digest = _hex_digest(tool_args_sha256, field="tool_args_sha256")
        provider_key = _clean_required(provider, field="provider", limit=80).lower()
        capability_key = _clean_required(capability, field="capability", limit=80).lower()
        observed_at = _utc(now or datetime.now(UTC), field="now")
        async with self._sf() as session:
            rows = (
                (
                    await session.execute(
                        select(PersonalIPPaidCallScopeRow)
                        .where(
                            PersonalIPPaidCallScopeRow.owner_user_id == owner,
                            PersonalIPPaidCallScopeRow.thread_id == thread,
                            PersonalIPPaidCallScopeRow.server_name == server,
                            PersonalIPPaidCallScopeRow.tool_name == tool,
                            PersonalIPPaidCallScopeRow.tool_args_sha256 == args_digest,
                            PersonalIPPaidCallScopeRow.provider == provider_key,
                            PersonalIPPaidCallScopeRow.capability == capability_key,
                            PersonalIPPaidCallScopeRow.status == "approved",
                            PersonalIPPaidCallScopeRow.execution_run_id.is_(None),
                            PersonalIPPaidCallScopeRow.expires_at > observed_at,
                        )
                        .order_by(PersonalIPPaidCallScopeRow.created_at.asc())
                        .limit(2)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                return None
            if len(rows) != 1:
                raise ValueError("multiple approved paid-call requests match the exact invocation")
            return self._scope_dict(rows[0])

    async def admit_next_operator_capped_evidence_stage_exact(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
        execution_run_id: str,
        server_name: str,
        tool_name: str,
        tool_args_sha256: str,
        provider: str,
        trusted_stage_policies: Iterable[OperatorCappedEvidenceStagePolicy],
        currency: str,
        reservation_event_key: str,
        admission_event_key: str,
        admission_jti: str,
        admission_proof_digest: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Atomically select and admit one approved operator-capped stage.

        The local amount is an admission risk limit, not a promise that the
        provider will cap its invoice.  The caller supplies a trusted set of
        allowlisted capability, policy, amount and duration bindings.  Zero
        matches returns ``None``; more than one match fails before any state
        transition; exactly one is reserved and admitted in this transaction.
        """

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        thread = _clean_required(thread_id, field="thread_id", limit=64)
        execution = _clean_required(
            execution_run_id,
            field="execution_run_id",
            limit=64,
        )
        server = _clean_required(server_name, field="server_name", limit=128).lower()
        tool = _clean_required(tool_name, field="tool_name", limit=128)
        args_digest = _hex_digest(tool_args_sha256, field="tool_args_sha256")
        provider_key = _clean_required(provider, field="provider", limit=80).lower()
        if provider_key != "volcengine-mediakit":
            raise ValueError("operator-capped evidence admission requires MediaKit")
        stage_policies = _trusted_operator_capped_stage_policies(trusted_stage_policies)
        normalized_currency = str(currency or "").strip().upper()
        if normalized_currency != "CNY":
            raise ValueError("operator-capped MediaKit evidence admission requires CNY")
        reservation_key = _clean_required(
            reservation_event_key,
            field="reservation_event_key",
            limit=256,
        )
        admission_key = _clean_required(
            admission_event_key,
            field="admission_event_key",
            limit=256,
        )
        if reservation_key == admission_key:
            raise ValueError("reservation and admission event keys must differ")
        jti = _clean_required(admission_jti, field="admission_jti", limit=256)
        if len(jti) < 16:
            raise ValueError("admission_jti must contain at least 16 characters")
        jti_hash = hashlib.sha256(jti.encode("utf-8")).hexdigest()
        proof = _hex_digest(
            admission_proof_digest,
            field="admission_proof_digest",
        )
        occurred_at = _utc(now or datetime.now(UTC), field="now")

        async with self._sf() as session:
            try:
                dialect = session.get_bind().dialect.name
                if dialect == "sqlite":
                    await session.execute(text("BEGIN IMMEDIATE"))
                stage_predicates = tuple(
                    and_(
                        PersonalIPPaidCallScopeRow.capability == stage.capability,
                        PersonalIPPaidCallScopeRow.policy_version == stage.policy_version,
                        PersonalIPPaidCallScopeRow.maximum_amount_micros == stage.local_admission_limit_micros,
                        PersonalIPPaidCallScopeRow.source_duration_millis <= stage.max_source_duration_millis,
                    )
                    for stage in stage_policies
                )
                statement = (
                    select(PersonalIPPaidCallScopeRow)
                    .where(
                        PersonalIPPaidCallScopeRow.owner_user_id == owner,
                        PersonalIPPaidCallScopeRow.thread_id == thread,
                        PersonalIPPaidCallScopeRow.execution_run_id.is_(None),
                        PersonalIPPaidCallScopeRow.server_name == server,
                        PersonalIPPaidCallScopeRow.tool_name == tool,
                        PersonalIPPaidCallScopeRow.tool_args_sha256 == args_digest,
                        PersonalIPPaidCallScopeRow.provider == provider_key,
                        or_(*stage_predicates),
                        PersonalIPPaidCallScopeRow.currency == normalized_currency,
                        PersonalIPPaidCallScopeRow.price_status == "operator_capped",
                        PersonalIPPaidCallScopeRow.status == "approved",
                        PersonalIPPaidCallScopeRow.expires_at > occurred_at,
                    )
                    .order_by(PersonalIPPaidCallScopeRow.created_at.asc())
                    .limit(2)
                )
                if dialect != "sqlite":
                    statement = statement.with_for_update()
                rows = (await session.execute(statement)).scalars().all()
                if not rows:
                    return None
                if len(rows) != 1:
                    raise AmbiguousOperatorCappedEvidenceStages(row.capability for row in rows)
                row = rows[0]
                if await self._existing_event(
                    session,
                    scope_id=row.id,
                    event_key=reservation_key,
                ) or await self._existing_event(
                    session,
                    scope_id=row.id,
                    event_key=admission_key,
                ):
                    raise ValueError("paid-call transition event key was already used")
                local_limit = int(row.maximum_amount_micros)

                reserved = self._event_row(
                    row,
                    event_key=reservation_key,
                    event_type="reserved",
                    execution_run_id=execution,
                    amount_micros=local_limit,
                    reason_code="operator_capped_provider_charge_unavailable",
                    occurred_at=occurred_at,
                )
                row.status = "reserved"
                row.execution_run_id = execution
                row.reserved_amount_micros = local_limit
                row.event_count += 1
                session.add(reserved)

                admitted = self._event_row(
                    row,
                    event_key=admission_key,
                    event_type="admitted",
                    execution_run_id=execution,
                    amount_micros=local_limit,
                    proof_digest=proof,
                    admission_jti_hash=jti_hash,
                    reason_code="operator_capped_evidence_stage",
                    occurred_at=occurred_at,
                )
                row.status = "admitted"
                row.admission_jti_hash = jti_hash
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(admitted)
                try:
                    await session.commit()
                except IntegrityError as exc:
                    await session.rollback()
                    raise ValueError("admission_jti has already been consumed") from exc
                return await self._result(
                    session,
                    row,
                    operation_event=admitted,
                    idempotent_replay=False,
                )
            except Exception:
                await session.rollback()
                raise

    async def admit_operator_capped_asr_exact(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
        execution_run_id: str,
        server_name: str,
        tool_name: str,
        tool_args_sha256: str,
        max_source_duration_millis: int,
        local_admission_limit_micros: int,
        currency: str,
        reservation_event_key: str,
        admission_event_key: str,
        admission_jti: str,
        admission_proof_digest: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Compatibility wrapper for the original single-capability ASR API."""

        return await self.admit_next_operator_capped_evidence_stage_exact(
            owner_user_id=owner_user_id,
            thread_id=thread_id,
            execution_run_id=execution_run_id,
            server_name=server_name,
            tool_name=tool_name,
            tool_args_sha256=tool_args_sha256,
            provider="volcengine-mediakit",
            trusted_stage_policies=(
                OperatorCappedEvidenceStagePolicy(
                    capability="asr",
                    policy_version=EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
                    local_admission_limit_micros=local_admission_limit_micros,
                    max_source_duration_millis=max_source_duration_millis,
                ),
            ),
            currency=currency,
            reservation_event_key=reservation_event_key,
            admission_event_key=admission_event_key,
            admission_jti=admission_jti,
            admission_proof_digest=admission_proof_digest,
            now=now,
        )

    async def mark_operator_capped_asr_reconciliation_exact(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
        execution_run_id: str,
        server_name: str,
        tool_name: str,
        tool_args_sha256: str,
        source_duration_millis: int,
        source_sha256: str,
        stage_digest: str,
        provider_request_sha256: str,
        event_key: str,
        execution_outcome_digest: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Hold the local reservation when the provider omits actual cost."""

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        thread = _clean_required(thread_id, field="thread_id", limit=64)
        execution = _clean_required(
            execution_run_id,
            field="execution_run_id",
            limit=64,
        )
        server = _clean_required(server_name, field="server_name", limit=128).lower()
        tool = _clean_required(tool_name, field="tool_name", limit=128)
        args_digest = _hex_digest(tool_args_sha256, field="tool_args_sha256")
        duration = _micros(
            source_duration_millis,
            field="source_duration_millis",
            positive=True,
        )
        source_digest = _hex_digest(source_sha256, field="source_sha256")
        stage = _hex_digest(stage_digest, field="stage_digest")
        provider_request = _hex_digest(
            provider_request_sha256,
            field="provider_request_sha256",
        )
        key = _clean_required(event_key, field="event_key", limit=256)
        proof = _hex_digest(
            execution_outcome_digest,
            field="execution_outcome_digest",
        )
        occurred_at = _utc(now or datetime.now(UTC), field="now")

        async with self._sf() as session:
            try:
                dialect = session.get_bind().dialect.name
                if dialect == "sqlite":
                    await session.execute(text("BEGIN IMMEDIATE"))
                statement = (
                    select(PersonalIPPaidCallScopeRow)
                    .where(
                        PersonalIPPaidCallScopeRow.owner_user_id == owner,
                        PersonalIPPaidCallScopeRow.thread_id == thread,
                        PersonalIPPaidCallScopeRow.execution_run_id == execution,
                        PersonalIPPaidCallScopeRow.server_name == server,
                        PersonalIPPaidCallScopeRow.tool_name == tool,
                        PersonalIPPaidCallScopeRow.tool_args_sha256 == args_digest,
                        PersonalIPPaidCallScopeRow.provider == "volcengine-mediakit",
                        PersonalIPPaidCallScopeRow.capability == "asr",
                        PersonalIPPaidCallScopeRow.source_duration_millis == duration,
                        PersonalIPPaidCallScopeRow.source_sha256 == source_digest,
                        PersonalIPPaidCallScopeRow.stage_digest == stage,
                        PersonalIPPaidCallScopeRow.provider_request_sha256 == provider_request,
                        PersonalIPPaidCallScopeRow.currency == "CNY",
                        PersonalIPPaidCallScopeRow.price_status == "operator_capped",
                        PersonalIPPaidCallScopeRow.policy_version == EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
                        PersonalIPPaidCallScopeRow.status.in_({"admitted", "reconciliation_required"}),
                    )
                    .limit(2)
                )
                if dialect != "sqlite":
                    statement = statement.with_for_update()
                rows = (await session.execute(statement)).scalars().all()
                if not rows:
                    return None
                if len(rows) != 1:
                    raise ValueError("multiple admitted operator-capped ASR calls match the exact result")
                row = rows[0]
                expected = self._event_row(
                    row,
                    event_key=key,
                    event_type="reconciliation_required",
                    execution_run_id=execution,
                    amount_micros=None,
                    proof_digest=proof,
                    reason_code="actual_amount_unknown",
                    occurred_at=occurred_at,
                )
                replay = await self._replay_or_none(
                    session,
                    row,
                    expected_event=expected,
                )
                if replay is not None:
                    return replay
                if row.status != "admitted":
                    raise ValueError("new unknown-cost reconciliation requires admitted status")
                row.status = "reconciliation_required"
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(expected)
                await session.commit()
                return await self._result(
                    session,
                    row,
                    operation_event=expected,
                    idempotent_replay=False,
                )
            except Exception:
                await session.rollback()
                raise

    async def mark_operator_capped_asr_invocation_unresolved(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
        execution_run_id: str,
        server_name: str,
        tool_name: str,
        tool_args_sha256: str,
        event_key: str,
        execution_outcome_digest: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Hold an admitted invocation when no exact provider result exists.

        This is the exception/download/invalid-result safety net.  It uses the
        outer invocation that was already atomically bound at admission and
        deliberately does not guess whether the provider was called.
        """

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        thread = _clean_required(thread_id, field="thread_id", limit=64)
        execution = _clean_required(
            execution_run_id,
            field="execution_run_id",
            limit=64,
        )
        server = _clean_required(server_name, field="server_name", limit=128).lower()
        tool = _clean_required(tool_name, field="tool_name", limit=128)
        args_digest = _hex_digest(tool_args_sha256, field="tool_args_sha256")
        key = _clean_required(event_key, field="event_key", limit=256)
        proof = _hex_digest(
            execution_outcome_digest,
            field="execution_outcome_digest",
        )
        occurred_at = _utc(now or datetime.now(UTC), field="now")
        async with self._sf() as session:
            try:
                dialect = session.get_bind().dialect.name
                if dialect == "sqlite":
                    await session.execute(text("BEGIN IMMEDIATE"))
                statement = (
                    select(PersonalIPPaidCallScopeRow)
                    .where(
                        PersonalIPPaidCallScopeRow.owner_user_id == owner,
                        PersonalIPPaidCallScopeRow.thread_id == thread,
                        PersonalIPPaidCallScopeRow.execution_run_id == execution,
                        PersonalIPPaidCallScopeRow.server_name == server,
                        PersonalIPPaidCallScopeRow.tool_name == tool,
                        PersonalIPPaidCallScopeRow.tool_args_sha256 == args_digest,
                        PersonalIPPaidCallScopeRow.provider == "volcengine-mediakit",
                        PersonalIPPaidCallScopeRow.capability == "asr",
                        PersonalIPPaidCallScopeRow.price_status == "operator_capped",
                        PersonalIPPaidCallScopeRow.policy_version == EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
                        PersonalIPPaidCallScopeRow.status == "admitted",
                    )
                    .limit(2)
                )
                if dialect != "sqlite":
                    statement = statement.with_for_update()
                rows = (await session.execute(statement)).scalars().all()
                if not rows:
                    return None
                if len(rows) != 1:
                    raise ValueError("multiple admitted operator-capped ASR calls match the invocation")
                row = rows[0]
                event = self._event_row(
                    row,
                    event_key=key,
                    event_type="reconciliation_required",
                    execution_run_id=execution,
                    amount_micros=None,
                    proof_digest=proof,
                    reason_code="provider_execution_outcome_unresolved",
                    occurred_at=occurred_at,
                )
                row.status = "reconciliation_required"
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(event)
                await session.commit()
                return await self._result(
                    session,
                    row,
                    operation_event=event,
                    idempotent_replay=False,
                )
            except Exception:
                await session.rollback()
                raise

    async def mark_operator_capped_evidence_stage_invocation_unresolved(
        self,
        *,
        scope_id: str,
        admission_jti_sha256: str,
        owner_user_id: str,
        thread_id: str,
        execution_run_id: str,
        server_name: str,
        tool_name: str,
        tool_args_sha256: str,
        provider: str,
        capability: str,
        policy_version: str,
        event_key: str,
        execution_outcome_digest: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Idempotently hold one exact admitted route-group stage.

        This is the generic transport-compensation seam for the independently
        approved remux and Video Understanding stages.  It cannot select a
        stage from user input: the capability and policy pair must be one of
        the repository's fixed MediaKit operator-capped bindings.
        """

        scope = _clean_required(scope_id, field="scope_id", limit=64)
        admission_jti_hash = _hex_digest(
            admission_jti_sha256,
            field="admission_jti_sha256",
        )
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        thread = _clean_required(thread_id, field="thread_id", limit=64)
        execution = _clean_required(
            execution_run_id,
            field="execution_run_id",
            limit=64,
        )
        server = _clean_required(server_name, field="server_name", limit=128).lower()
        tool = _clean_required(tool_name, field="tool_name", limit=128)
        args_digest = _hex_digest(tool_args_sha256, field="tool_args_sha256")
        provider_key = _clean_required(provider, field="provider", limit=80).lower()
        if provider_key != "volcengine-mediakit":
            raise ValueError("operator-capped evidence compensation requires MediaKit")
        capability_key = _clean_required(
            capability,
            field="capability",
            limit=80,
        ).lower()
        policy = _clean_required(
            policy_version,
            field="policy_version",
            limit=80,
        )
        if _OPERATOR_CAPPED_MEDIAKIT_POLICY_BY_CAPABILITY.get(capability_key) != policy:
            raise ValueError("operator-capped evidence compensation policy is invalid")
        key = _clean_required(event_key, field="event_key", limit=256)
        proof = _hex_digest(
            execution_outcome_digest,
            field="execution_outcome_digest",
        )
        occurred_at = _utc(now or datetime.now(UTC), field="now")

        async with self._sf() as session:
            try:
                dialect = session.get_bind().dialect.name
                if dialect == "sqlite":
                    await session.execute(text("BEGIN IMMEDIATE"))
                statement = (
                    select(PersonalIPPaidCallScopeRow)
                    .where(
                        PersonalIPPaidCallScopeRow.id == scope,
                        PersonalIPPaidCallScopeRow.admission_jti_hash == admission_jti_hash,
                        PersonalIPPaidCallScopeRow.owner_user_id == owner,
                        PersonalIPPaidCallScopeRow.thread_id == thread,
                        PersonalIPPaidCallScopeRow.execution_run_id == execution,
                        PersonalIPPaidCallScopeRow.server_name == server,
                        PersonalIPPaidCallScopeRow.tool_name == tool,
                        PersonalIPPaidCallScopeRow.tool_args_sha256 == args_digest,
                        PersonalIPPaidCallScopeRow.provider == provider_key,
                        PersonalIPPaidCallScopeRow.capability == capability_key,
                        PersonalIPPaidCallScopeRow.price_status == "operator_capped",
                        PersonalIPPaidCallScopeRow.policy_version == policy,
                        PersonalIPPaidCallScopeRow.status.in_({"admitted", "reconciliation_required"}),
                    )
                    .limit(2)
                )
                if dialect != "sqlite":
                    statement = statement.with_for_update()
                rows = (await session.execute(statement)).scalars().all()
                if not rows:
                    return None
                if len(rows) != 1:
                    raise ValueError("multiple admitted operator-capped evidence stages match the invocation")
                row = rows[0]
                event = self._event_row(
                    row,
                    event_key=key,
                    event_type="reconciliation_required",
                    execution_run_id=execution,
                    amount_micros=None,
                    proof_digest=proof,
                    reason_code="provider_execution_outcome_unresolved",
                    occurred_at=occurred_at,
                )
                replay = await self._replay_matching_fields_or_none(
                    session,
                    row,
                    event_key=key,
                    event_types={"reconciliation_required"},
                    execution_run_id=execution,
                    amount_micros=None,
                    proof_digest=proof,
                    admission_jti_hash=None,
                    reason_code="provider_execution_outcome_unresolved",
                )
                if replay is not None:
                    return replay
                if row.status != "admitted":
                    raise ValueError("new unresolved evidence-stage outcome requires admitted status")
                row.status = "reconciliation_required"
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(event)
                await session.commit()
                return await self._result(
                    session,
                    row,
                    operation_event=event,
                    idempotent_replay=False,
                )
            except Exception:
                await session.rollback()
                raise

    async def _decision(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        decision: str,
        proof_digest: str,
        reason_code: str | None,
        expected_event_count: int | None,
        now: datetime | None,
    ) -> dict[str, Any] | None:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        scope = _clean_required(scope_id, field="scope_id", limit=64)
        key = _clean_required(event_key, field="event_key", limit=256)
        proof = _hex_digest(proof_digest, field="proof_digest")
        reason = _clean_optional(reason_code, field="reason_code", limit=80)
        occurred_at = _utc(now or datetime.now(UTC), field="now")
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        if decision == "rejected" and reason is None:
            raise ValueError("rejected decision requires reason_code")

        async with self._sf() as session:
            try:
                row = await self._lock_scope(session, owner_user_id=owner, scope_id=scope)
                if row is None:
                    return None
                self._assert_request_binding(row, expected_request_digest)
                expected = self._event_row(
                    row,
                    event_key=key,
                    event_type=decision,
                    execution_run_id=None,
                    proof_digest=proof,
                    reason_code=reason,
                    occurred_at=occurred_at,
                )
                replay = await self._replay_or_none(session, row, expected_event=expected)
                if replay is not None:
                    return replay
                self._assert_version(row, expected_event_count)
                if row.status != "requested":
                    raise ValueError("paid-call decision requires requested status")
                if decision == "approved" and occurred_at >= _utc(row.expires_at, field="expires_at"):
                    raise ValueError("expired paid-call request cannot be approved")
                if decision == "approved" and (row.price_status not in {"quoted", "operator_capped"} or row.maximum_amount_micros is None or row.maximum_amount_micros <= 0):
                    raise ValueError("paid-call request cannot be approved without a positive quoted maximum or explicit operator cap")
                row.status = decision
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(expected)
                await session.commit()
                return await self._result(session, row, operation_event=expected, idempotent_replay=False)
            except Exception:
                await session.rollback()
                raise

    async def approve(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        approval_digest: str,
        expected_event_count: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        return await self._decision(
            scope_id,
            owner_user_id=owner_user_id,
            event_key=event_key,
            expected_request_digest=expected_request_digest,
            decision="approved",
            proof_digest=approval_digest,
            reason_code=None,
            expected_event_count=expected_event_count,
            now=now,
        )

    async def reject(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        decision_digest: str,
        reason_code: str,
        expected_event_count: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        return await self._decision(
            scope_id,
            owner_user_id=owner_user_id,
            event_key=event_key,
            expected_request_digest=expected_request_digest,
            decision="rejected",
            proof_digest=decision_digest,
            reason_code=reason_code,
            expected_event_count=expected_event_count,
            now=now,
        )

    async def reserve(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        execution_run_id: str,
        amount_micros: int,
        expected_event_count: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        scope = _clean_required(scope_id, field="scope_id", limit=64)
        key = _clean_required(event_key, field="event_key", limit=256)
        execution = _clean_required(execution_run_id, field="execution_run_id", limit=64)
        amount = _micros(amount_micros, field="amount_micros", positive=True)
        occurred_at = _utc(now or datetime.now(UTC), field="now")
        async with self._sf() as session:
            try:
                row = await self._lock_scope(session, owner_user_id=owner, scope_id=scope)
                if row is None:
                    return None
                self._assert_request_binding(row, expected_request_digest)
                if row.execution_run_id is not None:
                    self._assert_execution_binding(row, execution)
                if row.maximum_amount_micros is None:
                    raise ValueError("paid-call reservation requires a positive quoted maximum")
                event_type = "reserved" if amount <= row.maximum_amount_micros else "budget_rejected"
                reason = None if event_type == "reserved" else "maximum_amount_exceeded"
                expected = self._event_row(
                    row,
                    event_key=key,
                    event_type=event_type,
                    execution_run_id=execution,
                    amount_micros=amount,
                    reason_code=reason,
                    occurred_at=occurred_at,
                )
                replay = await self._replay_or_none(session, row, expected_event=expected)
                if replay is not None:
                    return replay
                self._assert_version(row, expected_event_count)
                if row.status != "approved":
                    raise ValueError("paid-call reservation requires approved status")
                if occurred_at >= _utc(row.expires_at, field="expires_at"):
                    raise ValueError("expired paid-call request cannot reserve budget")
                row.status = event_type
                row.execution_run_id = execution
                row.reserved_amount_micros = amount if event_type == "reserved" else 0
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(expected)
                await session.commit()
                return await self._result(session, row, operation_event=expected, idempotent_replay=False)
            except Exception:
                await session.rollback()
                raise

    async def admit(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        execution_run_id: str,
        admission_jti: str,
        admission_proof_digest: str,
        expected_event_count: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        scope = _clean_required(scope_id, field="scope_id", limit=64)
        key = _clean_required(event_key, field="event_key", limit=256)
        execution = _clean_required(execution_run_id, field="execution_run_id", limit=64)
        jti = _clean_required(admission_jti, field="admission_jti", limit=256)
        if len(jti) < 16:
            raise ValueError("admission_jti must contain at least 16 characters")
        jti_hash = hashlib.sha256(jti.encode("utf-8")).hexdigest()
        proof = _hex_digest(admission_proof_digest, field="admission_proof_digest")
        occurred_at = _utc(now or datetime.now(UTC), field="now")
        async with self._sf() as session:
            try:
                row = await self._lock_scope(session, owner_user_id=owner, scope_id=scope)
                if row is None:
                    return None
                self._assert_request_binding(row, expected_request_digest)
                self._assert_execution_binding(row, execution)
                existing = await self._existing_event(session, scope_id=row.id, event_key=key)
                if existing is not None:
                    replay = await self._replay_matching_fields_or_none(
                        session,
                        row,
                        event_key=key,
                        event_types={"admitted"},
                        execution_run_id=execution,
                        amount_micros=existing.amount_micros,
                        proof_digest=proof,
                        admission_jti_hash=jti_hash,
                    )
                    if replay is not None:
                        return replay
                expected = self._event_row(
                    row,
                    event_key=key,
                    event_type="admitted",
                    execution_run_id=execution,
                    amount_micros=row.reserved_amount_micros,
                    proof_digest=proof,
                    admission_jti_hash=jti_hash,
                    occurred_at=occurred_at,
                )
                self._assert_version(row, expected_event_count)
                if row.status != "reserved":
                    raise ValueError("paid-call admission requires reserved status")
                if occurred_at >= _utc(row.expires_at, field="expires_at"):
                    raise ValueError("expired paid-call request cannot be admitted")
                row.status = "admitted"
                row.admission_jti_hash = jti_hash
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(expected)
                try:
                    await session.commit()
                except IntegrityError as exc:
                    await session.rollback()
                    raise ValueError("admission_jti has already been consumed") from exc
                return await self._result(session, row, operation_event=expected, idempotent_replay=False)
            except Exception:
                await session.rollback()
                raise

    async def begin_provider_task_submission(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        execution_run_id: str,
        capability: str,
        source_sha256: str,
        client_token: str,
        submission_envelope: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Persist the exact encrypted request before a MediaKit submission."""

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        scope = _clean_required(scope_id, field="scope_id", limit=64)
        key = _clean_required(event_key, field="event_key", limit=256)
        execution = _clean_required(
            execution_run_id,
            field="execution_run_id",
            limit=64,
        )
        capability_key = _clean_required(
            capability,
            field="capability",
            limit=80,
        ).lower()
        source_digest = _hex_digest(source_sha256, field="source_sha256")
        if capability_key == _MEDIAKIT_VIDEO_STRATEGY_CAPABILITY:
            if not isinstance(client_token, str) or not 1 <= len(client_token) <= 64 or any(ord(character) < 32 or ord(character) > 126 for character in client_token):
                raise ValueError("client_token must be printable ASCII up to 64 characters")
            token = client_token
        else:
            token = _clean_required(client_token, field="client_token", limit=1024)
        token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        submission, submission_json, submission_digest = self._provider_submission(
            submission_envelope,
            capability=capability_key,
            source_sha256=source_digest,
            client_token=token,
        )
        occurred_at = _utc(now or datetime.now(UTC), field="now")
        async with self._sf() as session:
            try:
                row = await self._lock_scope(
                    session,
                    owner_user_id=owner,
                    scope_id=scope,
                )
                if row is None:
                    return None
                self._assert_request_binding(row, expected_request_digest)
                self._assert_execution_binding(row, execution)
                if row.provider != "volcengine-mediakit":
                    raise ValueError("recoverable provider task requires MediaKit")
                if row.capability != capability_key or row.source_sha256 != source_digest:
                    raise ValueError("provider task does not match the admitted capability and source")
                if capability_key == _MEDIAKIT_VIDEO_STRATEGY_CAPABILITY and row.provider_request_sha256 != submission["request_sha256"]:
                    raise ValueError("provider task does not match the approved Strategy request")
                if capability_key == _MEDIAKIT_VIDEO_STRATEGY_CAPABILITY:
                    contract_projection = {
                        "provider_submission_contract_version": submission["contract_version"],
                        "provider_input_ref_sha256": submission["provider_input_ref_sha256"],
                        "request_sha256": submission["request_sha256"],
                        "submit_body_sha256": submission["submit_body_sha256"],
                    }
                else:
                    contract_projection = {
                        "upload_file_id_sha256": submission["upload_file_id_sha256"],
                        "submit_body_sha256": submission["submit_body_sha256"],
                    }
                event = self._provider_task_event(
                    row,
                    event_key=key,
                    payload={
                        "provider_task_status": "submitting",
                        "client_token_sha256": token_digest,
                        "provider_submission_sha256": submission_digest,
                        **contract_projection,
                    },
                    occurred_at=occurred_at,
                )
                replay = await self._replay_or_none(
                    session,
                    row,
                    expected_event=event,
                )
                if replay is not None:
                    return replay
                if row.status != "admitted" or row.provider_task_status is not None:
                    raise ValueError("provider task submission requires a fresh admitted scope")
                row.provider_task_status = "submitting"
                row.encrypted_provider_client_token = self._encrypt_provider_value(token)
                row.provider_client_token_sha256 = token_digest
                row.encrypted_provider_submission_json = self._encrypt_provider_value(submission_json)
                row.provider_submission_sha256 = submission_digest
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(event)
                try:
                    await session.commit()
                except IntegrityError as exc:
                    await session.rollback()
                    raise ValueError("provider client token is already bound to another paid call") from exc
                return await self._result(
                    session,
                    row,
                    operation_event=event,
                    idempotent_replay=False,
                )
            except Exception:
                await session.rollback()
                raise

    async def claim_provider_task_submission_replay(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        expected_request_digest: str,
        execution_run_id: str,
        expected_submission_sha256: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Atomically grant at most one exact submit replay for one scope.

        The repository owns the event key.  A caller cannot obtain another
        claim by choosing a different key, and an idempotent replay of this
        method returns ``provider_submission_replay_claimed=False`` so the
        provider POST is not executed again.
        """

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        scope = _clean_required(scope_id, field="scope_id", limit=64)
        execution = _clean_required(
            execution_run_id,
            field="execution_run_id",
            limit=64,
        )
        submission_digest = _hex_digest(
            expected_submission_sha256,
            field="expected_submission_sha256",
        )
        event_key = f"provider-submit-replay:{submission_digest}"
        occurred_at = _utc(now or datetime.now(UTC), field="now")
        async with self._sf() as session:
            try:
                row = await self._lock_scope(
                    session,
                    owner_user_id=owner,
                    scope_id=scope,
                )
                if row is None:
                    return None
                self._assert_request_binding(row, expected_request_digest)
                self._assert_execution_binding(row, execution)
                if row.provider_submission_sha256 != submission_digest:
                    raise ValueError("provider submission recovery binding changed")
                event = self._provider_task_event(
                    row,
                    event_key=event_key,
                    payload={
                        "provider_task_status": "submitting",
                        "provider_submission_sha256": submission_digest,
                        "recovery_action": "exact_submit_replay_claimed",
                        "maximum_replay_count": 1,
                    },
                    occurred_at=occurred_at,
                )
                existing = await self._existing_event(
                    session,
                    scope_id=row.id,
                    event_key=event_key,
                )
                if existing is not None:
                    if existing.event_digest != event.event_digest:
                        raise ValueError("provider submit replay event binding changed")
                    result = await self._result(
                        session,
                        row,
                        operation_event=existing,
                        idempotent_replay=True,
                    )
                    result["provider_submission_replay_claimed"] = False
                    return result
                if row.status != "admitted" or row.provider_task_status != "submitting" or row.encrypted_provider_submission_json is None or row.encrypted_provider_task_id is not None:
                    raise ValueError("provider submit replay requires an unfinished exact submission")
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(event)
                await session.commit()
                result = await self._result(
                    session,
                    row,
                    operation_event=event,
                    idempotent_replay=False,
                )
                result["provider_submission_replay_claimed"] = True
                return result
            except Exception:
                await session.rollback()
                raise

    async def _record_provider_task_transition(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        execution_run_id: str,
        raw_task_id: str,
        target_status: str,
        observed_status: str,
        terminal_status: str | None = None,
        terminal_envelope: dict[str, Any] | None = None,
        event_projection: dict[str, Any] | None = None,
        now: datetime | None,
    ) -> dict[str, Any] | None:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        scope = _clean_required(scope_id, field="scope_id", limit=64)
        key = _clean_required(event_key, field="event_key", limit=256)
        execution = _clean_required(
            execution_run_id,
            field="execution_run_id",
            limit=64,
        )
        task_id, task_digest = self._provider_task_id(raw_task_id)
        observed = _clean_required(observed_status, field="observed_status", limit=32).lower()
        occurred_at = _utc(now or datetime.now(UTC), field="now")
        allowed = {
            "submitted": {"submitting"},
            "running": {"submitted", "running"},
            # A fast asynchronous task may already be terminal at the first
            # query.  Do not invent a provider "running" observation merely
            # to satisfy an internal state machine.
            "terminal": {"submitted", "running"},
        }[target_status]
        terminal = None
        terminal_json = None
        terminal_digest = None
        if target_status == "terminal":
            terminal = str(terminal_status or "").strip().lower().replace("cancelled", "canceled")
            if terminal not in {"completed", "failed", "canceled"}:
                raise ValueError("terminal_status is not a terminal provider state")
            if not isinstance(terminal_envelope, dict):
                raise ValueError("terminal_envelope must be an object")
            try:
                terminal_json = json.dumps(
                    terminal_envelope,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("terminal_envelope must be JSON serializable") from exc
            if len(terminal_json.encode("utf-8")) > _MAX_PROVIDER_TERMINAL_BYTES:
                raise ValueError("terminal_envelope exceeds the encrypted snapshot limit")
            terminal_digest = hashlib.sha256(terminal_json.encode("utf-8")).hexdigest()
        payload = {
            "provider_task_status": target_status,
            "provider_task_id_sha256": task_digest,
            "observed_provider_status": observed,
        }
        if event_projection is not None:
            if not isinstance(event_projection, dict):
                raise ValueError("provider task event projection must be an object")
            if set(payload).intersection(event_projection):
                raise ValueError("provider task event projection contains reserved fields")
            validate_credential_free_payload(
                event_projection,
                field="provider_task_event_projection",
            )
            payload.update(event_projection)
        if terminal is not None:
            payload.update(
                provider_terminal_status=terminal,
                provider_terminal_sha256=terminal_digest,
            )
        async with self._sf() as session:
            try:
                row = await self._lock_scope(
                    session,
                    owner_user_id=owner,
                    scope_id=scope,
                )
                if row is None:
                    return None
                self._assert_request_binding(row, expected_request_digest)
                self._assert_execution_binding(row, execution)
                submitted_projection = payload.get("submitted_task_record")
                if target_status == "submitted" and isinstance(submitted_projection, dict):
                    if submitted_projection.get("provider") != row.provider or submitted_projection.get("capability") != row.capability:
                        raise ValueError("submitted-task record does not match the paid-call scope")
                    if row.capability == _MEDIAKIT_VIDEO_STRATEGY_CAPABILITY and (
                        submitted_projection.get("request_sha256") != row.provider_request_sha256 or submitted_projection.get("client_token_sha256") != row.provider_client_token_sha256
                    ):
                        raise ValueError("submitted-task record does not match the Strategy request")
                event = self._provider_task_event(
                    row,
                    event_key=key,
                    payload=payload,
                    occurred_at=occurred_at,
                )
                replay = await self._replay_or_none(
                    session,
                    row,
                    expected_event=event,
                )
                if replay is not None:
                    return replay
                if row.provider_task_status not in allowed:
                    raise ValueError("provider task transition would violate monotonic state")
                if target_status == "submitted" and row.provider_submission_sha256 is not None and "submitted_task_record" not in payload:
                    raise ValueError("exact provider recovery requires a submitted-task record")
                if row.provider_task_id_sha256 is not None and row.provider_task_id_sha256 != task_digest:
                    raise ValueError("provider returned a conflicting task identifier")
                if row.encrypted_provider_task_id is None:
                    row.encrypted_provider_task_id = self._encrypt_provider_value(task_id)
                    row.provider_task_id_sha256 = task_digest
                elif self._decrypt_provider_value(row.encrypted_provider_task_id) != task_id:
                    raise ValueError("encrypted provider task binding is inconsistent")
                row.provider_task_status = target_status
                if terminal_json is not None:
                    row.provider_terminal_status = terminal
                    row.encrypted_provider_terminal_json = self._encrypt_provider_value(terminal_json)
                    row.provider_terminal_sha256 = terminal_digest
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(event)
                await session.commit()
                return await self._result(
                    session,
                    row,
                    operation_event=event,
                    idempotent_replay=False,
                )
            except Exception:
                await session.rollback()
                raise

    async def record_provider_task_submitted(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        execution_run_id: str,
        raw_task_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Legacy transition without submit-response recovery evidence.

        Exact MediaKit remux submissions created by revision 0026 are rejected
        by the transition guard; callers must use
        :meth:`record_provider_task_submission_confirmed`.
        """

        return await self._record_provider_task_transition(
            scope_id,
            owner_user_id=owner_user_id,
            event_key=event_key,
            expected_request_digest=expected_request_digest,
            execution_run_id=execution_run_id,
            raw_task_id=raw_task_id,
            target_status="submitted",
            observed_status="submitted",
            now=now,
        )

    async def record_provider_task_submission_confirmed(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        execution_run_id: str,
        submitted_task_record: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Bind the raw task id and its submit-response digest atomically."""

        record, safe_projection = self._provider_submitted_task_record(submitted_task_record)
        return await self._record_provider_task_transition(
            scope_id,
            owner_user_id=owner_user_id,
            event_key=event_key,
            expected_request_digest=expected_request_digest,
            execution_run_id=execution_run_id,
            raw_task_id=record["task_id"],
            target_status="submitted",
            observed_status="submitted",
            event_projection={"submitted_task_record": safe_projection},
            now=now,
        )

    async def record_provider_task_running(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        execution_run_id: str,
        raw_task_id: str,
        observed_provider_status: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        observed = str(observed_provider_status or "").strip().lower()
        if observed not in {"queued", "pending", "running", "processing"}:
            raise ValueError("observed provider status is not a running state")
        return await self._record_provider_task_transition(
            scope_id,
            owner_user_id=owner_user_id,
            event_key=event_key,
            expected_request_digest=expected_request_digest,
            execution_run_id=execution_run_id,
            raw_task_id=raw_task_id,
            target_status="running",
            observed_status=observed,
            now=now,
        )

    async def record_provider_task_terminal(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        execution_run_id: str,
        raw_task_id: str,
        terminal_status: str,
        terminal_envelope: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        return await self._record_provider_task_transition(
            scope_id,
            owner_user_id=owner_user_id,
            event_key=event_key,
            expected_request_digest=expected_request_digest,
            execution_run_id=execution_run_id,
            raw_task_id=raw_task_id,
            target_status="terminal",
            observed_status=terminal_status,
            terminal_status=terminal_status,
            terminal_envelope=terminal_envelope,
            now=now,
        )

    async def _recoverable_provider_task(
        self,
        session: AsyncSession,
        row: PersonalIPPaidCallScopeRow,
    ) -> dict[str, Any]:
        """Decrypt and validate one provider-task recovery projection."""

        client_token = self._decrypt_provider_value(row.encrypted_provider_client_token)
        submission_json = self._decrypt_provider_value(row.encrypted_provider_submission_json)
        raw_task_id = self._decrypt_provider_value(row.encrypted_provider_task_id)
        terminal_json = self._decrypt_provider_value(row.encrypted_provider_terminal_json)
        submission_envelope = json.loads(submission_json) if submission_json is not None else None
        if submission_envelope is not None:
            if client_token is None:
                raise RuntimeError("provider submission is missing its encrypted client token")
            _, canonical_submission, submission_digest = self._provider_submission(
                submission_envelope,
                capability=row.capability,
                source_sha256=row.source_sha256,
                client_token=client_token,
            )
            if row.provider_submission_sha256 != submission_digest or canonical_submission != submission_json:
                raise RuntimeError("encrypted provider submission binding is inconsistent")
        events = await self._events(session, row.id)
        submitted_events = [event for event in events if event["event_type"] == "provider_task" and event["payload"].get("provider_task_status") == "submitted"]
        submitted_task_record = None
        if row.provider_task_status == "submitting":
            if submitted_events:
                raise RuntimeError("submitting provider task has a premature submitted event")
        else:
            if len(submitted_events) != 1 or raw_task_id is None:
                raise RuntimeError("recoverable provider task is missing its unique submitted-task record")
            event_projection = submitted_events[0]["payload"].get("submitted_task_record")
            if not isinstance(event_projection, dict) or "task_id" in event_projection:
                raise RuntimeError("submitted-task event projection is invalid")
            submitted_task_record, safe_projection = self._provider_submitted_task_record({**event_projection, "task_id": raw_task_id})
            if (
                safe_projection != event_projection
                or submitted_task_record["task_id_sha256"] != row.provider_task_id_sha256
                or submitted_task_record["provider"] != row.provider
                or submitted_task_record["capability"] != row.capability
                or (row.capability == _MEDIAKIT_VIDEO_STRATEGY_CAPABILITY and (submitted_task_record["request_sha256"] != row.provider_request_sha256 or submitted_task_record["client_token_sha256"] != row.provider_client_token_sha256))
            ):
                raise RuntimeError("submitted-task recovery binding is inconsistent")
        terminal_envelope = json.loads(terminal_json) if terminal_json is not None else None
        return {
            **self._scope_dict(row),
            "client_token": client_token,
            "submission_envelope": submission_envelope,
            "submitted_task_record": submitted_task_record,
            "raw_task_id": raw_task_id,
            "terminal_envelope": terminal_envelope,
        }

    async def get_recoverable_provider_task(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any] | None:
        """Read one exact Owner-scoped provider task without a list window."""

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        scope = _clean_required(scope_id, field="scope_id", limit=64)
        async with self._sf() as session:
            row = (
                await session.execute(
                    select(PersonalIPPaidCallScopeRow).where(
                        PersonalIPPaidCallScopeRow.id == scope,
                        PersonalIPPaidCallScopeRow.owner_user_id == owner,
                        PersonalIPPaidCallScopeRow.provider_task_status.is_not(None),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return await self._recoverable_provider_task(session, row)

    async def list_recoverable_provider_tasks(
        self,
        *,
        owner_user_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Decrypt only one Owner's unfinished tasks and completed result refs."""

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        if isinstance(limit, bool) or not 1 <= int(limit) <= 500:
            raise ValueError("limit must be between 1 and 500")
        self._provider_cipher()
        async with self._sf() as session:
            rows = (
                (
                    await session.execute(
                        select(PersonalIPPaidCallScopeRow)
                        .where(
                            PersonalIPPaidCallScopeRow.owner_user_id == owner,
                            PersonalIPPaidCallScopeRow.provider_task_status.is_not(None),
                        )
                        .order_by(PersonalIPPaidCallScopeRow.updated_at.asc())
                        .limit(int(limit))
                    )
                )
                .scalars()
                .all()
            )
            return [await self._recoverable_provider_task(session, row) for row in rows]

    async def release(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        execution_run_id: str,
        no_provider_call_digest: str,
        reason_code: str,
        expected_event_count: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        return await self._finish_reserved(
            scope_id,
            owner_user_id=owner_user_id,
            event_key=event_key,
            expected_request_digest=expected_request_digest,
            execution_run_id=execution_run_id,
            proof_digest=no_provider_call_digest,
            reason_code=reason_code,
            expected_event_count=expected_event_count,
            now=now,
        )

    async def _finish_reserved(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        execution_run_id: str,
        proof_digest: str,
        reason_code: str,
        expected_event_count: int | None,
        now: datetime | None,
    ) -> dict[str, Any] | None:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        scope = _clean_required(scope_id, field="scope_id", limit=64)
        key = _clean_required(event_key, field="event_key", limit=256)
        execution = _clean_required(execution_run_id, field="execution_run_id", limit=64)
        proof = _hex_digest(proof_digest, field="no_provider_call_digest")
        reason = _clean_required(reason_code, field="reason_code", limit=80)
        occurred_at = _utc(now or datetime.now(UTC), field="now")
        async with self._sf() as session:
            try:
                row = await self._lock_scope(session, owner_user_id=owner, scope_id=scope)
                if row is None:
                    return None
                self._assert_request_binding(row, expected_request_digest)
                self._assert_execution_binding(row, execution)
                existing = await self._existing_event(session, scope_id=row.id, event_key=key)
                if existing is not None:
                    replay = await self._replay_matching_fields_or_none(
                        session,
                        row,
                        event_key=key,
                        event_types={"released"},
                        execution_run_id=execution,
                        amount_micros=existing.amount_micros,
                        proof_digest=proof,
                        admission_jti_hash=None,
                        reason_code=reason,
                    )
                    if replay is not None:
                        return replay
                expected = self._event_row(
                    row,
                    event_key=key,
                    event_type="released",
                    execution_run_id=execution,
                    amount_micros=row.reserved_amount_micros,
                    proof_digest=proof,
                    reason_code=reason,
                    occurred_at=occurred_at,
                )
                self._assert_version(row, expected_event_count)
                if row.status != "reserved":
                    raise ValueError("budget may be released only before provider admission")
                row.status = "released"
                row.reserved_amount_micros = 0
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(expected)
                await session.commit()
                return await self._result(session, row, operation_event=expected, idempotent_replay=False)
            except Exception:
                await session.rollback()
                raise

    async def settle(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        execution_run_id: str,
        actual_amount_micros: int | None,
        provider_receipt_digest: str,
        expected_event_count: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        scope = _clean_required(scope_id, field="scope_id", limit=64)
        key = _clean_required(event_key, field="event_key", limit=256)
        execution = _clean_required(execution_run_id, field="execution_run_id", limit=64)
        actual = None
        if actual_amount_micros is not None:
            actual = _micros(actual_amount_micros, field="actual_amount_micros", positive=False)
        receipt = _hex_digest(provider_receipt_digest, field="provider_receipt_digest")
        occurred_at = _utc(now or datetime.now(UTC), field="now")
        async with self._sf() as session:
            try:
                row = await self._lock_scope(session, owner_user_id=owner, scope_id=scope)
                if row is None:
                    return None
                self._assert_request_binding(row, expected_request_digest)
                self._assert_execution_binding(row, execution)
                replay = await self._replay_matching_fields_or_none(
                    session,
                    row,
                    event_key=key,
                    event_types={"settled", "reconciliation_required"},
                    execution_run_id=execution,
                    amount_micros=actual,
                    proof_digest=receipt,
                    admission_jti_hash=None,
                )
                if replay is not None:
                    return replay
                can_settle = actual is not None and actual <= row.reserved_amount_micros
                event_type = "settled" if can_settle else "reconciliation_required"
                if actual is None:
                    reason = "actual_amount_unknown"
                elif row.maximum_amount_micros is not None and actual > row.maximum_amount_micros:
                    reason = "actual_amount_exceeds_maximum"
                elif actual > row.reserved_amount_micros:
                    reason = "actual_amount_exceeds_reservation"
                else:
                    reason = None
                expected = self._event_row(
                    row,
                    event_key=key,
                    event_type=event_type,
                    execution_run_id=execution,
                    amount_micros=actual,
                    proof_digest=receipt,
                    reason_code=reason,
                    occurred_at=occurred_at,
                )
                self._assert_version(row, expected_event_count)
                if row.status not in {"admitted", "reconciliation_required"}:
                    raise ValueError("paid-call settlement requires admitted or reconciliation_required status")
                row.status = event_type
                if can_settle:
                    row.settled_amount_micros = actual
                    row.reserved_amount_micros = 0
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(expected)
                await session.commit()
                return await self._result(session, row, operation_event=expected, idempotent_replay=False)
            except Exception:
                await session.rollback()
                raise

    async def reconcile(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        execution_run_id: str,
        actual_amount_micros: int,
        reconciliation_digest: str,
        expected_event_count: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Resolve a held unknown/overrun amount with an explicit audit proof."""

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        scope = _clean_required(scope_id, field="scope_id", limit=64)
        key = _clean_required(event_key, field="event_key", limit=256)
        execution = _clean_required(execution_run_id, field="execution_run_id", limit=64)
        actual = _micros(actual_amount_micros, field="actual_amount_micros", positive=False)
        proof = _hex_digest(reconciliation_digest, field="reconciliation_digest")
        occurred_at = _utc(now or datetime.now(UTC), field="now")
        async with self._sf() as session:
            try:
                row = await self._lock_scope(session, owner_user_id=owner, scope_id=scope)
                if row is None:
                    return None
                self._assert_request_binding(row, expected_request_digest)
                self._assert_execution_binding(row, execution)
                expected = self._event_row(
                    row,
                    event_key=key,
                    event_type="settled",
                    execution_run_id=execution,
                    amount_micros=actual,
                    proof_digest=proof,
                    reason_code="manual_reconciliation",
                    occurred_at=occurred_at,
                )
                replay = await self._replay_or_none(session, row, expected_event=expected)
                if replay is not None:
                    return replay
                self._assert_version(row, expected_event_count)
                if row.status != "reconciliation_required":
                    raise ValueError("manual reconciliation requires reconciliation_required status")
                row.status = "settled"
                row.settled_amount_micros = actual
                row.reserved_amount_micros = 0
                row.event_count += 1
                row.updated_at = occurred_at
                session.add(expected)
                await session.commit()
                return await self._result(session, row, operation_event=expected, idempotent_replay=False)
            except Exception:
                await session.rollback()
                raise


__all__ = [
    "AmbiguousOperatorCappedEvidenceStages",
    "EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION",
    "EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION",
    "EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION",
    "EVIDENCE_VIDEO_STRATEGY_OPERATOR_CAP_POLICY_VERSION",
    "OperatorCappedEvidenceStagePolicy",
    "PAID_CALL_EVENT_CONTRACT_VERSION",
    "PAID_CALL_SCOPE_CONTRACT_VERSION",
    "PersonalIPPaidCallRepository",
]
