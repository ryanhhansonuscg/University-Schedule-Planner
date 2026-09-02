# University of Maryland data

This folder is the included example university. It uses a hybrid configuration with the standard semester calendar and a separate 12-week calendar.

## Departments included

- `CMSC.json`: Computer Science, undergraduate and graduate courses
- `ENEE.json`: Electrical & Computer Engineering, undergraduate and graduate courses

The application supports additional UMD departments without code changes. Add another `<DEPARTMENT>.json` file and rebuild this folder.

## Official sources

- Catalog: <https://academiccatalog.umd.edu/>
- Undergraduate CMSC: <https://academiccatalog.umd.edu/undergraduate/approved-courses/cmsc/>
- Graduate CMSC: <https://academiccatalog.umd.edu/graduate/courses/cmsc/>
- Undergraduate ENEE: <https://academiccatalog.umd.edu/undergraduate/approved-courses/enee/>
- Graduate ENEE: <https://academiccatalog.umd.edu/graduate/courses/enee/>
- Standard calendar: <https://provost.umd.edu/calendar>
- 12-week calendar: <https://provost.umd.edu/calendar/12-week>

Catalog snapshot date: 2026-09-01.

Course offering history is intentionally empty in this snapshot because it was not collected from archived official schedules. The planner reports that absence instead of guessing likely semesters.

## Rebuild

From the repository root:

```bash
python tools/validate_university.py universities/university-of-maryland
python tools/build_university.py universities/university-of-maryland
```
