const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const P = require('../docs/releases/view-presets');
const { siteSourceRows } = require('../docs/releases/source-visibility');

test('manufacturer grouping follows first credit and normalizes corporate suffixes', () => {
  for (const [credit, expected] of [
    ['Sega / Westone', 'Sega'], ['Taito America Corporation', 'Taito'],
    ['Taito Corporation Japan', 'Taito'], ['Cave (Capcom license)', 'Cave'],
    ['Atari Games', 'Atari'], ['Data East USA', 'Data East'], ['Japan', 'Japan'], ['', ''],
  ]) assert.equal(P.makerStem(credit), expected);
  const rows = [{ manufacturer: 'CAVE' }, { manufacturer: 'Cave (Capcom license)' }, { manufacturer: 'CAVE' }];
  const cat = P.catalogue(rows, () => '');
  assert.deepEqual(P.sectionOf(rows[0], 'maker', cat), P.sectionOf(rows[1], 'maker', cat));
  assert.equal(P.sectionOf(rows[1], 'maker', cat).label, 'CAVE');
});

test('core grouping uses full catalogue counts and gathers one-game and non-arcade cores', () => {
  const rows = [
    { base: 'Arcade', core: 'A' }, { base: 'Arcade', core: 'A' },
    { base: 'Arcade', core: 'B' }, { base: 'Arcade', core: '' },
    { base: 'Console', core: 'SNES' }, { base: 'Computer', core: 'BBC' }, { base: 'Other' },
  ];
  const cat = P.catalogue(rows, c => c || '');
  assert.deepEqual(rows.map(r => P.sectionOf(r, 'core', cat).label),
    ['A', 'A', 'Single-game cores', 'Core unknown', 'Console cores', 'Computer cores', 'Other cores']);
  // A search matching only one game still calls it A, not Single-game cores.
  assert.equal(P.sectionOf(rows.slice(0, 1)[0], 'core', cat).label, 'A');
});

test('uncertain years remain unknown and same-game umbrellas retain a useful section', () => {
  const cat = P.catalogue([], () => '');
  for (const year of ['199?', '1990-1992', '', '0000']) assert.equal(P.sectionOf({year}, 'year', cat).rank, 1);
  assert.equal(P.sectionOf({year:' 1981 '}, 'year', cat).label, '1981');
  const members = [{ year: '1981' }, { year: '' }];
  assert.equal(P.sectionOf({grp:true, members}, 'year', cat).label, '1981');
});

test('shared display validation ignores unknown columns, locks Title and rejects invalid sorts', () => {
  const columns = ['title', 'core', 'updated'];
  assert.equal(P.validate({ columns: 'title' }, columns), null);
  assert.equal(P.validate({ columns: [], sort: ['<script>', 1] }, columns), null);
  const safe = P.validate({preset:'__proto__', columns:['core','core','<script>'], sort:['updated',-1], section:'__proto__'}, columns);
  assert.deepEqual(safe.columns, ['title', 'core', 'updated']);
  assert.equal(safe.section, 'updated'); // old or malformed section choices derive from the valid sort
  assert.equal(safe.preset, '');
});

test('modified detection compares the actual display irrespective of column serialization order', () => {
  const p = P.byId.get('core'), state = P.display(p);
  state.columns.reverse();
  assert.equal(P.matches(p, state), true);
  state.sameGames = true;
  assert.equal(P.matches(p, state), false);
});

test('calendar sections cover recent days, Monday-based weeks, twelve months, years and missing dates', () => {
  const calendar = P.dateSections('2026-11-04');
  const key = day => calendar.get(day).key;
  assert.equal(calendar.get('2026-11-04').label, 'Today · Nov 4');
  assert.equal(calendar.get('2026-11-03').label, 'Yesterday · Nov 3');
  assert.equal(key('2026-11-02'), 'this-week');
  assert.equal(key('2026-11-01'), 'last-week');
  assert.equal(key('2026-10-26'), 'last-week');
  assert.equal(calendar.get('2026-10-25').label, 'October 2026');
  assert.equal(key('2025-12-01'), '2025-12');
  assert.equal(key('2025-11-30'), '2025');
  assert.equal(key('2026-11-05'), 'future');
  for (const day of [undefined, '', 'bad', '2026-02-31']) assert.equal(calendar.get(day).label, 'Date unknown');
  const monday = P.dateSections('2027-01-04');
  assert.equal(monday.get('2027-01-03').label, 'Yesterday · Jan 3');
  assert.equal(monday.get('2026-12-28').key, 'last-week');
  assert.equal(P.dateSections('2024-03-01').get('2024-02-29').label, 'Yesterday · Feb 29');
  assert.equal(P.localDay(new Date(2026, 10, 4, 23, 59)), '2026-11-04');
});

test('catalogue grouping never mutates release data and gives every row a valid section', () => {
  const rows = siteSourceRows(JSON.parse(fs.readFileSync('docs/releases/data.json', 'utf8')));
  const before = JSON.stringify(rows), cat = P.catalogue(rows, c => c || '');
  for (const mode of ['letter', 'maker', 'year', 'core']) for (const row of rows) {
    const section = P.sectionOf(row, mode, cat);
    assert.equal(typeof section.key, 'string');
    assert.equal(typeof section.label, 'string');
    assert.ok(section.label.length);
  }
  assert.equal(JSON.stringify(rows), before);
});
