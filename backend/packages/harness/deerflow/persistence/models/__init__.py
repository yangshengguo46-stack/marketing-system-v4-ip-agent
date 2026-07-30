"""ORM model registration entry point.

Importing this module ensures all ORM models are registered with
``Base.metadata`` so Alembic autogenerate detects every table.

The actual ORM classes have moved to entity-specific subpackages:
- ``deerflow.persistence.thread_meta``
- ``deerflow.persistence.run``
- ``deerflow.persistence.feedback``
- ``deerflow.persistence.user``

``RunEventRow`` remains in ``deerflow.persistence.models.run_event`` because
its storage implementation lives in ``deerflow.runtime.events.store.db`` and
there is no matching entity directory.
"""

from deerflow.persistence.channel_connections.model import (
    ChannelConnectionRow,
    ChannelConversationRow,
    ChannelCredentialRow,
    ChannelOAuthStateRow,
)
from deerflow.persistence.feedback.model import FeedbackRow
from deerflow.persistence.models.run_event import RunEventRow
from deerflow.persistence.personal_ip_accounts.model import PersonalIPAccountRow
from deerflow.persistence.personal_ip_brand.model import PersonalIPStrategyVersionRow
from deerflow.persistence.personal_ip_differentiation.model import (
    PersonalIPAssetObservationRow,
    PersonalIPDifferentiationVersionRow,
)
from deerflow.persistence.personal_ip_evidence_promotions.model import PersonalIPEvidencePromotionRow
from deerflow.persistence.personal_ip_metrics.model import PersonalIPMetricObservationRow
from deerflow.persistence.personal_ip_platform_connections.model import (
    PersonalIPPlatformConnectionRow,
    PersonalIPPlatformCredentialRow,
    PersonalIPPlatformOAuthStateRow,
)
from deerflow.persistence.personal_ip_platform_observations.model import PersonalIPPlatformObservationRow
from deerflow.persistence.personal_ip_preflights.model import PersonalIPPreflightRow
from deerflow.persistence.personal_ip_publish_receipts.model import PersonalIPPublishReceiptRow
from deerflow.persistence.personal_ip_retrospectives.model import PersonalIPRetrospectiveRow
from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.persistence.personal_ip_video_productions.model import (
    PersonalIPVideoProductionEventRow,
    PersonalIPVideoProductionRow,
)
from deerflow.persistence.run.model import RunRow
from deerflow.persistence.scheduled_task_runs.model import ScheduledTaskRunRow
from deerflow.persistence.scheduled_tasks.model import ScheduledTaskRow
from deerflow.persistence.thread_meta.model import ThreadMetaRow
from deerflow.persistence.user.model import UserRow

__all__ = [
    "ChannelConnectionRow",
    "ChannelConversationRow",
    "ChannelCredentialRow",
    "ChannelOAuthStateRow",
    "FeedbackRow",
    "PersonalIPAccountRow",
    "PersonalIPAssetObservationRow",
    "PersonalIPDifferentiationVersionRow",
    "PersonalIPEvidencePromotionRow",
    "PersonalIPMetricObservationRow",
    "PersonalIPPlatformConnectionRow",
    "PersonalIPPlatformCredentialRow",
    "PersonalIPPlatformOAuthStateRow",
    "PersonalIPPlatformObservationRow",
    "PersonalIPPreflightRow",
    "PersonalIPPublishReceiptRow",
    "PersonalIPRetrospectiveRow",
    "PersonalIPStrategyVersionRow",
    "PersonalIPSubjectRow",
    "PersonalIPVideoProductionEventRow",
    "PersonalIPVideoProductionRow",
    "RunEventRow",
    "RunRow",
    "ScheduledTaskRow",
    "ScheduledTaskRunRow",
    "ThreadMetaRow",
    "UserRow",
]
