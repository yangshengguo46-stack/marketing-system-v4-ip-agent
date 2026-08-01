# DeerFlow - Unified Development Environment

.PHONY: help config config-upgrade check install setup doctor support-bundle detect-thread-boundaries detect-blocking-io dev dev-direct dev-daemon start start-daemon nginx stop up down clean docker-init docker-start docker-stop docker-logs docker-logs-frontend docker-logs-gateway docker-logs-redis ip-init ip-refresh ip-package ip-package-verify ip-clean-install ip-test-prepare ip-test-start ip-test-reset ip-test-status ip-test-stop ip-test-evidence-reset ip-test-evidence-start ip-test-evidence-login ip-m2-prepare ip-m2-run personal-ip-publish-acceptance personal-ip-cost-acceptance personal-ip-data-lifecycle-acceptance personal-ip-observability-acceptance video-e2e-local video-e2e-paid-checkpoints video-renderers-install video-renderers-verify volcengine-install volcengine-doctor hllm-doctor ui-tars-install ui-tars-start ui-tars-stop ui-tars-status ui-tars-doctor minecontext-verify minecontext-install minecontext-doctor douyin-metrics-smoke ffmpeg-toolchain mediakit-toolchain mediakit-build mediakit-test

BASH ?= bash
PNPM ?= pnpm
BACKEND_UV_RUN = cd backend && uv run
IP_TEST_RUN = cd backend && PYTHONPATH=.. uv run python -m scripts.ip_agent_test_mode
IP_M2_RUN = cd backend && PYTHONPATH=.. uv run python -m scripts.ip_agent_m2_replay
VIDEO_E2E_DIR ?= .deer-flow/acceptance/video-e2e
VIDEO_E2E_FINISHER ?= auto

# Detect OS for Windows compatibility
ifeq ($(OS),Windows_NT)
    SHELL := cmd.exe
    PYTHON ?= python
    # Run repo shell scripts through Git Bash when Make is launched from cmd.exe / PowerShell.
    RUN_WITH_GIT_BASH = call scripts\run-with-git-bash.cmd
else
    PYTHON ?= python3
    RUN_WITH_GIT_BASH =
endif

