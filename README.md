# College Schedule Planner

A static, multi-university course explorer and four-year schedule planner. Every institution supplies its own identity, academic calendars (including unpublished-date placeholders), and one JSON file per department. The shared application reads those files without institution- or department-specific code.

No real institution data is shipped by default. The registry intentionally starts empty, while `template/university-template` contains a small, explicitly fictional development fixture that demonstrates the data format.

## Quickstart (V1, no server required)

Use **Python 3.12** (the supported Python feature release for V1). Download its
official 64-bit installer from the Python.org [Python 3.12.10 release
page](https://www.python.org/downloads/release/python-31210/): choose **Windows
installer (64-bit)** on Windows or **macOS 64-bit universal2 installer** on macOS.
Python 3.12.10 is specified because it is the final Python 3.12 release for which
Python.org provides the Windows and macOS binary installers needed by this
quickstart; do not substitute a Microsoft Store or third-party package.

### 1. Download and extract V1

1. On the repository's [Releases
   page](https://github.com/ryanhhansonuscg/University-Schedule-Planner/releases),
   open the **V1** release and download its release archive (`.zip`), rather than
   an individual source file.
2. **Windows:** in File Explorer, right-click the downloaded ZIP, select
   **Extract All...**, and then open the extracted folder.
3. **macOS:** in Finder, double-click the downloaded ZIP, and then open the
   extracted folder.

The extracted project folder must directly contain `README.md`, `tools`,
`template`, and `universities`. If those items are inside a second same-named
folder, use that inner folder as the project folder. Do not run commands while
viewing files inside the ZIP.

### 2. Install Python

**Windows:** run the downloaded Python installer, enable **Add python.exe to
PATH** on its first screen, choose **Install Now**, and finish the installer.
Open a new PowerShell or Command Prompt window and confirm the launcher works:

```powershell
py -3 --version
```

The result must begin with `Python 3.12`. The `py -3` launcher is used in the
Windows commands below even when `python` is not on PATH.

**macOS:** open the downloaded official `.pkg`, complete the installer, and then
open a new Terminal window. Confirm the installed command:

```bash
python3 --version
```

The result must begin with `Python 3.12`.

### 3. Ask a browsing-capable LLM for university data

Give the LLM all three of the following in the same conversation:

- the bundled directions file
  `template/university-template/LLM-SCRAPING-GUIDE.md` (upload the file or paste
  its complete contents);
- the official university catalog URL (plus official registrar calendar and
  schedule URLs, when they are separate); and
- the exact department names and subject codes to include, such as
  `Computer Science (CS)` and `Mathematics (MATH)`.

Tell it to browse only official university sources, follow the output contract
in the directions, and return a ZIP containing one completed university folder.
Review its reported inaccessible pages and ambiguities before accepting the ZIP.
Never provide credentials or ask it to bypass access controls.

### 4. Import, validate, and build the standalone planner

Save the returned ZIP anywhere convenient. Do not extract it yourself: the
quickstart command checks every archive entry, extracts to temporary storage,
validates and compiles the dataset, updates the registry, and builds the
standalone site as one rollback-safe operation.

From the extracted V1 project folder, run:

**Windows (PowerShell or Command Prompt):**

```powershell
py -3 tools\quickstart.py C:\path\to\university.zip
```

**macOS (Terminal):**

```bash
python3 tools/quickstart.py /path/to/university.zip
```

The ZIP must contain exactly one top-level folder named for its university slug,
with `university.json`, `calendars.json`, and `departments/*.json` beneath it.
Success prints the exact absolute `index.html` path to open.

```text
Success. Open this file in your browser:
<absolute-project-path>/dist/<university-slug>/index.html
```

Open `dist/<university-slug>/index.html` in File Explorer or Finder to launch
the course explorer; `planner.html` in the same folder is the schedule planner.
These generated pages work directly from disk: **no local web server is
required**.

If that slug is already installed, the command refuses to change anything. Only
when you intentionally want to replace its dataset, registry entry, and
standalone output, rerun the same command with `--replace`.

### Troubleshooting and review warnings

- **“`py` is not recognized” (Windows):** close and reopen the terminal. If it
  still fails, rerun the official installer and enable **Add python.exe to
  PATH** (and install the Python launcher), then retry `py -3 --version`.
- **“`python3: command not found`” (macOS):** finish the official `.pkg`
  installation, open a new Terminal window, and retry `python3 --version`.
- **“can't open file ... `tools/build_standalone.py`”:** change directory to
  the extracted project folder—the one that directly contains `tools`—and do
  not run the command from Downloads, from `universities`, or from inside the
  ZIP viewer.
- **Malformed university layout:** ask the LLM to recreate the ZIP with exactly
  one slug-named wrapper folder containing `university.json`, `calendars.json`,
  and `departments/*.json`; do not manually extract files into `universities/`.
- **`ERROR:` validation output:** do not ignore it or edit generated files.
  Give the exact error to the LLM, correct the source JSON, and rerun the build
  until the success message appears.
- **Data-review warning:** LLM output is not authoritative. Compare a sample
  from every department with official sources, and manually review calendar
  dates, credits, prerequisite/corequisite wording and `OR` logic, cross-listings,
  and every claimed offering. Missing or unpublished data must remain clearly
  identified rather than guessed. Confirm the finished plan with the university
  and an adviser before registration.

## Contributor development: run the source site locally

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

`university.json`, `calendars.json`, and `departments/*.json` are source files. `catalog.json` and `courses.db` are generated artifacts. Commit both artifacts for registered institutions so the static site works on GitHub Pages and downstream users can query SQLite. Do not generate them inside `template/`; tests build that fictional fixture only in a temporary directory. Builds honor the reproducible-build `SOURCE_DATE_EPOCH` environment variable: set it to a non-negative integer Unix timestamp and `generated_at` is that instant converted to UTC. If it is unset, the build uses the current UTC time; malformed, negative, or out-of-range values fail validation.

## Contributor workflow: add a university

1. Copy `template/university-template` to `universities/<unique-slug>`.
2. Complete `university.json` and `calendars.json`.
3. Create one `departments/<CODE>.json` file for every department.
4. Validate and build it:

   ```bash
   python tools/validate_university.py universities/<unique-slug>
   python tools/build_university.py universities/<unique-slug>
   ```

To make a directory that can be copied to removable media or opened directly
without a web server, build a standalone distribution for one university:

```bash
python tools/build_standalone.py universities/<unique-slug> dist/<unique-slug>
```

The command runs the same validation and catalog compilation as the normal build,
then writes `index.html`, `planner.html`, and their assets to the destination. The
registry and compiled catalog are embedded in `assets/embedded-data.js`, so both
pages work under `file://`; the selected university is retained when moving between
the explorer and planner. The source university directory is not modified.

5. Add the university to `universities/index.json`.
6. Run the local server and test both pages with `?university=<unique-slug>`.

The registry controls the picker. Set `default_university` to a registered slug; keep it `null` while the registry is empty.

## Repository checks

Run `python -m unittest discover -s tests`. The suite copies the fictional template to a temporary directory, validates and builds it there, confirms the production registry is internally consistent, and runs the institution-specific content check. You can run the latter alone with `python tools/check_prohibited_terms.py`.

## Calendar support

The `academic_calendar_system` may be `semester`, `quarter`, `trimester`, `hybrid`, or `custom`. A hybrid institution can define multiple calendars; each calendar has its own dated terms and exactly one calendar must be primary. Course offering records reference term codes, so historical and scheduled offerings work consistently across systems.

The planner uses terms whose `planning_enabled` value is true, excludes dated terms whose end date is in the past, and shows up to four distinct academic years. Publish official dates when available and add explicitly undated placeholder terms to cover that academic-period horizon.

## Planner files

CSV import requires a `Term Code` or `Term` column and either `Course #` or `Course Name`. Term values can be the stored term code or visible term name. When `Calendar ID` is present, rows are accepted only for the active calendar. Export writes:

```csv
Calendar ID,Term Code,Term,Course #,Course Name,Course Hours
```

Plans are kept in versioned browser local storage and separated by university slug and academic calendar. CSV import merges with the active calendar's plan.

## What schedule checks mean

The planner flags duplicate courses, explicit prerequisite/corequisite edges, and term patterns from stored offering history. These are advisory checks. Free-form catalog rules, degree requirements, permissions, minimum grades, credit limits, transfer equivalencies, and prerequisite `OR` logic may require human review. The original prerequisite text is always displayed for that reason.

## Hosted deployment: publish on GitHub Pages

1. Upload this folder as the repository root.
2. In repository **Settings → Pages**, deploy from the main branch and root folder.
3. Keep `universities/*/catalog.json` committed; the browser cannot build it itself.

No server-side code or secrets are required. The static application can also be hosted by Netlify, Cloudflare Pages, or any ordinary web server.

## License

This project is licensed under the MIT License. You may use and modify it as
long as you retain the copyright and license notices that credit the original
source. See [`LICENSE`](LICENSE) for the complete terms.

## Data responsibility

Course catalogs and calendars change. Store official source URLs and a `catalog_date`, never invent missing requirements or dates, and clearly mark unavailable offering history. Users should confirm their plan with the university and an adviser before registration.

## Release validation and test commands

The test harness deliberately has no third-party runtime or development dependencies. JavaScript tests use the `node:test` runner included with Node.js; `package-lock.json` pins the empty dependency graph and the supported toolchain is Python 3.12 and Node.js 20 or newer.

From the repository root, install the locked (dependency-free) npm project, then run the single canonical final-QA command. It requires Git, Python 3.12, Node.js 20+, and npm:

```bash
npm ci
python tools/final_qa.py
```

The gate normally requires a clean tracked worktree so it validates exactly what will be reviewed. During local development, `python tools/final_qa.py --allow-dirty` is an explicit override; CI and release validation must use the canonical command without that option.

The Python suite copies `template/university-template/` into a temporary directory before invoking any writing build. To reproduce CI's generated-artifact and SQLite checks locally:

```bash
tmp=$(mktemp -d)
cp -R template/university-template "$tmp/fictional-template-university"
SOURCE_DATE_EPOCH=1767225600 python tools/build_university.py "$tmp/fictional-template-university"
cp "$tmp/fictional-template-university/catalog.json" "$tmp/first.json"
cp "$tmp/fictional-template-university/courses.db" "$tmp/first.db"
SOURCE_DATE_EPOCH=1767225600 python tools/build_university.py "$tmp/fictional-template-university"
python tools/check_generated.py \
  "$tmp/first.json" "$tmp/first.db" \
  "$tmp/fictional-template-university/catalog.json" \
  "$tmp/fictional-template-university/courses.db"
```

Use the exact epoch `1767225600` (`2026-01-01T00:00:00+00:00`) for both builds, as CI and `tools/final_qa.py` do. The verifier compares the complete catalogs (including `generated_at`), SQLite schemas, and deterministically ordered rows from every table; it also runs SQLite integrity and foreign-key checks. Raw database bytes are checked as an additional diagnostic, not as the sole content comparison.

The semantic markup smoke checks inspect source markup and JavaScript contracts for navigation, loading states, calendar switching, Enter-key scheduling, local-storage serialization, CSV round-tripping, catalog failure handling, and accessible landmarks. They do not run a browser or an accessibility tree checker, so they must not be treated as automated accessibility conformance tests.

### Manual accessibility checks

Before release, serve the site locally and check both pages with a populated university catalog:

- **Keyboard navigation:** use only Tab, Shift+Tab, Enter, Space, and arrow keys. Confirm every filter, course, graph node, planner action, and import control is reachable; focus remains visible; selection and import messages are announced; and focus moves to actionable import errors.
- **Zoom and reflow:** test at 200% and 400% browser zoom, including a viewport 320 CSS pixels wide. Confirm content reflows without horizontal page scrolling, clipping, overlap, or loss of controls and relationship text.
- **Forced colors:** enable the operating system/browser forced-colors or high-contrast mode. Confirm focus indicators, selected courses, graph nodes, relationship lines, issue states, and buttons remain distinguishable without relying on color alone.
- **Dark mode:** select the system dark color scheme and confirm text, borders, focus indicators, badges, selected states, and links retain readable contrast.
- **Screen reader relationship navigation:** with a screen reader, select several courses, navigate the Relationship summary by heading and list, and confirm the selected course, prerequisites, corequisites, and dependents are understandable. Then navigate graph buttons and confirm each accessible name states its course and relationship. Ensure graph redraws are not announced wholesale and only concise selection/result-count status messages are spoken.

`python tools/final_qa.py` is the single canonical final release gate. It detects unresolved merge markers, missing required files and local references from HTML, CSS, and JavaScript modules, malformed tracked JSON, test or syntax failures, institution-specific content, and non-reproducible template artifacts. It reports each completed test layer separately. Run it from a clean worktree after merging work to ensure no conflict residue or required element was lost.

## Build an end-user release

End-user releases support **64-bit Windows 10 and Windows 11** and **macOS
Monterey 12 or newer**. They require the official Python 3.12 installation
described in the quickstart and a current version of Safari, Chrome, Edge, or
Firefox. The planner itself runs from extracted local files; neither platform
needs an HTTP server.

Set the release version in `package.json`, commit every intended change, and
start from the repository root with no modified tracked files. Then run:

```bash
python tools/build_release.py
```

The command refuses a dirty tracked worktree, runs the canonical
`python tools/final_qa.py` gate, and creates these deterministically named files
under the ignored `release/` directory:

```text
university-schedule-planner-v<version>.zip
university-schedule-planner-v<version>.zip.sha256
```

Packaging uses an explicit end-user allowlist. It includes the local-file web
application, required assets, CSV template, quickstart ZIP importer, build and
validation helpers, LLM scraping directions, and fictional university template.
It excludes tests, package-manager and CI configuration, caches, temporary
files, contributor-only tools, generated distributions, and every real
university source-data directory. Before reporting success, the command checks
the ZIP's exact manifest and file contents, rejects unsafe archive paths and
links, and extracts it into a temporary directory for static inspection. Upload
both generated files to the matching release; users can compare the ZIP's
SHA-256 digest with the single line in the `.sha256` file.

### Clean-machine manual release checklist

Perform this checklist on clean installations of every supported operating
system. Do not run `tools/serve.py` or start any other HTTP server during it.

- [ ] Download the ZIP and checksum, verify the SHA-256 digest with
  `Get-FileHash <zip> -Algorithm SHA256` on Windows or `shasum -a 256 <zip>` on
  macOS, and extract the ZIP using File Explorer or Finder.
- [ ] Confirm the extracted folder directly contains `README.md`, `index.html`,
  `planner.html`, `assets/`, `template/`, `tools/`, and `universities/`.
- [ ] Obtain a reviewed university ZIP with the documented single-folder layout
  and import it using `py -3 tools\quickstart.py <zip>` (Windows) or
  `python3 tools/quickstart.py <zip>` (macOS).
- [ ] Double-click the generated `dist/<slug>/index.html` and confirm the
  standalone course explorer launches from a `file://` URL without an HTTP
  server or browser console loading errors.
- [ ] Open `planner.html` using the planner navigation link, then return to the
  explorer and confirm the selected university is retained.
- [ ] Add courses in multiple terms, close every browser window, reopen the same
  `planner.html`, and confirm the plan persisted in browser local storage.
- [ ] Export the plan to CSV, clear or change it, import the exported CSV, and
  confirm term placement, course identity, hours, and validation messages round
  trip correctly. Also import `schedule-import-template.csv` after filling in
  valid courses for the installed university.
