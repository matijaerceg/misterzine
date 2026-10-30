const { test } = require('node:test');
const assert = require('node:assert/strict');
const { siteSourceRows, SITE_SOURCE_LABELS } = require('../docs/releases/source-visibility');
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

test('one listed build drops its label, two builds keep theirs', () => {
  // Power Spikes: asturur's own db folds Ongo's earlier build of his core
  // (a different file under another core name, so no alsoOngo note)
  const asturur = row('asturur', 'pspikes', 'Power Spikes (asturur)', 'pspikes',
    { g: 'pspikes', k: 'power-spikes-asturur', core: 'jtpspike', bh: 'aaa', mt: 'Power Spikes (World)' });
  const copy = row('ongo', 'pspikes', 'Power Spikes (Ongo)', 'pspikes',
    { g: 'pspikes', k: 'pspikes', core: 'pspike', bh: 'bbb', mt: 'Power Spikes (World)' });
  const alone = siteSourceRows([copy, asturur]);
  assert.deepEqual(alone, [{ ...asturur, title: 'Power Spikes', siteAliases: ['pspikes'] }]);
  // rmCores ships its own Power Spikes core (2026-10-29): two builds listed,
  // both named after their source, Ongo's copy still folded into asturur's
  const rm = row('rmcores', 'pspikes', 'Power Spikes (rmCores)', 'pspikes',
    { g: 'pspikes', k: 'power-spikes-rmcores', core: 'rmPowerSpikes', bh: 'ccc', mt: 'rm Power Spikes (World)' });
  const both = siteSourceRows([copy, asturur, rm]);
  assert.deepEqual(both, [{ ...asturur, siteAliases: ['pspikes'] }, rm]);
  assert.ok(!both.some(r => r.alsoOngo));
  // Night Slashers ships on two different cores: both stay, each named
  const blahm1d = row('blahm1d', 'nslashers', 'Night Slashers (blahm1d)', 'nslasher',
    { g: 'nslasher', k: 'nslashers-blahm1d', core: 'NightSlashers' });
  const rmonic = row('distribution_mister', 'nslasher', 'Night Slashers (rmonic79)', 'nslasher',
    { g: 'nslasher', k: 'nslasher', core: 'NightSlashers79' });
  assert.deepEqual(siteSourceRows([blahm1d, rmonic]), [blahm1d, rmonic]);
  // Aqua Jack: bazset's build is the only one listed and Ongo ships that
  // same core under bazset's name, so the row says Ongo has it too
  const aqua = row('bazset', 'aquajack', 'Aqua Jack (bazset)', 'aquajack',
    { g: 'aquajack', k: 'aquajack', core: 'AquaJack', bh: 'ddd', mt: 'Aqua Jack (World)' });
  const mirror = row('ongo', 'aquajack', 'Aqua Jack (Ongo)', 'aquajack',
    { g: 'aquajack', k: 'aquajack-ongo', core: 'bazset_AquaJack', bh: 'eee' });
  assert.deepEqual(siteSourceRows([mirror, aqua]),
    [{ ...aqua, title: 'Aqua Jack', siteAliases: ['aquajack-ongo'], alsoOngo: true }]);
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

// The published export is checked against the rules above, never against
// facts about particular games: developers ship and drop games every day,
// and a catalogue change alone must not be able to stop the site refresh.
test('published data: every source is labelled, keys survive folding, lone builds drop their label', () => {
  const rows = require('../docs/releases/data.json');
  const arcade = rows.filter(r => r.base === 'Arcade');
  const norm = title => (title || '').trim().toLowerCase().replace(/[^a-z0-9]/g, '');
  // every arcade source has a label entry (the Distributions label per core,
  // never per source, so they need none)
  const unbranded = new Set(['distribution_mister', 'theypsilon_unofficial_distribution']);
  const sources = [...new Set(arcade.map(r => r.src).filter(src => src && !unbranded.has(src)))];
  for (const src of sources) assert.ok(SITE_SOURCE_LABELS[src], `source ${src} missing from SITE_SOURCE_LABELS`);
  const visible = siteSourceRows(rows);
  // every deep-link key either stays visible or is carried as an alias by
  // exactly one visible row, so links and stars made on a hidden copy land
  const seen = new Map();
  for (const r of visible) for (const k of [r.k, ...(r.siteAliases || [])]) {
    assert.ok(k, `visible row without a key: ${r.title}`);
    assert.ok(!seen.has(k), `key ${k} reachable twice: ${seen.get(k)} and ${r.title}`);
    seen.set(k, r.title);
  }
  for (const r of rows) assert.ok(seen.has(r.k), `key ${r.k} (${r.src} ${r.title}) lost from the site`);
  assert.equal(seen.size, rows.length);
  // a hidden row is always an Ongo copy of a listed arcade game, or the
  // English-named twin of bazset's Meikyu Jima launcher
  const shown = new Set(visible.map(r => r.k));
  for (const r of rows.filter(r => !shown.has(r.k))) {
    const twin = r.src === 'bazset' && r.sn === 'kikcubic';
    assert.ok(r.src === 'ongo' || twin, `${r.src} ${r.title} hidden`);
    assert.equal(r.base, 'Arcade', `${r.title} hidden`);
  }
  // no visible Ongo row duplicates a listed game's set name
  const listedSets = new Set(visible.filter(r => r.src !== 'ongo' && r.base === 'Arcade' && !r.deprecated && r.sn)
    .map(r => r.sn.toLowerCase()));
  const ongoHome = r => /^kyledlester\//i.test(r.repo || '');
  for (const r of visible.filter(r => r.src === 'ongo' && r.base === 'Arcade' && r.sn && !ongoHome(r)))
    assert.ok(!listedSets.has(r.sn.toLowerCase()), `Ongo copy of ${r.sn} still visible`);
  // the only listed build of a game carries no source brand, unless the
  // plain name already belongs to another game (two builds reading the same
  // is misterzine.py's warn-only DUPLICATE TITLE tripwire, not a gate here)
  const counts = new Map();
  for (const r of visible.filter(r => r.base === 'Arcade')) {
    const id = r.g || r.family || r.sn;
    if (id) counts.set(id, (counts.get(id) || 0) + 1);
  }
  const titles = new Set(visible.map(r => norm(r.title)));
  for (const r of visible.filter(r => r.base === 'Arcade' && counts.get(r.g || r.family || r.sn) === 1)) {
    const suffix = SITE_SOURCE_LABELS[r.src] && ` (${SITE_SOURCE_LABELS[r.src]})`;
    if (!suffix || !r.title.endsWith(suffix)) continue;
    const plain = norm(r.title.slice(0, -suffix.length));
    assert.ok(titles.has(plain), `${r.title} keeps its label though ${plain} is free`);
  }
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
