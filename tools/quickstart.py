#!/usr/bin/env python3
"""Safely import an LLM-produced university ZIP and build the planner."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

if __package__:
    from tools.build_standalone import build_standalone
    from tools.build_university import DataError, ROOT, build, validate_and_compile, validate_registry
else:
    from build_standalone import build_standalone
    from build_university import DataError, ROOT, build, validate_and_compile, validate_registry


MAX_FILES = 2_000
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
ALLOWED_EXTENSIONS = {".json", ".md"}
DRIVE_PATH = re.compile(r"^[A-Za-z]:")


def inspect_archive(
    archive: Path,
    *,
    max_files: int = MAX_FILES,
    max_expanded_bytes: int = MAX_EXPANDED_BYTES,
) -> tuple[str, list[zipfile.ZipInfo]]:
    """Validate ZIP metadata without writing anything and return its root folder."""
    try:
        zipped = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise DataError(f"Cannot read ZIP archive {archive}: {exc}") from exc

    with zipped:
        members = zipped.infolist()
        files = [member for member in members if not member.is_dir()]
        if len(files) > max_files:
            raise DataError(f"Archive contains too many files ({len(files)}; limit {max_files})")
        expanded = sum(member.file_size for member in files)
        if expanded > max_expanded_bytes:
            raise DataError(
                f"Archive expands to too much data ({expanded} bytes; limit {max_expanded_bytes})"
            )

        seen: set[str] = set()
        roots: set[str] = set()
        paths: list[PurePosixPath] = []
        for member in members:
            name = member.filename
            # ZIP names use '/', but treating '\\' as a separator avoids a Windows
            # extraction ambiguity and rejects drive paths on every platform.
            portable = name.replace("\\", "/")
            path = PurePosixPath(portable)
            if (
                not portable
                or portable.startswith("/")
                or DRIVE_PATH.match(portable)
                or any(part in {"", ".", ".."} for part in path.parts)
            ):
                raise DataError(f"Unsafe archive path: {name!r}")
            key = portable.rstrip("/").casefold()
            if key in seen:
                raise DataError(f"Duplicate archive path: {name!r}")
            seen.add(key)
            roots.add(path.parts[0])
            paths.append(path)

            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise DataError(f"Archive may not contain symbolic links: {name!r}")
            file_type = stat.S_IFMT(mode)
            if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise DataError(f"Archive may contain only regular files and directories: {name!r}")
            if member.flag_bits & 0x1:
                raise DataError(f"Archive may not contain encrypted files: {name!r}")
            if not member.is_dir() and path.suffix.casefold() not in ALLOWED_EXTENSIONS:
                raise DataError(f"Unexpected file extension in archive: {name!r}")

        if len(roots) != 1 or not paths:
            raise DataError("Archive must contain exactly one top-level university folder")
        root = next(iter(roots))
        if any(len(path.parts) == 1 and not member.is_dir() for path, member in zip(paths, members)):
            raise DataError("Archive contents must be inside one top-level university folder")
        file_relatives = {
            PurePosixPath(*path.parts[1:]).as_posix()
            for path, member in zip(paths, members)
            if not member.is_dir()
        }
        required = {"university.json", "calendars.json"}
        missing = required - file_relatives
        department_files = [name for name in file_relatives if name.startswith("departments/")]
        if missing or not department_files or any(name.count("/") != 1 for name in department_files):
            detail = ", ".join(sorted(missing)) or "departments/*.json"
            raise DataError(f"Malformed university layout (missing or invalid {detail})")
        if any(
            name not in {"university.json", "calendars.json"}
            and not ("/" not in name and name.endswith(".md"))
            and not name.startswith("departments/")
            for name in file_relatives
        ):
            raise DataError("Malformed university layout: only source files are allowed")
        if any(not name.endswith(".json") for name in department_files):
            raise DataError("Malformed university layout: department files must be JSON")
        return root, members


def _extract(archive: Path, target: Path, members: list[zipfile.ZipInfo], limit: int) -> None:
    """Extract checked regular files while independently enforcing the byte limit."""
    written = 0
    with zipfile.ZipFile(archive) as zipped:
        for member in members:
            destination = target.joinpath(*PurePosixPath(member.filename.replace("\\", "/")).parts)
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(member) as source, destination.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    written += len(chunk)
                    if written > limit:
                        raise DataError(f"Archive exceeded expanded-size limit of {limit} bytes")
                    output.write(chunk)


def _write_json_atomic(path: Path, value: dict, scratch: Path) -> None:
    temporary = scratch / "index.json.new"
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def import_archive(
    archive: Path,
    *,
    replace: bool = False,
    repo_root: Path = ROOT,
    max_files: int = MAX_FILES,
    max_expanded_bytes: int = MAX_EXPANDED_BYTES,
) -> Path:
    """Perform the complete import transaction and return standalone index.html."""
    archive = archive.resolve()
    repo_root = repo_root.resolve()
    universities = repo_root / "universities"
    registry_path = universities / "index.json"
    dist = repo_root / "dist"
    universities.mkdir(parents=True, exist_ok=True)
    root_name, members = inspect_archive(
        archive, max_files=max_files, max_expanded_bytes=max_expanded_bytes
    )
    registry = validate_registry(registry_path)

    with tempfile.TemporaryDirectory(prefix=".quickstart-", dir=repo_root) as temporary_name:
        scratch = Path(temporary_name)
        extracted = scratch / "extracted"
        extracted.mkdir()
        _extract(archive, extracted, members, max_expanded_bytes)
        source = extracted / root_name
        catalog = validate_and_compile(source, check_directory_name=False)
        university = catalog["university"]
        slug = university["slug"]
        if root_name != slug:
            raise DataError(
                f"Archive wrapper {root_name!r} does not match normalized university slug {slug!r}"
            )
        destination = universities / slug
        output = dist / slug
        if destination.exists() and not replace:
            raise DataError(
                f"University slug {slug!r} is already installed; rerun with --replace to replace it"
            )

        entries = registry["universities"]
        matching = [entry for entry in entries if entry.get("slug") == slug]
        if matching and not replace:
            raise DataError(
                f"University slug {slug!r} already exists in the registry; rerun with --replace"
            )
        updated_entries = [entry for entry in entries if entry.get("slug") != slug]
        updated_entries.append({
            "slug": slug,
            "name": university["name"],
            "short_name": university["short_name"],
            "path": f"universities/{slug}/catalog.json",
        })
        updated_entries.sort(key=lambda entry: entry["name"].casefold())
        updated_registry = dict(registry)
        updated_registry["universities"] = updated_entries
        if not registry.get("default_university"):
            updated_registry["default_university"] = slug

        old_dataset = scratch / "old-dataset"
        old_output = scratch / "old-output"
        registry_backup = registry_path.read_bytes()
        installed = False
        output_installed = False
        try:
            if destination.exists():
                os.replace(destination, old_dataset)
            os.replace(source, destination)
            installed = True
            build(destination)

            staged_output = scratch / "standalone"
            build_standalone(destination, staged_output)
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                os.replace(output, old_output)
            os.replace(staged_output, output)
            output_installed = True
            _write_json_atomic(registry_path, updated_registry, scratch)
            validate_registry(registry_path, catalog["university"])
        except Exception:
            if output_installed and output.exists():
                shutil.rmtree(output)
            if old_output.exists():
                os.replace(old_output, output)
            if installed and destination.exists():
                shutil.rmtree(destination)
            if old_dataset.exists():
                os.replace(old_dataset, destination)
            registry_path.write_bytes(registry_backup)
            raise
        return output / "index.html"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="ZIP containing one completed university folder")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace an existing dataset, registry entry, and standalone build with the same slug",
    )
    args = parser.parse_args()
    try:
        output = import_archive(args.archive, replace=args.replace)
    except (DataError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Success. Open this file in your browser:\n{output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
