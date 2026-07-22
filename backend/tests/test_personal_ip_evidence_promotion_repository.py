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
                training_eligibility_json={"status": "eligible_for_policy_evaluation"},
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
async def test_evidence_promotion_auto_approves_cross_sample_support(tmp_path) -> None:
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
    promoted = await promotions.propose(**kwargs)
    replayed = await promotions.propose(**kwargs)

    assert replayed == promoted
    assert promoted["status"] == "approved"
    assert promoted["decided_at"] is not None
    assert promoted["evidence_summary"]["independent_measured_support"] == 3
    assert promoted["evidence_summary"]["account_count"] == 2
    assert promoted["decisions"][0]["decision"] == "approved"
    assert promoted["decisions"][0]["reviewer_source"] == "cross_sample_evidence_policy"
    assert "reviewer_user_id" not in promoted["decisions"][0]
    manifest = await promotions.export_approved(promoted["id"], owner_user_id="user-1")
    assert manifest is not None
    assert manifest["contract_version"] == "personal-ip-approved-evidence-v1"
    assert len(manifest["source_examples"]) == 3
    assert manifest["source_examples"][0]["status"] == "measured"
    assert manifest["source_examples"][0]["comparison_state"] == "unscored"
    assert manifest["promotion"]["evidence_digest"] == promoted["evidence_digest"]
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
    mixed_ids = await _seed_retrospectives(sf, owner_user_id="user-4", count=4, partial_indexes={3})
    with pytest.raises(ValueError, match="only completely measured"):
        await promotions.propose(
            owner_user_id="user-4",
            proposal_key="mixed",
            evidence_type="content_pattern",
            claim="部分样本不能混入晋级依据。",
            retrospective_ids=mixed_ids,
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
