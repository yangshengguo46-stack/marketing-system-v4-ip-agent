from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from test_personal_ip_differentiation import DIFFERENTIATION_THESIS, EVIDENCE_REFS

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_differentiation import PersonalIPDifferentiationRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository


def test_completed_contradictory_observations_cannot_validate_a_thesis() -> None:
    with pytest.raises(ValueError, match="supportive observations"):
        PersonalIPDifferentiationRepository._enforce_observation_gate(
            status="validated",
            summary={
                "complete_observation_count": 3,
                "supportive_observation_count": 0,
                "contradictory_observation_count": 3,
                "supportive_observation_types": [],
                "has_downstream_outcome": False,
            },
        )


@pytest.mark.asyncio
async def test_differentiation_versions_are_immutable_owner_scoped_and_evidence_gated(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    try:
        sf = get_session_factory()
        assert sf is not None
        subjects = PersonalIPSubjectRepository(sf)
        repo = PersonalIPDifferentiationRepository(sf)
        product = await subjects.create(
            owner_user_id="user-1",
            display_name="IP Agent",
            subject_type="product",
            relationship="self",
        )

        candidate = await repo.create_version(
            owner_user_id="user-1",
            operation_key="difference:candidate:v1",
            subject_id=product["id"],
            thesis_key="ip-agent-core",
            status="candidate",
            evidence_refs=EVIDENCE_REFS,
            **DIFFERENTIATION_THESIS,
        )
        assert candidate["version"] == 1
        assert candidate["primary_entity"]["entity_type"] == "product"

        replay = await repo.create_version(
            owner_user_id="user-1",
            operation_key="difference:candidate:v1",
            subject_id=product["id"],
            thesis_key="ip-agent-core",
            status="candidate",
            evidence_refs=EVIDENCE_REFS,
            **DIFFERENTIATION_THESIS,
        )
        assert replay["id"] == candidate["id"]

        changed = deepcopy(DIFFERENTIATION_THESIS)
        changed["strategic_difference"]["reason_to_choose"] = "另一个选择理由"
        with pytest.raises(ValueError, match="different differentiation version"):
            await repo.create_version(
                owner_user_id="user-1",
                operation_key="difference:candidate:v1",
                subject_id=product["id"],
                thesis_key="ip-agent-core",
                status="candidate",
                evidence_refs=EVIDENCE_REFS,
                **changed,
            )

        pilot = await repo.create_version(
            owner_user_id="user-1",
            operation_key="difference:pilot:v2",
            subject_id=product["id"],
            thesis_key="ip-agent-core",
            status="pilot",
            evidence_refs=EVIDENCE_REFS,
            **DIFFERENTIATION_THESIS,
        )
        assert pilot["version"] == 2
        assert await repo.get_latest(product["id"], owner_user_id="user-2") is None

        observed_at = datetime.now(UTC) - timedelta(days=1)
        first_observation = await repo.record_observation(
            owner_user_id="user-1",
            operation_key="difference:observation:1",
            subject_id=product["id"],
            differentiation_version_id=pilot["id"],
            observation_type="recognition",
            source="audience_feedback",
            observed_at=observed_at,
            coverage_status="complete",
            measures={
                "result": "supports",
                "qualified_mentions": 3,
                "attribution_phrase": "经营证据链",
            },
            evidence_refs=[{"kind": "audience_feedback", "id": "feedback-1"}],
        )
        assert first_observation["observation_type"] == "recognition"
        assert len(await repo.list_observations("user-1", subject_id=product["id"])) == 1

        provisional = await repo.create_version(
            owner_user_id="user-1",
            operation_key="difference:provisional:v3",
            subject_id=product["id"],
            thesis_key="ip-agent-core",
            status="provisionally_adopted",
            evidence_refs=EVIDENCE_REFS,
            **DIFFERENTIATION_THESIS,
        )
        assert provisional["status"] == "provisionally_adopted"

        with pytest.raises(ValueError, match="at least three complete"):
            await repo.create_version(
                owner_user_id="user-1",
                operation_key="difference:validated:too-early",
                subject_id=product["id"],
                thesis_key="ip-agent-core",
                status="validated",
                evidence_refs=EVIDENCE_REFS,
                **DIFFERENTIATION_THESIS,
            )

        for index, observation_type in enumerate(("trust", "adoption"), start=2):
            await repo.record_observation(
                owner_user_id="user-1",
                operation_key=f"difference:observation:{index}",
                subject_id=product["id"],
                differentiation_version_id=provisional["id"],
                observation_type=observation_type,
                source="commercial_record" if observation_type == "adoption" else "audience_feedback",
                observed_at=observed_at + timedelta(hours=index),
                coverage_status="complete",
                measures={"result": "supports", "qualified_events": index},
                evidence_refs=[
                    {
                        "kind": "commercial_signal" if observation_type == "adoption" else "audience_feedback",
                        "id": f"evidence-{index}",
                    }
                ],
            )

        validated = await repo.create_version(
            owner_user_id="user-1",
            operation_key="difference:validated:v4",
            subject_id=product["id"],
            thesis_key="ip-agent-core",
            status="validated",
            evidence_refs=EVIDENCE_REFS,
            **DIFFERENTIATION_THESIS,
        )
        assert validated["status"] == "validated"
        assert validated["validation_summary"]["complete_observation_count"] == 3
        assert validated["validation_summary"]["supportive_observation_count"] == 3
        assert "adoption" in validated["validation_summary"]["supportive_observation_types"]

        late_replay = await repo.create_version(
            owner_user_id="user-1",
            operation_key="difference:candidate:v1",
            subject_id=product["id"],
            thesis_key="ip-agent-core",
            status="candidate",
            evidence_refs=EVIDENCE_REFS,
            **DIFFERENTIATION_THESIS,
        )
        assert late_replay["id"] == candidate["id"]
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_new_thesis_lineage_must_restart_as_candidate(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    try:
        sf = get_session_factory()
        assert sf is not None
        subjects = PersonalIPSubjectRepository(sf)
        repo = PersonalIPDifferentiationRepository(sf)
        subject = await subjects.create(owner_user_id="user-1", display_name="品牌甲", subject_type="brand")
        await repo.create_version(
            owner_user_id="user-1",
            operation_key="difference:a",
            subject_id=subject["id"],
            thesis_key="direction-a",
            status="candidate",
            evidence_refs=EVIDENCE_REFS,
            **DIFFERENTIATION_THESIS,
        )
        with pytest.raises(ValueError, match="new thesis_key"):
            await repo.create_version(
                owner_user_id="user-1",
                operation_key="difference:b",
                subject_id=subject["id"],
                thesis_key="direction-b",
                status="pilot",
                evidence_refs=EVIDENCE_REFS,
                **DIFFERENTIATION_THESIS,
            )
    finally:
        await close_engine()
