#!/usr/bin/env python3
"""Build a self-contained, file:// compatible planner distribution."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

if __package__:
    from tools.build_university import DataError, ROOT, validate_and_compile
else:
    from build_university import DataError, ROOT, validate_and_compile


ASSETS = ("app.js", "editor-core.js", "editor.js", "loader.js", "planner-core.js", "planner.js", "styles.css")
PAGES = ("index.html", "planner.html", "editor.html")
EMBEDDED_SCRIPT = '<script src="assets/embedded-data.js" defer></script>'


def _javascript(value: object) -> str:
    """Serialize data without permitting JSON strings to terminate a script tag."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def build_standalone(
    university_dir: Path, output_dir: Path, *, allow_template_directory: bool = False
) -> dict:
    """Validate *university_dir* and write a standalone web app to *output_dir*."""
    university_dir = university_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir == ROOT or output_dir in ROOT.parents or output_dir == university_dir:
        raise DataError("Output directory must not overwrite the repository or university source")

    catalog = validate_and_compile(
        university_dir, allow_template_directory=allow_template_directory
    )
    university = catalog["university"]
    slug = university["slug"]
    manifest = {
        "schema_version": 1,
        "default_university": slug,
        "universities": [{
            "slug": slug,
            "name": university["name"],
            "path": f"universities/{slug}/catalog.json",
        }],
    }

    if output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "assets").mkdir(parents=True)
    for asset in ASSETS:
        shutil.copy2(ROOT / "assets" / asset, output_dir / "assets" / asset)
    embedded = {"manifest": manifest, "catalogs": {slug: catalog}}
    (output_dir / "assets" / "embedded-data.js").write_text(
        "window.COLLEGE_PLANNER_EMBEDDED = " + _javascript(embedded) + ";\n",
        encoding="utf-8",
    )
    for page in PAGES:
        html = (ROOT / page).read_text(encoding="utf-8")
        marker = '<script src="assets/loader.js" defer></script>'
        if marker in html:
            html = html.replace(marker, f"{EMBEDDED_SCRIPT}\n  {marker}", 1)
        (output_dir / page).write_text(html, encoding="utf-8")
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("university_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--allow-template-directory", action="store_true", help=argparse.SUPPRESS
    )
    args = parser.parse_args()
    try:
        catalog = build_standalone(
            args.university_dir,
            args.output_dir,
            allow_template_directory=args.allow_template_directory,
        )
    except (DataError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"Built standalone {catalog['university']['name']} in {args.output_dir}: "
        f"{len(catalog['courses'])} courses"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
