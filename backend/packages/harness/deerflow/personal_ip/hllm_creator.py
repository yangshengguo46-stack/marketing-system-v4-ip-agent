"""Personal-IP data adapter for ByteDance HLLM-Creator.

The upstream project is kept intact under ``third_party/bytedance/HLLM``. This
module only translates aggregate, account-level content history into the
upstream parquet row contract. It neither narrows an agent run to one account
nor treats anonymous audience embeddings as human identity or ground truth.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deerflow.personal_ip.minecontext import model_evidence_projection

HLLM_UPSTREAM_COMMIT = "864f17221c04a2d3082d9a072df00616bc7e6dab"
HLLM_UPSTREAM_RELATIVE_PATH = Path("third_party/bytedance/HLLM")
HLLM_CREATOR_FIELDS = (
    "user_profile",
    "original_title",
    "original_description",
    "prompt1",
    "prompt2",
    "response",
    "title_list",
    "item_id_list",
)

_FORBIDDEN_VIEWER_IDENTITY_KEYS = {
    "avatar",
    "contact",
    "email",
    "handle",
    "name",
    "nickname",
    "phone",
    "platform_account_id",
    "platform_user_id",
    "profile_url",
    "raw_comments",
    "real_name",
    "user_id",
    "username",
    "viewer_id",
    "wechat",
    "weixin",
}

_REQUIRED_UPSTREAM_FILES = (
    "LICENSE",
    "HLLM_CREATOR_README.md",
    "requirements.txt",
    "code/HLLM_Creator/HLLM_Creator.yaml",
    "code/REC/model/HLLM/hllm_creator.py",
    "code/REC/data/dataset/trainset.py",
    "reproduce/HLLM_Creator/HLLM_Creator.sh",
    "reproduce/HLLM_Creator/HLLM_Creator_eval.sh",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_vendored_hllm(repo_root: str | Path) -> dict[str, Any]:
    """Verify the pinned full upstream source and return its manifest."""

    source_root = Path(repo_root).resolve() / HLLM_UPSTREAM_RELATIVE_PATH
    manifest_path = source_root / "VENDORED_VERSION.json"
    if not manifest_path.is_file():
        raise RuntimeError("vendored HLLM manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "commit": HLLM_UPSTREAM_COMMIT,
        "license": "Apache-2.0",
        "source_mode": "full-upstream-source",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise RuntimeError(f"vendored HLLM {key} does not match the pinned source")
    missing = [relative for relative in _REQUIRED_UPSTREAM_FILES if not (source_root / relative).is_file()]
    if missing:
        raise RuntimeError(f"vendored HLLM source is incomplete: {', '.join(missing)}")
    checksums = {
        "license_sha256": source_root / "LICENSE",
        "creator_model_sha256": source_root / "code/REC/model/HLLM/hllm_creator.py",
    }
    for key, path in checksums.items():
        if manifest.get(key) != _sha256(path):
            raise RuntimeError(f"vendored HLLM checksum mismatch: {path.name}")
    return manifest


def _normalized_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_")


def _assert_no_individual_viewer_identity(value: Any, *, field: str) -> None:
    if isinstance(value, Mapping):
        leaked = sorted(_FORBIDDEN_VIEWER_IDENTITY_KEYS & {_normalized_key(key) for key in value})
        if leaked:
            raise ValueError(f"{field} contains individual viewer identity: {', '.join(leaked)}")
        for key, item in value.items():
            _assert_no_individual_viewer_identity(item, field=f"{field}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _assert_no_individual_viewer_identity(item, field=f"{field}[{index}]")


def _clean_text(value: Any, *, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise ValueError(f"{field} is required")
    return text[:limit]


def _parse_time(value: Any, *, field: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _stable_item_id(content_id: str) -> int:
    value = int.from_bytes(hashlib.sha256(content_id.encode("utf-8")).digest()[:8], "big")
    return value % 2_147_483_646 + 1


def _aggregate_metrics(value: Any, *, field: str) -> dict[str, int | float]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object when supplied")
    metrics: dict[str, int | float] = {}
    for key, raw in sorted(value.items(), key=lambda item: str(item[0])):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
            raise ValueError(f"{field}.{key} must be a finite aggregate metric")
        metrics[str(key)[:80]] = raw
    return metrics


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class HLLMCreatorAdapter:
    """Build HLLM-Creator examples without duplicating its model code."""

    def __init__(self, *, max_history: int = 50) -> None:
        if not 1 <= max_history <= 500:
            raise ValueError("max_history must be between 1 and 500")
        self.max_history = max_history

    def build_example(
        self,
        *,
        history: Sequence[Mapping[str, Any]],
        audience_profile: Mapping[str, Any],
        creator_profile: Mapping[str, Any],
        target: Mapping[str, Any],
        expected_creative: str = "",
        local_context_evidence: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        """Return one row accepted by upstream ``CreatorProcessor``.

        When history exists it is a chronological proxy built from aggregate
        account outcomes, never person-level click history. With no history,
        the same row carries an explicit cold-start hypothesis basis so the
        first pilot can be preflighted without inventing account evidence.
        """

        _assert_no_individual_viewer_identity(history, field="history")
        _assert_no_individual_viewer_identity(audience_profile, field="audience_profile")

        ordered: list[tuple[datetime, str, str]] = []
        for index, item in enumerate(history):
            content_id = _clean_text(item.get("content_id"), field=f"history[{index}].content_id", limit=256)
            published_at = _parse_time(item.get("published_at"), field=f"history[{index}].published_at")
            title = _clean_text(item.get("title"), field=f"history[{index}].title", limit=768)
            platform = _clean_text(item.get("platform"), field=f"history[{index}].platform", limit=64)
            content_type = _clean_text(
                item.get("content_type", "content"),
                field=f"history[{index}].content_type",
                limit=80,
            )
            metrics = _aggregate_metrics(item.get("metrics"), field=f"history[{index}].metrics")
            feature_text = f"{title} | platform={platform} | type={content_type} | aggregate_metrics={_canonical_json(metrics)}"
            ordered.append((published_at, feature_text[:4096], content_id))
        recent = sorted(ordered, key=lambda item: (item[0], item[2]))[-self.max_history :]
        audience_basis = "aggregate_account_cohort" if recent else "cold_start_hypothesis"

        target_title = _clean_text(target.get("title"), field="target.title", limit=768)
        target_description = _clean_text(target.get("description"), field="target.description", limit=4096)
        profile = {
            "schema_version": "personal-ip-hllm-audience-v2",
            "audience_basis": audience_basis,
            "privacy": "anonymous_cohort_no_individual_viewer_identity",
            "interpretable_projection": dict(audience_profile),
        }
        if local_context_evidence:
            profile["local_context_evidence"] = model_evidence_projection(local_context_evidence)
        if recent:
            prompt1 = "你是个人 IP 创意生成器。前面插入的是根据跨平台历史内容及实绩形成的匿名受众群体向量。请在不虚构受众事实、不破坏创作者表达边界的前提下，生成更匹配该受众的创意：\n"
        else:
            prompt1 = "你是个人 IP 创意生成器。当前没有账号历史，受众描述只是待验证的冷启动假设。请在不虚构受众事实、不破坏创作者表达边界的前提下，生成可被首轮试播验证的创意：\n"
        prompt2 = f"目标内容：{target_title}\n内容说明：{target_description}\n创作者约束：{_canonical_json(dict(creator_profile))}\n只输出最终创意，不要解释："
        values: dict[str, Any] = {
            "user_profile": _canonical_json(profile),
            "original_title": target_title,
            "original_description": target_description,
            "prompt1": prompt1,
            "prompt2": prompt2,
            "response": " ".join(str(expected_creative or "").split())[:4096],
            "title_list": [item[1] for item in recent],
            "item_id_list": [_stable_item_id(item[2]) for item in recent],
        }
        return {field: values[field] for field in HLLM_CREATOR_FIELDS}
