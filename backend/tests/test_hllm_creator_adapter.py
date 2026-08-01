from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deerflow.personal_ip.hllm_creator import (
    HLLM_CREATOR_FIELDS,
    HLLM_UPSTREAM_COMMIT,
    HLLMCreatorAdapter,
    verify_vendored_hllm,
)


def _history_item(index: int) -> dict:
    return {
        "content_id": f"video-{index}",
        "published_at": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)).isoformat(),
        "platform": "douyin",
        "title": f"第 {index} 条内容",
        "content_type": "short_video",
        "metrics": {"views": index * 100, "likes": index * 10},
    }


def test_adapter_builds_upstream_parquet_contract_from_aggregate_history() -> None:
    adapter = HLLMCreatorAdapter(max_history=50)

    row = adapter.build_example(
        history=[_history_item(index) for index in range(55, 0, -1)],
        audience_profile={
            "cohort_label": "关注本地智能体的创作者",
            "long_term_interest": ["个人 IP", "自动化"],
            "maslow_projection": "esteem",
            "jungian_projection": "Ne",
        },
        creator_profile={
            "positioning": "讲清楚本地智能体如何经营个人 IP",
            "voice": ["直接", "不用术语堆砌"],
        },
        target={
            "content_id": "draft-1",
            "title": "DeerFlow 与 HLLM-Creator",
            "description": "解释受众建模和内容预演如何结合。",
        },
        expected_creative="让智能体先懂观众，再替你做内容",
    )

    assert tuple(row) == HLLM_CREATOR_FIELDS
    assert len(row["title_list"]) == 50
    assert row["title_list"][0].startswith("第 6 条内容")
    assert row["title_list"][-1].startswith("第 55 条内容")
    assert len(row["item_id_list"]) == 50
    assert all(isinstance(item_id, int) and item_id > 0 for item_id in row["item_id_list"])
    assert row["response"] == "让智能体先懂观众，再替你做内容"
    assert "创作者约束" in row["prompt2"]
    assert json.loads(row["user_profile"])["audience_basis"] == "aggregate_account_cohort"


def test_adapter_builds_an_explicit_cold_start_example_without_inventing_history() -> None:
    row = HLLMCreatorAdapter().build_example(
        history=[],
        audience_profile={"hypothesis": "可能关心开店过程的本地顾客"},
        creator_profile={"voice": ["真实", "具体"]},
        target={"content_id": "pilot-1", "title": "第一次选址", "description": "记录开店选址过程"},
    )

    profile = json.loads(row["user_profile"])
    assert profile["audience_basis"] == "cold_start_hypothesis"
    assert row["title_list"] == []
    assert row["item_id_list"] == []
    assert "没有账号历史" in row["prompt1"]


def test_adapter_rejects_individual_viewer_identity() -> None:
    adapter = HLLMCreatorAdapter()

    with pytest.raises(ValueError, match="individual viewer identity"):
        adapter.build_example(
            history=[_history_item(1)],
            audience_profile={"cohort_label": "潜在客户", "viewer_id": "platform-user-123"},
            creator_profile={},
            target={"content_id": "draft-1", "title": "标题", "description": "说明"},
        )


def test_adapter_accepts_content_history_without_operating_metrics() -> None:
    adapter = HLLMCreatorAdapter()
    history = _history_item(1)
    history["metrics"] = {}

    example = adapter.build_example(
        history=[history],
        audience_profile={"cohort_label": "潜在客户"},
        creator_profile={},
        target={"content_id": "draft-1", "title": "标题", "description": "说明"},
    )
    assert "aggregate_metrics={}" in example["title_list"][0]


def test_adapter_embeds_only_sealed_local_context_projection() -> None:
    adapter = HLLMCreatorAdapter()
    row = adapter.build_example(
        history=[_history_item(1)],
        audience_profile={"cohort_label": "创作者"},
        creator_profile={"voice": ["直接"]},
        target={"content_id": "draft-1", "title": "标题", "description": "说明"},
        local_context_evidence=[
            {
                "schema_version": "personal-ip-local-context-evidence-v1",
                "evidence_id": "mctx_1",
                "source": {
                    "source_kind": "projects",
                    "context_type": "activity",
                    "observed_at": "2026-07-22T05:00:00+00:00",
                },
                "summary": {"title": "路线图", "text": "下周交付", "keywords": ["交付"]},
                "digest": "a" * 64,
                "raw_private_text": "must never cross",
            }
        ],
    )

    profile = json.loads(row["user_profile"])
    projection = profile["local_context_evidence"]
    assert projection["schema_version"] == "personal-ip-hllm-context-evidence-v1"
    assert projection["epistemic_status"] == "observational_partial_revisable"
    assert projection["raw_content_included"] is False
    assert projection["items"][0]["summary"] == "下周交付"
    assert "raw_private_text" not in row["user_profile"]
    assert "must never cross" not in row["user_profile"]


def test_vendored_hllm_source_is_pinned_and_complete() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    manifest = verify_vendored_hllm(repo_root)

    assert manifest["commit"] == HLLM_UPSTREAM_COMMIT
    assert manifest["license"] == "Apache-2.0"
    assert manifest["source_mode"] == "full-upstream-source"
