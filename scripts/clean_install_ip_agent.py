#!/usr/bin/env python3
"""Validate an IP Agent source archive in a credential-free clean room."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.package_ip_agent import (  # noqa: E402
    FORBIDDEN_PARTS,
    MANIFEST_NAME,
    verify_source_package,
)

ACCEPTANCE_CONTRACT_VERSION = "ip-agent-clean-install-v1"
DEFAULT_STEP_TIMEOUT_SECONDS = 300
DEFAULT_INSTALL_TIMEOUT_SECONDS = 1200
DEFAULT_FRONTEND_TIMEOUT_SECONDS = 1800
SAFE_ENVIRONMENT = {
    "CI": "1",
    "GIT_CONFIG_NOSYSTEM": "1",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "NEXT_TELEMETRY_DISABLED": "1",
    "NO_COLOR": "1",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
}
RUNTIME_ROOT_FILES = {
    ".env",
    "config.yaml",
    "config.yml",
    "configure.yml",
    "extensions_config.json",
    "mcp_config.json",
}


@dataclass(frozen=True)
class Tooling:
    python: str
    git: str
    make: str
    node: str
    uv: str
    pnpm_command: tuple[str, ...]

    @property
    def executable_paths(self) -> tuple[str, ...]:
        return (
            self.python,
            self.git,
            self.make,
            self.node,
            self.uv,
            self.pnpm_command[0],
        )


@dataclass(frozen=True)
class StageSpec:
    name: str
    display_command: str
    command: tuple[str, ...]
    cwd: Path
    timeout_seconds: int
    diagnostic_only: bool = False
    max_attempts: int = 1
    retry_categories: tuple[str, ...] = ()


@dataclass
class StageResult:
    name: str
    command: str
    status: str
    returncode: int | None
    duration_seconds: float
    diagnostic_category: str | None = None
    diagnostic: str | None = None


class AcceptanceFailure(RuntimeError):
    def __init__(self, result: StageResult):
        super().__init__(result.diagnostic or f"stage failed: {result.name}")
        self.result = result


class SystemDependencyError(RuntimeError):
    """A required host executable is unavailable before isolation starts."""


def _which(name: str) -> str | None:
    resolved = shutil.which(name)
    return str(Path(resolved).resolve()) if resolved else None


def resolve_tooling() -> Tooling:
    tools = {
        "git": _which("git"),
        "make": _which("make"),
        "node": _which("node"),
        "uv": _which("uv"),
    }
    missing = sorted(name for name, value in tools.items() if value is None)
    pnpm = _which("pnpm") or _which("pnpm.cmd")
    corepack = _which("corepack") or _which("corepack.cmd")
    if pnpm:
        pnpm_command = (pnpm,)
    elif corepack:
        pnpm_command = (corepack, "pnpm")
    else:
        missing.append("pnpm (or corepack)")
        pnpm_command = ()
    if missing:
        raise SystemDependencyError("missing required system tools: " + ", ".join(missing) + ". Install Node.js 22+, pnpm/Corepack, uv, Git and Make, then retry.")
    return Tooling(
        python=str(Path(sys.executable).resolve()),
        git=tools["git"] or "",
        make=tools["make"] or "",
        node=tools["node"] or "",
        uv=tools["uv"] or "",
        pnpm_command=pnpm_command,
    )


def build_clean_environment(workspace: Path, executable_paths: tuple[str, ...]) -> dict[str, str]:
    home = workspace / "home"
    cache = workspace / "cache"
    temporary = workspace / "tmp"
    for directory in (home, cache, temporary):
        directory.mkdir(parents=True, exist_ok=True)

    path_entries: list[str] = []
    for executable in executable_paths:
        parent = str(Path(executable).resolve().parent)
        if parent not in path_entries:
            path_entries.append(parent)
    for default in os.defpath.split(os.pathsep):
        if default and default not in path_entries:
            path_entries.append(default)

    environment = dict(SAFE_ENVIRONMENT)
    environment.update(
        {
            "COREPACK_HOME": str(cache / "corepack"),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "HOME": str(home),
            "NPM_CONFIG_CACHE": str(cache / "npm"),
            "NPM_CONFIG_USERCONFIG": str(home / ".npmrc"),
            "PATH": os.pathsep.join(path_entries),
            "PNPM_HOME": str(cache / "pnpm-home"),
            "PNPM_STORE_DIR": str(cache / "pnpm-store"),
            "TMPDIR": str(temporary),
            "UV_CACHE_DIR": str(cache / "uv"),
            "XDG_CACHE_HOME": str(cache),
            "XDG_CONFIG_HOME": str(workspace / "config-home"),
        }
    )
    return environment


def _tail(output: str, *, lines: int = 80) -> str:
    return "\n".join(output.splitlines()[-lines:])


def classify_failure(stage: str, output: str, *, timed_out: bool) -> tuple[str, str]:
    lowered = output.lower()
    if timed_out:
        if stage == "dependency_install":
            return (
                "network_or_source_build_timeout",
                "Dependency installation exceeded its timeout. Check PyPI/npm access; if the last package entered a source build, install its documented compiler toolchain or use a supported wheel platform.",
            )
        return "timeout", f"{stage} exceeded its configured timeout"
    if any(
        marker in lowered
        for marker in (
            "could not resolve host",
            "connection reset",
            "connection timed out",
            "econnreset",
            "enotfound",
            "network is unreachable",
            "operation was aborted due to timeout",
            "tls handshake",
        )
    ):
        return (
            "network",
            "A package registry or download endpoint was unreachable; verify DNS, TLS trust and outbound network access, then rerun the same stage.",
        )
    if any(
        marker in lowered
        for marker in (
            "cannot connect to the docker daemon",
            "docker daemon is not running",
        )
    ):
        return (
            "docker",
            "Docker is installed but its daemon is unreachable; start Docker and confirm `docker info` succeeds.",
        )
    if any(marker in lowered for marker in ("permission denied", "operation not permitted", "eacces")):
        return (
            "permission",
            "The clean room lacks permission for the reported path or executable; fix that exact ownership/permission without using a broad recursive chmod.",
        )
    if "doesn't have a source distribution or wheel for the current platform" in lowered:
        return (
            "python_abi_compatibility",
            "The selected Python ABI is unsupported by a locked dependency. Confirm the packaged .python-version is honored, or update the dependency/platform constraint before retrying.",
        )
    if any(
        marker in lowered
        for marker in (
            "command not found",
            "no such file or directory",
            "requires node",
            "not found (version",
        )
    ):
        return (
            "system_dependency",
            "A required executable or compatible system version is missing; install the named prerequisite and rerun.",
        )
    if stage == "doctor":
        return (
            "configuration",
            "Doctor completed with diagnostics, which is expected before customer credentials and optional system services are configured.",
        )
    return (
        "command_failure",
        f"{stage} returned a non-zero exit status; inspect the bounded output above and rerun the displayed command.",
    )


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
    else:
        process.kill()


def run_stage(spec: StageSpec, environment: dict[str, str]) -> StageResult:
    print(f"[{spec.name}] {spec.display_command}", flush=True)
    started = time.monotonic()
    for attempt in range(1, spec.max_attempts + 1):
        process = subprocess.Popen(
            list(spec.command),
            cwd=spec.cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=os.name == "posix",
        )
        timed_out = False
        try:
            output, _ = process.communicate(timeout=spec.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _stop_process(process)
            output, _ = process.communicate()
        except KeyboardInterrupt:
            _stop_process(process)
            process.communicate()
            raise
        duration = round(time.monotonic() - started, 3)
        if process.returncode == 0:
            result = StageResult(
                name=spec.name,
                command=spec.display_command,
                status="passed",
                returncode=0,
                duration_seconds=duration,
            )
            print(f"[{spec.name}] passed in {duration:.1f}s", flush=True)
            return result

        category, diagnostic = classify_failure(spec.name, output, timed_out=timed_out)
        if attempt < spec.max_attempts and category in spec.retry_categories:
            print(_tail(output), flush=True)
            print(
                f"[{spec.name}] {category}; retrying inside the same isolated cache ({attempt + 1}/{spec.max_attempts})",
                flush=True,
            )
            continue

        status = "diagnostic" if spec.diagnostic_only and not timed_out else "failed"
        result = StageResult(
            name=spec.name,
            command=spec.display_command,
            status=status,
            returncode=process.returncode,
            duration_seconds=duration,
            diagnostic_category=category,
            diagnostic=diagnostic,
        )
        print(_tail(output), flush=True)
        print(f"[{spec.name}] {status}: {diagnostic}", flush=True)
        if status == "failed":
            raise AcceptanceFailure(result)
        return result
    raise AssertionError("stage attempt loop exited unexpectedly")


def _assert_pristine_source_tree(root: Path) -> None:
    forbidden: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            forbidden.append(relative.as_posix())
            continue
        if path.is_file() and path.name.startswith(".env.") and path.name != ".env.example":
            forbidden.append(relative.as_posix())
    for filename in RUNTIME_ROOT_FILES:
        if (root / filename).exists():
            forbidden.append(filename)
    if forbidden:
        raise RuntimeError("extracted source archive contains forbidden local/runtime data: " + ", ".join(sorted(set(forbidden))[:20]))


def _extract_archive(archive_path: Path, target: Path, package_root: str) -> Path:
    target.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive_path, mode="r:gz") as archive:
        archive.extractall(target, filter="data")
    root = target / package_root
    if not root.is_dir():
        raise RuntimeError(f"archive package root was not extracted: {package_root}")
    _assert_pristine_source_tree(root)
    return root


def _backend_probe(database_path: Path) -> str:
    url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    return f"""
