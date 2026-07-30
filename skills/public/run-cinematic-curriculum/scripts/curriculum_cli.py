#!/usr/bin/env python3
"""Inspect and schedule the cinematic-IP curriculum without writing project state."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRICULUM_CANDIDATES = (
    ROOT / "curriculum" / "curriculum.json",
    ROOT / "references" / "curriculum.json",
)
DEFAULT_CURRICULUM = next(
    (path for path in CURRICULUM_CANDIDATES if path.exists()),
    CURRICULUM_CANDIDATES[0],
)


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Curriculum is missing: {path}. Run build_curriculum.py.")
    return json.loads(path.read_text(encoding="utf-8"))


def track_by_id(data: dict[str, Any], track_id: str) -> dict[str, Any]:
    for track in data["tracks"]:
        if track["track_id"] == track_id:
            return track
    choices = ", ".join(track["track_id"] for track in data["tracks"])
    raise SystemExit(f"Unknown track {track_id!r}. Choose: {choices}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curriculum", type=Path, default=DEFAULT_CURRICULUM)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List all tracks.")

    show = subparsers.add_parser("show", help="Show one module.")
    show.add_argument("--track", required=True)
    show.add_argument("--week", required=True, type=int)

    plan = subparsers.add_parser("plan", help="Create a dated study plan.")
    plan.add_argument("--track", action="append", required=True)
    plan.add_argument("--start", type=date.fromisoformat, default=date.today())
    plan.add_argument("--sessions-per-week", type=int, choices=[1, 2, 3], default=1)

    assessment = subparsers.add_parser("assessment-template")
    assessment.add_argument("--track", required=True)
    assessment.add_argument("--week", required=True, type=int)

    args = parser.parse_args()
    data = load(args.curriculum)

    if args.command == "list":
        print(
            json.dumps(
                [
                    {
                        "track_id": track["track_id"],
                        "name_zh": track["name_zh"],
                        "goal": track["goal"],
                        "modules": len(track["modules"]),
                    }
                    for track in data["tracks"]
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command in {"show", "assessment-template"}:
        track = track_by_id(data, args.track)
        if not 1 <= args.week <= len(track["modules"]):
            raise SystemExit(f"Week must be 1–{len(track['modules'])}")
        module = track["modules"][args.week - 1]
        if args.command == "show":
            print(json.dumps(module, ensure_ascii=False, indent=2))
        elif args.command == "assessment-template":
            print(
                json.dumps(
                    {
                        "module_id": module["module_id"],
                        "artifact": module["deliverable"],
                        "evidence_required": "作品中的页码、时间码、版本差异或拍摄记录。",
                        "scores": {
                            dimension: None
                            for dimension in module["assessment_dimensions"]
                        },
                        "scale": data["design"]["score_scale"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0

    plans = []
    session_index = 0
    for week in range(1, 13):
        for track_id in args.track:
            track = track_by_id(data, track_id)
            module = track["modules"][week - 1]
            session_day = args.start + timedelta(
                days=(session_index * 7) // args.sessions_per_week
            )
            plans.append(
                {
                    "date": session_day.isoformat(),
                    "track_id": track_id,
                    "module_id": module["module_id"],
                    "title": module["title"],
                    "exercise": module["exercise"],
                    "deliverable": module["deliverable"],
                }
            )
            session_index += 1
    print(json.dumps(plans, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
