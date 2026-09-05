#!/usr/bin/env python3
"""Reusable, transactional university ZIP and directory importer."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

if __package__:
    from tools.build_standalone import ASSETS, PAGES, build_standalone
    from tools.build_university import DataError, ROOT, build, validate_and_compile, validate_registry
else:
    from build_standalone import ASSETS, PAGES, build_standalone
    from build_university import DataError, ROOT, build, validate_and_compile, validate_registry

MAX_FILES = 2_000
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
DRIVE_PATH = re.compile(r"^[A-Za-z]:")
ROOT_FILES = {"university.json", "calendars.json"}

@dataclass(frozen=True)
class SourceInfo:
    path: Path
    kind: str
    slug: str
    modified: float
    files: tuple[str, ...]
    valid: bool = True
    error: str = ""

@dataclass(frozen=True)
class ImportManifest:
    source: Path
    source_files: tuple[str, ...]
    installed_files: tuple[str, ...]

def _allowed(relative: str) -> bool:
    path = PurePosixPath(relative)
    return (relative in ROOT_FILES or (len(path.parts) == 1 and path.suffix.casefold() == ".md")
            or (len(path.parts) == 2 and path.parts[0] == "departments" and path.suffix.casefold() == ".json"))

def _check_layout(files: set[str]) -> None:
    missing = ROOT_FILES - files
    departments = [name for name in files if PurePosixPath(name).parts[0] == "departments"]
    if missing or not departments:
        detail = ", ".join(sorted(missing)) or "departments/*.json"
        raise DataError(f"Malformed university layout (missing or invalid {detail})")
    unexpected = sorted(name for name in files if not _allowed(name))
    if unexpected:
        raise DataError(f"Malformed university layout: source file is not allowed: {unexpected[0]}")

def inspect_archive(archive: Path, *, max_files: int = MAX_FILES,
                    max_expanded_bytes: int = MAX_EXPANDED_BYTES) -> tuple[str, list[zipfile.ZipInfo]]:
    try:
        zipped = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise DataError(f"Cannot read ZIP archive {archive}: {exc}") from exc
    with zipped:
        members = zipped.infolist(); regular = [m for m in members if not m.is_dir()]
        if len(regular) > max_files: raise DataError(f"Archive contains too many files ({len(regular)}; limit {max_files})")
        expanded = sum(m.file_size for m in regular)
        if expanded > max_expanded_bytes: raise DataError(f"Archive expands to too much data ({expanded} bytes; limit {max_expanded_bytes})")
        roots=set(); seen=set(); paths=[]
        for member in members:
            portable=member.filename.replace("\\", "/"); path=PurePosixPath(portable)
            if not portable or portable.startswith("/") or DRIVE_PATH.match(portable) or any(p in {"", ".", ".."} for p in path.parts):
                raise DataError(f"Unsafe archive path: {member.filename!r}")
            key=portable.rstrip("/").casefold()
            if key in seen: raise DataError(f"Duplicate archive path: {member.filename!r}")
            seen.add(key); roots.add(path.parts[0]); paths.append(path)
            mode=member.external_attr >> 16
            if stat.S_ISLNK(mode): raise DataError(f"Archive may not contain symbolic links: {member.filename!r}")
            if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}: raise DataError("Archive may contain only regular files and directories")
            if member.flag_bits & 1: raise DataError("Archive may not contain encrypted files")
        if len(roots)!=1 or not paths: raise DataError("Archive must contain exactly one top-level university folder")
        root=next(iter(roots))
        if any(len(p.parts)==1 and not m.is_dir() for p,m in zip(paths,members)): raise DataError("Archive contents must be inside one top-level university folder")
        files={PurePosixPath(*p.parts[1:]).as_posix() for p,m in zip(paths,members) if not m.is_dir()}
        _check_layout(files)
        return root,members

def _reject_linked_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink(): raise DataError(f"Directory path may not traverse symbolic links: {current}")
    if not absolute.is_dir(): raise DataError(f"University source is not a directory: {absolute}")
    return absolute.resolve()

def inspect_directory(directory: Path, *, max_files: int=MAX_FILES,
                      max_expanded_bytes: int=MAX_EXPANDED_BYTES) -> tuple[Path, tuple[str, ...]]:
    root=_reject_linked_path(directory); files=[]; total=0
    for entry in root.rglob("*"):
        rel=entry.relative_to(root).as_posix()
        if entry.is_symlink(): raise DataError(f"University directory may not contain symbolic links: {rel}")
        mode=entry.stat(follow_symlinks=False).st_mode
        if stat.S_ISDIR(mode):
            if rel != "departments": raise DataError(f"Malformed university layout: directory is not allowed: {rel}")
            continue
        if not stat.S_ISREG(mode): raise DataError(f"University directory may contain only regular files: {rel}")
        files.append(rel); total += entry.stat(follow_symlinks=False).st_size
    if len(files)>max_files: raise DataError(f"Directory contains too many files ({len(files)}; limit {max_files})")
    if total>max_expanded_bytes: raise DataError(f"Directory contains too much data ({total} bytes; limit {max_expanded_bytes})")
    _check_layout(set(files)); return root,tuple(sorted(files))

def _copy_directory(root: Path, target: Path, files: tuple[str,...], limit: int) -> None:
    written=0
    for relative in files:
        source=root.joinpath(*PurePosixPath(relative).parts); destination=target/source.relative_to(root)
        if source.is_symlink(): raise DataError(f"Source changed during staging: {relative}")
        destination.parent.mkdir(parents=True,exist_ok=True)
        flags=os.O_RDONLY | getattr(os,"O_NOFOLLOW",0)
        try: descriptor=os.open(source,flags)
        except OSError as exc: raise DataError(f"Cannot safely stage source file {relative}: {exc}") from exc
        with os.fdopen(descriptor,"rb") as inp, destination.open("wb") as out:
            while chunk:=inp.read(1024*1024):
                written+=len(chunk)
                if written>limit: raise DataError(f"Directory exceeded size limit of {limit} bytes while staging")
                out.write(chunk)

def _extract(archive: Path,target: Path,members:list[zipfile.ZipInfo],limit:int)->None:
    written=0
    with zipfile.ZipFile(archive) as zipped:
        for member in members:
            destination=target.joinpath(*PurePosixPath(member.filename.replace("\\","/")).parts)
            if member.is_dir(): destination.mkdir(parents=True,exist_ok=True); continue
            destination.parent.mkdir(parents=True,exist_ok=True)
            with zipped.open(member) as source,destination.open("wb") as output:
                while chunk:=source.read(1024*1024):
                    written+=len(chunk)
                    if written>limit: raise DataError(f"Archive exceeded expanded-size limit of {limit} bytes")
                    output.write(chunk)

def _write_json_atomic(path:Path,value:dict,scratch:Path)->None:
    temporary=scratch/"index.json.new"; temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8"); os.replace(temporary,path)

def _transaction(source:Path, source_origin:Path, source_files:tuple[str,...], *, replace:bool, repo_root:Path,
                 manifest_callback:Callable[[ImportManifest],None]|None=None, worker_count:int|None=None,
                 cancel_event=None, progress=None)->Path:
    universities=repo_root/"universities"; registry_path=universities/"index.json"; dist=repo_root/"dist"
    universities.mkdir(parents=True,exist_ok=True); registry=validate_registry(registry_path)
    catalog=validate_and_compile(source,check_directory_name=False,worker_count=worker_count,cancel_event=cancel_event,progress=progress); university=catalog["university"]; slug=university["slug"]
    destination=universities/slug; output=dist/slug
    if (destination.exists() or any(e.get("slug")==slug for e in registry["universities"])) and not replace:
        raise DataError(f"University slug {slug!r} is already installed; explicit replacement confirmation is required (or use --replace)")
    entries=[e for e in registry["universities"] if e.get("slug")!=slug]
    entries.append({"slug":slug,"name":university["name"],"short_name":university["short_name"],"path":f"universities/{slug}/catalog.json"}); entries.sort(key=lambda e:e["name"].casefold())
    updated=dict(registry); updated["universities"]=entries
    if not registry.get("default_university"): updated["default_university"]=slug
    source_info = SourceInfo(source_origin, "ZIP" if source_origin.suffix.casefold() == ".zip" else "Extracted folder", slug, source_origin.stat().st_mtime, source_files)
    manifest = preview_manifest(source_info)
    if manifest_callback: manifest_callback(manifest)
    scratch=source.parent; old_dataset=scratch/"old-dataset"; old_output=scratch/"old-output"; backup=registry_path.read_bytes(); installed=output_installed=False
    try:
        build(source,worker_count=worker_count,cancel_event=cancel_event,progress=progress); staged_output=scratch/"standalone"; build_standalone(source,staged_output)
        if destination.exists(): os.replace(destination,old_dataset)
        os.replace(source,destination); installed=True; output.parent.mkdir(parents=True,exist_ok=True)
        if output.exists(): os.replace(output,old_output)
        os.replace(staged_output,output); output_installed=True; _write_json_atomic(registry_path,updated,scratch); validate_registry(registry_path,catalog["university"])
    except Exception:
        if output_installed and output.exists(): shutil.rmtree(output)
        if old_output.exists(): os.replace(old_output,output)
        if installed and destination.exists(): shutil.rmtree(destination)
        if old_dataset.exists(): os.replace(old_dataset,destination)
        registry_path.write_bytes(backup); raise
    return output/"index.html"

def import_archive(archive:Path,*,replace:bool=False,repo_root:Path=ROOT,max_files:int=MAX_FILES,max_expanded_bytes:int=MAX_EXPANDED_BYTES,manifest_callback=None,worker_count:int|None=None,cancel_event=None,progress=None)->Path:
    archive=archive.resolve(); repo_root=Path(os.path.abspath(repo_root)); root,members=inspect_archive(archive,max_files=max_files,max_expanded_bytes=max_expanded_bytes)
    files=tuple(sorted(PurePosixPath(*PurePosixPath(m.filename.replace("\\","/")).parts[1:]).as_posix() for m in members if not m.is_dir()))
    with tempfile.TemporaryDirectory(prefix=".launcher-import-",dir=repo_root) as name:
        scratch=Path(name); extracted=scratch/"extracted"; extracted.mkdir(); _extract(archive,extracted,members,max_expanded_bytes); source=extracted/root
        slug=validate_and_compile(source,check_directory_name=False)["university"]["slug"]
        if root!=slug: raise DataError(f"Archive wrapper {root!r} does not match normalized university slug {slug!r}")
        return _transaction(source,archive,files,replace=replace,repo_root=repo_root,manifest_callback=manifest_callback,worker_count=worker_count,cancel_event=cancel_event,progress=progress)

def import_directory(directory:Path,*,replace:bool=False,repo_root:Path=ROOT,max_files:int=MAX_FILES,max_expanded_bytes:int=MAX_EXPANDED_BYTES,manifest_callback=None,worker_count:int|None=None,cancel_event=None,progress=None)->Path:
    root,files=inspect_directory(directory,max_files=max_files,max_expanded_bytes=max_expanded_bytes); repo_root=Path(os.path.abspath(repo_root))
    with tempfile.TemporaryDirectory(prefix=".launcher-import-",dir=repo_root) as name:
        staged=Path(name)/"source"; staged.mkdir(); _copy_directory(root,staged,files,max_expanded_bytes)
        slug = validate_and_compile(staged, check_directory_name=False)["university"]["slug"]
        named = staged.with_name(slug); os.replace(staged, named)
        return _transaction(named,root,files,replace=replace,repo_root=repo_root,manifest_callback=manifest_callback,worker_count=worker_count,cancel_event=cancel_event,progress=progress)

def inspect_source(path: Path) -> SourceInfo:
    """Inspect and fully validate a selectable source without installing it."""
    path = Path(path)
    try:
        with tempfile.TemporaryDirectory(prefix="launcher-inspect-") as name:
            temporary = Path(name)
            if path.is_dir():
                root, files = inspect_directory(path)
                staged = temporary / "source"
                staged.mkdir()
                _copy_directory(root, staged, files, MAX_EXPANDED_BYTES)
                slug = validate_and_compile(staged, check_directory_name=False)["university"]["slug"]
                kind = "Extracted folder"
            else:
                wrapper, members = inspect_archive(path)
                files = tuple(sorted(
                    PurePosixPath(*PurePosixPath(member.filename.replace("\\", "/")).parts[1:]).as_posix()
                    for member in members if not member.is_dir()
                ))
                extracted = temporary / "extracted"
                extracted.mkdir()
                _extract(path, extracted, members, MAX_EXPANDED_BYTES)
                slug = validate_and_compile(extracted / wrapper, check_directory_name=False)["university"]["slug"]
                if wrapper != slug:
                    raise DataError(f"Archive wrapper {wrapper!r} does not match normalized university slug {slug!r}")
                kind = "ZIP"
        return SourceInfo(path.resolve(), kind, slug, path.stat().st_mtime, files)
    except Exception as exc:
        modified = path.stat().st_mtime if path.exists() else 0
        kind = "Extracted folder" if path.is_dir() else "ZIP"
        return SourceInfo(path.absolute(), kind, "", modified, (), False, str(exc))

def matching_sources(archive:Path,directory:Path)->tuple[SourceInfo,SourceInfo]|None:
    left,right=inspect_source(archive),inspect_source(directory)
    return (left,right) if left.valid and right.valid and left.slug==right.slug else None


def differing_source_files(left: SourceInfo, right: SourceInfo) -> tuple[str, ...]:
    """Return source names absent from one source or with different bytes."""
    names = set(left.files) | set(right.files)
    different = set(left.files) ^ set(right.files)
    if left.valid and right.valid:
        def content(info: SourceInfo, name: str) -> bytes:
            if info.kind == "ZIP":
                with zipfile.ZipFile(info.path) as archive:
                    return archive.read(f"{info.slug}/{name}")
            return (info.path / name).read_bytes()
        for name in set(left.files) & set(right.files):
            if content(left, name) != content(right, name):
                different.add(name)
    return tuple(sorted(different))


def choose_source(archive: Path, directory: Path, choice: str) -> Path | None:
    """Resolve an explicit ZIP/folder conflict decision; never choose implicitly."""
    conflict = matching_sources(archive, directory)
    if conflict is None:
        raise DataError("The selected ZIP and folder are not the same valid university")
    choices = {"zip": conflict[0].path, "directory": conflict[1].path, "cancel": None}
    if choice not in choices:
        raise DataError("Choose Use ZIP, Use extracted folder, or Cancel")
    return choices[choice]


def preview_manifest(info: SourceInfo) -> ImportManifest:
    """Describe every source file read and installed/generated path written."""
    if not info.valid:
        raise DataError(info.error)
    generated = ("catalog.json", "courses.db")
    installed = tuple(f"universities/{info.slug}/{name}" for name in info.files + generated)
    standalone = tuple(f"dist/{info.slug}/{page}" for page in PAGES)
    standalone += tuple(f"dist/{info.slug}/assets/{asset}" for asset in (*ASSETS, "embedded-data.js"))
    return ImportManifest(info.path, info.files, installed + standalone + ("universities/index.json",))
