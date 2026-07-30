#!/usr/bin/env python3
"""Query the SQLite library packaged with this skill."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = SKILL_DIR / "assets" / "cinema_library.sqlite"
TABLES = {
    "film": ("films", ["title", "directors", "writers", "craft_lenses"]),
    "creator": ("creators", ["name", "roles", "works", "mechanisms"]),
    "card": (
        "mechanism_cards",
        ["subject", "domain", "mechanism", "evidence_label"],
    ),
}


def search(
    connection: sqlite3.Connection,
    kind: str,
    query: str,
    limit: int,
    evidence: str | None,
) -> list[dict[str, Any]]:
    table, fields = TABLES[kind]
    clauses = ["(" + " OR ".join(f"{field} LIKE ?" for field in fields) + ")"]
    parameters: list[Any] = [f"%{query}%" for _ in fields]
    if evidence and kind == "card":
        clauses.append("evidence_label = ?")
        parameters.append(evidence)
    parameters.append(limit)
    sql = f"SELECT record_json FROM {table} WHERE {' AND '.join(clauses)} ORDER BY {fields[0]} COLLATE NOCASE LIMIT ?"
    return [
        json.loads(row[0]) for row in connection.execute(sql, parameters).fetchall()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--type", choices=["all", *TABLES], default="all")
    parser.add_argument("--evidence")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    if not args.db.exists():
        parser.error(f"Packaged database is missing: {args.db}")
    if not 1 <= args.limit <= 200:
        parser.error("--limit must be 1–200")
    connection = sqlite3.connect(args.db)
    try:
        kinds = TABLES if args.type == "all" else {args.type: TABLES[args.type]}
        result = {
            kind: search(connection, kind, args.query, args.limit, args.evidence)
            for kind in kinds
        }
    finally:
        connection.close()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for kind, records in result.items():
            print(f"[{kind}] {len(records)}")
            for record in records:
                if kind == "film":
                    print(f"- {record['title']} ({record['year']})")
                elif kind == "creator":
                    print(f"- {record['name']} — {', '.join(record['roles'])}")
                else:
                    print(
                        f"- {record['subject']} / {record['domain']} [{record['evidence_label']}]: {record['mechanism']}"
                    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
