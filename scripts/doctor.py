#!/usr/bin/env python3
"""DeerFlow Health Check (make doctor).

Checks system requirements, configuration, LLM provider, and optional
components, then prints an actionable report.

Exit codes:
  0 — all required checks passed (warnings allowed)
  1 — one or more required checks failed
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from importlib import import_module
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

Status = Literal["ok", "warn", "fail", "skip"]
RuntimeProfile = Literal["local-direct", "local-proxy", "production"]
RUNTIME_PROFILES = {"local-direct", "local-proxy", "production"}
RUNTIME_PROFILE_OPTIONS = {*RUNTIME_PROFILES, "auto"}

IP_AGENT_PLATFORMS = {
    "douyin",
    "wechat_channels",
    "wechat_official",
    "xiaohongshu",
    "x",
    "instagram",
    "youtube",
    "tiktok",
}

IP_AGENT_REQUIRED_SOURCE_PATHS = (
    "product/defaults/USER.md",
    "product/defaults/agents/ip-agent/SOUL.md",
    "product/defaults/agents/ip-agent/config.yaml",
    "product/volcengine/capabilities.yaml",
    "skills/public/video-generation/scripts/generate.py",
    "skills/public/image-generation/scripts/generate.py",
    "skills/public/podcast-generation/scripts/generate.py",
    "skills/public/volcengine-stack/scripts/run_media_executor.py",
    "skills/public/byted-mediakit-shared/SKILL.md",
    "skills/public/byted-mediakit-editing/SKILL.md",
    "skills/public/byted-mediakit-video/SKILL.md",
    "skills/public/byted-mediakit-image/SKILL.md",
    "skills/public/byted-mediakit-audio/SKILL.md",
    "scripts/package_ip_agent.py",
    "scripts/personal_ip_video_e2e.py",
    "scripts/install_video_renderers.py",
    "scripts/ui_tars_operator.py",
    "backend/packages/harness/deerflow/community/ui_tars/source.py",
    "backend/packages/harness/deerflow/personal_ip/video_acceptance.py",
    "third_party/volcengine/mediakit-cli/go.mod",
    "third_party/volcengine/mediakit-cli/cmd/mediakit/main.go",
    "third_party/volcengine/mediakit-cli/LICENSE",
    "third_party/bytedance/HLLM/VENDORED_VERSION.json",
    "third_party/bytedance/HLLM/HLLM_CREATOR_README.md",
    "third_party/bytedance/HLLM/LICENSE",
    "third_party/bytedance/UI-TARS-desktop/VENDORED_VERSION.json",
    "third_party/bytedance/UI-TARS-desktop/LICENSE",
    "third_party/bytedance/UI-TARS-desktop/packages/ui-tars/sdk/src/GUIAgent.ts",
    "third_party/bytedance/UI-TARS-desktop/packages/ui-tars/action-parser/src/actionParser.ts",
    "third_party/bytedance/UI-TARS-desktop/packages/ui-tars/operators/nut-js/src/index.ts",
    "scripts/minecontext_source.py",
    "third_party/volcengine/MineContext/VENDORED_VERSION.json",
    "third_party/volcengine/MineContext/LICENSE",
    "third_party/volcengine/MineContext/NOTICE",
    "third_party/volcengine/MineContext/UPSTREAM_FILES.sha256",
    "third_party/volcengine/MineContext/pyproject.toml",
    "third_party/volcengine/MineContext/opencontext/cli.py",
    "third_party/volcengine/MineContext/config/config.yaml",
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
)


def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    if _supports_color():
        return f"\033[{code}m{text}\033[0m"
    return text


def green(t: str) -> str:
    return _c(t, "32")


def red(t: str) -> str:
    return _c(t, "31")


def yellow(t: str) -> str:
    return _c(t, "33")


def cyan(t: str) -> str:
    return _c(t, "36")


def bold(t: str) -> str:
    return _c(t, "1")


def _icon(status: Status) -> str:
    icons = {"ok": green("✓"), "warn": yellow("!"), "fail": red("✗"), "skip": "—"}
    return icons[status]


def _run(cmd: list[str]) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return (r.stdout or r.stderr).strip()
    except Exception:
        return None


def _parse_major(version_text: str) -> int | None:
    v = version_text.lstrip("v").split(".", 1)[0]
    return int(v) if v.isdigit() else None


def _load_yaml_file(path: Path) -> dict:
    import yaml

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("top-level config must be a YAML mapping")
    return data


def _load_app_config(config_path: Path) -> object:
    from deerflow.config.app_config import AppConfig

    return AppConfig.from_file(str(config_path))


def _split_use_path(use: str) -> tuple[str, str] | None:
    if ":" not in use:
        return None
    module_name, attr_name = use.split(":", 1)
    if not module_name or not attr_name:
        return None
    return module_name, attr_name


# ---------------------------------------------------------------------------
# Check result container
# ---------------------------------------------------------------------------


class CheckResult:
    def __init__(
        self,
        label: str,
        status: Status,
        detail: str = "",
        fix: str | None = None,
    ) -> None:
        self.label = label
        self.status = status
        self.detail = detail
        self.fix = fix

    def print(self) -> None:
        icon = _icon(self.status)
        detail_str = f"  ({self.detail})" if self.detail else ""
        print(f"  {icon} {self.label}{detail_str}")
        if self.fix:
            for line in self.fix.splitlines():
                print(f"      {cyan('→')} {line}")


def resolve_runtime_profile(
    value: str | None,
    *,
    project_root: Path | None = None,
) -> RuntimeProfile:
    profile = str(value or os.environ.get("DEERFLOW_RUNTIME_PROFILE") or "auto").strip()
    if profile not in RUNTIME_PROFILE_OPTIONS:
        raise ValueError("runtime profile must be auto, local-direct, local-proxy, or production")
    if profile != "auto":
        return profile  # type: ignore[return-value]
    if project_root is not None and check_local_direct_routing(project_root).status == "ok":
        return "local-direct"
    if shutil.which("nginx"):
        return "local-proxy"
    return "local-direct"


def _dotenv_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        from dotenv import dotenv_values

        return {str(key): str(value) for key, value in dotenv_values(path).items() if value is not None}
    except ImportError:
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
        return values


def check_local_direct_routing(project_root: Path) -> CheckResult:
    """Verify the supported Next.js :3000 → Gateway :8001 local profile."""

    frontend_values = _dotenv_values(project_root / "frontend" / ".env")
    root_values = _dotenv_values(project_root / ".env")
    backend_url = frontend_values.get("NEXT_PUBLIC_BACKEND_BASE_URL", "")
    langgraph_url = frontend_values.get("NEXT_PUBLIC_LANGGRAPH_BASE_URL", "")
    cors_value = os.environ.get(
        "GATEWAY_CORS_ORIGINS",
        root_values.get("GATEWAY_CORS_ORIGINS", ""),
    )

    def _gateway_url(value: str, *, langgraph: bool = False) -> bool:
        parsed = urlsplit(value)
        path_ok = parsed.path.rstrip("/") == "/api" if langgraph else parsed.path in {"", "/"}
        return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"} and parsed.port == 8001 and path_ok

    cors_origins = {item.strip().rstrip("/") for item in cors_value.split(",") if item.strip()}
    cors_ok = bool(cors_origins & {"http://localhost:3000", "http://127.0.0.1:3000"})
    if _gateway_url(backend_url) and _gateway_url(langgraph_url, langgraph=True) and cors_ok:
        return CheckResult(
            "runtime profile",
            "ok",
            "local-direct: frontend :3000 → Gateway :8001",
        )
    return CheckResult(
        "runtime profile",
        "fail",
        "local-direct routing is incomplete",
        fix=("Set frontend/.env backend and LangGraph URLs to http://localhost:8001 and allow http://localhost:3000 in GATEWAY_CORS_ORIGINS; or run 'make doctor PROFILE=local-proxy'."),
    )


def check_runtime_profile(
    profile: RuntimeProfile,
    project_root: Path,
) -> CheckResult:
    if profile == "local-direct":
        return check_local_direct_routing(project_root)
    if profile == "local-proxy":
        result = check_nginx()
        result.label = "runtime profile"
        if result.status == "ok":
            result.detail = f"local-proxy: nginx :2026 ({result.detail})"
        return result
    nginx_result = check_nginx()
    if nginx_result.status == "ok":
        nginx_result.label = "runtime profile"
        nginx_result.detail = f"production: host nginx available ({nginx_result.detail})"
        return nginx_result
    if shutil.which("docker") and _run(["docker", "info", "--format", "{{.ServerVersion}}"]):
        return CheckResult(
            "runtime profile",
            "ok",
            "production: bundled Docker ingress and daemon available",
        )
    return CheckResult(
        "runtime profile",
        "fail",
        "production ingress unavailable",
        fix="Start Docker for the bundled production stack, or install nginx for host production mode",
    )


def as_optional_capability(result: CheckResult) -> CheckResult:
    """Keep malformed/insecure configuration visible; skip an absent optional organ."""

    if result.status == "warn" and "literal " not in result.detail:
        return CheckResult(
            result.label,
            "skip",
            f"optional; {result.detail}",
            result.fix,
        )
    return result


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_python() -> CheckResult:
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 12):
        return CheckResult("Python", "ok", version_str)
    return CheckResult(
        "Python",
        "fail",
        version_str,
        fix="Python 3.12+ required. Install from https://www.python.org/",
    )


def check_node() -> CheckResult:
    node = shutil.which("node")
    if not node:
        return CheckResult(
            "Node.js",
            "fail",
            fix="Install Node.js 22+: https://nodejs.org/",
        )
    out = _run(["node", "-v"]) or ""
    major = _parse_major(out)
    if major is None or major < 22:
        return CheckResult(
            "Node.js",
            "fail",
            out or "unknown version",
            fix="Node.js 22+ required. Install from https://nodejs.org/",
        )
    return CheckResult("Node.js", "ok", out.lstrip("v"))


def check_pnpm() -> CheckResult:
    candidates = [["pnpm"], ["pnpm.cmd"]]
    if shutil.which("corepack"):
        candidates.append(["corepack", "pnpm"])
    for cmd in candidates:
        if shutil.which(cmd[0]):
            out = _run([*cmd, "-v"]) or ""
            return CheckResult("pnpm", "ok", out)
    return CheckResult(
        "pnpm",
        "fail",
        fix="npm install -g pnpm   (or: corepack enable)",
    )


def check_uv() -> CheckResult:
    if not shutil.which("uv"):
        return CheckResult(
            "uv",
            "fail",
            fix="curl -LsSf https://astral.sh/uv/install.sh | sh",
        )
    out = _run(["uv", "--version"]) or ""
    parts = out.split()
    version = parts[1] if len(parts) > 1 else out
    return CheckResult("uv", "ok", version)


def check_nginx() -> CheckResult:
    if shutil.which("nginx"):
        out = _run(["nginx", "-v"]) or ""
        version = out.split("/", 1)[-1] if "/" in out else out
        return CheckResult("nginx", "ok", version)
    return CheckResult(
        "nginx",
        "fail",
        fix=("macOS:   brew install nginx\nUbuntu:  sudo apt install nginx\nWindows: use WSL or Docker mode"),
    )


def check_config_exists(config_path: Path) -> CheckResult:
    if config_path.exists():
        return CheckResult("config.yaml found", "ok")
    return CheckResult(
        "config.yaml found",
        "fail",
        fix="Run 'make setup' to create it",
    )


def check_config_version(config_path: Path, project_root: Path) -> CheckResult:
    if not config_path.exists():
        return CheckResult("config.yaml version", "skip")

    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            user_data = yaml.safe_load(f) or {}
        user_ver = int(user_data.get("config_version", 0))
    except Exception as exc:
        return CheckResult("config.yaml version", "fail", str(exc))

    example_path = project_root / "config.example.yaml"
    if not example_path.exists():
        return CheckResult("config.yaml version", "skip", "config.example.yaml not found")

    try:
        import yaml

        with open(example_path, encoding="utf-8") as f:
            example_data = yaml.safe_load(f) or {}
        example_ver = int(example_data.get("config_version", 0))
    except Exception:
        return CheckResult("config.yaml version", "skip")

    if user_ver < example_ver:
        return CheckResult(
            "config.yaml version",
            "warn",
            f"v{user_ver} < v{example_ver} (latest)",
            fix="make config-upgrade",
        )
    return CheckResult("config.yaml version", "ok", f"v{user_ver}")


def check_models_configured(config_path: Path) -> CheckResult:
    if not config_path.exists():
        return CheckResult("models configured", "skip")
    try:
        data = _load_yaml_file(config_path)
        models = data.get("models", [])
        if models:
            return CheckResult("models configured", "ok", f"{len(models)} model(s)")
        return CheckResult(
            "models configured",
            "fail",
            "no models found",
            fix="Run 'make setup' to configure an LLM provider",
        )
    except Exception as exc:
        return CheckResult("models configured", "fail", str(exc))


def check_config_loadable(config_path: Path) -> CheckResult:
    if not config_path.exists():
        return CheckResult("config.yaml loadable", "skip")

    try:
        _load_app_config(config_path)
        return CheckResult("config.yaml loadable", "ok")
    except Exception as exc:
        return CheckResult(
            "config.yaml loadable",
            "fail",
            str(exc),
            fix="Run 'make setup' again, or compare with config.example.yaml",
        )


def check_llm_api_key(config_path: Path) -> list[CheckResult]:
    """Check that each model's env var is set in the environment."""
    if not config_path.exists():
        return []

    results: list[CheckResult] = []
    try:
        import yaml
        from dotenv import load_dotenv

        env_path = config_path.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)

        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        for model in data.get("models") or []:
            # Collect all values that look like $ENV_VAR references
            def _collect_env_refs(obj: object) -> list[str]:
                refs: list[str] = []
                if isinstance(obj, str) and obj.startswith("$"):
                    refs.append(obj[1:])
                elif isinstance(obj, dict):
                    for v in obj.values():
                        refs.extend(_collect_env_refs(v))
                elif isinstance(obj, list):
                    for item in obj:
                        refs.extend(_collect_env_refs(item))
                return refs

            env_refs = _collect_env_refs(model)
            model_name = model.get("name", "default")
            for var in env_refs:
                label = f"{var} set (model: {model_name})"
                if os.environ.get(var):
                    results.append(CheckResult(label, "ok"))
                else:
                    results.append(
                        CheckResult(
                            label,
                            "fail",
                            fix=f"Add {var}=<your-key> to your .env file",
                        )
                    )
    except Exception as exc:
        results.append(CheckResult("LLM API key check", "fail", str(exc)))

    return results


