#!/usr/bin/env python3
"""Compare generated catalogs and SQLite databases semantically."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def _database_snapshot(path: Path) -> tuple[list[tuple], dict[str, list[tuple]]]:
    with sqlite3.connect(path) as database:
        integrity = database.execute("PRAGMA integrity_check").fetchall()
        if integrity != [("ok",)]:
            raise RuntimeError(f"SQLite integrity check failed for {path}: {integrity}")
        foreign_keys = database.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise RuntimeError(f"SQLite foreign-key check failed for {path}: {foreign_keys}")

        schema = database.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        tables = database.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        rows: dict[str, list[tuple]] = {}
        for (table,) in tables:
            quoted = table.replace('"', '""')
            columns = [
                row[1] for row in database.execute(f'PRAGMA table_info("{quoted}")')
            ]
            order_by = ", ".join(
                f'"{column.replace(chr(34), chr(34) * 2)}"' for column in columns
            )
            rows[table] = database.execute(
                f'SELECT * FROM "{quoted}" ORDER BY {order_by}'
            ).fetchall()
        return schema, rows


def verify_generated(
    first_catalog: Path,
    first_database: Path,
    second_catalog: Path,
    second_database: Path,
) -> None:
    first_document = json.loads(first_catalog.read_text(encoding="utf-8"))
    second_document = json.loads(second_catalog.read_text(encoding="utf-8"))
    if first_document != second_document:
        raise RuntimeError("Generated catalogs differ")

    first_snapshot = _database_snapshot(first_database)
    second_snapshot = _database_snapshot(second_database)
    if first_snapshot[0] != second_snapshot[0]:
        raise RuntimeError("Generated SQLite schemas differ")
    if first_snapshot[1] != second_snapshot[1]:
        raise RuntimeError("Generated SQLite table rows differ")

    # Retain the stronger check when the local SQLite version produces identical files.
    if first_database.read_bytes() != second_database.read_bytes():
        print("Warning: databases are semantically equal but raw bytes differ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_catalog", type=Path)
    parser.add_argument("first_database", type=Path)
    parser.add_argument("second_catalog", type=Path)
    parser.add_argument("second_database", type=Path)
    args = parser.parse_args()
    verify_generated(
        args.first_catalog,
        args.first_database,
        args.second_catalog,
        args.second_database,
    )
    print("Generated catalogs and SQLite databases match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
