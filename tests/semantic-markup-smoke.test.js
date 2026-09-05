const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const core = require('../assets/planner-core.js');

test('index exposes keyboard-native navigation and accessible loading state', () => {
  const html = fs.readFileSync('index.html','utf8');
  assert.match(html, /<nav[^>]+aria-label=/); assert.match(html, /<a[^>]+href="planner.html"/); assert.match(html, /aria-busy="true"/);
});
test('planner exposes calendar switching and keyboard add controls', () => {
  const html=fs.readFileSync('planner.html','utf8'); const js=fs.readFileSync('assets/planner.js','utf8');
  assert.match(html,/id="planner-calendar"/); assert.match(js,/plannerCalendar\.addEventListener\('change'/); assert.match(js,/event\.key === 'Enter'/);
});
test('schedule persistence and CSV round-trip preserve browser data', () => {
  const plan={FALL:['CS101']}; const courses=[{code:'CS101',title:'Intro',credits:'3'}]; const terms=[{code:'FALL',name:'Fall'}];
  assert.deepEqual(core.deserializePlan(core.serializePlan(plan)),plan);
  assert.deepEqual(core.parseCsv(core.scheduleCsv(terms,plan,courses)).rows[1],['Fall','CS101','Intro','3']);
});
test('catalog loader reports fetch failures rather than leaving busy UI', () => {
  const js=fs.readFileSync('assets/loader.js','utf8'); assert.match(js,/catch/); assert.match(js,/load-status/); assert.match(js,/aria-busy/);
});

test('course graph has a persistent semantic relationship summary and dedicated status', () => {
  const html = fs.readFileSync('index.html', 'utf8');
  const js = fs.readFileSync('assets/app.js', 'utf8');
  assert.doesNotMatch(html, /id="graph"[^>]*aria-live/);
  for (const id of ['relationship-summary', 'summary-selected', 'summary-prerequisites', 'summary-corequisites', 'summary-dependents']) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(html, /id="explorer-status"[^>]+role="status"/);
  assert.match(js, /renderRelationshipSummary\(\)/);
  assert.match(js, /PlannerCore\.requirementGroups\(edges, selectedCode, kind\)/);
  assert.match(html, /class="external"[^>]*aria-hidden="true"[^>]*>\s*<\/i> external requirement/);
  assert.match(html, /completion or concurrent registration/);
  assert.match(js, /setAttribute\('aria-label',[\s\S]*relationshipToSelected/);
});

test('planner controls reference guidance and import errors are focusable', () => {
  const html = fs.readFileSync('planner.html', 'utf8');
  const js = fs.readFileSync('assets/planner.js', 'utf8');
  for (const id of ['calendar-coverage', 'prerequisite-advisory', 'import-requirements', 'persistence-warning']) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(html, /id="import-schedule"[^>]+aria-describedby="[^"]*planner-message/);
  assert.match(html, /id="planner-message"[^>]+tabindex="-1"/);
  assert.match(html, /id="storage-warning"[^>]+role="alert"[^>]+aria-live="assertive"/);
  assert.match(js, /plannerMessage\.focus\?\.\(\)/);
});
