const { test } = require('node:test');
const assert = require('node:assert/strict');
const { siteSourceRows } = require('../docs/releases/source-visibility');
const row = (src, sn, title = 'Game', family = sn, extra = {}) =>
  ({ src, sn, title, family, base: 'Arcade', ...extra });

test('Meathax Simpsons launchers show their player counts without changing launch identity', () => {
  const variants = [row('meathax', 'simpsons2p', 'The Simpsons', 'simpsons',
    { core: 'Arcade-Simpsons', k: 'the-simpsons', mra: '_Arcade/_MeatCores/The Simpsons.mra' }),
  row('meathax', 'simpsons', 'Simpsons', 'simpsons',
    { core: 'Arcade-Simpsons', k: 'simpsons-2', mra: '_Arcade/_MeatCores/Simpsons.mra' })];
  const before = JSON.stringify(variants);
  const result = siteSourceRows(variants);
  assert.deepEqual(result.map(r => r.title), ['Simpsons (2-player)', 'Simpsons (4-player)']);
  result.forEach((r, i) => assert.deepEqual(r, { ...variants[i], title: r.title, mt: variants[i].title }));
  assert.equal(JSON.stringify(variants), before);
  assert.deepEqual(siteSourceRows(result), result);
  const jotego = { ...variants[1], src: 'jtbindb', core: 'jtsimson' };
  assert.deepEqual(siteSourceRows([jotego]), [jotego]);
});

test('renamed mirrors need game identity plus core evidence', () => {
  const direct = row('meathax', 'btoads', 'Battletoads', '', { core: 'Arcade-Battletoads', bh: 'abc' });
  const copy = row('ongo', 'btoads_meathax', 'Battletoads (Meathax)', '', { core: 'Meathax_Battletoads', bh: 'abc' });
  const newer = { ...copy, bh: 'def' };
  const otherGame = { ...copy, title: 'Another Game', sn: 'another' };
  const otherCore = { ...newer, core: 'DifferentCore' };
  const unknown = { ...newer, sn: 'btoads_unknown' };
  const before = JSON.stringify([copy, direct]);
  assert.deepEqual(siteSourceRows([copy, direct]), [direct]);
  assert.deepEqual(siteSourceRows([direct, newer]), [direct]);
  assert.deepEqual(siteSourceRows([direct, otherGame, otherCore, unknown]), [direct, otherGame, otherCore, unknown]);
  assert.deepEqual(siteSourceRows([{ ...direct, deprecated: true }, copy]), [{ ...direct, deprecated: true }, copy]);
  assert.equal(JSON.stringify([copy, direct]), before);
});

test('catalogue audit hides renamed copies but retains distinct implementations and games', () => {
  const rows = require('../docs/releases/data.json');
  const visible = new Set(siteSourceRows(rows).map(r => r.k));
  for (const key of ['btoads_meathax', 'narc_blahm1d', 'narc_meathax']) assert.ok(!visible.has(key), key);
  for (const key of ['btoads', 'narc', 'narc-blahm1d', 'mk_wolf', 'mk2_wolf', 'otwalls', 'swa', 'hotrod', 'sparkman', 'nbajamtese']) assert.ok(visible.has(key), key);
});

test('Meikyu Jima name aliases share one stable launcher without changing app data', () => {
  const japan = row('bazset', 'kikcubic', 'Meikyu Jima (bazset)', 'kikcubic',
    { k: 'meikyu-jima', mra: '_Arcade/_BAZSET/Meikyu Jima (Japan).mra' });
  const english = { ...japan, k: 'kickle-cubicle', title: 'Meikyu Jima',
    mra: '_Arcade/_BAZSET/Kickle Cubicle (English title).mra' };
  const before = JSON.stringify([english, japan]);
  const result = siteSourceRows([english, japan]);
  assert.equal(result.length, 1);
  assert.equal(result[0].title, 'Meikyu Jima / Kickle Cubicle');
  assert.equal(result[0].mra, japan.mra);
  assert.equal(result[0].k, japan.k);
  assert.deepEqual(result[0].siteAliases, ['kickle-cubicle']);
  assert.deepEqual(siteSourceRows([japan, english]), result);
  assert.equal(JSON.stringify([english, japan]), before);
  assert.equal(siteSourceRows([english])[0].mra, english.mra);
});

test('other sources win regardless of order without mutating the feed', () => {
  const direct = row('meathax', 'game');
  const backup = row('ongo', 'game');
  const unique = row('ongo', 'unique', 'Unique');
  const input = [backup, unique, direct];
  const before = JSON.stringify(input);
  assert.deepEqual(siteSourceRows(input), [unique, direct]);
  assert.deepEqual(siteSourceRows([...input].reverse()), [direct, unique]);
  assert.equal(JSON.stringify(input), before);
  assert.deepEqual(siteSourceRows([backup]), [backup]);
});

test('regional revisions fold but distinct games sharing a family survive', () => {
  const mk = row('blahm1d', 'mk', 'Mortal Kombat (T-Unit)');
  const revision = row('ongo', 'mkla4', 'Mortal Kombat (rev 4)', 'mk');
  const sprint1 = row('distribution_mister', 'sprint1', 'Sprint 1');
  const sprint2 = row('ongo', 'sprint2', 'Sprint 2', 'sprint1');
  const jima = row('bazset', 'kikcubic', 'Meikyu Jima');
  const kickle = row('ongo', 'kikcubicb', 'Kickle Cubele', 'kikcubic');
  assert.deepEqual(siteSourceRows([mk, revision, sprint1, sprint2, jima, kickle]),
    [mk, sprint1, sprint2, jima]);
});

test('missing metadata and retired sources do not hide a backup', () => {
  const backup = row('ongo', '', 'Unknown', '');
  const retired = row('meathax', 'old', 'Old', 'old', { deprecated: true });
  const available = row('ongo', 'old', 'Old');
  assert.deepEqual(siteSourceRows([row('other', '', 'Unknown', ''), backup, retired, available]),
    [row('other', '', 'Unknown', ''), backup, retired, available]);
});
