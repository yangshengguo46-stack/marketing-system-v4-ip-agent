from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_evidence_promotions import PersonalIPEvidencePromotionRepository
from deerflow.persistence.personal_ip_retrospectives.model import PersonalIPRetrospectiveRow


async def _seed_retrospectives(
    session_factory,
    *,
    owner_user_id: str,
    count: int,
    partial_indexes: set[int] | None = None,
    shared_publish: bool = False,
) -> list[str]:
    ids: list[str] = []
    partial_indexes = partial_indexes or set()
    async with session_factory() as session:
        for index in range(count):
            retrospective_id = f"retro-{owner_user_id}-{index}"
            publish_id = f"publish-{owner_user_id}-shared" if shared_publish else f"publish-{owner_user_id}-{index}"
            is_partial = index in partial_indexes
            row = PersonalIPRetrospectiveRow(
                id=retrospective_id,
                owner_user_id=owner_user_id,
                review_key=f"review-{owner_user_id}-{index}",
                preflight_id=f"preflight-{owner_user_id}-{index}",
                publish_receipt_id=publish_id,
                account_id=f"acct-{index % 2}",
                subject_id=None,
                platform="douyin" if index % 2 == 0 else "xiaohongshu",
                horizon=f"t+{index + 1}d" if shared_publish else "t+1d",
                selected_variant_id="v1",
                provider="hllm-lite",
                model_version="doubao-test",
                algorithm_version="lite-v0",
                metric_observation_ids_json=[f"metric-{owner_user_id}-{index}"],
                prediction_json={"variant": {"variant_id": "v1", "text": f"候选 {index}", "match_score": None}},
                outcome_json={"latest_metrics": {"views": 1000 + index * 100}},
                training_eligibility_json={"status": "pending_human_review"},
                evidence_digest=f"{index + 1:064x}",
                status="partial" if is_partial else "measured",
                comparison_state="unscored",
                created_at=datetime(2026, 7, 21, 8, 0, tzinfo=UTC) + timedelta(minutes=index),
            )
            session.add(row)
            ids.append(retrospective_id)
        await session.commit()
    return ids


@pytest.mark.asyncio
async def test_evidence_promotion_requires_cross_sample_support_and_human_approval(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    retrospective_ids = await _seed_retrospectives(sf, owner_user_id="user-1", count=3)
    promotions = PersonalIPEvidencePromotionRepository(sf)

    kwargs = {
        "owner_user_id": "user-1",
        "proposal_key": "promotion:hooks:v1",
        "evidence_type": "content_pattern",
        "claim": "前两秒直接给出矛盾点，更适合当前受众。",
        "retrospective_ids": retrospective_ids,
        "minimum_support": 3,
    }
    proposed = await promotions.propose(**kwargs)
    replayed = await promotions.propose(**kwargs)

    assert replayed == proposed
    assert proposed["status"] == "proposed"
    assert proposed["evidence_summary"]["independent_measured_support"] == 3
    assert proposed["evidence_summary"]["account_count"] == 2
    assert proposed["decisions"] == []
    with pytest.raises(ValueError, match="explicit human confirmation"):
        await promotions.decide(
            proposed["id"],
            owner_user_id="user-1",
            decision_key="approve:v1",
            decision="approved",
            rationale="三条独立发布均出现同方向结果。",
            confirmed_by_user=False,
        )

    approved = await promotions.decide(
        proposed["id"],
        owner_user_id="user-1",
        decision_key="approve:v1",
        decision="approved",
        rationale="三条独立发布均出现同方向结果。",
        confirmed_by_user=True,
        occurred_at=datetime(2026, 7, 25, 8, 0, tzinfo=UTC),
    )
    duplicate = await promotions.decide(
        proposed["id"],
        owner_user_id="user-1",
        decision_key="approve:v1",
        decision="approved",
        rationale="三条独立发布均出现同方向结果。",
        confirmed_by_user=True,
        occurred_at=datetime(2026, 7, 25, 8, 0, tzinfo=UTC),
    )

    assert duplicate == approved
    assert approved["status"] == "approved"
    assert approved["decisions"][0]["reviewer_user_id"] == "user-1"
    manifest = await promotions.export_approved(proposed["id"], owner_user_id="user-1")
    assert manifest is not None
    assert manifest["contract_version"] == "personal-ip-approved-evidence-v1"
    assert len(manifest["source_examples"]) == 3
    assert manifest["source_examples"][0]["status"] == "measured"
    assert manifest["source_examples"][0]["comparison_state"] == "unscored"
    assert manifest["promotion"]["evidence_digest"] == proposed["evidence_digest"]
    with pytest.raises(ValueError, match="terminal decision"):
        await promotions.decide(
            proposed["id"],
            owner_user_id="user-1",
            decision_key="reject-later",
            decision="rejected",
            rationale="反悔",
            confirmed_by_user=True,
        )
    await close_engine()


@pytest.mark.asyncio
async def test_evidence_promotion_rejects_partial_duplicate_or_foreign_support(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    partial_ids = await _seed_retrospectives(sf, owner_user_id="user-1", count=3, partial_indexes={2})
    duplicate_publish_ids = await _seed_retrospectives(sf, owner_user_id="user-2", count=3, shared_publish=True)
    foreign_ids = await _seed_retrospectives(sf, owner_user_id="user-3", count=3)
    promotions = PersonalIPEvidencePromotionRepository(sf)

    with pytest.raises(ValueError, match="independent measured retrospectives"):
        await promotions.propose(
            owner_user_id="user-1",
            proposal_key="partial",
            evidence_type="content_pattern",
            claim="部分数据不能凑样本数。",
            retrospective_ids=partial_ids,
            minimum_support=3,
        )
    with pytest.raises(ValueError, match="independent measured retrospectives"):
        await promotions.propose(
            owner_user_id="user-2",
            proposal_key="duplicate-publish",
            evidence_type="audience_pattern",
            claim="同一发布的多个观察窗口不能冒充多个样本。",
            retrospective_ids=duplicate_publish_ids,
            minimum_support=3,
        )
    with pytest.raises(ValueError, match="retrospective not found"):
        await promotions.propose(
            owner_user_id="user-1",
            proposal_key="foreign",
            evidence_type="platform_pattern",
            claim="不能拿别人的证据。",
            retrospective_ids=foreign_ids,
            minimum_support=3,
        )
    await close_engine()
