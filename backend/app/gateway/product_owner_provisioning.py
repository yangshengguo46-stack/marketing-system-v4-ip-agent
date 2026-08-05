"""Atomic, owner-exact installation of the operator-owned product Agent."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from deerflow.config.agents_config import AgentConfig, agent_artifact_sha256
from deerflow.config.paths import Paths, get_paths
from deerflow.config.runtime_paths import project_root as runtime_project_root

_PRODUCT_AGENT_FILES = ("config.yaml", "SOUL.md")


def _load_exact_agent_directory(
    directory: Path,
    *,
    assistant_id: str,
    label: str,
) -> AgentConfig:
    """Load only ``directory``; never use the legacy shared-agent fallback."""
    if directory.is_symlink():
        raise RuntimeError(f"{label} must not be a symbolic link")
    if not directory.is_dir():
        raise RuntimeError(f"{label} is incomplete: directory is missing")

    files = {name: directory / name for name in _PRODUCT_AGENT_FILES}
    missing = [name for name, path in files.items() if not path.is_file()]
    if missing:
        raise RuntimeError(f"{label} is incomplete: missing {', '.join(missing)}")
    linked = [name for name, path in files.items() if path.is_symlink()]
    if linked:
        raise RuntimeError(f"{label} must not contain symbolic links: {', '.join(linked)}")

    try:
        payload = yaml.safe_load(files["config.yaml"].read_text(encoding="utf-8")) or {}
        config = AgentConfig.model_validate(payload)
    except Exception as exc:
        raise RuntimeError(f"{label} has an invalid config.yaml") from exc
    if config.name != assistant_id:
        raise RuntimeError(f"{label} identity drift: name")
    return config


def _capability_mismatches(
    config: AgentConfig,
    declared_capability: Mapping[str, Any],
) -> list[str]:
    mismatches: list[str] = []
    if config.tool_allowlist != declared_capability.get("tool_allowlist"):
        mismatches.append("tool_allowlist")
    if config.skills != declared_capability.get("skills"):
        mismatches.append("skills")
    if config.memory_enabled is not declared_capability.get("memory_enabled"):
        mismatches.append("memory_enabled")
    return mismatches


def _validate_capability(
    config: AgentConfig,
    declared_capability: Mapping[str, Any],
    *,
    label: str,
) -> None:
    mismatches = _capability_mismatches(config, declared_capability)
    if mismatches:
        raise RuntimeError(f"{label} capability drift: {', '.join(mismatches)}")


def _validate_artifact(
    directory: Path,
    declared_artifact_sha256: str,
    *,
    label: str,
) -> None:
    actual = agent_artifact_sha256(directory)
    if actual != declared_artifact_sha256:
        raise RuntimeError(f"{label} artifact drift")


def _atomic_install(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.parent.chmod(0o700)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}.install-",
            dir=target.parent,
        )
    )
    temporary.chmod(0o700)
    try:
        for filename in _PRODUCT_AGENT_FILES:
            destination = temporary / filename
            shutil.copyfile(source / filename, destination)
            destination.chmod(0o600)
        try:
            temporary.rename(target)
        except OSError:
            # Another request completed the same atomic install first.  The
            # exact errno differs by platform (EEXIST on Linux, ENOTEMPTY on
            # macOS).  Suppress only when a real, non-symlink directory won;
            # the caller validates its complete contents below.
            if target.is_symlink() or not target.is_dir():
                raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def ensure_product_owner_agent(
    *,
    owner_user_id: str,
    assistant_id: str,
    declared_capability: Mapping[str, Any],
    declared_artifact_sha256: str,
    paths: Paths | None = None,
    project_root: Path | None = None,
) -> AgentConfig:
    """Return one exact Owner Agent, installing it once when wholly absent.

    Existing Owner state is never repaired or overwritten automatically.  A
    malformed, partial, symlinked or drifted directory fails closed so an
    operator can inspect it.  Legacy shared agents are deliberately ignored.
    """
    runtime_paths = paths or get_paths()
    target = runtime_paths.user_agent_dir(owner_user_id, assistant_id)
    if target.is_symlink():
        raise RuntimeError("Owner Product Agent must not be a symbolic link")
    if target.exists():
        owner_config = _load_exact_agent_directory(
            target,
            assistant_id=assistant_id,
            label="Owner Product Agent",
        )
        _validate_capability(
            owner_config,
            declared_capability,
            label="Owner Product Agent",
        )
        _validate_artifact(
            target,
            declared_artifact_sha256,
            label="Owner Product Agent",
        )
        return owner_config

    root = (project_root or runtime_project_root()).resolve()
    source = root / "product" / "defaults" / "agents" / assistant_id
    source_config = _load_exact_agent_directory(
        source,
        assistant_id=assistant_id,
        label="Product Agent source",
    )
    _validate_capability(
        source_config,
        declared_capability,
        label="Product Agent source",
    )
    _validate_artifact(
        source,
        declared_artifact_sha256,
        label="Product Agent source",
    )
    _atomic_install(source, target)

    owner_config = _load_exact_agent_directory(
        target,
        assistant_id=assistant_id,
        label="Owner Product Agent",
    )
    _validate_capability(
        owner_config,
        declared_capability,
        label="Owner Product Agent",
    )
    _validate_artifact(
        target,
        declared_artifact_sha256,
        label="Owner Product Agent",
    )
    return owner_config
