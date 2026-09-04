#!/usr/bin/env python3
"""Run the repository's final, cross-cutting quality gate."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from check_generated import verify_generated


ROOT = Path(__file__).resolve().parents[1]
REPRODUCIBLE_EPOCH = "1767225600"  # 2026-01-01T00:00:00+00:00
REQUIRED_PATHS = (
    ".gitattributes",
    ".github/workflows/ci.yml",
    ".gitignore",
    ".nojekyll",
    "CONTRIBUTING.md",
    "README.md",
    "assets/app.js",
    "assets/loader.js",
    "assets/planner-core.js",
    "assets/planner.js",
    "assets/styles.css",
    "index.html",
    "package-lock.json",
    "package.json",
    "planner.html",
    "schedule-import-template.csv",
    "schema.sql",
    "template/university-template/LLM-SCRAPING-GUIDE.md",
    "template/university-template/README.md",
    "template/university-template/calendars.json",
    "template/university-template/departments/SAMPLE.json",
    "template/university-template/university.json",
    "tools/check_generated.py",
    "tools/build_standalone.py",
    "tools/build_release.py",
    "universities/README.md",
    "universities/index.json",
)

# Keep the independently useful test layers visible in CI output. In particular,
# do not hide template slug validation or accessibility checks in a broad suite.
CATEGORIES = (
    ("Python repository and build tests", (sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")),
    ("CSV and planner-core tests", ("node", "--test", "tests/planner-core.test.js")),
    ("Storage-failure and planner tests", ("node", "--test", "tests/planner.test.js")),
    ("Progressive-compatibility and browser tests", ("node", "--test", "tests/app.test.js", "tests/styles.test.js")),
    ("Accessibility and semantic-markup tests", ("node", "--test", "tests/semantic-markup-smoke.test.js")),
    ("Python syntax checks", (sys.executable, "-m", "compileall", "-q", "tools", "tests")),
    ("JavaScript syntax checks", ("npm", "run", "check")),
    ("Institution-neutral content checks", (sys.executable, "tools/check_prohibited_terms.py")),
    ("Canonical template validation", (sys.executable, "tools/validate_university.py", "--template", "template/university-template")),
)

CSS_REFERENCE = re.compile(
    r"url\(\s*(['\"]?)(?P<url>[^)'\"\s]+)\1\s*\)|"
    r"@import\s+(?:url\(\s*)?['\"](?P<import>[^'\"]+)['\"]",
    re.IGNORECASE,
)
JS_REFERENCE = re.compile(
    r"\bimport\s*\(\s*['\"](?P<dynamic>[^'\"]+)['\"]|"
    r"(?:\bimport|\bexport)\s+[^;]*?\bfrom\s*['\"](?P<module>[^'\"]+)['\"]|"
    r"\bimport\s*['\"](?P<side_effect>[^'\"]+)['\"]",
    re.MULTILINE,
)


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for name in ("href", "src", "poster"):
            if value := values.get(name):
                self.references.append(value)
        if source_set := values.get("srcset"):
            self.references.extend(item.strip().split()[0] for item in source_set.split(","))


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ("git", "ls-files", "-z"), cwd=ROOT, check=True, capture_output=True
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def dirty_tracked_files() -> list[str]:
    result = subprocess.run(
        ("git", "status", "--porcelain", "--untracked-files=no"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _local_path(source: Path, reference: str) -> Path | None:
    """Resolve a browser reference, or return None for external/non-file URLs."""
    reference = reference.strip()
    parsed = urlsplit(reference)
    if not reference or reference.startswith("#") or parsed.scheme or parsed.netloc:
        return None
    path = unquote(parsed.path)
    if not path:
        return None
    return (ROOT / path.lstrip("/")) if path.startswith("/") else (source.parent / path)


def _references(path: Path, text: str) -> list[str]:
    if path.suffix == ".html":
        parser = AssetParser()
        parser.feed(text)
        return parser.references
    if path.suffix == ".css":
        return [match.group("url") or match.group("import") for match in CSS_REFERENCE.finditer(text)]
    if path.suffix in {".js", ".mjs"}:
        return [next(group for group in match.groups() if group is not None) for match in JS_REFERENCE.finditer(text)]
    return []


def structural_errors(files: list[Path]) -> list[str]:
    errors = [f"Missing required repository element: {path}" for path in REQUIRED_PATHS if not (ROOT / path).is_file()]
    markers = ("<" * 7, "=" * 7, ">" * 7)
    for path in files:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(content.splitlines(), 1):
            if line.startswith(markers):
                errors.append(f"Unresolved merge marker: {path.relative_to(ROOT)}:{number}")
        if path.suffix == ".json":
            try:
                json.loads(content)
            except json.JSONDecodeError as error:
                errors.append(f"Invalid JSON: {path.relative_to(ROOT)}:{error.lineno}:{error.colno}: {error.msg}")
        for reference in _references(path, content):
            target = _local_path(path, reference)
            if target is not None and not target.is_file():
                errors.append(f"Missing local file referenced by {path.relative_to(ROOT)}: {reference}")
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
        # The shared verifier compares the complete catalogs, ordered contents of
        # every SQLite table, schemas, integrity_check, and foreign_key_check.
        verify_generated(first_catalog, first_database, fixture / "catalog.json", fixture / "courses.db")


def verify_standalone_fixture() -> None:
    """Build and inspect the file:// distribution used by release QA."""
    source = ROOT / "template" / "university-template"
    with tempfile.TemporaryDirectory() as temporary:
        fixture = Path(temporary) / "fictional-template-university"
        output = Path(temporary) / "standalone"
        shutil.copytree(source, fixture)
        command = (sys.executable, str(ROOT / "tools/build_standalone.py"), str(fixture), str(output))
        subprocess.run(command, cwd=ROOT, check=True)
        for page in ("index.html", "planner.html"):
            text = (output / page).read_text(encoding="utf-8")
            if "assets/embedded-data.js" not in text:
                raise RuntimeError(f"Standalone {page} does not load embedded data")
        if list(output.rglob("*.json")):
            raise RuntimeError("Standalone output contains an unresolved local JSON dependency")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="allow uncommitted tracked changes for local development",
    )
    args = parser.parse_args()

    dirty = dirty_tracked_files()
    if dirty and not args.allow_dirty:
        print("Final QA refused to run with uncommitted tracked changes.", file=sys.stderr)
        print("Commit/stash them, or use --allow-dirty for local development:", file=sys.stderr)
        print("\n".join(f"- {line}" for line in dirty), file=sys.stderr)
        return 2

    completed: list[str] = ["Clean tracked worktree" if not dirty else "Tracked-worktree check (local override)"]
    errors = structural_errors(tracked_files())
    if errors:
        print("Final QA structural validation failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    completed.append("Repository structure, local references, JSON, and merge-marker validation")

    try:
        for category, command in CATEGORIES:
            print(f"\n==> {category}: {' '.join(command)}", flush=True)
            subprocess.run(command, cwd=ROOT, check=True)
            completed.append(category)
        print("\n==> Reproducible generated catalogs and SQLite contents", flush=True)
        verify_reproducible_fixture()
        completed.append("Reproducible generated catalogs and SQLite contents")
        print("\n==> Standalone artifact generation and embedded-data validation", flush=True)
        verify_standalone_fixture()
        completed.append("Standalone artifact generation and embedded-data validation")
    except subprocess.CalledProcessError as error:
        print(f"\nFinal QA failed while running: {' '.join(error.cmd)}", file=sys.stderr)
        return error.returncode or 1

    print("\nFinal QA passed. Completed categories:")
    for category in completed:
        print(f"- PASS: {category}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
