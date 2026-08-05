#!/usr/bin/env python3
"""Build and validate the pinned AI MediaKit CLI directly from vendored source."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

MEDIAKIT_COMMIT = "279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0"
MEDIAKIT_VERSION = "0.2.0+ip-agent.279e5bb"
DEFAULT_GO_PROXY = "https://goproxy.cn,direct"
MEDIAKIT_UPSTREAM_TREE = "e9b40b73ef691e7bbf5a38c9af4e06d699d62beb"
MEDIAKIT_SOURCE_MODE = "full-upstream-source-with-prebuilt-binary-excluded"
MEDIAKIT_MANIFEST = "VENDORED_VERSION.json"
MEDIAKIT_EXCLUDED_UPSTREAM_PATHS = ("mediakit",)
EXPECTED_MEDIAKIT_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "audio": ("probe-audio-metadata", "separate-voice"),
    "editing": (
        "add-image-to-video",
        "add-subtitle-to-video",
        "adjust-audio-speed",
        "adjust-video-speed",
        "adjust-video-volume",
        "apply-video-filter",
        "concat-audio",
        "concat-video",
        "extract-audio",
        "fade-audio",
        "fade-video-audio",
        "flip-video",
        "image-to-video",
        "mix-audio",
        "mux-audio-video",
        "trim-audio",
        "trim-video",
    ),
    "image": (
        "enhance-image",
        "erase-image",
        "evaluate-image-quality",
        "image-ocr",
        "remove-image-background",
    ),
    "shared": ("fetch-file", "query-task"),
    "video": (
        "analyze-video-highlights",
        "analyze-video-storyline",
        "asr-subtitles",
        "enhance-video",
        "enhance-video-generative",
        "erase-video-subtitle",
        "erase-video-subtitle-pro",
        "generate-highlights-microdrama",
        "generate-highlights-minigame",
        "matte-greenscreen-video",
        "matte-portrait-video",
        "probe-video-metadata",
        "segment-scenes",
        "video-ocr",
    ),
}


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_tree_fingerprint(source: Path) -> tuple[int, str]:
    """Fingerprint every retained upstream file and its relative path.

    The product-owned provenance manifest is excluded from the digest.  Any
    other added, removed, renamed or modified file changes the fingerprint.
    """

    files = sorted(
        (path for path in source.rglob("*") if path.is_file() and path.relative_to(source).as_posix() != MEDIAKIT_MANIFEST),
        key=lambda path: path.relative_to(source).as_posix(),
    )
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(source).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(path)))
        digest.update(b"\0")
    return len(files), digest.hexdigest()


def _capability_catalog_sha256(catalog: dict[str, tuple[str, ...]]) -> str:
    encoded = json.dumps(
        {domain: list(tools) for domain, tools in catalog.items()},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_capability_catalog(help_text: str) -> dict[str, tuple[str, ...]]:
    """Parse the stable domain/tool index emitted by ``--help-full``."""

    catalog: dict[str, list[str]] = {}
    domain: str | None = None
    for raw_line in help_text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            domain = line[1:-1].strip()
            catalog.setdefault(domain, [])
            continue
        if domain is not None and line.startswith("- "):
            tool = line[2:].split(maxsplit=1)[0].strip()
            if tool:
                catalog[domain].append(tool)
    return {name: tuple(tools) for name, tools in catalog.items()}


def validate_runtime_catalog(
    binary: Path,
    *,
    environment: dict[str, str] | None = None,
) -> dict[str, tuple[str, ...]]:
    result = subprocess.run(
        [str(binary), "--help-full"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        raise RuntimeError("MediaKit runtime capability discovery failed")
    catalog = parse_capability_catalog(result.stdout)
    if catalog != EXPECTED_MEDIAKIT_CAPABILITIES:
        raise RuntimeError("MediaKit runtime capability catalog drifted from the pinned contract")
    return catalog


def validate_source(root: Path) -> Path:
    source = source_dir(root)
    required = (
        source / MEDIAKIT_MANIFEST,
        source / "go.mod",
        source / "cmd" / "mediakit" / "main.go",
        source / "LICENSE",
        source / "Open Source Notice.txt",
        source / "package.json",
    )
    missing = [path.relative_to(root) for path in required if not path.is_file()]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise RuntimeError(f"vendored MediaKit source is incomplete: {joined}")
    if (source / "mediakit").exists():
        raise RuntimeError("unexpected prebuilt MediaKit binary in the source tree")
    try:
        manifest = json.loads((source / MEDIAKIT_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("vendored MediaKit provenance manifest is invalid") from exc
    expected_manifest = {
        "commit": MEDIAKIT_COMMIT,
        "upstream_tree": MEDIAKIT_UPSTREAM_TREE,
        "package_version": "0.2.0",
        "source_mode": MEDIAKIT_SOURCE_MODE,
        "excluded_upstream_paths": list(MEDIAKIT_EXCLUDED_UPSTREAM_PATHS),
        "retained_source_file_count": 119,
        "capability_count": sum(len(tools) for tools in EXPECTED_MEDIAKIT_CAPABILITIES.values()),
        "capability_catalog_sha256": _capability_catalog_sha256(EXPECTED_MEDIAKIT_CAPABILITIES),
        "declared_license": "MIT",
        "notice_license_statement": "Apache-2.0",
        "license_review_status": "upstream-conflict-open",
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            raise RuntimeError(f"vendored MediaKit {key} does not match the pinned contract")
    for manifest_key, relative in {
        "license_sha256": "LICENSE",
        "package_json_sha256": "package.json",
        "open_source_notice_sha256": "Open Source Notice.txt",
    }.items():
        if manifest.get(manifest_key) != _sha256(source / relative):
            raise RuntimeError(f"vendored MediaKit checksum mismatch: {relative}")
    file_count, tree_digest = _source_tree_fingerprint(source)
    if file_count != manifest.get("retained_source_file_count"):
        raise RuntimeError("vendored MediaKit retained source file count mismatch")
    if tree_digest != manifest.get("source_tree_sha256"):
        raise RuntimeError("vendored MediaKit source tree digest mismatch")
    return source


def require_go(root: Path) -> str:
    go = shutil.which("go")
    if go is None:
        suffix = ".exe" if sys.platform.startswith("win") else ""
        local_go = root / ".deer-flow" / "toolchains" / "go" / "bin" / f"go{suffix}"
        go = str(local_go) if local_go.is_file() else None
    if go is None:
        raise RuntimeError("Go 1.22+ is required to build MediaKit from source. Run `make mediakit-toolchain`, then rerun `make mediakit-build`.")
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
        raise RuntimeError("MediaKit has not been built; run `make mediakit-build` first")
    env = media_environment(root)
    subprocess.run([str(binary), "version"], check=True, env=env)
    validate_runtime_catalog(binary, environment=env)
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
