(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.PlannerCore = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function dateValue(value) { return value == null ? null : new Date(`${value}T00:00:00`); }

  function academicYearStart(term) {
    const year = Number.parseInt(String(term.academic_year || '').split('-')[0], 10);
    return Number.isFinite(year) ? year : Number.MAX_SAFE_INTEGER;
  }

  function compareTerms(a, b) {
    const yearDifference = academicYearStart(a) - academicYearStart(b);
    if (yearDifference) return yearDifference;
    const aDate = dateValue(a.start_date); const bDate = dateValue(b.start_date);
    if (aDate && bDate) return aDate - bDate;
    return Number(a.sequence) - Number(b.sequence);
  }

  function planningTerms(calendars, calendarId, now = new Date()) {
    const calendar = (calendars || []).find(item => item.id === calendarId);
    if (!calendar) return [];
    const today = new Date(now); today.setHours(0, 0, 0, 0);
    const eligible = (calendar.terms || []).filter(term => {
      if (!term.planning_enabled) return false;
      const end = dateValue(term.end_date);
      return end === null || end >= today;
    }).sort(compareTerms);
    // Four academic periods means four distinct academic years represented by the
    // calendar, not an arbitrary date exactly four years from today.
    const horizonYears = new Set();
    eligible.forEach(term => {
      if (term.academic_year && (horizonYears.has(term.academic_year) || horizonYears.size < 4)) horizonYears.add(term.academic_year);
    });
    return eligible.filter(term => horizonYears.has(term.academic_year));
  }

  function resolveCourse(courses, value) {
    const raw = String(value || '').trim();
    if (!raw) return null;
    const byCode = new Map(courses.map(course => [course.code, course]));
    const direct = byCode.get(raw.replace(/\s/g, '').toUpperCase());
    if (direct) return direct;
    const prefix = raw.match(/^([A-Za-z]{2,}\s*\d{2,4}[A-Za-z]?)/)?.[1].replace(/\s/g, '').toUpperCase();
    if (prefix && byCode.has(prefix)) return byCode.get(prefix);
    const normalized = raw.toLowerCase();
    const matches = courses.filter(course => course.title.toLowerCase() === normalized || course.title.toLowerCase().includes(normalized));
    return matches.length === 1 ? matches[0] : null;
  }

  function serializePlan(plan) { return JSON.stringify(plan && typeof plan === 'object' ? plan : {}); }
  function deserializePlan(value) {
    try { const plan = JSON.parse(value || '{}'); return plan && typeof plan === 'object' && !Array.isArray(plan) ? plan : {}; } catch { return {}; }
  }
  function csvCell(value) { return `"${String(value ?? '').replaceAll('"', '""')}"`; }
  function scheduleCsv(terms, plan, courses) {
    const byCode = new Map(courses.map(course => [course.code, course]));
    const rows = [['Term', 'Course #', 'Course Name', 'Course Hours']];
    terms.forEach(term => (plan[term.code] || []).forEach(code => { const course = byCode.get(code); rows.push([term.name, code, course?.title || '', course?.credits || '']); }));
    return `\uFEFF${rows.map(row => row.map(csvCell).join(',')).join('\r\n')}\r\n`;
  }
  function parseCsv(text) {
    const rows = []; let row = []; let cell = ''; let quoted = false;
    for (let i = 0; i < text.length; i += 1) { const char = text[i];
      if (quoted) { if (char === '"' && text[i + 1] === '"') { cell += '"'; i += 1; } else if (char === '"') quoted = false; else cell += char; }
      else if (char === '"') quoted = true; else if (char === ',') { row.push(cell.trim()); cell = ''; }
      else if (char === '\n') { row.push(cell.trim()); if (row.some(Boolean)) rows.push(row); row = []; cell = ''; }
      else if (char !== '\r' && char !== '\uFEFF') cell += char;
    }
    if (quoted) throw new Error('Unclosed quoted CSV field');
    row.push(cell.trim()); if (row.some(Boolean)) rows.push(row); return rows;
  }
  function importRows(text, terms, courses) {
    const rows = parseCsv(text); if (rows.length < 2) return { error: 'The CSV must include a header and at least one schedule row.' };
    const headers = rows[0].map(value => value.toLowerCase().replace(/[^a-z0-9]/g, ''));
    const termIndex = headers.indexOf('term'); const codeIndex = headers.findIndex(value => ['course', 'coursecode', 'coursenumber'].includes(value)); const nameIndex = headers.indexOf('coursename');
    if (termIndex < 0 || (codeIndex < 0 && nameIndex < 0)) return { error: 'Import requires a Term column and either Course # or Course Name.' };
    const termMap = new Map(); terms.forEach(term => { termMap.set(term.code.toLowerCase(), term); termMap.set(term.name.toLowerCase(), term); });
    const records = []; const skipped = [];
    rows.slice(1).forEach((row, i) => { const term = termMap.get((row[termIndex] || '').toLowerCase()); const course = resolveCourse(courses, (codeIndex >= 0 ? row[codeIndex] : '') || (nameIndex >= 0 ? row[nameIndex] : '')); if (term && course) records.push({ termCode: term.code, courseCode: course.code }); else skipped.push(i + 2); });
    return { records, skipped };
  }
  function requirementGroups(edges, target, kind) {
    const groups = new Map();
    (edges || []).filter(edge => edge.target === target && edge.kind === kind).forEach((edge, index) => {
      const structured = typeof edge.logic_group === 'string' && edge.logic_group && ['AND', 'OR'].includes(edge.logic_operator);
      const key = structured ? edge.logic_group : `__edge_${index}`;
      if (!groups.has(key)) groups.set(key, { id: structured ? key : null, operator: structured ? edge.logic_operator : 'AND', sources: [] });
      const group = groups.get(key);
      // Invalid/conflicting runtime data is never relaxed into an alternative.
      if (!structured || group.operator !== edge.logic_operator) group.operator = 'AND';
      group.sources.push(edge.source);
    });
    return [...groups.values()];
  }
  function evaluateRequirements(edges, target, kind, completed, concurrent = new Set()) {
    const available = new Set([...(completed || []), ...(kind === 'corequisite' ? concurrent || [] : [])]);
    return requirementGroups(edges, target, kind).filter(group => group.operator === 'OR'
      ? !group.sources.some(source => available.has(source))
      : group.sources.some(source => !available.has(source))).map(group => ({
        ...group,
        sources: group.operator === 'AND' ? group.sources.filter(source => !available.has(source)) : group.sources,
      }));
  }
  function describeRequirementGroups(groups, verb = 'complete') {
    return groups.map(group => group.operator === 'OR'
      ? `${verb} one of ${group.sources.join(' or ')}`
      : `${verb} ${group.sources.join(' and ')}`).join('; and ');
  }
  function prerequisiteMissing(edges, target, seen) {
    return evaluateRequirements(edges, target, 'prerequisite', seen).flatMap(group => group.sources.filter(source => !seen.has(source)));
  }
  function evaluateOffering(course, term) {
    const history = Array.isArray(course?.offering_history) ? course.offering_history : [];
    if (!history.length) return { status: 'lacking-data', exactStatus: null, historicalContext: 'none' };

    const exact = history.filter(item => item.term_code === term?.code);
    // A cancellation is the most consequential exact-term fact, even when a
    // stale or conflicting scheduled record is also present.
    if (exact.some(item => item.offering_status === 'cancelled')) {
      return { status: 'cancelled', exactStatus: 'cancelled', historicalContext: 'none' };
    }
    const confirmed = exact.find(item => ['scheduled', 'held'].includes(item.offering_status));
    if (confirmed) return { status: 'confirmed', exactStatus: confirmed.offering_status, historicalContext: 'none' };

    const historical = history.filter(item => item.term_status === 'historical' && item.offering_status === 'held');
    if (!historical.length) return { status: 'not-listed', exactStatus: null, historicalContext: 'none' };
    if (historical.some(item => item.term_type === term?.term_type)) {
      return { status: 'not-listed', exactStatus: null, historicalContext: 'typical' };
    }
    return { status: 'historically-unusual', exactStatus: null, historicalContext: 'unusual' };
  }

  // Retained for integrations that consumed the former, less expressive API.
  function offeringDiagnostic(course, term) {
    const status = evaluateOffering(course, term).status;
    if (status === 'lacking-data') return 'unavailable';
    if (status === 'historically-unusual') return 'unusual';
    return status === 'confirmed' ? null : status;
  }
  return { planningTerms, compareTerms, resolveCourse, serializePlan, deserializePlan, scheduleCsv, parseCsv, importRows, requirementGroups, evaluateRequirements, describeRequirementGroups, prerequisiteMissing, evaluateOffering, offeringDiagnostic };
}));