def check_llm_package(config_path: Path) -> list[CheckResult]:
    """Check that the LangChain provider package is installed."""
    if not config_path.exists():
        return []

    results: list[CheckResult] = []
    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        seen_packages: set[str] = set()
        for model in data.get("models") or []:
            use = model.get("use", "")
            if ":" in use:
                package_path = use.split(":")[0]
                # e.g. langchain_openai → langchain-openai
                top_level = package_path.split(".")[0]
                pip_name = top_level.replace("_", "-")
                if pip_name in seen_packages:
                    continue
                seen_packages.add(pip_name)
                label = f"{pip_name} installed"
                try:
                    __import__(top_level)
                    results.append(CheckResult(label, "ok"))
                except ImportError:
                    results.append(
                        CheckResult(
                            label,
                            "fail",
                            fix=f"cd backend && uv add {pip_name}",
                        )
                    )
    except Exception as exc:
        results.append(CheckResult("LLM package check", "fail", str(exc)))

    return results


def check_llm_auth(config_path: Path) -> list[CheckResult]:
    if not config_path.exists():
        return []

    results: list[CheckResult] = []
    try:
        data = _load_yaml_file(config_path)
        for model in data.get("models") or []:
            use = model.get("use", "")
            model_name = model.get("name", "default")

            if use == "deerflow.models.openai_codex_provider:CodexChatModel":
                auth_path = Path(os.environ.get("CODEX_AUTH_PATH", "~/.codex/auth.json")).expanduser()
                if auth_path.exists():
                    results.append(
                        CheckResult(
                            f"Codex CLI auth available (model: {model_name})",
                            "ok",
                            str(auth_path),
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            f"Codex CLI auth available (model: {model_name})",
                            "fail",
                            str(auth_path),
                            fix="Run `codex login`, or set CODEX_AUTH_PATH to a valid auth.json",
                        )
                    )

            if use == "deerflow.models.claude_provider:ClaudeChatModel":
                credential_paths = [Path(os.environ["CLAUDE_CODE_CREDENTIALS_PATH"]).expanduser() for env_name in ("CLAUDE_CODE_CREDENTIALS_PATH",) if os.environ.get(env_name)]
                credential_paths.append(Path("~/.claude/.credentials.json").expanduser())
                has_oauth_env = any(
                    os.environ.get(name)
                    for name in (
                        "ANTHROPIC_API_KEY",
                        "CLAUDE_CODE_OAUTH_TOKEN",
                        "ANTHROPIC_AUTH_TOKEN",
                        "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
                    )
                )
                existing_path = next((path for path in credential_paths if path.exists()), None)
                if has_oauth_env or existing_path is not None:
                    detail = "env var set" if has_oauth_env else str(existing_path)
                    results.append(CheckResult(f"Claude auth available (model: {model_name})", "ok", detail))
                else:
                    results.append(
                        CheckResult(
                            f"Claude auth available (model: {model_name})",
                            "fail",
                            fix=("Set ANTHROPIC_API_KEY / CLAUDE_CODE_OAUTH_TOKEN, or place credentials at ~/.claude/.credentials.json"),
                        )
                    )
    except Exception as exc:
        results.append(CheckResult("LLM auth check", "fail", str(exc)))
    return results


