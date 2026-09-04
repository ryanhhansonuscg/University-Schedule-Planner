const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');
const PlannerCore = require('../assets/planner-core.js');

const plannerSource = fs.readFileSync(new URL('../assets/planner.js', `file://${__filename}`), 'utf8');

class Element {
  constructor(id = '') {
    this.id = id;
    this.value = '';
    this.textContent = '';
    this.disabled = false;
    this.hidden = false;
    this.children = [];
    this.listeners = {};
    this.files = [];
  }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); return child; }
  remove() {}
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this[name] = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  async dispatch(name, extra = {}) { return this.listeners[name]?.({ target: this, preventDefault() {}, ...extra }); }
  click() { return this.dispatch('click'); }
  get options() { return this.children; }
  get selectedIndex() { return Math.max(0, this.children.findIndex(child => child.value === this.value)); }
}

function catalog() {
  return {
    university: { slug: 'test-u', name: 'Test U', academic_calendar_system: 'Mixed' },
    courses: [
      { code: 'CS101', title: 'Intro', credits: 3, offering_history: [
        { term_code: 'S27', term_type: 'spring', term_status: 'future', offering_status: 'scheduled' },
        { term_code: 'S27', term_type: 'spring', term_status: 'future', offering_status: 'cancelled' },
      ] },
      { code: 'CS102', title: 'Next', credits: 4, offering_history: [
        { term_code: 'OLD', term_type: 'fall', term_status: 'historical', offering_status: 'held' },
      ] },
      { code: 'ART200', title: 'Studio', credits: 3, repeatable: 'May be repeated for up to 9 credits.', offering_history: [] },
    ],
    edges: [{ source: 'EXTERNAL100', target: 'CS102', kind: 'prerequisite', source_in_database: false }],
    academic_calendars: [
      { id: 'semester', name: 'Semester', system_type: 'semester', is_primary: true, terms: [
        { code: 'S27', name: 'Spring', academic_year: '2026-2027', sequence: 1, term_type: 'spring', planning_enabled: true, start_date: '2027-01-01', end_date: '2027-05-01' },
        { code: 'TBD', name: 'Future term', academic_year: '2027-2028', sequence: 1, term_type: 'fall', planning_enabled: true, start_date: null, end_date: null },
        { code: 'OLD', name: 'Archive', academic_year: '2019-2020', sequence: 1, term_type: 'fall', planning_enabled: false, start_date: '2020-01-01', end_date: '2020-05-01' },
        { code: 'PAST', name: 'Past enabled', academic_year: '2020-2021', sequence: 1, term_type: 'fall', planning_enabled: true, start_date: '2020-08-01', end_date: '2020-12-01' },
        { code: 'OFF', name: 'Disabled future', academic_year: '2027-2028', sequence: 2, term_type: 'spring', planning_enabled: false, start_date: '2028-01-01', end_date: '2028-05-01' },
      ] },
      { id: 'quarter', name: 'Quarter', system_type: 'quarter', terms: [
        { code: 'Q27', name: 'Spring', academic_year: '2026-2027', sequence: 1, term_type: 'spring', planning_enabled: true, start_date: '2027-01-02', end_date: '2027-03-01' },
      ] },
    ],
  };
}

