import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.build_standalone import build_standalone
from tools.build_university import DataError


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "template" / "university-template"


class StandaloneBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.source = base / "fictional-template-university"
        self.output = base / "distribution"
        shutil.copytree(FIXTURE, self.source)

    def tearDown(self):
        self.temporary.cleanup()

    def test_build_contains_pages_assets_and_embedded_compiled_data(self):
        catalog = build_standalone(self.source, self.output)
        for relative in (
            "index.html", "planner.html", "assets/styles.css", "assets/loader.js",
            "assets/app.js", "assets/planner.js", "assets/planner-core.js",
            "assets/embedded-data.js",
        ):
            self.assertTrue((self.output / relative).is_file(), relative)
        script = (self.output / "assets/embedded-data.js").read_text()
        payload = json.loads(script.removeprefix("window.COLLEGE_PLANNER_EMBEDDED = ").removesuffix(";\n"))
        slug = catalog["university"]["slug"]
        self.assertEqual(slug, payload["manifest"]["default_university"])
        self.assertEqual(catalog, payload["catalogs"][slug])
        for page in ("index.html", "planner.html"):
            html = (self.output / page).read_text()
            self.assertLess(html.index("embedded-data.js"), html.index("loader.js"))

    def test_build_uses_validation_without_writing_into_source(self):
        build_standalone(self.source, self.output)
        self.assertFalse((self.source / "catalog.json").exists())
        university = json.loads((self.source / "university.json").read_text())
        university["slug"] = "wrong"
        (self.source / "university.json").write_text(json.dumps(university))
        with self.assertRaises(DataError):
            build_standalone(self.source, self.output)

    def test_output_has_no_json_files_or_unresolved_json_asset_references(self):
        build_standalone(self.source, self.output)
        self.assertEqual([], list(self.output.rglob("*.json")))
        for html in self.output.glob("*.html"):
            self.assertNotIn(".json", html.read_text())


if __name__ == "__main__":
    unittest.main()
