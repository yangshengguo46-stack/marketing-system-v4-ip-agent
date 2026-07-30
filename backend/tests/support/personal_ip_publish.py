from __future__ import annotations

from typing import Any

from deerflow.personal_ip.publish_compliance import (
    COMPLIANCE_EVIDENCE_SCHEMA_VERSION,
    COMPLIANCE_SCHEMA_VERSION,
)

_COMMERCIAL_DISCLOSURES = {
    "douyin": "visible_ad_disclosure",
    "wechat_channels": "visible_ad_disclosure",
    "wechat_official": "visible_ad_disclosure",
    "xiaohongshu": "visible_ad_disclosure",
    "x": "visible_paid_partnership_disclosure",
    "instagram": "paid_partnership_label",
    "youtube": "paid_promotion_setting",
    "tiktok": "content_disclosure_branded_content",
}
_OWN_BRAND_DISCLOSURES = {
    "douyin": "visible_ad_disclosure",
    "wechat_channels": "visible_ad_disclosure",
    "wechat_official": "visible_ad_disclosure",
    "xiaohongshu": "visible_ad_disclosure",
    "tiktok": "content_disclosure_own_brand",
}
_SYNTHETIC_DISCLOSURES = {
    "douyin": "platform_ai_generated_label",
    "wechat_channels": "platform_ai_generated_label",
    "wechat_official": "platform_ai_generated_label",
    "xiaohongshu": "platform_ai_generated_label",
    "x": "visible_synthetic_media_context",
    "instagram": "ai_disclosure_tool",
    "youtube": "altered_content_setting",
    "tiktok": "ai_generated_content_setting",
}


def compliant_publish_request(
    platform: str,
    *,
    commercial_relationship: str = "none",
    synthetic_media: str = "none",
    sensitive_topics: list[str] | None = None,
    **payload: Any,
) -> dict[str, Any]:
    disclosures: list[str] = []
    if commercial_relationship == "own_brand":
        own_brand = _OWN_BRAND_DISCLOSURES.get(platform)
        if own_brand:
            disclosures.append(own_brand)
    elif commercial_relationship != "none":
        disclosures.append(_COMMERCIAL_DISCLOSURES[platform])
    if synthetic_media == "generated_or_materially_altered":
        disclosures.append(_SYNTHETIC_DISCLOSURES[platform])
    topics = list(sensitive_topics or [])
    return {
        **payload,
        "compliance": {
            "schema_version": COMPLIANCE_SCHEMA_VERSION,
            "commercial_relationship": commercial_relationship,
            "synthetic_media": synthetic_media,
            "sensitive_topics": topics,
            "rights_confirmed": True,
            "moderation_review": {
                "status": "passed",
                "reviewer": "human" if topics else "agent_assisted",
                "notes": "敏感主题已由真人复核" if topics else "",
            },
            "planned_disclosures": disclosures,
        },
    }


def compliant_publish_result(
    receipt: dict[str, Any],
    *,
    evidence_ref: str = "test://publish-settings",
    **payload: Any,
) -> dict[str, Any]:
    compliance_receipt = receipt["request"]["compliance_receipt"]
    return {
        **payload,
        "compliance_evidence": {
            "schema_version": COMPLIANCE_EVIDENCE_SCHEMA_VERSION,
            "receipt_digest": compliance_receipt["receipt_digest"],
            "applied_disclosures": compliance_receipt["required_disclosures"],
            "moderation_status": "passed",
            "evidence_refs": [evidence_ref],
        },
    }
