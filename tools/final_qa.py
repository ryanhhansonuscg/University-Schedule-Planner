#!/usr/bin/env python3
"""Run the repository's final, cross-cutting quality gate."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

from check_generated import verify_generated


ROOT = Path(__file__).resolve().parents[1]
REPRODUCIBLE_EPOCH = "1767225600"  # 2026-01-01T00:00:00+00:00
REQUIRED_PATHS = (
    ".github/workflows/ci.yml",
    "CONTRIBUTING.md",
    "README.md",
    "assets/app.js",
    "assets/loader.js",
    "assets/planner-core.js",
    "assets/planner.js",
    "assets/styles.css",
    "index.html",
    "planner.html",
    "schema.sql",
    "template/university-template/calendars.json",
    "template/university-template/departments/SAMPLE.json",
    "template/university-template/university.json",
    "universities/index.json",
    "tools/check_generated.py",
)
COMMANDS = (
    (sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"),
    ("npm", "test"),
    (sys.executable, "-m", "compileall", "-q", "tools", "tests"),
    ("npm", "run", "check"),
    (sys.executable, "tools/check_prohibited_terms.py"),
    (sys.executable, "tools/validate_university.py", "--template", "template/university-template"),
)


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for name in ("href", "src"):
            value = values.get(name)
            if value and not value.startswith(("#", "data:", "http://", "https://")):
                self.references.append(value.split("?", 1)[0])


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ("git", "ls-files", "-z"), cwd=ROOT, check=True, capture_output=True
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def structural_errors(files: list[Path]) -> list[str]:
    errors = [f"Missing required repository element: {path}" for path in REQUIRED_PATHS if not (ROOT / path).is_file()]
    markers = ("<" * 7, "=" * 7, ">" * 7)
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if line.startswith(markers):
                errors.append(f"Unresolved merge marker: {path.relative_to(ROOT)}:{number}")
        if path.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as error:
                errors.append(f"Invalid JSON: {path.relative_to(ROOT)}:{error.lineno}:{error.colno}: {error.msg}")
    for name in ("index.html", "planner.html"):
        page = ROOT / name
        if not page.is_file():
            continue
        parser = AssetParser()
        parser.feed(page.read_text(encoding="utf-8"))
        for reference in parser.references:
            if not (page.parent / reference).is_file():
                errors.append(f"Missing local asset referenced by {name}: {reference}")
    return errors


def verify_reproducible_fixture() -> None:
    source = ROOT / "template" / "university-template"
    with tempfile.TemporaryDirectory() as temporary:
        fixture = Path(temporary) / "fictional-template-university"
        shutil.copytree(source, fixture)
        environment = {**os.environ, "SOURCE_DATE_EPOCH": REPRODUCIBLE_EPOCH}
        command = (sys.executable, str(ROOT / "tools/build_university.py"), str(fixture))
        subprocess.run(command, check=True, env=environment)
        first_catalog = Path(temporary) / "first.json"
        first_database = Path(temporary) / "first.db"
        shutil.copy2(fixture / "catalog.json", first_catalog)
        shutil.copy2(fixture / "courses.db", first_database)
        subprocess.run(command, check=True, env=environment)
        verify_generated(
            first_catalog, first_database,
            fixture / "catalog.json", fixture / "courses.db",
        )


def main() -> int:
    errors = structural_errors(tracked_files())
    if errors:
        print("Final QA structural checks failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    for command in COMMANDS:
        print(f"\n==> {' '.join(command)}", flush=True)
        subprocess.run(command, cwd=ROOT, check=True)
    print("\n==> reproducible template build and SQLite checks", flush=True)
    verify_reproducible_fixture()
    print("\nFinal QA passed: required elements, references, JSON, merge state, tests, and generated artifacts are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
