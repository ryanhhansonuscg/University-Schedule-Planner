#!/usr/bin/env python3
"""Build and inspect the versioned, end-user release ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
RELEASE_EPOCH = 1767225600  # 2026-01-01, also used by the reproducibility gate.
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){1,2}(?:[-.][A-Za-z0-9]+)*$")

# This allowlist is deliberately the release contract. In particular, do not
# replace it with a broad copy of tracked files: tests and real source datasets
# must never leak into an end-user archive.
RELEASE_FILES = (
    "LICENSE",
    "README.md",
    "index.html",
    "planner.html",
    "schedule-import-template.csv",
    "schema.sql",
    "assets/app.js",
    "assets/loader.js",
    "assets/planner-core.js",
    "assets/planner.js",
    "assets/styles.css",
    "template/university-template/LLM-SCRAPING-GUIDE.md",
    "template/university-template/README.md",
    "template/university-template/calendars.json",
    "template/university-template/departments/SAMPLE.json",
    "template/university-template/university.json",
    "tools/build_standalone.py",
    "tools/build_university.py",
    "tools/quickstart.py",
    "tools/validate_university.py",
    "universities/README.md",
    "universities/index.json",
)


def _clean_tracked_worktree() -> bool:
    result = subprocess.run(
        ("git", "status", "--porcelain", "--untracked-files=no"),
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return not result.stdout.strip()


def _version() -> str:
    value = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    if not isinstance(value, str) or not VERSION_RE.fullmatch(value):
        raise ValueError("package.json contains an invalid release version")
    return value


def create_archive(destination: Path, files: tuple[str, ...] = RELEASE_FILES) -> None:
    """Create a byte-reproducible ZIP containing only the release allowlist."""
    missing = [name for name in files if not (ROOT / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Release inputs are missing: {', '.join(missing)}")
    timestamp = tuple(__import__("time").gmtime(RELEASE_EPOCH)[:6])
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in sorted(files):
                info = zipfile.ZipInfo(name, timestamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (0o100644 << 16)
                archive.writestr(info, (ROOT / name).read_bytes(), compresslevel=9)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def inspect_and_extract(archive_path: Path, destination: Path) -> None:
    """Verify the exact manifest, reject unsafe entries, and extract for inspection."""
    expected = set(RELEASE_FILES)
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        names: set[str] = set()
        for member in members:
            path = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if (not member.filename or member.filename.startswith(("/", "\\"))
                    or "\\" in member.filename or any(part in {"", ".", ".."} for part in path.parts)
                    or stat.S_ISLNK(mode) or member.is_dir()):
                raise ValueError(f"Unsafe release archive entry: {member.filename!r}")
            if member.filename in names:
                raise ValueError(f"Duplicate release archive entry: {member.filename!r}")
            names.add(member.filename)
        if names != expected:
            raise ValueError(
                f"Release manifest mismatch; missing={sorted(expected - names)}, "
                f"unexpected={sorted(names - expected)}"
            )
        destination.mkdir(parents=True, exist_ok=True)
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            if target.read_bytes() != (ROOT / member.filename).read_bytes():
                raise ValueError(f"Release content differs from source: {member.filename}")


def smoke_test_extracted_release(extracted: Path) -> None:
    """Exercise the documented quickstart using only files in the release."""
    slug = "fictional-template-university"
    template = extracted / "template" / "university-template"
    fixture_archive = extracted / "quickstart-smoke.zip"
    with zipfile.ZipFile(fixture_archive, "w", zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(path for path in template.rglob("*") if path.is_file()):
            relative = source.relative_to(template)
            archive.write(source, (PurePosixPath(slug) / relative.as_posix()).as_posix())

    subprocess.run(
        (sys.executable, "tools/quickstart.py", str(fixture_archive)),
        cwd=extracted,
        check=True,
        capture_output=True,
        text=True,
    )
    standalone = extracted / "dist" / slug
    required = (
        standalone / "index.html",
        standalone / "planner.html",
        standalone / "assets/embedded-data.js",
    )
    missing = [path.relative_to(extracted).as_posix() for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"Extracted release quickstart did not create: {', '.join(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "release")
    args = parser.parse_args()
    if not _clean_tracked_worktree():
        parser.error("release packaging requires a clean tracked worktree")

    print("Running canonical final QA gate...", flush=True)
    subprocess.run((sys.executable, "tools/final_qa.py"), cwd=ROOT, check=True)
    version = _version()
    archive_path = args.output_dir.resolve() / f"university-schedule-planner-v{version}.zip"
    create_archive(archive_path)
    with tempfile.TemporaryDirectory() as temporary:
        extracted = Path(temporary)
        inspect_and_extract(archive_path, extracted)
        smoke_test_extracted_release(extracted)

    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {archive_path.name}\n", encoding="ascii")
    print(f"Release: {archive_path}")
    print(f"SHA-256: {checksum_path}")
    print("Archive manifest, safe extraction, and extracted quickstart smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
