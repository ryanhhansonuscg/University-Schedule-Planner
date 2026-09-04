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
- Test the course explorer, planner, CSV import, and CSV export.
- Describe missing or ambiguous data in the university README.
- Run `python tools/check_prohibited_terms.py` to ensure removed institution-specific names, domains, and colors have not returned.
- Run `python -m unittest discover -s tests` to build the fictional template fixture in a temporary directory and exercise repository checks.
- Run `python tools/final_qa.py` after merging changes; it is the final gate for unresolved conflict markers, missing repository elements, broken local asset references, malformed JSON, tests, and generated-artifact integrity.

Keep unrelated universities and departments out of the same pull request when practical. This makes source review and future updates easier.

The files in `template/university-template` are fictional placeholders, not a publishable institution. Tests copy them into a temporary directory so generated fixture artifacts are not committed or exposed through the production registry.
