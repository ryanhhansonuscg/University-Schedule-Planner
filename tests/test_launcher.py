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
from tools.import_university import (choose_source, differing_source_files, import_archive,
    import_directory, inspect_archive, inspect_directory, inspect_source, matching_sources)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "template" / "university-template"
SLUG = "fictional-template-university"


class LauncherImportTests(unittest.TestCase):
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
        with mock.patch("tools.import_university.build_standalone", side_effect=DataError("forced")):
            with self.assertRaisesRegex(DataError, "forced"):
                import_archive(archive, replace=True, repo_root=self.repo)
        self.assertEqual("old", marker.read_text())
        self.assertEqual("old", (output / "old.txt").read_text())
        self.assertEqual(registry_before, (self.repo / "universities/index.json").read_bytes())

    def directory(self, name="folder"):
        source = self.base / name
        if source.exists(): shutil.rmtree(source)
        shutil.copytree(FIXTURE, source)
        return source

    def test_folder_layout_allowlist_and_symlinks(self):
        source = self.directory()
        root, files = inspect_directory(source)
        self.assertEqual(source.resolve(), root)
        self.assertIn("university.json", files)
        (source / "catalog.json").write_text("generated")
        with self.assertRaisesRegex(DataError, "not allowed"):
            inspect_directory(source)
        (source / "catalog.json").unlink()
        (source / "departments/link.json").symlink_to(source / "university.json")
        with self.assertRaisesRegex(DataError, "symbolic links"):
            inspect_directory(source)

    def test_folder_is_copied_before_validation_and_remains_immutable(self):
        source = self.directory()
        original = json.loads((source / "university.json").read_text())
        def mutate(_manifest):
            changed = dict(original); changed["name"] = "Edited during import"
            (source / "university.json").write_text(json.dumps(changed))
        import_directory(source, repo_root=self.repo, manifest_callback=mutate)
        installed = json.loads((self.repo / "universities" / SLUG / "university.json").read_text())
        self.assertEqual(original["name"], installed["name"])

    def test_zip_folder_conflict_requires_explicit_selection(self):
        archive, directory = self.archive(), self.directory(SLUG)
        pair = matching_sources(archive, directory)
        self.assertIsNotNone(pair)
        self.assertEqual(archive.resolve(), choose_source(archive, directory, "zip"))
        self.assertEqual(directory.resolve(), choose_source(archive, directory, "directory"))
        self.assertIsNone(choose_source(archive, directory, "cancel"))
        with self.assertRaisesRegex(DataError, "Choose"):
            choose_source(archive, directory, "automatic")
        (directory / "README.md").write_text("newer manual edit")
        left, right = matching_sources(archive, directory)
        self.assertEqual(("README.md",), differing_source_files(left, right))

    def test_directory_replacement_requires_confirmation_and_rolls_back(self):
        source = self.directory()
        import_directory(source, repo_root=self.repo)
        marker = self.repo / "universities" / SLUG / "marker.txt"; marker.write_text("old")
        with self.assertRaisesRegex(DataError, "explicit replacement confirmation"):
            import_directory(source, repo_root=self.repo)
        with mock.patch("tools.import_university.build_standalone", side_effect=DataError("forced")):
            with self.assertRaisesRegex(DataError, "forced"):
                import_directory(source, replace=True, repo_root=self.repo)
        self.assertEqual("old", marker.read_text())


class LauncherServiceTests(unittest.TestCase):
    def test_repository_root_does_not_depend_on_current_directory(self):
        from tools.launcher import repository_root

        with mock.patch("pathlib.Path.cwd", return_value=Path("/unrelated")):
            self.assertEqual(ROOT, repository_root())

    def test_shutdown_terminates_only_managed_processes(self):
        from tools.launcher import LauncherService, ManagedProcess

        owned = mock.Mock()
        owned.pid = 101
        owned.poll.side_effect = [None, 0, 0]
        owned.stdout = mock.Mock()
        unrelated = mock.Mock()
        service = LauncherService(lambda _event, _value: None, root=ROOT)
        service.processes.append(ManagedProcess("owned", ("python", "serve.py"), owned))

        service.shutdown()

        owned.terminate.assert_called_once_with()
        owned.kill.assert_not_called()
        owned.stdout.close.assert_called_once_with()
        unrelated.terminate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
