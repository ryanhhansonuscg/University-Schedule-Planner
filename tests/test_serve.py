import json
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from tools.launcher import HEALTH_PATH, server_health


ROOT = Path(__file__).resolve().parents[1]
SERVE = ROOT / "tools" / "serve.py"


class ServeTests(unittest.TestCase):
    def start_server(self):
        temporary = tempfile.TemporaryDirectory()
        ready = Path(temporary.name) / "ready.json"
        process = subprocess.Popen(
            [sys.executable, str(SERVE), "--port", "0", "--ready-file", str(ready)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not ready.exists() and process.poll() is None:
            time.sleep(0.02)

        def stop_process():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=3)
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()

        self.addCleanup(temporary.cleanup)
        self.addCleanup(stop_process)
        self.assertIsNone(process.poll(), process.stderr.read() if process.poll() is not None else "")
        self.assertTrue(ready.exists())
        return process, json.loads(ready.read_text())

    def test_dynamic_port_readiness_health_and_clean_shutdown(self):
        process, metadata = self.start_server()
        self.assertGreater(metadata["port"], 0)
        self.assertEqual(process.pid, metadata["pid"])
        self.assertEqual(str(ROOT.resolve()), metadata["repository_root"])
        url = f"http://{metadata['host']}:{metadata['port']}/"
        with urllib.request.urlopen(url + HEALTH_PATH.lstrip("/"), timeout=2) as response:
            self.assertEqual(metadata, json.load(response))
        self.assertEqual(metadata, server_health(url, ROOT))

        process.send_signal(signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGTERM)
        self.assertEqual(0, process.wait(timeout=3))
        with self.assertRaises(OSError):
            socket.create_connection((metadata["host"], metadata["port"]), timeout=0.2)

    def test_address_conflict_reports_failure_without_readiness(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            with tempfile.TemporaryDirectory() as directory:
                ready = Path(directory) / "ready.json"
                result = subprocess.run(
                    [sys.executable, str(SERVE), "--port", str(port), "--ready-file", str(ready)],
                    capture_output=True, text=True, timeout=3,
                )
                self.assertEqual(2, result.returncode)
                self.assertIn("could not bind", result.stderr)
                self.assertFalse(ready.exists())

    def test_public_binding_requires_explicit_authorization(self):
        result = subprocess.run(
            [sys.executable, str(SERVE), "--host", "0.0.0.0", "--port", "0"],
            capture_output=True, text=True, timeout=3,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("--allow-public", result.stderr)

    def test_health_rejects_a_different_repository(self):
        process, metadata = self.start_server()
        url = f"http://{metadata['host']}:{metadata['port']}/"
        self.assertIsNone(server_health(url, ROOT.parent))


if __name__ == "__main__":
    unittest.main()
