"""Owner-isolated, consent-gated bridge to the vendored MineContext source.

MineContext is a local observation sidecar, never an agent brain. Only the
allowlisted, minimized evidence records produced in this module cross into
DeerFlow. Raw screenshots, file text, paths, vectors and credentials remain
outside the agent/model contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from deerflow.config.minecontext_config import MineContextConfig
from deerflow.config.paths import Paths

MINECONTEXT_UPSTREAM_COMMIT = "171c7a9ea8091e326ddcf0f10718aa1b58c83c65"
MINECONTEXT_UPSTREAM_RELATIVE_PATH = Path("third_party/volcengine/MineContext")
MINECONTEXT_EVIDENCE_SCHEMA_VERSION = "personal-ip-local-context-evidence-v1"
MINECONTEXT_CONSENT_SCHEMA_VERSION = "personal-ip-local-context-consent-v1"
MINECONTEXT_BOUNDED_SCREEN_PROFILE_VERSION = "personal-ip-explicit-bounded-screen-v2"

MineContextScope = Literal["screen", "files", "people", "projects", "work_activity"]
MineContextPurpose = Literal[
    "persona_modeling",
    "audience_modeling",
]
DEFAULT_MINECONTEXT_SCOPES: tuple[MineContextScope, ...] = (
    "screen",
    "files",
    "people",
    "projects",
    "work_activity",
)
DEFAULT_MINECONTEXT_PURPOSES: tuple[MineContextPurpose, ...] = (
    "persona_modeling",
    "audience_modeling",
)

_REQUIRED_UPSTREAM_FILES = (
    "LICENSE",
    "NOTICE",
    "README.md",
    "UPSTREAM_FILES.sha256",
    "pyproject.toml",
    "opencontext/cli.py",
    "opencontext/server/context_operations.py",
)
_CHECKSUM_PATHS = {
    "license_sha256": "LICENSE",
    "pyproject_sha256": "pyproject.toml",
    "cli_sha256": "opencontext/cli.py",
    "context_operations_sha256": "opencontext/server/context_operations.py",
}
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{4,}"),
    re.compile(r"(?i)\b(?:api[_ -]?key|password|passwd|secret|token)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]{4,})?\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)"),
)
_MAX_TITLE = 200
_MAX_SUMMARY = 800
_MAX_KEYWORD = 80


class _Process(Protocol):
    pid: int

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def kill(self) -> None: ...


class MineContextConsent(BaseModel):
    """The exact scope and purpose an owner approved."""

    scopes: list[MineContextScope] = Field(min_length=1)
    purposes: list[MineContextPurpose] = Field(min_length=1)
    retention_days: int = Field(default=30, ge=1, le=3650)
    collection_mode: Literal["manual", "bounded_continuous"] = "manual"
    watched_paths: list[str] = Field(default_factory=list, max_length=20)
    recursive_file_watch: bool = False
    screen_targets: list[str] = Field(default_factory=list, max_length=8)
    screen_capture_interval_seconds: int = Field(default=60, ge=60, le=86_400)
    continuous_screen_capture_confirmed: bool = False

    @field_validator("scopes", "purposes")
    @classmethod
    def deduplicate_values(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @field_validator("screen_targets")
    @classmethod
    def normalize_targets(cls, value: list[str]) -> list[str]:
        cleaned = [" ".join(item.split())[:120] for item in value]
        if any(not item for item in cleaned):
            raise ValueError("screen targets cannot be blank")
        return list(dict.fromkeys(cleaned))

    @model_validator(mode="after")
    def validate_continuous_capture(self) -> MineContextConsent:
        if self.collection_mode == "manual":
            if self.continuous_screen_capture_confirmed:
                raise ValueError("continuous confirmation is invalid in manual mode")
            return self
        if "screen" in self.scopes:
            if not self.continuous_screen_capture_confirmed:
                raise ValueError("continuous screen capture confirmation is required")
            if not self.screen_targets:
                raise ValueError("continuous screen capture requires named screen targets")
            if self.screen_targets != ["all_displays"]:
                raise ValueError("this MineContext pin can only enforce the explicit screen target 'all_displays'")
        return self


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_time(value: Any, *, fallback: datetime) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return fallback
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_vendored_minecontext(repo_root: str | Path) -> dict[str, Any]:
    """Verify provenance, required source and pinned high-value checksums."""

    source_root = Path(repo_root).resolve() / MINECONTEXT_UPSTREAM_RELATIVE_PATH
    manifest_path = source_root / "VENDORED_VERSION.json"
    if not manifest_path.is_file():
        raise RuntimeError("vendored MineContext manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "commit": MINECONTEXT_UPSTREAM_COMMIT,
        "license": "Apache-2.0",
        "source_mode": "full-upstream-source",
    }
    for key, expected_value in expected.items():
        if manifest.get(key) != expected_value:
            raise RuntimeError(f"vendored MineContext {key} does not match the pinned source")
    missing = [relative for relative in _REQUIRED_UPSTREAM_FILES if not (source_root / relative).is_file()]
    if missing:
        raise RuntimeError(f"vendored MineContext source is incomplete: {', '.join(missing)}")
    for key, relative in _CHECKSUM_PATHS.items():
        if manifest.get(key) != _sha256(source_root / relative):
            raise RuntimeError(f"vendored MineContext checksum mismatch: {relative}")
    file_manifest_path = source_root / "UPSTREAM_FILES.sha256"
    if manifest.get("upstream_file_manifest_sha256") != _sha256(file_manifest_path):
        raise RuntimeError("vendored MineContext full-source manifest checksum mismatch")
    entries = file_manifest_path.read_text(encoding="utf-8").splitlines()
    if len(entries) != manifest.get("upstream_tracked_file_count"):
        raise RuntimeError("vendored MineContext full-source file count mismatch")
    for entry in entries:
        try:
            expected_digest, relative = entry.split("  ", 1)
        except ValueError as exc:
            raise RuntimeError("vendored MineContext full-source manifest is invalid") from exc
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise RuntimeError("vendored MineContext full-source manifest contains an unsafe path")
        source_path = source_root / relative_path
        if not source_path.is_file() or _sha256(source_path) != expected_digest:
            raise RuntimeError(f"vendored MineContext upstream file mismatch: {relative}")
    binary_magics = (b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf")
    for path in source_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {"", ".exe", ".dll", ".dylib", ".so"}:
            with path.open("rb") as candidate:
                if candidate.read(4).startswith(binary_magics):
                    raise RuntimeError("vendored MineContext contains an unexpected executable binary")
    return manifest


def _redact_text(value: Any, *, limit: int) -> tuple[str, int]:
    text = " ".join(str(value or "").split())
    count = 0
    for pattern in _SECRET_PATTERNS:
        text, substitutions = pattern.subn("[REDACTED]", text)
        count += substitutions
    # Remove URL query/fragment values without preserving their potentially sensitive content.
    text, substitutions = re.subn(r"(https?://[^\s?#]+)(?:\?[^\s#]*)?(?:#[^\s]*)?", r"\1", text)
    count += substitutions
    return text[:limit], count


def seal_minecontext_results(
    results: Sequence[Mapping[str, Any]],
    *,
    source_kind: MineContextScope,
    observed_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Convert upstream vector-search results to the only model-facing contract."""

    sealed_at = observed_at or _utc_now()
    records: list[dict[str, Any]] = []
    for raw in results:
        context = raw.get("context")
        if not isinstance(context, Mapping):
            continue
        extracted = context.get("extracted_data")
        if not isinstance(extracted, Mapping):
            continue
        upstream_id = str(context.get("id") or "")[:512]
        if not upstream_id:
            continue
        title, title_redactions = _redact_text(extracted.get("title"), limit=_MAX_TITLE)
        summary, summary_redactions = _redact_text(extracted.get("summary"), limit=_MAX_SUMMARY)
        if not title and not summary:
            continue
        keywords: list[str] = []
        keyword_redactions = 0
        raw_keywords = extracted.get("keywords")
        if isinstance(raw_keywords, Sequence) and not isinstance(raw_keywords, (str, bytes, bytearray)):
            for raw_keyword in raw_keywords[:20]:
                keyword, redactions = _redact_text(raw_keyword, limit=_MAX_KEYWORD)
                keyword_redactions += redactions
                if keyword and keyword not in keywords:
                    keywords.append(keyword)
        properties = context.get("properties") if isinstance(context.get("properties"), Mapping) else {}
        actual_observed_at = _parse_time(properties.get("create_time"), fallback=sealed_at)
        context_type = " ".join(str(extracted.get("context_type") or "unknown").split())[:80]
        source_record_hash = hashlib.sha256(upstream_id.encode("utf-8")).hexdigest()
        basis = {
            "source_record_hash": source_record_hash,
            "source_kind": source_kind,
            "observed_at": _iso(actual_observed_at),
            "title": title,
            "summary": summary,
            "keywords": keywords,
            "context_type": context_type,
        }
        evidence_id = f"mctx_{hashlib.sha256(_canonical_json(basis).encode()).hexdigest()[:24]}"
        records.append(
            {
                "schema_version": MINECONTEXT_EVIDENCE_SCHEMA_VERSION,
                "evidence_id": evidence_id,
                "source": {
                    "provider": "volcengine/MineContext",
                    "upstream_commit": MINECONTEXT_UPSTREAM_COMMIT,
                    "source_record_hash": source_record_hash,
                    "source_kind": source_kind,
                    "context_type": context_type,
                    "observed_at": _iso(actual_observed_at),
                    "sealed_at": _iso(sealed_at),
                },
                "summary": {"title": title, "text": summary, "keywords": keywords},
                "coverage": {
                    "completeness": "partial",
                    "basis": "authorized local observations matching the query; absence is not evidence of absence",
                },
                "privacy": {
                    "raw_content_included": False,
                    "paths_included": False,
                    "credentials_included": False,
                    "redaction_count": title_redactions + summary_redactions + keyword_redactions,
                },
                "relevance_score": round(max(0.0, min(float(raw.get("score") or 0.0), 1.0)), 6),
                "digest": hashlib.sha256(_canonical_json(basis).encode()).hexdigest(),
            }
        )
    return records


