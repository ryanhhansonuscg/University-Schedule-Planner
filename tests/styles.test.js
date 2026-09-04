const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

const css = fs.readFileSync('assets/styles.css', 'utf8');

function luminance(hex) {
  const channels = hex.match(/[a-f\d]{2}/gi).map(value => parseInt(value, 16) / 255)
    .map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

function contrast(first, second) {
  const values = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

test('essential modern colors retain preceding concrete fallbacks', () => {
  const declarations = css.split(/\n|;/).map(value => value.trim().replace(/^.*\{\s*/, '')).filter(Boolean);
  declarations.forEach((declaration, index) => {
    if (!/light-dark\(|color-mix\(/.test(declaration)) return;
    const property = declaration.match(/^([\w-]+):/)[1];
    assert.match(declarations[index - 1], new RegExp(`^${property}:`), `${property} needs an adjacent fallback`);
    assert.doesNotMatch(declarations[index - 1], /light-dark\(|color-mix\(/);
  });
});

test('fallback text palette meets WCAG AA contrast', () => {
  assert.ok(contrast('#152019', '#f7f7f3') >= 4.5);
  assert.ok(contrast('#627066', '#ffffff') >= 4.5);
  assert.ok(contrast('#ffffff', '#1d6d45') >= 4.5);
});

test('focus rings contrast with light and dark surfaces', () => {
  assert.ok(contrast('#005fcc', '#ffffff') >= 3);
  assert.ok(contrast('#005fcc', '#f7f7f3') >= 3);
  assert.ok(contrast('#8ecaff', '#191f1c') >= 3);
  assert.ok(contrast('#8ecaff', '#111513') >= 3);
});

test('file import focus remains visible in normal and forced colors', () => {
  assert.match(css, /\.file-action:focus-within\s*\{[^}]*outline:/);
  assert.match(css, /@media \(forced-colors: active\)[\s\S]*\.file-action:focus-within[^}]*outline:\s*3px solid Highlight/);
});
