#!/usr/bin/env python3
"""Serve the project locally with Python's standard-library web server."""

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    print(f"Serving College Schedule Planner at http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), SimpleHTTPRequestHandler).serve_forever()


if __name__ == "__main__":
    main()
