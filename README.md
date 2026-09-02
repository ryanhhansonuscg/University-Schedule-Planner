# College Schedule Planner

A static, multi-university course explorer and four-year schedule planner. Every institution supplies its own identity, dated academic calendars, and one JSON file per department. The shared application reads those files without institution- or department-specific code.

No real institution data is shipped by default. The registry intentionally starts empty, while `template/university-template` contains a small, explicitly fictional development fixture that demonstrates the data format.

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
│   └── index.json                Public institution registry (initially empty)
└── template/university-template/
    ├── README.md                 Setup and fictional-fixture walkthrough
    ├── university.json           Fictional quarter-system fixture
    ├── calendars.json
    ├── departments/SAMPLE.json
    └── LLM-SCRAPING-GUIDE.md     Copy/paste collection prompt
```

`university.json`, `calendars.json`, and `departments/*.json` are source files. `catalog.json` and `courses.db` are generated artifacts. Commit both artifacts for registered institutions so the static site works on GitHub Pages and downstream users can query SQLite. Do not generate them inside `template/`; tests build that fictional fixture only in a temporary directory.

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

The registry controls the picker. Set `default_university` to a registered slug; keep it `null` while the registry is empty.

## Repository checks

Run `python -m unittest discover -s tests`. The suite copies the fictional template to a temporary directory, validates and builds it there, confirms the production registry is internally consistent, and runs the institution-specific content check. You can run the latter alone with `python tools/check_prohibited_terms.py`.

## Calendar support

The `academic_calendar_system` may be `semester`, `quarter`, `trimester`, `hybrid`, or `custom`. A hybrid institution can define multiple calendars; each calendar has its own dated terms and exactly one calendar must be primary. Course offering records reference term codes, so historical and scheduled offerings work consistently across systems.

The planner uses terms whose `planning_enabled` value is true, whose end date is not in the past, and whose start date falls within four years of the current date. Publish enough future terms to cover the intended planning horizon.

## Planner files

CSV import requires a `Term` column and either `Course #` or `Course Name`. Term values can be the stored term code or visible term name. Export writes:

```csv
Term,Course #,Course Name,Course Hours
```

Plans are kept in browser local storage and separated by university slug. CSV import merges with the current plan.

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
