const test = require('node:test');
const assert = require('node:assert/strict');
const core = require('../assets/planner-core.js');

test('storage adapter contains denied, quota, and removal failures', () => {
  const denied = new Error('blocked'); denied.name = 'SecurityError';
  const quota = new Error('full'); quota.name = 'QuotaExceededError';
  const adapter = core.createStorageAdapter({
    getItem() { throw denied; }, setItem() { throw quota; }, removeItem() { throw denied; },
  });
  assert.deepEqual(adapter.read('plan'), { ok: false, value: null, error: { operation: 'read', name: 'SecurityError', message: 'blocked' } });
  assert.equal(adapter.write('plan', '{}').error.name, 'QuotaExceededError');
  assert.equal(adapter.remove('plan').error.operation, 'remove');
});

test('storage adapter guards access to the storage object itself', () => {
  const adapter = core.createStorageAdapter(() => { throw new DOMException('denied', 'SecurityError'); });
  assert.equal(adapter.read('plan').error.operation, 'read');
  assert.equal(adapter.write('plan', '{}').error.operation, 'write');
  assert.equal(adapter.remove('plan').error.operation, 'remove');
});

test('versioned storage validator checks nested maps and migration data', () => {
  const valid = { version: 2, calendars: { semester: { F27: ['CS101'] } }, migration: { unmatched: { OLD: ['MATH9'] } } };
  assert.equal(core.validateStoredPlans(valid, 2), true);
  assert.equal(core.validateStoredPlans({ ...valid, calendars: [] }, 2), false);
  assert.equal(core.validateStoredPlans({ ...valid, calendars: { semester: { F27: 'CS101' } } }, 2), false);
  assert.equal(core.validateStoredPlans({ ...valid, calendars: { semester: { '': ['CS101'] } } }, 2), false);
  assert.equal(core.validateStoredPlans({ ...valid, calendars: { semester: { F27: [42] } } }, 2), false);
  assert.equal(core.validateStoredPlans({ ...valid, migration: { unmatched: [] } }, 2), false);
});
const courses = [{code:'CS101',title:'Intro, "CS"',credits:'3',offering_history:[]},{code:'CS201',title:'Algorithms',credits:'4',offering_history:[{term_code:'F1',term_type:'fall',term_status:'future',offering_status:'scheduled'}]}];
const terms = [{code:'F1',name:'Fall 2026',academic_year:'2026-2027',sequence:1,start_date:'2026-09-01',end_date:'2026-12-01',planning_enabled:true,term_type:'fall'},{code:'FAR',name:'Far',academic_year:'2031-2032',sequence:1,start_date:'2031-01-01',end_date:'2031-02-01',planning_enabled:true}];
test('planning horizon extends four years from a middle term and sorts dated and undated terms',()=>{
  const mixed = [
    {code:'A2',academic_year:'2026-2027',sequence:2,start_date:'2026-01-01',end_date:'2026-05-31',planning_enabled:true},
    {code:'A1',academic_year:'2026-2027',sequence:1,start_date:'2025-09-01',end_date:'2025-12-31',planning_enabled:true},
    {code:'B2',academic_year:'2027-2028',sequence:2,start_date:'2028-01-01',end_date:'2028-05-01',planning_enabled:true},
    {code:'B1',academic_year:'2027-2028',sequence:1,start_date:'2027-09-01',end_date:'2027-12-01',planning_enabled:true},
    {code:'C',academic_year:'2028-2029',sequence:1,start_date:null,end_date:null,planning_enabled:true},
    {code:'D',academic_year:'2029-2030',sequence:1,start_date:null,end_date:null,planning_enabled:true},
    {code:'END1',academic_year:'2030-2031',sequence:1,start_date:null,end_date:null,planning_enabled:true},
    {code:'END2',academic_year:'2030-2031',sequence:2,start_date:null,end_date:null,planning_enabled:true},
    {code:'OUT',academic_year:'2030-2031',sequence:3,start_date:null,end_date:null,planning_enabled:true},
    {code:'PAST',academic_year:'2025-2026',sequence:1,start_date:'2025-01-01',end_date:'2025-02-01',planning_enabled:true},
  ];
  const result=core.planningTerms([{id:'c',terms:mixed}], 'c', new Date('2026-02-01'));
  assert.deepEqual(result.terms.map(t=>t.code),['A2','B1','B2','C','D','END1','END2']);
  assert.equal(result.horizon.endpointCovered,true);
  assert.equal(result.horizon.dependsOnUnpublishedDates,true);
});

