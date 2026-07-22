from __future__ import annotations

import tomllib
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
HARNESS_PYPROJECT = BACKEND_ROOT / "packages" / "harness" / "pyproject.toml"
UV_LOCK = BACKEND_ROOT / "uv.lock"


def test_macos_intel_cryptography_uses_a_binary_compatible_release() -> None:
    harness = tomllib.loads(HARNESS_PYPROJECT.read_text(encoding="utf-8"))
    dependencies = harness["project"]["dependencies"]

    assert ("cryptography>=48.0.1,<49; sys_platform == 'darwin' and platform_machine == 'x86_64'") in dependencies
    assert ("cryptography>=48.0.1; sys_platform != 'darwin' or platform_machine != 'x86_64'") in dependencies

    lock = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    compatible_releases = [package for package in lock["package"] if package["name"] == "cryptography" and tuple(int(part) for part in package["version"].split(".")[:2]) < (49, 0)]

    assert compatible_releases
    assert any("macosx" in wheel["url"] and any(architecture in wheel["url"] for architecture in ("universal2", "x86_64")) for package in compatible_releases for wheel in package.get("wheels", []))
