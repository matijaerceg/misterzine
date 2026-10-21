// Website-only source preference. Keep the shared app catalogue intact.
function siteGameTitle(row) {
  return (row.mt || row.title || '').trim().toLowerCase()
    .replace(/\s*[\(\[].*$/, '').replace(/[^a-z0-9]/g, '');
}

function siteRenamedMirror(row, original) {
  const norm = value => (value || '').trim().toLowerCase();
  if (!siteGameTitle(row) || siteGameTitle(row) !== siteGameTitle(original)) return false;
  // A shared core can run many games: require the game title as well.
  if (norm(row.bh) && norm(row.bh) === norm(original.bh)) return true;
  // A mirror may carry a different build. Only remove a source suffix when
  // it names this original's source, and the core identity agrees too.
  const source = norm(original.src), set = norm(original.sn);
  if (!source || !set || norm(row.sn) !== set + '_' + source) return false;
  const core = value => {
    let name = norm(value).replace(/^arcade[-_]/, '');
    if (name.startsWith(source + '_')) name = name.slice(source.length + 1);
    return name;
  };
  return !!core(row.core) && core(row.core) === core(original.core);
}

// Developers whose cores reach update_all only through Ongo (their own repos
// have no database), so an Ongo row of theirs is the original, never a copy:
// Kyle Lester's Nostradamus core stays listed beside decoryah's, and his
// Crystal System beside Meathax's.
const ONGO_HOME_OWNERS = ['kyledlester'];

// Does an Ongo copy carry the original's own build (so the original's panel
// can say Ongo ships it too)? The same rbf bytes, or the same core: Ongo
// names most mirrored cores <source>_<Core> (bazset_AquaJack, Meathax_SPY).
function siteSameBuild(copy, original) {
  const norm = value => (value || '').trim().toLowerCase();
  if (norm(copy.bh) && norm(copy.bh) === norm(original.bh)) return true;
  const core = value => norm(value).replace(/^arcade[-_]/, '').replace(/_\d{8}[a-z]?$/, '');
  const c = core(copy.core);
  if (!c) return false;
  return c.startsWith(norm(original.src) + '_') || c === core(original.core);
}

function siteSingletonTitles(rows) {
  // Only known source-brand suffixes are disposable. Never strip arbitrary
  // parentheses (player count, hardware, region, bootleg, etc.).
  const labels = { coinop: 'Coin-Op Collection', jtbindb: 'Jotego', meathax: 'Meathax',
    rmcores: 'rmCores', slopcore: 'TheJesusFish', kuzecores: 'kuzearcade',
    blahm1d: 'blahm1d', bazset: 'bazset', rossops: 'rossops', ongo: 'Ongo',
    tomsvr: 'TomSVR', decoryah: 'decoryah', ppriest: 'ppriest', gm0rk: 'Gm0rk',
    jlrh: 'jlrh', shmupfan: 'shmupfan' };
  const norm = title => (title || '').trim().toLowerCase().replace(/[^a-z0-9]/g, '');
  const identity = row => row.g || row.family || row.sn;
  const counts = new Map(), names = new Map();
  const proposed = rows.map(row => {
    const suffix = labels[row.src] && ` (${labels[row.src]})`;
    return row.base === 'Arcade' && suffix && row.title.endsWith(suffix)
      ? row.title.slice(0, -suffix.length) : row.title;
  });
  rows.forEach((row, i) => {
    if (row.base === 'Arcade' && identity(row)) {
      const key = identity(row);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    const name = norm(proposed[i]);
    names.set(name, (names.get(name) || 0) + 1);
  });
  // A plain name another game already uses (the arcade Rush'n Attack beside
  // ppriest's PlayChoice-10 port) falls back to the MRA's own name instead,
  // "Rush'n Attack (PlayChoice-10)", when that one is free.
  const taken = new Set(rows.map(row => norm(row.title)));
  return rows.map((row, i) => {
    if (proposed[i] === row.title || !norm(proposed[i]) || !identity(row) ||
      counts.get(identity(row)) !== 1) return row;
    if (names.get(norm(proposed[i])) === 1) return { ...row, title: proposed[i], mt: row.mt || row.title };
    return row.mt && !taken.has(norm(row.mt)) ? { ...row, title: row.mt } : row;
  });
}

function siteSourceRows(rows) {
  const sets = new Map(), games = new Map();
  const titles = new Map();
  const norm = value => (value || '').trim().toLowerCase();
  const game = row => {
    let title = norm(row.mt || row.title).replace(/\s*[\(\[].*$/, '').trim();
    // Regional names of the same game; family alone can also join distinct
    // games (for example Sprint 1 and Sprint 2), so it is not sufficient.
    if (title === 'kickle cubele') title = 'meikyu jima';
    return row.family && title ? norm(row.family) + ':' + title : '';
  };
  const add = (map, key, row) => {
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(row);
  };
  for (const row of rows) {
    if (row.src === 'ongo' || row.base !== 'Arcade' || row.deprecated) continue;
    if (row.sn) add(sets, norm(row.sn), row);
    if (game(row)) add(games, game(row), row);
    const title = siteGameTitle(row);
    if (title) add(titles, title, row);
  }
  const ongoHome = row => ONGO_HOME_OWNERS.includes(norm(row.repo).split('/')[0]);
  const originals = row => row.src !== 'ongo' || row.base !== 'Arcade' || ongoHome(row) ? [] : [
    ...(row.sn && sets.get(norm(row.sn)) || []),
    ...(game(row) && games.get(game(row)) || []),
    ...(titles.get(siteGameTitle(row)) || []).filter(original => siteRenamedMirror(row, original)),
  ];
  // An Ongo copy of a game another source lists gives way to that row. The
  // original takes over the copy's key, so deep links and stars made on the
  // copy still land, and says Ongo ships it too when the copy is its build.
  const heirs = new Map();
  const kept = rows.filter(row => {
    const found = originals(row);
    if (!found.length) return true;
    const heir = found.find(original => siteSameBuild(row, original)) || found[0];
    if (!heirs.has(heir)) heirs.set(heir, { keys: [], same: false });
    if (row.k) heirs.get(heir).keys.push(row.k);
    if (siteSameBuild(row, heir)) heirs.get(heir).same = true;
    return false;
  });
  const visible = kept.map(row => {
    const heir = heirs.get(row);
    if (heir && heir.keys.length) row = { ...row, siteAliases: [...(row.siteAliases || []), ...heir.keys] };
    if (heir && heir.same) row = { ...row, alsoOngo: true };
    // MeatCores ships separate two- and four-player launchers on one core.
    const players = { simpsons2p: 2, simpsons: 4 }[row.sn];
    return row.src === 'meathax' && row.core === 'Arcade-Simpsons' && players
      ? { ...row, title: `Simpsons (${players}-player)`, mt: row.mt || row.title }
      : row;
  });
  // BAZSET's English-name launcher differs from the Japan launcher only in
  // its name. Keep one launch target and expose both names on the website.
  const paths = new Set([
    '_Arcade/_BAZSET/Meikyu Jima (Japan).mra',
    '_Arcade/_BAZSET/Kickle Cubicle (English title).mra',
  ]);
  const aliases = visible.filter(row => row.src === 'bazset' && row.sn === 'kikcubic' && paths.has(row.mra));
  if (!aliases.length) return siteSingletonTitles(visible);
  const lead = aliases.find(row => row.mra.endsWith('/Meikyu Jima (Japan).mra')) || aliases[0];
  const others = aliases.filter(r => r !== lead);
  return siteSingletonTitles(visible.filter(row => !aliases.includes(row) || row === lead).map(row => row === lead
    ? { ...row, title: 'Meikyu Jima / Kickle Cubicle',
      siteAliases: [...(row.siteAliases || []), ...others.map(r => r.k).filter(Boolean),
        ...others.flatMap(r => r.siteAliases || [])],
      ...(others.some(r => r.alsoOngo) ? { alsoOngo: true } : {}) }
    : row));
}

if (typeof module !== 'undefined') module.exports = { siteSourceRows, siteGameTitle, siteRenamedMirror, siteSameBuild };
