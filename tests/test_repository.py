from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_university import build, normalize_credits, validate_registry  # noqa: E402
from check_prohibited_terms import violations  # noqa: E402
from check_llm_instructions import instruction_errors  # noqa: E402


class RepositoryTests(unittest.TestCase):
    def test_readme_links_to_authoritative_llm_guide(self) -> None:
        self.assertEqual(instruction_errors(ROOT), [])

    def test_llm_guide_credit_examples_match_validator_grammar(self) -> None:
        guide = (ROOT / "template" / "university-template" / "LLM-SCRAPING-GUIDE.md").read_text(encoding="utf-8")
        course_rules = re.split(r"\n#{1,4} ", guide.split("#### COURSE RULES", 1)[1], maxsplit=1)[0]
        normalized_rules = " ".join(course_rules.split())

        def documented_examples(label: str) -> list[object]:
            sentence = re.search(rf"{label} examples: (.*?)\.(?: Do| Preserve)", course_rules, re.DOTALL)
            self.assertIsNotNone(sentence)
            return [json.loads(value) for value in re.findall(r"`([^`]+)`", sentence.group(1))]

        accepted = documented_examples("Accepted")
        rejected = documented_examples("Rejected")
        self.assertEqual([3, "3", "1-4"], accepted)
        self.assertEqual(["3 credits", "variable", "3, 4", "4-1"], rejected)
        self.assertTrue(all(normalize_credits(value) is not None for value in accepted))
        self.assertTrue(all(normalize_credits(value) is None for value in rejected))
        for terminology in (
            "non-negative JSON number",
            "numeric string",
            "ascending numeric range",
            "units",
            "comma-separated alternatives",
            "descending ranges",
            "appropriate prose field",
            "provenance",
            "never invent a numeric value",
        ):
            self.assertIn(terminology, normalized_rules)

    def test_production_registry_is_consistent(self) -> None:
        registry = validate_registry(ROOT / "universities" / "index.json")
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
