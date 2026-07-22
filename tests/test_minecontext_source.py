from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "minecontext_source.py"
    spec = importlib.util.spec_from_file_location("minecontext_source_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vendored_minecontext_source_verifies_without_installing_runtime() -> None:
    module = _module()
    root = Path(__file__).resolve().parents[1]

    manifest = module.validate_source(root)

    assert manifest["commit"] == module.MINECONTEXT_COMMIT
    assert manifest["source_mode"] == "full-upstream-source"
    assert module.runtime_python(root).parent.name == "bin"


def test_runtime_python_request_uses_supported_repository_version(tmp_path: Path) -> None:
    module = _module()
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / ".python-version").write_text("3.13\n", encoding="utf-8")

    assert module.runtime_python_request(tmp_path) == "3.13"


def test_runtime_python_request_rejects_incompatible_version(tmp_path: Path) -> None:
    module = _module()
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / ".python-version").write_text("3.14\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="supported Python 3.12 or 3.13"):
        module.runtime_python_request(tmp_path)


def test_doctor_probe_does_not_write_bytecode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    source = tmp_path / "source"
    package = source / "opencontext" / "__init__.py"
    package.parent.mkdir(parents=True)
    package.write_text("", encoding="utf-8")
    python = tmp_path / "runtime" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(module, "validate_source", lambda _root: {"commit": module.MINECONTEXT_COMMIT})
    monkeypatch.setattr(module, "runtime_python", lambda _root: python)
    monkeypatch.setattr(module, "source_dir", lambda _root: source)

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=f"{package}\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.doctor(tmp_path)

    assert calls == [[str(python), "-B", "-c", calls[0][3]]]
