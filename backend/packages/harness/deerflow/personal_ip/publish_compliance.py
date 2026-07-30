"""Versioned, deterministic publication-compliance contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

COMPLIANCE_SCHEMA_VERSION = "personal-ip-publish-compliance-v1"
COMPLIANCE_EVIDENCE_SCHEMA_VERSION = "personal-ip-publish-compliance-evidence-v1"
POLICY_REVIEWED_AT = "2026-07-30"

_COMMERCIAL_RELATIONSHIPS = {
    "none",
    "own_brand",
    "paid_partnership",
    "gifted",
    "affiliate",
}
_SYNTHETIC_MEDIA_STATES = {
    "none",
    "assistive",
    "generated_or_materially_altered",
}
_SENSITIVE_TOPICS = {
    "health",
    "finance",
    "elections",
    "conflict",
    "disaster",
    "minors",
    "regulated_goods",
}
_CHINA_AI_SOURCE = "https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm"
_CHINA_AD_SOURCE = "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/ggjgs/art/2024/art_89824524f2804c5594e95408fbdf8602.html"


@dataclass(frozen=True)
class PlatformPublishPolicy:
    version: str
    default_commercial_disclosure: str | None
    own_brand_disclosure: str | None
    synthetic_disclosure: str
    policy_sources: tuple[str, ...]

    def commercial_disclosure(self, relationship: str) -> str | None:
        if relationship == "none":
            return None
        if relationship == "own_brand":
            return self.own_brand_disclosure
        return self.default_commercial_disclosure


_POLICIES = {
    "douyin": PlatformPublishPolicy(
        version="2026-07-30.douyin.1",
        default_commercial_disclosure="visible_ad_disclosure",
        own_brand_disclosure="visible_ad_disclosure",
        synthetic_disclosure="platform_ai_generated_label",
        policy_sources=(_CHINA_AI_SOURCE, _CHINA_AD_SOURCE),
    ),
    "wechat_channels": PlatformPublishPolicy(
        version="2026-07-30.wechat-channels.1",
        default_commercial_disclosure="visible_ad_disclosure",
        own_brand_disclosure="visible_ad_disclosure",
        synthetic_disclosure="platform_ai_generated_label",
        policy_sources=(_CHINA_AI_SOURCE, _CHINA_AD_SOURCE),
    ),
    "wechat_official": PlatformPublishPolicy(
        version="2026-07-30.wechat-official.1",
        default_commercial_disclosure="visible_ad_disclosure",
        own_brand_disclosure="visible_ad_disclosure",
        synthetic_disclosure="platform_ai_generated_label",
        policy_sources=(_CHINA_AI_SOURCE, _CHINA_AD_SOURCE),
    ),
    "xiaohongshu": PlatformPublishPolicy(
        version="2026-07-30.xiaohongshu.1",
        default_commercial_disclosure="visible_ad_disclosure",
        own_brand_disclosure="visible_ad_disclosure",
        synthetic_disclosure="platform_ai_generated_label",
        policy_sources=(
            _CHINA_AI_SOURCE,
            _CHINA_AD_SOURCE,
            "https://pgy.xiaohongshu.com/faq",
        ),
    ),
    "x": PlatformPublishPolicy(
        version="2026-07-30.x.1",
        default_commercial_disclosure="visible_paid_partnership_disclosure",
        own_brand_disclosure=None,
        synthetic_disclosure="visible_synthetic_media_context",
        policy_sources=(
            "https://help.x.com/en/rules-and-policies/paid-partnerships-policy.html",
            "https://help.x.com/en/rules-and-policies/authenticity",
        ),
    ),
    "instagram": PlatformPublishPolicy(
        version="2026-07-30.instagram.1",
        default_commercial_disclosure="paid_partnership_label",
        own_brand_disclosure=None,
        synthetic_disclosure="ai_disclosure_tool",
        policy_sources=(
            "https://www.facebook.com/help/instagram/616901995832907",
            "https://about.fb.com/news/2024/02/labeling-ai-generated-images-on-facebook-instagram-and-threads/",
        ),
    ),
    "youtube": PlatformPublishPolicy(
        version="2026-07-30.youtube.1",
        default_commercial_disclosure="paid_promotion_setting",
        own_brand_disclosure=None,
        synthetic_disclosure="altered_content_setting",
        policy_sources=(
            "https://support.google.com/youtube/answer/10588440",
            "https://support.google.com/youtube/answer/14328491",
        ),
    ),
    "tiktok": PlatformPublishPolicy(
        version="2026-07-30.tiktok.1",
        default_commercial_disclosure="content_disclosure_branded_content",
        own_brand_disclosure="content_disclosure_own_brand",
        synthetic_disclosure="ai_generated_content_setting",
        policy_sources=(
            "https://support.tiktok.com/en/business-and-creator/creator-and-business-accounts/promoting-a-brand-product-or-service",
            "https://support.tiktok.com/en/using-tiktok/creating-videos/ai-generated-content",
        ),
    ),
}


def _digest(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _required_text(value: Any, *, field: str, limit: int = 2000) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _string_list(value: Any, *, field: str, allowed: set[str] | None = None) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result: list[str] = []
    for item in value:
        text = _required_text(item, field=field, limit=128)
        if allowed is not None and text not in allowed:
            raise ValueError(f"{field} contains an unsupported value")
        if text in result:
            raise ValueError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _required_disclosures(
    policy: PlatformPublishPolicy,
    *,
    commercial_relationship: str,
    synthetic_media: str,
) -> list[str]:
    required: list[str] = []
    commercial = policy.commercial_disclosure(commercial_relationship)
    if commercial:
        required.append(commercial)
    if synthetic_media == "generated_or_materially_altered":
        required.append(policy.synthetic_disclosure)
    return required


def compile_publish_compliance(
    platform: str,
    declaration: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate one declaration and compile its immutable platform receipt."""

    policy = _POLICIES.get(str(platform or "").strip())
    if policy is None:
        raise ValueError("unsupported publish compliance platform")
    if not isinstance(declaration, dict) or not declaration:
        raise ValueError("publish compliance declaration is required")
    if declaration.get("compliance_receipt") is not None:
        raise ValueError("compliance_receipt is server-owned")

    schema_version = str(declaration.get("schema_version") or "").strip()
    if schema_version != COMPLIANCE_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {COMPLIANCE_SCHEMA_VERSION}")
    commercial_relationship = str(declaration.get("commercial_relationship") or "").strip()
    if commercial_relationship not in _COMMERCIAL_RELATIONSHIPS:
        raise ValueError("commercial_relationship is unsupported")
    synthetic_media = str(declaration.get("synthetic_media") or "").strip()
    if synthetic_media not in _SYNTHETIC_MEDIA_STATES:
        raise ValueError("synthetic_media is unsupported")
    if declaration.get("rights_confirmed") is not True:
        raise ValueError("rights_confirmed must be true before publishing")

    sensitive_topics = _string_list(
        declaration.get("sensitive_topics"),
        field="sensitive_topics",
        allowed=_SENSITIVE_TOPICS,
    )
    moderation = declaration.get("moderation_review")
    if not isinstance(moderation, dict):
        raise ValueError("moderation_review must be an object")
    moderation_status = str(moderation.get("status") or "").strip()
    if moderation_status != "passed":
        raise ValueError("moderation_review.status must be passed")
    reviewer = str(moderation.get("reviewer") or "").strip()
    if reviewer not in {"human", "agent_assisted"}:
        raise ValueError("moderation_review.reviewer is unsupported")
    notes = " ".join(str(moderation.get("notes") or "").split())
    if len(notes) > 4000:
        raise ValueError("moderation_review.notes is too long")
    if sensitive_topics and (reviewer != "human" or not notes):
        raise ValueError("sensitive topics require human review and non-empty notes")

    planned_disclosures = _string_list(
        declaration.get("planned_disclosures"),
        field="planned_disclosures",
    )
    required_disclosures = _required_disclosures(
        policy,
        commercial_relationship=commercial_relationship,
        synthetic_media=synthetic_media,
    )
    if planned_disclosures != required_disclosures:
        raise ValueError(f"planned_disclosures must exactly match the platform-required disclosures {required_disclosures}")

    normalized = {
        "schema_version": COMPLIANCE_SCHEMA_VERSION,
        "commercial_relationship": commercial_relationship,
        "synthetic_media": synthetic_media,
        "sensitive_topics": sensitive_topics,
        "rights_confirmed": True,
        "moderation_review": {
            "status": "passed",
            "reviewer": reviewer,
            "notes": notes,
        },
        "planned_disclosures": planned_disclosures,
    }
    receipt = {
        "schema_version": COMPLIANCE_SCHEMA_VERSION,
        "platform": str(platform).strip(),
        "policy_version": policy.version,
        "policy_reviewed_at": POLICY_REVIEWED_AT,
        "policy_sources": list(policy.policy_sources),
        "commercial_relationship": commercial_relationship,
        "synthetic_media": synthetic_media,
        "sensitive_topics": sensitive_topics,
        "required_disclosures": required_disclosures,
        "moderation_review": normalized["moderation_review"],
        "decision": "ready_for_publish",
    }
    receipt["receipt_digest"] = _digest(receipt)
    return normalized, receipt


