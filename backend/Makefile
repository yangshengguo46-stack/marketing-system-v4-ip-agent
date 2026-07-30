install:
	uv sync

dev:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python -m uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 --reload

gateway:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python -m uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001

test:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python -m pytest tests/ -v

test-blocking-io:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python -m pytest tests/blocking_io -q --tb=short

personal-ip-publish-acceptance:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python -m pytest tests/test_personal_ip_browser_publishing.py tests/test_personal_ip_publish_receipt_repository.py tests/test_personal_ip_publish_receipt_router.py tests/test_personal_ip_publish_recovery_e2e.py tests/test_personal_ip_workflow_tools.py -q --tb=short

personal-ip-cost-acceptance:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python -m pytest tests/test_personal_ip_video_budget.py tests/test_personal_ip_video_production_repository.py tests/test_personal_ip_tools.py tests/test_media_executor_script.py -q --tb=short

personal-ip-data-lifecycle-acceptance:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python -m pytest tests/test_personal_ip_data_lifecycle.py tests/test_personal_ip_data_lifecycle_router.py tests/test_personal_ip_platform_connection_repository.py -q --tb=short

personal-ip-observability-acceptance:
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python -m pytest tests/test_doctor.py tests/test_personal_ip_operating_cockpit.py tests/test_personal_ip_video_budget.py -q --tb=short

lint:
	uvx ruff check .
	uvx ruff format --check .

format:
	uvx ruff check . --fix && uvx ruff format .

detect-blocking-io:
	@PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python ../scripts/detect_blocking_io_static.py --output ../.deer-flow/blocking-io-findings.json

# Generate a new alembic revision by autogenerating the diff against the live
# ORM models. Usage: make migrate-rev MSG="add foo column to runs"
# The Gateway runs `alembic upgrade head` automatically at startup via
# `bootstrap_schema`, so there is intentionally no `migrate` / `migrate-stamp`
# target -- the single execution path keeps ops mistakes off the table.
# The script builds a fresh temp SQLite at head, then diffs the live models
# against it, so a clean checkout does NOT need a pre-existing ./data/deerflow.db.
migrate-rev:
	@if [ -z "$(MSG)" ]; then echo 'usage: make migrate-rev MSG="describe the change"'; exit 1; fi
	PYTHONPATH=. PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python scripts/_autogen_revision.py "$(MSG)"