help:
	@echo "DeerFlow Development Commands:"
	@echo "  make setup           - Interactive setup wizard (recommended for new users)"
	@echo "  make ip-init         - Install the default local personal-IP Agent"
	@echo "  make ip-package      - Build and smoke-test the complete source archive"
	@echo "  make ip-package-verify PACKAGE=... - Verify an existing source archive"
	@echo "  make ip-test-start   - Start the isolated local IP-Agent test environment"
	@echo "  make ip-test-reset   - Rotate test state to a recoverable snapshot and prepare a clean state"
	@echo "  make ip-test-status  - Show the isolated test-state paths and readiness"
	@echo "  make ip-test-stop    - Stop the local test environment"
	@echo "  make ip-test-evidence-reset - Reset into the isolated two-tool Evidence MCP profile"
	@echo "  make ip-test-evidence-login - Open the dedicated Douyin login profile"
	@echo "  make ip-test-evidence-start - Start the two-tool Evidence MCP test profile"
	@echo "  make ip-m2-prepare    - Validate the isolated four-group M2 comparison matrix"
	@echo "  make ip-m2-run        - Run locked Doubao M2 groups with controlled-exit config restore"
	@echo "  make personal-ip-publish-acceptance - Run local-only eight-platform publish recovery checks"
	@echo "  make personal-ip-cost-acceptance - Run video hard-budget reservation/retry/concurrency checks"
	@echo "  make personal-ip-data-lifecycle-acceptance - Verify credential-safe backup, restore and whole-domain deletion"
	@echo "  make personal-ip-observability-acceptance - Verify runtime profiles and sanitized operating alerts"
	@echo "  make video-e2e-local - Run/resume the free local video delivery acceptance"
	@echo "  make video-e2e-paid-checkpoints - Write paid media commands without running them"
	@echo "  make video-renderers-install - Install exact source-owned HyperFrames dependencies"
	@echo "  make video-renderers-verify - Verify renderer source, lock and installed versions"
	@echo "  make ip-clean-install - Validate the source archive in a credential-free clean room"
	@echo "  make volcengine-install - Build the pinned AI MediaKit CLI from source"
	@echo "  make volcengine-doctor  - Check the source-built AI MediaKit CLI"
	@echo "  make hllm-doctor        - Verify the quarantined HLLM research source"
	@echo "  make ui-tars-install    - Verify/register the pinned source-only UI-TARS organ"
	@echo "  make ui-tars-start      - Start or connect the optional local UI-TARS operator"
	@echo "  make ui-tars-stop       - Stop the managed local UI-TARS operator"
	@echo "  make ui-tars-status     - Show sanitized UI-TARS lifecycle and health status"
	@echo "  make ui-tars-doctor     - Check source, config, connection and desktop permissions"
	@echo "  make minecontext-verify - Verify pinned Apache-2.0 MineContext source"
	@echo "  make minecontext-install - Reinstall the bundled runtime from vendored source"
	@echo "  make minecontext-doctor - Verify source/runtime and provider readiness"
	@echo "  make douyin-metrics-smoke - Query authorized Douyin video metrics"
	@echo "  make ffmpeg-toolchain   - Build pinned project-local FFmpeg with subtitles"
	@echo "  make mediakit-toolchain - Install a pinned project-local Go toolchain"
	@echo "  make mediakit-test      - Run the vendored MediaKit Go tests"
	@echo "  make doctor          - Check configuration and system requirements"
	@echo "  make support-bundle  - Create a redacted issue summary, AI draft, and evidence bundle"
	@echo "  make config          - Generate local config files (aborts if config already exists)"
	@echo "  make config-upgrade  - Merge new fields from config.example.yaml into config.yaml"
	@echo "  make check           - Check if all required tools are installed"
	@echo "  make detect-thread-boundaries - Inventory async/thread boundary points"
	@echo "  make detect-blocking-io        - Inventory blocking IO that may block the backend event loop"
	@echo "  make install         - Install dependencies (Git checkouts also get pre-commit hooks)"
	@echo "  make setup-sandbox   - Pre-pull sandbox container image (recommended)"
	@echo "  make dev             - Start all services in development mode (with hot-reloading)"
	@echo "  make dev-direct      - Start local frontend + Gateway without host nginx"
	@echo "  make dev-daemon      - Start dev services in background (daemon mode)"
	@echo "  make start           - Start all services in production mode (optimized, no hot-reloading)"
	@echo "  make start-daemon    - Start prod services in background (daemon mode)"
	@echo "  make nginx           - Start nginx alone in the foreground (local dev config)"
	@echo "  make stop            - Stop all running services"
	@echo "  make clean           - Clean up processes and temporary files"
	@echo ""
	@echo "Docker Production Commands:"
	@echo "  make up              - Build and start production Docker services (localhost:2026)"
	@echo "  make down            - Stop and remove production Docker containers"
	@echo ""
	@echo "Docker Development Commands:"
	@echo "  make docker-init     - Pull the sandbox image"
	@echo "  make docker-start    - Start Docker services (mode-aware from config.yaml, localhost:2026)"
	@echo "  make docker-stop     - Stop Docker development services"
	@echo "  make docker-logs     - View Docker development logs"
	@echo "  make docker-logs-frontend - View Docker frontend logs"
	@echo "  make docker-logs-gateway - View Docker gateway logs"
	@echo "  make docker-logs-redis - View Docker Redis logs"

## Setup & Diagnosis
setup:
	@$(BACKEND_UV_RUN) python ../scripts/setup_wizard.py

ip-init:
	@$(PYTHON) ./scripts/init_ip_agent.py

ip-refresh:
	@$(PYTHON) ./scripts/init_ip_agent.py --refresh-product-agent