async function setup(saved = null, storageDouble = null) {
  const ids = ['planner-calendar', 'planner-course-search', 'course-options', 'planner-term', 'completed-courses', 'plan-grid', 'issue-list', 'issue-count', 'calendar-coverage', 'planner-message', 'storage-warning', 'export-schedule', 'clear-schedule', 'import-schedule', 'add-to-plan', 'load-status', 'planner', 'app', 'recovery-notice', 'recovery-summary', 'export-recovery', 'reassign-recovery', 'remove-recovery'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
  const values = new Map(saved === null ? [] : [['college-schedule-plan:test-u', JSON.stringify(saved)]]);
  let exportedBlob;
  let downloadName;
  const document = {
    title: '', body: new Element('body'),
    getElementById: id => elements[id],
    createElement: tag => {
      const element = new Element();
      if (tag === 'a') element.click = () => { downloadName = element.download; };
      return element;
    },
  };
  const context = {
    window: { COLLEGE_PLANNER: { loadCatalog: async () => ({ catalog: catalog() }) }, confirm: () => true },
    document,
    localStorage: storageDouble || { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) },
    Option: class extends Element { constructor(text, value) { super(); this.text = text; this.textContent = text; this.value = value; } },
    Blob, Date, Set, Map, setTimeout, clearTimeout,
    PlannerCore,
    URL: { createObjectURL: blob => { exportedBlob = blob; return 'blob:test'; }, revokeObjectURL() {} },
  };
  vm.runInNewContext(plannerSource, context);
  await new Promise(resolve => setImmediate(resolve));
  return { elements, values, exported: async () => exportedBlob?.text(), downloadName };
}

async function addCourse(app, course, term) {
  app.elements['planner-course-search'].value = course;
  app.elements['planner-term'].value = term;
  await app.elements['add-to-plan'].click();
}

test('switching calendars isolates plans with overlapping visible term names', async () => {
  const app = await setup();
  await addCourse(app, 'CS101', 'S27');
  app.elements['planner-calendar'].value = 'quarter';
  await app.elements['planner-calendar'].dispatch('change');
  assert.equal(app.elements['export-schedule'].disabled, true);
  assert.match(app.elements['planner-message'].textContent, /Semester to Quarter/);
  await addCourse(app, 'CS102', 'Q27');
  app.elements['planner-calendar'].value = 'semester';
  await app.elements['planner-calendar'].dispatch('change');
  const stored = JSON.parse(app.values.get('college-schedule-plan:test-u'));
  assert.deepEqual(stored.calendars.semester.S27, ['CS101']);
  assert.deepEqual(stored.calendars.quarter.Q27, ['CS102']);
});

test('migrates old storage by term code and preserves unmatched entries', async () => {
  const app = await setup({ S27: ['CS101'], Q27: ['CS102'], MISSING: ['CS101'] });
  const stored = JSON.parse(app.values.get('college-schedule-plan:test-u'));
  assert.equal(stored.version, 3);
  assert.deepEqual(stored.calendars.semester.S27, ['CS101']);
  assert.deepEqual(stored.calendars.quarter.Q27, ['CS102']);
  assert.deepEqual(stored.recovery._unmatched.MISSING, ['CS101']);
  assert.match(app.elements['planner-message'].textContent, /recovery bucket/);
});

test('clear removes visible entries but preserves hidden recovery entries', async () => {
  const app = await setup({ version: 2, calendars: { semester: { OLD: ['CS101'] }, quarter: { Q27: ['CS102'] } }, migration: {} });
  assert.equal(app.elements['export-schedule'].disabled, true);
  assert.equal(app.elements['recovery-notice'].hidden, false);
  await app.elements['clear-schedule'].click();
  const stored = JSON.parse(app.values.get('college-schedule-plan:test-u'));
  assert.deepEqual(stored.calendars.semester, {});
  assert.deepEqual(stored.recovery.semester.OLD, ['CS101']);
  assert.deepEqual(stored.calendars.quarter.Q27, ['CS102']);
  assert.equal(app.elements['clear-schedule'].disabled, true);
});

test('ordinary export includes only visible entries and recovery export retains original term code', async () => {
  const app = await setup({ version: 2, calendars: { semester: { S27: ['CS101'], OLD: ['CS102'] }, quarter: { Q27: ['CS102'] } }, migration: {} });
  await app.elements['export-schedule'].click();
  const csv = await app.exported();
  assert.match(csv, /"Calendar ID","Term Code","Term"/);
  assert.match(csv, /"semester","S27","Spring","CS101"/);
  assert.doesNotMatch(csv, /OLD/);
  assert.doesNotMatch(csv, /quarter|Q27/);
  await app.elements['export-recovery'].click();
  assert.match(await app.exported(), /"semester","OLD","Archive","CS102"/);
});

