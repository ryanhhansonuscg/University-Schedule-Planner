const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');
const PlannerCore = require('../assets/planner-core.js');

const appSource = fs.readFileSync('assets/app.js', 'utf8');

class Element {
  constructor(id = '') {
    this.id = id;
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

async function initialize(withResizeObserver) {
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
    constructor(callback) { this.callback = callback; }
    observe(element) { observed = element; }
  }
  const window = {
    COLLEGE_PLANNER: { loadCatalog: async () => ({ catalog: catalog() }) },
    addEventListener: (name, callback) => { windowListeners[name] = callback; },
    setTimeout,
    clearTimeout,
  };
  if (withResizeObserver) window.ResizeObserver = ResizeObserverDouble;
  const document = {
    title: '',
    getElementById: id => elements[id],
    createElement: () => new Element(),
    createElementNS: () => new Element(),
  };
  vm.runInNewContext(appSource, { window, document, Option, Node: Element, PlannerCore, Map, Set });
  await new Promise(resolve => setImmediate(resolve));
  return { elements, graphNodes, observed, windowListeners };
}

for (const withResizeObserver of [true, false]) {
  test(`explorer initializes ${withResizeObserver ? 'with' : 'without'} ResizeObserver`, async () => {
    const app = await initialize(withResizeObserver);
    assert.equal(app.elements['load-status'].hidden, true);
    assert.equal(app.elements.explorer.hidden, false);
    assert.equal(app.elements.app['aria-busy'], 'false');
    assert.ok(app.graphNodes.replaceCount > 0, 'initial graph rendered');
    if (withResizeObserver) {
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