ip-package:
	@$(PYTHON) ./scripts/package_ip_agent.py build --smoke

ip-package-verify:
	@test -n "$(PACKAGE)" || (echo "Set PACKAGE=/path/to/ip-agent-source-*.tar.gz" && exit 2)
	@$(PYTHON) ./scripts/package_ip_agent.py verify "$(PACKAGE)" --smoke

ip-test-prepare:
	@$(IP_TEST_RUN) prepare

ip-test-start:
	@$(IP_TEST_RUN) start

ip-test-reset:
	@$(IP_TEST_RUN) reset

ip-test-status:
	@$(IP_TEST_RUN) status

ip-test-stop:
	@$(IP_TEST_RUN) stop

ip-test-evidence-reset:
	@$(IP_TEST_RUN) reset --profile evidence

ip-test-evidence-login:
	@$(IP_TEST_RUN) login-douyin --profile evidence

ip-test-evidence-start:
	@$(IP_TEST_RUN) start --profile evidence

ip-m2-prepare:
	@$(IP_M2_RUN) prepare

ip-m2-run:
	@$(IP_M2_RUN) run

personal-ip-publish-acceptance:
	@$(MAKE) -C backend personal-ip-publish-acceptance

personal-ip-cost-acceptance:
	@$(MAKE) -C backend personal-ip-cost-acceptance

personal-ip-data-lifecycle-acceptance:
	@$(MAKE) -C backend personal-ip-data-lifecycle-acceptance
	@cd frontend && $(PNPM) exec rstest tests/unit/core/personal-ip-data-lifecycle.test.ts

personal-ip-observability-acceptance:
	@$(MAKE) -C backend personal-ip-observability-acceptance
	@cd frontend && $(PNPM) exec rstest run tests/unit/core/personal-ip-dashboard.test.ts
	@cd frontend && $(PNPM) check

video-e2e-local:
	@$(BACKEND_UV_RUN) python ../scripts/personal_ip_video_e2e.py local --work-dir "$(abspath $(VIDEO_E2E_DIR))" --finisher "$(VIDEO_E2E_FINISHER)"

video-e2e-paid-checkpoints:
	@$(BACKEND_UV_RUN) python ../scripts/personal_ip_video_e2e.py paid-checkpoints --work-dir "$(abspath $(VIDEO_E2E_DIR))"

video-renderers-install:
	@$(PYTHON) ./scripts/install_video_renderers.py

video-renderers-verify:
	@node ./product/video-renderers/verify-pins.mjs

ip-clean-install:
	@$(PYTHON) ./scripts/clean_install_ip_agent.py

volcengine-install: ffmpeg-toolchain mediakit-toolchain
	@$(PYTHON) ./scripts/mediakit_source.py build

volcengine-doctor:
	@$(PYTHON) ./scripts/mediakit_source.py doctor

hllm-doctor:
	@$(PYTHON) ./scripts/hllm_creator_source.py

ui-tars-install:
	@$(BACKEND_UV_RUN) python ../scripts/ui_tars_operator.py install

ui-tars-start:
	@$(BACKEND_UV_RUN) python ../scripts/ui_tars_operator.py start

ui-tars-stop:
	@$(BACKEND_UV_RUN) python ../scripts/ui_tars_operator.py stop

ui-tars-status:
	@$(BACKEND_UV_RUN) python ../scripts/ui_tars_operator.py status

ui-tars-doctor:
	@$(BACKEND_UV_RUN) python ../scripts/ui_tars_operator.py doctor

minecontext-verify:
	@$(PYTHON) ./scripts/minecontext_source.py verify

minecontext-install:
	@$(PYTHON) ./scripts/minecontext_source.py install

minecontext-doctor:
	@$(PYTHON) ./scripts/minecontext_source.py doctor

douyin-metrics-smoke:
	@$(BACKEND_UV_RUN) python ../scripts/douyin_metrics_smoke.py