test('reconciliation reports expired, disabled, and deleted term entries without discarding them', async () => {
  const app = await setup({ version: 2, calendars: { semester: { PAST: ['CS101'], OFF: ['CS102'], DELETED: ['CS101'] } }, migration: {} });
  assert.equal(app.elements['export-schedule'].disabled, true);
  assert.match(app.elements['recovery-summary'].textContent, /1 expired, 1 disabled, 1 unknown/);
  const stored = JSON.parse(app.values.get('college-schedule-plan:test-u'));
  assert.deepEqual(stored.calendars.semester, {});
  assert.deepEqual(stored.recovery.semester.PAST, ['CS101']);
  assert.deepEqual(stored.recovery.semester.OFF, ['CS102']);
  assert.deepEqual(stored.recovery.semester.DELETED, ['CS101']);
});

test('only-hidden schedules can be recovery-exported with a deleted original term code', async () => {
  const app = await setup({ version: 3, calendars: { semester: {} }, migration: {}, recovery: { semester: { GONE: ['CS102'] } } });
  assert.equal(app.elements['export-schedule'].disabled, true);
  await app.elements['export-schedule'].click();
  assert.equal(await app.exported(), undefined);
  await app.elements['export-recovery'].click();
  assert.match(await app.exported(), /"semester","GONE","Unknown term","CS102"/);
});

test('recovery data is removed only by its explicit removal action', async () => {
  const app = await setup({ version: 3, calendars: { semester: { S27: ['CS101'] } }, migration: {}, recovery: { semester: { GONE: ['CS102'] } } });
  await app.elements['clear-schedule'].click();
  let stored = JSON.parse(app.values.get('college-schedule-plan:test-u'));
  assert.deepEqual(stored.recovery.semester.GONE, ['CS102']);
  await app.elements['remove-recovery'].click();
  stored = JSON.parse(app.values.get('college-schedule-plan:test-u'));
  assert.deepEqual(stored.recovery.semester, {});
  assert.equal(app.elements['recovery-notice'].hidden, true);
});

test('import honors calendar ID and term code rather than an overlapping term name', async () => {
  const app = await setup();
  app.elements['import-schedule'].files = [{ text: async () => 'Calendar ID,Term Code,Term,Course #\nquarter,Q27,Spring,CS101\nsemester,S27,Spring,CS102\n' }];
  await app.elements['import-schedule'].dispatch('change');
  const stored = JSON.parse(app.values.get('college-schedule-plan:test-u'));
  assert.deepEqual(stored.calendars.semester.S27, ['CS102']);
  assert.equal(stored.calendars.quarter, undefined);
  assert.match(app.elements['planner-message'].textContent, /Rejected row 2: wrong calendar/);
});

test('undated terms render publication and planning-placeholder labels', async () => {
  const app = await setup();
  const options = app.elements['planner-term'].options;
  assert.match(options.find(option => option.value === 'TBD').textContent, /Dates not yet published/);
  const undatedSection = app.elements['plan-grid'].children.find(section => section.children[0].textContent === 'Future term');
  assert.match(undatedSection.children[1].textContent, /Dates not yet published/);
  assert.match(undatedSection.children[1].textContent, /planning placeholder, not a confirmed schedule/);
  assert.match(app.elements['calendar-coverage'].textContent, /four-year horizon/);
});

test('course badges show unconfirmed availability while exact cancellation is prominent', async () => {
  const app = await setup();
  await addCourse(app, 'CS101', 'S27');
  await addCourse(app, 'CS102', 'S27');
  const spring = app.elements['plan-grid'].children.find(section => section.children[0].textContent === 'Spring');
  const badges = spring.children[2].children.map(item => item.children[0].children[2]);
  assert.equal(badges[0].textContent, 'Cancelled');
  assert.equal(badges[1].textContent, 'Unconfirmed · unusual term');
  assert.match(badges[1].title, /do not predict availability/);
  assert.match(app.elements['issue-list'].children[0].children[1].children[0].textContent, /Cancelled offering: CS101/);
});

