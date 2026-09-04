# LLM-assisted university data collection

This guide is designed to be given to a browsing-capable LLM or coding agent. Human review is still required. University catalogs frequently encode prerequisite alternatives, minimum grades, permissions, cross-listings, variable credits, and calendar exceptions in prose.

## Before you begin

Give the agent:

1. the copied university folder;
2. the official catalog, registrar calendar, and schedule-of-classes starting URLs;
3. the departments and catalog years in scope;
4. permission to browse official public pages;
5. a clear snapshot date.

Do not give credentials or ask an agent to bypass authentication, robots controls, rate limits, or access restrictions. Prefer official downloadable data/API endpoints when the institution provides them. Follow the site's terms of use.

## Copy/paste prompt

```text
You are collecting verified university course and calendar data for the open-source College Schedule Planner repository.

TARGET
- University: <FULL UNIVERSITY NAME>
- Folder/slug: universities/<SLUG>
- Departments in scope: <OFFICIAL SUBJECT CODES AND NAMES>
- Catalog year(s): <YEAR OR EDITION>
- Snapshot date: <YYYY-MM-DD>
- Official catalog starting URL: <URL>
- Official registrar calendar URL: <URL>
- Official schedule-of-classes/archive URL: <URL>

OUTPUT CONTRACT
Read template/university-template/README.md and follow its schema exactly. Edit only:
- universities/<SLUG>/university.json
- universities/<SLUG>/calendars.json
- universities/<SLUG>/departments/<CODE>.json (one file per department)
- universities/<SLUG>/README.md for provenance, scope, caveats, and source URLs
Do not hand-edit catalog.json or courses.db; they are generated.

SOURCE RULES
1. Use only official university-controlled catalog, registrar, departmental, or schedule pages. Do not use aggregators, search snippets, Reddit, degree-planning sites, or another university's equivalency pages as facts.
2. Record the exact page URL that supports each course and offering. Record the calendar source URL. Note the snapshot date.
3. Never guess or interpolate missing data. If future dates are not officially published, omit them. If offering history cannot be verified, use an empty array and document the gap.
4. Preserve course titles, descriptions, credit values/ranges, prerequisite text, corequisite text, restrictions, repeatability, and cross-listing text faithfully. Normalize whitespace only.
5. Do not translate informal statements such as “typically offered in fall” into a held or scheduled offering. Offering history requires a term-specific official schedule record.
6. Respect access controls, robots instructions, rate limits, and terms of use. Do not bypass logins or anti-bot measures.

RELATIONSHIP RULES
1. Add an edge only when the official prerequisite/corequisite text explicitly names the source course.
2. The edge target belongs in the target course's department file. The target must exist in the collected dataset.
3. Set source_in_database to true only if the source course exists in one of the collected department files.
4. Use kind prerequisite, corequisite, or recommended exactly.
5. Preserve the complete prose requirement on the course even after extracting edges.
6. When the source clearly states alternatives, give related edges the same logic_group and logic_operator "OR". For a conjunction, use "AND". Do not infer grouping from ambiguous prose; document ambiguity in the university README.
7. Requirements that are not courses—class standing, placement scores, programs, permissions, minimum credits, grades, or instructor consent—remain in the prose fields and are not fabricated as course edges.

CALENDAR RULES
1. Identify the institution-level system as semester, quarter, trimester, hybrid, or custom.
2. For a hybrid system, create separate calendars for populations with different official dates.
3. Give every term a unique stable code, official display name, academic year, term type, sequence, exact start/end dates, status, and boolean `planning_enabled` flag. Treat that flag as authored source data: historical terms must use `false`, and current or future terms may use `false` when planning should be unavailable.
4. Include historical terms referenced by offering records and enough future terms for four academic years. Use `dates_status: "official"` with both published dates, or `dates_status: "unpublished"` with both dates set to `null`; never estimate dates.
5. Verify that term date ranges do not overlap unexpectedly within one calendar. Document legitimate overlaps or sessions.

COURSE RULES
1. Create one JSON file for every requested subject/department. The uppercase filename must equal department.code.
2. Course code is subject plus number with spaces removed and uppercase; keep the printed number separately as text.
3. Use level undergraduate, graduate, professional, continuing-education, or other.
4. Keep credits as text to preserve ranges and variable-credit notation.
5. Use a small, consistent tag vocabulary derived from explicit title/description topics and structural attributes. Do not use tags to invent requirements.
6. Deduplicate cross-listed or renumbered records only when the official source says they are the same course; otherwise retain both and document the relationship in prose.

OFFERING-HISTORY RULES
1. Record term_code, offering_status (held, scheduled, or cancelled), and the official term-specific source_url.
2. A catalog listing alone is not proof that a course was held.
3. A future catalog rotation is not proof that a section is scheduled.
4. Never mark held when the only evidence is planned, tentative, or cancelled.

QUALITY CONTROL
1. Ensure all JSON is valid UTF-8 and contains no comments.
2. Confirm every department filename/code match, every course code is unique, every edge target exists, and every offering term_code exists in calendars.json.
3. Run:
   python tools/validate_university.py universities/<SLUG>
   python tools/build_university.py universities/<SLUG>
4. Report counts by department, validation/build results, official sources used, pages that could not be accessed, unresolved ambiguities, and data deliberately left blank.
5. Do not claim completion until validation succeeds. Ask for human review of prerequisite logic and a sample of records from every source format.
```

## Suggested human audit

Sample at least ten courses per department, including introductory, advanced, graduate, variable-credit, cross-listed, and prerequisite-heavy records. Compare the generated JSON with the rendered official pages. Separately audit all `OR` prerequisite groups, every future scheduled offering, the transition between historical/current/future terms, and the university's official brand colors.

After approval, rebuild generated files and inspect the course explorer and planner in a browser. An LLM's summary is not a substitute for the validator or human source comparison.
