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

function siteSourceRows(rows) {
  const sets = new Set(), games = new Set();
  const titles = new Map();
  const norm = value => (value || '').trim().toLowerCase();
  const game = row => {
    let title = norm(row.mt || row.title).replace(/\s*[\(\[].*$/, '').trim();
    // Regional names of the same game; family alone can also join distinct
    // games (for example Sprint 1 and Sprint 2), so it is not sufficient.
    if (title === 'kickle cubele') title = 'meikyu jima';
    return row.family && title ? norm(row.family) + ':' + title : '';
  };
  for (const row of rows) {
    if (row.src === 'ongo' || row.base !== 'Arcade' || row.deprecated) continue;
    if (row.sn) sets.add(norm(row.sn));
    if (game(row)) games.add(game(row));
    const title = siteGameTitle(row);
    if (title) {
      if (!titles.has(title)) titles.set(title, []);
      titles.get(title).push(row);
    }
  }
  const visible = rows.filter(row => row.src !== 'ongo' || row.base !== 'Arcade' ||
    !(row.sn && sets.has(norm(row.sn))) && !(game(row) && games.has(game(row))) &&
    !(titles.get(siteGameTitle(row)) || []).some(original => siteRenamedMirror(row, original)))
    .map(row => {
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
  if (!aliases.length) return visible;
  const lead = aliases.find(row => row.mra.endsWith('/Meikyu Jima (Japan).mra')) || aliases[0];
  return visible.filter(row => !aliases.includes(row) || row === lead).map(row => row === lead
    ? { ...row, title: 'Meikyu Jima / Kickle Cubicle', siteAliases: aliases.filter(r => r !== lead).map(r => r.k).filter(Boolean) }
    : row);
}

if (typeof module !== 'undefined') module.exports = { siteSourceRows, siteGameTitle, siteRenamedMirror };