test('mixed-validity imports apply valid additions after confirmation', async () => {
  const app = await setup();
  app.elements['import-schedule'].files = [{ size: 100, text: async () => 'Calendar ID,Term Code,Course #\nsemester,S27,CS101\nother,S27,CS102\n' }];
  await app.elements['import-schedule'].dispatch('change');
  const stored = JSON.parse(app.values.get('college-schedule-plan:test-u'));
  assert.deepEqual(stored.calendars.semester.S27, ['CS101']);
  assert.match(app.elements['planner-message'].textContent, /Rejected row 3: wrong calendar/);
});

test('oversized and unreadable imports leave the plan unchanged', async () => {
  const app = await setup();
  app.elements['import-schedule'].files = [{ size: 1024 * 1024 + 1, text: async () => '' }];
  await app.elements['import-schedule'].dispatch('change');
  assert.match(app.elements['planner-message'].textContent, /too large/);
  app.elements['import-schedule'].files = [{ size: 10, text: async () => { throw new Error('read'); } }];
  await app.elements['import-schedule'].dispatch('change');
  assert.match(app.elements['planner-message'].textContent, /could not be read/);
  assert.equal(JSON.parse(app.values.get('college-schedule-plan:test-u')).calendars.semester, undefined);
});

test('row-limit preflight rejects imports before core parsing and leaves the plan unchanged', async () => {
  const app = await setup();
  const rows = Array.from({ length: 10001 }, () => 'S27,CS101').join('\n');
  app.elements['import-schedule'].files = [{ size: rows.length, text: async () => `Term Code,Course #\n${rows}` }];
  await app.elements['import-schedule'].dispatch('change');
  assert.match(app.elements['planner-message'].textContent, /too many rows/);
  assert.equal(JSON.parse(app.values.get('college-schedule-plan:test-u')).calendars.semester, undefined);
});

test('denied reads show an accessible persistent warning and start empty', async () => {
  const app = await setup(null, { getItem() { const error = new Error('denied'); error.name = 'SecurityError'; throw error; }, setItem() { throw new Error('denied'); }, removeItem() {} });
  assert.equal(app.elements['storage-warning'].hidden, false);
  assert.match(app.elements['storage-warning'].textContent, /current planning session still works/);
  await addCourse(app, 'CS101', 'S27');
  assert.equal(app.elements['export-schedule'].disabled, false);
  app.elements['planner-calendar'].value = 'quarter';
  await app.elements['planner-calendar'].dispatch('change');
  app.elements['planner-calendar'].value = 'semester';
  await app.elements['planner-calendar'].dispatch('change');
  assert.equal(app.elements['export-schedule'].disabled, false);
});

test('malformed JSON and malformed versioned payloads are rejected', async () => {
  const malformedJson = new Map([['college-schedule-plan:test-u', '{nope']]);
  const first = await setup(null, { getItem: key => malformedJson.get(key) ?? null, setItem: (key, value) => malformedJson.set(key, value), removeItem() {} });
  assert.match(first.elements['storage-warning'].textContent, /malformed/);

  const malformedPayload = { version: 2, calendars: { semester: { S27: [17] } }, migration: {} };
  const second = await setup(malformedPayload);
  assert.equal(second.elements['export-schedule'].disabled, true);
  assert.match(second.elements['storage-warning'].textContent, /invalid format/);
});