def check_web_search(config_path: Path) -> CheckResult:
    return check_web_tool(config_path, tool_name="web_search", label="web search configured")


def check_web_tool(config_path: Path, *, tool_name: str, label: str) -> CheckResult:
    """Warn (not fail) if a web capability is not configured."""
    if not config_path.exists():
        return CheckResult(label, "skip")

    try:
        from dotenv import load_dotenv

        env_path = config_path.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)

        data = _load_yaml_file(config_path)

        tool_entries = [t for t in data.get("tools", []) if t.get("name") == tool_name]
        if not tool_entries:
            return CheckResult(
                label,
                "warn",
                f"no {tool_name} tool in config",
                fix=f"Run 'make setup' to configure {tool_name}",
            )

        free_providers = {
            "web_search": {"ddg_search": "DuckDuckGo (no key needed)"},
            "web_fetch": {
                "jina_ai": "Jina AI Reader (no key needed)",
                "crawl4ai": "Crawl4AI (self-hosted, no key needed)",
            },
            "image_search": {"deerflow.community.image_search.tools": "DuckDuckGo Images (no key needed)"},
        }
        key_providers = {
            "web_search": {
                "tavily": "TAVILY_API_KEY",
                "infoquest": "INFOQUEST_API_KEY",
                "exa": "EXA_API_KEY",
                "firecrawl": "FIRECRAWL_API_KEY",
                "fastcrw": "CRW_API_KEY",
                "brave": "BRAVE_SEARCH_API_KEY",
                "serper": "SERPER_API_KEY",
                "volcengine_web_search": "VOLCENGINE_API_KEY",
            },
            "web_fetch": {
                "infoquest": "INFOQUEST_API_KEY",
                "exa": "EXA_API_KEY",
                "firecrawl": "FIRECRAWL_API_KEY",
                "fastcrw": "CRW_API_KEY",
            },
            "image_search": {
                "brave": "BRAVE_SEARCH_API_KEY",
                "infoquest": "INFOQUEST_API_KEY",
                "serper": "SERPER_API_KEY",
            },
            "web_capture": {
                "browserless": "BROWSERLESS_TOKEN",
            },
        }
        key_fields = {
            "web_capture": {
                "browserless": "token",
            },
        }

        def _configured_key_detail(tool: dict, default_var: str, key_field: str = "api_key") -> tuple[Status, str] | None:
            configured_key = tool.get(key_field)
            if isinstance(configured_key, str) and configured_key.strip():
                key = configured_key.strip()
                if key.startswith("$"):
                    env_name = key[1:]
                    val = os.environ.get(env_name)
                    if val and val.strip():
                        return ("ok", f"{env_name} set from config")
                    # The referenced var is unset; fall through to the default
                    # env var below, which tools use as a runtime fallback.
                else:
                    return ("warn", f"literal {key_field} set in config")

            val = os.environ.get(default_var)
            return ("ok", f"{default_var} set") if val and val.strip() else None

        def _browserless_self_hosted(tool: dict) -> bool:
            base_url = str(tool.get("base_url") or "http://localhost:3032").lower()
            return "browserless.io" not in base_url

        for tool in tool_entries:
            use = tool.get("use", "")
            for provider, detail in free_providers.get(tool_name, {}).items():
                if provider in use:
                    return CheckResult(label, "ok", detail)

        for tool in tool_entries:
            use = tool.get("use", "")
            for provider, var in key_providers.get(tool_name, {}).items():
                if provider in use:
                    key_field = key_fields.get(tool_name, {}).get(provider, "api_key")
                    key_status = _configured_key_detail(tool, var, key_field=key_field)
                    if key_status:
                        status, detail = key_status
                        if status == "warn":
                            return CheckResult(
                                label,
                                "warn",
                                f"{provider} ({detail})",
                                fix=f"Move the {key_field} to .env as {var}=<your-key> and reference it as ${var}",
                            )
                        if provider == "volcengine_web_search":
                            detail = f"{detail}; service activation checked on first use"
                        return CheckResult(label, "ok", f"{provider} ({detail})")
                    if tool_name == "web_capture" and provider == "browserless" and _browserless_self_hosted(tool):
                        return CheckResult(label, "ok", "browserless (self-hosted, token optional)")
                    return CheckResult(
                        label,
                        "warn",
                        f"{provider} configured but {var} not set",
                        fix=f"Add {var}=<your-key> to .env, or run 'make setup'",
                    )

        for tool in tool_entries:
            use = tool.get("use", "")
            split = _split_use_path(use)
            if split is None:
                return CheckResult(
                    label,
                    "fail",
                    f"invalid use path: {use}",
                    fix="Use a valid module:path provider from config.example.yaml",
                )
            module_name, attr_name = split
            try:
                module = import_module(module_name)
                getattr(module, attr_name)
            except Exception as exc:
                return CheckResult(
                    label,
                    "fail",
                    f"provider import failed: {use} ({exc})",
                    fix="Install the provider dependency or pick a valid provider in `make setup`",
                )

        return CheckResult(label, "ok")
    except Exception as exc:
        return CheckResult(label, "warn", str(exc))


