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

Keep unrelated universities and departments out of the same pull request when practical. This makes source review and future updates easier.
