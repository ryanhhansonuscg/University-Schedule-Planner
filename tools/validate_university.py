#!/usr/bin/env python3
"""Validate a university source folder without changing generated files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from build_university import DataError, build


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("university_dir", type=Path)
    args = parser.parse_args()
    try:
        catalog = build(args.university_dir, validate_only=True)
    except DataError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Valid: {catalog['university']['name']} ({len(catalog['departments'])} departments, {len(catalog['courses'])} courses)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
