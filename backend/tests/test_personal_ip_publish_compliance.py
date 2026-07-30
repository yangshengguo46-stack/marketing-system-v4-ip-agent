from __future__ import annotations

import pytest

from deerflow.personal_ip.publish_compliance import (
    COMPLIANCE_EVIDENCE_SCHEMA_VERSION,
    COMPLIANCE_SCHEMA_VERSION,
    compile_publish_compliance,
    validate_publish_compliance_evidence,
)


def _declaration(
    *planned_disclosures: str,
    commercial_relationship: str = "paid_partnership",
    synthetic_media: str = "generated_or_materially_altered",
    sensitive_topics: list[str] | None = None,
) -> dict:
    topics = list(sensitive_topics or [])
    return {
        "schema_version": COMPLIANCE_SCHEMA_VERSION,
        "commercial_relationship": commercial_relationship,
        "synthetic_media": synthetic_media,
        "sensitive_topics": topics,
        "rights_confirmed": True,
        "moderation_review": {
            "status": "passed",
            "reviewer": "human" if topics else "agent_assisted",
            "notes": "医疗表达已由真人复核" if topics else "",
        },
        "planned_disclosures": list(planned_disclosures),
    }


@pytest.mark.parametrize(
    ("platform", "commercial_disclosure", "synthetic_disclosure"),
    [
        ("douyin", "visible_ad_disclosure", "platform_ai_generated_label"),
        ("wechat_channels", "visible_ad_disclosure", "platform_ai_generated_label"),
        ("wechat_official", "visible_ad_disclosure", "platform_ai_generated_label"),
        ("xiaohongshu", "visible_ad_disclosure", "platform_ai_generated_label"),
        ("x", "visible_paid_partnership_disclosure", "visible_synthetic_media_context"),
        ("instagram", "paid_partnership_label", "ai_disclosure_tool"),
        ("youtube", "paid_promotion_setting", "altered_content_setting"),
        ("tiktok", "content_disclosure_branded_content", "ai_generated_content_setting"),
    ],
)
def test_compile_publish_compliance_is_versioned_for_all_eight_platforms(
    platform: str,
    commercial_disclosure: str,
    synthetic_disclosure: str,
) -> None:
    declaration, receipt = compile_publish_compliance(
        platform,
        _declaration(
            commercial_disclosure,
            synthetic_disclosure,
            sensitive_topics=["health"],
        ),
    )

    assert declaration["planned_disclosures"] == [
        commercial_disclosure,
        synthetic_disclosure,
    ]
    assert receipt["schema_version"] == COMPLIANCE_SCHEMA_VERSION
    assert receipt["platform"] == platform
    assert receipt["policy_version"].startswith("2026-07-30.")
    assert receipt["policy_reviewed_at"] == "2026-07-30"
    assert receipt["required_disclosures"] == [
        commercial_disclosure,
        synthetic_disclosure,
    ]
    assert receipt["decision"] == "ready_for_publish"
    assert len(receipt["receipt_digest"]) == 64
    assert len(receipt["policy_sources"]) >= 2
    assert all(source.startswith("https://") for source in receipt["policy_sources"])


def test_compile_publish_compliance_rejects_missing_or_false_attestations() -> None:
    with pytest.raises(ValueError, match="compliance declaration is required"):
        compile_publish_compliance("youtube", None)

    declaration = _declaration("paid_promotion_setting", "altered_content_setting")
    declaration["rights_confirmed"] = False
    with pytest.raises(ValueError, match="rights_confirmed"):
        compile_publish_compliance("youtube", declaration)

    declaration = _declaration("paid_promotion_setting", "altered_content_setting")
    declaration["moderation_review"]["status"] = "pending"
    with pytest.raises(ValueError, match="moderation_review.status"):
        compile_publish_compliance("youtube", declaration)


def test_compile_publish_compliance_rejects_missing_or_unnecessary_disclosures() -> None:
    with pytest.raises(ValueError, match="planned_disclosures"):
        compile_publish_compliance(
            "tiktok",
            _declaration("ai_generated_content_setting"),
        )

    with pytest.raises(ValueError, match="planned_disclosures"):
        compile_publish_compliance(
            "youtube",
            _declaration(
                "paid_promotion_setting",
                commercial_relationship="none",
                synthetic_media="none",
            ),
        )


def test_sensitive_topics_require_human_review_and_notes() -> None:
    declaration = _declaration(
        "altered_content_setting",
        commercial_relationship="none",
        sensitive_topics=["finance"],
    )
    declaration["moderation_review"] = {
        "status": "passed",
        "reviewer": "agent_assisted",
        "notes": "",
    }
    with pytest.raises(ValueError, match="human review"):
        compile_publish_compliance("youtube", declaration)


def test_published_attempt_requires_evidence_bound_to_the_compliance_receipt() -> None:
    declaration, receipt = compile_publish_compliance(
        "instagram",
        _declaration("paid_partnership_label", "ai_disclosure_tool"),
    )
    request = {
        "caption": "候选文案",
        "compliance": declaration,
        "compliance_receipt": receipt,
    }

    with pytest.raises(ValueError, match="compliance_evidence"):
        validate_publish_compliance_evidence(request, {})

    with pytest.raises(ValueError, match="receipt_digest"):
        validate_publish_compliance_evidence(
            request,
            {
                "compliance_evidence": {
                    "schema_version": COMPLIANCE_EVIDENCE_SCHEMA_VERSION,
                    "receipt_digest": "0" * 64,
                    "applied_disclosures": [
                        "paid_partnership_label",
                        "ai_disclosure_tool",
                    ],
                    "moderation_status": "passed",
                    "evidence_refs": ["browser://publish-settings"],
                }
            },
        )

    evidence = validate_publish_compliance_evidence(
        request,
        {
            "compliance_evidence": {
                "schema_version": COMPLIANCE_EVIDENCE_SCHEMA_VERSION,
                "receipt_digest": receipt["receipt_digest"],
                "applied_disclosures": [
                    "paid_partnership_label",
                    "ai_disclosure_tool",
                ],
                "moderation_status": "passed",
                "evidence_refs": ["browser://publish-settings"],
            }
        },
    )
    assert evidence["receipt_digest"] == receipt["receipt_digest"]
