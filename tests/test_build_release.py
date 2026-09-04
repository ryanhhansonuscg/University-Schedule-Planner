import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.build_release import (
    RELEASE_FILES,
    create_archive,
    inspect_and_extract,
    smoke_test_extracted_release,
)


class ReleaseBuilderTests(unittest.TestCase):
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

    def test_extracted_release_completes_documented_quickstart(self):
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

    def test_inspection_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "bad.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../README.md", "bad")
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                inspect_and_extract(archive_path, Path(temporary) / "output")


if __name__ == "__main__":
    unittest.main()
