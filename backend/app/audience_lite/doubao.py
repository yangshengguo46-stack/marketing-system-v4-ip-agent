"""Doubao-backed creative generator for the first HLLM-Lite stage."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from deerflow.personal_ip.audience_provider import AudienceCreativeVariant, AudiencePreflightRequest

_DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
_DEFAULT_MODEL = "doubao-seed-2-0-pro-260215"


class AudienceLiteGenerationError(RuntimeError):
    """Raised when HLLM-Lite cannot obtain a valid structured generation."""


def _json_object(text: str) -> dict[str, Any]:
    candidate = str(text or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise AudienceLiteGenerationError("Doubao did not return valid JSON") from exc
    if not isinstance(value, dict):
        raise AudienceLiteGenerationError("Doubao response must be a JSON object")
    return value


class DoubaoAudienceGenerator:
    """Generate audience-conditioned variants without pretending to rank them."""

    provider = "hllm-lite"
    algorithm_version = "doubao-profile-conditioned-v0"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_ARK_BASE_URL,
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = str(api_key or "").strip() or None
        self.model = str(model or "").strip()
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        if not self.model:
            raise ValueError("Doubao audience model is required")
        if not self.base_url.startswith("https://") and not self.base_url.startswith(("http://localhost", "http://127.0.0.1")):
            raise ValueError("Doubao base URL must use HTTPS unless it is local")

    @classmethod
    def from_env(cls) -> DoubaoAudienceGenerator:
        return cls(
            api_key=os.getenv("VOLCENGINE_API_KEY"),
            model=os.getenv("PERSONAL_IP_AUDIENCE_MODEL", _DEFAULT_MODEL),
            base_url=os.getenv("VOLCENGINE_ARK_BASE_URL", _DEFAULT_ARK_BASE_URL),
        )

    @property
    def model_version(self) -> str:
        return self.model

    @property
    def configured(self) -> bool:
        return self.api_key is not None

    @staticmethod
    def _prompt(request: AudiencePreflightRequest) -> str:
        example = request.to_payload()["example"]
        return (
            "你是个人 IP 内容预演中的创意生成器。请根据匿名受众群体画像、历史内容及其聚合实绩，"
            "为目标内容生成不同角度的候选创意。不得虚构受众个人信息，不得声称预测结果必然发生。\n\n"
            f"匿名受众画像：{example['user_profile']}\n"
            f"历史内容与聚合实绩：{json.dumps(example['title_list'], ensure_ascii=False)}\n"
            f"目标标题：{example['original_title']}\n"
            f"目标说明：{example['original_description']}\n"
            f"生成约束：{example['prompt2']}\n\n"
            f"生成 {request.variant_count} 个候选。只输出 JSON："
            '{"variants":[{"text":"候选创意","tags":["角度标签"]}]}。'
        )

    async def generate(self, request: AudiencePreflightRequest) -> list[AudienceCreativeVariant]:
        if not self.api_key:
            raise AudienceLiteGenerationError("VOLCENGINE_API_KEY is not configured")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": self._prompt(request)}],
            "response_format": {"type": "json_object"},
            "temperature": 0.8,
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout_seconds),
                transport=self.transport,
            ) as client:
                response = await client.post("/chat/completions", json=body)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AudienceLiteGenerationError("Doubao audience generation request failed") from exc
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AudienceLiteGenerationError("Doubao response is missing message content") from exc
        variants_raw = _json_object(content).get("variants")
        if not isinstance(variants_raw, list) or not variants_raw:
            raise AudienceLiteGenerationError("Doubao response contains no creative variants")
        variants: list[AudienceCreativeVariant] = []
        for index, item in enumerate(variants_raw[: request.variant_count]):
            if not isinstance(item, dict):
                continue
            text = " ".join(str(item.get("text") or "").split())
            tags_raw = item.get("tags", [])
            tags = [" ".join(str(tag).split())[:80] for tag in tags_raw[:32]] if isinstance(tags_raw, list) else []
            if text:
                variants.append(
                    AudienceCreativeVariant(
                        variant_id=f"v{index + 1}",
                        text=text[:12_000],
                        match_score=None,
                        tags=[tag for tag in tags if tag],
                    )
                )
        if not variants:
            raise AudienceLiteGenerationError("Doubao response contains no usable creative variants")
        return variants
