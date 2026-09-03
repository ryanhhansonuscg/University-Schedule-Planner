# Contributing data

Thanks for improving College Schedule Planner. Data changes should be reviewable, traceable to official university sources, and limited to source files whenever possible.

## Pull request checklist

- Edit `university.json`, `calendars.json`, or one or more `departments/*.json` files.
- Use official catalog, registrar, and schedule-of-classes URLs.
- Update `catalog_date` when the catalog snapshot changes.
- Preserve the university's exact prerequisite/corequisite wording.
- Do not infer a course offering from an undated rotation claim.
- Run `python tools/validate_university.py universities/<slug>`.
- Run `python tools/build_university.py universities/<slug>` and commit the regenerated `catalog.json` and `courses.db`.
- Test the course explorer, planner, CSV import, and CSV export.
- Describe missing or ambiguous data in the university README.
- Run `python tools/check_prohibited_terms.py` to ensure removed institution-specific names, domains, and colors have not returned.
- Run `python -m unittest discover -s tests` to build the fictional template fixture in a temporary directory and exercise repository checks.

Keep unrelated universities and departments out of the same pull request when practical. This makes source review and future updates easier.

## Run the complete test suite

CI runs on every push and pull request. Use Python 3.12 and Node.js 20 or newer, then run these exact commands from the repository root before submitting changes:

```bash
npm ci
python -m unittest discover -s tests -v
npm test
python -m compileall -q tools tests
npm run check
python tools/validate_university.py template/university-template
python tools/check_prohibited_terms.py
node --test tests/browser-smoke.test.js
```

`npm test` includes planner-core unit coverage and page-level smoke checks. `node --test tests/browser-smoke.test.js` is the focused accessibility/browser-contract check used by CI. There are currently no external npm packages: Node's built-in `node:test` is the test runner, and the committed `package-lock.json` reproducibly records that dependency-free policy.

Build tests must never write into the template fixture. Copy it first:

```bash
tmp=$(mktemp -d)
cp -R template/university-template "$tmp/fixture"
python tools/build_university.py "$tmp/fixture"
```

For the exact reproducibility and SQLite integrity script, use the commands in the README's **Test and validation commands** section.

The files in `template/university-template` are fictional placeholders, not a publishable institution. Tests copy them into a temporary directory so generated fixture artifacts are not committed or exposed through the production registry.
