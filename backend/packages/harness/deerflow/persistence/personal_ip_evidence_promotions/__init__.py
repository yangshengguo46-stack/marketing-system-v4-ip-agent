"""Read-only compatibility persistence for legacy evidence promotions."""

from deerflow.persistence.personal_ip_evidence_promotions.model import PersonalIPEvidencePromotionRow
from deerflow.persistence.personal_ip_evidence_promotions.sql import PersonalIPEvidencePromotionRepository

__all__ = ["PersonalIPEvidencePromotionRepository", "PersonalIPEvidencePromotionRow"]
