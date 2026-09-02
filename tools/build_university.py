#!/usr/bin/env python3
"""Validate one university folder and build its catalog.json and courses.db."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema.sql"
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CALENDAR_SYSTEMS = {"semester", "quarter", "trimester", "hybrid", "custom"}
COURSE_LEVELS = {"undergraduate", "graduate", "professional", "continuing-education", "other"}
EDGE_KINDS = {"prerequisite", "corequisite", "recommended"}
TERM_STATUSES = {"historical", "current", "future"}
OFFERING_STATUSES = {"held", "scheduled", "cancelled"}


class DataError(ValueError):
    pass


def read_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataError(f"Missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise DataError(f"{path} root must be a JSON object")
    return document


def require(record: dict, fields: tuple[str, ...], context: str) -> None:
    if not isinstance(record, dict):
        raise DataError(f"{context} must be a JSON object")
    missing = [field for field in fields if record.get(field) in (None, "")]
    if missing:
        raise DataError(f"{context} is missing: {', '.join(missing)}")


def parse_date(value: str, context: str) -> dt.date:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise DataError(f"{context} must be YYYY-MM-DD, got {value!r}")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise DataError(f"{context} is not a real date: {value}") from exc


def validate_and_compile(university_dir: Path) -> dict:
    university = read_json(university_dir / "university.json")
    calendar_doc = read_json(university_dir / "calendars.json")
    require(
        university,
        (
            "slug", "name", "short_name", "map_title", "primary_color",
            "secondary_color", "accent_color", "catalog_date", "schema_version",
            "academic_calendar_system",
        ),
        "university.json",
    )
    scalar_types = {"slug": str, "name": str, "short_name": str, "map_title": str,
                    "primary_color": str, "secondary_color": str, "accent_color": str,
                    "catalog_date": str, "schema_version": int, "academic_calendar_system": str}
    for field, expected in scalar_types.items():
        if isinstance(university[field], bool) or not isinstance(university[field], expected):
            raise DataError(f"university.json {field} must be {expected.__name__}")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", university["slug"]):
        raise DataError("university.json slug must contain lowercase letters, digits, and hyphens")
    if university_dir.parent.name == "universities" and university_dir.name != university["slug"]:
        raise DataError(f"University directory {university_dir.name!r} does not match slug {university['slug']!r}")
    if university["academic_calendar_system"] not in CALENDAR_SYSTEMS:
        raise DataError(f"Unknown academic_calendar_system: {university['academic_calendar_system']}")
    for field in ("primary_color", "secondary_color", "accent_color"):
        if not COLOR_RE.fullmatch(university[field]):
            raise DataError(f"university.json {field} must be a six-digit hex color")
    parse_date(university["catalog_date"], "university.json catalog_date")

    calendars = calendar_doc.get("academic_calendars", [])
    if not isinstance(calendars, list):
        raise DataError("calendars.json academic_calendars must be an array")
    if not calendars:
        raise DataError("calendars.json must contain at least one academic calendar")
    calendar_ids: set[str] = set()
    term_by_code: dict[str, dict] = {}
    primary_count = 0
    for calendar in calendars:
        require(calendar, ("id", "name", "system_type", "is_primary", "terms"), "academic calendar")
        if not isinstance(calendar["is_primary"], bool) or not isinstance(calendar["terms"], list):
            raise DataError("academic calendar is_primary must be boolean and terms must be an array")
        if calendar["id"] in calendar_ids:
            raise DataError(f"Duplicate academic calendar id: {calendar['id']}")
        calendar_ids.add(calendar["id"])
        primary_count += int(bool(calendar["is_primary"]))
        if calendar["system_type"] not in CALENDAR_SYSTEMS:
            raise DataError(f"Unknown calendar system_type: {calendar['system_type']}")
        for term in calendar["terms"]:
            require(
                term,
                ("code", "name", "academic_year", "term_type", "sequence", "start_date", "end_date", "status"),
                f"term in {calendar['id']}",
            )
            if term["code"] in term_by_code:
                raise DataError(f"Duplicate term code across calendars: {term['code']}")
            start = parse_date(term["start_date"], f"term {term['code']} start_date")
            end = parse_date(term["end_date"], f"term {term['code']} end_date")
            if start > end:
                raise DataError(f"term {term['code']} starts after it ends")
            if term["status"] not in TERM_STATUSES:
                raise DataError(f"term {term['code']} has unknown status {term['status']!r}")
            term.setdefault("planning_enabled", term["status"] in {"current", "future"})
            term_by_code[term["code"]] = {**term, "calendar_id": calendar["id"]}
    if primary_count != 1:
        raise DataError("Exactly one academic calendar must set is_primary to true")

    department_dir = university_dir / "departments"
    department_files = sorted(department_dir.glob("*.json"))
    if not department_files:
        raise DataError(f"No department JSON files found in {department_dir}")

    departments: list[dict] = []
    courses: list[dict] = []
    edges: list[dict] = []
    department_codes: set[str] = set()
    course_codes: set[str] = set()
    edge_keys: set[tuple[str, str, str]] = set()

    for path in department_files:
        document = read_json(path)
        department = document.get("department", {})
        require(department, ("code", "name"), str(path))
        code = department["code"].upper()
        if code in department_codes:
            raise DataError(f"Duplicate department code: {code}")
        if path.stem.upper() != code:
            raise DataError(f"{path.name} must match department code {code}.json")
        department["code"] = code
        department_codes.add(code)
        departments.append(department)
        if not isinstance(document.get("courses", []), list) or not isinstance(document.get("edges", []), list):
            raise DataError(f"{path} courses and edges must be arrays")
        for course in document.get("courses", []):
            require(course, ("code", "number", "level", "title", "credits"), f"course in {path.name}")
            course["code"] = course["code"].replace(" ", "").upper()
            course.setdefault("department", code)
            if course["department"] != code:
                raise DataError(f"Course {course['code']} belongs in {course['department']}.json, not {path.name}")
            if course["code"] in course_codes:
                raise DataError(f"Duplicate course code: {course['code']}")
            if course["level"] not in COURSE_LEVELS:
                raise DataError(f"Course {course['code']} has unsupported level {course['level']!r}")
            course_codes.add(course["code"])
            course.setdefault("description", "")
            course.setdefault("prerequisites", "")
            course.setdefault("corequisites", "")
            course.setdefault("restrictions", "")
            course.setdefault("repeatable", "")
            course.setdefault("source_url", department.get("source_url", university.get("catalog_url", "")))
            course.setdefault("source_catalog", course["level"])
            course["tags"] = sorted(set(course.get("tags", [])))
            course.setdefault("offering_history", [])
            courses.append(course)
        for edge in document.get("edges", []):
            require(edge, ("source", "target", "kind"), f"edge in {path.name}")
            edge["source"] = edge["source"].replace(" ", "").upper()
            edge["target"] = edge["target"].replace(" ", "").upper()
            if edge["kind"] not in EDGE_KINDS:
                raise DataError(f"Edge {edge['source']} -> {edge['target']} has unknown kind {edge['kind']!r}")
            key = (edge["source"], edge["target"], edge["kind"])
            if key in edge_keys:
                raise DataError(f"Duplicate edge: {key}")
            edge_keys.add(key)
            edges.append(edge)

    for edge in edges:
        if edge["target"] not in course_codes:
            raise DataError(f"Edge target {edge['target']} is not present in any department file")
        target_department = next(course["department"] for course in courses if course["code"] == edge["target"])
        edge.setdefault("source_in_database", edge["source"] in course_codes)
        if not edge.get("logic_operator"):
            edge.pop("logic_operator", None)
        if not edge.get("logic_group"):
            edge.pop("logic_group", None)
        if target_department not in department_codes:
            raise DataError(f"Edge target {edge['target']} has invalid department")

    for course in courses:
        enriched_history = []
        seen_offerings: set[str] = set()
        for offering in course.get("offering_history", []):
            require(offering, ("term_code", "offering_status"), f"offering for {course['code']}")
            term_code = offering["term_code"]
            if term_code not in term_by_code:
                raise DataError(f"Offering for {course['code']} references unknown term {term_code}")
            if term_code in seen_offerings:
                raise DataError(f"Course {course['code']} repeats offering term {term_code}")
            if offering["offering_status"] not in OFFERING_STATUSES:
                raise DataError(f"Offering for {course['code']} has unknown status {offering['offering_status']!r}")
            seen_offerings.add(term_code)
            term = term_by_code[term_code]
            enriched_history.append({
                "term_code": term_code,
                "term_name": term["name"],
                "term_type": term["term_type"],
                "term_status": term["status"],
                "offering_status": offering["offering_status"],
                "source_url": offering.get("source_url", ""),
            })
        course["offering_history"] = enriched_history

    courses.sort(key=lambda item: item["code"])
    edges.sort(key=lambda item: (item["target"], item["kind"], item["source"]))
    departments.sort(key=lambda item: item["code"])
    return {
        "schema_version": university["schema_version"],
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "university": university,
        "departments": departments,
        "academic_calendars": calendars,
        "courses": courses,
        "edges": edges,
    }


def write_database(path: Path, catalog: dict) -> None:
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        university = catalog["university"]
        connection.execute(
            "INSERT INTO university VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(university.get(field, "") for field in (
                "slug", "name", "short_name", "map_title", "primary_color", "secondary_color",
                "accent_color", "catalog_url", "catalog_date", "schema_version", "academic_calendar_system",
            )),
        )
        for department in catalog["departments"]:
            connection.execute(
                "INSERT INTO departments VALUES (?, ?, ?, ?)",
                (department["code"], department["name"], department.get("school", ""), department.get("source_url", "")),
            )
        for calendar in catalog["academic_calendars"]:
            connection.execute(
                "INSERT INTO academic_calendars VALUES (?, ?, ?, ?, ?, ?)",
                (calendar["id"], university["slug"], calendar["name"], calendar["system_type"], int(calendar["is_primary"]), calendar.get("source_url", "")),
            )
            for term in calendar["terms"]:
                connection.execute(
                    "INSERT INTO academic_terms (calendar_id, code, name, academic_year, term_type, sequence, start_date, end_date, status, planning_enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (calendar["id"], term["code"], term["name"], term["academic_year"], term["term_type"], term["sequence"], term["start_date"], term["end_date"], term["status"], int(term["planning_enabled"])),
                )
        for course in catalog["courses"]:
            connection.execute(
                "INSERT INTO courses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(course.get(field, "") for field in (
                    "code", "department", "number", "level", "title", "credits", "description",
                    "prerequisites", "corequisites", "restrictions", "repeatable", "source_url", "source_catalog",
                )),
            )
            for tag in course["tags"]:
                connection.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
                tag_id = connection.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()[0]
                connection.execute("INSERT INTO course_tags VALUES (?, ?)", (course["code"], tag_id))
            for offering in course["offering_history"]:
                term_id = connection.execute("SELECT id FROM academic_terms WHERE code = ?", (offering["term_code"],)).fetchone()[0]
                connection.execute(
                    "INSERT INTO course_offerings VALUES (?, ?, ?, ?)",
                    (course["code"], term_id, offering["offering_status"], offering.get("source_url", "")),
                )
        for edge in catalog["edges"]:
            connection.execute(
                "INSERT INTO prerequisite_edges VALUES (?, ?, ?, ?, ?, ?)",
                (edge["source"], edge["target"], edge["kind"], int(edge["source_in_database"]), edge.get("logic_group"), edge.get("logic_operator")),
            )
        connection.commit()
    finally:
        connection.close()


def build(university_dir: Path, validate_only: bool = False) -> dict:
    university_dir = university_dir.resolve()
    catalog = validate_and_compile(university_dir)
    if not validate_only:
        (university_dir / "catalog.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        write_database(university_dir / "courses.db", catalog)
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("university_dir", type=Path, help="Folder containing university.json, calendars.json, and departments/")
    parser.add_argument("--validate-only", action="store_true", help="Validate without writing catalog.json or courses.db")
    args = parser.parse_args()
    try:
        catalog = build(args.university_dir, args.validate_only)
    except DataError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    action = "Validated" if args.validate_only else "Built"
    print(f"{action} {catalog['university']['name']}: {len(catalog['departments'])} departments, {len(catalog['courses'])} courses, {len(catalog['edges'])} relationships")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
