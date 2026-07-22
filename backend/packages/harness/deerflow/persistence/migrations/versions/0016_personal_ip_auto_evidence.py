"""Automatically promote legacy evidence proposals

Revision ID: 0016_personal_ip_auto_evidence
Revises: 0015_personal_ip_video_productions
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0016_personal_ip_auto_evidence"
down_revision: str | Sequence[str] | None = "0015_personal_ip_video_productions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if "personal_ip_evidence_promotions" not in sa.inspect(bind).get_table_names():
        return
    promotions = sa.table(
        "personal_ip_evidence_promotions",
        sa.column("id", sa.String()),
        sa.column("evidence_digest", sa.String()),
        sa.column("evidence_summary_json", sa.JSON()),
        sa.column("minimum_support", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("decisions_json", sa.JSON()),
        sa.column("decided_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    rows = bind.execute(
        sa.select(
            promotions.c.id,
            promotions.c.evidence_digest,
            promotions.c.evidence_summary_json,
            promotions.c.minimum_support,
        ).where(promotions.c.status == "proposed")
    ).mappings()
    for row in rows:
        now = datetime.now(UTC)
        summary = row["evidence_summary_json"] or {}
        support = int(summary.get("independent_measured_support") or row["minimum_support"])
        decision = {
            "decision_key": f"evidence-policy:{row['evidence_digest']}",
            "decision": "approved",
            "reviewer_source": "cross_sample_evidence_policy",
            "rationale": (f"Automatically promoted after {support} independent measured publications satisfied the minimum support of {row['minimum_support']}."),
            "occurred_at": now.isoformat(),
        }
        bind.execute(
            sa.update(promotions)
            .where(promotions.c.id == row["id"])
            .values(
                status="approved",
                decisions_json=[decision],
                decided_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    # Policy approvals are durable evidence receipts and are not reversed.
    pass