function academicTerms(currentSequence, includeEndpoint=true) {
  const terms=[];
  for (let year=2025;year<=2029;year+=1) for (let sequence=1;sequence<=3;sequence+=1) {
    if (year===2029 && sequence===currentSequence && !includeEndpoint) continue;
    terms.push({code:`${year}-${sequence}`,academic_year:`${year}-${year+1}`,sequence,start_date:null,end_date:null,planning_enabled:true});
  }
  const dates=[['2025-09-01','2025-12-31'],['2026-01-01','2026-05-31'],['2026-06-01','2026-08-31']][currentSequence-1];
  const current=terms.find(term=>term.code===`2025-${currentSequence}`);
  current.start_date=dates[0]; current.end_date=dates[1];
  return terms;
}

for (const [label,sequence,today] of [['beginning',1,'2025-09-01'],['middle',2,'2026-03-01'],['final',3,'2026-07-01']]) {
  test(`an academic year at its ${label} retains the equivalent endpoint period`,()=>{
    const result=core.planningTerms([{id:'c',terms:academicTerms(sequence)}],'c',new Date(today));
    assert.ok(result.terms.some(term=>term.code===`2029-${sequence}`));
    assert.ok(!result.terms.some(term=>term.code===`2029-${sequence+1}`));
    assert.equal(result.horizon.endpointCovered,true);
    assert.equal(result.horizon.dependsOnUnpublishedDates,true);
  });
}

test('dated terms include both exact four-year endpoint boundaries',()=>{
  const terms=[
    {code:'CURRENT',academic_year:'2025-2026',sequence:1,start_date:'2025-09-04',end_date:'2025-12-01',planning_enabled:true},
    {code:'ENDS',academic_year:'2029-2030',sequence:1,start_date:'2029-08-01',end_date:'2029-09-04',planning_enabled:true},
    {code:'STARTS',academic_year:'2029-2030',sequence:2,start_date:'2029-09-04',end_date:'2029-12-01',planning_enabled:true},
    {code:'AFTER',academic_year:'2029-2030',sequence:3,start_date:'2029-09-05',end_date:'2029-12-31',planning_enabled:true},
  ];
  const result=core.planningTerms([{id:'c',terms}],'c',new Date('2025-09-04'));
  assert.deepEqual(result.terms.map(term=>term.code),['CURRENT','ENDS','STARTS']);
  assert.equal(result.horizon.endpointCovered,true);
  assert.equal(result.horizon.dependsOnUnpublishedDates,false);
});

