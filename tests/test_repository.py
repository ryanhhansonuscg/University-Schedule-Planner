from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_university import build  # noqa: E402
from check_prohibited_terms import violations  # noqa: E402


class RepositoryTests(unittest.TestCase):
    def test_production_registry_is_consistent(self) -> None:
        registry = json.loads((ROOT / "universities" / "index.json").read_text())
        entries = registry["universities"]
        slugs = {entry["slug"] for entry in entries}
        self.assertEqual(len(slugs), len(entries))
        if entries:
            self.assertIn(registry["default_university"], slugs)
            for entry in entries:
                self.assertTrue((ROOT / entry["path"]).is_file())
        else:
            self.assertIsNone(registry["default_university"])

    def test_fictional_template_builds_only_in_temporary_directory(self) -> None:
        source = ROOT / "template" / "university-template"
        self.assertFalse((source / "catalog.json").exists())
        self.assertFalse((source / "courses.db").exists())
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "fictional-template-university"
            shutil.copytree(source, fixture)
            catalog = build(fixture)
            self.assertEqual(catalog["university"]["name"], "Fictional Template University")
            self.assertTrue((fixture / "catalog.json").is_file())
            self.assertTrue((fixture / "courses.db").is_file())
        self.assertFalse((source / "catalog.json").exists())
        self.assertFalse((source / "courses.db").exists())

    def test_removed_institution_content_does_not_return(self) -> None:
        self.assertEqual(violations(ROOT), [])

    def test_content_check_rejects_removed_branding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            test_root = Path(temporary)
            (test_root / "content.txt").write_text("Mary" + "land", encoding="utf-8")
            self.assertEqual(len(violations(test_root)), 1)


if __name__ == "__main__":
    unittest.main()
