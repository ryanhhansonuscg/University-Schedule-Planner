'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync('assets/loader.js', 'utf8');

function environment({ embedded, responses = [], href = 'https://example.test/index.html' } = {}) {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      id, classList: { add() {} }, style: { setProperty() {} },
      setAttribute() {}, replaceChildren(...children) { this.children = children; },
      addEventListener(type, callback) { this[type] = callback; },
    });
    return elements.get(id);
  }
  const fetchCalls = [];
  const context = {
    URL, URLSearchParams,
    Option: function Option(name, value) { return { name, value }; },
    document: { documentElement: element('root'), getElementById: element },
    fetch: async path => { fetchCalls.push(path); return responses.shift(); },
  };
  context.window = {
    location: { href, protocol: new URL(href).protocol, assign(value) { this.assigned = value; } },
  };
  if (embedded !== undefined) context.window.COLLEGE_PLANNER_EMBEDDED = embedded;
  vm.runInNewContext(source, context);
  return { ...context, elements, fetchCalls };
}

const selected = { slug: 'sample-u', name: 'Sample U', path: 'universities/sample-u/catalog.json' };
const manifest = { default_university: 'sample-u', universities: [selected] };
const catalog = { university: { slug: 'sample-u', name: 'Sample U', primary_color: '#123456' } };

test('loads embedded registry and catalog without fetch', async () => {
  const env = environment({ embedded: { manifest, catalogs: { 'sample-u': catalog } }, href: 'file:///tmp/app/index.html' });
  const result = await env.window.COLLEGE_PLANNER.loadCatalog();
  assert.equal(result.catalog.university.name, 'Sample U');
  assert.deepEqual(env.fetchCalls, []);
  assert.equal(env.elements.get('planner-link').href, 'planner.html?university=sample-u');
});

test('retains hosted registry and catalog fetch loading', async () => {
  const response = value => ({ ok: true, json: async () => value });
  const env = environment({ responses: [response(manifest), response(catalog)] });
  const result = await env.window.COLLEGE_PLANNER.loadCatalog();
  assert.equal(result.catalog, catalog);
  assert.deepEqual(env.fetchCalls, ['universities/index.json', selected.path]);
});

test('reports missing embedded catalog without falling back to fetch', async () => {
  const env = environment({ embedded: { manifest, catalogs: {} }, href: 'file:///tmp/app/planner.html' });
  await assert.rejects(env.window.COLLEGE_PLANNER.loadCatalog(), /missing embedded catalog data/);
  assert.match(env.elements.get('load-status').textContent, /does not contain usable embedded data/);
  assert.deepEqual(env.fetchCalls, []);
});

test('file navigation is relative and preserves the selected university', () => {
  const env = environment({ href: 'file:///tmp/folder/index.html?university=old' });
  assert.equal(env.window.COLLEGE_PLANNER.urlFor('planner.html', 'sample-u'), 'planner.html?university=sample-u');
});
