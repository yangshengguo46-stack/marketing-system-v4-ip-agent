#!/usr/bin/env python3
"""Build and validate the pinned AI MediaKit CLI directly from vendored source."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

MEDIAKIT_COMMIT = "279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0"
MEDIAKIT_VERSION = "0.2.0+ip-agent.279e5bb"
DEFAULT_GO_PROXY = "https://goproxy.cn,direct"


def source_dir(root: Path) -> Path:
    return root / "third_party" / "volcengine" / "mediakit-cli"


def binary_path(root: Path, *, platform_name: str | None = None) -> Path:
    platform_name = platform_name or sys.platform
    suffix = ".exe" if platform_name.startswith("win") else ""
    return root / ".deer-flow" / "bin" / f"mediakit-cli{suffix}"


def media_environment(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    paths = (
        root / ".deer-flow" / "toolchains" / "ffmpeg" / "bin",
        root / ".deer-flow" / "bin",
    )
    env["PATH"] = os.pathsep.join([*(str(path) for path in paths), env.get("PATH", "")])
    return env


def validate_source(root: Path) -> Path:
    source = source_dir(root)
    required = (
        source / "go.mod",
        source / "cmd" / "mediakit" / "main.go",
        source / "LICENSE",
    )
    missing = [path.relative_to(root) for path in required if not path.is_file()]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise RuntimeError(f"vendored MediaKit source is incomplete: {joined}")
    if (source / "mediakit").exists():
        raise RuntimeError("unexpected prebuilt MediaKit binary in the source tree")
    return source


def require_go(root: Path) -> str:
    go = shutil.which("go")
    if go is None:
        suffix = ".exe" if sys.platform.startswith("win") else ""
        local_go = root / ".deer-flow" / "toolchains" / "go" / "bin" / f"go{suffix}"
        go = str(local_go) if local_go.is_file() else None
    if go is None:
        raise RuntimeError(
            "Go 1.22+ is required to build MediaKit from source. "
            "Run `make mediakit-toolchain`, then rerun `make mediakit-build`."
        )
    return go


def go_environment() -> dict[str, str]:
    env = dict(os.environ)
    env["CGO_ENABLED"] = "0"
    env.setdefault("GOPROXY", DEFAULT_GO_PROXY)
    return env


def build(root: Path) -> Path:
    source = validate_source(root)
    go = require_go(root)
    output = binary_path(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    build_date = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ldflags = " ".join(
        (
            "-s -w",
            f"-X mediakit-cli/internal/build.Version={MEDIAKIT_VERSION}",
            f"-X mediakit-cli/internal/build.Date={build_date}",
        )
    )
    subprocess.run(
        [
            go,
            "build",
            "-trimpath",
            "-ldflags",
            ldflags,
            "-o",
            str(output),
            "./cmd/mediakit",
        ],
        cwd=source,
        env=go_environment(),
        check=True,
    )
    print(f"built {output} from MediaKit {MEDIAKIT_COMMIT}")
    return output


def test_source(root: Path) -> None:
    source = validate_source(root)
    go = require_go(root)
    subprocess.run([go, "test", "./..."], cwd=source, env=go_environment(), check=True)


def doctor(root: Path) -> None:
    validate_source(root)
    binary = binary_path(root)
    if not binary.is_file():
        raise RuntimeError(
            "MediaKit has not been built; run `make mediakit-build` first"
        )
    env = media_environment(root)
    subprocess.run([str(binary), "version"], check=True, env=env)
    subprocess.run([str(binary), "doctor"], check=True, env=env)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "test", "doctor", "path"))
    args = parser.parse_args()
    try:
        if args.command == "build":
            build(root)
        elif args.command == "test":
            test_source(root)
        elif args.command == "doctor":
            doctor(root)
        else:
            validate_source(root)
            print(binary_path(root))
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"MediaKit source command failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
