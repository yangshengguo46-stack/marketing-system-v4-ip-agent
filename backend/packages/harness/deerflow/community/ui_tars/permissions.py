"""Read-only desktop permission diagnosis; never prompts or opens settings."""

from __future__ import annotations

import ctypes
import platform
from typing import Literal, TypedDict


class DesktopPermissionDiagnosis(TypedDict):
    platform: str
    supported: bool
    screen_recording: Literal["granted", "denied", "unknown", "not_applicable"]
    accessibility: Literal["granted", "denied", "unknown", "not_applicable"]
    detail: str


def _macos_boolean(framework: str, function: str) -> bool | None:
    try:
        library = ctypes.CDLL(framework)
        target = getattr(library, function)
        target.argtypes = []
        target.restype = ctypes.c_bool
        return bool(target())
    except (AttributeError, OSError):
        return None


def diagnose_desktop_permissions() -> DesktopPermissionDiagnosis:
    """Inspect current permissions without taking a screenshot or requesting access."""
    system = platform.system().lower()
    if system != "darwin":
        return {
            "platform": system or "unknown",
            "supported": False,
            "screen_recording": "not_applicable",
            "accessibility": "not_applicable",
            "detail": "The bundled source-only desktop backend currently supports macOS; connect mode may provide another local backend.",
        }

    screen = _macos_boolean(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics",
        "CGPreflightScreenCaptureAccess",
    )
    accessibility = _macos_boolean(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices",
        "AXIsProcessTrusted",
    )

    def state(value: bool | None) -> Literal["granted", "denied", "unknown"]:
        if value is None:
            return "unknown"
        return "granted" if value else "denied"

    return {
        "platform": "darwin",
        "supported": True,
        "screen_recording": state(screen),
        "accessibility": state(accessibility),
        "detail": "Grant Screen Recording and Accessibility to the Python executable that starts the local UI-TARS operator, then restart it.",
    }
