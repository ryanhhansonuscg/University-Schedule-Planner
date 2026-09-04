import json
import shutil
import stat
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

from tools.build_university import DataError
from tools.quickstart import import_archive, inspect_archive


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "template" / "university-template"
SLUG = "fictional-template-university"


class QuickstartTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        (self.repo / "universities").mkdir(parents=True)
        (self.repo / "universities/index.json").write_text(
            json.dumps({"schema_version": 1, "default_university": None, "universities": []})
        )

    def tearDown(self):
        self.temporary.cleanup()

    def archive(self, name="input.zip", transform=None, root_name=SLUG):
        source = self.base / "source" / SLUG
        if source.exists():
            shutil.rmtree(source.parent)
        shutil.copytree(FIXTURE, source)
        if transform:
            transform(source)
        output = self.base / name
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipped:
            for path in source.rglob("*"):
                if path.is_file():
                    zipped.write(path, f"{root_name}/{path.relative_to(source).as_posix()}")
        return output

    def test_valid_import_builds_artifacts_registry_and_standalone(self):
        output = import_archive(self.archive(), repo_root=self.repo)
        installed = self.repo / "universities" / SLUG
        self.assertEqual(self.repo / "dist" / SLUG / "index.html", output)
        self.assertTrue(output.is_file())
        self.assertTrue((installed / "catalog.json").is_file())
        self.assertTrue((installed / "courses.db").is_file())
        registry = json.loads((self.repo / "universities/index.json").read_text())
        self.assertEqual(SLUG, registry["default_university"])
        self.assertEqual(SLUG, registry["universities"][0]["slug"])

    def test_malformed_json_and_invalid_dataset_leave_no_install(self):
        malformed = self.archive(
            "malformed.zip", lambda source: (source / "university.json").write_text("{")
        )
        with self.assertRaisesRegex(DataError, "Invalid JSON"):
            import_archive(malformed, repo_root=self.repo)
        invalid = self.archive(
            "invalid.zip",
            lambda source: (source / "calendars.json").unlink(),
        )
        with self.assertRaisesRegex(DataError, "Malformed university layout"):
            import_archive(invalid, repo_root=self.repo)
        self.assertFalse((self.repo / "universities" / SLUG).exists())

    def test_wrapper_must_match_normalized_slug_without_side_effects(self):
        registry_path = self.repo / "universities/index.json"
        registry_before = registry_path.read_bytes()
        archive = self.archive(root_name="different-wrapper")

        with self.assertRaisesRegex(
            DataError,
            "Archive wrapper 'different-wrapper' does not match normalized university slug "
            f"'{SLUG}'",
        ):
            import_archive(archive, repo_root=self.repo)

        self.assertFalse((self.repo / "universities" / SLUG).exists())
        self.assertFalse((self.repo / "dist" / SLUG).exists())
        self.assertEqual(registry_before, registry_path.read_bytes())

    def test_rejects_traversal_absolute_and_symlink_entries(self):
        for filename in (f"{SLUG}/../escape.json", "/absolute.json", "C:/drive.json"):
            archive = self.base / (str(abs(hash(filename))) + ".zip")
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr(filename, "{}")
            with self.assertRaisesRegex(DataError, "Unsafe archive path"):
                inspect_archive(archive)

        archive = self.base / "symlink.zip"
        info = zipfile.ZipInfo(f"{SLUG}/departments/link.json")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr(info, "../../outside")
        with self.assertRaisesRegex(DataError, "symbolic links"):
            inspect_archive(archive)

    def test_rejects_file_count_expanded_size_and_duplicate_paths(self):
        archive = self.archive()
        with self.assertRaisesRegex(DataError, "too many files"):
            inspect_archive(archive, max_files=1)
        with self.assertRaisesRegex(DataError, "too much data"):
            inspect_archive(archive, max_expanded_bytes=10)

        duplicate = self.base / "duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate, "w") as zipped:
                zipped.writestr(f"{SLUG}/university.json", "{}")
                zipped.writestr(f"{SLUG}/university.json", "{}")
        with self.assertRaisesRegex(DataError, "Duplicate archive path"):
            inspect_archive(duplicate)

    def test_collision_requires_replace_and_replace_updates_registry(self):
        archive = self.archive()
        import_archive(archive, repo_root=self.repo)
        with self.assertRaisesRegex(DataError, "--replace"):
            import_archive(archive, repo_root=self.repo)
        import_archive(archive, replace=True, repo_root=self.repo)
        registry = json.loads((self.repo / "universities/index.json").read_text())
        self.assertEqual(1, len(registry["universities"]))

    def test_registry_update_preserves_existing_default(self):
        registry = {
            "schema_version": 1,
            "default_university": "existing",
            "universities": [{"slug": "existing", "name": "Existing", "path": "universities/existing/catalog.json"}],
        }
        (self.repo / "universities/index.json").write_text(json.dumps(registry))
        import_archive(self.archive(), repo_root=self.repo)
        updated = json.loads((self.repo / "universities/index.json").read_text())
        self.assertEqual("existing", updated["default_university"])
        self.assertEqual({"existing", SLUG}, {entry["slug"] for entry in updated["universities"]})

    def test_failure_rolls_back_replaced_dataset_registry_and_output(self):
        archive = self.archive()
        import_archive(archive, repo_root=self.repo)
        marker = self.repo / "universities" / SLUG / "keep.txt"
        marker.write_text("old")
        registry_before = (self.repo / "universities/index.json").read_bytes()
        output = self.repo / "dist" / SLUG
        (output / "old.txt").write_text("old")
        with mock.patch("tools.quickstart.build_standalone", side_effect=DataError("forced")):
            with self.assertRaisesRegex(DataError, "forced"):
                import_archive(archive, replace=True, repo_root=self.repo)
        self.assertEqual("old", marker.read_text())
        self.assertEqual("old", (output / "old.txt").read_text())
        self.assertEqual(registry_before, (self.repo / "universities/index.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
