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
  return rows.filter(row => row.src !== 'ongo' || row.base !== 'Arcade' ||
    !(row.sn && sets.has(norm(row.sn))) && !(game(row) && games.has(game(row))));
}

if (typeof module !== 'undefined') module.exports = { siteSourceRows };
