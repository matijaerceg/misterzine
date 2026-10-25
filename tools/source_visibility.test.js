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
  assert.deepEqual(result, [{ ...original, title: 'Aqua Jack', siteAliases: ['mirror'] }]);
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

test('published Aqua Jack and Meta Fox: one build drops its label, two builds keep theirs', () => {
  const rows = require('../docs/releases/data.json');
  const visible = siteSourceRows(rows);
  const shown = (src, sn) => visible.find(r => r.k === rows.find(o => o.src === src && o.sn === sn).k);
  // bazset's Aqua Jack is the only build listed; Ongo's copy of it folds in
  const aqua = shown('bazset', 'aquajack');
  assert.equal(aqua.title, 'Aqua Jack');
  assert.ok(aqua.alsoOngo);
  assert.ok(aqua.siteAliases.includes(rows.find(r => r.src === 'ongo' && r.sn === 'aquajack').k));
  // (Meta Fox used to be the second example; ppriest dropped it from his db
  // on 2026-10-25, leaving Ongo's copy alone.)
  // Power Spikes: asturur's own db folds Ongo's earlier build of his core,
  // a different file under another core name, so no alsoOngo note
  const spikes = shown('asturur', 'pspikes');
  assert.equal(spikes.title, 'Power Spikes');
  assert.ok(!spikes.alsoOngo);
  assert.ok(spikes.siteAliases.includes(rows.find(r => r.src === 'ongo' && r.sn === 'pspikes').k));
  assert.ok(!visible.some(r => r.src === 'ongo' && r.sn === 'pspikes'));
  // Night Slashers ships on two different cores: both stay, each named
  assert.equal(shown('blahm1d', 'nslashers').title, 'Night Slashers (blahm1d)');
  assert.equal(shown('distribution_mister', 'nslasher').title, 'Night Slashers (rmonic79)');
});

test('renamed mirrors need game identity plus core evidence', () => {
  const direct = row('meathax', 'btoads', 'Battletoads', '', { core: 'Arcade-Battletoads', bh: 'abc' });
  const copy = row('ongo', 'btoads_meathax', 'Battletoads (Meathax)', '', { core: 'Meathax_Battletoads', bh: 'abc' });
  const newer = { ...copy, bh: 'def' };
  const otherGame = { ...copy, title: 'Another Game', sn: 'another' };
  const otherCore = { ...newer, core: 'DifferentCore' };
  const unknown = { ...newer, sn: 'btoads_unknown' };
  const before = JSON.stringify([copy, direct]);
  assert.deepEqual(siteSourceRows([copy, direct]), [{ ...direct, alsoOngo: true }]);
  assert.deepEqual(siteSourceRows([direct, newer]), [{ ...direct, alsoOngo: true }]);
  assert.deepEqual(siteSourceRows([direct, otherGame, otherCore, unknown]), [direct, otherGame, otherCore, unknown]);
  assert.deepEqual(siteSourceRows([{ ...direct, deprecated: true }, copy]), [{ ...direct, deprecated: true }, copy]);
  assert.equal(JSON.stringify([copy, direct]), before);
});

test('catalogue audit hides renamed copies but retains distinct implementations and games', () => {
  const rows = require('../docs/releases/data.json');
  const visible = new Set(siteSourceRows(rows).map(r => r.k));
  // otwalls: Ongo's Off the Wall (Sente) gives way to ppriest's own build
  for (const key of ['narc_blahm1d', 'otwalls']) assert.ok(!visible.has(key), key);
  for (const key of ['narc-blahm1d', 'mk_wolf', 'mk2_wolf', 'off-the-wall-sente-10-16-84', 'swa', 'nbajamtese']) assert.ok(visible.has(key), key);
  // MeatCores is delisted (misterzine.py DELISTED_SOURCES): neither its rows
  // nor Ongo's copies of its cores reach the site
  assert.ok(!rows.some(r => r.src === 'meathax' || /^meathax_/i.test(r.core || '')));
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

test('a hidden Ongo copy hands its key to the original, and notes Ongo only for the same build', () => {
  const ppriest = row('ppriest', 'metafox', 'Meta Fox', 'metafox', { k: 'meta-fox-ppriest', core: 'SetaDowntown' });
  const meathax = row('meathax', 'metafox', 'Meta Fox', 'metafox', { k: 'meta-fox', core: 'Arcade-Arbalester' });
  const copy = row('ongo', 'metafox', 'Meta Fox (Ongo)', 'metafox', { k: 'meta-fox-ongo', core: 'SetaDowntown' });
  const input = [meathax, copy, ppriest], before = JSON.stringify(input);
  const result = siteSourceRows(input);
  assert.deepEqual(result.map(r => r.k), ['meta-fox', 'meta-fox-ppriest']);
  assert.deepEqual(result[1].siteAliases, ['meta-fox-ongo']);
  assert.equal(result[1].alsoOngo, true);
  assert.equal(result[0].siteAliases, undefined);
  assert.equal(result[0].alsoOngo, undefined);
  assert.equal(JSON.stringify(input), before);
  // only another core lists it: the copy still gives way, without the Ongo note
  assert.deepEqual(siteSourceRows([meathax, copy]), [{ ...meathax, siteAliases: ['meta-fox-ongo'] }]);
});

test("Kyle Lester's cores stay listed: Ongo is their home, not a copy", () => {
  const decoryah = row('decoryah', 'nost', 'Nostradamus', 'nost', { k: 'nostradamus-decoryah', core: 'mcatadv' });
  const kyle = row('ongo', 'nost', 'Nostradamus', 'nost',
    { k: 'nost', core: 'Nostradamus', repo: 'kyledlester/Nostradamus_Magical_Cat_Adventure_MiSTer' });
  const mirror = row('ongo', 'nost', 'Nostradamus', 'nost', { k: 'nost-2', core: 'mcatadv' });
  assert.deepEqual(siteSourceRows([kyle, decoryah]), [kyle, decoryah]);
  assert.deepEqual(siteSourceRows([kyle, mirror, decoryah]).map(r => r.k), ['nost', 'nostradamus-decoryah']);
});

test('Meikyu Jima keeps an Ongo key folded into its English launcher', () => {
  const japan = row('bazset', 'kikcubic', 'Meikyu Jima', 'kikcubic',
    { k: 'meikyu-jima', mra: '_Arcade/_BAZSET/Meikyu Jima (Japan).mra' });
  const english = { ...japan, k: 'kickle-cubicle', mra: '_Arcade/_BAZSET/Kickle Cubicle (English title).mra' };
  const copy = row('ongo', 'kikcubicb', 'Kickle Cubele', 'kikcubic', { k: 'kickle-ongo', core: 'bazset_kickle' });
  const [lead] = siteSourceRows([english, copy, japan]);
  assert.equal(lead.k, 'meikyu-jima');
  assert.deepEqual([...lead.siteAliases].sort(), ['kickle-cubicle', 'kickle-ongo']);
  assert.equal(lead.alsoOngo, true);
});
