"""Regression tests for running a checkout after its directory is moved."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_local_python_entrypoints_do_not_depend_on_console_script_shebangs():
    backend_makefile = _read("backend/Makefile")
    docker_compose = _read("docker/docker-compose.yaml")
    docker_entrypoint = _read("docker/dev-entrypoint.sh")
    dockerfile = _read("backend/Dockerfile")
    root_makefile = _read("Makefile")
    serve_script = _read("scripts/serve.sh")

    assert "uv run python -m pytest" in backend_makefile
    assert "uv run pytest" not in backend_makefile
    assert "uv run python -m uvicorn" in backend_makefile
    assert "uv run uvicorn" not in backend_makefile
    assert "uv run python -m uvicorn app.audience_lite.app:app" in root_makefile
    assert "uv run python -m uvicorn app.gateway.app:app" in serve_script
    for content in (docker_compose, docker_entrypoint, dockerfile):
        assert "uv run python -m uvicorn app.gateway.app:app" in content
        assert "uv run uvicorn" not in content
