"""Small first-party capability runtime inspired by the Doris MCP lifecycle.

The runtime is intentionally transport-agnostic.  An MCP server registers
strict child capabilities, exposes a deterministic manifest, probes current
availability, and dispatches only an exact registered binding.  It never
discovers functions by reflection or executes a caller-supplied route.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CapabilityAvailability(BaseModel):
    status: Literal["available", "degraded", "unavailable", "unknown"]
    callable: bool
    reason_code: str = Field(min_length=1, max_length=100)
    evidence_sources: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    model_config = ConfigDict(extra="forbid")


CapabilityHandler = Callable[[BaseModel], Awaitable[BaseModel | Mapping[str, Any]]]
CapabilityProbe = Callable[[], Awaitable[CapabilityAvailability] | CapabilityAvailability]


@dataclass(frozen=True, slots=True)
class CapabilitySpec[InputModel: BaseModel, OutputModel: BaseModel]:
    domain: str
    child: str
    description: str
    input_model: type[InputModel]
    output_model: type[OutputModel]
    handler: CapabilityHandler
    probe: CapabilityProbe
    routes: tuple[str, ...]
    timeout_seconds: float
    read_only: bool = True

    @property
    def feature_id(self) -> str:
        return f"{self.domain}.{self.child}"


class CapabilityRegistry:
    """Own deterministic capability definitions and availability snapshots."""

    def __init__(self, *, name: str, semantic_manifest: Mapping[str, Any]) -> None:
        self.name = name
        self._semantic_manifest = dict(semantic_manifest)
        self._specs: dict[str, CapabilitySpec[Any, Any]] = {}

    def register(self, spec: CapabilitySpec[Any, Any]) -> None:
        if not spec.domain or not spec.child or "." in spec.domain or "." in spec.child:
            raise ValueError("capability domain and child must be non-empty atomic identifiers")
        if not spec.routes or spec.timeout_seconds <= 0:
            raise ValueError("capability requires a route and positive execution timeout")
        if spec.feature_id in self._specs:
            raise ValueError(f"duplicate capability binding: {spec.feature_id}")
        self._specs[spec.feature_id] = spec

    @property
    def manifest_version(self) -> str:
        canonical = json.dumps(self._structural_manifest(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _structural_manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "semantic_model": self._semantic_manifest,
            "capabilities": [
                {
                    "feature_id": spec.feature_id,
                    "domain": spec.domain,
                    "child": spec.child,
                    "description": spec.description,
                    "input_schema": spec.input_model.model_json_schema(),
                    "output_schema": spec.output_model.model_json_schema(),
                    "routes": list(spec.routes),
                    "timeout_seconds": spec.timeout_seconds,
                    "read_only": spec.read_only,
                }
                for spec in sorted(self._specs.values(), key=lambda item: item.feature_id)
            ],
        }

    async def manifest(self) -> dict[str, Any]:
        structural = self._structural_manifest()
        capabilities: list[dict[str, Any]] = []
        for capability in structural["capabilities"]:
            spec = self._specs[capability["feature_id"]]
            availability = await _resolve_probe(spec.probe)
            capabilities.append({**capability, "availability": availability.model_dump(mode="json")})
        return {
            "manifest_version": self.manifest_version,
            **structural,
            "capabilities": capabilities,
        }

    def exact(self, domain: str, child: str) -> CapabilitySpec[Any, Any]:
        feature_id = f"{domain}.{child}"
        try:
            return self._specs[feature_id]
        except KeyError as exc:
            raise LookupError("capability is not registered") from exc


class CapabilityDispatcher:
    """Revalidate, probe, bind and execute one exact child capability."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    async def dispatch(
        self,
        *,
        domain: str,
        child: str,
        arguments: Mapping[str, Any],
        manifest_version: str | None = None,
    ) -> BaseModel:
        if manifest_version is not None and manifest_version != self.registry.manifest_version:
            raise ValueError("capability manifest version is stale")
        spec = self.registry.exact(domain, child)
        availability = await _resolve_probe(spec.probe)
        if not availability.callable:
            raise RuntimeError(f"capability unavailable: {availability.reason_code}")
        validated_arguments = spec.input_model.model_validate(dict(arguments))
        result = await asyncio.wait_for(spec.handler(validated_arguments), timeout=spec.timeout_seconds)
        if isinstance(result, spec.output_model):
            return result
        return spec.output_model.model_validate(result)


async def _resolve_probe(probe: CapabilityProbe) -> CapabilityAvailability:
    result = probe()
    if isinstance(result, Awaitable):
        result = await result
    return CapabilityAvailability.model_validate(result)
