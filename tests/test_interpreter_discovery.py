import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.launcher import (
    InterpreterCandidate, _conda_root, candidate_commands, discover_interpreters,
    load_interpreter_override, probe_interpreter, reset_interpreter_override,
    save_interpreter_override, select_interpreter,
)


class InterpreterDiscoveryTests(unittest.TestCase):
    def result(self, path, version="3.10.0", returncode=0, stderr=""):
        return subprocess.CompletedProcess([], returncode, f"{path}\n{version}\n", stderr)

    @mock.patch("tools.launcher.shutil.which", return_value="/opt/conda/condabin/conda")
    def test_order_starts_conda_exe_then_path_then_standard_locations(self, _which):
        commands = candidate_commands("darwin", {"CONDA_EXE": "/custom/conda/bin/conda", "HOME": "/Users/me", "PATH": "/bin"})
        flattened = [command[0] for command, _source in commands]
        self.assertEqual("/custom/conda/bin/python", flattened[0])
        self.assertEqual("/opt/conda/bin/python", flattened[1])
        self.assertIn("/Users/me/miniconda3/bin/python", flattened)
        self.assertIn("/Users/me/anaconda3/bin/python", flattened)

    @mock.patch("tools.launcher.shutil.which", return_value=None)
    def test_active_windows_conda_environment_is_first(self, _which):
        commands = candidate_commands("win32", {
            "CONDA_PREFIX": "D:/Portable/conda",
            "USERPROFILE": "D:/Profile",
            "PATH": "",
        })
        self.assertEqual((("D:/Portable/conda/python.exe",), "active Conda environment"), commands[0])

    def test_windows_library_bin_shim_resolves_installation_root(self):
        executable = Path("D:/Portable/conda/Library/bin/conda.bat")
        self.assertEqual(Path("D:/Portable/conda"), _conda_root(executable))

    @mock.patch("tools.launcher.subprocess.run")
    def test_probe_rejects_invalid_and_incompatible_executables(self, run):
        run.side_effect = OSError("not executable")
        self.assertIn("could not execute", probe_interpreter(("bad",), "custom").reason)
        run.side_effect = None
        run.return_value = self.result("/old/python", "3.9.18")
        old = probe_interpreter(("old",), "custom")
        self.assertFalse(old.compatible)
        self.assertIn("3.10+", old.reason)

    @mock.patch("tools.launcher.subprocess.run")
    def test_paths_with_spaces_are_passed_as_one_argument(self, run):
        path = "/Applications/Python Tools/python3"
        run.return_value = self.result(path)
        candidate = probe_interpreter((path,), "custom")
        self.assertTrue(candidate.compatible)
        self.assertEqual(path, run.call_args.args[0][0])

    def test_saved_override_round_trip_and_reset(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "settings" / "launcher.json"
            executable = Path(temporary) / "Python With Spaces" / "python"
            save_interpreter_override(executable, config)
            self.assertEqual(executable.resolve(), load_interpreter_override(config))
            self.assertEqual(str(executable.resolve()), json.loads(config.read_text())["python"])
            reset_interpreter_override(config)
            self.assertIsNone(load_interpreter_override(config))

    @mock.patch("tools.launcher.probe_interpreter")
    def test_discovery_deduplicates_resolved_paths_and_falls_back(self, probe):
        path = Path("/resolved/python")
        probe.side_effect = [
            InterpreterCandidate(("python3",), "first", path, (3, 11, 0), True, "compatible"),
            InterpreterCandidate(("python",), "duplicate", path, (3, 11, 0), True, "compatible"),
            InterpreterCandidate(("bad",), "bad", reason="rejected"),
        ]
        found = discover_interpreters([(("python3",), "first"), (("python",), "duplicate"), (("bad",), "bad")])
        self.assertEqual(2, len(found))
        self.assertEqual(path, select_interpreter(found).path)
        incompatible = [InterpreterCandidate(("old",), "old", reason="too old")]
        self.assertIsNone(select_interpreter(incompatible))


if __name__ == "__main__":
    unittest.main()
