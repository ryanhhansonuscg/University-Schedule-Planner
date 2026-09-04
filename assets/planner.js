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
  const storageWarning = document.getElementById('storage-warning');
  const exportButton = document.getElementById('export-schedule');
  const clearButton = document.getElementById('clear-schedule');
  const importInput = document.getElementById('import-schedule');
  const storageKey = `college-schedule-plan:${data.university?.slug || 'university'}`;
  const storageVersion = 2;
  const storage = PlannerCore.createStorageAdapter(localStorage);
  let migrationNotice = '';
  let savedPlans = loadPlans();
  let activeCalendarId = '';
  let plan = {};
  let completedSaveTimer;

  document.title = `${data.university?.short_name || data.university?.name || 'College'} Schedule Planner`;

  function cleanPlan(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value)
      .filter(([, codes]) => Array.isArray(codes))
      .map(([termCode, codes]) => [termCode, [...new Set(codes.filter(code => typeof code === 'string'))]]));
  }

  function warnStorage(message = 'Changes cannot be saved in this browser. You can continue planning during this session; export your schedule before leaving.') {
    if (storageWarning.textContent === message && !storageWarning.hidden) return;
    storageWarning.textContent = message;
    storageWarning.hidden = false;
  }

  function loadPlans() {
    const result = storage.read(storageKey);
    if (!result.ok) { warnStorage(); return { version: storageVersion, calendars: {}, migration: {} }; }
    let saved;
    try { saved = JSON.parse(result.value || '{}'); }
    catch { warnStorage('Saved planner data is malformed and could not be loaded. New changes will use a fresh in-memory schedule.'); return { version: storageVersion, calendars: {}, migration: {} }; }
    if (Object.hasOwn(saved, 'version')) {
      if (!PlannerCore.validateStoredPlans(saved, storageVersion)) {
        warnStorage('Saved planner data has an invalid format and could not be loaded. New changes will use a fresh in-memory schedule.');
        return { version: storageVersion, calendars: {}, migration: {} };
      }
      return saved;
    }

    try {
      if (!PlannerCore.validatePlanMap(saved)) throw new Error('Invalid legacy plan');
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
      if (!storage.write(storageKey, JSON.stringify(migrated)).ok) warnStorage();
      return migrated;
    } catch {
      warnStorage('Saved planner data has an invalid format and could not be loaded. New changes will use a fresh in-memory schedule.');
      return { version: storageVersion, calendars: {}, migration: {} };
    }
  }

  function savePlan() {
    if (activeCalendarId) savedPlans.calendars[activeCalendarId] = cleanPlan(plan);
    const result = storage.write(storageKey, JSON.stringify(savedPlans));
    if (!result.ok) warnStorage();
    return result;
  }

  function loadActivePlan() {
    activeCalendarId = activeCalendar()?.id || '';
    plan = cleanPlan(savedPlans.calendars[activeCalendarId]);
  }

  function dateValue(value) {
    if (value == null) return null;
    return new Date(`${value}T00:00:00`);
  }

  function dateLabel(value) {
    const date = dateValue(value);
    return date ? date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'Dates not yet published';
  }

  function termDateLabel(term) {
    return term.start_date == null
      ? 'Dates not yet published — planning placeholder, not a confirmed schedule'
      : `${dateLabel(term.start_date)} – ${dateLabel(term.end_date)}`;
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
    const completedResult = storage.read(`${storageKey}:completed`);
    if (completedResult.ok) completedCourses.value = completedResult.value || '';
    else warnStorage();
    refreshPlannerCalendar();
    if (migrationNotice) plannerMessage.textContent = migrationNotice;
  }

  function refreshPlannerCalendar() {
    const terms = planningTerms();
    plannerTerm.replaceChildren(...terms.map(term => new Option(`${term.name} · ${term.start_date == null ? 'Dates not yet published' : dateLabel(term.start_date)}`, term.code)));
    const calendar = activeCalendar();
    if (!calendar) {
      calendarCoverage.textContent = 'No academic calendar is configured.';
    } else {
      const academicYears = [...new Set(terms.map(term => term.academic_year).filter(Boolean))];
      const coverage = academicYears.length ? `academic years ${academicYears[0]}–${academicYears.at(-1)}` : 'no currently plannable academic periods';
      const shortfall = academicYears.length < 4 ? ' The calendar does not cover the full four-academic-period horizon.' : '';
      calendarCoverage.textContent = `${data.university.academic_calendar_system} institution · ${calendar.name} covers ${coverage}.${shortfall} Terms without dates are planning placeholders, not confirmed schedules. Logical alternatives in prerequisite text should be confirmed with an adviser.`;
    }
    renderPlan();
  }

  function resolveCourse(value) { return PlannerCore.resolveCourse(courses, value); }

  function offeringBadge(evaluation) {
    if (evaluation.status === 'confirmed') return { label: 'Confirmed', detail: `Exact-term record: ${evaluation.exactStatus}.` };
    if (evaluation.status === 'cancelled') return { label: 'Cancelled', detail: 'An exact-term cancellation is recorded.' };
    if (evaluation.status === 'lacking-data') return { label: 'No offering data', detail: 'Availability is unconfirmed because no offering records are stored.' };
    if (evaluation.status === 'historically-unusual') return { label: 'Unconfirmed · unusual term', detail: 'No exact-term record; past held records are for other term types and do not predict availability.' };
    if (evaluation.historicalContext === 'typical') return { label: 'Unconfirmed · seen historically', detail: 'No exact-term record; prior offerings in this term type do not guarantee availability.' };
    return { label: 'Unconfirmed', detail: 'No exact-term offering record is stored.' };
  }

  function renderPlan() {
    const terms = planningTerms();
    planGrid.replaceChildren(...terms.map(term => {
      const section = document.createElement('section');
      section.className = 'plan-term';
      const heading = document.createElement('h3');
      heading.textContent = term.name;
      const dates = document.createElement('span');
      dates.className = 'term-dates';
      dates.textContent = termDateLabel(term);
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
          if (course) {
            const evaluation = PlannerCore.evaluateOffering(course, term);
            const badgeCopy = offeringBadge(evaluation);
            const badge = document.createElement('small');
            badge.className = `availability-badge ${evaluation.status}`;
            badge.textContent = badgeCopy.label;
            badge.setAttribute('title', badgeCopy.detail);
            label.append(badge);
          }
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
        const missing = PlannerCore.evaluateRequirements(edges, code, 'prerequisite', seen);
        if (missing.length) {
          addIssue('error', `Possible missing prerequisite for ${code}`, `${term.name}: ${PlannerCore.describeRequirementGroups(missing)} earlier, or verify qualifications in the catalog wording.`);
          issues += 1;
        }
        const missingCoreq = PlannerCore.evaluateRequirements(edges, code, 'corequisite', seen, sameTerm);
        if (missingCoreq.length) {
          addIssue('error', `Missing corequisite for ${code}`, `${term.name}: ${PlannerCore.describeRequirementGroups(missingCoreq, 'add')} in this or an earlier term.`);
          issues += 1;
        }
        const offering = PlannerCore.evaluateOffering(course, term);
        if (offering.status === 'cancelled') {
          addIssue('error', `Cancelled offering: ${code}`, `${code} has an exact-term cancellation record for ${term.name}. Choose another course or verify a newer official schedule.`);
          issues += 1;
        } else if (offering.status === 'historically-unusual') {
          addIssue('warning', `Availability unconfirmed: ${code}`, `No exact offering record exists for ${term.name}. Stored past offerings were in other term types; that history does not predict a future offering.`);
          issues += 1;
        }
      });
      sameTerm.forEach(code => seen.add(code));
    });
    issueCount.textContent = `${issues} issue${issues === 1 ? '' : 's'}`;
    if (!issues) {
      const clear = document.createElement('p');
      clear.className = 'all-clear';
      clear.textContent = 'No prerequisite, duplicate, cancellation, or unusual-history issues found. Check each course badge for offering availability.';
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
    const csv = `\uFEFF${rows.map(row => row.map(csvCell).join(',')).join('\r\n')}\r\n`;
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `${data.university?.slug || 'university'}-proposed-schedule.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function reportImportError(message) {
    plannerMessage.textContent = message;
    plannerMessage.focus?.();
  }

  async function importSchedule(file) {
    const maxFileSize = 1024 * 1024; const maxRows = 10000;
    if (Number.isFinite(file.size) && file.size > maxFileSize) { reportImportError('The CSV is too large. Choose a file no larger than 1 MB.'); return; }
    let text;
    try { text = await file.text(); } catch { reportImportError('The CSV could not be read. Choose another file and try again.'); return; }
    let result;
    try { result = PlannerCore.importRows(text, activeCalendar()?.terms || [], courses, activeCalendarId, plan); }
    catch { reportImportError('The CSV could not be parsed. Check its formatting and try again.'); return; }
    if (result.rowCount > maxRows) { reportImportError(`The CSV has too many rows. The limit is ${maxRows.toLocaleString()}.`); return; }
    if (result.error) { reportImportError(result.error); return; }
    const headerErrors = result.errors.filter(error => error.row === 1);
    if (headerErrors.length) { reportImportError(`The CSV header is invalid: ${headerErrors.map(error => `${error.message} (row ${error.row}, column ${error.column})`).join(' ')}`); return; }
    const rejected = result.failures;
    const failureSummary = rejected.map(item => `row ${item.row}: ${item.category}`).join('; ');
    if (!result.additions.length) { reportImportError(`No courses were imported.${rejected.length ? ` Rejected ${failureSummary}.` : ''}`); return; }
    if (rejected.length && !window.confirm(`Import ${result.additions.length} valid course${result.additions.length === 1 ? '' : 's'} and reject ${rejected.length} row${rejected.length === 1 ? '' : 's'}? ${failureSummary}`)) {
      plannerMessage.textContent = 'Import cancelled; the schedule was not changed.'; return;
    }
    const nextPlan = cleanPlan(plan);
    result.additions.forEach(({ termCode, courseCode }) => { nextPlan[termCode] = [...(nextPlan[termCode] || []), courseCode]; });
    plan = nextPlan;
    savePlan();
    renderPlan();
    plannerMessage.textContent = `${result.additions.length} course${result.additions.length === 1 ? '' : 's'} imported into ${activeCalendar()?.name || 'the schedule'}.${rejected.length ? ` Rejected ${failureSummary}.` : ''}`;
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
    checkPlan(planningTerms());
    clearTimeout(completedSaveTimer);
    completedSaveTimer = setTimeout(() => {
      if (!storage.write(`${storageKey}:completed`, completedCourses.value).ok) warnStorage();
    }, 300);
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
