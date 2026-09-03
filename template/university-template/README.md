# University setup template

**Everything in this directory is fictional test and template data. It does not describe a real institution.** Reserved `.invalid` URLs are deliberately non-functional.

Copy this entire folder to `universities/<university-slug>`, rename it, and replace every fictional placeholder. The repository tests copy this fixture to a temporary directory and build it there; generated `catalog.json` and `courses.db` files are never shipped from the template. Keep source data split from generated output: contributors edit the files described here, then the build tool creates those artifacts in the new university directory.

## 1. Configure `university.json`

Required fields:

- `slug`: lowercase URL-safe identifier; it must match the folder name.
- `name` and `short_name`: display names.
- `map_title`: heading shown in the course explorer.
- `primary_color`, `secondary_color`, `accent_color`: six-digit hex values from official brand guidance.
- `catalog_url`: official top-level course catalog.
- `catalog_date`: date the source snapshot was checked, in `YYYY-MM-DD` form.
- `schema_version`: currently `3`.
- `academic_calendar_system`: `semester`, `quarter`, `trimester`, `hybrid`, or `custom`.

## 2. Configure `calendars.json`

Create one or more calendars. Semester and quarter institutions normally need one. A hybrid institution can define separate calendars for populations that use different dates. Exactly one must set `is_primary` to `true`.

Each calendar requires:

- a unique `id`, display `name`, `system_type`, official `source_url`, and `terms` array;
- historical terms needed by course offering records;
- the current term and enough future term records to cover four academic periods (four distinct `academic_year` values), including neutral placeholders when dates have not been published;

Each term requires a globally unique `code`, display `name`, `academic_year` in `YYYY-YYYY` form, `term_type`, numeric sort `sequence`, `dates_status`, `start_date`, `end_date`, and a `status` of `historical`, `current`, or `future`. Set `planning_enabled` to `true` for terms users may select.

`dates_status` must be one of:

- `official`: both `start_date` and `end_date` are required in `YYYY-MM-DD` form. The calendar's `source_url` must identify the official source for those published dates.
- `unpublished`: both `start_date` and `end_date` must explicitly be `null`. The planner labels the term as a planning placeholder, not a confirmed schedule.

Dates are all-or-nothing: a term with only one date is invalid. Do not create estimated future dates. Instead, add neutrally named unpublished terms through the four-academic-period planning horizon. Within each academic year, `sequence` establishes the order of unpublished terms; official terms are ordered by their dates.

## 3. Create department files

Delete `departments/SAMPLE.json`. Add one file per department using its official subject code, such as `MATH.json`, `BIO.json`, or `LAW.json`. The filename and `department.code` must match, including case.

Every course includes:

- `code`, `department`, `number`, `level`, `title`, and `credits`;
- catalog text fields: `description`, `prerequisites`, `corequisites`, `restrictions`, and `repeatable`;
- `source_url`, `source_catalog`, and descriptive `tags`;
- an `offering_history` array, possibly empty.

Allowed course levels are `undergraduate`, `graduate`, `professional`, `continuing-education`, and `other`. `credits` is either a non-negative JSON number or a numeric string; use an ascending numeric range such as `1-4` for variable-credit courses. Other prose (such as `variable`, units, or comma-separated alternatives) is not valid in this field.

Course offerings reference a term from `calendars.json`:

```json
{
  "term_code": "2026FA",
  "offering_status": "held",
  "source_url": "https://registrar.example.invalid/schedule/2026-fall/course"
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

### Prerequisite expression contract

An edge with no `logic_group` is an independent, mandatory one-course requirement. It must also omit `logic_operator`; the planner treats several such edges as several independent requirements (all must be met).

Use `logic_group` only to encode a relationship explicitly supported by the catalog. Every edge in a group must have the same target, `kind`, and operator, and a group must contain at least two edges. Group names are identifiers and must not be reused for another target or relationship kind. `logic_operator` is the documented enum `"AND"` or `"OR"` (uppercase):

- `AND` applies **within that group** and requires every source course.
- `OR` applies **within that group** and requires at least one source course.

Multiple groups for the same target are independent and combine with an implicit AND: every group must be satisfied. Ungrouped edges are each equivalent to a separate one-member AND group. The same rules apply separately to prerequisite and corequisite edges. Prerequisites must be completed earlier; corequisites may instead be enrolled in the same term.

For example, these edges begin a clearly documented alternative group:

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

Do not turn prose that cannot be represented by this contract (minimum grades, placement scores, permissions, class standing, nested expressions, and similar qualifications) into invented logic. Preserve it in the course's official catalog text. The planner evaluates the structured edges conservatively and continues to display that text for the qualifications it cannot evaluate.

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
