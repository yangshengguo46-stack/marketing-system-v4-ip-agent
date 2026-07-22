"""Loopback client for the optional UI-TARS operator process."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from deerflow.config.runtime_paths import runtime_home


class UITarsOperatorError(RuntimeError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


class UITarsOperatorClient:
    def __init__(self, endpoint: str, *, timeout_seconds: float, state_dir: Path | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.state_dir = state_dir or (runtime_home() / "ui-tars")

    def _token(self) -> str:
        environment_token = os.environ.get("UI_TARS_OPERATOR_TOKEN", "").strip()
        if len(environment_token) >= 32:
            return environment_token
        token_path = self.state_dir / "operator.token"
        try:
            token = token_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise UITarsOperatorError("not_started", "UI-TARS operator token is missing; start or connect the local operator") from exc
        if len(token) < 32:
            raise UITarsOperatorError("not_started", "UI-TARS operator token is invalid; restart the local operator")
        return token

    def _request(self, path: str, *, payload: dict[str, Any] | None, authenticated: bool) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if authenticated:
            headers["Authorization"] = f"Bearer {self._token()}"
        request = urllib.request.Request(
            f"{self.endpoint}{path}",
            data=body,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(1_048_577)
        except urllib.error.HTTPError as exc:
            category = "authorization" if exc.code in {401, 403} else "operator_rejected"
            raise UITarsOperatorError(category, f"UI-TARS operator rejected the request (HTTP {exc.code})") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UITarsOperatorError("unavailable", "UI-TARS operator is unavailable; run the UI-TARS doctor and start/connect it") from exc
        if len(raw) > 1_048_576:
            raise UITarsOperatorError("invalid_response", "UI-TARS operator response exceeded the safety limit")
        try:
            result = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise UITarsOperatorError("invalid_response", "UI-TARS operator returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise UITarsOperatorError("invalid_response", "UI-TARS operator returned an invalid response object")
        return result

    async def health(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._request, "/health", payload=None, authenticated=False)

    async def step(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._request, "/v1/step", payload=payload, authenticated=True)
