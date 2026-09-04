#!/usr/bin/env python3
"""Launch the University Schedule Planner and safely import university ZIPs."""

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

    with tempfile.TemporaryDirectory(prefix=".launcher-import-", dir=repo_root) as temporary_name:
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
            # Build while the import is still staged outside universities/. A
            # production directory is required to match the registry, which is
            # intentionally not updated until every artifact is ready.
            build(source)
            staged_output = scratch / "standalone"
            build_standalone(source, staged_output)

            if destination.exists():
                os.replace(destination, old_dataset)
            os.replace(source, destination)
            installed = True
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


def import_cli(argv: list[str] | None = None) -> int:
    """Run the legacy command-line archive importer."""
    parser = argparse.ArgumentParser(description="Import, validate, and build a university archive")
    parser.add_argument("archive", type=Path, help="ZIP containing one completed university folder")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace an existing dataset, registry entry, and standalone build with the same slug",
    )
    args = parser.parse_args(argv)
    try:
        output = import_archive(args.archive, replace=args.replace)
    except (DataError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Success. Open this file in your browser:\n{output.resolve()}")
    return 0


# GUI imports deliberately live below the import service. This keeps command-line
# compatibility useful on Python installations whose optional Tk package is absent.
import queue
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from typing import Callable


APP_NAME = "University Schedule Planner Launcher"
HOST = "127.0.0.1"
STARTUP_TIMEOUT = 15.0
SHUTDOWN_TIMEOUT = 3.0


def repository_root() -> Path:
    """Return the repository root independently of the process working directory."""
    root = Path(__file__).resolve().parents[1]
    if not (root / "tools" / "serve.py").is_file():
        raise RuntimeError(f"Cannot locate tools/serve.py beneath repository root {root}")
    return root


def available_port(host: str = HOST) -> int:
    """Ask the operating system for an unused loopback TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((host, 0))
        return int(server.getsockname()[1])


@dataclass
class ManagedProcess:
    name: str
    command: tuple[str, ...]
    process: subprocess.Popen[str]
    state: str = "Starting"
    error: str = ""
    output: list[str] = field(default_factory=list)

    @property
    def pid(self) -> int:
        return self.process.pid


class LauncherService:
    """Own launcher-created subprocesses and perform blocking work off the Tk thread."""

    def __init__(self, notify: Callable[[str, object], None], root: Path | None = None) -> None:
        self.root = (root or repository_root()).resolve()
        self.notify = notify
        self.stop_event = threading.Event()
        self.processes: list[ManagedProcess] = []
        self.workers: set[threading.Thread] = set()
        self._lock = threading.Lock()
        self.url = ""

    def _start_worker(self, target: Callable[..., None], *args: object) -> bool:
        if self.stop_event.is_set():
            return False

        def run() -> None:
            try:
                target(*args)
            except Exception as exc:  # report unexpected worker failures without killing Tk
                self.notify("error", str(exc))
            finally:
                with self._lock:
                    self.workers.discard(threading.current_thread())

        worker = threading.Thread(target=run, name=f"launcher-{target.__name__}")
        with self._lock:
            if self.stop_event.is_set():
                return False
            self.workers.add(worker)
        worker.start()
        return True

    def start_server(self) -> bool:
        """Start the bundled server lazily and health-check it on worker threads."""
        with self._lock:
            if self.stop_event.is_set() or any(item.process.poll() is None for item in self.processes):
                return False
        return self._start_worker(self._launch_server)

    def _launch_server(self) -> None:
        port = available_port()
        command = (sys.executable, str(self.root / "tools" / "serve.py"), "--port", str(port))
        startup_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            process = subprocess.Popen(
                command,
                cwd=self.root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=startup_flags,
            )
        except OSError as exc:
            self.notify("error", f"Could not start the planner server: {exc}")
            return
        managed = ManagedProcess("Planner server", command, process)
        with self._lock:
            if self.stop_event.is_set():
                # Startup raced with shutdown. It remains our child and must be reaped below.
                managed.state = "Stopping"
            self.processes.append(managed)
        self.notify("process", managed)
        self._start_worker(self._read_output, managed)
        if self.stop_event.is_set():
            self._terminate(managed)
            return
        self.url = f"http://{HOST}:{port}/"
        self._wait_until_ready(managed, self.url)

    def _read_output(self, managed: ManagedProcess) -> None:
        stream = managed.process.stdout
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                line = line.rstrip()
                if line:
                    managed.output.append(line)
                    del managed.output[:-20]
                    if managed.state != "Ready":
                        managed.error = line
                    self.notify("process", managed)
                if self.stop_event.is_set() and managed.process.poll() is not None:
                    break
        except (OSError, ValueError):
            pass

    def _wait_until_ready(self, managed: ManagedProcess, url: str) -> None:
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            return_code = managed.process.poll()
            if return_code is not None:
                managed.state = f"Exited ({return_code})"
                managed.error = managed.error or "Server exited before becoming reachable."
                self.notify("process", managed)
                return
            try:
                with urllib.request.urlopen(url, timeout=0.4) as response:
                    if response.status < 500:
                        managed.state = "Ready"
                        managed.error = ""
                        self.notify("ready", url)
                        self.notify("process", managed)
                        return
            except (OSError, urllib.error.URLError):
                self.stop_event.wait(0.1)
        if self.stop_event.is_set():
            return
        managed.state = "Startup failed"
        managed.error = managed.error or f"HTTP endpoint was not reachable after {STARTUP_TIMEOUT:g}s."
        self.notify("process", managed)
        self._terminate(managed)

    def import_in_background(self, archive: Path, replace: bool = False) -> bool:
        return self._start_worker(self._import, archive, replace)

    def _import(self, archive: Path, replace: bool) -> None:
        self.notify("status", f"Importing {archive.name}…")
        output = import_archive(archive, replace=replace, repo_root=self.root)
        if not self.stop_event.is_set():
            self.notify("status", f"Import complete: {output}")

    def _terminate(self, managed: ManagedProcess) -> None:
        process = managed.process
        if process.poll() is None:
            managed.state = "Stopping"
            self.notify("process", managed)
            try:
                process.terminate()
                process.wait(timeout=SHUTDOWN_TIMEOUT)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            except OSError:
                pass
        managed.state = f"Exited ({process.poll()})"
        if process.stdout is not None:
            try:
                process.stdout.close()
            except OSError:
                pass
        self.notify("process", managed)

    def shutdown(self) -> None:
        """Reject new work, stop only owned children, and join all launcher workers."""
        self.stop_event.set()
        with self._lock:
            processes = list(self.processes)
        for managed in processes:
            self._terminate(managed)
        while True:
            with self._lock:
                workers = [worker for worker in self.workers if worker is not threading.current_thread()]
            if not workers:
                break
            for worker in workers:
                worker.join(timeout=0.1)


class LauncherWindow:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.minsize(760, 390)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.service = LauncherService(self._post)
        self.closing = False
        self.shutdown_done = threading.Event()

        frame = ttk.Frame(self.root, padding=16)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        ttk.Label(frame, text=APP_NAME, font=("TkDefaultFont", 16, "bold")).grid(row=0, column=0, sticky="w")
        self.status = tk.StringVar(value="Starting local planner server…")
        ttk.Label(frame, textvariable=self.status).grid(row=1, column=0, sticky="ew", pady=(6, 10))
        columns = ("name", "pid", "state", "command", "error")
        self.table = ttk.Treeview(frame, columns=columns, show="headings", height=8)
        for column, heading, width in zip(columns, ("Process", "PID", "State", "Launch command", "Recent startup error"), (120, 70, 100, 280, 220)):
            self.table.heading(column, text=heading)
            self.table.column(column, width=width, minwidth=55)
        self.table.grid(row=2, column=0, sticky="nsew")

        url_frame = ttk.Frame(frame)
        url_frame.grid(row=3, column=0, sticky="ew", pady=(14, 8))
        url_frame.columnconfigure(1, weight=1)
        ttk.Label(url_frame, text="Planner URL:").grid(row=0, column=0, padx=(0, 8))
        self.url = tk.StringVar()
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url, state="readonly")
        self.url_entry.grid(row=0, column=1, sticky="ew")

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, sticky="e")
        self.import_button = ttk.Button(buttons, text="Import University ZIP…", command=self._choose_archive)
        self.import_button.grid(row=0, column=0, padx=4)
        self.open_button = ttk.Button(buttons, text="Open Planner", command=self._open, state="disabled")
        self.open_button.grid(row=0, column=1, padx=4)
        self.copy_button = ttk.Button(buttons, text="Copy URL", command=self._copy, state="disabled")
        self.copy_button.grid(row=0, column=2, padx=4)

        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(40, self._drain_events)
        self.service.start_server()

    def _post(self, event: str, value: object) -> None:
        if not self.closing:
            self.events.put((event, value))

    def _drain_events(self) -> None:
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "process":
                    self._show_process(value)
                elif event == "ready":
                    self.url.set(str(value))
                    self.status.set("Planner is ready.")
                    self.open_button.configure(state="normal")
                    self.copy_button.configure(state="normal")
                elif event == "status":
                    self.status.set(str(value))
                elif event == "error":
                    self.status.set(f"Error: {value}")
        except queue.Empty:
            pass
        if not self.closing:
            self.root.after(40, self._drain_events)

    def _show_process(self, value: object) -> None:
        managed = value
        assert isinstance(managed, ManagedProcess)
        command = subprocess.list2cmdline(managed.command)
        values = (managed.name, managed.pid, managed.state, command, managed.error)
        item = str(managed.pid)
        if self.table.exists(item):
            self.table.item(item, values=values)
        else:
            self.table.insert("", "end", iid=item, values=values)

    def _choose_archive(self) -> None:
        from tkinter import filedialog

        filename = filedialog.askopenfilename(title="Select university ZIP", filetypes=(("ZIP archives", "*.zip"), ("All files", "*")))
        if filename:
            self.service.import_in_background(Path(filename))

    def _open(self) -> None:
        if self.url.get():
            webbrowser.open(self.url.get())

    def _copy(self) -> None:
        if self.url.get():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.url.get())
            self.root.update_idletasks()
            self.status.set("Planner URL copied to the clipboard.")

    def _close(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.status.set("Stopping launcher processes…")
        self.import_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")

        def finish() -> None:
            self.service.shutdown()
            self.shutdown_done.set()

        threading.Thread(target=finish, name="launcher-shutdown", daemon=True).start()
        self._poll_shutdown()

    def _poll_shutdown(self) -> None:
        if self.shutdown_done.is_set():
            self.root.destroy()
        else:
            self.root.after(40, self._poll_shutdown)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    if len(sys.argv) > 1:
        if sys.argv[1] == "--import-archive":
            return import_cli(sys.argv[2:])
        print(f"Usage: {Path(sys.argv[0]).name} [--import-archive ZIP [--replace]]", file=sys.stderr)
        return 2
    try:
        LauncherWindow().run()
    except ImportError as exc:
        print(f"ERROR: {APP_NAME} requires Python's tkinter support: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
