#!/usr/bin/env python3
"""Build and verify a deterministic, credential-free IP Agent source archive."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

PACKAGE_CONTRACT_VERSION = "ip-agent-source-package-v1"
MANIFEST_NAME = "IP_AGENT_PACKAGE_MANIFEST.json"
CINEMATIC_IP_SKILLS = (
    "audit-ip-continuity",
    "build-cinematic-ip-system",
    "calibrate-cinematic-ip",
    "coach-ip-screen-performance",
    "design-character-relations",
    "design-cinematography",
    "design-ip-series-bible",
    "design-light-color-texture",
    "design-production-world",
    "design-screen-sound",
    "develop-theme-premise",
    "direct-ip-visual-language",
    "direct-scene-blocking",
    "distill-screen-methods",
    "edit-screen-rhythm",
    "engineer-desire-behavior",
    "engineer-plot-information",
    "ingest-ip-evidence",
    "previsualize-screen-direction",
    "query-cinematic-library",
    "route-ip-genre-engine",
    "run-cinematic-curriculum",
    "shape-ip-emotion",
    "write-action-adventure",
    "write-comedy-satire",
    "write-crime-power-western",
    "write-documentary-reality",
    "write-horror",
    "write-ip-episode",
    "write-musical-performance",
    "write-mystery-thriller",
    "write-romance-family-growth",
    "write-scenes-dialogue",
    "write-scifi-fantasy-animation",
    "write-war-history-epic",
)
REQUIRED_PACKAGE_PATHS = (
    "IP_AGENT.md",
    "Install.md",
    "LICENSE",
    "Makefile",
    "backend/pyproject.toml",
    "backend/uv.lock",
    "frontend/package.json",
    "frontend/pnpm-lock.yaml",
    "frontend/pnpm-workspace.yaml",
    "product/defaults/USER.md",
    "product/defaults/agents/ip-agent/SOUL.md",
    "product/defaults/agents/ip-agent/config.yaml",
    "product/cinematic-ip/matrix.yaml",
    "product/cinematic-ip/PROVENANCE.md",
    "product/cinematic-ip/research-source-registry.md",
    "product/cinematic-ip/source_manifest.json",
    "product/skill-lab/policy.yaml",
    "product/skill-lab/vendor/skillhone/SKILL.md",
    "product/skill-lab/vendor/skillhone-evaluation/SKILL.md",
    "product/skill-lab/vendor/skillhone-optimization/SKILL.md",
    "product/volcengine/capabilities.yaml",
    "product/video-renderers/package.json",
    "product/video-renderers/package-lock.json",
    "product/video-renderers/version-policy.json",
    "product/video-renderers/verify-pins.mjs",
    "product/video-renderers/prepare-hyperframes.mjs",
    "product/video-renderers/render-remotion.mjs",
    "product/video-renderers/remotion/index.ts",
    "product/video-renderers/remotion/root.tsx",
    "product/video-renderers/remotion/scene.tsx",
    "product/video-renderers/THIRD_PARTY_LICENSES.md",
    "product/video-renderers/SECURITY_NOTES.md",
    "scripts/doctor.py",
    "scripts/clean_install_ip_agent.py",
    "scripts/init_ip_agent.py",
    "scripts/install_dev_hooks.py",
    "scripts/install_ffmpeg_toolchain.py",
    "scripts/install_go_toolchain.py",
    "scripts/install_video_renderers.py",
    "scripts/mediakit_source.py",
    "scripts/minecontext_source.py",
    "scripts/package_ip_agent.py",
    "scripts/personal_ip_video_e2e.py",
    "scripts/ui_tars_operator.py",
    "backend/packages/harness/deerflow/community/ui_tars/source.py",
    "backend/packages/harness/deerflow/personal_ip/video_acceptance.py",
    "product/research/ip-agent/README.md",
    "product/research/ip-agent/python/audience_provider.py",
    "product/research/ip-agent/python/hllm_creator.py",
    "product/research/ip-agent/python/video_method_distillation.py",
    "product/research/ip-agent/python/video_skill_compiler.py",
    "skills/public/volcengine-stack/SKILL.md",
    "skills/public/volcengine-stack/scripts/run_media_executor.py",
    "skills/public/ip-strategy-director/SKILL.md",
    "skills/public/ip-strategy-director/references/strategy-judgment.md",
    "skills/public/ip-strategy-director/references/benchmark-and-launch.md",
    "skills/public/ip-content-calibration/SKILL.md",
    "skills/public/ip-content-calibration/references/editorial-rubric.md",
    "skills/public/ip-content-calibration/references/learning-policy.md",
    "skills/public/video-pattern-learning/SKILL.md",
    "skills/public/video-method-distillation/SKILL.md",
    "skills/public/video-method-distillation/agents/openai.yaml",
    "skills/public/video-method-distillation/references/method-contract.md",
    *(f"skills/public/{name}/SKILL.md" for name in CINEMATIC_IP_SKILLS),
    "skills/public/query-cinematic-library/assets/cinema_library.sqlite",
    "skills/public/query-cinematic-library/scripts/query_library.py",
    "skills/public/run-cinematic-curriculum/references/curriculum.json",
    "skills/public/run-cinematic-curriculum/scripts/curriculum_cli.py",
    "skills/public/engineer-desire-behavior/scripts/validate_desire_ledger.py",
    "skills/public/reference-media-analysis/SKILL.md",
    "skills/public/reference-media-analysis/EVAL.md",
    "skills/public/precise-video-description/SKILL.md",
    "skills/public/precise-video-description/EVAL.md",
    "skills/public/cinematic-shot-direction/SKILL.md",
    "skills/public/cinematic-shot-direction/EVAL.md",
    "skills/public/visual-style-direction/SKILL.md",
    "skills/public/visual-style-direction/EVAL.md",
    "skills/public/character-design-continuity/SKILL.md",
    "skills/public/character-design-continuity/EVAL.md",
    "skills/public/production-design-direction/SKILL.md",
    "skills/public/production-design-direction/EVAL.md",
    "skills/public/lighting-direction/SKILL.md",
    "skills/public/lighting-direction/EVAL.md",
    "skills/public/performance-direction/SKILL.md",
    "skills/public/performance-direction/EVAL.md",
    "skills/public/asset-continuity-management/SKILL.md",
    "skills/public/asset-continuity-management/EVAL.md",
    "skills/public/dialogue-editing-adr/SKILL.md",
    "skills/public/dialogue-editing-adr/EVAL.md",
    "skills/public/sound-design-foley/SKILL.md",
    "skills/public/sound-design-foley/EVAL.md",
    "skills/public/music-supervision-scoring/SKILL.md",
    "skills/public/music-supervision-scoring/EVAL.md",
    "skills/public/captions-media-accessibility/SKILL.md",
    "skills/public/captions-media-accessibility/EVAL.md",
    "skills/public/captions-media-accessibility/scripts/validate_captions.py",
    "skills/public/color-grading-finishing/SKILL.md",
    "skills/public/color-grading-finishing/EVAL.md",
    "skills/public/brand-launch-film-production/SKILL.md",
    "skills/public/brand-launch-film-production/EVAL.md",
    "skills/public/product-ad-production/SKILL.md",
    "skills/public/product-ad-production/EVAL.md",
    "skills/public/ugc-ad-production/SKILL.md",
    "skills/public/ugc-ad-production/EVAL.md",
    "skills/public/talking-head-podcast-recut/SKILL.md",
    "skills/public/talking-head-podcast-recut/EVAL.md",
    "THIRD_PARTY_SKILLS.md",
    "licenses/generative-media-skills-MIT.txt",
    "licenses/cangjie-skill-MIT.txt",
    "licenses/tencent-skillhone-MIT.txt",
    "third_party/bytedance/HLLM/VENDORED_VERSION.json",
    "third_party/bytedance/UI-TARS-desktop/VENDORED_VERSION.json",
    "third_party/bytedance/UI-TARS-desktop/LICENSE",
    "third_party/bytedance/UI-TARS-desktop/packages/ui-tars/sdk/src/GUIAgent.ts",
    "third_party/bytedance/UI-TARS-desktop/packages/ui-tars/action-parser/src/actionParser.ts",
    "third_party/bytedance/UI-TARS-desktop/packages/ui-tars/operators/nut-js/src/index.ts",
    "third_party/volcengine/mediakit-cli/go.mod",
    "third_party/volcengine/MineContext/VENDORED_VERSION.json",
    "third_party/volcengine/MineContext/LICENSE",
    "third_party/volcengine/MineContext/NOTICE",
    "third_party/volcengine/MineContext/README.md",
    "third_party/volcengine/MineContext/UPSTREAM_FILES.sha256",
    "third_party/volcengine/MineContext/pyproject.toml",
    "third_party/volcengine/MineContext/opencontext/cli.py",
    "third_party/volcengine/MineContext/opencontext/server/context_operations.py",
    "third_party/volcengine/MineContext/config/config.yaml",
)
FORBIDDEN_PARTS = {
    ".deer-flow",
    ".env",
    ".git",
    ".playwright-mcp",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
    "__pycache__",
}
RUNTIME_ROOT_FILES = {
    ".env",
    "config.yaml",
    "config.yml",
    "configure.yml",
    "extensions_config.json",
    "mcp_config.json",
}
SOURCE_CONFIG_PATHS = {
    "product/defaults/agents/ip-agent/config.yaml",
    "third_party/volcengine/MineContext/config/config.yaml",
}


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _tracked_files(root: Path) -> list[tuple[str, int]]:
    raw = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout
    result: list[tuple[str, int]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode_text, _object_id, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise RuntimeError(
                "source package cannot be built with unresolved index stages"
            )
        relative = os.fsdecode(raw_path)
        if mode_text not in {"100644", "100755"}:
            raise RuntimeError(f"unsupported tracked file mode {mode_text}: {relative}")
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"tracked source file is missing: {relative}")
        result.append((relative, 0o755 if mode_text == "100755" else 0o644))
    return sorted(result)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_archive_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RuntimeError(f"unsafe archive path: {value}")
    return path


def _assert_credential_free_path(relative: str) -> None:
    path = _safe_archive_path(relative)
    if any(part in FORBIDDEN_PARTS for part in path.parts):
        raise RuntimeError(
            f"forbidden local/runtime path in source package: {relative}"
        )
    if path.name.startswith(".env.") and path.name != ".env.example":
        raise RuntimeError(
            f"forbidden local/runtime path in source package: {relative}"
        )
    if len(path.parts) == 1 and path.name in RUNTIME_ROOT_FILES:
        raise RuntimeError(f"runtime config must not enter source package: {relative}")
    if path.name == "config.yaml" and str(path) not in SOURCE_CONFIG_PATHS:
        raise RuntimeError(f"runtime config must not enter source package: {relative}")


def _manifest(
    *,
    commit: str,
    commit_timestamp: int,
    prefix: str,
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    created_at = datetime.fromtimestamp(commit_timestamp, tz=UTC).isoformat()
    return {
        "contract_version": PACKAGE_CONTRACT_VERSION,
        "package_root": prefix,
        "source_commit": commit,
        "created_at": created_at,
        "file_count": len(files),
        "files": files,
        "required_paths": list(REQUIRED_PACKAGE_PATHS),
        "install": ["make config", "make ip-init", "make install", "make doctor"],
        "clean_install_acceptance": ["python3 scripts/clean_install_ip_agent.py"],
        "optional_media_install": ["make volcengine-install", "make volcengine-doctor"],
        "optional_video_renderers_install": [
            "make video-renderers-install",
            "make video-renderers-verify",
        ],
        "optional_ui_tars_install": ["make ui-tars-install", "make ui-tars-doctor"],
        "bundled_local_context": {
            "installed_by": "make install",
            "verify": "make minecontext-doctor",
        },
    }


def build_source_package(
    root: Path, output: Path, *, allow_dirty: bool = False
) -> Path:
    root = root.resolve()
    output = output.resolve()
    if not allow_dirty:
        dirty = _git(root, "status", "--porcelain", "--untracked-files=no")
        if dirty:
            raise RuntimeError(
                "tracked worktree changes exist; commit them before building a release package"
            )
    commit = _git(root, "rev-parse", "HEAD")
    short_commit = commit[:12]
    commit_timestamp = int(_git(root, "show", "-s", "--format=%ct", "HEAD"))
    prefix = f"ip-agent-source-{short_commit}"
    tracked = _tracked_files(root)
    required_missing = sorted(
        set(REQUIRED_PACKAGE_PATHS) - {relative for relative, _mode in tracked}
    )
    if required_missing:
        raise RuntimeError(
            f"required package paths are not tracked: {', '.join(required_missing)}"
        )

    file_entries: list[dict[str, Any]] = []
    payloads: list[tuple[str, int, bytes]] = []
    for relative, mode in tracked:
        _assert_credential_free_path(relative)
        data = (root / relative).read_bytes()
        payloads.append((relative, mode, data))
        file_entries.append(
            {
                "path": relative,
                "mode": f"{mode:04o}",
                "size_bytes": len(data),
                "sha256": _sha256(data),
            }
        )
    manifest = _manifest(
        commit=commit,
        commit_timestamp=commit_timestamp,
        prefix=prefix,
        files=file_entries,
    )
    manifest_data = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        with temporary.open("wb") as raw_output:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw_output, mtime=commit_timestamp
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
                ) as archive:
                    for relative, mode, data in payloads:
                        info = tarfile.TarInfo(f"{prefix}/{relative}")
                        info.size = len(data)
                        info.mode = mode
                        info.mtime = commit_timestamp
                        info.uid = 0
                        info.gid = 0
                        info.uname = "root"
                        info.gname = "root"
                        archive.addfile(info, io.BytesIO(data))
                    info = tarfile.TarInfo(f"{prefix}/{MANIFEST_NAME}")
                    info.size = len(manifest_data)
                    info.mode = 0o644
                    info.mtime = commit_timestamp
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    archive.addfile(info, io.BytesIO(manifest_data))
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    digest = _sha256(output.read_bytes())
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="utf-8"
    )
    return output


def verify_source_package(archive_path: Path) -> dict[str, Any]:
    archive_path = archive_path.resolve()
    seen_names: set[str] = set()
    with tarfile.open(archive_path, mode="r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            path = _safe_archive_path(member.name)
            if member.name in seen_names:
                raise RuntimeError(f"duplicate archive member: {member.name}")
            seen_names.add(member.name)
            if not member.isfile():
                raise RuntimeError(
                    f"source package contains a non-regular member: {member.name}"
                )
            if len(path.parts) < 2:
                raise RuntimeError(
                    f"source package member is outside its package root: {member.name}"
                )
        manifest_members = [
            member
            for member in members
            if PurePosixPath(member.name).name == MANIFEST_NAME
        ]
        if len(manifest_members) != 1:
            raise RuntimeError(
                "source package must contain exactly one package manifest"
            )
        manifest_file = archive.extractfile(manifest_members[0])
        if manifest_file is None:
            raise RuntimeError("package manifest cannot be read")
        manifest = json.loads(manifest_file.read())
        if manifest.get("contract_version") != PACKAGE_CONTRACT_VERSION:
            raise RuntimeError("unsupported IP Agent source package contract")
        prefix = str(manifest.get("package_root") or "")
        if not prefix:
            raise RuntimeError("package manifest has no package_root")
        expected: dict[str, dict[str, Any]] = {}
        for item in manifest.get("files", []):
            relative = str(item.get("path") or "")
            _assert_credential_free_path(relative)
            if relative in expected:
                raise RuntimeError(f"duplicate manifest file: {relative}")
            expected[relative] = item
        required_missing = sorted(set(REQUIRED_PACKAGE_PATHS) - set(expected))
        if required_missing:
            raise RuntimeError(
                f"source package is incomplete: {', '.join(required_missing)}"
            )
        actual_names = {
            member.name
            for member in members
            if member.name != f"{prefix}/{MANIFEST_NAME}"
        }
        expected_names = {f"{prefix}/{relative}" for relative in expected}
        if actual_names != expected_names:
            raise RuntimeError(
                "archive members do not match the signed package manifest"
            )
        for relative, item in expected.items():
            member = archive.getmember(f"{prefix}/{relative}")
            fileobj = archive.extractfile(member)
            if fileobj is None:
                raise RuntimeError(f"package source cannot be read: {relative}")
            data = fileobj.read()
            if len(data) != item.get("size_bytes") or _sha256(data) != item.get(
                "sha256"
            ):
                raise RuntimeError(f"package checksum mismatch: {relative}")
            if f"{member.mode & 0o777:04o}" != item.get("mode"):
                raise RuntimeError(f"package mode mismatch: {relative}")
        if int(manifest.get("file_count", -1)) != len(expected):
            raise RuntimeError("package file_count does not match its manifest")
    return manifest


def smoke_test_source_package(archive_path: Path) -> None:
    manifest = verify_source_package(archive_path)
    prefix = manifest["package_root"]
    with tempfile.TemporaryDirectory(prefix="ip-agent-package-smoke-") as temporary:
        target = Path(temporary)
        with tarfile.open(archive_path, mode="r:gz") as archive:
            archive.extractall(target, filter="data")
        root = target / prefix
        state_dir = target / "state"
        subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "init_ip_agent.py"),
                "--state-dir",
                str(state_dir),
                "--user-id",
                "package-smoke",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        required_installed = (
            state_dir / "USER.md",
            state_dir / "users" / "package-smoke" / "agents" / "ip-agent" / "SOUL.md",
            state_dir
            / "users"
            / "package-smoke"
            / "agents"
            / "ip-agent"
            / "config.yaml",
        )
        if not all(path.is_file() for path in required_installed):
            raise RuntimeError(
                "extracted package could not install the default IP Agent profile"
            )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "compileall",
                "-q",
                str(root / "scripts"),
                str(
                    root
                    / "backend"
                    / "packages"
                    / "harness"
                    / "deerflow"
                    / "personal_ip"
                ),
                str(
                    root
                    / "backend"
                    / "packages"
                    / "harness"
                    / "deerflow"
                    / "community"
                    / "ui_tars"
                ),
                str(root / "skills" / "public" / "volcengine-stack" / "scripts"),
            ],
            cwd=root,
            check=True,
        )
        subprocess.run(
            [sys.executable, str(root / "scripts" / "minecontext_source.py"), "verify"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )


def _default_output(root: Path) -> Path:
    short_commit = _git(root, "rev-parse", "--short=12", "HEAD")
    return root / "dist" / f"ip-agent-source-{short_commit}.tar.gz"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--output", type=Path)
    build_parser.add_argument("--allow-dirty", action="store_true")
    build_parser.add_argument("--smoke", action="store_true")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("archive", type=Path)
    verify_parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "build":
            output = args.output or _default_output(root)
            archive = build_source_package(root, output, allow_dirty=args.allow_dirty)
            manifest = verify_source_package(archive)
            if args.smoke:
                smoke_test_source_package(archive)
            print(f"IP Agent source package: {archive}")
            print(f"  commit: {manifest['source_commit']}")
            print(f"  files: {manifest['file_count']}")
            print(f"  sha256: {archive.with_suffix(archive.suffix + '.sha256')}")
        else:
            manifest = verify_source_package(args.archive)
            if args.smoke:
                smoke_test_source_package(args.archive)
            print(f"IP Agent source package verified: {args.archive.resolve()}")
            print(f"  commit: {manifest['source_commit']}")
            print(f"  files: {manifest['file_count']}")
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        tarfile.TarError,
        json.JSONDecodeError,
    ) as exc:
        print(f"IP Agent package command failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
