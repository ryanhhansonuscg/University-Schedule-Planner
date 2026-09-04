(() => {
  const file = document.getElementById('editor-file');
  const workspace = document.getElementById('editor-workspace');
  const status = document.getElementById('editor-status');
  const list = document.getElementById('editor-course-list');
  const query = document.getElementById('editor-query');
  const form = document.getElementById('course-form');
  const edgeList = document.getElementById('edge-list');
  const validation = document.getElementById('validation-summary');
  const dirtyIndicator = document.getElementById('dirty-indicator');
  let data; let selectedCode = ''; let dirty = false; let filename = 'corrected-department.json';

  const example = {
    schema_version: 3,
    department: { code: 'SAMPLE', name: 'Sample Studies', school: '', source_url: 'https://catalog.example.edu/sample' },
    courses: [
      { code: 'SAMPLE101', department: 'SAMPLE', number: '101', level: 'undergraduate', title: 'Foundations', credits: '3', description: '', prerequisites: '', corequisites: '', restrictions: '', repeatable: 'No', source_url: 'https://catalog.example.edu/sample101', source_catalog: 'Scraped catalog', tags: ['foundation'], offering_history: [] },
      { code: 'SAMPLE201', department: 'SAMPLE', number: '201', level: 'undergraduate', title: 'Applied Seminar', credits: '3', description: '', prerequisites: 'SAMPLE101', corequisites: '', restrictions: '', repeatable: 'No', source_url: 'https://catalog.example.edu/sample201', source_catalog: 'Scraped catalog', tags: [], offering_history: [] },
    ],
    edges: [{ source: 'SAMPLE101', target: 'SAMPLE201', kind: 'prerequisite', source_in_database: true, logic_group: 'foundation', logic_operator: 'AND' }],
  };

  function setDirty(value) { dirty = value; dirtyIndicator.textContent = dirty ? 'Unapplied edits' : 'All edits applied'; }
  function showValidation() {
    const errors = EditorCore.validate(data);
    validation.className = `validation-summary ${errors.length ? 'has-errors' : 'is-valid'}`;
    validation.textContent = errors.length ? `${errors.length} issue${errors.length === 1 ? '' : 's'}: ${errors.join(' ')}` : 'No structural issues found. Ready to download.';
    return !errors.length;
  }
  function renderList() {
    const needle = query.value.trim().toLowerCase();
    const courses = data.courses.filter(course => `${course.code} ${course.title}`.toLowerCase().includes(needle));
    document.getElementById('editor-count').textContent = `${courses.length} course${courses.length === 1 ? '' : 's'}`;
    list.replaceChildren(...courses.map(course => {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'course-button';
      button.setAttribute('aria-pressed', String(course.code === selectedCode));
      const code = document.createElement('strong'); code.textContent = course.code;
      const title = document.createElement('span'); title.textContent = course.title;
      button.append(code, title); button.addEventListener('click', () => select(course.code)); return button;
    }));
  }
  function edgeRow(edge = { source: '', kind: 'prerequisite', source_in_database: true, logic_group: '', logic_operator: 'AND' }) {
    const row = document.createElement('div'); row.className = 'edge-row';
    row.innerHTML = `<label>Required course or condition<input data-edge="source"></label><label>Timing<select data-edge="kind">${EditorCore.KINDS.map(kind => `<option>${kind}</option>`).join('')}</select></label><label>Logic group<input data-edge="logic_group" placeholder="e.g. calculus"></label><label>Within group<select data-edge="logic_operator"><option>AND</option><option>OR</option></select></label><label class="edge-check"><input data-edge="source_in_database" type="checkbox"> Course exists in catalog</label><button type="button" class="remove-edge" aria-label="Remove requirement">Remove</button>`;
    row.querySelector('[data-edge="source"]').value = edge.source || '';
    row.querySelector('[data-edge="kind"]').value = edge.kind || 'prerequisite';
    row.querySelector('[data-edge="logic_group"]').value = edge.logic_group || '';
    row.querySelector('[data-edge="logic_operator"]').value = edge.logic_operator || 'AND';
    row.querySelector('[data-edge="source_in_database"]').checked = edge.source_in_database !== false;
    row.querySelector('.remove-edge').addEventListener('click', () => { row.remove(); setDirty(true); });
    row.querySelectorAll('input, select').forEach(control => control.addEventListener('input', () => setDirty(true)));
    return row;
  }
  function select(code) {
    if (dirty && !window.confirm('Discard unapplied edits and select another course?')) return;
    selectedCode = code; const course = data.courses.find(item => item.code === code);
    [...form.elements].forEach(control => { if (control.name && Object.hasOwn(course, control.name)) control.value = control.name === 'tags' ? (course.tags || []).join(', ') : course[control.name]; });
    edgeList.replaceChildren(...EditorCore.edgesFor(data, code).map(edgeRow));
    setDirty(false); renderList(); showValidation();
  }
  function load(document, sourceName) {
    try {
      data = EditorCore.normalize(document); filename = sourceName.replace(/\.json$/i, '') + '-corrected.json';
      selectedCode = data.courses[0]?.code || ''; workspace.hidden = false;
      status.textContent = `Loaded ${sourceName}. Review highlighted validation issues before downloading.`;
      query.value = ''; renderList(); if (selectedCode) select(selectedCode); else showValidation();
    } catch (error) { status.textContent = `Could not load JSON: ${error.message}`; }
  }
  function apply() {
    const course = data.courses.find(item => item.code === selectedCode); const previousCode = course.code;
    ['code', 'number', 'title', 'level', 'credits', 'description', 'prerequisites', 'corequisites', 'restrictions', 'repeatable', 'source_url'].forEach(name => { course[name] = form.elements[name].value.trim(); });
    course.tags = form.elements.tags.value.split(',').map(value => value.trim()).filter(Boolean);
    if (course.code !== previousCode) data.edges.forEach(edge => { if (edge.source === previousCode) edge.source = course.code; if (edge.target === previousCode) edge.target = course.code; });
    const edges = [...edgeList.children].map(row => {
      const group = row.querySelector('[data-edge="logic_group"]').value.trim();
      const edge = { source: row.querySelector('[data-edge="source"]').value.trim(), kind: row.querySelector('[data-edge="kind"]').value, source_in_database: row.querySelector('[data-edge="source_in_database"]').checked };
      if (group) { edge.logic_group = group; edge.logic_operator = row.querySelector('[data-edge="logic_operator"]').value; }
      return edge;
    });
    EditorCore.replaceEdges(data, course.code, edges); selectedCode = course.code; setDirty(false); renderList(); showValidation();
  }
  form.addEventListener('input', event => { if (!event.target.closest('.edge-row')) setDirty(true); });
  form.addEventListener('submit', event => { event.preventDefault(); apply(); status.textContent = `Applied edits to ${selectedCode}.`; });
  document.getElementById('add-edge').addEventListener('click', () => { edgeList.append(edgeRow()); setDirty(true); });
  query.addEventListener('input', renderList);
  file.addEventListener('change', async () => { if (!file.files[0]) return; try { load(JSON.parse(await file.files[0].text()), file.files[0].name); } catch (error) { status.textContent = `Could not parse JSON: ${error.message}`; } file.value = ''; });
  document.getElementById('load-example').addEventListener('click', () => load(example, 'sample-department.json'));
  document.getElementById('download-json').addEventListener('click', () => {
    if (dirty) apply(); if (!showValidation()) { status.textContent = 'Correct the validation issues before downloading.'; return; }
    const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: 'application/json' })); link.download = filename; link.click(); URL.revokeObjectURL(link.href);
    status.textContent = `Downloaded ${filename}. Run the repository validator before publishing.`;
  });
})();
