# University setup template

Copy this entire folder to `universities/<university-slug>`, rename it, and replace every example value. Keep source data split from generated output: contributors edit the files described here, then the build tool creates `catalog.json` and `courses.db`.

## 1. Configure `university.json`

Required fields:

- `slug`: lowercase URL-safe identifier; it must match the folder name.
- `name` and `short_name`: display names.
- `map_title`: heading shown in the course explorer.
- `primary_color`, `secondary_color`, `accent_color`: six-digit hex values from official brand guidance.
- `catalog_url`: official top-level course catalog.
- `catalog_date`: date the source snapshot was checked, in `YYYY-MM-DD` form.
- `schema_version`: currently `2`.
- `academic_calendar_system`: `semester`, `quarter`, `trimester`, `hybrid`, or `custom`.

## 2. Configure `calendars.json`

Create one or more calendars. Semester and quarter institutions normally need one. A hybrid institution can define separate calendars for populations that use different dates. Exactly one must set `is_primary` to `true`.

Each calendar requires:

- a unique `id`, display `name`, `system_type`, official `source_url`, and `terms` array;
- historical terms needed by course offering records;
- the current term and all officially published future terms, ideally covering four years.

Each term requires a globally unique `code`, display `name`, `academic_year`, `term_type`, sort `sequence`, exact `start_date` and `end_date`, and a `status` of `historical`, `current`, or `future`. Set `planning_enabled` to `true` for terms users may select.

Do not create estimated future dates. If official dates stop early, include only published dates; the planner displays a coverage warning.

## 3. Create department files

Delete `departments/SAMPLE.json`. Add one file per department using its official subject code, such as `MATH.json`, `BIO.json`, or `LAW.json`. The filename and `department.code` must match, including case.

Every course includes:

- `code`, `department`, `number`, `level`, `title`, and `credits`;
- catalog text fields: `description`, `prerequisites`, `corequisites`, `restrictions`, and `repeatable`;
- `source_url`, `source_catalog`, and descriptive `tags`;
- an `offering_history` array, possibly empty.

Allowed course levels are `undergraduate`, `graduate`, `professional`, `continuing-education`, and `other`. Keep `credits` as text so ranges such as `1-4` are preserved.

Course offerings reference a term from `calendars.json`:

```json
{
  "term_code": "2026FA",
  "offering_status": "held",
  "source_url": "https://official.example.edu/schedule/2026-fall/course"
}
```

The status is `held`, `scheduled`, or `cancelled`. An empty array means no verified records were collected; it does not mean the course was never offered.

## 4. Record course relationships

Store each prerequisite, corequisite, or recommendation as a directed edge. Put an edge in the department file that owns the target course.

```json
{
  "source": "MATH101",
  "target": "PHYS201",
  "kind": "prerequisite",
  "source_in_database": false
}
```

`source_in_database` is false when the prerequisite course belongs to a department that has not been imported. The target must always exist. Preserve the full catalog wording on the course even when edges are present.

For a clearly documented alternative group, optional `logic_group` and `logic_operator` fields may identify related edges:

```json
{
  "source": "MATH120",
  "target": "STAT300",
  "kind": "prerequisite",
  "source_in_database": true,
  "logic_group": "stat300-math-choice",
  "logic_operator": "OR"
}
```

The current planner remains conservative and may flag all explicit prerequisite edges. Users are told to verify alternatives against the original catalog text.

## 5. Validate and build

From the repository root:

```bash
python tools/validate_university.py universities/<university-slug>
python tools/build_university.py universities/<university-slug>
```

The build writes `catalog.json` for the browser and `courses.db` for code/data users. Fix every validation error rather than editing generated files.

## 6. Register and test

Add the university to `universities/index.json` and optionally set it as `default_university`. Then run:

```bash
python tools/serve.py
```

Test these URLs:

- `http://127.0.0.1:8000/index.html?university=<university-slug>`
- `http://127.0.0.1:8000/planner.html?university=<university-slug>`

Check department/level filters, a prerequisite neighborhood, university colors, all calendars, course search by name and code, schedule warnings, CSV import, and CSV export.

For assisted data collection, use `LLM-SCRAPING-GUIDE.md` in this folder.
