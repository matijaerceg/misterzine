// Website-only source preference. Keep the shared app catalogue intact.
function siteSourceRows(rows) {
  const sets = new Set(), games = new Set();
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
  }
  const visible = rows.filter(row => row.src !== 'ongo' || row.base !== 'Arcade' ||
    !(row.sn && sets.has(norm(row.sn))) && !(game(row) && games.has(game(row))));
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

if (typeof module !== 'undefined') module.exports = { siteSourceRows };
