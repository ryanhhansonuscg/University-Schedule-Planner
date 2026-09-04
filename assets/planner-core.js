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

  function termPosition(term) {
    const year = academicYearStart(term);
    const sequence = Number(term.sequence);
    return Number.isFinite(year) && year !== Number.MAX_SAFE_INTEGER && Number.isFinite(sequence)
      ? { year, sequence }
      : null;
  }

  function comparePositions(a, b) {
    return a.year - b.year || a.sequence - b.sequence;
  }

  function planningTerms(calendars, calendarId, now = new Date()) {
    const calendar = (calendars || []).find(item => item.id === calendarId);
    const today = new Date(now); today.setHours(0, 0, 0, 0);
    const cutoff = new Date(today); cutoff.setFullYear(cutoff.getFullYear() + 4);
    const empty = {
      terms: [],
      horizon: { years: 4, start: today, endpoint: cutoff, endpointCovered: false, dependsOnUnpublishedDates: false },
    };
    if (!calendar) return empty;
    const enabled = (calendar.terms || []).filter(term => term.planning_enabled).sort(compareTerms);
    const dated = enabled.filter(term => dateValue(term.start_date) && dateValue(term.end_date));
    // The horizon is the closed interval [today, the same calendar date four years
    // later]. A dated term belongs when its own closed interval intersects it.
    const selectedDated = dated.filter(term => dateValue(term.end_date) >= today && dateValue(term.start_date) <= cutoff);

    // Undated terms are compared to today's academic position. This preserves the
    // fraction of the current academic year: e.g. spring-to-spring includes four
    // future springs rather than allowing the current, nearly-finished year to
    // count as one of four labels.
    const anchorTerm = dated.find(term => dateValue(term.start_date) <= today && dateValue(term.end_date) >= today)
      || dated.find(term => dateValue(term.end_date) >= today);
    const anchor = anchorTerm && termPosition(anchorTerm);
    const endpointPosition = anchor && { year: anchor.year + 4, sequence: anchor.sequence };
    const undated = enabled.filter(term => !dateValue(term.start_date) || !dateValue(term.end_date));
    const selectedUndated = anchor ? undated.filter(term => {
      const position = termPosition(term);
      return position && comparePositions(position, anchor) >= 0 && comparePositions(position, endpointPosition) <= 0;
    }) : [];

    const datedEndpointCoverage = dated.some(term => dateValue(term.start_date) <= cutoff && dateValue(term.end_date) >= cutoff);
    const unpublishedEndpointCoverage = !datedEndpointCoverage && endpointPosition && undated.some(term => {
      const position = termPosition(term);
      return position && position.year === endpointPosition.year && position.sequence === endpointPosition.sequence;
    });
    return {
      terms: [...selectedDated, ...selectedUndated].sort(compareTerms),
      horizon: {
        years: 4,
        start: today,
        endpoint: cutoff,
        endpointCovered: Boolean(datedEndpointCoverage || unpublishedEndpointCoverage),
        dependsOnUnpublishedDates: Boolean(unpublishedEndpointCoverage),
      },
    };
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

  function parseCompletedCourses(value, courses, edges = []) {
    const catalogCodes = new Map((courses || []).map(course => [course.code.replace(/\s/g, '').toUpperCase(), course.code]));
    const externalCodes = new Map((edges || [])
      .filter(edge => edge.source_in_database === false && typeof edge.source === 'string')
      .map(edge => [edge.source.replace(/\s/g, '').toUpperCase(), edge.source]));
    const codes = []; const unknownTokens = [];
    // Commas, semicolons, and lines are the unambiguous delimiters. Within each
    // part, accept either compact codes or the common "CS 101" spelling.
    String(value || '').split(/[,;\n]+/).forEach(part => {
      const words = part.trim().split(/\s+/).filter(Boolean);
      for (let index = 0; index < words.length; index += 1) {
        let token = words[index];
        if (/^[A-Za-z][A-Za-z&-]*$/.test(token) && /^\d{2,4}[A-Za-z]?$/.test(words[index + 1] || '')) {
          token += words[index + 1]; index += 1;
        }
        const normalized = token.replace(/\s/g, '').toUpperCase();
        const code = catalogCodes.get(normalized) || externalCodes.get(normalized);
        if (code) codes.push(code);
        else unknownTokens.push(token);
      }
    });
    return { codes: [...new Set(codes)], unknownTokens };
  }

  function repeatabilityWording(course) {
    const wording = typeof course?.repeatable === 'string' ? course.repeatable.trim() : '';
    if (!wording || /^(?:no|none|false|not repeatable)$/i.test(wording)
      || /\b(?:not|never|cannot|can't|may not)\s+(?:be\s+)?repeat/i.test(wording)) return '';
    return /\b(?:repeat(?:ed|able|ing)?|multiple times|additional credit|more than once)\b/i.test(wording) ? wording : '';
  }

  function parseCredits(value) {
    if (typeof value !== 'string' && typeof value !== 'number') return null;
    const text = String(value).trim();
    // Catalog credit values are either one non-negative number or a range. Do
    // not partially parse malformed values (for example, "3 credits").
    const match = text.match(/^(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?))?$/);
    if (!match) return null;
    const min = Number(match[1]);
    const max = Number(match[2] ?? match[1]);
    if (!Number.isFinite(min) || !Number.isFinite(max) || min > max) return null;
    return { min, max };
  }

  function accumulateCredits(values) {
    return (Array.isArray(values) ? values : []).reduce((total, value) => {
      const parsed = parseCredits(value && typeof value === 'object' ? value.credits : value);
      if (parsed) {
        // Limit floating-point artifacts without changing meaningful decimal
        // credit precision.
        total.min = Number((total.min + parsed.min).toFixed(12));
        total.max = Number((total.max + parsed.max).toFixed(12));
      }
      return total;
    }, { min: 0, max: 0 });
  }

  function serializePlan(plan) { return JSON.stringify(plan && typeof plan === 'object' ? plan : {}); }
  function deserializePlan(value) {
    try { const plan = JSON.parse(value || '{}'); return plan && typeof plan === 'object' && !Array.isArray(plan) ? plan : {}; } catch { return {}; }
  }

  function storageError(operation, error) {
    return {
      operation,
      name: typeof error?.name === 'string' ? error.name : 'Error',
      message: typeof error?.message === 'string' ? error.message : 'Browser storage is unavailable.',
    };
  }

  function createStorageAdapter(storage) {
    // A provider function also guards browsers that throw merely while the
    // localStorage property is being accessed (before getItem is called).
    const getStorage = () => (typeof storage === 'function' ? storage() : storage);
    return {
      read(key) {
        try { return { ok: true, value: getStorage().getItem(key) }; }
        catch (error) { return { ok: false, value: null, error: storageError('read', error) }; }
      },
      write(key, value) {
        try { getStorage().setItem(key, value); return { ok: true }; }
        catch (error) { return { ok: false, error: storageError('write', error) }; }
      },
      remove(key) {
        try { getStorage().removeItem(key); return { ok: true }; }
        catch (error) { return { ok: false, error: storageError('remove', error) }; }
      },
    };
  }

  function isRecord(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
  function validStorageKey(value) { return typeof value === 'string' && value.length > 0 && value.length <= 200 && !/[\u0000-\u001f]/.test(value); }
  function validCourseCode(value) { return typeof value === 'string' && value === value.trim() && value.length > 0 && value.length <= 100 && !/[\u0000-\u001f]/.test(value); }
  function validatePlanMap(value) {
    return isRecord(value) && Object.entries(value).every(([termCode, codes]) =>
      validStorageKey(termCode) && Array.isArray(codes) && codes.every(validCourseCode));
  }
  function validateStoredPlans(value, version) {
    if (!isRecord(value) || value.version !== version || !isRecord(value.calendars) || !isRecord(value.migration)) return false;
    if (!Object.entries(value.calendars).every(([calendarId, plan]) => validStorageKey(calendarId) && validatePlanMap(plan))) return false;
    if (version >= 3 && (!isRecord(value.recovery)
      || !Object.entries(value.recovery).every(([calendarId, plan]) => validStorageKey(calendarId) && validatePlanMap(plan)))) return false;
    const migrationKeys = Object.keys(value.migration);
    return migrationKeys.every(key => key === 'unmatched')
      && (!Object.hasOwn(value.migration, 'unmatched') || validatePlanMap(value.migration.unmatched));
  }
  function csvCell(value) { return `"${String(value ?? '').replaceAll('"', '""')}"`; }
  function scheduleCsv(terms, plan, courses) {
    const byCode = new Map(courses.map(course => [course.code, course]));
    const rows = [['Term', 'Course #', 'Course Name', 'Course Hours']];
    terms.forEach(term => (plan[term.code] || []).forEach(code => { const course = byCode.get(code); rows.push([term.name, code, course?.title || '', course?.credits || '']); }));
    return `\uFEFF${rows.map(row => row.map(csvCell).join(',')).join('\r\n')}\r\n`;
  }
  function csvRowCount(text, stopAfter = Number.POSITIVE_INFINITY) {
    const source = String(text ?? '').replace(/^\uFEFF/, '');
    let quoted = false; let rowHasContent = false; let count = 0;
    for (let index = 0; index < source.length; index += 1) {
      const char = source[index];
      if (char === '"') {
        rowHasContent = true;
        if (quoted && source[index + 1] === '"') index += 1;
        else quoted = !quoted;
      } else if (char === '\n' && !quoted) {
        if (rowHasContent) count += 1;
        rowHasContent = false;
        if (count > stopAfter) return count;
      } else if (char !== '\r' && !/\s/.test(char)) rowHasContent = true;
    }
    return count + (rowHasContent ? 1 : 0);
  }
  function parseCsv(text) {
    const rows = []; const rowLocations = []; const errors = []; let row = []; let cell = ''; let quoted = false; let closedQuote = false;
    let physicalRow = 1; let column = 1; let rowStart = 1; let quoteStart;
    const addError = (type, message, atRow = physicalRow, atColumn = column) => errors.push({ type, message, row: atRow, column: atColumn });
    const finishCell = () => { row.push(quoted || closedQuote ? cell : cell.trim()); cell = ''; closedQuote = false; };
    const finishRow = () => {
      finishCell();
      if (row.some(value => value !== '') || row.length > 1) { rows.push(row); rowLocations.push(rowStart); }
      row = []; rowStart = physicalRow + 1;
    };
    const source = String(text ?? '').replace(/^\uFEFF/, '');
    for (let i = 0; i < source.length; i += 1) {
      const char = source[i];
      if (quoted) {
        if (char === '"' && source[i + 1] === '"') { cell += '"'; i += 1; column += 1; }
        else if (char === '"') { quoted = false; closedQuote = true; }
        else cell += char;
      } else if (closedQuote) {
        if (char === ',') finishCell();
        else if (char === '\n') finishRow();
        else if (char !== '\r' && !/\s/.test(char)) { addError('unexpected-quote', 'Unexpected character after a closing quote.'); cell += char; closedQuote = false; }
      } else if (char === '"') {
        if (cell.trim() !== '') { addError('unexpected-quote', 'Unexpected quote in an unquoted field.'); cell += char; }
        else { cell = ''; quoted = true; quoteStart = { row: physicalRow, column }; }
      } else if (char === ',') finishCell();
      else if (char === '\n') finishRow();
      else if (char !== '\r') cell += char;
      if (char === '\n') { physicalRow += 1; column = 1; }
      else column += 1;
    }
    if (quoted) addError('unterminated-field', 'Unterminated quoted field.', quoteStart.row, quoteStart.column);
    if (cell !== '' || row.length) finishRow();
    if (rows.length) {
      const width = rows[0].length;
      rows.forEach((values, index) => { if (values.length !== width) errors.push({ type: 'inconsistent-width', message: `Expected ${width} cells but found ${values.length}.`, row: rowLocations[index], column: Math.min(values.length + 1, width) }); });
      const normalized = rows[0].map(value => String(value).toLowerCase().replace(/[^a-z0-9]/g, ''));
      const seen = new Map();
      normalized.forEach((value, index) => {
        if (!value) errors.push({ type: 'empty-header', message: 'Header cells cannot be empty.', row: rowLocations[0], column: index + 1 });
        else if (seen.has(value)) errors.push({ type: 'duplicate-header', message: `Duplicate normalized header “${value}”.`, row: rowLocations[0], column: index + 1 });
        else seen.set(value, index);
      });
    }
    return { rows, rowLocations, errors };
  }
  function importRows(text, terms, courses, activeCalendarId = '', existingPlan = {}) {
    const parsed = parseCsv(text); const { rows } = parsed; const additions = []; const failures = [];
    if (!rows.length) return { additions, records: additions, failures, errors: parsed.errors, error: 'The CSV must include a header and at least one schedule row.' };
    const headers = rows[0].map(value => value.toLowerCase().replace(/[^a-z0-9]/g, ''));
    const termIndex = headers.indexOf('term'); const termCodeIndex = headers.indexOf('termcode'); const calendarIndex = headers.indexOf('calendarid');
    const codeIndex = headers.findIndex(value => ['course', 'coursecode', 'coursenumber'].includes(value)); const nameIndex = headers.indexOf('coursename');
    if ((termIndex < 0 && termCodeIndex < 0) || (codeIndex < 0 && nameIndex < 0)) return { additions, records: additions, failures, errors: parsed.errors, error: 'Import requires a Term Code or Term column and either Course # or Course Name.' };
    if (rows.length < 2) return { additions, records: additions, failures, errors: parsed.errors, error: 'The CSV contains only headers; include at least one schedule row.' };
    const headerRow = parsed.rowLocations[0] || 1;
    const parseErrorsByRow = new Map(parsed.errors.filter(error => error.row !== headerRow).map(error => [error.row, error]));
    const termByCode = new Map(terms.map(term => [term.code.toLowerCase(), term]));
    const coursesByCode = new Map(courses.map(course => [course.code.toUpperCase(), course]));
    const scheduled = new Set(Object.entries(existingPlan || {}).flatMap(([term, codes]) => (codes || []).map(code => `${term}\0${code}`)));
    rows.slice(1).forEach((row, index) => {
      const rowNumber = parsed.rowLocations[index + 1] || index + 2;
      const fail = (category, message, column = 1, type = category.replaceAll(' ', '-')) => failures.push({ row: rowNumber, column, category, type, message });
      const parseError = parseErrorsByRow.get(rowNumber);
      if (parseError) { fail('malformed row', parseError.message, parseError.column, parseError.type); return; }
      if (row.length !== headers.length) { fail('malformed row', 'The row has an inconsistent number of cells.', Math.min(row.length + 1, headers.length), 'inconsistent-width'); return; }
      if (calendarIndex >= 0 && !row[calendarIndex]) { fail('malformed row', 'Calendar ID is required.', calendarIndex + 1, 'missing-required-cell'); return; }
      if ((termCodeIndex < 0 || !row[termCodeIndex]) && (termIndex < 0 || !row[termIndex])) { fail('malformed row', 'A Term Code or Term is required.', (termCodeIndex >= 0 ? termCodeIndex : termIndex) + 1, 'missing-required-cell'); return; }
      if ((codeIndex < 0 || !row[codeIndex]) && (nameIndex < 0 || !row[nameIndex])) { fail('malformed row', 'A Course # or Course Name is required.', (codeIndex >= 0 ? codeIndex : nameIndex) + 1, 'missing-required-cell'); return; }
      if (calendarIndex >= 0 && row[calendarIndex] !== activeCalendarId) { fail('wrong calendar', `Calendar ID does not match ${activeCalendarId}.`, calendarIndex + 1); return; }
      let term;
      if (termCodeIndex >= 0 && row[termCodeIndex]) term = termByCode.get(row[termCodeIndex].toLowerCase());
      else {
        const label = (row[termIndex] || '').toLowerCase(); const matches = terms.filter(item => item.name.toLowerCase() === label);
        if (matches.length > 1) { fail('ambiguous term name', 'The term name matches multiple terms; use Term Code.', termIndex + 1); return; }
        term = matches[0];
      }
      if (!term) { fail('unknown term', 'The term was not recognized.', (termCodeIndex >= 0 && row[termCodeIndex] ? termCodeIndex : termIndex) + 1); return; }
      let course;
      if (codeIndex >= 0 && row[codeIndex]) course = coursesByCode.get(row[codeIndex].replace(/\s/g, '').toUpperCase());
      else {
        const title = (row[nameIndex] || '').toLowerCase(); const matches = courses.filter(item => item.title.toLowerCase() === title || item.title.toLowerCase().includes(title));
        if (matches.length > 1) { fail('ambiguous course title', 'The course title matches multiple courses; use Course #.', nameIndex + 1); return; }
        course = matches[0];
      }
      if (!course) { fail('unknown course', 'The course was not recognized.', (codeIndex >= 0 && row[codeIndex] ? codeIndex : nameIndex) + 1); return; }
      const key = `${term.code}\0${course.code}`;
      if (scheduled.has(key)) { fail('duplicate schedule entry', 'The course is already scheduled in this term.', (codeIndex >= 0 && row[codeIndex] ? codeIndex : nameIndex) + 1); return; }
      scheduled.add(key); additions.push({ termCode: term.code, courseCode: course.code });
    });
    return { additions, records: additions, failures, skipped: failures.map(item => item.row), errors: [...parsed.errors, ...failures], headerRow, rowCount: rows.length - 1 };
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
  return { planningTerms, compareTerms, resolveCourse, parseCompletedCourses, repeatabilityWording, parseCredits, accumulateCredits, serializePlan, deserializePlan, createStorageAdapter, validatePlanMap, validateStoredPlans, scheduleCsv, csvRowCount, parseCsv, importRows, requirementGroups, evaluateRequirements, describeRequirementGroups, prerequisiteMissing, evaluateOffering, offeringDiagnostic };
}));
