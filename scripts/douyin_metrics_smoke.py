#!/usr/bin/env python3
"""Call Douyin's official video-query endpoint without printing credentials."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict

from deerflow.personal_ip.platform_metrics import DouyinVideoMetricCollector, PlatformMetricCollectionError


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test authorized Douyin public-video metrics")
    parser.add_argument("--item-id", action="append", dest="item_ids", help="Authorized Douyin item_id; repeat for more than one")
    return parser.parse_args()


async def _run(item_ids: list[str]) -> int:
    access_token = os.getenv("DOUYIN_ACCESS_TOKEN", "").strip()
    open_id = os.getenv("DOUYIN_OPEN_ID", "").strip()
    if not access_token or not open_id:
        print("DOUYIN_ACCESS_TOKEN and DOUYIN_OPEN_ID are required", file=sys.stderr)
        return 2
    try:
        snapshots = await DouyinVideoMetricCollector(access_token=access_token, open_id=open_id).collect_video_snapshots(item_ids)
    except PlatformMetricCollectionError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "category": exc.category,
                    "retryable": exc.retryable,
                    "provider_code": exc.provider_code,
                    "provider_log_id": exc.provider_log_id,
                    "message": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    payload = []
    for snapshot in snapshots:
        value = asdict(snapshot)
        value["observed_at"] = snapshot.observed_at.isoformat()
        payload.append(value)
    print(json.dumps({"ok": True, "snapshots": payload}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main() -> int:
    args = _arguments()
    item_ids = list(args.item_ids or [])
    env_item_id = os.getenv("DOUYIN_ITEM_ID", "").strip()
    if env_item_id and not item_ids:
        item_ids = [env_item_id]
    if not item_ids:
        print("Pass --item-id or set DOUYIN_ITEM_ID", file=sys.stderr)
        return 2
    return asyncio.run(_run(item_ids))


if __name__ == "__main__":
    raise SystemExit(main())
