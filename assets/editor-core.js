(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.EditorCore = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const LEVELS = ['undergraduate', 'graduate', 'professional', 'continuing-education', 'other'];
  const KINDS = ['prerequisite', 'corequisite', 'recommended'];

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function normalize(document) {
    if (!document || typeof document !== 'object' || Array.isArray(document)) throw new Error('The JSON root must be an object.');
    if (!document.department || typeof document.department.code !== 'string') throw new Error('A department object with a code is required.');
    if (!Array.isArray(document.courses) || !Array.isArray(document.edges)) throw new Error('courses and edges must both be arrays.');
    const result = clone(document);
    result.courses.forEach(course => { if (!Array.isArray(course.tags)) course.tags = []; });
    return result;
  }
  function validate(document) {
    const errors = [];
    let data;
    try { data = normalize(document); } catch (error) { return [error.message]; }
    const codes = new Set();
    data.courses.forEach((course, index) => {
      const label = `Course ${index + 1}`;
      if (!/^[A-Z][A-Z0-9]{1,11}[0-9]{1,4}[A-Z]?$/.test(course.code || '')) errors.push(`${label} has an invalid course code.`);
      if (codes.has(course.code)) errors.push(`${label} duplicates ${course.code}.`);
      codes.add(course.code);
      if (!course.title?.trim()) errors.push(`${course.code || label} needs a title.`);
      if (!LEVELS.includes(course.level)) errors.push(`${course.code || label} has an invalid level.`);
      if (!/^(?:0|[1-9]\d*)(?:\.\d+)?(?:-(?:0|[1-9]\d*)(?:\.\d+)?)?$/.test(String(course.credits ?? ''))) errors.push(`${course.code || label} has invalid credits.`);
      if (course.department !== data.department.code) errors.push(`${course.code || label} must use department ${data.department.code}.`);
    });
    data.edges.forEach((edge, index) => {
      const label = `Requirement ${index + 1}`;
      if (!codes.has(edge.target)) errors.push(`${label} targets an unknown course.`);
      if (!KINDS.includes(edge.kind)) errors.push(`${label} has an invalid relationship type.`);
      if (typeof edge.source !== 'string' || !edge.source.trim()) errors.push(`${label} needs a source.`);
      if (typeof edge.source_in_database !== 'boolean') errors.push(`${label} must state whether its source is in this data set.`);
      if ((edge.logic_group || edge.logic_operator) && (!edge.logic_group || !['AND', 'OR'].includes(edge.logic_operator))) errors.push(`${label} has an incomplete logic group.`);
    });
    return errors;
  }
  function edgesFor(document, target) { return document.edges.filter(edge => edge.target === target); }
  function replaceEdges(document, target, replacements) {
    document.edges = document.edges.filter(edge => edge.target !== target).concat(replacements.map(edge => ({ ...edge, target })));
  }
  return { LEVELS, KINDS, normalize, validate, edgesFor, replaceEdges };
}));