def check_web_fetch(config_path: Path) -> CheckResult:
    return check_web_tool(config_path, tool_name="web_fetch", label="web fetch configured")


def check_web_capture(config_path: Path) -> CheckResult:
    return check_web_tool(config_path, tool_name="web_capture", label="web capture configured")


def check_image_search(config_path: Path) -> CheckResult:
    return check_web_tool(config_path, tool_name="image_search", label="image search configured")


def check_frontend_env(project_root: Path) -> CheckResult:
    env_path = project_root / "frontend" / ".env"
    if env_path.exists():
        return CheckResult("frontend/.env found", "ok")
    return CheckResult(
        "frontend/.env found",
        "warn",
        fix="Run 'make setup' or copy frontend/.env.example to frontend/.env",
    )


def check_sandbox(config_path: Path) -> list[CheckResult]:
    if not config_path.exists():
        return [CheckResult("sandbox configured", "skip")]

    try:
        data = _load_yaml_file(config_path)
        sandbox = data.get("sandbox")
        if not isinstance(sandbox, dict):
            return [
                CheckResult(
                    "sandbox configured",
                    "fail",
                    "missing sandbox section",
                    fix="Run 'make setup' to choose an execution mode",
                )
            ]

        sandbox_use = sandbox.get("use", "")
        tools = data.get("tools", [])
        tool_names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
        results: list[CheckResult] = []

        if "LocalSandboxProvider" in sandbox_use:
            results.append(CheckResult("sandbox configured", "ok", "Local sandbox"))
            has_bash_tool = "bash" in tool_names
            allow_host_bash = bool(sandbox.get("allow_host_bash", False))
            if has_bash_tool and not allow_host_bash:
                results.append(
                    CheckResult(
                        "bash compatibility",
                        "warn",
                        "bash tool configured but host bash is disabled",
                        fix="Enable host bash only in a fully trusted environment, or switch to container sandbox",
                    )
                )
            elif allow_host_bash:
                results.append(
                    CheckResult(
                        "bash compatibility",
                        "warn",
                        "host bash enabled on LocalSandboxProvider",
                        fix="Use container sandbox for stronger isolation when bash is required",
                    )
                )
        elif "AioSandboxProvider" in sandbox_use:
            results.append(CheckResult("sandbox configured", "ok", "Container sandbox"))
            if not sandbox.get("provisioner_url") and not (shutil.which("docker") or shutil.which("container")):
                results.append(
                    CheckResult(
                        "container runtime available",
                        "warn",
                        "no Docker/Apple Container runtime detected",
                        fix="Install Docker Desktop / Apple Container, or switch to local sandbox",
                    )
                )
        elif sandbox_use:
            results.append(CheckResult("sandbox configured", "ok", sandbox_use))
        else:
            results.append(
                CheckResult(
                    "sandbox configured",
                    "fail",
                    "sandbox.use is empty",
                    fix="Run 'make setup' to choose an execution mode",
                )
            )
        return results
    except Exception as exc:
        return [CheckResult("sandbox configured", "fail", str(exc))]


