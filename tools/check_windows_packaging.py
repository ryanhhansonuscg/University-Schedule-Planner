#!/usr/bin/env python3
"""Statically check the Windows executable packaging contract."""

from __future__ import annotations

import ast
from pathlib import Path

from build_release import RELEASE_FILES


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    spec = ROOT / "packaging" / "windows.spec"
    workflow = ROOT / ".github" / "workflows" / "windows-exe.yml"
    ast.parse(spec.read_text(encoding="utf-8"), filename=str(spec))
    text = spec.read_text(encoding="utf-8")
    if 'namespace["RELEASE_FILES"]' not in text or 'contents_directory="."' not in text:
        raise RuntimeError("Windows spec must use RELEASE_FILES and keep resources beside the executable")
    missing = [name for name in RELEASE_FILES if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError(f"Windows packaging inputs are missing: {', '.join(missing)}")
    workflow_text = workflow.read_text(encoding="utf-8")
    required = ("workflow_dispatch:", "contents: write", "windows-latest", "packaging/windows.spec",
                "gh release view", "gh release upload", "Get-FileHash")
    absent = [token for token in required if token not in workflow_text]
    if absent:
        raise RuntimeError(f"Windows workflow is missing required steps: {', '.join(absent)}")
    print(f"Windows packaging contract passed ({len(RELEASE_FILES)} runtime files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
