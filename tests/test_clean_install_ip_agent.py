from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.clean_install_ip_agent import (
    StageSpec,
    Tooling,
    _assert_pristine_source_tree,
    acceptance_stage_specs,
    build_clean_environment,
    classify_failure,
    run_stage,
)


def test_clean_environment_does_not_inherit_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXISTING_API_KEY", "must-not-cross-boundary")
    monkeypatch.setenv("HTTP_PROXY", "http://credential@example.invalid")

    environment = build_clean_environment(tmp_path, (sys.executable,))

    assert "EXISTING_API_KEY" not in environment
    assert "HTTP_PROXY" not in environment
    assert environment["HOME"] == str(tmp_path / "home")
    assert environment["UV_CACHE_DIR"] == str(tmp_path / "cache" / "uv")
    assert environment["PNPM_STORE_DIR"] == str(tmp_path / "cache" / "pnpm-store")
    assert environment["NEXT_TELEMETRY_DISABLED"] == "1"
    assert str(Path(sys.executable).resolve().parent) in environment["PATH"].split(os.pathsep)


def test_clean_install_stage_contract_covers_product_acceptance(tmp_path: Path) -> None:
    executable = str(Path(sys.executable).resolve())
    tooling = Tooling(
        python=executable,
        git=executable,
        make=executable,
        node=executable,
        uv=executable,
        pnpm_command=(executable, "pnpm"),
    )

    stages = acceptance_stage_specs(
        tmp_path,
        tooling,
        step_timeout=10,
        install_timeout=20,
        frontend_timeout=30,
    )

    assert [stage.name for stage in stages] == [
        "config_bootstrap",
        "ip_init",
        "dependency_install",
        "doctor",
        "backend_import_migration",
        "frontend_build",
    ]
    assert stages[3].diagnostic_only
    assert stages[2].max_attempts == 2
    assert stages[2].retry_categories == (
        "network",
        "network_or_source_build_timeout",
    )
    make_pnpm = stages[2].command[1]
    assert "--network-concurrency=4" in make_pnpm
    assert "--fetch-timeout=300000" in make_pnpm


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        ".env.local",
        "config.yaml",
        ".deer-flow/browser/profiles/default/Cookies",
        "frontend/node_modules/package/index.js",
        "backend/.venv/pyvenv.cfg",
    ],
)
def test_pristine_archive_check_rejects_runtime_data(
    tmp_path: Path,
    relative: str,
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("runtime data", encoding="utf-8")

    with pytest.raises(RuntimeError, match="forbidden"):
        _assert_pristine_source_tree(tmp_path)


def test_failure_diagnostics_distinguish_external_blockers() -> None:
    assert (
        classify_failure(
            "dependency_install",
            "Could not resolve host: pypi.org",
            timed_out=False,
        )[0]
        == "network"
    )
    assert (
        classify_failure(
            "docker_probe",
            "Cannot connect to the Docker daemon",
            timed_out=False,
        )[0]
        == "docker"
    )
    assert (
        classify_failure(
            "dependency_install",
            "building native package",
            timed_out=True,
        )[0]
        == "network_or_source_build_timeout"
    )
    assert (
        classify_failure(
            "dependency_install",
            "doesn't have a source distribution or wheel for the current platform",
            timed_out=False,
        )[0]
        == "python_abi_compatibility"
    )
    assert (
        classify_failure(
            "dependency_install",
            "The operation was aborted due to timeout",
            timed_out=False,
        )[0]
        == "network"
    )


def test_network_stage_retries_once_inside_the_clean_room(tmp_path: Path) -> None:
    counter = tmp_path / "attempts"
    program = (
        f"from pathlib import Path; import sys; p=Path({str(counter)!r}); n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n + 1)); print('operation was aborted due to timeout') if n == 0 else None; sys.exit(1 if n == 0 else 0)"
    )
    result = run_stage(
        StageSpec(
            name="dependency_install",
            display_command="fake install",
            command=(sys.executable, "-c", program),
            cwd=tmp_path,
            timeout_seconds=10,
            max_attempts=2,
            retry_categories=("network",),
        ),
        build_clean_environment(tmp_path / "environment", (sys.executable,)),
    )

    assert result.status == "passed"
    assert counter.read_text(encoding="utf-8") == "2"
