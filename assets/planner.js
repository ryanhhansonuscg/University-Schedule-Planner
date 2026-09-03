(async () => {
  let data;
  try {
    ({ catalog: data } = await window.COLLEGE_PLANNER.loadCatalog());
  } catch {
    return;
  }

  const courses = data.courses || [];
  const edges = data.edges || [];
  const courseByCode = new Map(courses.map(course => [course.code, course]));
  const plannerCalendar = document.getElementById('planner-calendar');
  const plannerCourseSearch = document.getElementById('planner-course-search');
  const courseOptions = document.getElementById('course-options');
  const plannerTerm = document.getElementById('planner-term');
  const completedCourses = document.getElementById('completed-courses');
  const planGrid = document.getElementById('plan-grid');
  const issueList = document.getElementById('issue-list');
  const issueCount = document.getElementById('issue-count');
  const calendarCoverage = document.getElementById('calendar-coverage');
  const plannerMessage = document.getElementById('planner-message');
  const exportButton = document.getElementById('export-schedule');
  const clearButton = document.getElementById('clear-schedule');
  const importInput = document.getElementById('import-schedule');
  const storageKey = `college-schedule-plan:${data.university?.slug || 'university'}`;
  const storageVersion = 2;
  let migrationNotice = '';
  let savedPlans = loadPlans();
  let activeCalendarId = '';
  let plan = {};

  document.title = `${data.university?.short_name || data.university?.name || 'College'} Schedule Planner`;

  function cleanPlan(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value)
      .filter(([, codes]) => Array.isArray(codes))
      .map(([termCode, codes]) => [termCode, [...new Set(codes.filter(code => typeof code === 'string'))]]));
  }

  function loadPlans() {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || '{}');
      if (saved?.version === storageVersion && saved.calendars && typeof saved.calendars === 'object') {
        return {
          version: storageVersion,
          calendars: Object.fromEntries(Object.entries(saved.calendars).map(([id, value]) => [id, cleanPlan(value)])),
          migration: saved.migration && typeof saved.migration === 'object' ? saved.migration : {},
        };
      }

      const calendars = {};
      const unmatched = {};
      Object.entries(cleanPlan(saved)).forEach(([termCode, codes]) => {
        const matches = (data.academic_calendars || []).filter(calendar =>
          (calendar.terms || []).some(term => term.code === termCode));
        if (!matches.length) unmatched[termCode] = codes;
        matches.forEach(calendar => {
          calendars[calendar.id] ||= {};
          calendars[calendar.id][termCode] = codes;
        });
      });
      const migrated = { version: storageVersion, calendars, migration: {} };
      if (Object.keys(unmatched).length) {
        migrated.migration.unmatched = unmatched;
        migrationNotice = `Schedule storage was upgraded. ${Object.keys(unmatched).length} unmatched term entr${Object.keys(unmatched).length === 1 ? 'y was' : 'ies were'} preserved in the migration recovery bucket.`;
      } else if (Object.keys(saved || {}).length) {
        migrationNotice = 'Schedule storage was upgraded for calendar-specific plans.';
      }
      localStorage.setItem(storageKey, JSON.stringify(migrated));
      return migrated;
      return PlannerCore.deserializePlan(localStorage.getItem(storageKey));
    } catch {
      return { version: storageVersion, calendars: {}, migration: {} };
    }
  }

  function savePlan() {
    if (activeCalendarId) savedPlans.calendars[activeCalendarId] = cleanPlan(plan);
    localStorage.setItem(storageKey, JSON.stringify(savedPlans));
  }

  function loadActivePlan() {
    activeCalendarId = activeCalendar()?.id || '';
    plan = cleanPlan(savedPlans.calendars[activeCalendarId]);
    localStorage.setItem(storageKey, PlannerCore.serializePlan(plan));
  }

  function dateValue(value) {
    return new Date(`${value}T00:00:00`);
  }

  function dateLabel(value) {
    return dateValue(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function activeCalendar() {
    return (data.academic_calendars || []).find(calendar => calendar.id === plannerCalendar.value);
  }

  function planningTerms() {
    return PlannerCore.planningTerms(data.academic_calendars, plannerCalendar.value);
  }

  function configurePlanner() {
    const calendars = data.academic_calendars || [];
    plannerCalendar.replaceChildren(...calendars.map(calendar => new Option(`${calendar.name} · ${calendar.system_type}`, calendar.id)));
    const primary = calendars.find(calendar => calendar.is_primary) || calendars[0];
    if (primary) plannerCalendar.value = primary.id;
    loadActivePlan();
    courseOptions.replaceChildren(...courses.map(course => {
      const option = document.createElement('option');
      option.value = `${course.code} — ${course.title}`;
      return option;
    }));
    completedCourses.value = localStorage.getItem(`${storageKey}:completed`) || '';
    refreshPlannerCalendar();
    if (migrationNotice) plannerMessage.textContent = migrationNotice;
  }

  function refreshPlannerCalendar() {
    const terms = planningTerms();
    plannerTerm.replaceChildren(...terms.map(term => new Option(`${term.name} · ${dateLabel(term.start_date)}`, term.code)));
    const calendar = activeCalendar();
    const last = terms.at(-1);
    const horizon = new Date();
    horizon.setFullYear(horizon.getFullYear() + 4);
    if (!calendar) {
      calendarCoverage.textContent = 'No academic calendar is configured.';
    } else {
      const coverage = terms.length ? `${dateLabel(terms[0].start_date)}–${dateLabel(last.end_date)}` : 'no currently plannable terms';
      const shortfall = last && dateValue(last.end_date) < horizon ? ' Published dates end before the full four-year horizon.' : '';
      calendarCoverage.textContent = `${data.university.academic_calendar_system} institution · ${calendar.name} covers ${coverage}.${shortfall} Logical alternatives in prerequisite text should be confirmed with an adviser.`;
    }
    renderPlan();
  }

  function resolveCourse(value) { return PlannerCore.resolveCourse(courses, value); }

  function renderPlan() {
    const terms = planningTerms();
    planGrid.replaceChildren(...terms.map(term => {
      const section = document.createElement('section');
      section.className = 'plan-term';
      const heading = document.createElement('h3');
      heading.textContent = term.name;
      const dates = document.createElement('span');
      dates.className = 'term-dates';
      dates.textContent = `${dateLabel(term.start_date)} – ${dateLabel(term.end_date)}`;
      const items = document.createElement('div');
      items.className = 'planned-courses';
      const codes = plan[term.code] || [];
      if (!codes.length) {
        const empty = document.createElement('span');
        empty.className = 'term-empty';
        empty.textContent = 'No courses planned';
        items.appendChild(empty);
      } else {
        codes.forEach(code => {
          const course = courseByCode.get(code);
          const item = document.createElement('div');
          item.className = 'planned-course';
          const label = document.createElement('span');
          const strong = document.createElement('strong');
          strong.textContent = code;
          const name = document.createElement('small');
          name.textContent = course?.title || 'Unknown course';
          label.append(strong, name);
          const remove = document.createElement('button');
          remove.type = 'button';
          remove.setAttribute('aria-label', `Remove ${code} from ${term.name}`);
          remove.textContent = 'Remove';
          remove.addEventListener('click', () => {
            plan[term.code] = plan[term.code].filter(value => value !== code);
            savePlan();
            renderPlan();
          });
          item.append(label, remove);
          items.appendChild(item);
        });
      }
      section.append(heading, dates, items);
      return section;
    }));
    const hasCourses = Object.values(plan).some(values => Array.isArray(values) && values.length);
    exportButton.disabled = !hasCourses;
    clearButton.disabled = !hasCourses;
    checkPlan(terms);
  }

  function addIssue(severity, title, message) {
    const item = document.createElement('div');
    item.className = `issue ${severity}`;
    const mark = document.createElement('i');
    mark.className = 'issue-mark';
    mark.setAttribute('aria-hidden', 'true');
    const copy = document.createElement('div');
    const strong = document.createElement('strong');
    strong.textContent = title;
    const detail = document.createElement('span');
    detail.textContent = message;
    copy.append(strong, detail);
    item.append(mark, copy);
    issueList.appendChild(item);
  }

  function checkPlan(terms) {
    issueList.replaceChildren();
    const completed = new Set(completedCourses.value.toUpperCase().split(/[\s,;]+/).filter(Boolean));
    const seen = new Set(completed);
    const scheduled = new Set();
    let issues = 0;
    terms.forEach(term => {
      const sameTerm = new Set(plan[term.code] || []);
      sameTerm.forEach(code => {
        if (scheduled.has(code)) {
          addIssue('error', `Duplicate course: ${code}`, `${code} appears more than once in the proposed schedule.`);
          issues += 1;
        }
        scheduled.add(code);
        const course = courseByCode.get(code);
        if (!course) {
          addIssue('error', `Unknown course: ${code}`, `The selected university catalog does not contain ${code}.`);
          issues += 1;
          return;
        }
        const missing = PlannerCore.prerequisiteMissing(edges, code, seen).map(source => ({ source }));
        if (missing.length) {
          addIssue('error', `Possible missing prerequisite for ${code}`, `${term.name}: complete ${[...new Set(missing.map(edge => edge.source))].join(', ')} earlier, or verify an alternative in the catalog wording.`);
          issues += 1;
        }
        const missingCoreq = edges.filter(edge => edge.target === code && edge.kind === 'corequisite' && !seen.has(edge.source) && !sameTerm.has(edge.source));
        if (missingCoreq.length) {
          addIssue('error', `Missing corequisite for ${code}`, `${term.name}: add ${[...new Set(missingCoreq.map(edge => edge.source))].join(', ')} in this or an earlier term.`);
          issues += 1;
        }
        const history = course.offering_history || [];
        const historical = history.filter(offering => offering.term_status === 'historical' && offering.offering_status === 'held');
        const exactFuture = history.some(offering => offering.term_code === term.code && ['scheduled', 'held'].includes(offering.offering_status));
        if (!history.length) {
          addIssue('info', `Offering history unavailable: ${code}`, `No past or scheduled offering records are stored for ${code}. Confirm ${term.name} with the live schedule.`);
          issues += 1;
        } else if (!exactFuture && historical.length && !historical.some(offering => offering.term_type === term.term_type)) {
          addIssue('warning', `Unusual term for ${code}`, `${code} has not previously been recorded in a ${term.term_type} term.`);
          issues += 1;
        }
      });
      sameTerm.forEach(code => seen.add(code));
    });
    issueCount.textContent = `${issues} issue${issues === 1 ? '' : 's'}`;
    if (!issues) {
      const clear = document.createElement('p');
      clear.className = 'all-clear';
      clear.textContent = 'No issues found with the stored prerequisites and offering history.';
      issueList.appendChild(clear);
    }
  }

  function csvCell(value) {
    return `"${String(value ?? '').replaceAll('"', '""')}"`;
  }

  function exportSchedule() {
    const rows = [['Calendar ID', 'Term Code', 'Term', 'Course #', 'Course Name', 'Course Hours']];
    const calendar = activeCalendar();
    (calendar?.terms || []).forEach(term => (plan[term.code] || []).forEach(code => {
      const course = courseByCode.get(code);
      rows.push([calendar.id, term.code, term.name, code, course?.title || '', course?.credits || '']);
    }));
    if (rows.length === 1) return;
    const csv = PlannerCore.scheduleCsv(planningTerms(), plan, courses);
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `${data.university?.slug || 'university'}-proposed-schedule.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function parseCsv(text) { return PlannerCore.parseCsv(text); }

  function normalizedHeader(value) {
    return value.toLowerCase().replace(/[^a-z0-9]/g, '');
  }

  async function importSchedule(file) {
    const rows = parseCsv(await file.text());
    if (rows.length < 2) {
      plannerMessage.textContent = 'The CSV must include a header and at least one schedule row.';
      return;
    }
    const headers = rows[0].map(normalizedHeader);
    const termIndex = headers.indexOf('term');
    const termCodeIndex = headers.indexOf('termcode');
    const calendarIndex = headers.indexOf('calendarid');
    const codeIndex = headers.findIndex(value => ['course', 'coursecode', 'coursenumber'].includes(value));
    const nameIndex = headers.indexOf('coursename');
    if ((termIndex < 0 && termCodeIndex < 0) || (codeIndex < 0 && nameIndex < 0)) {
      plannerMessage.textContent = 'Import requires a Term Code or Term column and either Course # or Course Name.';
      return;
    }
    const terms = activeCalendar()?.terms || [];
    const termByLabel = new Map();
    terms.forEach(term => {
      termByLabel.set(term.code.toLowerCase(), term);
      termByLabel.set(term.name.toLowerCase(), term);
    });
    let imported = 0;
    const skipped = [];
    rows.slice(1).forEach((row, rowIndex) => {
      const rowCalendarId = calendarIndex >= 0 ? row[calendarIndex]?.trim() : '';
      const termValue = (termCodeIndex >= 0 ? row[termCodeIndex] : '') || (termIndex >= 0 ? row[termIndex] : '');
      const term = termByLabel.get(termValue?.trim().toLowerCase());
      const course = resolveCourse((codeIndex >= 0 ? row[codeIndex] : '') || (nameIndex >= 0 ? row[nameIndex] : ''));
      if ((rowCalendarId && rowCalendarId !== activeCalendar()?.id) || !term || !course) {
        skipped.push(rowIndex + 2);
        return;
      }
      const before = (plan[term.code] || []).length;
      plan[term.code] = [...new Set([...(plan[term.code] || []), course.code])];
      if (plan[term.code].length > before) imported += 1;
    });
    savePlan();
    renderPlan();
    plannerMessage.textContent = `${imported} course${imported === 1 ? '' : 's'} imported into ${activeCalendar()?.name || 'the schedule'}.${skipped.length ? ` Skipped row${skipped.length === 1 ? '' : 's'} ${skipped.join(', ')} because the term or course was not recognized.` : ''}`;
  }

  plannerCalendar.addEventListener('change', () => {
    const previous = activeCalendarId;
    savePlan();
    loadActivePlan();
    refreshPlannerCalendar();
    const selected = activeCalendar();
    plannerMessage.textContent = `Switched from ${(data.academic_calendars || []).find(calendar => calendar.id === previous)?.name || 'the previous calendar'} to ${selected?.name || 'the selected calendar'}.`;
  });
  completedCourses.addEventListener('input', () => {
    localStorage.setItem(`${storageKey}:completed`, completedCourses.value);
    checkPlan(planningTerms());
  });
  document.getElementById('add-to-plan').addEventListener('click', () => {
    const course = resolveCourse(plannerCourseSearch.value);
    const termCode = plannerTerm.value;
    if (!course) {
      plannerMessage.textContent = 'Choose a suggestion, or enter an exact course number or unique course name.';
      return;
    }
    if (!termCode) {
      plannerMessage.textContent = 'No plannable term is available in this calendar.';
      return;
    }
    plan[termCode] = [...new Set([...(plan[termCode] || []), course.code])];
    plannerCourseSearch.value = '';
    plannerMessage.textContent = `${course.code} added to ${plannerTerm.options[plannerTerm.selectedIndex].text.split(' · ')[0]}.`;
    savePlan();
    renderPlan();
  });
  plannerCourseSearch.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      document.getElementById('add-to-plan').click();
    }
  });
  exportButton.addEventListener('click', exportSchedule);
  clearButton.addEventListener('click', () => {
    if (!window.confirm(`Clear every course from ${activeCalendar()?.name || 'this calendar'}?`)) return;
    plan = {};
    savePlan();
    renderPlan();
    plannerMessage.textContent = 'Schedule cleared.';
  });
  importInput.addEventListener('change', async () => {
    const file = importInput.files?.[0];
    if (file) await importSchedule(file);
    importInput.value = '';
  });

  document.getElementById('load-status').hidden = true;
  document.getElementById('planner').hidden = false;
  document.getElementById('app').setAttribute('aria-busy', 'false');
  configurePlanner();
})();
