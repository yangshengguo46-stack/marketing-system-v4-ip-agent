"""SQL repository for auditable Personal-IP publishing operations."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_accounts.model import PersonalIPAccountRow
from deerflow.persistence.personal_ip_platform_observations.sql import validate_credential_free_payload
from deerflow.persistence.personal_ip_preflights.model import PersonalIPPreflightRow
from deerflow.persistence.personal_ip_publish_receipts.model import PersonalIPPublishReceiptRow
from deerflow.personal_ip.browser_publishing import normalize_publication_url, platform_publication_url_allowed
from deerflow.personal_ip.publish_compliance import (
    compile_publish_compliance,
    validate_publish_compliance_evidence,
)
from deerflow.utils.time import coerce_iso

_EXECUTORS = {"platform_api", "ui_tars", "browser", "manual"}
_ATTEMPT_STATUSES = {"pending", "published", "failed", "unknown", "deleted"}
_TRANSITIONS = {
    "planned": {"pending", "published", "failed", "unknown"},
    "pending": {"pending", "published", "failed", "unknown"},
    "failed": {"pending", "published", "failed", "unknown"},
    "unknown": {"pending", "published", "failed", "unknown"},
    "published": {"published", "deleted"},
    "deleted": {"deleted"},
}


def _clean_required(value: Any, *, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _json_snapshot(value: Any, *, field: str) -> Any:
    validate_credential_free_payload(value, field=field)
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc
    if len(serialized.encode("utf-8")) > 1_000_000:
        raise ValueError(f"{field} exceeds the 1 MB snapshot limit")
    return json.loads(serialized)


def _safe_external_url(value: Any, *, platform: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) > 4096:
        raise ValueError("external_url is too long")
    url = normalize_publication_url(raw, platform=platform)
    if not platform_publication_url_allowed(platform, url):
        raise ValueError("external_url does not belong to the publish platform")
    return url


def _digest(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _utc_datetime(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


class PersonalIPPublishReceiptRepository:
    """Create idempotent operations and append executor attempts."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _to_dict(row: PersonalIPPublishReceiptRow) -> dict[str, Any]:
        data = row.to_dict()
        data["request"] = data.pop("request_json") or {}
        data["attempts"] = data.pop("attempts_json") or []
        for field in ("last_attempt_at", "published_at", "created_at", "updated_at"):
            if isinstance(data.get(field), datetime):
                data[field] = coerce_iso(data[field])
        return data

    @staticmethod
    def _same_operation(
        row: PersonalIPPublishReceiptRow,
        *,
        operation_key: str,
        idempotency_key: str,
        account_id: str,
        preflight_id: str | None,
        executor: str,
        request_payload: dict[str, Any],
    ) -> bool:
        return row.operation_key == operation_key and row.idempotency_key == idempotency_key and row.account_id == account_id and row.preflight_id == preflight_id and row.executor == executor and row.request_json == request_payload

    async def begin(
        self,
        *,
        owner_user_id: str,
        operation_key: str,
        idempotency_key: str,
        account_id: str,
        preflight_id: str | None,
        executor: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        operation = _clean_required(operation_key, field="operation_key", limit=256)
        idempotency = _clean_required(idempotency_key, field="idempotency_key", limit=256)
        account_key = _clean_required(account_id, field="account_id", limit=64)
        preflight_key = str(preflight_id or "").strip() or None
        executor_key = str(executor or "").strip()
        if executor_key not in _EXECUTORS:
            raise ValueError("unsupported publish executor")
        request_snapshot = _json_snapshot(request_payload, field="request_payload")
        if not isinstance(request_snapshot, dict) or not request_snapshot:
            raise ValueError("request_payload must be a non-empty object")
        if "compliance_receipt" in request_snapshot:
            raise ValueError("compliance_receipt is server-owned")

        async with self._sf() as session:
            account = await session.get(PersonalIPAccountRow, account_key)
            if account is None or account.owner_user_id != owner or account.status != "active":
                raise ValueError("Personal-IP publish target account not found")
            compliance, compliance_receipt = compile_publish_compliance(
                account.platform,
                request_snapshot.get("compliance"),
            )
            request_snapshot = {
                **request_snapshot,
                "compliance": compliance,
                "compliance_receipt": compliance_receipt,
            }
            existing_statement = select(PersonalIPPublishReceiptRow).where(
                PersonalIPPublishReceiptRow.owner_user_id == owner,
                or_(
                    PersonalIPPublishReceiptRow.operation_key == operation,
                    PersonalIPPublishReceiptRow.idempotency_key == idempotency,
                ),
            )
            existing = (await session.execute(existing_statement)).scalars().first()
            if existing is not None:
                if self._same_operation(
                    existing,
                    operation_key=operation,
                    idempotency_key=idempotency,
                    account_id=account_key,
                    preflight_id=preflight_key,
                    executor=executor_key,
                    request_payload=request_snapshot,
                ):
                    return self._to_dict(existing)
                raise ValueError("operation or idempotency key already records a different publish request")

            preflight = None
            if preflight_key is not None:
                preflight = await session.get(PersonalIPPreflightRow, preflight_key)
                if preflight is None or preflight.owner_user_id != owner or preflight.status == "invalidated":
                    raise ValueError("Personal-IP preflight not found")
                targets = list(preflight.target_account_ids_json or [])
                if targets and account_key not in targets:
                    raise ValueError("publish account is outside the sealed preflight targets")
                selected_variant_id = str(request_snapshot.get("variant_id") or "").strip()
                if not selected_variant_id:
                    raise ValueError("publish request must identify the selected preflight variant")
                variants = list((preflight.provider_receipt_json or {}).get("variants") or [])
                if not any(str(variant.get("variant_id") or "") == selected_variant_id for variant in variants):
                    raise ValueError("publish request selects a variant outside the sealed preflight receipt")

            now = datetime.now(UTC)
            row = PersonalIPPublishReceiptRow(
                id=f"publish-{uuid.uuid4().hex}",
                owner_user_id=owner,
                operation_key=operation,
                idempotency_key=idempotency,
                preflight_id=preflight_key,
                subject_id=account.subject_id,
                account_id=account.id,
                platform=account.platform,
                action="publish",
                executor=executor_key,
                request_digest=_digest(request_snapshot),
                request_json=request_snapshot,
                attempts_json=[],
                status="planned",
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def record_attempt(
        self,
        receipt_id: str,
        *,
        owner_user_id: str,
        attempt_key: str,
        status: str,
        result_payload: dict[str, Any],
        occurred_at: datetime | None = None,
        external_post_id: str | None = None,
        external_url: str | None = None,
    ) -> dict[str, Any] | None:
        attempt = _clean_required(attempt_key, field="attempt_key", limit=256)
        status_key = str(status or "").strip()
        if status_key not in _ATTEMPT_STATUSES:
            raise ValueError("unsupported publish attempt status")
        result_snapshot = _json_snapshot(result_payload, field="result_payload")
        if not isinstance(result_snapshot, dict):
            raise ValueError("result_payload must be an object")
        event_time = _utc_datetime(occurred_at)
        post_id = str(external_post_id or "").strip() or None
        if post_id is not None and len(post_id) > 256:
            raise ValueError("external_post_id is too long")

        async with self._sf() as session:
            row = await session.get(PersonalIPPublishReceiptRow, receipt_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            if status_key == "published":
                compliance_evidence = validate_publish_compliance_evidence(
                    row.request_json,
                    result_snapshot,
                )
                result_snapshot = {
                    **result_snapshot,
                    "compliance_evidence": compliance_evidence,
                }
            url = _safe_external_url(external_url, platform=row.platform)
            if status_key == "published" and post_id is None and url is None:
                raise ValueError("published attempts require an external post id or URL")
            event = {
                "attempt_key": attempt,
                "status": status_key,
                "result": result_snapshot,
                "external_post_id": post_id,
                "external_url": url,
                "occurred_at": coerce_iso(event_time),
            }
            for existing in row.attempts_json or []:
                if existing.get("attempt_key") == attempt:
                    if existing == event:
                        return self._to_dict(row)
                    raise ValueError("attempt_key already records a different result")
            if status_key not in _TRANSITIONS[row.status]:
                raise ValueError(f"publish receipt cannot transition from {row.status} to {status_key}")
            if row.external_post_id and post_id and row.external_post_id != post_id:
                raise ValueError("publish receipt external_post_id cannot be replaced")
            if row.external_url and url and row.external_url != url:
                raise ValueError("publish receipt external_url cannot be replaced")

            row.attempts_json = [*(row.attempts_json or []), event]
            row.status = status_key
            row.last_attempt_at = event_time
            row.updated_at = datetime.now(UTC)
            if post_id:
                row.external_post_id = post_id
            if url:
                row.external_url = url
            if status_key == "published" and row.published_at is None:
                row.published_at = event_time
                if row.preflight_id:
                    preflight = await session.get(PersonalIPPreflightRow, row.preflight_id)
                    if preflight is not None and preflight.owner_user_id == owner_user_id and preflight.status == "sealed":
                        preflight.status = "published"
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def get(self, receipt_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPPublishReceiptRow, receipt_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            return self._to_dict(row)

    async def list(
        self,
        owner_user_id: str,
        *,
        account_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        statement = select(PersonalIPPublishReceiptRow).where(PersonalIPPublishReceiptRow.owner_user_id == owner_user_id)
        if account_id is not None:
            statement = statement.where(PersonalIPPublishReceiptRow.account_id == account_id)
        statement = statement.order_by(PersonalIPPublishReceiptRow.updated_at.desc(), PersonalIPPublishReceiptRow.id.desc()).limit(max(1, min(int(limit), 500)))
        async with self._sf() as session:
            rows = (await session.execute(statement)).scalars()
            return [self._to_dict(row) for row in rows]
