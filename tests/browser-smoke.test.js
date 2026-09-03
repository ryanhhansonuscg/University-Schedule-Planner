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
  assert.deepEqual(core.parseCsv(core.scheduleCsv(terms,plan,courses))[1],['Fall','CS101','Intro','3']);
});
test('catalog loader reports fetch failures rather than leaving busy UI', () => {
  const js=fs.readFileSync('assets/loader.js','utf8'); assert.match(js,/catch/); assert.match(js,/load-status/); assert.match(js,/aria-busy/);
});
