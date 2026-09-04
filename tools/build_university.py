#!/usr/bin/env python3
"""Validate one university folder and build its catalog.json and courses.db."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema.sql"
TEMPLATE_DIRECTORY = (ROOT / "template" / "university-template").resolve()
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CALENDAR_SYSTEMS = {"semester", "quarter", "trimester", "hybrid", "custom"}
COURSE_LEVELS = {"undergraduate", "graduate", "professional", "continuing-education", "other"}
EDGE_KINDS = {"prerequisite", "corequisite", "recommended"}
LOGIC_OPERATORS = {"AND", "OR"}
TERM_STATUSES = {"historical", "current", "future"}
DATE_STATUSES = {"official", "unpublished"}
OFFERING_STATUSES = {"held", "scheduled", "cancelled"}
DATA_SCHEMA_VERSION = 3
REGISTRY_SCHEMA_VERSION = 1
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DEPARTMENT_RE = re.compile(r"^[A-Z][A-Z0-9]{1,11}$")
COURSE_NUMBER_RE = re.compile(r"^[0-9]{1,4}[A-Z]?$")
CREDITS_RE = re.compile(r"^(?:0|[1-9]\d*)(?:\.\d+)?(?:-(?:0|[1-9]\d*)(?:\.\d+)?)?$")


class DataError(ValueError):
    pass


def normalize_credits(value: object) -> str | None:
    """Return the validator's canonical credit text, or None when unsupported."""
    credit_text = str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value
    if not isinstance(credit_text, str) or not CREDITS_RE.fullmatch(credit_text):
        return None
    if "-" in credit_text and float(credit_text.split("-")[0]) > float(credit_text.split("-")[1]):
        return None
    return credit_text


def generated_at() -> str:
    """Return the build timestamp, honoring the reproducible-build convention."""
    value = os.environ.get("SOURCE_DATE_EPOCH")
    if value is None:
        timestamp = dt.datetime.now(dt.timezone.utc)
    else:
        try:
            epoch = int(value)
            if epoch < 0:
                raise ValueError
            timestamp = dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
        except (ValueError, OverflowError, OSError) as exc:
            raise DataError(
                "SOURCE_DATE_EPOCH must be a non-negative integer Unix timestamp"
            ) from exc
    return timestamp.replace(microsecond=0).isoformat()


