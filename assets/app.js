(async () => {
  let data;
  try {
    ({ catalog: data } = await window.COLLEGE_PLANNER.loadCatalog());
  } catch {
    return;
  }

  const courses = data.courses || [];
  const edges = data.edges || [];
  const courseByCode = new Map(courses.map(course => [course.code, course]));
  const incoming = new Map();
  const outgoing = new Map();
  edges.forEach(edge => {
    if (!incoming.has(edge.target)) incoming.set(edge.target, []);
    if (!outgoing.has(edge.source)) outgoing.set(edge.source, []);
    incoming.get(edge.target).push(edge);
    outgoing.get(edge.source).push(edge);
  });

  const department = document.getElementById('department');
  const level = document.getElementById('level');
  const tag = document.getElementById('tag');
  const query = document.getElementById('query');
  const list = document.getElementById('course-list');
  const count = document.getElementById('result-count');
  const graph = document.getElementById('graph');
  const graphNodes = graph.querySelector('.graph-nodes');
  const edgeLayer = graph.querySelector('svg g');
  const details = document.getElementById('details');
  let selectedCode = '';

  const university = data.university || {};
  document.getElementById('map-title').textContent = university.map_title || `${university.short_name || 'University'} course explorer`;
  document.title = `${university.short_name || university.name || 'College'} Course Explorer`;
  document.getElementById('site-footer').textContent = `Catalog snapshot: ${university.catalog_date || 'date not recorded'}. Confirm requirements and availability with ${university.short_name || university.name || 'the university'} before registration.`;

  const departmentNames = new Map((data.departments || []).map(item => [item.code, item.name]));
  const departmentCodes = [...new Set(courses.map(course => course.department))].sort();
  department.replaceChildren(...departmentCodes.map(code => new Option(`${code} · ${departmentNames.get(code) || code}`, code)));

  function filteredCourses() {
    const needle = query.value.trim().toLowerCase();
    return courses.filter(course =>
      course.department === department.value
      && (level.value === 'all' || course.level === level.value)
      && (tag.value === 'all' || (course.tags || []).includes(tag.value))
      && (!needle || `${course.code} ${course.title} ${course.description || ''} ${(course.tags || []).join(' ')}`.toLowerCase().includes(needle))
    );
  }

  function refreshTags() {
    const current = tag.value;
    const values = [...new Set(courses
      .filter(course => course.department === department.value && (level.value === 'all' || course.level === level.value))
      .flatMap(course => course.tags || []))].sort();
    tag.replaceChildren(new Option('All tags', 'all'), ...values.map(value => new Option(value, value)));
    tag.value = values.includes(current) ? current : 'all';
  }

  function appendCourseLabel(container, course) {
    const strong = document.createElement('strong');
    strong.textContent = course.code;
    const title = document.createElement('span');
    title.textContent = course.title;
    container.append(strong, title);
  }

  function renderList() {
    const matches = filteredCourses();
    count.textContent = `${matches.length} course${matches.length === 1 ? '' : 's'}`;
    list.replaceChildren(...matches.map(course => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'course-button';
      button.setAttribute('aria-pressed', String(course.code === selectedCode));
      appendCourseLabel(button, course);
      button.addEventListener('click', () => selectCourse(course.code));
      return button;
    }));
  }

  function neighborhood(code) {
    if (!code) return new Map();
    const layers = new Map([[code, 0]]);
    let frontier = [code];
    for (let depth = 1; depth <= 3; depth += 1) {
      const next = [];
      frontier.forEach(target => (incoming.get(target) || []).forEach(edge => {
        if (courseByCode.has(edge.source) && !layers.has(edge.source)) {
          layers.set(edge.source, -depth);
          next.push(edge.source);
        }
      }));
      frontier = next;
    }
    frontier = [code];
    for (let depth = 1; depth <= 2; depth += 1) {
      const next = [];
      frontier.forEach(source => (outgoing.get(source) || []).forEach(edge => {
        if (courseByCode.has(edge.target) && !layers.has(edge.target)) {
          layers.set(edge.target, depth);
          next.push(edge.target);
        }
      }));
      frontier = next;
    }
    const layerValues = [...new Set(layers.values())].sort((a, b) => a - b);
    const compact = new Map(layerValues.map((value, index) => [value, index]));
    return new Map([...layers].map(([key, value]) => [key, compact.get(value)]));
  }

  function renderGraph() {
    const layers = neighborhood(selectedCode);
    graphNodes.replaceChildren();
    edgeLayer.replaceChildren();
    if (!layers.size) {
      const empty = document.createElement('p');
      empty.className = 'graph-empty';
      empty.textContent = 'No courses match the current filters.';
      graphNodes.appendChild(empty);
      return;
    }

    const layerCount = Math.max(...layers.values()) + 1;
    const grouped = Array.from({ length: layerCount }, () => []);
    layers.forEach((column, code) => grouped[column].push(code));
    grouped.forEach(items => items.sort());
    const mobile = graph.clientWidth < 560;
    const rowHeight = mobile ? 78 : 72;
    const maxRows = Math.max(...grouped.map(items => items.length), 1);
    const height = Math.max(mobile ? 660 : 420, maxRows * rowHeight + 70);
    graph.style.minHeight = `${height}px`;
    const width = graph.clientWidth;
    const sidePadding = mobile ? 72 : 95;
    const positions = new Map();
    grouped.forEach((items, column) => items.forEach((code, row) => {
      const x = layerCount === 1 ? width / 2 : sidePadding + column * ((width - sidePadding * 2) / Math.max(1, layerCount - 1));
      const y = 46 + row * rowHeight;
      positions.set(code, { x, y });
    }));

    layers.forEach((_column, code) => {
      const course = courseByCode.get(code);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `graph-node${code === selectedCode ? ' selected' : ''}`;
      button.style.left = `${positions.get(code).x}px`;
      button.style.top = `${positions.get(code).y}px`;
      appendCourseLabel(button, course);
      button.addEventListener('click', () => selectCourse(code));
      graphNodes.appendChild(button);
    });

    edges.filter(edge => layers.has(edge.source) && layers.has(edge.target)).forEach(edge => {
      const from = positions.get(edge.source);
      const to = positions.get(edge.target);
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      const bend = (from.x + to.x) / 2;
      path.setAttribute('d', `M ${from.x} ${from.y} C ${bend} ${from.y}, ${bend} ${to.y}, ${to.x} ${to.y}`);
      path.setAttribute('class', edge.kind);
      edgeLayer.appendChild(path);
    });
  }

  function addDetailRow(listElement, label, content) {
    const term = document.createElement('dt');
    term.textContent = label;
    const description = document.createElement('dd');
    if (content instanceof Node) description.appendChild(content);
    else description.textContent = content;
    listElement.append(term, description);
  }

  function renderDetails() {
    details.replaceChildren();
    const course = courseByCode.get(selectedCode);
    if (!course) return;
    const heading = document.createElement('h3');
    heading.textContent = `${course.code} · ${course.title}`;
    const meta = document.createElement('p');
    meta.className = 'meta';
    meta.textContent = `${course.level || 'level not recorded'} · ${course.credits || '?'} credit hours · ${departmentNames.get(course.department) || course.department}`;
    const description = document.createElement('p');
    description.textContent = course.description || 'No description listed.';
    const definitionList = document.createElement('dl');
    addDetailRow(definitionList, 'Prerequisites', course.prerequisites || 'None listed');
    addDetailRow(definitionList, 'Corequisites', course.corequisites || 'None listed');
    ['prerequisite', 'corequisite'].forEach(kind => {
      const groups = PlannerCore.requirementGroups(edges, course.code, kind);
      if (groups.length) addDetailRow(definitionList, `Structured ${kind} groups`, PlannerCore.describeRequirementGroups(groups));
    });
    addDetailRow(definitionList, 'Restrictions', course.restrictions || 'None listed');

    const history = document.createElement('span');
    if (!(course.offering_history || []).length) {
      history.textContent = 'No offering history recorded';
    } else {
      course.offering_history.forEach((offering, index) => {
        if (index) history.append(', ');
        if (offering.source_url) {
          const link = document.createElement('a');
          link.href = offering.source_url;
          link.target = '_blank';
          link.rel = 'noreferrer';
          link.textContent = offering.term_name || offering.term_code;
          history.appendChild(link);
        } else history.append(offering.term_name || offering.term_code);
      });
    }
    addDetailRow(definitionList, 'Offerings', history);

    const tags = document.createElement('span');
    tags.className = 'tags';
    (course.tags || []).forEach(value => {
      const item = document.createElement('span');
      item.className = 'tag';
      item.textContent = value;
      tags.appendChild(item);
    });
    addDetailRow(definitionList, 'Tags', tags);

    const source = document.createElement('span');
    if (course.source_url) {
      const link = document.createElement('a');
      link.href = course.source_url;
      link.target = '_blank';
      link.rel = 'noreferrer';
      link.textContent = 'Official catalog listing';
      source.appendChild(link);
    } else source.textContent = 'No source URL recorded';
    addDetailRow(definitionList, 'Catalog', source);
    details.append(heading, meta, description, definitionList);
  }

  function selectCourse(code) {
    selectedCode = code;
    renderList();
    renderGraph();
    renderDetails();
  }

  function refresh() {
    refreshTags();
    const matches = filteredCourses();
    if (!matches.some(course => course.code === selectedCode)) {
      selectedCode = matches.length ? matches.reduce((best, course) => {
        const score = (incoming.get(course.code) || []).length + (outgoing.get(course.code) || []).length;
        const bestScore = (incoming.get(best.code) || []).length + (outgoing.get(best.code) || []).length;
        return score > bestScore ? course : best;
      }, matches[0]).code : '';
    }
    renderList();
    renderGraph();
    renderDetails();
  }

  [department, level, tag].forEach(control => control.addEventListener('change', refresh));
  query.addEventListener('input', refresh);
  new ResizeObserver(renderGraph).observe(graph);
  document.getElementById('load-status').hidden = true;
  document.getElementById('explorer').hidden = false;
  document.getElementById('app').setAttribute('aria-busy', 'false');
  refresh();
})();
