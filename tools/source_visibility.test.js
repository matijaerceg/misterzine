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

test('source suffix cleanup follows mirror removal, preserves identity, and is repeatable', () => {
  const original = row('bazset', 'aquajack', 'Aqua Jack (bazset)', 'aquajack',
    { g: 'aquajack', mt: 'Aqua Jack (World)', k: 'aquajack', mra: 'Aqua Jack.mra' });
  const mirror = { ...original, src: 'ongo', title: 'Aqua Jack (Ongo)', k: 'mirror' };
  const input = [mirror, original], before = JSON.stringify(input);
  const result = siteSourceRows(input);
  assert.deepEqual(result, [{ ...original, title: 'Aqua Jack' }]);
  assert.deepEqual(siteSourceRows([...input].reverse()), result);
  assert.deepEqual(siteSourceRows(result), result);
  assert.equal(JSON.stringify(input), before);
});

test('cleanup retains multiple implementations, unknown labels and meaningful qualifiers', () => {
  const a = row('meathax', 'game', 'Game (Meathax)');
  const b = row('bazset', 'game', 'Game (bazset)');
  assert.deepEqual(siteSourceRows([a, b]), [a, b]);
  for (const title of ['Game (2-player)', 'Game (4-player)', 'Game (Bootleg)',
    'Game (Japan)', 'Game (T-Unit)', 'Game (Unrecognized)']) {
    const variant = { ...a, title };
    assert.deepEqual(siteSourceRows([variant]), [variant]);
  }
  const bootleg = { ...a, title: 'Game (Bootleg) (Meathax)' };
  assert.equal(siteSourceRows([bootleg])[0].title, 'Game (Bootleg)');
  const collision = row('other', 'different', 'Game');
  assert.deepEqual(siteSourceRows([a, collision]), [a, collision]);
  const unknown = { ...a, sn: '', family: '' };
  assert.deepEqual(siteSourceRows([unknown]), [unknown]);
});

test('published Aqua Jack and Meta Fox become unambiguous plain titles', () => {
  const rows = require('../docs/releases/data.json');
  const visible = siteSourceRows(rows);
  for (const [src, sn, title] of [['bazset', 'aquajack', 'Aqua Jack'], ['meathax', 'metafox', 'Meta Fox']]) {
    const original = rows.find(r => r.src === src && r.sn === sn);
    const result = visible.find(r => r.k === original.k);
    assert.deepEqual(result, { ...original, title });
  }
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
