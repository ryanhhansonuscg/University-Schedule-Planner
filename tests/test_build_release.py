import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tools.build_release import (
    RELEASE_FILES,
    create_archive,
    inspect_and_extract,
    smoke_test_extracted_release,
)


class ReleaseBuilderTests(unittest.TestCase):
    def test_release_contract_contains_launcher_server_bootstraps_and_ui(self):
        self.assertTrue({
            ".nojekyll", "0.launch-planner.bat", "0.launch-planner.command",
            "tools/launcher.py", "tools/import_university.py", "tools/serve.py",
            "index.html", "planner.html", "editor.html", "assets/app.js", "assets/loader.js",
            "assets/editor-core.js", "assets/editor.js",
            "assets/planner-core.js", "assets/planner.js", "assets/styles.css",
        }.issubset(RELEASE_FILES))

    def test_archive_is_deterministic_and_has_exact_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "first.zip", root / "second.zip"
            create_archive(first)
            create_archive(second)
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(set(archive.namelist()), set(RELEASE_FILES))
                self.assertIn("LICENSE", archive.namelist())
            inspect_and_extract(first, root / "extracted")

    def test_extracted_release_completes_isolated_launcher_integration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "release.zip"
            extracted = root / "extracted"
            create_archive(archive)
            inspect_and_extract(archive, extracted)
            smoke_test_extracted_release(extracted)

            standalone = extracted / "dist" / "fictional-template-university"
            self.assertTrue((standalone / "index.html").is_file())
            self.assertTrue((standalone / "planner.html").is_file())
            self.assertTrue((standalone / "assets" / "embedded-data.js").is_file())
            self.assertTrue((extracted / "universities" / "fictional-template-university" / "catalog.json").is_file())
            self.assertTrue((extracted / "universities" / "fictional-template-university" / "courses.db").is_file())

    def test_inspection_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "bad.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../README.md", "bad")
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                inspect_and_extract(archive_path, Path(temporary) / "output")

    def test_inspection_rejects_every_unsafe_entry_before_extraction(self):
        unsafe = ("/absolute", r"folder\file", "folder/./file", "folder/../file", "folder/")
        for name in unsafe:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive_path = root / "bad.zip"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    # ZipInfo normalizes backslashes on Windows during construction.
                    # Assign afterward so the archive contains the exact hostile name.
                    member = zipfile.ZipInfo("placeholder")
                    member.filename = name
                    archive.writestr(member, "bad")
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    inspect_and_extract(archive_path, root / "output")
                self.assertFalse((root / "output").exists())

    def test_inspection_rejects_duplicate_and_non_exact_manifests(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            duplicate = root / "duplicate.zip"
            with zipfile.ZipFile(duplicate, "w") as archive:
                archive.writestr("README.md", "first")
                with mock.patch("warnings.warn"):
                    archive.writestr("README.md", "second")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                inspect_and_extract(duplicate, root / "duplicate-output")

            missing = root / "missing.zip"
            create_archive(missing, tuple(item for item in RELEASE_FILES if item != "README.md"))
            with self.assertRaisesRegex(ValueError, "manifest mismatch"):
                inspect_and_extract(missing, root / "missing-output")

            unexpected = root / "unexpected.zip"
            create_archive(unexpected, RELEASE_FILES + ("package.json",))
            with self.assertRaisesRegex(ValueError, "manifest mismatch"):
                inspect_and_extract(unexpected, root / "unexpected-output")


if __name__ == "__main__":
    unittest.main()
