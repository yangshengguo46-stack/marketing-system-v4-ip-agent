"""Operator-only policy for unknown-price, single-video Evidence ASR calls.

The configured amount is a local admission risk limit.  It is deliberately
not described as a provider quote or a provider-enforced billing ceiling.
Every admitted call still requires an exact Owner approval and is held for
reconciliation when the provider omits its actual charge.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from deerflow.persistence.personal_ip_paid_calls import (
    EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
)

_ENABLED_ENV = "IP_AGENT_EVIDENCE_ASR_DIRECT_PAY_ENABLED"
_LIMIT_ENV = "IP_AGENT_EVIDENCE_ASR_DIRECT_PAY_MAXIMUM_MICROS"
_DURATION_ENV = "IP_AGENT_EVIDENCE_ASR_DIRECT_PAY_MAX_DURATION_SECONDS"

# These are product-side safety ceilings for configuring the local admission
# policy. They do not and cannot constrain a provider invoice after submission.
ABSOLUTE_LOCAL_ADMISSION_LIMIT_MICROS = 10_000_000  # CNY 10.00
ABSOLUTE_SOURCE_DURATION_MILLIS = 20 * 60 * 1_000


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _required_positive_integer(name: str) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        raise RuntimeError(f"{name} is required when direct-pay ASR is enabled")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class EvidenceASRDirectPayPolicy:
    """Explicit, capability-specific local admission policy."""

    enabled: bool = False
    local_admission_limit_micros: int | None = None
    max_source_duration_millis: int | None = None
    currency: str = "CNY"
    policy_version: str = EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION

    def __post_init__(self) -> None:
        if not self.enabled:
            if self.local_admission_limit_micros is not None or self.max_source_duration_millis is not None:
                raise ValueError("disabled direct-pay policy cannot carry limits")
            return
        amount = self.local_admission_limit_micros
        duration = self.max_source_duration_millis
        if amount is None or not 0 < amount <= ABSOLUTE_LOCAL_ADMISSION_LIMIT_MICROS:
            raise ValueError("direct-pay ASR local admission limit is outside the product safety ceiling")
        if duration is None or not 0 < duration <= ABSOLUTE_SOURCE_DURATION_MILLIS:
            raise ValueError("direct-pay ASR source duration is outside the product safety ceiling")
        if self.currency != "CNY":
            raise ValueError("direct-pay ASR currently supports CNY only")
        if self.policy_version != EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION:
            raise ValueError("unsupported direct-pay ASR policy version")

    @classmethod
    def from_environment(cls) -> EvidenceASRDirectPayPolicy:
        """Load a fail-closed operator policy from startup environment."""

        if not _enabled(os.getenv(_ENABLED_ENV)):
            return cls()
        local_limit = _required_positive_integer(_LIMIT_ENV)
        max_duration_seconds = _required_positive_integer(_DURATION_ENV)
        try:
            return cls(
                enabled=True,
                local_admission_limit_micros=local_limit,
                max_source_duration_millis=max_duration_seconds * 1_000,
            )
        except ValueError as exc:
            raise RuntimeError("invalid direct-pay ASR operator policy") from exc

    def admits_source(self, *, duration_millis: int) -> bool:
        return bool(self.enabled and self.max_source_duration_millis is not None and 0 < duration_millis <= self.max_source_duration_millis)


__all__ = [
    "ABSOLUTE_LOCAL_ADMISSION_LIMIT_MICROS",
    "ABSOLUTE_SOURCE_DURATION_MILLIS",
    "EvidenceASRDirectPayPolicy",
]
