#!/usr/bin/env python3
"""Launch the University Schedule Planner and import university sources."""

from __future__ import annotations

import os
import json
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

if __package__:
    from tools.build_university import DataError
    from tools.import_university import (ImportManifest, SourceInfo, import_archive,
        import_directory, inspect_archive, inspect_source, matching_sources, differing_source_files, choose_source, preview_manifest)
else:
    from build_university import DataError
    from import_university import (ImportManifest, SourceInfo, import_archive,
        import_directory, inspect_archive, inspect_source, matching_sources, differing_source_files, choose_source, preview_manifest)


def import_cli(argv: list[str] | None = None) -> int:
    """Import either a ZIP archive or an extracted university directory."""
    import argparse
    parser = argparse.ArgumentParser(description="Import, validate, and build university data")
    parser.add_argument("source", type=Path, help="university ZIP or extracted directory")
    parser.add_argument("--replace", action="store_true", help="replace an installed dataset")
    args = parser.parse_args(argv)
    try:
        function = import_directory if args.source.is_dir() else import_archive
        output = function(args.source, replace=args.replace)
    except (DataError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Success. Open this file in your browser:\n{output.resolve()}")
    return 0


APP_NAME = "University Schedule Planner Launcher"
HOST = "127.0.0.1"
STARTUP_TIMEOUT = 15.0
SHUTDOWN_TIMEOUT = 3.0
MINIMUM_PYTHON = (3, 10)
CONFIG_FILENAME = "launcher.json"


@dataclass(frozen=True)
class InterpreterCandidate:
    """A probed Python executable and the reason it was considered."""

    command: tuple[str, ...]
    source: str
    path: Path | None = None
    version: tuple[int, int, int] | None = None
    compatible: bool = False
    reason: str = "Not probed"

    @property
    def display(self) -> str:
        location = str(self.path) if self.path else subprocess.list2cmdline(self.command)
        version = ".".join(map(str, self.version)) if self.version else "unknown version"
        return f"{location} — {version} — {self.reason}"


def config_path(platform: str | None = None, environ: dict[str, str] | None = None) -> Path:
    """Return an OS user-level settings path; never write into the checkout."""
    platform, env = platform or sys.platform, environ or os.environ
    if platform == "win32":
        base = Path(env.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "university-schedule-planner" / CONFIG_FILENAME


def load_interpreter_override(path: Path | None = None) -> Path | None:
    try:
        value = json.loads((path or config_path()).read_text(encoding="utf-8"))["python"]
        return Path(value).expanduser().resolve() if isinstance(value, str) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_interpreter_override(executable: Path, path: Path | None = None) -> None:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"python": str(executable.resolve())}, indent=2) + "\n", encoding="utf-8")


def reset_interpreter_override(path: Path | None = None) -> None:
    (path or config_path()).unlink(missing_ok=True)


def _conda_candidates(prefix: Path) -> Iterable[Path]:
    executable = "python.exe" if os.name == "nt" else "bin/python"
    yield prefix / executable
    envs = prefix / "envs"
    if envs.is_dir():
        for environment in sorted(envs.iterdir()):
            yield environment / executable


def candidate_commands(platform: str | None = None, environ: dict[str, str] | None = None) -> list[tuple[tuple[str, ...], str]]:
    """Build a stable, broad candidate list without asserting who installed Python."""
    platform, env = platform or sys.platform, environ or os.environ
    items: list[tuple[tuple[str, ...], str]] = []
    active_root = None
    if env.get("CONDA_PREFIX"):
        prefix = Path(env["CONDA_PREFIX"])
        items.append(((str(prefix / ("python.exe" if platform == "win32" else "bin/python")),), "active Conda environment"))
        if "envs" in prefix.parts:
            active_root = Path(*prefix.parts[:prefix.parts.index("envs")])
    items.append(((sys.executable,), "current interpreter"))
    items.extend([(("py", "-3"), "Python launcher"), (("python3",), "PATH"), (("python",), "PATH")])
    conda_roots: list[Path] = []
    if active_root:
        conda_roots.append(active_root)
    for name in ("conda", "mamba"):
        found = shutil.which(name)
        if found:
            conda_roots.append(Path(found).resolve().parent.parent)
    home = Path(env.get("USERPROFILE" if platform == "win32" else "HOME", Path.home()))
    conda_roots.extend([home / "miniconda3", home / "anaconda3"])
    if platform == "win32":
        conda_roots.extend([home / "Miniconda3", home / "Anaconda3"])
        local = Path(env.get("LOCALAPPDATA", home / "AppData" / "Local"))
        program = Path(env.get("ProgramFiles", "C:/Program Files"))
        items.extend([((str(local / "Programs/Python/Python313/python.exe"),), "common Windows location"),
                      ((str(local / "Programs/Python/Python312/python.exe"),), "common Windows location"),
                      ((str(program / "Python313/python.exe"),), "common Windows location"),
                      ((str(program / "Python312/python.exe"),), "common Windows location")])
    elif platform == "darwin":
        items.extend([(("/opt/homebrew/bin/python3",), "Homebrew"), (("/usr/local/bin/python3",), "local installation"),
                      (("/Library/Frameworks/Python.framework/Versions/Current/bin/python3",), "macOS framework")])
    for root in conda_roots:
        items.extend(((str(path),), "discoverable Conda environment") for path in _conda_candidates(root))
    return items