test('quota failures preserve in-memory add, switch, import, remove, and clear behavior', async () => {
  const values = new Map();
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem() { const error = new Error('quota'); error.name = 'QuotaExceededError'; throw error; },
    removeItem() {},
  };
  const app = await setup(null, storage);
  await addCourse(app, 'CS101', 'S27');
  assert.equal(app.elements['export-schedule'].disabled, false);
  assert.equal(app.elements['storage-warning'].hidden, false);
  app.elements['planner-calendar'].value = 'quarter';
  await app.elements['planner-calendar'].dispatch('change');
  await addCourse(app, 'CS102', 'Q27');
  app.elements['planner-calendar'].value = 'semester';
  await app.elements['planner-calendar'].dispatch('change');
  let spring = app.elements['plan-grid'].children.find(section => section.children[0].textContent === 'Spring');
  await spring.children[2].children[0].children[1].click();
  assert.equal(app.elements['export-schedule'].disabled, true);
  app.elements['import-schedule'].files = [{ size: 100, text: async () => 'Term Code,Course #\nS27,CS101\n' }];
  await app.elements['import-schedule'].dispatch('change');
  assert.equal(app.elements['export-schedule'].disabled, false);
  await app.elements['clear-schedule'].click();
  assert.equal(app.elements['export-schedule'].disabled, true);
});

test('completed-course persistence is debounced and warns only once', async () => {
  let writes = 0;
  const storage = { getItem: () => null, setItem() { writes += 1; throw new Error('denied'); }, removeItem() {} };
  const app = await setup(null, storage);
  app.elements['completed-courses'].value = 'CS';
  await app.elements['completed-courses'].dispatch('input');
  app.elements['completed-courses'].value = 'CS101';
  await app.elements['completed-courses'].dispatch('input');
  assert.equal(writes, 1); // Initial empty-plan migration only.
  await new Promise(resolve => setTimeout(resolve, 350));
  assert.equal(writes, 2);
  assert.equal(app.elements['storage-warning'].hidden, false);
});

test('clearing completed courses uses guarded removal after the debounce', async () => {
  let removals = 0;
  const storage = { getItem: key => key.endsWith(':completed') ? 'CS101' : null, setItem() {}, removeItem() { removals += 1; throw new Error('denied'); } };
  const app = await setup(null, storage);
  app.elements['completed-courses'].value = '';
  await app.elements['completed-courses'].dispatch('input');
  assert.equal(removals, 0);
  await new Promise(resolve => setTimeout(resolve, 350));
  assert.equal(removals, 1);
  assert.match(app.elements['storage-warning'].textContent, /will not survive a reload/);
});

test('unknown completed-course tokens are displayed as issues', async () => {
  const app = await setup();
  app.elements['completed-courses'].value = 'CS999';
  await app.elements['completed-courses'].dispatch('input');
  assert.match(app.elements['issue-list'].children[0].children[1].children[0].textContent, /Unknown completed course: CS999/);
  assert.match(app.elements['issue-list'].children[0].children[1].children[1].textContent, /not a course in this catalog/);
});

test('a scheduled completed non-repeatable course is reported', async () => {
  const app = await setup();
  app.elements['completed-courses'].value = 'CS 101';
  await app.elements['completed-courses'].dispatch('input');
  await addCourse(app, 'CS101', 'S27');
  assert.match(app.elements['issue-list'].children[0].children[1].children[0].textContent, /Already completed: CS101/);
  assert.match(app.elements['issue-list'].children[0].children[1].children[1].textContent, /does not explicitly permit repeating/);
});

test('repeatable completed courses retain the catalog wording', async () => {
  const app = await setup();
  app.elements['completed-courses'].value = 'ART200';
  await app.elements['completed-courses'].dispatch('input');
  await addCourse(app, 'ART200', 'S27');
  const issue = app.elements['issue-list'].children[0];
  assert.match(issue.children[1].children[0].textContent, /Repeatable completed course: ART200/);
  assert.match(issue.children[1].children[1].textContent, /May be repeated for up to 9 credits/);
});

test('supported external prerequisites entered as completed satisfy requirements', async () => {
  const app = await setup();
  app.elements['completed-courses'].value = 'external 100';
  await app.elements['completed-courses'].dispatch('input');
  await addCourse(app, 'CS102', 'S27');
  const titles = app.elements['issue-list'].children.map(issue => issue.children[1]?.children[0]?.textContent || '');
  assert.ok(!titles.some(title => /missing prerequisite/i.test(title)));
});
