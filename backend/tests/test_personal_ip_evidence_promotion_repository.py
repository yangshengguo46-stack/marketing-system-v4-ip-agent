from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import (
    close_engine,
    get_session_factory,
    init_engine_from_config,
)
from deerflow.persistence.personal_ip_evidence_promotions import (
    PersonalIPEvidencePromotionRepository,
)
from deerflow.persistence.personal_ip_evidence_promotions.model import (
    PersonalIPEvidencePromotionRow,
)
from deerflow.persistence.personal_ip_retrospectives.model import (
    PersonalIPRetrospectiveRow,
)


@pytest.mark.asyncio
async def test_historical_promotions_are_owner_scoped_read_only(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    try:
        sf = get_session_factory()
        assert sf is not None
        now = datetime.now(UTC)
        async with sf() as session:
            retrospective = PersonalIPRetrospectiveRow(
                id="retro-1",
                owner_user_id="user-1",
                review_key="review-1",
                preflight_id="preflight-1",
                publish_receipt_id="publish-1",
                account_id="acct-1",
                subject_id=None,
                platform="douyin",
                horizon="T+1d",
                selected_variant_id="v1",
                provider="legacy",
                model_version="legacy",
                algorithm_version="legacy",
                metric_observation_ids_json=["metric-1"],
                prediction_json={},
                outcome_json={},
                training_eligibility_json={},
                evidence_digest="a" * 64,
                status="measured",
                comparison_state="unscored",
                created_at=now,
            )
            promotion = PersonalIPEvidencePromotionRow(
                id="promotion-1",
                owner_user_id="user-1",
                proposal_key="legacy-1",
                evidence_type="content_pattern",
                claim="历史规则",
                retrospective_ids_json=["retro-1"],
                evidence_summary_json={"retrospective_count": 1},
                evidence_digest="b" * 64,
                minimum_support=3,
                status="approved",
                decisions_json=[],
                decided_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add_all([retrospective, promotion])
            await session.commit()

        repository = PersonalIPEvidencePromotionRepository(sf)
        assert await repository.get("promotion-1", owner_user_id="user-2") is None
        listed = await repository.list("user-1")
        assert listed[0]["id"] == "promotion-1"
        exported = await repository.export_approved(
            "promotion-1",
            owner_user_id="user-1",
        )
        assert exported is not None
        assert exported["source_examples"][0]["retrospective_id"] == "retro-1"
        assert not hasattr(repository, "propose")
    finally:
        await close_engine()
