#!/usr/bin/env python3
"""Install the distribution's default profile and local IP Agent safely."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import shutil
from pathlib import Path

_BINDING_ACTIVE_KID = "IP_AGENT_EVIDENCE_BINDING_ACTIVE_KID"
_BINDING_KEYS_JSON = "IP_AGENT_EVIDENCE_BINDING_KEYS_JSON"
_ENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
_BINDING_KID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_B64URL_PADDED = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")


def default_state_dir(root: Path) -> Path:
    """Resolve the same runtime state directory used by the local launcher."""

    configured = os.environ.get("DEER_FLOW_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return root / "backend" / ".deer-flow"


def copy_file(source: Path, target: Path, *, force: bool) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        return f"kept existing {target}"
    shutil.copy2(source, target)
    return f"installed {target}"


def _environment_value(text: str, name: str) -> str:
    value = ""
    for line in text.splitlines():
        match = _ENV_ASSIGNMENT.match(line)
        if match is None or match.group(1) != name:
            continue
        value = match.group(2).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def _normalized_binding_keyring(
    active_kid: str,
    raw_keys: str,
) -> tuple[dict[str, str], bool] | None:
    if _BINDING_KID.fullmatch(active_kid) is None:
        return None
    try:
        parsed = json.loads(raw_keys)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict) or active_kid not in parsed:
        return None
    normalized: dict[str, str] = {}
    changed = False
    for kid, encoded in parsed.items():
        if (
            not isinstance(kid, str)
            or _BINDING_KID.fullmatch(kid) is None
            or not isinstance(encoded, str)
            or _B64URL_PADDED.fullmatch(encoded) is None
        ):
            return None
        without_padding = encoded.rstrip("=")
        try:
            decoded = base64.b64decode(
                without_padding + "=" * (-len(without_padding) % 4),
                altchars=b"-_",
                validate=True,
            )
        except (ValueError, UnicodeError):
            return None
        if len(decoded) < 32:
            return None
        normalized[kid] = without_padding
        changed = changed or without_padding != encoded
    return normalized, changed


def _write_private_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_account_binding_environment(env_path: Path) -> str:
    """Install one persistent local account-binding keyring when absent."""

    env_path = env_path.resolve()
    existing = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
    active_kid = _environment_value(existing, _BINDING_ACTIVE_KID)
    raw_keys = _environment_value(existing, _BINDING_KEYS_JSON)
    keyring = _normalized_binding_keyring(active_kid, raw_keys)
    if keyring is not None and keyring[1] is False:
        env_path.chmod(0o600)
        return f"kept existing account binding environment in {env_path}"

    if keyring is None:
        active_kid = "local-v1"
        encoded_key = (
            base64.urlsafe_b64encode(secrets.token_bytes(32))
            .decode("ascii")
            .rstrip("=")
        )
        keys = {active_kid: encoded_key}
        action = "installed"
    else:
        keys = keyring[0]
        action = "normalized"

    retained_lines: list[str] = []
    for line in existing.splitlines():
        match = _ENV_ASSIGNMENT.match(line)
        if match is not None and match.group(1) in {
            _BINDING_ACTIVE_KID,
            _BINDING_KEYS_JSON,
        }:
            continue
        retained_lines.append(line)
    if retained_lines and retained_lines[-1]:
        retained_lines.append("")
    retained_lines.extend(
        [
            f"{_BINDING_ACTIVE_KID}={active_kid}",
            f"{_BINDING_KEYS_JSON}='{json.dumps(keys, sort_keys=True, separators=(',', ':'))}'",
        ]
    )
    _write_private_text(env_path, "\n".join(retained_lines) + "\n")
    return f"{action} account binding environment in {env_path}"


def install(
    root: Path,
    state_dir: Path,
    user_id: str,
    *,
    force: bool,
    refresh_product_agent: bool = False,
) -> list[str]:
    defaults = root / "product" / "defaults"
    messages = [
        copy_file(defaults / "USER.md", state_dir / "USER.md", force=force),
        copy_file(
            defaults / "product-runtime-profile.yaml",
            state_dir / "product-runtime-profile.yaml",
            force=force or refresh_product_agent,
        ),
    ]
    source_agent = defaults / "agents" / "ip-agent"
    target_agent = state_dir / "users" / user_id / "agents" / "ip-agent"
    for filename in ("config.yaml", "SOUL.md"):
        messages.append(
            copy_file(
                source_agent / filename,
                target_agent / filename,
                force=force or refresh_product_agent,
            )
        )
    return messages


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=default_state_dir(root),
        help=(
            "DeerFlow state directory (default: DEER_FLOW_HOME or <repo>/backend/.deer-flow)"
        ),
    )
    parser.add_argument("--user-id", default="default")
    parser.add_argument(
        "--force", action="store_true", help="replace existing defaults"
    )
    parser.add_argument(
        "--refresh-product-agent",
        action="store_true",
        help="replace the product-owned ip-agent files while preserving USER.md",
    )
    args = parser.parse_args()
    print(ensure_account_binding_environment(root / ".env"))
    for message in install(
        root,
        args.state_dir.resolve(),
        args.user_id,
        force=args.force,
        refresh_product_agent=args.refresh_product_agent,
    ):
        print(message)


if __name__ == "__main__":
    main()