def check_env_file(project_root: Path) -> CheckResult:
    env_path = project_root / ".env"
    if env_path.exists():
        return CheckResult(".env found", "ok")
    return CheckResult(
        ".env found",
        "warn",
        fix="Run 'make setup' or copy .env.example to .env",
    )


def check_ip_agent_source_bundle(project_root: Path) -> CheckResult:
    missing = [relative for relative in IP_AGENT_REQUIRED_SOURCE_PATHS if not (project_root / relative).is_file()]
    if missing:
        preview = ", ".join(missing[:3])
        if len(missing) > 3:
            preview += f", and {len(missing) - 3} more"
        return CheckResult(
            "IP Agent source bundle",
            "fail",
            f"missing {len(missing)} required source file(s): {preview}",
            fix="Restore the complete IP Agent source distribution; do not replace it with standalone binaries",
        )
    return CheckResult(
        "IP Agent source bundle",
        "ok",
        f"{len(IP_AGENT_REQUIRED_SOURCE_PATHS)} required source files",
    )


def _verify_minecontext_source(project_root: Path) -> dict:
    from deerflow.personal_ip.minecontext import verify_vendored_minecontext

    return verify_vendored_minecontext(project_root)


def check_minecontext(project_root: Path, config_path: Path) -> list[CheckResult]:
    """Report pinned source, bundled runtime and provider readiness."""

    try:
        manifest = _verify_minecontext_source(project_root)
        results = [
            CheckResult(
                "MineContext pinned source",
                "ok",
                f"Apache-2.0 @ {manifest['commit'][:12]}",
            )
        ]
    except Exception:
        return [
            CheckResult(
                "MineContext pinned source",
                "fail",
                "source verification failed",
                fix="Restore the complete pinned third_party/volcengine/MineContext source tree",
            )
        ]
    try:
        data = _load_yaml_file(config_path) if config_path.is_file() else {}
    except Exception as exc:
        return [*results, CheckResult("MineContext configuration", "fail", str(exc))]
    config = data.get("minecontext") if isinstance(data.get("minecontext"), dict) else {}
    enabled = bool(config.get("enabled", True))
    configured_runtime = str(config.get("runtime_python") or "").strip()
    suffix = Path("Scripts/python.exe") if sys.platform.startswith("win") else Path("bin/python")
    runtime = Path(configured_runtime).expanduser() if configured_runtime else project_root / ".deer-flow" / "toolchains" / "minecontext" / suffix
    if not runtime.is_absolute():
        runtime = project_root / runtime
    if not enabled:
        results.append(CheckResult("MineContext local source", "ok", "disabled by operator configuration"))
        return results
    if runtime.is_file():
        results.append(CheckResult("MineContext source runtime", "ok", "installed from vendored source"))
    else:
        results.append(
            CheckResult(
                "MineContext source runtime",
                "warn",
                "enabled but runtime is not installed",
                fix="Run 'make minecontext-install'",
            )
        )
    vlm_key = os.environ.get("MINECONTEXT_VLM_API_KEY") or os.environ.get("VOLCENGINE_API_KEY")
    embedding_key = os.environ.get("MINECONTEXT_EMBEDDING_API_KEY") or os.environ.get("VOLCENGINE_API_KEY")
    if not vlm_key or not embedding_key:
        results.append(
            CheckResult(
                "MineContext provider settings",
                "warn",
                "VOLCENGINE_API_KEY is missing",
                fix="Set VOLCENGINE_API_KEY in .env; MINECONTEXT_* variables are optional overrides",
            )
        )
    else:
        results.append(
            CheckResult(
                "MineContext provider settings",
                "ok",
                "Volcengine key available; values not displayed",
            )
        )
    return results


