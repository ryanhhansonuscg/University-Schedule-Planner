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
      { code: 'CS101', title: 'Intro', credits: 3 },
      { code: 'CS102', title: 'Next', credits: 4 },
    ],
    edges: [],
    academic_calendars: [
      { id: 'semester', name: 'Semester', system_type: 'semester', is_primary: true, terms: [
        { code: 'S27', name: 'Spring', academic_year: '2026-2027', sequence: 1, term_type: 'spring', planning_enabled: true, start_date: '2027-01-01', end_date: '2027-05-01' },
        { code: 'TBD', name: 'Future term', academic_year: '2027-2028', sequence: 1, term_type: 'fall', planning_enabled: true, start_date: null, end_date: null },
        { code: 'OLD', name: 'Archive', academic_year: '2019-2020', sequence: 1, term_type: 'fall', planning_enabled: false, start_date: '2020-01-01', end_date: '2020-05-01' },
      ] },
      { id: 'quarter', name: 'Quarter', system_type: 'quarter', terms: [
        { code: 'Q27', name: 'Spring', academic_year: '2026-2027', sequence: 1, term_type: 'spring', planning_enabled: true, start_date: '2027-01-02', end_date: '2027-03-01' },
      ] },
    ],
  };
}

async function setup(saved = null) {
  const ids = ['planner-calendar', 'planner-course-search', 'course-options', 'planner-term', 'completed-courses', 'plan-grid', 'issue-list', 'issue-count', 'calendar-coverage', 'planner-message', 'export-schedule', 'clear-schedule', 'import-schedule', 'add-to-plan', 'load-status', 'planner', 'app'];
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
    localStorage: { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) },
    Option: class extends Element { constructor(text, value) { super(); this.text = text; this.textContent = text; this.value = value; } },
    Blob, Date, Set, Map,
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
  assert.equal(stored.version, 2);
  assert.deepEqual(stored.calendars.semester.S27, ['CS101']);
  assert.deepEqual(stored.calendars.quarter.Q27, ['CS102']);
  assert.deepEqual(stored.migration.unmatched.MISSING, ['CS101']);
  assert.match(app.elements['planner-message'].textContent, /recovery bucket/);
});

test('clear removes only the active calendar, including hidden entries', async () => {
  const app = await setup({ version: 2, calendars: { semester: { OLD: ['CS101'] }, quarter: { Q27: ['CS102'] } }, migration: {} });
  assert.equal(app.elements['export-schedule'].disabled, false);
  await app.elements['clear-schedule'].click();
  const stored = JSON.parse(app.values.get('college-schedule-plan:test-u'));
  assert.deepEqual(stored.calendars.semester, {});
  assert.deepEqual(stored.calendars.quarter.Q27, ['CS102']);
  assert.equal(app.elements['clear-schedule'].disabled, true);
});

test('export includes active calendar ID and term code, including hidden terms', async () => {
  const app = await setup({ version: 2, calendars: { semester: { S27: ['CS101'], OLD: ['CS102'] }, quarter: { Q27: ['CS102'] } }, migration: {} });
  await app.elements['export-schedule'].click();
  const csv = await app.exported();
  assert.match(csv, /"Calendar ID","Term Code","Term"/);
  assert.match(csv, /"semester","S27","Spring","CS101"/);
  assert.match(csv, /"semester","OLD","Archive","CS102"/);
  assert.doesNotMatch(csv, /quarter|Q27/);
});

test('import honors calendar ID and term code rather than an overlapping term name', async () => {
  const app = await setup();
  app.elements['import-schedule'].files = [{ text: async () => 'Calendar ID,Term Code,Term,Course #\nquarter,Q27,Spring,CS101\nsemester,S27,Spring,CS102\n' }];
  await app.elements['import-schedule'].dispatch('change');
  const stored = JSON.parse(app.values.get('college-schedule-plan:test-u'));
  assert.deepEqual(stored.calendars.semester.S27, ['CS102']);
  assert.equal(stored.calendars.quarter, undefined);
  assert.match(app.elements['planner-message'].textContent, /Skipped row 2/);
});

test('undated terms render publication and planning-placeholder labels', async () => {
  const app = await setup();
  const options = app.elements['planner-term'].options;
  assert.match(options.find(option => option.value === 'TBD').textContent, /Dates not yet published/);
  const undatedSection = app.elements['plan-grid'].children.find(section => section.children[0].textContent === 'Future term');
  assert.match(undatedSection.children[1].textContent, /Dates not yet published/);
  assert.match(undatedSection.children[1].textContent, /planning placeholder, not a confirmed schedule/);
  assert.match(app.elements['calendar-coverage'].textContent, /four-academic-period horizon/);
});