def probe_interpreter(command: tuple[str, ...], source: str, timeout: float = 3.0) -> InterpreterCandidate:
    """Run one lightweight version/Tk probe and resolve the executable path."""
    script = ("import pathlib,sys,tkinter; "
              "print(str(pathlib.Path(sys.executable).resolve())); "
              "print('.'.join(map(str,sys.version_info[:3])))")
    try:
        result = subprocess.run((*command, "-c", script), capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return InterpreterCandidate(command, source, reason=f"rejected: could not execute ({exc})")
    lines = result.stdout.strip().splitlines()
    if result.returncode or len(lines) < 2:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else f"exit status {result.returncode}"
        return InterpreterCandidate(command, source, reason=f"rejected: version/Tk probe failed ({detail})")
    try:
        version = tuple(int(part) for part in lines[-1].split("."))
        resolved = Path(lines[-2]).resolve()
    except (ValueError, OSError):
        return InterpreterCandidate(command, source, reason="rejected: probe returned malformed output")
    if version < (*MINIMUM_PYTHON, 0):
        return InterpreterCandidate(command, source, resolved, version, False,
                                    f"rejected: Python {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]}+ is required")
    return InterpreterCandidate(command, source, resolved, version, True, f"compatible ({source})")


def discover_interpreters(commands=None) -> list[InterpreterCandidate]:
    """Probe candidates in preference order and deduplicate their resolved paths."""
    results, seen = [], set()
    for command, source in commands or candidate_commands():
        candidate = probe_interpreter(tuple(command), source)
        key = os.path.normcase(str(candidate.path)) if candidate.path else (tuple(command), source)
        if candidate.path and key in seen:
            continue
        if candidate.path:
            seen.add(key)
        results.append(candidate)
    return results


def select_interpreter(candidates: list[InterpreterCandidate], override: Path | None = None) -> InterpreterCandidate | None:
    if override:
        selected = probe_interpreter((str(override),), "saved override")
        if selected.compatible:
            return selected
    return next((candidate for candidate in candidates if candidate.compatible), None)


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

    def __init__(self, notify: Callable[[str, object], None], root: Path | None = None,
                 executable: Path | None = None) -> None:
        self.root = (root or repository_root()).resolve()
        self.notify = notify
        self.stop_event = threading.Event()
        self.processes: list[ManagedProcess] = []
        self.workers: set[threading.Thread] = set()
        self._lock = threading.Lock()
        self.url = ""
        self.executable = executable or Path(sys.executable).resolve()

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
        command = (str(self.executable), str(self.root / "tools" / "serve.py"), "--port", str(port))
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

    def import_in_background(self, source: Path, replace: bool = False) -> bool:
        return self._start_worker(self._import, source, replace)

    def _import(self, source: Path, replace: bool) -> None:
        self.notify("status", f"Importing {source.name}…")
        importer = import_directory if source.is_dir() else import_archive
        output = importer(source, replace=replace, repo_root=self.root)
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
        self.root.minsize(820, 430)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.interpreters = discover_interpreters()
        selected = select_interpreter(self.interpreters, load_interpreter_override())
        self.service = LauncherService(self._post, executable=selected.path if selected else Path(sys.executable))
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
        self.import_button = ttk.Button(buttons, text="Import ZIP…", command=self._choose_archive)
        self.import_button.grid(row=0, column=0, padx=4)
        self.folder_button = ttk.Button(buttons, text="Import extracted folder…", command=self._choose_directory)
        self.folder_button.grid(row=0, column=1, padx=4)
        self.open_button = ttk.Button(buttons, text="Open Planner", command=self._open, state="disabled")
        self.open_button.grid(row=0, column=2, padx=4)
        self.copy_button = ttk.Button(buttons, text="Copy URL", command=self._copy, state="disabled")
        self.copy_button.grid(row=0, column=3, padx=4)
        ttk.Button(buttons, text="Python Settings…", command=self._python_settings).grid(row=0, column=4, padx=4)

        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(40, self._drain_events)
        self.service.start_server()

    def _python_settings(self) -> None:
        window = self.tk.Toplevel(self.root)
        window.title("Python settings")
        window.minsize(720, 300)
        frame = self.ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        self.ttk.Label(frame, text="Detected interpreters (selection applies to new child processes):").pack(anchor="w")
        listing = self.tk.Listbox(frame, height=8)
        listing.pack(fill="both", expand=True, pady=6)
        for candidate in self.interpreters:
            listing.insert("end", candidate.display)
        message = self.tk.StringVar(value=f"Selected: {self.service.executable}")
        self.ttk.Label(frame, textvariable=message, wraplength=680).pack(anchor="w")

        def use(path: Path, save: bool = True) -> None:
            candidate = probe_interpreter((str(path),), "custom selection")
            if not candidate.compatible or candidate.path is None:
                from tkinter import messagebox
                messagebox.showerror("Invalid Python interpreter", candidate.reason, parent=window)
                return
            if save:
                save_interpreter_override(candidate.path)
            self.service.executable = candidate.path
            message.set(f"Selected: {candidate.path}. New child processes will use it.")

        def choose_detected() -> None:
            selection = listing.curselection()
            if selection:
                candidate = self.interpreters[selection[0]]
                if candidate.path:
                    use(candidate.path)

        def browse() -> None:
            from tkinter import filedialog
            filename = filedialog.askopenfilename(title="Select a Python executable", parent=window)
            if filename:
                use(Path(filename))

        def automatic(reset: bool = False) -> None:
            if reset:
                reset_interpreter_override()
            selected = select_interpreter(self.interpreters)
            if selected and selected.path:
                use(selected.path, save=not reset)
                if reset:
                    message.set(f"Override removed. Auto-detected: {selected.path}")
            else:
                message.set("No compatible Python 3.10+ interpreter with tkinter was detected.")

        buttons = self.ttk.Frame(frame)
        buttons.pack(anchor="e", pady=(8, 0))
        self.ttk.Button(buttons, text="Use selected", command=choose_detected).pack(side="left", padx=3)
        self.ttk.Button(buttons, text="Browse…", command=browse).pack(side="left", padx=3)
        self.ttk.Button(buttons, text="Auto-detect", command=automatic).pack(side="left", padx=3)
        self.ttk.Button(buttons, text="Reset", command=lambda: automatic(True)).pack(side="left", padx=3)

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
            archive = Path(filename)
            info = inspect_source(archive)
            candidate = archive.parent / info.slug
            source = archive
            if info.valid and candidate.is_dir() and matching_sources(archive, candidate):
                source = self._resolve_conflict(archive, candidate)
            if source:
                self._confirm_import(source)

    def _choose_directory(self) -> None:
        from tkinter import filedialog
        filename = filedialog.askdirectory(title="Select extracted university folder")
        if filename:
            self._confirm_import(Path(filename))

    def _resolve_conflict(self, archive: Path, directory: Path) -> Path | None:
        from tkinter import messagebox
        left, right = matching_sources(archive, directory)  # type: ignore[misc]
        differing = differing_source_files(left, right)
        def describe(item: SourceInfo) -> str:
            return (f"{item.kind}: {item.path}\nModified: {time.ctime(item.modified)}; "
                    f"{len(item.files)} files; validation: {'valid' if item.valid else item.error}")
        detail = (f"Both sources contain university {left.slug!r}. The extracted folder may "
                  "contain newer manual edits. They will not be merged.\n\n" + describe(left) +
                  "\n\n" + describe(right) + "\n\nDiffering source files: " +
                  (", ".join(differing) or "none") +
                  "\n\nYes = Use ZIP; No = Use extracted folder; Cancel = Cancel")
        answer = messagebox.askyesnocancel("Choose university source", detail)
        return choose_source(archive, directory, "zip" if answer is True else "directory" if answer is False else "cancel")

    def _confirm_import(self, source: Path) -> None:
        from tkinter import messagebox
        info = inspect_source(source)
        if not info.valid:
            messagebox.showerror("Invalid university source", info.error); return
        manifest = preview_manifest(info)
        detail = ("Exact source files read:\n  " + "\n  ".join(manifest.source_files) +
                  "\n\nGenerated/installed files written:\n  " + "\n  ".join(manifest.installed_files))
        if not messagebox.askokcancel("Import manifest", detail): return
        installed = self.service.root / "universities" / info.slug
        replace = installed.exists()
        if replace and not messagebox.askyesno("Replace installed dataset?", f"{info.slug!r} is installed. Replace it and its generated output?"):
            return
        self.service.import_in_background(source, replace=replace)

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
        self.folder_button.configure(state="disabled")
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
        print(f"Usage: {Path(sys.argv[0]).name} [--import-archive SOURCE [--replace]]", file=sys.stderr)
        return 2
    try:
        LauncherWindow().run()
    except ImportError as exc:
        print(f"ERROR: {APP_NAME} requires Python's tkinter support: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
