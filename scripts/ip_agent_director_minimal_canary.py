#!/usr/bin/env python3
"""Run one research-only IP director prompt directly against Ark Chat API."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seed-evolving-latest-version"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--thinking", choices=("enabled", "disabled"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--max-tokens", type=int, default=2500)
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser


def _read_text(path: Path) -> str:
    return path.resolve(strict=True).read_text(encoding="utf-8")


def _request(args: argparse.Namespace, api_key: str) -> tuple[dict[str, Any], float]:
    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": _read_text(args.system)},
            {"role": "user", "content": _read_text(args.input)},
        ],
        "stream": False,
        "temperature": 0,
        "max_tokens": args.max_tokens,
        "thinking": {"type": args.thinking},
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=args.timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body, time.monotonic() - started


def _result(args: argparse.Namespace, body: dict[str, Any], elapsed: float) -> dict[str, Any]:
    choices = body.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    content = message.get("content") or ""
    parsed: Any = None
    parse_error: str | None = None
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError) as exc:
        parse_error = f"{type(exc).__name__}: {exc}"

    return {
        "schema_version": "ip-director-minimal-canary-result-v1",
        "scope": "research_direct_provider_only",
        "product_capability": False,
        "request": {
            "model": args.model,
            "thinking": args.thinking,
            "max_tokens": args.max_tokens,
            "system_path": str(args.system),
            "input_path": str(args.input),
        },
        "response": {
            "id": body.get("id"),
            "actual_model": body.get("model"),
            "elapsed_seconds": round(elapsed, 3),
            "finish_reason": choice.get("finish_reason"),
            "usage": body.get("usage"),
            "json_parse_error": parse_error,
            "content": parsed if parse_error is None else content,
        },
    }


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env")
    api_key = os.environ.get("VOLCENGINE_API_KEY")
    if not api_key:
        raise SystemExit("VOLCENGINE_API_KEY is not configured")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing result: {args.output}")

    try:
        body, elapsed = _request(args, api_key)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Ark HTTP {exc.code}: {error_body[:1000]}") from exc

    result = _result(args, body, elapsed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "elapsed_seconds": result["response"]["elapsed_seconds"],
                "actual_model": result["response"]["actual_model"],
                "finish_reason": result["response"]["finish_reason"],
                "usage": result["response"]["usage"],
                "json_parse_error": result["response"]["json_parse_error"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