class MineContextService:
    """Lifecycle, storage and evidence boundary for per-owner sidecars."""

    def __init__(
        self,
        *,
        config: MineContextConfig,
        paths: Paths | Any | None = None,
        project_root: str | Path | None = None,
        source_verifier: Callable[[str | Path], dict[str, Any]] = verify_vendored_minecontext,
        process_factory: Callable[..., _Process] | None = None,
        health_probe: Callable[[str, int, float], bool] | None = None,
        search_client: Callable[..., Sequence[Mapping[str, Any]]] | None = None,
    ) -> None:
        self.config = config
        self.paths = paths or Paths()
        self.project_root = Path(project_root or Path(__file__).resolve().parents[5]).resolve()
        self._source_verifier = source_verifier
        self._process_factory = process_factory or self._launch_process
        self._health_probe = health_probe or self._probe_health
        self._search_client = search_client or self._search
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def _owner_root(self, owner_user_id: str) -> Path:
        """Return the owner path without creating it.

        Read paths, especially the public status GET, must not create owner
        state. Write helpers create and chmod their exact parent when needed.
        """

        return self.paths.user_dir(owner_user_id) / "minecontext"

    def _consent_path(self, owner_user_id: str) -> Path:
        return self._owner_root(owner_user_id) / "consent.json"

    def _evidence_path(self, owner_user_id: str) -> Path:
        return self._owner_root(owner_user_id) / "evidence.json"

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def _read_consent(self, owner_user_id: str) -> dict[str, Any] | None:
        value = self._read_json(self._consent_path(owner_user_id), None)
        return value if isinstance(value, dict) else None

    def _default_consent(self, *, continuous_screen_capture_confirmed: bool = False) -> MineContextConsent:
        collection_mode: Literal["manual", "bounded_continuous"] = "bounded_continuous" if continuous_screen_capture_confirmed else "manual"
        return MineContextConsent(
            scopes=list(DEFAULT_MINECONTEXT_SCOPES),
            purposes=list(DEFAULT_MINECONTEXT_PURPOSES),
            retention_days=self.config.default_retention_days,
            collection_mode=collection_mode,
            watched_paths=[],
            recursive_file_watch=False,
            screen_targets=["all_displays"] if continuous_screen_capture_confirmed else [],
            screen_capture_interval_seconds=self.config.min_screen_interval_seconds,
            continuous_screen_capture_confirmed=continuous_screen_capture_confirmed,
        )

    def enable_default(
        self,
        owner_user_id: str,
        *,
        retention_days: int | None = None,
        preserve_existing_paths: bool = True,
        continuous_screen_capture_confirmed: bool,
    ) -> dict[str, Any]:
        """Apply the bounded profile after an explicit owner confirmation."""

        if not continuous_screen_capture_confirmed:
            raise ValueError("explicit screen capture confirmation is required")

        consent = self._read_consent(owner_user_id)
        default_consent = self._default_consent(continuous_screen_capture_confirmed=True)
        default_consent.retention_days = int(retention_days if retention_days is not None else (consent or {}).get("retention_days", self.config.default_retention_days))
        if consent is not None and preserve_existing_paths:
            default_consent.watched_paths = list(consent.get("watched_paths", []))
            default_consent.recursive_file_watch = bool(consent.get("recursive_file_watch", False))
        self.authorize(owner_user_id, default_consent)
        migrated = self._read_consent(owner_user_id) or {}
        migrated["default_profile_version"] = MINECONTEXT_BOUNDED_SCREEN_PROFILE_VERSION
        self._write_json(self._consent_path(owner_user_id), migrated)
        return self.start(owner_user_id)

    def ensure_default(self, owner_user_id: str, *, strict: bool = False) -> dict[str, Any]:
        """Resume an already authorized owner without creating consent.

        This compatibility entry point is used by explicit evidence operations.
        It must never authorize a new owner or change an existing consent mode.
        """

        current = self.status(owner_user_id)
        if not self.config.enabled:
            return current
        consent = self._read_consent(owner_user_id)
        if consent is None or not consent.get("active"):
            return current
        if not current["available"]:
            return current
        try:
            if not current["running"]:
                return self.start(owner_user_id)
            return current
        except (PermissionError, RuntimeError, ValueError) as exc:
            if strict:
                raise
            current = self.status(owner_user_id)
            current["startup_error"] = str(exc)
            return current

    def authorize(self, owner_user_id: str, consent: MineContextConsent) -> dict[str, Any]:
        if consent.retention_days > self.config.max_retention_days:
            raise ValueError("retention exceeds the operator maximum")
        normalized_paths: list[str] = []
        for value in consent.watched_paths:
            path = Path(value).expanduser()
            if not path.is_absolute() or not path.is_dir():
                raise ValueError("each watched path must be an existing absolute directory")
            resolved = path.resolve()
            if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
                raise ValueError("broad root or home-directory collection is not allowed")
            normalized_paths.append(str(resolved))
        payload = consent.model_dump()
        payload["watched_paths"] = normalized_paths
        payload.update(
            {
                "schema_version": MINECONTEXT_CONSENT_SCHEMA_VERSION,
                "active": True,
                "authorized_at": _iso(_utc_now()),
                "revoked_at": None,
            }
        )
        with self._lock:
            self._write_json(self._consent_path(owner_user_id), payload)
        return self.status(owner_user_id)

    def _require_consent(self, owner_user_id: str, *, purpose: str | None = None) -> dict[str, Any]:
        consent = self._read_consent(owner_user_id)
        if not consent or not consent.get("active"):
            raise PermissionError("MineContext authorization is not active")
        if purpose is not None and purpose not in consent.get("purposes", []):
            raise PermissionError(f"MineContext purpose '{purpose}' was not authorized")
        return consent

    def status(self, owner_user_id: str) -> dict[str, Any]:
        with self._lock:
            consent = self._read_consent(owner_user_id)
            session = self._sessions.get(owner_user_id)
            running = bool(session and session["process"].poll() is None)
            evidence = self._read_json(self._evidence_path(owner_user_id), [])
        source_verified = False
        source_error: str | None = None
        try:
            self._source_verifier(self.project_root)
            source_verified = True
        except RuntimeError:
            source_error = "vendored source verification failed"
        runtime_ready = self._runtime_python().is_file()
        return {
            "schema_version": MINECONTEXT_CONSENT_SCHEMA_VERSION,
            "operator_enabled": self.config.enabled,
            "available": bool(self.config.enabled and source_verified and runtime_ready),
            "source_verified": source_verified,
            "source_error": source_error,
            "runtime_ready": runtime_ready,
            "authorized": bool(consent and consent.get("active")),
            "running": running,
            "scopes": list(consent.get("scopes", [])) if consent else [],
            "purposes": list(consent.get("purposes", [])) if consent else [],
            "collection_mode": consent.get("collection_mode") if consent else None,
            "retention_days": consent.get("retention_days") if consent else self.config.default_retention_days,
            "watched_path_count": len(consent.get("watched_paths", [])) if consent else 0,
            "screen_targets": list(consent.get("screen_targets", [])) if consent else [],
            "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
            "data_location": "local_owner_isolated",
            "raw_content_enters_deerflow": False,
        }

    def _runtime_python(self) -> Path:
        if self.config.runtime_python:
            configured = Path(self.config.runtime_python).expanduser()
            return configured if configured.is_absolute() else (self.project_root / configured).absolute()
        suffix = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        return (self.project_root / ".deer-flow" / "toolchains" / "minecontext" / suffix).absolute()

    def _source_root(self) -> Path:
        configured = Path(self.config.source_path)
        root = configured.resolve() if configured.is_absolute() else (self.project_root / configured).resolve()
        if root != (self.project_root / MINECONTEXT_UPSTREAM_RELATIVE_PATH).resolve():
            raise RuntimeError("MineContext source_path must resolve to the pinned vendored source")
        return root

    def _choose_port(self) -> int:
        for port in range(self.config.port_start, self.config.port_end + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind(("127.0.0.1", port))
                except OSError:
                    continue
                return port
        raise RuntimeError("no loopback MineContext port is available")

    def _generated_config(self, owner_user_id: str, consent: Mapping[str, Any], *, port: int, api_key: str) -> dict[str, Any]:
        owner_root = self._owner_root(owner_user_id)
        runtime = owner_root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        runtime.chmod(0o700)
        continuous = consent.get("collection_mode") == "bounded_continuous"
        screen_enabled = continuous and "screen" in consent.get("scopes", [])
        file_enabled = continuous and "files" in consent.get("scopes", []) and bool(consent.get("watched_paths"))
        return {
            "enabled": True,
            "logging": {"level": "INFO", "log_path": str(runtime / "opencontext.log")},
            "user_setting_path": str(runtime / "user_setting.yaml"),
            "document_processing": {"enabled": file_enabled, "batch_size": 3, "max_image_size": 1024, "dpi": 200, "text_threshold_per_page": 50},
            "vlm_model": {
                "base_url": "${MINECONTEXT_VLM_BASE_URL}",
                "api_key": "${MINECONTEXT_VLM_API_KEY}",
                "model": "${MINECONTEXT_VLM_MODEL}",
                "provider": self.config.vlm_provider,
            },
            "embedding_model": {
                "base_url": "${MINECONTEXT_EMBEDDING_BASE_URL}",
                "api_key": "${MINECONTEXT_EMBEDDING_API_KEY}",
                "model": "${MINECONTEXT_EMBEDDING_MODEL}",
                "provider": self.config.embedding_provider,
                "output_dim": 2048,
            },
            "capture": {
                "enabled": screen_enabled or file_enabled,
                "screenshot": {"enabled": screen_enabled, "capture_interval": int(consent.get("screen_capture_interval_seconds", 60)), "storage_path": str(runtime / "screenshots")},
                "folder_monitor": {
                    "enabled": file_enabled,
                    "monitor_interval": 30,
                    "watch_folder_paths": list(consent.get("watched_paths", [])),
                    "recursive": bool(consent.get("recursive_file_watch", False)),
                    "max_file_size": 104_857_600,
                    "initial_scan": False,
                },
                "file_monitor": {"enabled": False, "recursive": False, "initial_scan": False, "monitor_paths": [], "capture_interval": 30, "ignore_patterns": ["**/.git/**", "**/node_modules/**"]},
                "vault_document_monitor": {"enabled": False, "monitor_interval": 30, "initial_scan": False},
            },
            "processing": {
                "enabled": screen_enabled or file_enabled,
                "document_processor": {"enabled": file_enabled, "batch_size": 5, "batch_timeout": 30},
                "screenshot_processor": {"enabled": screen_enabled, "enabled_delete": True, "max_raw_properties": 5},
                "context_merger": {"enabled": False},
            },
            "storage": {
                "enabled": True,
                "backends": [
                    {
                        "name": "default_vector",
                        "storage_type": "vector_db",
                        "backend": "chromadb",
                        "config": {
                            "mode": "local",
                            "path": str(runtime / "persist" / "chromadb"),
                            "collection_prefix": "opencontext",
                        },
                    },
                    {
                        "name": "document_store",
                        "storage_type": "document_db",
                        "backend": "sqlite",
                        "config": {"path": str(runtime / "persist" / "sqlite" / "app.db")},
                    },
                ],
            },
            "consumption": {"enabled": False},
            "web": {"host": "127.0.0.1", "port": port},
            "api_auth": {"enabled": True, "api_keys": [api_key], "excluded_paths": ["/health", "/api/health"]},
            "prompts": {"language": "zh"},
            "content_generation": {"debug": {"enabled": False}, "activity": {"enabled": False}, "tips": {"enabled": False}, "todos": {"enabled": False}, "report": {"enabled": False}},
            "tools": {"operation_tools": {"web_search_tool": {"enabled": False}}},
            "completion": {"enabled": False},
        }

    def _child_environment(self) -> dict[str, str]:
        environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR") if os.environ.get(key)}
        fallback_api_key = os.environ.get(self.config.fallback_api_key_env, "")
        values = {
            "MINECONTEXT_VLM_BASE_URL": os.environ.get(
                self.config.vlm_base_url_env,
                self.config.default_vlm_base_url,
            ),
            "MINECONTEXT_VLM_API_KEY": os.environ.get(
                self.config.vlm_api_key_env,
                fallback_api_key,
            ),
            "MINECONTEXT_VLM_MODEL": os.environ.get(
                self.config.vlm_model_env,
                self.config.default_vlm_model,
            ),
            "MINECONTEXT_EMBEDDING_BASE_URL": os.environ.get(
                self.config.embedding_base_url_env,
                self.config.default_embedding_base_url,
            ),
            "MINECONTEXT_EMBEDDING_API_KEY": os.environ.get(
                self.config.embedding_api_key_env,
                fallback_api_key,
            ),
            "MINECONTEXT_EMBEDDING_MODEL": os.environ.get(
                self.config.embedding_model_env,
                self.config.default_embedding_model,
            ),
        }
        environment.update({key: value for key, value in values.items() if value})
        environment["PYTHONUNBUFFERED"] = "1"
        return environment

    @staticmethod
    def _launch_process(**kwargs: Any) -> _Process:
        return subprocess.Popen(  # noqa: S603 - absolute source-built Python and fixed argv
            kwargs["command"],
            cwd=kwargs["cwd"],
            env=kwargs["env"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    @staticmethod
    def _probe_health(host: str, port: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                response = httpx.get(f"http://{host}:{port}/health", timeout=0.5)
                if response.status_code < 500:
                    return True
            except httpx.HTTPError:
                time.sleep(0.1)
        return False

    @staticmethod
    def _search(*, host: str, port: int, api_key: str, query: str, limit: int, context_types: Sequence[str]) -> Sequence[Mapping[str, Any]]:
        response = httpx.post(
            f"http://{host}:{port}/api/vector_search",
            headers={"X-API-Key": api_key},
            json={"query": query, "top_k": limit, "context_types": list(context_types) or None, "filters": None},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {}) if isinstance(payload, Mapping) else {}
        results = data.get("results", []) if isinstance(data, Mapping) else []
        return results if isinstance(results, list) else []

    def start(self, owner_user_id: str) -> dict[str, Any]:
        if not self.config.enabled:
            raise RuntimeError("MineContext is disabled by the operator")
        consent = self._require_consent(owner_user_id)
        self._source_verifier(self.project_root)
        runtime_python = self._runtime_python()
        if not runtime_python.is_file():
            raise RuntimeError("MineContext runtime is not installed; run `make minecontext-install`")
        with self._lock:
            existing = self._sessions.get(owner_user_id)
            if existing and existing["process"].poll() is None:
                return self.status(owner_user_id)
            live = [session for session in self._sessions.values() if session["process"].poll() is None]
            if len(live) >= self.config.max_owner_processes:
                raise RuntimeError("MineContext owner process capacity is reached")
            port = self._choose_port()
            api_key = secrets.token_urlsafe(32)
            config_path = self._owner_root(owner_user_id) / "runtime" / "config.yaml"
            generated = self._generated_config(owner_user_id, consent, port=port, api_key=api_key)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(yaml.safe_dump(generated, allow_unicode=True, sort_keys=False), encoding="utf-8")
            config_path.chmod(0o600)
            command = [str(runtime_python), "-m", "opencontext.cli", "start", "--config", str(config_path), "--host", "127.0.0.1", "--port", str(port), "--workers", "1"]
            process = self._process_factory(command=command, cwd=str(self._source_root()), env=self._child_environment())
            self._sessions[owner_user_id] = {"process": process, "port": port, "api_key": api_key, "started_at": _iso(_utc_now())}
        if not self._health_probe("127.0.0.1", port, self.config.start_timeout_seconds):
            self.stop(owner_user_id)
            raise RuntimeError("MineContext did not become healthy on loopback")
        return self.status(owner_user_id)

    def stop(self, owner_user_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.pop(owner_user_id, None)
        if session:
            process = session["process"]
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=self.config.stop_timeout_seconds)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=self.config.stop_timeout_seconds)
        return self.status(owner_user_id)

    def stop_all(self) -> None:
        for owner_user_id in list(self._sessions):
            self.stop(owner_user_id)

    def revoke(self, owner_user_id: str) -> dict[str, Any]:
        self.stop(owner_user_id)
        consent = self._read_consent(owner_user_id)
        if consent:
            consent["active"] = False
            consent["revoked_at"] = _iso(_utc_now())
            consent["watched_paths"] = []
            consent["screen_targets"] = []
            self._write_json(self._consent_path(owner_user_id), consent)
        runtime = self._owner_root(owner_user_id) / "runtime"
        if runtime.exists():
            shutil.rmtree(runtime)
        return self.status(owner_user_id)

    def store_evidence(self, owner_user_id: str, records: Sequence[Mapping[str, Any]]) -> int:
        consent = self._require_consent(owner_user_id)
        allowed_scopes = set(consent.get("scopes", []))
        with self._lock:
            current = self._read_json(self._evidence_path(owner_user_id), [])
            if not isinstance(current, list):
                current = []
            by_id = {item.get("evidence_id"): item for item in current if isinstance(item, dict)}
            for record in records:
                source = record.get("source") if isinstance(record.get("source"), Mapping) else {}
                if record.get("schema_version") != MINECONTEXT_EVIDENCE_SCHEMA_VERSION or source.get("source_kind") not in allowed_scopes:
                    continue
                by_id[record.get("evidence_id")] = dict(record)
            retained = list(by_id.values())[-self.config.max_evidence_records :]
            self._write_json(self._evidence_path(owner_user_id), retained)
            self._prune(owner_user_id, consent=consent)
        return len(records)

    def _prune(self, owner_user_id: str, *, consent: Mapping[str, Any] | None = None) -> int:
        consent = consent or self._read_consent(owner_user_id)
        retention_days = int((consent or {}).get("retention_days", self.config.default_retention_days))
        cutoff = _utc_now() - timedelta(days=retention_days)
        path = self._evidence_path(owner_user_id)
        records = self._read_json(path, [])
        if not isinstance(records, list):
            records = []
        retained = []
        for record in records:
            source = record.get("source") if isinstance(record, Mapping) else None
            if not isinstance(source, Mapping):
                continue
            if _parse_time(source.get("observed_at"), fallback=datetime.min.replace(tzinfo=UTC)) >= cutoff:
                retained.append(record)
        if retained != records:
            self._write_json(path, retained)
        return len(records) - len(retained)

    def read_evidence(
        self,
        owner_user_id: str,
        *,
        purpose: MineContextPurpose,
        source_kinds: Sequence[MineContextScope] | None = None,
        evidence_ids: Sequence[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        self.ensure_default(owner_user_id, strict=True)
        consent = self._require_consent(owner_user_id, purpose=purpose)
        self._prune(owner_user_id, consent=consent)
        allowed_scopes = set(consent.get("scopes", []))
        requested_scopes = set(source_kinds or allowed_scopes) & allowed_scopes
        requested_ids = set(evidence_ids or [])
        records = self._read_json(self._evidence_path(owner_user_id), [])
        selected = []
        for record in reversed(records if isinstance(records, list) else []):
            source = record.get("source") if isinstance(record, Mapping) else {}
            if source.get("source_kind") not in requested_scopes:
                continue
            if requested_ids and record.get("evidence_id") not in requested_ids:
                continue
            selected.append(dict(record))
            if len(selected) >= min(max(limit, 1), 100):
                break
        return selected

    def sync(
        self,
        owner_user_id: str,
        *,
        query: str,
        source_kind: MineContextScope,
        purpose: MineContextPurpose,
        context_types: Sequence[str] = (),
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        self.ensure_default(owner_user_id, strict=True)
        consent = self._require_consent(owner_user_id, purpose=purpose)
        if source_kind not in consent.get("scopes", []):
            raise PermissionError(f"MineContext scope '{source_kind}' was not authorized")
        session = self._sessions.get(owner_user_id)
        if not session or session["process"].poll() is not None:
            raise RuntimeError("MineContext is not running")
        clean_query, _ = _redact_text(query, limit=500)
        if not clean_query:
            raise ValueError("query is required")
        bounded_limit = min(max(limit, 1), self.config.max_sync_results)
        raw_results = self._search_client(host="127.0.0.1", port=session["port"], api_key=session["api_key"], query=clean_query, limit=bounded_limit, context_types=[str(item)[:80] for item in context_types[:20]])
        sealed = seal_minecontext_results(raw_results[:bounded_limit], source_kind=source_kind)
        self.store_evidence(owner_user_id, sealed)
        return sealed

    def clear(self, owner_user_id: str, *, scope: Literal["evidence", "all"] = "evidence") -> dict[str, Any]:
        evidence = self._read_json(self._evidence_path(owner_user_id), [])
        deleted = len(evidence) if isinstance(evidence, list) else 0
        path = self._evidence_path(owner_user_id)
        if path.exists():
            path.unlink()
        if scope == "all":
            self.stop(owner_user_id)
            root = self._owner_root(owner_user_id)
            if root.exists():
                shutil.rmtree(root)
            disabled = self._default_consent().model_dump()
            disabled.update(
                {
                    "schema_version": MINECONTEXT_CONSENT_SCHEMA_VERSION,
                    "default_profile_version": MINECONTEXT_BOUNDED_SCREEN_PROFILE_VERSION,
                    "active": False,
                    "authorized_at": None,
                    "revoked_at": _iso(_utc_now()),
                }
            )
            self._write_json(self._consent_path(owner_user_id), disabled)
        return {"scope": scope, "deleted_evidence_records": deleted, "local_data_deleted": True}