def validate_publish_compliance_evidence(
    request_payload: dict[str, Any],
    result_payload: dict[str, Any],
) -> dict[str, Any]:
    """Require terminal publication evidence for the sealed compliance plan."""

    receipt = request_payload.get("compliance_receipt")
    if not isinstance(receipt, dict) or receipt.get("schema_version") != COMPLIANCE_SCHEMA_VERSION:
        raise ValueError("publish request has no valid compliance receipt")
    evidence = result_payload.get("compliance_evidence")
    if not isinstance(evidence, dict):
        raise ValueError("published attempts require compliance_evidence")
    if evidence.get("schema_version") != COMPLIANCE_EVIDENCE_SCHEMA_VERSION:
        raise ValueError(f"compliance_evidence.schema_version must be {COMPLIANCE_EVIDENCE_SCHEMA_VERSION}")
    receipt_digest = str(evidence.get("receipt_digest") or "").strip()
    if receipt_digest != receipt.get("receipt_digest"):
        raise ValueError("compliance_evidence.receipt_digest does not match the publish request")
    applied = _string_list(
        evidence.get("applied_disclosures"),
        field="compliance_evidence.applied_disclosures",
    )
    if applied != list(receipt.get("required_disclosures") or []):
        raise ValueError("compliance_evidence.applied_disclosures must match the sealed compliance receipt")
    if evidence.get("moderation_status") != "passed":
        raise ValueError("compliance_evidence.moderation_status must be passed")
    evidence_refs = _string_list(
        evidence.get("evidence_refs"),
        field="compliance_evidence.evidence_refs",
    )
    if not evidence_refs:
        raise ValueError("compliance_evidence.evidence_refs must not be empty")
    return {
        "schema_version": COMPLIANCE_EVIDENCE_SCHEMA_VERSION,
        "receipt_digest": receipt_digest,
        "applied_disclosures": applied,
        "moderation_status": "passed",
        "evidence_refs": evidence_refs,
    }