class ErrorCollector:
    """Accumulate independent input errors and raise them together."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def add(self, filename: Path | str, json_path: str, message: str) -> None:
        self.errors.append(f"{filename}:{json_path}: {message}")

    def check(self) -> None:
        if self.errors:
            raise DataError("Validation failed:\n- " + "\n- ".join(self.errors))


def _type(value: object, expected: type) -> bool:
    return isinstance(value, expected) and not (expected is int and isinstance(value, bool))


def validate_object(value: object, errors: ErrorCollector, filename: Path | str, path: str) -> dict:
    if not isinstance(value, dict):
        errors.add(filename, path, "must be an object")
        return {}
    return value


def validate_array(value: object, errors: ErrorCollector, filename: Path | str, path: str) -> list:
    # Deliberately accept JSON arrays only, not tuples, sets, generators, or strings.
    if not isinstance(value, list):
        errors.add(filename, path, "must be an array")
        return []
    return value


def validate_string(value: object, errors: ErrorCollector, filename: Path | str, path: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        errors.add(filename, path, "must be a non-empty string" if nonempty else "must be a string")
        return ""
    return value


def validate_integer(value: object, errors: ErrorCollector, filename: Path | str, path: str) -> int:
    if not _type(value, int):
        errors.add(filename, path, "must be an integer")
        return 0
    return value


def validate_boolean(value: object, errors: ErrorCollector, filename: Path | str, path: str) -> bool:
    if not isinstance(value, bool):
        errors.add(filename, path, "must be a boolean")
        return False
    return value


def validate_enum(value: object, choices: set[str], errors: ErrorCollector, filename: Path | str, path: str) -> str:
    value = validate_string(value, errors, filename, path)
    if value and value not in choices:
        errors.add(filename, path, f"must be one of {sorted(choices)}, got {value!r}")
    return value


def validate_url(value: object, errors: ErrorCollector, filename: Path | str, path: str, *, required: bool = True) -> str:
    value = validate_string(value, errors, filename, path, nonempty=required)
    if value:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.add(filename, path, "must be an HTTP(S) URL")
    return value


def validate_nullable_date(value: object, errors: ErrorCollector, filename: Path | str, path: str) -> dt.date | None:
    if value is None:
        return None
    try:
        return parse_date(value, f"{filename}:{path}")
    except DataError as exc:
        errors.add(filename, path, str(exc).split(": ", 1)[-1])
        return None


def validate_string_array(value: object, errors: ErrorCollector, filename: Path | str, path: str) -> list[str]:
    values = validate_array(value, errors, filename, path)
    for index, item in enumerate(values):
        validate_string(item, errors, filename, f"{path}[{index}]")
    return [item for item in values if isinstance(item, str)]


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


def validate_registry(registry_path: Path, catalog_metadata: dict | None = None) -> dict:
    """Validate the registry, optionally checking one compiled catalog's metadata."""
    registry = read_json(registry_path)
    errors = ErrorCollector()
    version = validate_integer(registry.get("schema_version"), errors, registry_path, "$.schema_version")
    if version != REGISTRY_SCHEMA_VERSION:
        errors.add(registry_path, "$.schema_version", f"unsupported schema version {version}; expected {REGISTRY_SCHEMA_VERSION}")
    entries = validate_array(registry.get("universities"), errors, registry_path, "$.universities")
    seen: set[str] = set()
    for index, raw_entry in enumerate(entries):
        path = f"$.universities[{index}]"
        entry = validate_object(raw_entry, errors, registry_path, path)
        slug = validate_string(entry.get("slug"), errors, registry_path, path + ".slug")
        validate_string(entry.get("name"), errors, registry_path, path + ".name")
        validate_string(entry.get("path"), errors, registry_path, path + ".path")
        if slug in seen:
            errors.add(registry_path, path + ".slug", f"duplicate slug {slug!r}")
        seen.add(slug)
    if catalog_metadata:
        slug = catalog_metadata["slug"]
        matches = [(i, entry) for i, entry in enumerate(entries) if isinstance(entry, dict) and entry.get("slug") == slug]
        if len(matches) != 1:
            errors.add(registry_path, "$.universities", f"must contain exactly one entry for slug {slug!r}")
        else:
            index, entry = matches[0]
            expected_path = f"universities/{slug}/catalog.json"
            if entry.get("name") != catalog_metadata["name"]:
                errors.add(registry_path, f"$.universities[{index}].name", f"must match catalog name {catalog_metadata['name']!r}")
            if entry.get("path") != expected_path:
                errors.add(registry_path, f"$.universities[{index}].path", f"must match compiled catalog path {expected_path!r}")
    errors.check()
    return registry


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


def validate_prerequisite_graph(
    edges: list[dict], course_codes: set[str], edge_files: dict[int, Path], university_dir: Path
) -> None:
    """Reject cycles made entirely of internal prerequisite relationships.

    Corequisite (and recommended) edges deliberately do not impose an ordering and
    are therefore excluded.  Consequently, a mixed-kind cycle is permissible when
    removing its non-prerequisite edges breaks the cycle; it is invalid only when
    the prerequisite-only subgraph still contains a cycle.
    """
    adjacency: dict[str, list[tuple[str, Path]]] = {code: [] for code in course_codes}
    for edge in edges:
        if (
            edge["kind"] == "prerequisite"
            and edge["source"] in course_codes
            and edge["target"] in course_codes
        ):
            adjacency[edge["source"]].append(
                (edge["target"], edge_files[id(edge)])
            )
    for neighbors in adjacency.values():
        neighbors.sort(key=lambda item: item[0])

    state: dict[str, int] = {}
    node_stack: list[str] = []
    edge_stack: list[Path] = []

    def visit(node: str) -> None:
        state[node] = 1
        node_stack.append(node)
        for target, filename in adjacency[node]:
            if state.get(target, 0) == 0:
                edge_stack.append(filename)
                visit(target)
                edge_stack.pop()
            elif state[target] == 1:
                start = node_stack.index(target)
                cycle = node_stack[start:] + [target]
                files = edge_stack[start:] + [filename]
                source_files = sorted(
                    {str(path.relative_to(university_dir)) for path in files}
                )
                raise DataError(
                    "Prerequisite cycle detected: "
                    + " -> ".join(cycle)
                    + "; source department files: "
                    + ", ".join(source_files)
                )
        node_stack.pop()
        state[node] = 2

    for code in sorted(course_codes):
        if state.get(code, 0) == 0:
            visit(code)


