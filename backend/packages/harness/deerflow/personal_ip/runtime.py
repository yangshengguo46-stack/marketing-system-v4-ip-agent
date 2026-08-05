"""Process-local runtime services exposed to native personal-IP agent tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_content import PersonalIPContentRepository
from deerflow.persistence.personal_ip_metrics import PersonalIPMetricRepository
from deerflow.persistence.personal_ip_platform_connections import PersonalIPPlatformConnectionRepository
from deerflow.persistence.personal_ip_platform_observations import PersonalIPPlatformObservationRepository
from deerflow.persistence.personal_ip_publish_receipts import PersonalIPPublishReceiptRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.persistence.personal_ip_video_productions import PersonalIPVideoProductionRepository

if TYPE_CHECKING:
    from deerflow.personal_ip.minecontext import MineContextService


@dataclass(frozen=True, slots=True)
class PersonalIPRuntimeServices:
    connections: PersonalIPPlatformConnectionRepository
    metrics: PersonalIPMetricRepository
    publish_receipts: PersonalIPPublishReceiptRepository
    accounts: PersonalIPAccountRepository | None = None
    content: PersonalIPContentRepository | None = None
    platform_observations: PersonalIPPlatformObservationRepository | None = None
    subjects: PersonalIPSubjectRepository | None = None
    video_productions: PersonalIPVideoProductionRepository | None = None
    minecontext: MineContextService | None = None


_services: PersonalIPRuntimeServices | None = None


def configure_personal_ip_runtime(services: PersonalIPRuntimeServices | None) -> None:
    """Install or clear the current Gateway process's repository bundle."""
    global _services
    _services = services


def get_personal_ip_runtime() -> PersonalIPRuntimeServices:
    if _services is None:
        raise RuntimeError("Personal-IP persistence is not available")
    return _services
