# LLM university data collection and archive contract

This document is a self-contained prompt for a browsing-capable LLM or coding
agent. Supply it unchanged with only (a) the university's name **or** one official
university starting URL and (b) the requested departments. The agent must discover
the remaining official sources and return an import-ready ZIP. Human review is
still required because catalogs often express prerequisite alternatives, minimum
grades, permissions, cross-listings, variable credits, and exceptions in prose.

## Input to append to this prompt

```text
University name OR official university starting URL: <ONE VALUE>
Requested departments: <OFFICIAL SUBJECT CODES OR DEPARTMENT NAMES>
```

If a department name is supplied instead of a subject code, determine its code
from the official catalog. Do not ask for catalog, registrar, schedule, academic
year, slug, or snapshot-date fields unless official sources genuinely leave the
request ambiguous. Use the date on which browsing occurs as the snapshot date.

## Your task

Collect verified university metadata, academic calendars, courses, relationships,
and offering history for the requested departments. The field contract below is
self-contained and uses schema version 3. If
`template/university-template/README.md` is also available, use it as supplementary
documentation; the only required user inputs remain the institution and requested
departments.

### 1. Discover and verify official sources

1. Resolve the supplied name to the institution's official website, or verify that
   the supplied URL is controlled by the named institution. Treat redirects and
   separate official catalog/schedule hosts as valid only when the official site
   links to them or clearly identifies them as its service provider.
2. Starting at that official page, inspect navigation, sitemaps, and on-site search
   for links labelled **Academics**, **Catalog**, **Courses**, **Registrar**,
   **Academic Calendar**, **Class Schedule**, **Course Search**, or equivalent.
   Follow official links to find, in order:
   - the current course catalog and requested subject pages;
   - the registrar's authoritative academic-calendar page or document; and
   - public term-specific schedules, archives, downloads, or APIs.
3. If navigation is insufficient, use a web search restricted to the verified
   official domain(s), with queries such as `site:official.example catalog`,
   `site:official.example registrar academic calendar`, and
   `site:official.example schedule of classes`. A search result or snippet is only
   a discovery lead: open the official page and verify the fact there.
4. Prefer official structured downloads or public APIs over scraping rendered
   pages. Record the final exact official URL for every department, course,
   calendar, and term-specific offering. Record the official catalog edition when
   it is stated.
5. Do not use aggregators, social media, search snippets, degree-planning sites, or
   another institution's equivalency pages as evidence. Never infer an unpublished
   date, course, subject code, credit value, relationship, or offering. Use an
   empty offering-history array or `null` unpublished calendar dates where the
   schema permits, and document the gap.
6. Respect robots instructions, authentication, access controls, rate limits, and
   terms of use. Do not bypass a login, CAPTCHA, anti-bot control, paywall, or other
   restriction. Slow or stop requests when required. List every relevant source
   that was inaccessible; do not fill the resulting gaps from guesses.

### 2. Derive and validate the slug

Derive one stable slug from the official university name: Unicode-normalize and
transliterate where possible, lowercase it, replace each run of non-alphanumeric
characters with one hyphen, and remove leading/trailing hyphens. Validate the
result against `^[a-z0-9]+(?:-[a-z0-9]+)*$`. It must be non-empty and must match
the `slug` in `university.json` and the archive's directory name. If transliteration
is ambiguous, report the ambiguity and ask for a slug rather than choosing
nondeterministically.

### 3. Deterministic ZIP output contract

The deliverable is `<slug>.zip`. Return it as an attached **downloadable artifact**;
merely printing JSON, Markdown, a base64 string, or a filesystem path in chat does
not satisfy the task.

The ZIP must contain exactly one top-level directory named `<slug>/`. Directory
entries themselves are optional, but the only file paths allowed are:

```text
<slug>/university.json
<slug>/calendars.json
<slug>/README.md
<slug>/departments/<CODE>.json
```

There must be exactly one department JSON file for each requested department and
no others. `<CODE>` is the official uppercase subject code and must match the
file's `department.code`. Sort department files by code, JSON object keys in schema
order, arrays in the stable orders described below, and use UTF-8, two-space JSON
indentation, a final newline, and no comments. Give ZIP members a fixed timestamp
of `1980-01-01 00:00:00`, store paths with `/`, and add members in the exact order
shown above followed by department files in code order. This makes equivalent
outputs reproducible.

Do **not** include a repository/project wrapper (for example
`University-Schedule-Planner/` or `universities/`), a second top-level entry,
`catalog.json`, `courses.db`, source-page dumps, screenshots, caches, logs, scripts,
executables, symlinks, credentials, cookies, tokens, personal data, or unrelated
scraped content. All ZIP members must be ordinary files beneath `<slug>/`; reject
absolute paths and `..` path components. The four named paths and requested
department files are the complete allowlist.

### 4. Content rules

Use these object shapes (fields shown are required unless marked optional):

```text
university.json = {slug, name, short_name, map_title, primary_color,
  secondary_color, accent_color, catalog_url, catalog_date, schema_version: 3,
  academic_calendar_system}
calendars.json = {schema_version: 3, academic_calendars: [{id, name,
  system_type, is_primary, source_url, terms: [{code, name, academic_year,
  term_type, sequence, start_date, end_date, dates_status, status,
  planning_enabled}]}]}
departments/<CODE>.json = {schema_version: 3, department: {code, name,
  school (optional), source_url}, courses: [{code, department, number, level,
  title, credits, description, prerequisites, corequisites, restrictions,
  repeatable, source_url, source_catalog, tags, offering_history:
  [{term_code, offering_status, source_url}]}], edges: [{source, target, kind,
  source_in_database, logic_group (optional), logic_operator (optional)}]}
```