def validate_and_compile(
    university_dir: Path,
    *,
    allow_template_directory: bool = False,
    check_directory_name: bool = True,
) -> dict:
    """Validate source data, with configurable checks for its containing directory."""
    university_dir = university_dir.resolve()
    university = read_json(university_dir / "university.json")
    calendar_doc = read_json(university_dir / "calendars.json")
    errors = ErrorCollector()
    university_file = university_dir / "university.json"
    calendar_file = university_dir / "calendars.json"
    for document, filename in ((university, university_file), (calendar_doc, calendar_file)):
        version = validate_integer(document.get("schema_version"), errors, filename, "$.schema_version")
        if version != DATA_SCHEMA_VERSION:
            errors.add(filename, "$.schema_version", f"unsupported schema version {version}; expected {DATA_SCHEMA_VERSION}")
    errors.check()
    require(
        university,
        (
            "slug", "name", "short_name", "map_title", "primary_color",
            "secondary_color", "accent_color", "catalog_date", "schema_version",
            "academic_calendar_system", "catalog_url",
        ),
        "university.json",
    )
    scalar_types = {"slug": str, "name": str, "short_name": str, "map_title": str,
                    "primary_color": str, "secondary_color": str, "accent_color": str,
                    "catalog_date": str, "schema_version": int, "academic_calendar_system": str}
    for field, expected in scalar_types.items():
        if isinstance(university[field], bool) or not isinstance(university[field], expected):
            raise DataError(f"university.json {field} must be {expected.__name__}")
    if not SLUG_RE.fullmatch(university["slug"]):
        raise DataError("university.json slug must contain lowercase letters, digits, and hyphens")
    is_canonical_template = allow_template_directory and university_dir == TEMPLATE_DIRECTORY
    if (
        check_directory_name
        and university_dir.name != university["slug"]
        and not is_canonical_template
    ):
        raise DataError(f"University directory {university_dir.name!r} does not match slug {university['slug']!r}")
    if university["academic_calendar_system"] not in CALENDAR_SYSTEMS:
        raise DataError(f"Unknown academic_calendar_system: {university['academic_calendar_system']}")
    for field in ("primary_color", "secondary_color", "accent_color"):
        if not COLOR_RE.fullmatch(university[field]):
            raise DataError(f"university.json {field} must be a six-digit hex color")
    parse_date(university["catalog_date"], "university.json catalog_date")
    validate_url(university["catalog_url"], errors, university_file, "$.catalog_url")
    errors.check()

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
        validate_url(calendar.get("source_url"), errors, calendar_file, f"$.academic_calendars[{len(calendar_ids)}].source_url")
        if calendar["id"] in calendar_ids:
            raise DataError(f"Duplicate academic calendar id: {calendar['id']}")
        calendar_ids.add(calendar["id"])
        primary_count += int(bool(calendar["is_primary"]))
        if calendar["system_type"] not in CALENDAR_SYSTEMS:
            raise DataError(f"Unknown calendar system_type: {calendar['system_type']}")
        for term in calendar["terms"]:
            require(
                term,
                (
                    "code", "name", "academic_year", "term_type", "sequence",
                    "dates_status", "status", "planning_enabled",
                ),
                f"term in {calendar['id']}",
            )
            if term["code"] in term_by_code:
                raise DataError(f"Duplicate term code across calendars: {term['code']}")
            if not isinstance(term["academic_year"], str) or not re.fullmatch(r"\d{4}-\d{4}", term["academic_year"]):
                raise DataError(f"term {term['code']} academic_year must be YYYY-YYYY")
            first_year, second_year = map(int, term["academic_year"].split("-"))
            if second_year != first_year + 1:
                raise DataError(f"term {term['code']} academic_year must contain consecutive years")
            if isinstance(term["sequence"], bool) or not isinstance(term["sequence"], int):
                raise DataError(f"term {term['code']} sequence must be an integer")
            if term["dates_status"] not in DATE_STATUSES:
                raise DataError(f"term {term['code']} has unknown dates_status {term['dates_status']!r}")
            if "start_date" not in term or "end_date" not in term:
                raise DataError(f"term {term['code']} must explicitly provide start_date and end_date")
            start_value, end_value = term.get("start_date"), term.get("end_date")
            if (start_value is None) != (end_value is None):
                raise DataError(f"term {term['code']} must provide both start_date and end_date, or set both to null")
            if term["dates_status"] == "official":
                if start_value is None:
                    raise DataError(f"term {term['code']} with official dates_status requires both dates")
                if not calendar.get("source_url"):
                    raise DataError(f"term {term['code']} published dates require calendar source_url metadata")
                start = parse_date(start_value, f"term {term['code']} start_date")
                end = parse_date(end_value, f"term {term['code']} end_date")
                if start > end:
                    raise DataError(f"term {term['code']} starts after it ends")
            elif start_value is not None:
                raise DataError(f"term {term['code']} with unpublished dates_status must set both dates to null")
            if term["status"] not in TERM_STATUSES:
                raise DataError(f"term {term['code']} has unknown status {term['status']!r}")
            if not isinstance(term["planning_enabled"], bool):
                raise DataError(f"term {term['code']} planning_enabled must be a boolean")
            if term["status"] == "historical" and term["planning_enabled"]:
                raise DataError(f"historical term {term['code']} cannot be planning-enabled")
            term_by_code[term["code"]] = {**term, "calendar_id": calendar["id"]}
        by_year: dict[str, list[int]] = {}
        for item in calendar["terms"]:
            by_year.setdefault(item["academic_year"], []).append(item["sequence"])
        if any(len(values) != len(set(values)) for values in by_year.values()):
            raise DataError(f"calendar {calendar['id']} term sequences must be unique within each academic year")
        official = sorted(
            (item for item in calendar["terms"] if item["dates_status"] == "official"),
            key=lambda item: (item["academic_year"], item["sequence"]),
        )
        for previous, current in zip(official, official[1:]):
            previous_start = parse_date(previous["start_date"], f"term {previous['code']} start_date")
            current_start = parse_date(current["start_date"], f"term {current['code']} start_date")
            previous_end = parse_date(previous["end_date"], f"term {previous['code']} end_date")
            if current_start < previous_start:
                raise DataError(f"calendar {calendar['id']} official terms are not chronological by sequence")
            if current_start <= previous_end:
                raise DataError(f"calendar {calendar['id']} terms {previous['code']} and {current['code']} overlap")
    errors.check()
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
    edge_files: dict[int, Path] = {}

    for path in department_files:
        document = read_json(path)
        version = validate_integer(document.get("schema_version"), errors, path, "$.schema_version")
        if version != DATA_SCHEMA_VERSION:
            errors.add(path, "$.schema_version", f"unsupported schema version {version}; expected {DATA_SCHEMA_VERSION}")
        department = document.get("department", {})
        require(department, ("code", "name"), str(path))
        code = department["code"].strip().upper()
        if not DEPARTMENT_RE.fullmatch(code):
            errors.add(path, "$.department.code", "must be 2-12 uppercase letters or digits, beginning with a letter")
        if code in department_codes:
            raise DataError(f"Duplicate department code: {code}")
        if path.stem.upper() != code:
            raise DataError(f"{path.name} must match department code {code}.json")
        department["code"] = code
        department_codes.add(code)
        departments.append(department)
        validate_url(department.get("source_url"), errors, path, "$.department.source_url")
        if not isinstance(document.get("courses", []), list) or not isinstance(document.get("edges", []), list):
            raise DataError(f"{path} courses and edges must be arrays")
        for course_index, course in enumerate(document.get("courses", [])):
            require(course, ("code", "number", "level", "title", "credits"), f"course in {path.name}")
            course["code"] = course["code"].replace(" ", "").upper()
            number = str(course["number"]).strip().upper()
            supplied_department = str(course.get("department", code)).strip().upper()
            if supplied_department != code:
                raise DataError(f"Course {course['code']} belongs in {course['department']}.json, not {path.name}")
            course["department"] = code
            course["number"] = number
            if not COURSE_NUMBER_RE.fullmatch(number) or course["code"] != code + number:
                errors.add(path, f"$.courses[{course_index}].code", f"must equal normalized department and number ({code + number})")
            if course["code"] in course_codes:
                raise DataError(f"Duplicate course code: {course['code']}")
            if course["level"] not in COURSE_LEVELS:
                raise DataError(f"Course {course['code']} has unsupported level {course['level']!r}")
            course_codes.add(course["code"])
            credit_text = normalize_credits(course["credits"])
            if credit_text is None:
                errors.add(path, f"$.courses[{course_index}].credits", "must be a non-negative number or numeric string/range such as '3' or '1-4'")
            else:
                course["credits"] = credit_text
            for field in ("description", "prerequisites", "corequisites", "restrictions", "repeatable"):
                course.setdefault(field, "")
            course["source_url"] = course.get("source_url") or department.get("source_url", university.get("catalog_url", ""))
            validate_url(course["source_url"], errors, path, f"$.courses[{course_index}].source_url")
            course.setdefault("source_catalog", course["level"])
            course["tags"] = sorted(set(validate_string_array(course.get("tags", []), errors, path, f"$.courses[{course_index}].tags")))
            course["offering_history"] = validate_array(course.get("offering_history", []), errors, path, f"$.courses[{course_index}].offering_history")
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
            edge_files[id(edge)] = path

    errors.check()

    for edge in edges:
        if edge["target"] not in course_codes:
            raise DataError(f"Edge target {edge['target']} is not present in any department file")
        target_department = next(course["department"] for course in courses if course["code"] == edge["target"])
        actual_source_in_database = edge["source"] in course_codes
        edge["source_in_database"] = actual_source_in_database
        has_group = "logic_group" in edge
        has_operator = "logic_operator" in edge
        if has_group != has_operator:
            raise DataError(f"Edge {edge['source']} -> {edge['target']} must provide logic_group and logic_operator together")
        if has_group:
            if not isinstance(edge["logic_group"], str) or not edge["logic_group"].strip():
                raise DataError(f"Edge {edge['source']} -> {edge['target']} logic_group must be a non-empty string")
            if edge["logic_operator"] not in LOGIC_OPERATORS:
                raise DataError(f"Edge {edge['source']} -> {edge['target']} has unknown logic_operator {edge['logic_operator']!r}")
        if target_department not in department_codes:
            raise DataError(f"Edge target {edge['target']} has invalid department")

    logic_groups: dict[str, list[dict]] = {}
    for edge in edges:
        if "logic_group" in edge:
            logic_groups.setdefault(edge["logic_group"], []).append(edge)
    for name, members in logic_groups.items():
        if len(members) < 2:
            raise DataError(f"Logic group {name!r} must contain at least two edges")
        signatures = {(edge["target"], edge["kind"], edge["logic_operator"]) for edge in members}
        if len(signatures) != 1:
            raise DataError(f"Logic group {name!r} has contradictory target, kind, or operator metadata")

    # Prerequisites impose strict before/after ordering, so their cycles are hard
    # validation failures. Exceptional catalog prose must be modeled explicitly
    # (for example, as a corequisite), rather than bypassed with an override.
    validate_prerequisite_graph(edges, course_codes, edge_files, university_dir)

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
            validate_url(offering.get("source_url", ""), errors, "department course offering", f"$.courses[{course['code']}].offering_history[{term_code}].source_url", required=False)
        course["offering_history"] = enriched_history

    errors.check()

    # A checked-in university must agree with its registry and compiled metadata.
    if university_dir.parent == ROOT / "universities":
        registry_path = ROOT / "universities" / "index.json"
        validate_registry(registry_path, university)

    courses.sort(key=lambda item: item["code"])
    edges.sort(key=lambda item: (item["target"], item["kind"], item["source"]))
    departments.sort(key=lambda item: item["code"])
    return {
        "schema_version": university["schema_version"],
        "generated_at": generated_at(),
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
                    "INSERT INTO academic_terms (calendar_id, code, name, academic_year, term_type, sequence, start_date, end_date, dates_status, status, planning_enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (calendar["id"], term["code"], term["name"], term["academic_year"], term["term_type"], term["sequence"], term["start_date"], term["end_date"], term["dates_status"], term["status"], int(term["planning_enabled"])),
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


def build(
    university_dir: Path,
    validate_only: bool = False,
    *,
    allow_template_directory: bool = False,
) -> dict:
    university_dir = university_dir.resolve()
    catalog = validate_and_compile(
        university_dir, allow_template_directory=allow_template_directory
    )
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
