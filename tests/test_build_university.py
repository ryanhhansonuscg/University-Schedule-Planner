import copy
import json
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tools.build_university import (
    DataError, ErrorCollector, build, validate_and_compile, validate_array,
    generated_at, validate_boolean, validate_enum, validate_integer, validate_nullable_date,
    validate_object, validate_registry, validate_string, validate_string_array,
    validate_url,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "template/university-template"

class BuildUniversityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name) / "fictional-template-university"
        shutil.copytree(FIXTURE, self.directory)
    def tearDown(self): self.temp.cleanup()
    def load(self, relative): return json.loads((self.directory / relative).read_text())
    def save(self, relative, value): (self.directory / relative).write_text(json.dumps(value))
    def reset(self): shutil.rmtree(self.directory); shutil.copytree(FIXTURE, self.directory)
    def add_course(self, doc, number):
        course = copy.deepcopy(doc["courses"][0])
        course.update(code=f"SAMPLE{number}", number=str(number), title=f"Course {number}")
        course["offering_history"] = []
        doc["courses"].append(course)
        return course["code"]
    def assert_invalid(self, relative, mutate, message):
        doc = self.load(relative); mutate(doc); self.save(relative, doc)
        with self.assertRaisesRegex(DataError, message): validate_and_compile(self.directory)

    def test_successful_compilation_does_not_write_during_validation(self):
        catalog = build(self.directory, validate_only=True)
        self.assertEqual(["SAMPLE101", "SAMPLE201"], [c["code"] for c in catalog["courses"]])
        self.assertFalse((self.directory / "catalog.json").exists())
    def test_valid_source_date_epoch(self):
        with mock.patch.dict("os.environ", {"SOURCE_DATE_EPOCH": "0"}, clear=True):
            self.assertEqual("1970-01-01T00:00:00+00:00", generated_at())
    def test_invalid_source_date_epoch(self):
        with mock.patch.dict("os.environ", {"SOURCE_DATE_EPOCH": "not-a-time"}, clear=True):
            with self.assertRaisesRegex(DataError, "SOURCE_DATE_EPOCH"):
                generated_at()
    def test_source_date_epoch_is_converted_in_utc(self):
        with mock.patch.dict("os.environ", {"SOURCE_DATE_EPOCH": "946684800"}, clear=True):
            timestamp = generated_at()
        self.assertEqual("2000-01-01T00:00:00+00:00", timestamp)
        self.assertTrue(timestamp.endswith("+00:00"))
    def test_same_source_date_epoch_produces_identical_catalogs(self):
        with mock.patch.dict("os.environ", {"SOURCE_DATE_EPOCH": "1767225600"}, clear=True):
            first = build(self.directory, validate_only=True)
            second = build(self.directory, validate_only=True)
        self.assertEqual(first, second)
        self.assertEqual("2026-01-01T00:00:00+00:00", first["generated_at"])
    def test_malformed_json_and_root_documents(self):
        (self.directory / "university.json").write_text("[")
        with self.assertRaisesRegex(DataError, "Invalid JSON"): validate_and_compile(self.directory)
        (self.directory / "university.json").write_text("[]")
        with self.assertRaisesRegex(DataError, "root must be a JSON object"): validate_and_compile(self.directory)
    def test_invalid_scalar_types(self):
        self.assert_invalid("university.json", lambda d: d.update(schema_version="2"), "schema_version.*must be an integer")
        self.reset()
        self.assert_invalid("university.json", lambda d: d.update(schema_version=True), "must be an integer")
    def test_json_array_validator_rejects_arbitrary_iterables(self):
        for value in ((1, 2), {1, 2}, "12", iter([1, 2])):
            errors = ErrorCollector(); self.assertEqual([], validate_array(value, errors, "x.json", "$.items"))
            with self.assertRaisesRegex(DataError, r"x.json:\$\.items: must be an array"): errors.check()
    def test_integer_validator_rejects_boolean(self):
        errors = ErrorCollector(); validate_integer(True, errors, "x.json", "$.count")
        with self.assertRaisesRegex(DataError, "must be an integer"): errors.check()
    def test_reusable_field_validators_reject_each_invalid_shape(self):
        errors = ErrorCollector()
        validate_object([], errors, "fields.json", "$.object")
        validate_string(7, errors, "fields.json", "$.string")
        validate_boolean("true", errors, "fields.json", "$.boolean")
        validate_enum("wrong", {"right"}, errors, "fields.json", "$.enum")
        validate_url("file:///tmp/a", errors, "fields.json", "$.url")
        validate_nullable_date("2026-02-30", errors, "fields.json", "$.date")
        validate_string_array(["ok", 2], errors, "fields.json", "$.strings")
        with self.assertRaises(DataError) as raised: errors.check()
        for path in ("$.object", "$.string", "$.boolean", "$.enum", "$.url", "$.date", "$.strings[1]"):
            self.assertIn(path, str(raised.exception))
    def test_all_source_document_schema_versions_are_required_and_matching(self):
        for relative in ("university.json", "calendars.json", "departments/SAMPLE.json"):
            self.assert_invalid(relative, lambda d: d.update(schema_version=99), "unsupported schema version")
    def test_directory_slug_must_match(self):
        doc=self.load("university.json"); doc["slug"]="another-slug"; self.save("university.json",doc)
        with self.assertRaisesRegex(DataError, "does not match slug"): validate_and_compile(self.directory)
    def test_canonical_source_template_requires_explicit_permission(self):
        with self.assertRaisesRegex(DataError, "does not match slug"):
            validate_and_compile(FIXTURE)
        catalog = validate_and_compile(FIXTURE, allow_template_directory=True)
        self.assertEqual("fictional-template-university", catalog["university"]["slug"])
    def test_correctly_named_copied_fixture_is_valid(self):
        self.assertEqual(
            "fictional-template-university",
            validate_and_compile(self.directory)["university"]["slug"],
        )
    def test_template_permission_does_not_allow_incorrectly_named_copy(self):
        incorrect = Path(self.temp.name) / "university-template"
        self.directory.rename(incorrect)
        with self.assertRaisesRegex(DataError, "does not match slug"):
            validate_and_compile(incorrect, allow_template_directory=True)
    def test_template_permission_does_not_allow_incorrect_production_directory(self):
        production = Path(tempfile.mkdtemp(prefix="incorrect-template-", dir=ROOT / "universities"))
        try:
            shutil.copytree(FIXTURE, production, dirs_exist_ok=True)
            with self.assertRaisesRegex(DataError, "does not match slug"):
                validate_and_compile(production, allow_template_directory=True)
        finally:
            shutil.rmtree(production, ignore_errors=True)
    def test_registry_schema_name_and_path_contract(self):
        path = Path(self.temp.name) / "index.json"
        path.write_text(json.dumps({"schema_version": 2, "universities": [{"slug":"fictional-template-university", "name":"Wrong", "path":"wrong.json"}]}))
        with self.assertRaises(DataError) as raised:
            validate_registry(path, self.load("university.json"))
        message=str(raised.exception)
        self.assertIn("$.schema_version", message); self.assertIn("$.universities[0].name", message); self.assertIn("$.universities[0].path", message)
    def test_department_and_course_code_contract(self):
        self.assert_invalid("departments/SAMPLE.json", lambda d: d["courses"][0].update(code="SAMPLE999"), "must equal normalized department and number")
        self.assert_invalid("departments/SAMPLE.json", lambda d: d["courses"][0].update(number="10-1"), "must equal normalized")
    def test_department_codes_are_normalized_for_comparison(self):
        doc=self.load("departments/SAMPLE.json"); doc["courses"][0]["department"]=" sample "; self.save("departments/SAMPLE.json",doc)
        self.assertEqual("SAMPLE", validate_and_compile(self.directory)["courses"][0]["department"])
    def test_credit_contract(self):
        for credits in (True, "variable", "4-1", -1):
            shutil.rmtree(self.directory); shutil.copytree(FIXTURE, self.directory)
            self.assert_invalid("departments/SAMPLE.json", lambda d, value=credits: d["courses"][0].update(credits=value), "credits")
    def test_actual_boolean_fields(self):
        self.assert_invalid("calendars.json", lambda d: d["academic_calendars"][0].update(is_primary=1), "is_primary must be boolean")
        self.reset()
        self.assert_invalid("calendars.json", lambda d: d["academic_calendars"][0]["terms"][0].update(planning_enabled=1), "planning_enabled must be a boolean")
    def test_planning_enabled_is_required(self):
        self.assert_invalid(
            "calendars.json",
            lambda d: d["academic_calendars"][0]["terms"][-1].pop("planning_enabled"),
            "missing: planning_enabled",
        )
    def test_historical_term_cannot_be_planning_enabled(self):
        self.assert_invalid(
            "calendars.json",
            lambda d: d["academic_calendars"][0]["terms"][0].update(planning_enabled=True),
            "historical term .* cannot be planning-enabled",
        )
    def test_disabled_future_term_is_preserved(self):
        calendars = self.load("calendars.json")
        calendars["academic_calendars"][0]["terms"][-1]["planning_enabled"] = False
        self.save("calendars.json", calendars)
        term = validate_and_compile(self.directory)["academic_calendars"][0]["terms"][-1]
        self.assertEqual("future", term["status"])
        self.assertFalse(term["planning_enabled"])
    def test_http_source_urls_and_multiple_error_paths(self):
        doc=self.load("departments/SAMPLE.json"); doc["department"]["source_url"]="ftp://bad"; doc["courses"][0]["source_url"]="not-a-url"; self.save("departments/SAMPLE.json",doc)
        with self.assertRaises(DataError) as raised: validate_and_compile(self.directory)
        self.assertIn("$.department.source_url", str(raised.exception)); self.assertIn("$.courses[0].source_url", str(raised.exception))
    def test_term_sequence_chronology_and_overlap_contracts(self):
        self.assert_invalid("calendars.json", lambda d: d["academic_calendars"][0]["terms"][1].update(sequence=3), "sequences must be unique")
        self.reset()
        self.assert_invalid("calendars.json", lambda d: d["academic_calendars"][0]["terms"][1].update(start_date="2026-05-01"), "overlap")
        self.reset()
        def reverse(d): d["academic_calendars"][0]["terms"][0]["sequence"],d["academic_calendars"][0]["terms"][1]["sequence"] = 4,3
        self.assert_invalid("calendars.json", reverse, "not chronological")
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
    def test_prerequisite_self_dependency_reports_complete_cycle(self):
        def self_dependency(doc):
            doc["edges"] = [{"source": "SAMPLE101", "target": "SAMPLE101", "kind": "prerequisite"}]
        self.assert_invalid(
            "departments/SAMPLE.json", self_dependency,
            r"Prerequisite cycle detected: SAMPLE101 -> SAMPLE101; source department files: departments/SAMPLE.json",
        )
    def test_two_course_prerequisite_cycle_is_a_hard_failure(self):
        def reverse_dependency(doc):
            doc["edges"].append({"source": "SAMPLE201", "target": "SAMPLE101", "kind": "prerequisite"})
        self.assert_invalid(
            "departments/SAMPLE.json", reverse_dependency,
            r"SAMPLE101 -> SAMPLE201 -> SAMPLE101",
        )
    def test_longer_prerequisite_cycle_reports_every_source_file(self):
        sample = self.load("departments/SAMPLE.json")
        sample["edges"].append({"source": "OTHER101", "target": "SAMPLE101", "kind": "prerequisite"})
        self.save("departments/SAMPLE.json", sample)
        other_course = copy.deepcopy(sample["courses"][0])
        other_course.update(code="OTHER101", department="OTHER", number="101", title="Other Course")
        other_course["offering_history"] = []
        other = {
            "schema_version": 3,
            "department": {"code": "OTHER", "name": "Other Studies", "source_url": "https://example.invalid/other"},
            "courses": [other_course],
            "edges": [{"source": "SAMPLE201", "target": "OTHER101", "kind": "prerequisite"}],
        }
        self.save("departments/OTHER.json", other)
        with self.assertRaises(DataError) as raised:
            validate_and_compile(self.directory)
        message = str(raised.exception)
        self.assertIn("OTHER101 -> SAMPLE101 -> SAMPLE201 -> OTHER101", message)
        self.assertIn("departments/OTHER.json, departments/SAMPLE.json", message)
    def test_acyclic_prerequisite_diamond_is_valid(self):
        doc = self.load("departments/SAMPLE.json")
        self.add_course(doc, 202)
        self.add_course(doc, 301)
        doc["edges"] = [
            {"source": "SAMPLE101", "target": "SAMPLE201", "kind": "prerequisite"},
            {"source": "SAMPLE101", "target": "SAMPLE202", "kind": "prerequisite"},
            {"source": "SAMPLE201", "target": "SAMPLE301", "kind": "prerequisite"},
            {"source": "SAMPLE202", "target": "SAMPLE301", "kind": "prerequisite"},
        ]
        self.save("departments/SAMPLE.json", doc)
        self.assertEqual(4, len(validate_and_compile(self.directory)["edges"]))
    def test_external_prerequisite_source_is_not_a_graph_vertex(self):
        doc = self.load("departments/SAMPLE.json")
        doc["edges"] = [{"source": "EXTERNAL101", "target": "SAMPLE101", "kind": "prerequisite"}]
        self.save("departments/SAMPLE.json", doc)
        edge = validate_and_compile(self.directory)["edges"][0]
        self.assertFalse(edge["source_in_database"])
    def test_corequisite_cycle_is_permissible(self):
        doc = self.load("departments/SAMPLE.json")
        doc["edges"] = [
            {"source": "SAMPLE101", "target": "SAMPLE201", "kind": "corequisite"},
            {"source": "SAMPLE201", "target": "SAMPLE101", "kind": "corequisite"},
        ]
        self.save("departments/SAMPLE.json", doc)
        self.assertEqual(2, len(validate_and_compile(self.directory)["edges"]))
    def test_mixed_cycle_is_permissible_when_corequisite_removal_breaks_it(self):
        doc = self.load("departments/SAMPLE.json")
        doc["edges"] = [
            {"source": "SAMPLE101", "target": "SAMPLE201", "kind": "prerequisite"},
            {"source": "SAMPLE201", "target": "SAMPLE101", "kind": "corequisite"},
        ]
        self.save("departments/SAMPLE.json", doc)
        self.assertEqual(2, len(validate_and_compile(self.directory)["edges"]))
    def test_source_membership_is_always_recomputed(self):
        doc = self.load("departments/SAMPLE.json")
        doc["edges"][0]["source_in_database"] = False
        self.save("departments/SAMPLE.json", doc)
        self.assertTrue(validate_and_compile(self.directory)["edges"][0]["source_in_database"])
    def test_enriched_course_fields_are_recomputed(self):
        departments = self.load("departments/SAMPLE.json")
        departments["courses"][0]["tags"] = ["z", "a", "z"]
        departments["courses"][0]["offering_history"][0].update(
            term_name="fabricated", term_type="fabricated", term_status="fabricated"
        )
        self.save("departments/SAMPLE.json", departments)
        catalog = validate_and_compile(self.directory)
        self.assertEqual(["a", "z"], catalog["courses"][0]["tags"])
        offering = catalog["courses"][0]["offering_history"][0]
        self.assertNotEqual("fabricated", offering["term_name"])
        self.assertNotEqual("fabricated", offering["term_type"])
        self.assertNotEqual("fabricated", offering["term_status"])
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
