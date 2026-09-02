#!/usr/bin/env python3
"""Fail when removed institution-specific branding returns to repository files."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIPPED_PARTS = {".git", "__pycache__"}

# Keep the terms split so this check does not exempt itself from its own scan.
PROHIBITED = (
    re.compile(r"\bU" + r"MD\b", re.IGNORECASE),
    re.compile(r"University of Mary" + r"land", re.IGNORECASE),
    re.compile(r"Mary" + r"land", re.IGNORECASE),
    re.compile(r"Ter" + r"ps", re.IGNORECASE),
    re.compile(r"u" + r"md\.edu", re.IGNORECASE),
    re.compile(r"ter" + r"\.ps", re.IGNORECASE),
    re.compile(r"#?e2" + r"1833", re.IGNORECASE),
    re.compile(r"#?ff" + r"d200", re.IGNORECASE),
)


def violations(root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or SKIPPED_PARTS.intersection(path.parts):
            continue
        try:
            contents = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(contents.splitlines(), 1):
            if any(pattern.search(line) for pattern in PROHIBITED):
                findings.append(f"{path.relative_to(root)}:{line_number}: {line.strip()}")
    return findings


def main() -> int:
    findings = violations()
    if findings:
        print("Prohibited institution-specific content found:")
        print("\n".join(findings))
        return 1
    print("No prohibited institution-specific content found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
