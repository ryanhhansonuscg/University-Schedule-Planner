# College Schedule Planner

A static, multi-university course explorer and four-year schedule planner. Every university supplies its own identity, dated academic calendars, and one JSON file per department. The shared application reads those files without university- or department-specific code.

The included University of Maryland example contains 238 undergraduate and graduate CMSC and ENEE courses. The architecture is not limited to those subjects: add any department by adding another department file.

## Run locally

The browser must load JSON over HTTP; opening `index.html` directly from disk will not work.

```bash
python tools/serve.py
```

Then open <http://127.0.0.1:8000>. The project has no package manager, build framework, or third-party runtime dependency. Python 3 is only needed for data validation/building and the optional local server.

## Repository layout

```text
College Schedule Planner/
├── index.html                    Course explorer
├── planner.html                  Schedule planner and CSV import/export
├── assets/                       Shared browser application
├── schema.sql                    Generated SQLite schema
├── tools/                        Standard-library Python tools
├── universities/
│   ├── index.json                Public university registry
│   └── university-of-maryland/
│       ├── university.json       Name, colors, source snapshot, system type
│       ├── calendars.json        Historical/current/future dated terms
│       ├── departments/
│       │   ├── CMSC.json         One source file per department
│       │   └── ENEE.json
│       ├── catalog.json          Generated browser catalog
│       └── courses.db            Generated SQLite database
└── template/university-template/
    ├── README.md                 Setup walkthrough
    ├── university.json           Quarter-system example
    ├── calendars.json
    ├── departments/SAMPLE.json
    └── LLM-SCRAPING-GUIDE.md     Copy/paste collection prompt
```

`university.json`, `calendars.json`, and `departments/*.json` are source files. `catalog.json` and `courses.db` are generated artifacts. Commit both generated artifacts so the static site works on GitHub Pages and downstream users can query SQLite.

## Add a university

1. Copy `template/university-template` to `universities/<unique-slug>`.
2. Complete `university.json` and `calendars.json`.
3. Create one `departments/<CODE>.json` file for every department.
4. Validate and build it:

   ```bash
   python tools/validate_university.py universities/<unique-slug>
   python tools/build_university.py universities/<unique-slug>
   ```

5. Add the university to `universities/index.json`.
6. Run the local server and test both pages with `?university=<unique-slug>`.

The university registry controls the picker. The `default_university` value is loaded when no query parameter is present.

## Calendar support

The `academic_calendar_system` may be `semester`, `quarter`, `trimester`, `hybrid`, or `custom`. A hybrid institution can define multiple calendars; each calendar has its own dated terms and exactly one calendar must be primary. Course offering records reference term codes, so historical and scheduled offerings work consistently across systems.

The planner uses terms whose `planning_enabled` value is true, whose end date is not in the past, and whose start date falls within four years of the current date. Publish enough future terms to cover the intended planning horizon.

## Planner files

CSV import requires a `Term Code` or `Term` column and either `Course #` or `Course Name`. Term values can be the stored term code or visible term name. When `Calendar ID` is present, rows are accepted only for the active calendar. Export writes:

```csv
Calendar ID,Term Code,Term,Course #,Course Name,Course Hours
```

Plans are kept in versioned browser local storage and separated by university slug and academic calendar. CSV import merges with the active calendar's plan.

## What schedule checks mean

The planner flags duplicate courses, explicit prerequisite/corequisite edges, and term patterns from stored offering history. These are advisory checks. Free-form catalog rules, degree requirements, permissions, minimum grades, credit limits, transfer equivalencies, and prerequisite `OR` logic may require human review. The original prerequisite text is always displayed for that reason.

## Publish on GitHub Pages

1. Upload this folder as the repository root.
2. In repository **Settings → Pages**, deploy from the main branch and root folder.
3. Keep `universities/*/catalog.json` committed; the browser cannot build it itself.
4. Add a repository license before accepting outside contributions. No license has been selected automatically for you.

No server-side code or secrets are required. The static application can also be hosted by Netlify, Cloudflare Pages, or any ordinary web server.

## Data responsibility

Course catalogs and calendars change. Store official source URLs and a `catalog_date`, never invent missing requirements or dates, and clearly mark unavailable offering history. Users should confirm their plan with the university and an adviser before registration.