test('insufficient future placeholders report that the endpoint is not covered',()=>{
  const result=core.planningTerms([{id:'c',terms:academicTerms(2,false)}],'c',new Date('2026-03-01'));
  assert.equal(result.horizon.endpointCovered,false);
  assert.equal(result.horizon.dependsOnUnpublishedDates,false);
});
test('an intentionally disabled future term is excluded from planning terms',()=>{
  const futureTerms = [
    {code:'ENABLED',academic_year:'2025-2026',sequence:1,start_date:'2026-01-01',end_date:'2026-05-31',status:'current',planning_enabled:true},
    {code:'DISABLED',academic_year:'2026-2027',sequence:2,start_date:null,end_date:null,status:'future',planning_enabled:false},
  ];
  const result=core.planningTerms([{id:'c',terms:futureTerms}],'c',new Date('2026-03-01'));
  assert.deepEqual(result.terms.map(term=>term.code),['ENABLED']);
});
test('OR prerequisite groups accept either course',()=>assert.deepEqual(core.prerequisiteMissing([{source:'A',target:'C',kind:'prerequisite',logic_group:'g',logic_operator:'OR'},{source:'B',target:'C',kind:'prerequisite',logic_group:'g',logic_operator:'OR'}],'C',new Set(['B'])),[]));
test('requirement evaluation handles single edges, AND groups, and accurate messages',()=>{
  const edges=[
    {source:'A',target:'T',kind:'prerequisite'},
    {source:'B',target:'T',kind:'prerequisite',logic_group:'both',logic_operator:'AND'},
    {source:'C',target:'T',kind:'prerequisite',logic_group:'both',logic_operator:'AND'},
  ];
  const missing=core.evaluateRequirements(edges,'T','prerequisite',new Set(['B']));
  assert.deepEqual(missing.map(group=>group.sources),[['A'],['C']]);
  assert.equal(core.describeRequirementGroups(missing),'complete A; and complete C');
});
test('OR alternatives and multiple independent groups are all evaluated',()=>{
  const edges=[
    {source:'A',target:'T',kind:'prerequisite',logic_group:'choice',logic_operator:'OR'},
    {source:'B',target:'T',kind:'prerequisite',logic_group:'choice',logic_operator:'OR'},
    {source:'C',target:'T',kind:'prerequisite'},
  ];
  const missing=core.evaluateRequirements(edges,'T','prerequisite',new Set(['C']));
  assert.equal(core.describeRequirementGroups(missing),'complete one of A or B');
  assert.deepEqual(core.evaluateRequirements(edges,'T','prerequisite',new Set(['A','C'])),[]);
});
test('corequisites accept earlier completion or same-term enrollment',()=>{
  const edges=[{source:'LAB',target:'SCI',kind:'corequisite'}];
  assert.equal(core.evaluateRequirements(edges,'SCI','corequisite',new Set(),new Set()).length,1);
  assert.deepEqual(core.evaluateRequirements(edges,'SCI','corequisite',new Set(['LAB']),new Set()),[]);
  assert.deepEqual(core.evaluateRequirements(edges,'SCI','corequisite',new Set(),new Set(['LAB'])),[]);
});
test('external and malformed requirements remain conservatively mandatory',()=>{
  const edges=[
    {source:'EXTERNAL100',target:'T',kind:'prerequisite',source_in_database:false},
    {source:'A',target:'T',kind:'prerequisite',logic_group:'bad',logic_operator:'XOR'},
    {source:'B',target:'T',kind:'prerequisite',logic_group:'bad',logic_operator:'OR'},
  ];
  assert.deepEqual(core.evaluateRequirements(edges,'T','prerequisite',new Set()).map(group=>group.sources),[['EXTERNAL100'],['A'],['B']]);
});
test('offering evaluation covers exact scheduled, held, cancelled, and absent records',()=>{
  const term={code:'F1',term_type:'fall'};
  const record=offering_status=>({term_code:'F1',term_type:'fall',term_status:'future',offering_status});
  assert.deepEqual(core.evaluateOffering({offering_history:[record('scheduled')]},term),{status:'confirmed',exactStatus:'scheduled',historicalContext:'none'});
  assert.deepEqual(core.evaluateOffering({offering_history:[record('held')]},term),{status:'confirmed',exactStatus:'held',historicalContext:'none'});
  assert.deepEqual(core.evaluateOffering({offering_history:[record('scheduled'),record('cancelled')]},term),{status:'cancelled',exactStatus:'cancelled',historicalContext:'none'});
  assert.deepEqual(core.evaluateOffering({offering_history:[]},term),{status:'lacking-data',exactStatus:null,historicalContext:'none'});
});
test('offering evaluation keeps historical patterns subordinate to exact-term absence',()=>{
  const held=term_type=>({term_code:`OLD-${term_type}`,term_type,term_status:'historical',offering_status:'held'});
  assert.deepEqual(core.evaluateOffering({offering_history:[held('fall')]},{code:'NEW',term_type:'fall'}),{status:'not-listed',exactStatus:null,historicalContext:'typical'});
  assert.deepEqual(core.evaluateOffering({offering_history:[held('spring')]},{code:'NEW',term_type:'fall'}),{status:'historically-unusual',exactStatus:null,historicalContext:'unusual'});
});
test('storage serialization tolerates corrupt data',()=>{assert.deepEqual(core.deserializePlan(core.serializePlan({F1:['CS101']})),{F1:['CS101']});assert.deepEqual(core.deserializePlan('{'),{})});
test('course resolution supports spaced codes, title, and rejects ambiguity',()=>{assert.equal(core.resolveCourse(courses,'cs 101').code,'CS101');assert.equal(core.resolveCourse(courses,'Algorithms').code,'CS201')});
test('CSV parsing, escaping, and import validation',()=>{const csv=core.scheduleCsv(terms,{F1:['CS101']},courses);assert.equal(core.parseCsv(csv).rows[1][2],'Intro, "CS"');assert.match(core.importRows('bad\nrow',terms,courses).error,/Term/);assert.deepEqual(core.importRows('Term,Course #\nFall 2026,CS101',terms,courses).records,[{termCode:'F1',courseCode:'CS101'}]);assert.equal(core.parseCsv('\"bad').errors[0].type,'unterminated-field') });
test('CSV parser handles BOM, line endings, quoted newlines, commas, and escaped quotes',()=>{
  const parsed=core.parseCsv('\uFEFFName,Note\r\n"Ada","line 1\r\nline 2, and ""quoted"""\r\n');
  assert.deepEqual(parsed.errors,[]);
  assert.deepEqual(parsed.rows,[['Name','Note'],['Ada','line 1\r\nline 2, and "quoted"']]);
  assert.deepEqual(core.parseCsv('A,B\n1,2\n').rows,[['A','B'],['1','2']]);
  assert.equal(core.csvRowCount('A,B\n"one\ntwo",3\n'),2);
});
test('CSV parser reports malformed quotes, headers, and widths with locations',()=>{
  const parsed=core.parseCsv('Term,,TERM\n"Fall"oops,CS101\nshort\n"open');
  assert.ok(parsed.errors.every(error=>Number.isInteger(error.row)&&Number.isInteger(error.column)));
  for (const type of ['empty-header','duplicate-header','unexpected-quote','inconsistent-width','unterminated-field']) assert.ok(parsed.errors.some(error=>error.type===type),type);
});
test('imports categorize ambiguous labels and all other row failures',()=>{
  const importTerms=[...terms,{code:'F2',name:'Fall 2026'}];
  const importCourses=[...courses,{code:'CS301',title:'Algorithms'}];
  const csv='Calendar ID,Term Code,Term,Course #,Course Name\nother,F1,,CS101,\ncal,BAD,,CS101,\ncal,,Fall 2026,CS101,\ncal,F1,,BAD,\ncal,F1,,,Algorithms\ncal,F1,,CS101,\ncal,F1,,,\n';
  const result=core.importRows(csv,importTerms,importCourses,'cal',{F1:['CS101']});
  assert.deepEqual(result.failures.map(f=>f.category),['wrong calendar','unknown term','ambiguous term name','unknown course','ambiguous course title','duplicate schedule entry','malformed row']);
  assert.ok(result.failures.every(f=>Number.isInteger(f.row)&&Number.isInteger(f.column)&&f.type));
  assert.equal(result.failures.at(-1).type,'missing-required-cell');
});
test('import locations retain physical rows after quoted newlines',()=>{
  const result=core.importRows('Term Code,Course Name\nF1,"Unknown\nCourse"\nF1,Algorithms',terms,courses,'cal');
  assert.equal(result.failures[0].row,2);
  assert.equal(result.additions[0].courseCode,'CS201');
  assert.equal(core.parseCsv('A,B\n"open').errors[0].column,1);
});
test('imports reject header-only files and prefer stable identifiers',()=>{
  assert.match(core.importRows('Term Code,Course #\n',terms,courses,'cal').error,/only headers/);
  assert.deepEqual(core.importRows('Term Code,Term,Course #,Course Name\nF1,Wrong,CS101,Wrong',terms,courses,'cal').additions,[{termCode:'F1',courseCode:'CS101'}]);
});
