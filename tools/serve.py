#!/usr/bin/env python3
"""Serve the project locally with a supervisable standard-library server."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import signal
import socket
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
HEALTH_PATH = "/.well-known/university-schedule-planner-health"


def is_loopback(host: str) -> bool:
    """Return whether every address represented by *host* is loopback-only."""
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
        return bool(addresses) and all(ipaddress.ip_address(address).is_loopback for address in addresses)
    except (OSError, ValueError):
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=8000, choices=range(0, 65536), metavar="PORT")
    parser.add_argument("--allow-public", action="store_true",
                        help="explicitly authorize binding to a non-loopback address")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--ready-file", type=Path, help="atomically write JSON readiness to this path")
    target.add_argument("--ready-fd", type=int, help="write one JSON readiness record to this inherited descriptor")
    return parser


class PlannerHandler(SimpleHTTPRequestHandler):
    server: "PlannerServer"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.split("?", 1)[0] == HEALTH_PATH:
            payload = json.dumps(self.server.metadata, sort_keys=True).encode() + b"\n"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()


class PlannerServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True
    metadata: dict[str, object]


def write_readiness(record: dict[str, object], ready_file: Path | None, ready_fd: int | None) -> None:
    payload = json.dumps(record, sort_keys=True) + "\n"
    if ready_fd is not None:
        with os.fdopen(ready_fd, "w", encoding="utf-8", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
    elif ready_file is not None:
        ready_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = ready_file.with_name(f".{ready_file.name}.{os.getpid()}.tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, ready_file)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.allow_public and not is_loopback(args.host):
        parser.error("--host must resolve only to loopback addresses; use --allow-public to authorize public binding")
    root = Path(__file__).resolve().parents[1]
    try:
        server = PlannerServer((args.host, args.port), partial(PlannerHandler, directory=str(root)))
    except OSError as exc:
        print(f"ERROR: could not bind {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 2
    with server:
        bound_host, actual_port = server.server_address[:2]
        server.metadata = {"host": str(bound_host), "port": int(actual_port), "pid": os.getpid(),
                           "repository_root": str(root.resolve())}
        try:
            write_readiness(server.metadata, args.ready_file, args.ready_fd)
        except OSError as exc:
            print(f"ERROR: could not publish readiness: {exc}", file=sys.stderr)
            return 3
        stopping = threading.Event()

        def request_shutdown(_signum: int, _frame: object) -> None:
            if not stopping.is_set():
                stopping.set()
                threading.Thread(target=server.shutdown, name="server-shutdown", daemon=True).start()

        previous = {signum: signal.signal(signum, request_shutdown) for signum in (signal.SIGINT, signal.SIGTERM)}
        print(f"Serving University Schedule Planner at http://{bound_host}:{actual_port}", flush=True)
        try:
            server.serve_forever(poll_interval=0.1)
        except KeyboardInterrupt:
            request_shutdown(signal.SIGINT, None)
        finally:
            stopping.set()
            server.shutdown()
            server.server_close()
            for signum, old_handler in previous.items():
                signal.signal(signum, old_handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
