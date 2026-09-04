const assert = require('node:assert/strict');
const test = require('node:test');
const EditorCore = require('../assets/editor-core.js');

function document() {
  return {
    schema_version: 3,
    department: { code: 'CS', name: 'Computer Science' },
    courses: [
      { code: 'CS101', department: 'CS', number: '101', level: 'undergraduate', title: 'Introduction', credits: '3', tags: [] },
      { code: 'CS201', department: 'CS', number: '201', level: 'undergraduate', title: 'Topics', credits: '3', tags: [] },
    ],
    edges: [{ source: 'CS101', target: 'CS201', kind: 'prerequisite', source_in_database: true }],
  };
}

test('normalizes scraped department data without mutating the source', () => {
  const source = document(); delete source.courses[0].tags;
  const normalized = EditorCore.normalize(source);
  assert.deepEqual(normalized.courses[0].tags, []);
  assert.equal(source.courses[0].tags, undefined);
});

test('validates course fields and structured requirement semantics', () => {
  assert.deepEqual(EditorCore.validate(document()), []);
  const invalid = document();
  invalid.courses[0].credits = 'three credits';
  invalid.edges[0] = { source: '', target: 'MISSING', kind: 'concurrent', source_in_database: 'yes', logic_group: 'choice' };
  const errors = EditorCore.validate(invalid).join(' ');
  assert.match(errors, /invalid credits/);
  assert.match(errors, /unknown course/);
  assert.match(errors, /invalid relationship type/);
  assert.match(errors, /needs a source/);
  assert.match(errors, /must state whether/);
  assert.match(errors, /incomplete logic group/);
});

test('replaces only the selected course requirements and preserves timing kinds', () => {
  const data = document();
  data.edges.push({ source: 'MATH100', target: 'CS101', kind: 'corequisite', source_in_database: false });
  EditorCore.replaceEdges(data, 'CS201', [
    { source: 'CS101', kind: 'corequisite', source_in_database: true, logic_group: 'pair', logic_operator: 'AND' },
  ]);
  assert.deepEqual(EditorCore.edgesFor(data, 'CS201'), [
    { source: 'CS101', target: 'CS201', kind: 'corequisite', source_in_database: true, logic_group: 'pair', logic_operator: 'AND' },
  ]);
  assert.equal(EditorCore.edgesFor(data, 'CS101')[0].source, 'MATH100');
});
