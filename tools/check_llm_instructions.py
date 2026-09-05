#!/usr/bin/env python3
"""Keep the LLM safety prompt authoritative and linked from the root README."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE_PATH = Path("template/university-template/LLM-SCRAPING-GUIDE.md")
REQUIRED_SAFETY_PARAGRAPH = (
    "Tell it to browse only official university sources, follow the output contract "
    "in the directions, and return a ZIP containing one completed university folder. "
    "Review its reported inaccessible pages and ambiguities before accepting the ZIP. "
    "Never provide credentials or ask it to bypass access controls."
)
REQUIRED_README_LINK = f"]({GUIDE_PATH.as_posix()})"
REQUIRED_PREREQUISITE_DIRECTIONS = (
    "**Mandatory prerequisite completeness pass:**",
    "recommended preparation, prior-coursework",
    "**Relationship reconciliation:**",
    "source course outside the requested collection scope must not be silently dropped",
    "**Complex logic:**",
    "mixed “prior or concurrent” rules",
    'annotate that relationship with `kind: "corequisite"`',
    "planner displays and evaluates both allowed timings",
    "**Pre-delivery prerequisite audit:**",
    "Keep an internal coverage ledger",
    "Report these five counts separately for every department",
    "edges with sources outside the collected dataset",
    "- Prerequisite coverage: PASS",
)


def instruction_errors(root: Path = ROOT) -> list[str]:
    """Return violations of the guide/README source-of-truth contract."""
    guide = (root / GUIDE_PATH).read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    normalized_guide = " ".join(guide.split())
    errors: list[str] = []

    if guide.count(REQUIRED_SAFETY_PARAGRAPH) != 1:
        errors.append("LLM guide must contain the required safety paragraph exactly once")
    if REQUIRED_README_LINK not in readme:
        errors.append("README must link to the authoritative LLM scraping guide")
    if REQUIRED_SAFETY_PARAGRAPH in readme:
        errors.append("README must link to, rather than duplicate, the safety paragraph")
    for direction in REQUIRED_PREREQUISITE_DIRECTIONS:
        if normalized_guide.count(direction) != 1:
            errors.append(
                f"LLM guide must contain prerequisite completeness direction exactly once: {direction!r}"
            )
    return errors


def main() -> int:
    errors = instruction_errors()
    if errors:
        print("LLM instruction check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("LLM instruction check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
