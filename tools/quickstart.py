#!/usr/bin/env python3
"""Compatibility entry point for the renamed launcher import service."""

from __future__ import annotations

import sys

if __package__:
    from tools.launcher import import_cli
else:
    from launcher import import_cli


def main() -> int:
    print(
        "Note: Quickstart has moved to the University Schedule Planner Launcher "
        "(tools/launcher.py). Running its compatible archive importer.",
        file=sys.stderr,
    )
    return import_cli()


if __name__ == "__main__":
    raise SystemExit(main())