def check_ip_agent_capability_manifest(project_root: Path) -> CheckResult:
    manifest_path = project_root / "product" / "volcengine" / "capabilities.yaml"
    if not manifest_path.is_file():
        return CheckResult("eight-platform capability manifest", "fail", "manifest missing")
    try:
        manifest = _load_yaml_file(manifest_path)
        configured = set(manifest.get("capabilities", {}).get("platform_operations", {}).get("platforms", []))
    except Exception as exc:
        return CheckResult("eight-platform capability manifest", "fail", str(exc))
    missing = sorted(IP_AGENT_PLATFORMS - configured)
    unexpected = sorted(configured - IP_AGENT_PLATFORMS)
    if missing or unexpected:
        detail = f"missing={missing or 'none'}; unexpected={unexpected or 'none'}"
        return CheckResult(
            "eight-platform capability manifest",
            "fail",
            detail,
            fix="Restore product/volcengine/capabilities.yaml from the source distribution",
        )
    return CheckResult("eight-platform capability manifest", "ok", "8 browser-first platforms")


def check_volcengine_product_credentials() -> list[CheckResult]:
    results: list[CheckResult] = []
    if os.environ.get("VOLCENGINE_API_KEY"):
        results.append(CheckResult("Volcengine Ark generation", "ok", "VOLCENGINE_API_KEY set"))
    else:
        results.append(
            CheckResult(
                "Volcengine Ark generation",
                "warn",
                "Seedream/Seedance and default Doubao models are unavailable",
                fix="Add VOLCENGINE_API_KEY=<your-key> to .env",
            )
        )

    if os.environ.get("VOLCENGINE_TTS_API_KEY"):
        results.append(
            CheckResult(
                "Doubao Speech",
                "ok",
                "single API key set; AppID is not required",
            )
        )
    elif os.environ.get("VOLCENGINE_TTS_ACCESS_TOKEN"):
        results.append(
            CheckResult(
                "Doubao Speech",
                "ok",
                "single API key set through the backward-compatible local alias; AppID is not required",
            )
        )
    else:
        results.append(
            CheckResult(
                "Doubao Speech",
                "warn",
                "voice generation disabled",
                fix="Add VOLCENGINE_TTS_API_KEY=<your-key> to .env",
            )
        )

    if os.environ.get("MEDIAKIT_API_KEY"):
        results.append(CheckResult("AI MediaKit cloud", "ok", "paid cloud capabilities enabled"))
    else:
        results.append(
            CheckResult(
                "AI MediaKit cloud",
                "ok",
                "optional paid key not set; deterministic local media operations remain available",
            )
        )
    return results


def check_local_media_toolchain(project_root: Path) -> list[CheckResult]:
    suffix = ".exe" if sys.platform.startswith("win") else ""
    ffmpeg = project_root / ".deer-flow" / "toolchains" / "ffmpeg" / "bin" / f"ffmpeg{suffix}"
    ffprobe = project_root / ".deer-flow" / "toolchains" / "ffmpeg" / "bin" / f"ffprobe{suffix}"
    mediakit = project_root / ".deer-flow" / "bin" / f"mediakit-cli{suffix}"
    results: list[CheckResult] = []

    if ffmpeg.is_file() and ffprobe.is_file():
        version = _run([str(ffmpeg), "-version"])
        if version is None:
            results.append(
                CheckResult(
                    "project-local FFmpeg",
                    "fail",
                    "installed binaries cannot execute",
                    fix="Run 'make ffmpeg-toolchain' to rebuild the pinned toolchain",
                )
            )
        else:
            first_line = version.splitlines()[0] if version else "version available"
            results.append(CheckResult("project-local FFmpeg", "ok", first_line))
    else:
        results.append(
            CheckResult(
                "project-local FFmpeg",
                "warn",
                "pinned ffmpeg/ffprobe not built",
                fix="Run 'make ffmpeg-toolchain'",
            )
        )

    if mediakit.is_file():
        version = _run([str(mediakit), "version"])
        if version is None:
            results.append(
                CheckResult(
                    "source-built MediaKit CLI",
                    "fail",
                    "binary cannot execute",
                    fix="Run 'make mediakit-build' to rebuild from vendored source",
                )
            )
        else:
            results.append(
                CheckResult(
                    "source-built MediaKit CLI",
                    "ok",
                    version.splitlines()[0] if version else "version available",
                )
            )
    else:
        results.append(
            CheckResult(
                "source-built MediaKit CLI",
                "warn",
                "not built yet",
                fix="Run 'make mediakit-toolchain && make mediakit-build'",
            )
        )
    return results


def _playwright_chromium_path() -> Path:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        return Path(playwright.chromium.executable_path)


def check_chromium_runtime() -> CheckResult:
    try:
        executable = _playwright_chromium_path()
    except ImportError:
        return CheckResult(
            "Chromium browser runtime",
            "warn",
            "Playwright browser extra is not installed",
            fix="cd backend && uv sync --extra browser && uv run playwright install chromium",
        )
    except Exception as exc:
        return CheckResult(
            "Chromium browser runtime",
            "warn",
            f"Playwright could not resolve Chromium: {exc}",
            fix="cd backend && uv run playwright install chromium",
        )
    if executable.is_file():
        return CheckResult("Chromium browser runtime", "ok", "Playwright Chromium installed")
    return CheckResult(
        "Chromium browser runtime",
        "warn",
        "Playwright is installed but Chromium is missing",
        fix="cd backend && uv run playwright install chromium",
    )


