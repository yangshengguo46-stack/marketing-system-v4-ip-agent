"""ORM models for server-authoritative one-shot paid-call admission."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPPaidCallScopeRow(Base):
    """Immutable exact-call request plus its append-only event projection."""

    __tablename__ = "personal_ip_paid_call_scopes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_key: Mapped[str] = mapped_column(String(256), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    origin_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    execution_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    server_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_args_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    sku: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_label: Mapped[str] = mapped_column(String(120), nullable=False)
    capability_label: Mapped[str] = mapped_column(String(120), nullable=False)
    object_ref_label: Mapped[str] = mapped_column(String(96), nullable=False)
    source_duration_millis: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    stage_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    maximum_amount_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    billing_basis: Mapped[str] = mapped_column(String(160), nullable=False)
    price_status: Mapped[str] = mapped_column(String(16), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    price_version: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_input_attested: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence_coverage: Mapped[str] = mapped_column(String(16), nullable=False)
    warning_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="requested")
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reserved_amount_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    settled_amount_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    admission_jti_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_task_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    encrypted_provider_client_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_client_token_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    encrypted_provider_submission_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_submission_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    encrypted_provider_task_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_task_id_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_terminal_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    encrypted_provider_terminal_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_terminal_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "request_key",
            name="uq_personal_ip_paid_call_scopes_owner_request",
        ),
        UniqueConstraint(
            "admission_jti_hash",
            name="uq_personal_ip_paid_call_scopes_admission_jti",
        ),
        UniqueConstraint(
            "provider_client_token_sha256",
            name="uq_personal_ip_paid_call_scopes_provider_client_token",
        ),
        CheckConstraint("scope_kind = 'run'", name="ck_personal_ip_paid_call_scopes_kind"),
        CheckConstraint(
            "status IN ('requested','approved','rejected','reserved','budget_rejected','admitted','released','settled','reconciliation_required')",
            name="ck_personal_ip_paid_call_scopes_status",
        ),
        CheckConstraint(
            "(price_status = 'unknown' AND maximum_amount_micros IS NULL) OR (price_status IN ('quoted','operator_capped') AND maximum_amount_micros > 0)",
            name="ck_personal_ip_paid_call_scopes_price_state",
        ),
        CheckConstraint(
            "source_duration_millis > 0",
            name="ck_personal_ip_paid_call_scopes_duration_positive",
        ),
        CheckConstraint(
            "evidence_coverage IN ('partial','complete')",
            name="ck_personal_ip_paid_call_scopes_coverage",
        ),
        CheckConstraint(
            "reserved_amount_micros >= 0",
            name="ck_personal_ip_paid_call_scopes_reserved_nonnegative",
        ),
        CheckConstraint(
            "settled_amount_micros IS NULL OR settled_amount_micros >= 0",
            name="ck_personal_ip_paid_call_scopes_settled_nonnegative",
        ),
        CheckConstraint(
            "provider_task_status IS NULL OR provider_task_status IN ('submitting','submitted','running','terminal')",
            name="ck_personal_ip_paid_call_scopes_provider_task_status",
        ),
        CheckConstraint(
            "provider_terminal_status IS NULL OR provider_terminal_status IN ('completed','failed','canceled')",
            name="ck_personal_ip_paid_call_scopes_provider_terminal_status",
        ),
        CheckConstraint(
            "(provider_task_status IS NULL AND encrypted_provider_client_token IS NULL "
            "AND provider_client_token_sha256 IS NULL AND encrypted_provider_submission_json IS NULL "
            "AND provider_submission_sha256 IS NULL AND encrypted_provider_task_id IS NULL "
            "AND provider_task_id_sha256 IS NULL AND provider_terminal_status IS NULL "
            "AND encrypted_provider_terminal_json IS NULL AND provider_terminal_sha256 IS NULL) OR "
            "(provider_task_status = 'submitting' AND encrypted_provider_client_token IS NOT NULL "
            "AND provider_client_token_sha256 IS NOT NULL AND encrypted_provider_submission_json IS NOT NULL "
            "AND provider_submission_sha256 IS NOT NULL AND encrypted_provider_task_id IS NULL "
            "AND provider_task_id_sha256 IS NULL AND provider_terminal_status IS NULL "
            "AND encrypted_provider_terminal_json IS NULL AND provider_terminal_sha256 IS NULL) OR "
            "(provider_task_status IN ('submitted','running') AND encrypted_provider_client_token IS NOT NULL "
            "AND provider_client_token_sha256 IS NOT NULL AND encrypted_provider_submission_json IS NOT NULL "
            "AND provider_submission_sha256 IS NOT NULL AND encrypted_provider_task_id IS NOT NULL "
            "AND provider_task_id_sha256 IS NOT NULL AND provider_terminal_status IS NULL "
            "AND encrypted_provider_terminal_json IS NULL AND provider_terminal_sha256 IS NULL) OR "
            "(provider_task_status = 'terminal' AND encrypted_provider_client_token IS NOT NULL "
            "AND provider_client_token_sha256 IS NOT NULL AND encrypted_provider_submission_json IS NOT NULL "
            "AND provider_submission_sha256 IS NOT NULL AND encrypted_provider_task_id IS NOT NULL "
            "AND provider_task_id_sha256 IS NOT NULL AND provider_terminal_status IS NOT NULL "
            "AND encrypted_provider_terminal_json IS NOT NULL AND provider_terminal_sha256 IS NOT NULL)",
            name="ck_personal_ip_paid_call_scopes_provider_task_state",
        ),
        Index(
            "ix_personal_ip_paid_call_scopes_owner_origin_run",
            "owner_user_id",
            "origin_run_id",
        ),
        Index(
            "ix_personal_ip_paid_call_scopes_owner_execution_run",
            "owner_user_id",
            "execution_run_id",
        ),
        Index(
            "ix_personal_ip_paid_call_scopes_owner_updated",
            "owner_user_id",
            "updated_at",
        ),
        Index(
            "ix_personal_ip_paid_call_scopes_provider_task_recovery",
            "provider_task_status",
            "updated_at",
        ),
    )


class PersonalIPPaidCallEventRow(Base):
    """One immutable state transition in a paid-call scope."""

    __tablename__ = "personal_ip_paid_call_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_paid_call_scopes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_key: Mapped[str] = mapped_column(String(256), nullable=False)
    event_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    execution_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    proof_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    admission_jti_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "scope_id",
            "event_key",
            name="uq_personal_ip_paid_call_events_key",
        ),
        UniqueConstraint(
            "scope_id",
            "sequence",
            name="uq_personal_ip_paid_call_events_sequence",
        ),
        CheckConstraint(
            "event_type IN ('requested','approved','rejected','reserved','budget_rejected','admitted','released','settled','reconciliation_required','provider_task')",
            name="ck_personal_ip_paid_call_events_type",
        ),
        CheckConstraint(
            "amount_micros IS NULL OR amount_micros >= 0",
            name="ck_personal_ip_paid_call_events_amount_nonnegative",
        ),
        Index(
            "ix_personal_ip_paid_call_events_scope_sequence",
            "scope_id",
            "sequence",
        ),
    )
