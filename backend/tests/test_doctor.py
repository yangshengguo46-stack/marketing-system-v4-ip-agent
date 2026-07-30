"""Unit tests for scripts/doctor.py.

Run from repo root:
    cd backend && uv run pytest tests/test_doctor.py -v
"""

from __future__ import annotations

import sys

import doctor
import pytest


class TestUITarsDoctor:
    def test_default_off_is_explicit_and_source_is_verified(self, tmp_path, monkeypatch):
        config = tmp_path / "config.yaml"
        config.write_text("ui_tars:\n  enabled: false\n", encoding="utf-8")
        monkeypatch.setattr(
            "deerflow.community.ui_tars.source.verify_vendored_ui_tars",
            lambda _root: {
                "upstream_commit": "c2ad42e3eb9b27830db41a3e6f51ca7179d9b168",
                "license": "Apache-2.0",
            },
        )
        results = doctor.check_ui_tars(tmp_path, config)
        assert results[0].status == "ok"
        assert results[1].status == "skip"
        assert "Browser Control" in results[1].detail

    def test_enabled_reports_model_permission_and_connection_gaps(self, tmp_path, monkeypatch):
        config = tmp_path / "config.yaml"
        config.write_text(
            "ui_tars:\n  enabled: true\n  endpoint: http://127.0.0.1:9137\n  model: fixture\n  api_base: https://model.example/v1\n  api_key_env: UI_TARS_API_KEY\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("UI_TARS_API_KEY", "not-printed")
        monkeypatch.setattr(
            "deerflow.community.ui_tars.source.verify_vendored_ui_tars",
            lambda _root: {
                "upstream_commit": "c2ad42e3eb9b27830db41a3e6f51ca7179d9b168",
                "license": "Apache-2.0",
            },
        )
        monkeypatch.setattr(
            "deerflow.community.ui_tars.permissions.diagnose_desktop_permissions",
            lambda: {
                "supported": True,
                "screen_recording": "denied",
                "accessibility": "denied",
                "detail": "grant permissions",
            },
        )
        monkeypatch.setattr(
            "deerflow.community.ui_tars.client.UITarsOperatorClient._request",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
        )
        results = doctor.check_ui_tars(tmp_path, config)
        by_label = {result.label: result for result in results}
        assert by_label["UI-TARS model configuration"].status == "ok"
        assert "not-printed" not in by_label["UI-TARS model configuration"].detail
        assert by_label["UI-TARS desktop permissions"].status == "warn"
        assert by_label["UI-TARS local operator"].status == "warn"

    def test_enabled_loopback_model_does_not_require_api_key(self, tmp_path, monkeypatch):
        config = tmp_path / "config.yaml"
        config.write_text(
            "ui_tars:\n  enabled: true\n  model: fixture\n  api_base: http://127.0.0.1:9999/v1\n",
            encoding="utf-8",
        )
        monkeypatch.delenv("UI_TARS_API_KEY", raising=False)
        monkeypatch.setattr(
            "deerflow.community.ui_tars.source.verify_vendored_ui_tars",
            lambda _root: {
                "upstream_commit": "c2ad42e3eb9b27830db41a3e6f51ca7179d9b168",
                "license": "Apache-2.0",
            },
        )
        monkeypatch.setattr(
            "deerflow.community.ui_tars.permissions.diagnose_desktop_permissions",
            lambda: {
                "supported": False,
                "screen_recording": "not_applicable",
                "accessibility": "not_applicable",
                "detail": "fixture",
            },
        )
        monkeypatch.setattr(
            "deerflow.community.ui_tars.client.UITarsOperatorClient._request",
            lambda *_args, **_kwargs: {"status": "degraded"},
        )

        by_label = {result.label: result for result in doctor.check_ui_tars(tmp_path, config)}
        assert by_label["UI-TARS model configuration"].status == "ok"
        assert "key optional" in by_label["UI-TARS model configuration"].detail


# ---------------------------------------------------------------------------
# check_python
# ---------------------------------------------------------------------------


class TestCheckPython:
    def test_current_python_passes(self):
        result = doctor.check_python()
        assert sys.version_info >= (3, 12)
        assert result.status == "ok"


# ---------------------------------------------------------------------------
# check_config_exists
# ---------------------------------------------------------------------------


class TestCheckConfigExists:
    def test_missing_config(self, tmp_path):
        result = doctor.check_config_exists(tmp_path / "config.yaml")
        assert result.status == "fail"
        assert result.fix is not None

    def test_present_config(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")
        result = doctor.check_config_exists(cfg)
        assert result.status == "ok"


# ---------------------------------------------------------------------------
# check_config_version
# ---------------------------------------------------------------------------


class TestCheckConfigVersion:
    def test_up_to_date(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")
        example = tmp_path / "config.example.yaml"
        example.write_text("config_version: 5\n")
        result = doctor.check_config_version(cfg, tmp_path)
        assert result.status == "ok"

    def test_outdated(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 3\n")
        example = tmp_path / "config.example.yaml"
        example.write_text("config_version: 5\n")
        result = doctor.check_config_version(cfg, tmp_path)
        assert result.status == "warn"
        assert result.fix is not None

    def test_missing_config_skipped(self, tmp_path):
        result = doctor.check_config_version(tmp_path / "config.yaml", tmp_path)
        assert result.status == "skip"


# ---------------------------------------------------------------------------
# check_config_loadable
# ---------------------------------------------------------------------------


class TestCheckConfigLoadable:
    def test_loadable_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")
        monkeypatch.setattr(doctor, "_load_app_config", lambda _path: object())
        result = doctor.check_config_loadable(cfg)
        assert result.status == "ok"

    def test_invalid_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")

        def fail(_path):
            raise ValueError("bad config")

        monkeypatch.setattr(doctor, "_load_app_config", fail)
        result = doctor.check_config_loadable(cfg)
        assert result.status == "fail"
        assert "bad config" in result.detail


# ---------------------------------------------------------------------------
# check_models_configured
# ---------------------------------------------------------------------------


class TestCheckModelsConfigured:
    def test_no_models(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels: []\n")
        result = doctor.check_models_configured(cfg)
        assert result.status == "fail"

    def test_one_model(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels:\n  - name: default\n    use: langchain_openai:ChatOpenAI\n    model: gpt-4o\n    api_key: $OPENAI_API_KEY\n")
        result = doctor.check_models_configured(cfg)
        assert result.status == "ok"

    def test_missing_config_skipped(self, tmp_path):
        result = doctor.check_models_configured(tmp_path / "config.yaml")
        assert result.status == "skip"


# ---------------------------------------------------------------------------
# check_llm_api_key
# ---------------------------------------------------------------------------


class TestCheckLLMApiKey:
    def test_key_set(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels:\n  - name: default\n    use: langchain_openai:ChatOpenAI\n    model: gpt-4o\n    api_key: $OPENAI_API_KEY\n")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        results = doctor.check_llm_api_key(cfg)
        assert any(r.status == "ok" for r in results)
        assert all(r.status != "fail" for r in results)

    def test_key_missing(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels:\n  - name: default\n    use: langchain_openai:ChatOpenAI\n    model: gpt-4o\n    api_key: $OPENAI_API_KEY\n")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        results = doctor.check_llm_api_key(cfg)
        assert any(r.status == "fail" for r in results)
        failed = [r for r in results if r.status == "fail"]
        assert all(r.fix is not None for r in failed)
        assert any("OPENAI_API_KEY" in (r.fix or "") for r in failed)

    def test_missing_config_returns_empty(self, tmp_path):
        results = doctor.check_llm_api_key(tmp_path / "config.yaml")
        assert results == []


# ---------------------------------------------------------------------------
# check_llm_auth
# ---------------------------------------------------------------------------


class TestCheckLLMAuth:
    def test_codex_auth_file_missing_fails(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels:\n  - name: codex\n    use: deerflow.models.openai_codex_provider:CodexChatModel\n    model: gpt-5.4\n")
        monkeypatch.setenv("CODEX_AUTH_PATH", str(tmp_path / "missing-auth.json"))
        results = doctor.check_llm_auth(cfg)
        assert any(result.status == "fail" and "Codex CLI auth available" in result.label for result in results)

    def test_claude_oauth_env_passes(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels:\n  - name: claude\n    use: deerflow.models.claude_provider:ClaudeChatModel\n    model: claude-sonnet-4-6\n")
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")
        results = doctor.check_llm_auth(cfg)
        assert any(result.status == "ok" and "Claude auth available" in result.label for result in results)


# ---------------------------------------------------------------------------
# check_web_search
# ---------------------------------------------------------------------------


class TestCheckWebSearch:
    def test_ddg_always_ok(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "config_version: 5\nmodels:\n  - name: default\n    use: langchain_openai:ChatOpenAI\n    model: gpt-4o\n    api_key: $OPENAI_API_KEY\ntools:\n  - name: web_search\n    use: deerflow.community.ddg_search.tools:web_search_tool\n"
        )
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"
        assert "DuckDuckGo" in result.detail

    def test_tavily_with_key_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.tavily.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"

    def test_tavily_without_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.tavily.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert result.fix is not None
        assert "make setup" in result.fix

    def test_brave_with_key_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "bsa-test")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.brave.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"

    def test_brave_without_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.brave.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert result.fix is not None
        assert "BRAVE_SEARCH_API_KEY" in result.fix

    def test_brave_with_inline_api_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text('config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.brave.tools:web_search_tool\n    api_key: "inline-key"\n')
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert "literal api_key set in config" in result.detail
        assert "BRAVE_SEARCH_API_KEY" in (result.fix or "")

    def test_brave_with_api_key_env_ref_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "bsa-test")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.brave.tools:web_search_tool\n    api_key: $BRAVE_SEARCH_API_KEY\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"
        assert "BRAVE_SEARCH_API_KEY set from config" in result.detail

    def test_serper_with_key_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.serper.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"
        assert "serper" in result.detail

    def test_serper_without_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.serper.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert "SERPER_API_KEY" in (result.fix or "")

    def test_serper_inline_api_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.serper.tools:web_search_tool\n    api_key: inline-key\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert "literal api_key set in config" in result.detail
        assert "SERPER_API_KEY" in (result.fix or "")

    def test_serper_config_env_ref_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.serper.tools:web_search_tool\n    api_key: $SERPER_API_KEY\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"
        assert "SERPER_API_KEY set from config" in result.detail

    def test_serper_unresolved_env_ref_falls_back_to_default_var(self, tmp_path, monkeypatch):
        # The referenced $VAR is unset, but the default SERPER_API_KEY is set,
        # which the tool uses as a runtime fallback; report ok rather than warn.
        monkeypatch.delenv("MY_CUSTOM_SERPER_KEY", raising=False)
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.serper.tools:web_search_tool\n    api_key: $MY_CUSTOM_SERPER_KEY\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"
        assert "SERPER_API_KEY set" in result.detail

    def test_serper_unresolved_env_ref_without_default_warns(self, tmp_path, monkeypatch):
        # Neither the referenced $VAR nor the default SERPER_API_KEY is set.
        monkeypatch.delenv("MY_CUSTOM_SERPER_KEY", raising=False)
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.serper.tools:web_search_tool\n    api_key: $MY_CUSTOM_SERPER_KEY\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert "SERPER_API_KEY" in (result.fix or "")

    def test_no_search_tool_warns(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools: []\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert result.fix is not None
        assert "make setup" in result.fix

    def test_missing_config_skipped(self, tmp_path):
        result = doctor.check_web_search(tmp_path / "config.yaml")
        assert result.status == "skip"

    def test_invalid_provider_use_fails(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.not_real.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "fail"


# ---------------------------------------------------------------------------
# check_web_fetch
# ---------------------------------------------------------------------------


class TestCheckWebFetch:
    def test_jina_always_ok(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_fetch\n    use: deerflow.community.jina_ai.tools:web_fetch_tool\n")
        result = doctor.check_web_fetch(cfg)
        assert result.status == "ok"
        assert "Jina AI" in result.detail

    def test_firecrawl_without_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_fetch\n    use: deerflow.community.firecrawl.tools:web_fetch_tool\n")
        result = doctor.check_web_fetch(cfg)
        assert result.status == "warn"
        assert "FIRECRAWL_API_KEY" in (result.fix or "")

    def test_no_fetch_tool_warns(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools: []\n")
        result = doctor.check_web_fetch(cfg)
        assert result.status == "warn"
        assert result.fix is not None

    def test_invalid_provider_use_fails(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_fetch\n    use: deerflow.community.not_real.tools:web_fetch_tool\n")
        result = doctor.check_web_fetch(cfg)
        assert result.status == "fail"


# ---------------------------------------------------------------------------
# check_web_capture
# ---------------------------------------------------------------------------


class TestCheckWebCapture:
    def test_browserless_self_host_without_token_ok(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BROWSERLESS_TOKEN", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_capture\n    use: deerflow.community.browserless.tools:web_capture_tool\n    base_url: http://localhost:3032\n")

        result = doctor.check_web_capture(cfg)

        assert result.status == "ok"
        assert "self-hosted" in result.detail

    def test_browserless_token_env_ref_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BROWSERLESS_TOKEN", "browserless-test")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_capture\n    use: deerflow.community.browserless.tools:web_capture_tool\n    base_url: https://production-sfo.browserless.io\n    token: $BROWSERLESS_TOKEN\n")

        result = doctor.check_web_capture(cfg)

        assert result.status == "ok"
        assert "BROWSERLESS_TOKEN set from config" in result.detail

    def test_browserless_cloud_without_token_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BROWSERLESS_TOKEN", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_capture\n    use: deerflow.community.browserless.tools:web_capture_tool\n    base_url: https://production-sfo.browserless.io\n")

        result = doctor.check_web_capture(cfg)

        assert result.status == "warn"
        assert "BROWSERLESS_TOKEN" in (result.fix or "")


# ---------------------------------------------------------------------------
# check_image_search
# ---------------------------------------------------------------------------


class TestCheckImageSearch:
    def test_ddg_always_ok(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.image_search.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "ok"
        assert "DuckDuckGo" in result.detail

    def test_serper_with_key_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.serper.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "ok"
        assert "serper" in result.detail

    def test_serper_without_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.serper.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "warn"
        assert "SERPER_API_KEY" in (result.fix or "")

    def test_serper_inline_api_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.serper.tools:image_search_tool\n    api_key: inline-key\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "warn"
        assert "literal api_key set in config" in result.detail
        assert "SERPER_API_KEY" in (result.fix or "")

    def test_serper_config_env_ref_without_env_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.serper.tools:image_search_tool\n    api_key: $SERPER_API_KEY\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "warn"
        assert "SERPER_API_KEY" in (result.fix or "")

    def test_brave_image_search_with_key_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "bsa-test")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.brave.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "ok"
        assert "brave" in result.detail

    def test_brave_image_search_without_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.brave.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "warn"
        assert "BRAVE_SEARCH_API_KEY" in (result.fix or "")

    def test_brave_image_search_inline_api_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.brave.tools:image_search_tool\n    api_key: inline-key\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "warn"
        assert "literal api_key set in config" in result.detail
        assert "BRAVE_SEARCH_API_KEY" in (result.fix or "")

    def test_infoquest_with_key_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INFOQUEST_API_KEY", "test-key")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.infoquest.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "ok"
        assert "infoquest" in result.detail

    def test_no_image_search_tool_warns(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools: []\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "warn"
        assert result.fix is not None

    def test_invalid_provider_use_fails(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.not_real.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "fail"


# ---------------------------------------------------------------------------
# check_env_file
# ---------------------------------------------------------------------------


class TestCheckEnvFile:
    def test_missing(self, tmp_path):
        result = doctor.check_env_file(tmp_path)
        assert result.status == "warn"

    def test_present(self, tmp_path):
        (tmp_path / ".env").write_text("KEY=val\n")
        result = doctor.check_env_file(tmp_path)
        assert result.status == "ok"


# ---------------------------------------------------------------------------
# check_frontend_env
# ---------------------------------------------------------------------------


class TestCheckFrontendEnv:
    def test_missing(self, tmp_path):
        result = doctor.check_frontend_env(tmp_path)
        assert result.status == "warn"

    def test_present(self, tmp_path):
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        (frontend_dir / ".env").write_text("KEY=val\n")
        result = doctor.check_frontend_env(tmp_path)
        assert result.status == "ok"


class TestRuntimeProfiles:
    def test_local_direct_requires_matching_frontend_and_cors(self, tmp_path):
        (tmp_path / "frontend").mkdir()
        (tmp_path / "frontend" / ".env").write_text(
            "NEXT_PUBLIC_BACKEND_BASE_URL=http://localhost:8001\nNEXT_PUBLIC_LANGGRAPH_BASE_URL=http://localhost:8001/api\n",
            encoding="utf-8",
        )
        (tmp_path / ".env").write_text(
            "GATEWAY_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000\n",
            encoding="utf-8",
        )

        result = doctor.check_local_direct_routing(tmp_path)

        assert result.status == "ok"
        assert "3000" in result.detail
        assert "8001" in result.detail

    def test_local_direct_rejects_proxy_frontend_urls(self, tmp_path):
        (tmp_path / "frontend").mkdir()
        (tmp_path / "frontend" / ".env").write_text(
            "NEXT_PUBLIC_BACKEND_BASE_URL=http://localhost:2026\nNEXT_PUBLIC_LANGGRAPH_BASE_URL=http://localhost:2026/api/langgraph\n",
            encoding="utf-8",
        )
        (tmp_path / ".env").write_text(
            "GATEWAY_CORS_ORIGINS=http://localhost:3000\n",
            encoding="utf-8",
        )

        result = doctor.check_local_direct_routing(tmp_path)

        assert result.status == "fail"
        assert result.fix is not None

    def test_profile_resolution_is_explicit(self, monkeypatch):
        monkeypatch.delenv("DEERFLOW_RUNTIME_PROFILE", raising=False)
        assert doctor.resolve_runtime_profile(None) == "local-direct"
        monkeypatch.setenv("DEERFLOW_RUNTIME_PROFILE", "local-proxy")
        assert doctor.resolve_runtime_profile(None) == "local-proxy"
        with pytest.raises(ValueError, match="runtime profile"):
            doctor.resolve_runtime_profile("mystery")

    def test_optional_capability_is_not_a_health_warning(self):
        result = doctor.as_optional_capability(doctor.CheckResult("web fetch configured", "warn", "not configured"))

        assert result.status == "skip"
        assert "optional" in result.detail


# ---------------------------------------------------------------------------
# check_sandbox
# ---------------------------------------------------------------------------


class TestCheckSandbox:
    def test_missing_sandbox_fails(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")
        results = doctor.check_sandbox(cfg)
        assert results[0].status == "fail"

    def test_local_sandbox_with_disabled_host_bash_warns(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nsandbox:\n  use: deerflow.sandbox.local:LocalSandboxProvider\n  allow_host_bash: false\ntools:\n  - name: bash\n    use: deerflow.sandbox.tools:bash_tool\n")
        results = doctor.check_sandbox(cfg)
        assert any(result.status == "warn" for result in results)

    def test_container_sandbox_without_runtime_warns(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nsandbox:\n  use: deerflow.community.aio_sandbox:AioSandboxProvider\ntools: []\n")
        monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
        results = doctor.check_sandbox(cfg)
        assert any(result.label == "container runtime available" and result.status == "warn" for result in results)


# ---------------------------------------------------------------------------
# IP Agent product checks
# ---------------------------------------------------------------------------


class TestIPAgentProductChecks:
    def test_source_bundle_fails_when_required_source_is_missing(self, tmp_path):
        result = doctor.check_ip_agent_source_bundle(tmp_path)
        assert result.status == "fail"
        assert "missing" in result.detail

    def test_source_bundle_accepts_complete_required_tree(self, tmp_path):
        for relative in doctor.IP_AGENT_REQUIRED_SOURCE_PATHS:
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("source", encoding="utf-8")

        result = doctor.check_ip_agent_source_bundle(tmp_path)

        assert result.status == "ok"
        assert str(len(doctor.IP_AGENT_REQUIRED_SOURCE_PATHS)) in result.detail

    def test_minecontext_doctor_reports_disabled_source_without_runtime_requirement(self, tmp_path, monkeypatch):
        config = tmp_path / "config.yaml"
        config.write_text("minecontext:\n  enabled: false\n", encoding="utf-8")
        monkeypatch.setattr(doctor, "_verify_minecontext_source", lambda _root: {"commit": "171c7a9"})

        results = doctor.check_minecontext(tmp_path, config)

        assert results[0].status == "ok"
        assert results[1].status == "ok"
        assert "disabled" in results[1].detail

    def test_minecontext_doctor_warns_when_enabled_runtime_or_credentials_missing(self, tmp_path, monkeypatch):
        config = tmp_path / "config.yaml"
        config.write_text("minecontext:\n  enabled: true\n", encoding="utf-8")
        monkeypatch.setattr(doctor, "_verify_minecontext_source", lambda _root: {"commit": "171c7a9"})
        for name in (
            "MINECONTEXT_VLM_BASE_URL",
            "MINECONTEXT_VLM_API_KEY",
            "MINECONTEXT_VLM_MODEL",
            "MINECONTEXT_EMBEDDING_BASE_URL",
            "MINECONTEXT_EMBEDDING_API_KEY",
            "MINECONTEXT_EMBEDDING_MODEL",
            "VOLCENGINE_API_KEY",
        ):
            monkeypatch.delenv(name, raising=False)

        results = doctor.check_minecontext(tmp_path, config)

        assert results[0].status == "ok"
        assert results[1].status == "warn"
        assert "minecontext-install" in (results[1].fix or "")
        assert results[2].status == "warn"
        assert "VOLCENGINE_API_KEY" in results[2].detail

    def test_minecontext_doctor_accepts_shared_volcengine_key(self, tmp_path, monkeypatch):
        config = tmp_path / "config.yaml"
        config.write_text("minecontext:\n  enabled: true\n", encoding="utf-8")
        runtime = tmp_path / ".deer-flow" / "toolchains" / "minecontext" / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")
        runtime.parent.mkdir(parents=True)
        runtime.write_text("fixture", encoding="utf-8")
        monkeypatch.setattr(doctor, "_verify_minecontext_source", lambda _root: {"commit": "171c7a9"})
        monkeypatch.setenv("VOLCENGINE_API_KEY", "secret")

        results = doctor.check_minecontext(tmp_path, config)

        assert [result.status for result in results] == ["ok", "ok", "ok"]

    def test_capability_manifest_requires_exact_eight_platforms(self, tmp_path):
        manifest = tmp_path / "product" / "volcengine" / "capabilities.yaml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            "capabilities:\n  platform_operations:\n    platforms:\n" + "".join(f"      - {platform}\n" for platform in sorted(doctor.IP_AGENT_PLATFORMS)),
            encoding="utf-8",
        )

        result = doctor.check_ip_agent_capability_manifest(tmp_path)

        assert result.status == "ok"
        assert "8" in result.detail

        manifest.write_text(
            "capabilities:\n  platform_operations:\n    platforms:\n      - douyin\n",
            encoding="utf-8",
        )
        result = doctor.check_ip_agent_capability_manifest(tmp_path)
        assert result.status == "fail"
        assert "wechat_channels" in result.detail

    def test_product_credentials_distinguish_optional_cloud_from_missing_generation(self, monkeypatch):
        for name in (
            "VOLCENGINE_API_KEY",
            "VOLCENGINE_TTS_API_KEY",
            "VOLCENGINE_TTS_APPID",
            "VOLCENGINE_TTS_ACCESS_TOKEN",
            "MEDIAKIT_API_KEY",
        ):
            monkeypatch.delenv(name, raising=False)

        results = doctor.check_volcengine_product_credentials()
        by_label = {result.label: result for result in results}

        assert by_label["Volcengine Ark generation"].status == "warn"
        assert by_label["Doubao Speech"].status == "warn"
        assert by_label["AI MediaKit cloud"].status == "ok"
        assert "optional" in by_label["AI MediaKit cloud"].detail

    def test_product_credentials_report_single_tts_key_without_values(self, monkeypatch):
        monkeypatch.setenv("VOLCENGINE_API_KEY", "secret-ark")
        monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", "secret-speech")
        monkeypatch.setenv("MEDIAKIT_API_KEY", "secret-media")

        results = doctor.check_volcengine_product_credentials()
        rendered = " ".join(result.detail for result in results)

        assert all(result.status == "ok" for result in results)
        assert "AppID is not required" in rendered
        assert "secret-" not in rendered

    def test_product_credentials_accept_legacy_tts_key_name_without_appid(self, monkeypatch):
        monkeypatch.delenv("VOLCENGINE_TTS_API_KEY", raising=False)
        monkeypatch.delenv("VOLCENGINE_TTS_APPID", raising=False)
        monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "secret-speech")

        results = doctor.check_volcengine_product_credentials()
        speech = next(result for result in results if result.label == "Doubao Speech")

        assert speech.status == "ok"
        assert "AppID is not required" in speech.detail

    def test_local_media_toolchain_prefers_project_binaries(self, tmp_path, monkeypatch):
        ffmpeg_dir = tmp_path / ".deer-flow" / "toolchains" / "ffmpeg" / "bin"
        ffmpeg_dir.mkdir(parents=True)
        (ffmpeg_dir / "ffmpeg").write_text("binary")
        (ffmpeg_dir / "ffprobe").write_text("binary")
        mediakit = tmp_path / ".deer-flow" / "bin" / "mediakit-cli"
        mediakit.parent.mkdir(parents=True)
        mediakit.write_text("binary")
        calls = []
        monkeypatch.setattr(doctor, "_run", lambda command: calls.append(command) or "tool version 1")

        results = doctor.check_local_media_toolchain(tmp_path)

        assert all(result.status == "ok" for result in results)
        assert calls[0][0] == str(ffmpeg_dir / "ffmpeg")
        assert calls[1][0] == str(mediakit)

    def test_chromium_runtime_reports_installed_and_missing(self, tmp_path, monkeypatch):
        executable = tmp_path / "chromium"
        executable.write_text("binary")
        monkeypatch.setattr(doctor, "_playwright_chromium_path", lambda: executable)
        assert doctor.check_chromium_runtime().status == "ok"

        monkeypatch.setattr(doctor, "_playwright_chromium_path", lambda: tmp_path / "missing")
        missing = doctor.check_chromium_runtime()
        assert missing.status == "warn"
        assert "playwright install chromium" in (missing.fix or "")

    def test_local_state_reports_agent_and_profile_count(self, tmp_path, monkeypatch):
        state = tmp_path / "state"
        agent = state / "users" / "user-1" / "agents" / "ip-agent" / "SOUL.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("agent")
        profile = state / "users" / "user-1" / "browser-profiles" / "account-1"
        profile.mkdir(parents=True)
        monkeypatch.setenv("DEER_FLOW_HOME", str(state))

        results = doctor.check_ip_agent_local_state(tmp_path)

        assert results[0].status == "ok"
        assert "1 user" in results[0].detail
        assert results[1].status == "ok"
        assert "1 persisted" in results[1].detail

    def test_local_state_warns_when_product_agent_is_stale(self, tmp_path, monkeypatch):
        product_agent = (
            tmp_path / "product" / "defaults" / "agents" / "ip-agent"
        )
        product_agent.mkdir(parents=True)
        (product_agent / "SOUL.md").write_text("current soul")
        (product_agent / "config.yaml").write_text("name: ip-agent")
        state = tmp_path / "state"
        installed = state / "users" / "user-1" / "agents" / "ip-agent"
        installed.mkdir(parents=True)
        (installed / "SOUL.md").write_text("old soul")
        (installed / "config.yaml").write_text("name: ip-agent")
        monkeypatch.setenv("DEER_FLOW_HOME", str(state))

        results = doctor.check_ip_agent_local_state(tmp_path)

        assert results[0].status == "warn"
        assert "1 stale" in results[0].detail
        assert "make ip-refresh" in (results[0].fix or "")

    def test_local_state_defaults_to_backend_runtime_home(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DEER_FLOW_HOME", raising=False)
        product_agent = (
            tmp_path / "product" / "defaults" / "agents" / "ip-agent"
        )
        product_agent.mkdir(parents=True)
        (product_agent / "SOUL.md").write_text("current soul")
        (product_agent / "config.yaml").write_text("name: ip-agent")
        installed = (
            tmp_path
            / "backend"
            / ".deer-flow"
            / "users"
            / "default"
            / "agents"
            / "ip-agent"
        )
        installed.mkdir(parents=True)
        (installed / "SOUL.md").write_text("current soul")
        (installed / "config.yaml").write_text("name: ip-agent")

        results = doctor.check_ip_agent_local_state(tmp_path)

        assert results[0].status == "ok"
        assert "1 user" in results[0].detail


# ---------------------------------------------------------------------------
# main() exit code
# ---------------------------------------------------------------------------


class TestMainExitCode:
    def test_returns_int(self, tmp_path, monkeypatch, capsys):
        """main() should return 0 or 1 without raising."""
        repo_root = tmp_path / "repo"
        scripts_dir = repo_root / "scripts"
        scripts_dir.mkdir(parents=True)
        fake_doctor = scripts_dir / "doctor.py"
        fake_doctor.write_text("# test-only shim for __file__ resolution\n")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(doctor, "__file__", str(fake_doctor))
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)

        exit_code = doctor.main()

        captured = capsys.readouterr()
        output = captured.out + captured.err

        assert exit_code in (0, 1)
        assert output
        assert "config.yaml" in output
        assert ".env" in output