import asyncio
from sqlalchemy import text
from app.gateway.app import app as gateway_app
from deerflow.persistence.engine import close_engine, get_engine, init_engine

async def probe():
    assert gateway_app is not None
    await init_engine(backend="sqlite", url={url!r}, sqlite_dir={str(database_path.parent)!r})
    engine = get_engine()
    assert engine is not None
    async with engine.connect() as connection:
        version = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        assert version
    await close_engine()
    await init_engine(backend="sqlite", url={url!r}, sqlite_dir={str(database_path.parent)!r})
    await close_engine()

asyncio.run(probe())
print("backend import and repeatable SQLite migration passed")
"""


def acceptance_stage_specs(
    extracted_root: Path,
    tooling: Tooling,
    *,
    step_timeout: int,
    install_timeout: int,
    frontend_timeout: int,
) -> list[StageSpec]:
    pnpm_make_value = " ".join(
        (
            *tooling.pnpm_command,
            "--network-concurrency=4",
            "--fetch-timeout=300000",
            "--fetch-retries=5",
        )
    )
    database_path = extracted_root / ".deer-flow" / "clean-install" / "acceptance.db"
    return [
        StageSpec(
            "config_bootstrap",
            "make config",
            (tooling.make, "config"),
            extracted_root,
            step_timeout,
        ),
        StageSpec(
            "ip_init",
            "make ip-init",
            (tooling.make, "ip-init"),
            extracted_root,
            step_timeout,
        ),
        StageSpec(
            "dependency_install",
            "make install",
            (tooling.make, f"PNPM={pnpm_make_value}", "install"),
            extracted_root,
            install_timeout,
            max_attempts=2,
            retry_categories=("network", "network_or_source_build_timeout"),
        ),
        StageSpec(
            "doctor",
            "make doctor",
            (tooling.make, "doctor"),
            extracted_root,
            step_timeout,
            diagnostic_only=True,
        ),
        StageSpec(
            "backend_import_migration",
            "cd backend && uv run python <clean-install backend probe>",
            (tooling.uv, "run", "python", "-c", _backend_probe(database_path)),
            extracted_root / "backend",
            step_timeout,
        ),
        StageSpec(
            "frontend_build",
            "cd frontend && pnpm build",
            (*tooling.pnpm_command, "build"),
            extracted_root / "frontend",
            frontend_timeout,
        ),
    ]


def _post_install_assertions(root: Path) -> None:
    expected = (
        root / "backend" / ".venv",
        root / "frontend" / "node_modules",
        root / ".deer-flow" / "toolchains" / "minecontext" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"),
        root / "backend" / ".deer-flow" / "USER.md",
        root / "backend" / ".deer-flow" / "users" / "default" / "agents" / "ip-agent" / "SOUL.md",
        root / "backend" / ".deer-flow" / "users" / "default" / "agents" / "ip-agent" / "config.yaml",
    )
    missing = [str(path.relative_to(root)) for path in expected if not path.exists()]
    if missing:
        raise RuntimeError(f"clean install did not create required runtime paths: {', '.join(missing)}")


def _archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _create_workspace(requested: Path | None) -> tuple[Path, bool]:
    if requested is None:
        return Path(tempfile.mkdtemp(prefix="ip-agent-clean-install-")), True
    workspace = requested.resolve()
    if workspace.exists():
        raise RuntimeError(f"clean-install workspace must not already exist: {workspace}")
    workspace.mkdir(parents=True)
    return workspace, False


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def run_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    workspace, auto_workspace = _create_workspace(args.workspace)
    report: dict[str, Any] = {
        "contract_version": ACCEPTANCE_CONTRACT_VERSION,
        "status": "running",
        "isolation": {
            "mode": "temporary_directory",
            "credential_environment": "allowlist_only",
            "fresh_home": True,
            "fresh_dependency_caches": True,
        },
        "environment": {
            "machine": platform.machine(),
            "platform": platform.system(),
            "python": platform.python_version(),
            "docker": "available" if _which("docker") else "not_installed_not_required",
        },
        "stages": [],
    }
    try:
        tooling = resolve_tooling()
        environment = build_clean_environment(workspace, tooling.executable_paths)
        archive_path = args.archive.resolve() if args.archive else workspace / "archive" / "ip-agent-source.tar.gz"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        if args.archive:
            package_command = (
                tooling.python,
                str(ROOT / "scripts" / "package_ip_agent.py"),
                "verify",
                str(archive_path),
                "--smoke",
            )
            display = "python3 scripts/package_ip_agent.py verify <archive> --smoke"
        else:
            package_args = [
                tooling.python,
                str(ROOT / "scripts" / "package_ip_agent.py"),
                "build",
                "--output",
                str(archive_path),
                "--smoke",
            ]
            if args.allow_dirty:
                package_args.append("--allow-dirty")
            package_command = tuple(package_args)
            display = "python3 scripts/package_ip_agent.py build --smoke"
        package_result = run_stage(
            StageSpec(
                "source_archive",
                display,
                package_command,
                ROOT,
                args.step_timeout,
            ),
            environment,
        )
        report["stages"].append(asdict(package_result))

        manifest = verify_source_package(archive_path)
        extracted_root = _extract_archive(
            archive_path,
            workspace / "extracted",
            str(manifest["package_root"]),
        )
        report["package"] = {
            "file_count": manifest["file_count"],
            "sha256": _archive_sha256(archive_path),
            "source_commit": manifest["source_commit"],
            "manifest": MANIFEST_NAME,
        }

        for spec in acceptance_stage_specs(
            extracted_root,
            tooling,
            step_timeout=args.step_timeout,
            install_timeout=args.install_timeout,
            frontend_timeout=args.frontend_timeout,
        ):
            result = run_stage(spec, environment)
            report["stages"].append(asdict(result))
            if spec.name == "dependency_install":
                _post_install_assertions(extracted_root)

        has_diagnostics = any(stage["status"] == "diagnostic" for stage in report["stages"])
        report["status"] = "passed_with_doctor_diagnostics" if has_diagnostics else "passed"
    except SystemDependencyError as exc:
        report["status"] = "failed"
        report["failure"] = {
            "stage": "system_preflight",
            "category": "system_dependency",
            "diagnostic": str(exc),
        }
    except KeyboardInterrupt:
        report["status"] = "failed"
        report["failure"] = {
            "stage": "interrupted",
            "category": "interrupted",
            "diagnostic": "Clean-install acceptance was interrupted; the active child process was terminated.",
        }
    except AcceptanceFailure as exc:
        if not any(stage["name"] == exc.result.name for stage in report["stages"]):
            report["stages"].append(asdict(exc.result))
        report["status"] = "failed"
        report["failure"] = {
            "stage": exc.result.name,
            "category": exc.result.diagnostic_category,
            "diagnostic": exc.result.diagnostic,
        }
    except Exception as exc:
        report["status"] = "failed"
        report["failure"] = {
            "stage": "orchestration",
            "category": "clean_install_orchestration",
            "diagnostic": str(exc),
        }
    finally:
        keep = args.keep_workspace or not auto_workspace
        if keep:
            report["workspace"] = str(workspace)
            print(f"Clean-install workspace kept at: {workspace}")
        else:
            shutil.rmtree(workspace, ignore_errors=True)
        if args.report:
            _write_report(args.report, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="verify this archive instead of building HEAD")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="development-only: package tracked working-tree changes",
    )
    parser.add_argument("--workspace", type=Path, help="new directory to use for the isolated install")
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="keep an automatically-created workspace",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="write the credential-free JSON acceptance report here",
    )
    parser.add_argument("--step-timeout", type=int, default=DEFAULT_STEP_TIMEOUT_SECONDS)
    parser.add_argument("--install-timeout", type=int, default=DEFAULT_INSTALL_TIMEOUT_SECONDS)
    parser.add_argument("--frontend-timeout", type=int, default=DEFAULT_FRONTEND_TIMEOUT_SECONDS)
    args = parser.parse_args()
    if min(args.step_timeout, args.install_timeout, args.frontend_timeout) <= 0:
        parser.error("timeouts must be positive seconds")

    report = run_acceptance(args)
    print(f"IP Agent clean-install result: {report['status']}")
    if failure := report.get("failure"):
        print(f"  stage: {failure['stage']}")
        print(f"  category: {failure['category']}")
        print(f"  diagnostic: {failure['diagnostic']}")
    return 0 if report["status"].startswith("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