def check_video_renderers(project_root: Path) -> list[CheckResult]:
    root = project_root / "product" / "video-renderers"
    node = shutil.which("node")
    if not node:
        return [CheckResult("HyperFrames source renderer", "warn", "Node.js is unavailable")]
    source_files = (
        root / "package.json",
        root / "package-lock.json",
        root / "version-policy.json",
        root / "verify-pins.mjs",
        root / "prepare-hyperframes.mjs",
        root / "render-remotion.mjs",
        root / "remotion" / "scene.tsx",
    )
    if any(not path.is_file() for path in source_files):
        return [
            CheckResult(
                "HyperFrames source renderer",
                "fail",
                "required renderer source is incomplete",
            )
        ]
    installed = (root / "node_modules" / "hyperframes" / "dist" / "cli.js").is_file() and (root / "node_modules" / "gsap" / "dist" / "gsap.min.js").is_file() and (root / "node_modules" / "@remotion" / "cli" / "remotion-cli.js").is_file()
    verification = _run([node, str(root / "verify-pins.mjs")])
    if verification is None:
        return [
            CheckResult(
                "HyperFrames source renderer",
                "fail",
                "source or dependency versions drifted",
                fix="Run 'make video-renderers-install'",
            )
        ]
    return [
        CheckResult(
            "HyperFrames source renderer",
            "ok" if installed else "warn",
            "HyperFrames 0.7.57 exact pins installed" if installed else "source and lock verified; runtime dependencies are not installed",
            fix=None if installed else "Run 'make video-renderers-install'",
        ),
        CheckResult(
            "Remotion renderer",
            "ok",
            "4.0.488 available for MVP; confirm license eligibility before customer distribution",
        ),
    ]


