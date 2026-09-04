#!/usr/bin/env python3
"""Run the repository's final, cross-cutting quality gate."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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
)
COMMANDS = (
    (sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"),
    ("npm", "test"),
    (sys.executable, "-m", "compileall", "-q", "tools", "tests"),
    ("npm", "run", "check"),
    (sys.executable, "tools/check_prohibited_terms.py"),
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
        subprocess.run((sys.executable, str(ROOT / "tools/build_university.py"), str(fixture)), check=True)
        first_catalog = json.loads((fixture / "catalog.json").read_text(encoding="utf-8"))
        first_database = (fixture / "courses.db").read_bytes()
        subprocess.run((sys.executable, str(ROOT / "tools/build_university.py"), str(fixture)), check=True)
        second_catalog = json.loads((fixture / "catalog.json").read_text(encoding="utf-8"))
        first_catalog.pop("generated_at", None)
        second_catalog.pop("generated_at", None)
        if first_catalog != second_catalog:
            raise RuntimeError("Template catalog rebuild is not semantically reproducible")
        if first_database != (fixture / "courses.db").read_bytes():
            raise RuntimeError("Template SQLite rebuild is not byte-for-byte reproducible")
        with sqlite3.connect(fixture / "courses.db") as database:
            if database.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise RuntimeError("Template SQLite integrity check failed")
            if database.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Template SQLite foreign-key check failed")


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
