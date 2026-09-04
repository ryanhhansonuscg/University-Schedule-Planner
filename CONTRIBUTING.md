# Contributing data

Thanks for improving College Schedule Planner. Data changes should be reviewable, traceable to official university sources, and limited to source files whenever possible.

## Pull request checklist

- Edit `university.json`, `calendars.json`, or one or more `departments/*.json` files.
- Use official catalog, registrar, and schedule-of-classes URLs.
- Update `catalog_date` when the catalog snapshot changes.
- Preserve the university's exact prerequisite/corequisite wording.
- Do not infer a course offering from an undated rotation claim.
- Run `python tools/validate_university.py universities/<slug>`.
- When editing the source template, run `python tools/validate_university.py --template template/university-template`; `--template` does not relax slug checks for copies or production universities.
- Run `python tools/build_university.py universities/<slug>` and commit the regenerated `catalog.json` and `courses.db`.
- For a deterministic rebuild, run `SOURCE_DATE_EPOCH=1767225600 python tools/build_university.py universities/<slug>` for every build being compared. The value must be a non-negative integer Unix timestamp and is converted to UTC for the complete catalog's `generated_at`; leaving it unset uses the current UTC time.
- Test the course explorer, planner, CSV import, and CSV export.
- Describe missing or ambiguous data in the university README.
- Run `python tools/check_prohibited_terms.py` to ensure removed institution-specific names, domains, and colors have not returned.
- Run `python -m unittest discover -s tests` to build the fictional template fixture in a temporary directory and exercise repository checks.
- With Git, Python 3.12+, Node.js 20+, and npm installed, run `npm ci` and then the single canonical gate, `python tools/final_qa.py`, from a clean tracked worktree after merging changes. It checks unresolved conflict markers, missing repository elements, broken local references, malformed JSON, all test layers, and generated-artifact integrity. `--allow-dirty` is only an explicit local-development override; do not use it for release or CI validation.

Keep unrelated universities and departments out of the same pull request when practical. This makes source review and future updates easier.

CI and `tools/final_qa.py` build the template twice with the exact epoch `1767225600` (`2026-01-01T00:00:00+00:00`) and invoke `python tools/check_generated.py FIRST_CATALOG FIRST_DB SECOND_CATALOG SECOND_DB`. This shared verifier compares complete JSON catalogs, SQLite schema, and deterministically ordered rows for every table, then performs `PRAGMA integrity_check` and `PRAGMA foreign_key_check`; raw-byte equality is only an additional diagnostic.

The files in `template/university-template` are fictional placeholders, not a publishable institution. Tests copy them into a temporary directory so generated fixture artifacts are not committed or exposed through the production registry.
