import copy
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.build_university import DataError, build, validate_and_compile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "template/university-template"

class BuildUniversityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name) / "fixture"
        shutil.copytree(FIXTURE, self.directory)
    def tearDown(self): self.temp.cleanup()
    def load(self, relative): return json.loads((self.directory / relative).read_text())
    def save(self, relative, value): (self.directory / relative).write_text(json.dumps(value))
    def assert_invalid(self, relative, mutate, message):
        doc = self.load(relative); mutate(doc); self.save(relative, doc)
        with self.assertRaisesRegex(DataError, message): validate_and_compile(self.directory)

    def test_successful_compilation_does_not_write_during_validation(self):
        catalog = build(self.directory, validate_only=True)
        self.assertEqual(["SAMPLE101", "SAMPLE201"], [c["code"] for c in catalog["courses"]])
        self.assertFalse((self.directory / "catalog.json").exists())
    def test_malformed_json_and_root_documents(self):
        (self.directory / "university.json").write_text("[")
        with self.assertRaisesRegex(DataError, "Invalid JSON"): validate_and_compile(self.directory)
        (self.directory / "university.json").write_text("[]")
        with self.assertRaisesRegex(DataError, "root must be a JSON object"): validate_and_compile(self.directory)
    def test_invalid_scalar_types(self):
        self.assert_invalid("university.json", lambda d: d.update(schema_version="2"), "schema_version must be int")
    def test_duplicate_identifiers(self):
        self.assert_invalid("departments/SAMPLE.json", lambda d: d["courses"].append(copy.deepcopy(d["courses"][0])), "Duplicate course code")
    def test_calendar_errors(self):
        self.assert_invalid("calendars.json", lambda d: d["academic_calendars"][0]["terms"][0].update(start_date="2026-99-01"), "not a real date")
    def test_fully_dated_and_fully_undated_terms_are_valid(self):
        catalog = validate_and_compile(self.directory)
        terms = catalog["academic_calendars"][0]["terms"]
        self.assertTrue(any(term["dates_status"] == "official" and term["start_date"] for term in terms))
        self.assertTrue(any(term["dates_status"] == "unpublished" and term["start_date"] is None and term["end_date"] is None for term in terms))
    def test_partially_dated_term_is_invalid(self):
        self.assert_invalid("calendars.json", lambda d: d["academic_calendars"][0]["terms"][-1].update(start_date="2030-06-01"), "provide both")
    def test_undated_term_must_explicitly_include_both_date_fields(self):
        self.assert_invalid("calendars.json", lambda d: d["academic_calendars"][0]["terms"][-1].pop("start_date"), "explicitly provide")
    def test_published_dates_require_official_source_metadata(self):
        self.assert_invalid("calendars.json", lambda d: d["academic_calendars"][0].update(source_url=""), "source_url metadata")
    def test_relationship_logic_and_unknown_targets(self):
        self.assert_invalid("departments/SAMPLE.json", lambda d: d["edges"][0].update(kind="requires"), "unknown kind")
    def test_relationship_logic_metadata_is_well_formed(self):
        self.assert_invalid("departments/SAMPLE.json", lambda d: d["edges"][0].update(logic_operator="OR"), "provide logic_group and logic_operator together")
    def test_relationship_operator_uses_documented_enum(self):
        self.assert_invalid("departments/SAMPLE.json", lambda d: d["edges"][0].update(logic_group="g", logic_operator="XOR"), "unknown logic_operator")
    def test_relationship_group_membership_is_consistent(self):
        def contradictory(doc):
            first = doc["edges"][0]
            first.update(logic_group="g", logic_operator="OR")
            doc["edges"].append({"source":"SAMPLE101", "target":"SAMPLE101", "kind":"corequisite", "logic_group":"g", "logic_operator":"OR"})
        self.assert_invalid("departments/SAMPLE.json", contradictory, "contradictory target, kind, or operator")
    def test_relationship_group_requires_multiple_members(self):
        self.assert_invalid("departments/SAMPLE.json", lambda d: d["edges"][0].update(logic_group="g", logic_operator="AND"), "at least two edges")
    def test_source_membership_cannot_contradict_catalog(self):
        self.assert_invalid("departments/SAMPLE.json", lambda d: d["edges"][0].update(source_in_database=False), "contradicts the catalog")
    def test_offering_records(self):
        self.assert_invalid("departments/SAMPLE.json", lambda d: d["courses"][0]["offering_history"][0].update(term_code="NOPE"), "unknown term")
    def test_department_slug_filename_mismatch(self):
        path=self.directory/"departments/SAMPLE.json"; doc=json.loads(path.read_text()); doc["department"]["code"]="WRONG"; path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(DataError, "must match department code"): validate_and_compile(self.directory)
    def test_generated_sqlite_integrity_and_foreign_keys(self):
        build(self.directory)
        with sqlite3.connect(self.directory / "courses.db") as db:
            self.assertEqual("ok", db.execute("PRAGMA integrity_check").fetchone()[0])
            self.assertEqual(2, db.execute("SELECT count(*) FROM courses").fetchone()[0])
            self.assertGreater(db.execute("SELECT count(*) FROM academic_terms WHERE start_date IS NULL AND dates_status = 'unpublished'").fetchone()[0], 0)
            self.assertEqual(0, len(db.execute("PRAGMA foreign_key_check").fetchall()))

if __name__ == "__main__": unittest.main()