All named prose fields remain strings even when the official source has no value
(use `""`); `tags`, `offering_history`, `courses`, and `edges` remain arrays even
when empty. Allowed university/calendar systems are `semester`, `quarter`,
`trimester`, `hybrid`, and `custom`. Allowed course levels are `undergraduate`,
`graduate`, `professional`, `continuing-education`, and `other`. Credits are a
non-negative JSON number or a numeric string/range such as `"3"` or `"1-4"`.

- `university.json`: use the official name and branding, the validated slug, the
  official top-level catalog URL, the snapshot date (`YYYY-MM-DD`), schema version
  3, and the documented calendar-system enum. Do not approximate brand colors;
  when official values cannot be verified, describe the ambiguity instead of
  claiming they are official.
- `calendars.json`: create one calendar, or separate calendars for officially
  distinct populations. Exactly one is primary. Give every term a globally unique
  stable code, official display name, academic year, term type, sequence, status,
  and boolean `planning_enabled`. Include historical terms used by offerings and
  enough records for four academic years. Published start/end dates use
  `dates_status: "official"`; if either date is unavailable, use
  `dates_status: "unpublished"` with both dates `null`. Never estimate dates.
  Historical terms have `planning_enabled: false`. Check unexpected overlaps and
  document legitimate sessions or overlaps.
- `departments/<CODE>.json`: preserve official titles, descriptions, credit
  values/ranges, prerequisite and corequisite prose, restrictions, repeatability,
  and cross-listing text. Course `code` is uppercase subject plus printed number
  with spaces removed; retain the printed number separately. Sort courses by code
  using natural numeric order and make codes unique.
- Add a relationship edge only when official text explicitly names its source
  course; its target must exist in the collected data. Set `source_in_database`
  accurately. Use only `prerequisite`, `corequisite`, or `recommended`. Preserve
  full prose after extracting edges. Encode explicit alternatives/conjunctions
  with a shared `logic_group` and uppercase `OR`/`AND`; do not encode ambiguous or
  nested prose, grades, standing, placement, programs, or permission as invented
  edges.
- An offering requires a term-specific official schedule record. Use only `held`,
  `scheduled`, or `cancelled`, and cite that record's URL. A catalog entry or stated
  rotation is not evidence that a course ran. Sort offering history by term
  sequence. Use an empty array when no offering can be verified.
- `README.md`: state provenance, requested scope, snapshot date, official source
  URLs, inaccessible sources, deliberate omissions, and ambiguities. Do not place
  credentials or copied page content in it.

### 5. Validate before delivery

Extract the ZIP into a new empty temporary directory (never over existing files),
then verify the filename, slug regex, single-root layout, exact file allowlist,
ordinary-file types, absence of symlinks, and absence of path traversal. Parse all
JSON and check filename/code matches, unique courses and term codes, relationship
targets, offering term references, enum values, URLs, dates, and four-academic-year
calendar coverage.

When the repository tools are available, also run from its root:

```bash
python tools/validate_university.py /temporary/extraction/<slug>
```

Do not run the build command on the deliverable directory because it creates the
forbidden generated files. If a build compatibility check is desired, copy the
extracted directory elsewhere, run
`python tools/build_university.py <copied-directory>`, and delete that copy.
Do not claim completion unless archive inspection, JSON checks, and the available
validator succeed.

### 6. Required response and final validation report

Attach `<slug>.zip` as a downloadable artifact first. Then provide a concise report
in this exact section order:

```text
VALIDATION REPORT
Archive: <slug>.zip
Snapshot date: YYYY-MM-DD
Departments: <total>
- <CODE>: <course count>
Courses total: <total>
Inaccessible sources:
- <URL and reason, or "None">
Ambiguities:
- <unresolved issue and conservative handling, or "None">
Checks:
- Archive layout and prohibited-content check: PASS
- JSON/schema/reference check: PASS
- Repository validator: PASS | NOT AVAILABLE (reason)
```

Counts must be computed from the files in the final ZIP, not from scraping notes.
Do not hide inaccessible sources or ambiguities to produce a cleaner report. Ask
for human review of prerequisite logic and samples from each official source
format.

## Human audit recommendation

Sample introductory, advanced, graduate, variable-credit, cross-listed, and
prerequisite-heavy records in every department. Compare them directly with the
official pages. Separately audit every `OR` group, future scheduled offering,
calendar boundary, and brand color. The report is not a substitute for validator
results or source comparison.

## Example archive fixture

`tests/fixtures/example-university-archive/` is a deliberately small, fictional,
text-only source fixture for the required archive layout. Its sole child,
`example-university/`, is the directory to package as `example-university.zip`;
keeping the fixture expanded avoids storing a binary ZIP in repositories and code
review systems that do not support binary files. Automated importer tests can ZIP
these files in the documented order with the fixed timestamp, then exercise their
normal archive reader. The fixture's `.invalid` URLs are reserved and intentionally
non-functional. It is not real university data and must not be used as a factual
source.
