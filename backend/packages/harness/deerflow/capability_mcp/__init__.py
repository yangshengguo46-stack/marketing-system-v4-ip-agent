"""Reusable manifest, probe and exact-dispatch substrate for local MCPs."""

from .runtime import (
    CapabilityAvailability,
    CapabilityDispatcher,
    CapabilityRegistry,
    CapabilitySpec,
)

__all__ = [
    "CapabilityAvailability",
    "CapabilityDispatcher",
    "CapabilityRegistry",
    "CapabilitySpec",
]
