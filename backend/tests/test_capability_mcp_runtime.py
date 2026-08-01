from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from deerflow.capability_mcp import (
    CapabilityAvailability,
    CapabilityDispatcher,
    CapabilityRegistry,
    CapabilitySpec,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Input(_StrictModel):
    value: int


class _Output(_StrictModel):
    doubled: int


async def _handler(arguments: _Input) -> _Output:
    return _Output(doubled=arguments.value * 2)


def _available() -> CapabilityAvailability:
    return CapabilityAvailability(
        status="available",
        callable=True,
        reason_code="READY",
        evidence_sources=["test"],
    )


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry(name="test", semantic_manifest={"name": "test-semantic"})
    registry.register(
        CapabilitySpec(
            domain="math",
            child="double",
            description="Double one integer.",
            input_model=_Input,
            output_model=_Output,
            handler=_handler,
            probe=_available,
            routes=("local",),
            timeout_seconds=1,
        )
    )
    return registry


@pytest.mark.asyncio
async def test_manifest_is_deterministic_and_dispatch_requires_exact_binding() -> None:
    registry = _registry()
    first = await registry.manifest()
    second = await registry.manifest()

    assert first == second
    assert first["manifest_version"] == registry.manifest_version
    assert first["capabilities"][0]["availability"]["callable"] is True

    dispatcher = CapabilityDispatcher(registry)
    result = await dispatcher.dispatch(
        domain="math",
        child="double",
        arguments={"value": 4},
        manifest_version=registry.manifest_version,
    )
    assert result == _Output(doubled=8)

    with pytest.raises(LookupError, match="not registered"):
        await dispatcher.dispatch(domain="math", child="missing", arguments={"value": 4})


@pytest.mark.asyncio
async def test_dispatch_rejects_stale_manifest_and_unavailable_capability() -> None:
    registry = _registry()
    dispatcher = CapabilityDispatcher(registry)
    with pytest.raises(ValueError, match="stale"):
        await dispatcher.dispatch(
            domain="math",
            child="double",
            arguments={"value": 4},
            manifest_version="old",
        )

    blocked = CapabilityRegistry(name="blocked", semantic_manifest={"name": "blocked"})
    blocked.register(
        CapabilitySpec(
            domain="external",
            child="read",
            description="Blocked test capability.",
            input_model=_Input,
            output_model=_Output,
            handler=_handler,
            probe=lambda: CapabilityAvailability(
                status="unavailable",
                callable=False,
                reason_code="AUTH_REQUIRED",
            ),
            routes=("external",),
            timeout_seconds=1,
        )
    )
    with pytest.raises(RuntimeError, match="AUTH_REQUIRED"):
        await CapabilityDispatcher(blocked).dispatch(
            domain="external",
            child="read",
            arguments={"value": 1},
        )
