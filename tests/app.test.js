const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');
const PlannerCore = require('../assets/planner-core.js');

const appSource = fs.readFileSync('assets/app.js', 'utf8');

class Element {
  constructor(id = '', tagName = '') {
    this.id = id;
    this.tagName = tagName.toUpperCase();
    this.value = '';
    this.textContent = '';
    this.hidden = false;
    this.children = [];
    this.listeners = {};
    this.style = {};
    this.clientWidth = 800;
    this.replaceCount = 0;
  }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; this.replaceCount += 1; }
  setAttribute(name, value) { this[name] = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
}

class Option extends Element {
  constructor(text, value) { super(); this.textContent = text; this.value = value; }
}

function catalog() {
  return {
    university: { short_name: 'Test U', catalog_date: '2026-09-01' },
    departments: [{ code: 'CS', name: 'Computer Science' }],
    courses: [{ code: 'CS101', department: 'CS', level: 'undergraduate', title: 'Introduction', credits: 3, tags: [] }],
    edges: [],
  };
}

async function initialize(resizeObserverMode, catalogData = catalog()) {
  const ids = ['department', 'level', 'tag', 'query', 'course-list', 'result-count', 'graph',
    'explorer-status', 'summary-selected', 'summary-prerequisites', 'summary-corequisites',
    'summary-dependents', 'details', 'map-title', 'site-footer', 'load-status', 'explorer', 'app'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
  elements.department.value = 'CS';
  elements.level.value = 'all';
  elements.tag.value = 'all';
  const graphNodes = new Element();
  const edgeLayer = new Element();
  elements.graph.querySelector = selector => selector === '.graph-nodes' ? graphNodes : edgeLayer;

  const windowListeners = {};
  let observed;
  class ResizeObserverDouble {
    constructor(callback) {
      if (resizeObserverMode === 'throwing') throw new Error('ResizeObserver construction failed');
      this.callback = callback;
    }
    observe(element) { observed = element; }
  }
  const window = {
    COLLEGE_PLANNER: { loadCatalog: async () => ({ catalog: catalogData }) },
    addEventListener: (name, callback) => { windowListeners[name] = callback; },
    setTimeout,
    clearTimeout,
  };
  if (resizeObserverMode === true || resizeObserverMode === 'throwing') window.ResizeObserver = ResizeObserverDouble;
  const document = {
    title: '',
    getElementById: id => elements[id],
    createElement: tagName => new Element('', tagName),
    createElementNS: () => new Element(),
  };
  vm.runInNewContext(appSource, { window, document, Option, Node: Element, PlannerCore, Map, Set });
  await new Promise(resolve => setImmediate(resolve));
  return { elements, graphNodes, observed, windowListeners };
}

function requirementCatalog(edges) {
  return {
    university: { short_name: 'Test U', catalog_date: '2026-09-01' },
    departments: [{ code: 'CS', name: 'Computer Science' }],
    courses: [
      { code: 'CS300', department: 'CS', level: 'undergraduate', title: 'Target course', credits: 3, tags: [] },
      { code: 'CS100', department: 'CS', level: 'undergraduate', title: 'Catalog course', credits: 3, tags: [] },
    ],
    edges,
  };
}

async function renderRequirements(edges) {
  const app = await initialize(true, requirementCatalog(edges));
  // CS300 has the most relationships, so the initial explorer selection is deterministic.
  const externalNodes = app.graphNodes.children.filter(node => node.className === 'graph-node external');
  return { ...app, externalNodes };
}

function offeringDetails(app) {
  const definitionList = app.elements.details.children[3];
  const offeringLabelIndex = definitionList.children.findIndex(child => child.textContent === 'Offerings');
  return definitionList.children[offeringLabelIndex + 1].children[0];
}

test('browser smoke: offering history identifies held, scheduled, and cancelled term records', async () => {
  const data = catalog();
  data.courses[0].offering_history = [
    { term_name: 'Fall 2025', term_status: 'historical', offering_status: 'held', source_url: 'https://example.edu/fall-2025' },
    { term_name: 'Fall 2026', term_status: 'current', offering_status: 'scheduled', source_url: 'https://example.edu/fall-2026' },
    { term_name: 'Spring 2027', term_status: 'future', offering_status: 'cancelled', source_url: 'https://example.edu/spring-2027' },
  ];
  const history = offeringDetails(await initialize(true, data));

  assert.equal(history.tagName, 'UL');
  assert.equal(history.children.length, 3);
  const expected = [
    ['offering-record offering-held', 'Fall 2025', 'held', 'historical'],
    ['offering-record offering-scheduled', 'Fall 2026', 'scheduled', 'current'],
    ['offering-record offering-cancelled', 'Spring 2027', 'cancelled', 'future'],
  ];
  history.children.forEach((record, index) => {
    assert.equal(record.tagName, 'LI');
    assert.equal(record.className, expected[index][0]);
    assert.equal(record.children[0].tagName, 'A');
    assert.equal(record.children[0].textContent, expected[index][1]);
    assert.equal(record.children[1].textContent, expected[index][2]);
    assert.equal(record.children[2].textContent, expected[index][3]);
  });
  assert.equal(history.children[2].children[0].href, 'https://example.edu/spring-2027');
});

test('browser smoke: offering history supports missing sources and no-history state', async () => {
  const missingSource = catalog();
  missingSource.courses[0].offering_history = [
    { term_name: 'Summer 2026', term_status: 'current', offering_status: 'scheduled' },
  ];
  const history = offeringDetails(await initialize(true, missingSource));
  assert.equal(history.children[0].children[0].tagName, 'SPAN');
  assert.equal(history.children[0].children[0].textContent, 'Summer 2026');

  const empty = offeringDetails(await initialize(true));
  assert.equal(empty.tagName, 'P');
  assert.equal(empty.className, 'offering-history-empty');
  assert.equal(empty.textContent, 'No offering history recorded');
});

test('browser smoke: external prerequisite is visible but not selectable', async () => {
  const app = await renderRequirements([
    { source: 'PLACEMENT', target: 'CS300', kind: 'prerequisite', source_in_database: false },
  ]);
  assert.equal(app.externalNodes.length, 1);
  assert.equal(app.externalNodes[0].tagName, 'DIV');
  assert.equal(app.externalNodes[0].listeners.click, undefined);
  assert.equal(app.externalNodes[0].children[1].textContent, 'External or uncataloged requirement');
  assert.match(app.elements['summary-prerequisites'].children[0].textContent, /AND — all of: PLACEMENT — External or uncataloged requirement/);
});

test('browser smoke: external corequisite appears in graph and semantic summary', async () => {
  const app = await renderRequirements([
    { source: 'LAB-CONSENT', target: 'CS300', kind: 'corequisite', source_in_database: false },
  ]);
  assert.equal(app.externalNodes.length, 1);
  assert.match(app.elements['summary-corequisites'].children[0].textContent,
    /AND — complete earlier or register concurrently; all of: LAB-CONSENT — External or uncataloged requirement/);
  assert.match(app.externalNodes[0]['aria-label'], /may be completed earlier or taken concurrently with selected course/);

  const details = app.elements.details.children[3];
  const officialWording = details.children.findIndex(child => child.textContent === 'Completion or concurrent registration (official wording)');
  const structured = details.children.findIndex(child => child.textContent === 'Structured completion/concurrent groups');
  assert.notEqual(officialWording, -1);
  assert.equal(details.children[officialWording + 1].textContent, 'None listed');
  assert.notEqual(structured, -1);
  assert.match(details.children[structured + 1].textContent, /Complete earlier or register concurrently: all of LAB-CONSENT/);
});

test('browser smoke: grouped external alternatives retain OR semantics', async () => {
  const app = await renderRequirements([
    { source: 'MATH-PLACEMENT', target: 'CS300', kind: 'prerequisite', source_in_database: false, logic_group: 'entry', logic_operator: 'OR' },
    { source: 'INSTRUCTOR-CONSENT', target: 'CS300', kind: 'prerequisite', source_in_database: false, logic_group: 'entry', logic_operator: 'OR' },
  ]);
  assert.equal(app.externalNodes.length, 2);
  assert.match(app.elements['summary-prerequisites'].children[0].textContent,
    /OR — one of: MATH-PLACEMENT .* or INSTRUCTOR-CONSENT/);
});

test('browser smoke: mixed internal and external groups retain AND semantics', async () => {
  const app = await renderRequirements([
    { source: 'CS100', target: 'CS300', kind: 'prerequisite', source_in_database: true, logic_group: 'foundation', logic_operator: 'AND' },
    { source: 'PORTFOLIO', target: 'CS300', kind: 'prerequisite', source_in_database: false, logic_group: 'foundation', logic_operator: 'AND' },
  ]);
  assert.equal(app.externalNodes.length, 1);
  assert.match(app.elements['summary-prerequisites'].children[0].textContent,
    /AND — all of: CS100 — Catalog course and PORTFOLIO — External or uncataloged requirement/);
  const internal = app.graphNodes.children.find(node => node.children[0]?.textContent === 'CS100');
  assert.equal(internal.tagName, 'BUTTON');
  assert.equal(typeof internal.listeners.click, 'function');
});

for (const scenario of [
  { name: 'with ResizeObserver', mode: true, usesObserver: true },
  { name: 'without ResizeObserver', mode: false, usesObserver: false },
  { name: 'when ResizeObserver construction throws', mode: 'throwing', usesObserver: false },
]) {
  test(`explorer initializes ${scenario.name}`, async () => {
    const app = await initialize(scenario.mode);
    assert.equal(app.elements['course-list'].children.length, 1, 'course list rendered');
    assert.equal(app.elements['course-list'].children[0].children[0].textContent, 'CS101');
    assert.ok(app.graphNodes.replaceCount > 0, 'initial graph rendered');
    assert.ok(app.graphNodes.children.length > 0, 'graph contains a course node');
    assert.equal(app.elements.details.children[0].textContent, 'CS101 · Introduction', 'details rendered');
    assert.equal(app.elements['load-status'].hidden, true);
    assert.equal(app.elements.explorer.hidden, false);
    assert.equal(app.elements.app['aria-busy'], 'false');
    if (scenario.usesObserver) {
      assert.equal(app.observed, app.elements.graph);
      assert.equal(app.windowListeners.resize, undefined);
    } else {
      assert.equal(typeof app.windowListeners.resize, 'function');
      const renders = app.graphNodes.replaceCount;
      app.windowListeners.resize();
      app.windowListeners.resize();
      await new Promise(resolve => setTimeout(resolve, 175));
      assert.equal(app.graphNodes.replaceCount, renders + 1, 'resize rendering is debounced');
    }
  });
}