def check_ui_tars(project_root: Path, config_path: Path) -> list[CheckResult]:
    """Verify the default-off UI-TARS source, config, permissions and health."""
    from deerflow.community.ui_tars.permissions import diagnose_desktop_permissions
    from deerflow.community.ui_tars.source import verify_vendored_ui_tars

    results: list[CheckResult] = []
    try:
        manifest = verify_vendored_ui_tars(project_root / "third_party" / "bytedance" / "UI-TARS-desktop")
        results.append(
            CheckResult(
                "UI-TARS pinned source",
                "ok",
                f"{manifest['upstream_commit'][:12]}; Apache-2.0; no precompiled operator binary",
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        results.append(
            CheckResult(
                "UI-TARS pinned source",
                "fail",
                str(exc),
                fix="Restore third_party/bytedance/UI-TARS-desktop from the fixed source package",
            )
        )

    if not config_path.is_file():
        results.append(CheckResult("UI-TARS optional organ", "skip", "config.yaml missing"))
        return results
    try:
        config = _load_yaml_file(config_path).get("ui_tars") or {}
        if not isinstance(config, dict):
            raise ValueError("ui_tars must be a mapping")
    except Exception as exc:
        results.append(CheckResult("UI-TARS optional organ", "fail", str(exc)))
        return results
    if config.get("enabled") is not True:
        results.append(
            CheckResult(
                "UI-TARS optional organ",
                "skip",
                "disabled by default; Browser Control remains primary",
                fix="Set ui_tars.enabled only after configuring a local model and desktop permissions",
            )
        )
        return results

    model = str(config.get("model") or "").strip()
    api_base = str(config.get("api_base") or "").strip()
    key_env = str(config.get("api_key_env") or "UI_TARS_API_KEY").strip()
    missing = [name for name, value in (("model", model), ("api_base", api_base)) if not value]
    model_host = urlsplit(api_base).hostname
    model_is_loopback = model_host in {"127.0.0.1", "localhost", "::1"}
    key_is_required = bool(api_base) and not model_is_loopback
    key_is_configured = bool(os.environ.get(key_env))
    if missing or (key_is_required and not key_is_configured):
        detail = "missing " + ", ".join(
            [
                *missing,
                *([key_env] if key_is_required and not key_is_configured else []),
            ]
        )
        results.append(
            CheckResult(
                "UI-TARS model configuration",
                "fail",
                detail,
                fix=f"Set ui_tars.model/api_base and export {key_env} for a remote model; the key value is never logged",
            )
        )
    else:
        authentication = f"{key_env} set" if key_is_configured else "loopback model; key optional"
        results.append(CheckResult("UI-TARS model configuration", "ok", f"model={model}; {authentication}"))

    state_dir = _ip_agent_state_dir(project_root) / "ui-tars"
    token_is_configured = len(os.environ.get("UI_TARS_OPERATOR_TOKEN", "").strip()) >= 32
    if not token_is_configured:
        try:
            token_is_configured = len((state_dir / "operator.token").read_text(encoding="utf-8").strip()) >= 32
        except OSError:
            token_is_configured = False
    if token_is_configured:
        results.append(CheckResult("UI-TARS operator authentication", "ok", "local token configured"))
    else:
        results.append(
            CheckResult(
                "UI-TARS operator authentication",
                "warn",
                "local token missing",
                fix="Managed mode: run make ui-tars-start. Connect mode: export UI_TARS_OPERATOR_TOKEN in the Gateway environment",
            )
        )

    permissions = diagnose_desktop_permissions()
    permission_states = (permissions["screen_recording"], permissions["accessibility"])
    if permissions["supported"] and all(state == "granted" for state in permission_states):
        results.append(
            CheckResult(
                "UI-TARS desktop permissions",
                "ok",
                "Screen Recording and Accessibility granted",
            )
        )
    else:
        results.append(
            CheckResult(
                "UI-TARS desktop permissions",
                "warn",
                f"screen={permission_states[0]}; accessibility={permission_states[1]}; {permissions['detail']}",
                fix="Grant the two permissions to the Python executable used by make ui-tars-start, then restart the operator",
            )
        )

    try:
        from deerflow.community.ui_tars.client import UITarsOperatorClient

        endpoint = str(config.get("endpoint") or "http://127.0.0.1:9137")
        client = UITarsOperatorClient(endpoint, timeout_seconds=2.0, state_dir=state_dir)
        health = client._request("/health", payload=None, authenticated=False)  # noqa: SLF001 - doctor probe
        results.append(
            CheckResult(
                "UI-TARS local operator",
                "ok",
                f"connected; status={health.get('status', 'unknown')}",
            )
        )
    except Exception:
        results.append(
            CheckResult(
                "UI-TARS local operator",
                "warn",
                "not connected",
                fix="Run 'make ui-tars-install && make ui-tars-start', then rerun 'make ui-tars-doctor'",
            )
        )
    return results


def _ip_agent_state_dir(project_root: Path) -> Path:
    configured = os.environ.get("DEER_FLOW_HOME")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else project_root / "backend" / ".deer-flow"
    )


def check_ip_agent_local_state(project_root: Path) -> list[CheckResult]:
    state_dir = _ip_agent_state_dir(project_root)
    installed_agents = list(state_dir.glob("users/*/agents/ip-agent/SOUL.md")) if state_dir.is_dir() else []
    if installed_agents:
        product_agent = project_root / "product" / "defaults" / "agents" / "ip-agent"
        expected_files = tuple(product_agent / name for name in ("SOUL.md", "config.yaml"))
        stale_count = 0
        if all(path.is_file() for path in expected_files):
            for installed_soul in installed_agents:
                installed_dir = installed_soul.parent
                if any(
                    not (installed_dir / source.name).is_file()
                    or (installed_dir / source.name).read_bytes() != source.read_bytes()
                    for source in expected_files
                ):
                    stale_count += 1
        if stale_count:
            agent_result = CheckResult(
                "default IP Agent installed",
                "warn",
                f"{len(installed_agents)} user profile(s); {stale_count} stale product agent(s)",
                fix="Run 'make ip-refresh' to update the product-owned IP Agent without replacing USER.md",
            )
        else:
            agent_result = CheckResult(
                "default IP Agent installed",
                "ok",
                f"{len(installed_agents)} user profile(s)",
            )
    else:
        agent_result = CheckResult(
            "default IP Agent installed",
            "warn",
            "no user-scoped IP Agent profile found",
            fix="Run 'make ip-init' for the default user before first launch",
        )

    profile_roots = list(state_dir.glob("users/*/browser-profiles")) if state_dir.is_dir() else []
    profile_count = sum(1 for root in profile_roots for child in root.iterdir() if child.is_dir())
    profile_result = CheckResult(
        "account-isolated browser profiles",
        "ok",
        f"{profile_count} persisted account profile(s); new profiles are created after manual login",
    )
    return [agent_result, profile_result]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DeerFlow health check")
    parser.add_argument(
        "--profile",
        choices=sorted(RUNTIME_PROFILE_OPTIONS),
        help="supported runtime profile (default: DEERFLOW_RUNTIME_PROFILE or auto)",
    )
    args = parser.parse_args([] if argv is None else argv)
    project_root = Path(__file__).resolve().parents[1]
    profile = resolve_runtime_profile(args.profile, project_root=project_root)
    config_path = project_root / "config.yaml"

    # Load .env early so key checks work
    try:
        from dotenv import load_dotenv

        env_path = project_root / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
    except ImportError:
        pass

    print()
    print(bold("DeerFlow Health Check"))
    print("═" * 40)

    sections: list[tuple[str, list[CheckResult]]] = []

    # ── System Requirements ────────────────────────────────────────────────────
    sys_checks = [
        check_python(),
        check_node(),
        check_pnpm(),
        check_uv(),
        check_runtime_profile(profile, project_root),
    ]
    sections.append(("System Requirements", sys_checks))

    # ── Configuration ─────────────────────────────────────────────────────────
    cfg_checks: list[CheckResult] = [
        check_env_file(project_root),
        check_frontend_env(project_root),
        check_config_exists(config_path),
        check_config_version(config_path, project_root),
        check_config_loadable(config_path),
        check_models_configured(config_path),
    ]
    sections.append(("Configuration", cfg_checks))

    # ── LLM Provider ──────────────────────────────────────────────────────────
    llm_checks: list[CheckResult] = [
        *check_llm_api_key(config_path),
        *check_llm_auth(config_path),
        *check_llm_package(config_path),
    ]
    sections.append(("LLM Provider", llm_checks))

    # ── Web Capabilities ─────────────────────────────────────────────────────
    search_checks = [
        as_optional_capability(check_web_search(config_path)),
        as_optional_capability(check_web_fetch(config_path)),
        as_optional_capability(check_web_capture(config_path)),
        as_optional_capability(check_image_search(config_path)),
    ]
    sections.append(("Web Capabilities", search_checks))

    # ── Sandbox ──────────────────────────────────────────────────────────────
    sandbox_checks = check_sandbox(config_path)
    sections.append(("Sandbox", sandbox_checks))

    # ── IP Agent Product ─────────────────────────────────────────────────────
    ip_agent_checks = [
        check_ip_agent_source_bundle(project_root),
        check_ip_agent_capability_manifest(project_root),
        *check_minecontext(project_root, config_path),
        *check_volcengine_product_credentials(),
        *check_local_media_toolchain(project_root),
        *check_video_renderers(project_root),
        check_chromium_runtime(),
        *check_ui_tars(project_root, config_path),
        *check_ip_agent_local_state(project_root),
    ]
    sections.append(("IP Agent Product", ip_agent_checks))

    # ── Render ────────────────────────────────────────────────────────────────
    total_fails = 0
    total_warns = 0

    for section_title, checks in sections:
        print()
        print(bold(section_title))
        for cr in checks:
            cr.print()
            if cr.status == "fail":
                total_fails += 1
            elif cr.status == "warn":
                total_warns += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("═" * 40)
    if total_fails == 0 and total_warns == 0:
        print(f"Status: {green('Ready')}")
        command = "make dev-direct" if profile == "local-direct" else "make dev"
        print(f"Run {cyan(command)} to start DeerFlow")
    elif total_fails == 0:
        print(f"Status: {yellow(f'Ready ({total_warns} warning(s))')}")
        command = "make dev-direct" if profile == "local-direct" else "make dev"
        print(f"Run {cyan(command)} to start DeerFlow")
    else:
        print(f"Status: {red(f'{total_fails} error(s), {total_warns} warning(s)')}")
        print("Fix the errors above, then run 'make doctor' again.")

    print()
    return 0 if total_fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