mediakit-toolchain:
	@$(PYTHON) ./scripts/install_go_toolchain.py

ffmpeg-toolchain:
	@$(PYTHON) ./scripts/install_ffmpeg_toolchain.py

mediakit-build:
	@$(PYTHON) ./scripts/mediakit_source.py build

mediakit-test:
	@$(PYTHON) ./scripts/mediakit_source.py test

doctor:
	@$(BACKEND_UV_RUN) python ../scripts/doctor.py --profile $(or $(PROFILE),auto)

support-bundle:
	@$(BACKEND_UV_RUN) python ../scripts/support_bundle.py --include-doctor

detect-thread-boundaries:
	@$(PYTHON) ./scripts/detect_thread_boundaries.py

detect-blocking-io:
	@$(MAKE) -C backend detect-blocking-io

config:
	@$(PYTHON) ./scripts/configure.py

config-upgrade:
	@$(RUN_WITH_GIT_BASH) ./scripts/config-upgrade.sh

# Check required tools
check:
	@$(PYTHON) ./scripts/check.py

# Install all dependencies
install:
	@echo "Installing backend dependencies..."
	@cd backend && uv sync
	@echo "Installing bundled MineContext runtime..."
	@$(PYTHON) ./scripts/minecontext_source.py install
	@echo "Installing frontend dependencies..."
	@cd frontend && $(PNPM) install
	@echo "Installing repository-only developer hooks..."
	@$(PYTHON) ./scripts/install_dev_hooks.py
	@echo "✓ All dependencies and local context runtime installed"
	@echo ""
	@echo "=========================================="
	@echo "  Optional: Pre-pull Sandbox Image"
	@echo "=========================================="
	@echo ""
	@echo "If you plan to use Docker/Container-based sandbox, you can pre-pull the image:"
	@echo "  make setup-sandbox"
	@echo ""

# Pre-pull sandbox Docker image (optional but recommended)
setup-sandbox:
	@$(RUN_WITH_GIT_BASH) ./scripts/setup-sandbox.sh

# Start all services in development mode (with hot-reloading)
dev:
	@$(PYTHON) ./scripts/check.py
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --dev

# Start the supported local direct profile without requiring host nginx
dev-direct:
	@$(MAKE) doctor PROFILE=local-direct
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --dev --no-nginx

# Start all services in production mode (with optimizations)
start:
	@$(PYTHON) ./scripts/check.py
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --prod

# Start all services in daemon mode (background)
dev-daemon:
	@$(PYTHON) ./scripts/check.py
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --dev --daemon

# Start prod services in daemon mode (background)
start-daemon:
	@$(PYTHON) ./scripts/check.py
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --prod --daemon

# Start nginx alone in the foreground with the local dev config
nginx:
	@$(RUN_WITH_GIT_BASH) ./scripts/nginx.sh

# Stop all services
stop:
	@$(RUN_WITH_GIT_BASH) ./scripts/serve.sh --stop

# Clean up
clean: stop
	@echo "Cleaning up..."
	@-rm -rf backend/.deer-flow 2>/dev/null || true
	@-rm -rf logs/*.log 2>/dev/null || true
	@echo "✓ Cleanup complete"

# ==========================================
# Docker Development Commands
# ==========================================

# Initialize Docker containers and install dependencies
docker-init:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh init

# Start Docker development environment
docker-start:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh start

# Stop Docker development environment
docker-stop:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh stop

# View Docker development logs
docker-logs:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh logs

# View Docker development logs
docker-logs-frontend:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh logs --frontend
docker-logs-gateway:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh logs --gateway
docker-logs-redis:
	@$(RUN_WITH_GIT_BASH) ./scripts/docker.sh logs --redis

# ==========================================
# Production Docker Commands
# ==========================================

# Build and start production services
up:
	@$(RUN_WITH_GIT_BASH) ./scripts/deploy.sh

# Stop and remove production containers
down:
	@$(RUN_WITH_GIT_BASH) ./scripts/deploy.sh down
