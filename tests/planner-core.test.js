const test = require('node:test');
const assert = require('node:assert/strict');
const core = require('../assets/planner-core.js');
const courses = [{code:'CS101',title:'Intro, "CS"',credits:'3',offering_history:[]},{code:'CS201',title:'Algorithms',credits:'4',offering_history:[{term_code:'F1',term_type:'fall',term_status:'future',offering_status:'scheduled'}]}];
const terms = [{code:'F1',name:'Fall 2026',academic_year:'2026-2027',sequence:1,start_date:'2026-09-01',end_date:'2026-12-01',planning_enabled:true,term_type:'fall'},{code:'FAR',name:'Far',academic_year:'2031-2032',sequence:1,start_date:'2031-01-01',end_date:'2031-02-01',planning_enabled:true}];
test('planning horizon uses four academic periods and sorts dated and undated terms',()=>{
  const mixed = [
    {code:'A2',academic_year:'2026-2027',sequence:2,start_date:null,end_date:null,planning_enabled:true},
    {code:'A1',academic_year:'2026-2027',sequence:1,start_date:null,end_date:null,planning_enabled:true},
    {code:'B2',academic_year:'2027-2028',sequence:2,start_date:'2028-01-01',end_date:'2028-05-01',planning_enabled:true},
    {code:'B1',academic_year:'2027-2028',sequence:1,start_date:'2027-09-01',end_date:'2027-12-01',planning_enabled:true},
    {code:'C',academic_year:'2028-2029',sequence:1,start_date:null,end_date:null,planning_enabled:true},
    {code:'D',academic_year:'2029-2030',sequence:1,start_date:null,end_date:null,planning_enabled:true},
    {code:'OUT',academic_year:'2030-2031',sequence:1,start_date:null,end_date:null,planning_enabled:true},
    {code:'PAST',academic_year:'2025-2026',sequence:1,start_date:'2025-01-01',end_date:'2025-02-01',planning_enabled:true},
  ];
  assert.deepEqual(core.planningTerms([{id:'c',terms:mixed}], 'c', new Date('2026-01-01')).map(t=>t.code),['A1','A2','B1','B2','C','D']);
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
});
test('imports reject header-only files and prefer stable identifiers',()=>{
  assert.match(core.importRows('Term Code,Course #\n',terms,courses,'cal').error,/only headers/);
  assert.deepEqual(core.importRows('Term Code,Term,Course #,Course Name\nF1,Wrong,CS101,Wrong',terms,courses,'cal').additions,[{termCode:'F1',courseCode:'CS101'}]);
});
