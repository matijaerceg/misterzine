// Browser and Node share these definitions. Presets configure the existing table;
// section headings are presentation, never catalogue entries or same-game groups.
(function (root) {
  'use strict';
  const standard = [
    { id: 'updated', label: 'Build date', description: 'Recent builds first, grouped by update.', sort: ['updated', -1], columns: ['title', 'typesort', 'core', 'updated', 'date', 'year', 'manufacturer'], batches: true },
    { id: 'debut', label: 'MiSTer debut', description: 'New arrivals first, grouped by debut.', sort: ['date', -1], columns: ['title', 'typesort', 'core', 'src', 'date', 'year'], batches: true },
    { id: 'alphabetical', label: 'A–Z', description: 'Browse titles by letter.', sort: ['title', 1], columns: ['title', 'typesort', 'genre', 'year', 'manufacturer'] },
    { id: 'maker', label: 'Manufacturer', description: 'Games grouped by maker, then A–Z.', sort: ['manufacturer', 1], columns: ['title', 'typesort', 'genre', 'year', 'manufacturer'] },
    { id: 'year', label: 'Original year', description: 'Newest original releases first, grouped by year.', sort: ['year', -1], columns: ['title', 'typesort', 'genre', 'year', 'manufacturer'] },
    { id: 'core', label: 'Core', description: 'Each implementation under the core that runs it.', sort: ['core', 1], columns: ['title', 'core', 'src', 'updated', 'year'], sameGames: false },
    { id: 'cabinet', label: 'Cabinet setup', description: 'Rotation, video signal, players and controls together.', sort: ['title', 1], columns: ['title', 'rot', 'res', 'plr', 'ctl', 'spc'] },
  ];
  const genres = [
    ['shmups', "Shoot 'em ups", "Shoot 'em up"], ['fighting', 'Fighting', 'Fighting'],
    ['beatemups', "Beat 'em ups", "Beat 'em up"], ['runnguns', "Run 'n guns", "Run 'n gun"],
    ['platformers', 'Platformers', 'Platformer'], ['arenashooters', 'Arena shooters', 'Arena shooter'],
    ['fixedshooters', 'Fixed shooters', 'Fixed shooter'], ['railshooters', 'Rail shooters', 'Rail shooter'],
    ['lightgun', 'Light gun', 'Light gun'], ['racing', 'Racing', 'Racing'], ['maze', 'Maze', 'Maze'],
    ['puzzle', 'Puzzle', 'Puzzle'], ['sports', 'Sports', 'Sports'],
    ['tabletopquiz', 'Tabletop & quiz', 'Tabletop & quiz'], ['other', 'Other genre', 'Other'],
  ].map(([id, label, genre]) => ({ id, label, genre, description: label + ', A–Z. Selects this genre.',
    sort: ['title', 1], columns: ['title', 'core', 'src', 'year', 'manufacturer'] }));
  const sections = { none: null, letter: 'title', maker: 'manufacturer', year: 'year', core: 'core',
    updated: 'updated', date: 'date', mz: 'mz', src: 'src', genre: 'genre' };
  const sectionForSort = key => Object.keys(sections).find(mode => sections[mode] === key) || 'none';
  const presets = [...standard, ...genres].map(p => ({ batches: false, sameGames: true, ...p, section: sectionForSort(p.sort[0]) }));
  const byId = new Map(presets.map(p => [p.id, p]));
  const isDateSort = key => key === 'updated' || key === 'date' || key === 'mz';
  // The feed contains calendar dates. Take today's date from the reader's
  // calendar, then do arithmetic in UTC so daylight-saving changes cost no day.
  function localDay(now = new Date()) {
    return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())).toISOString().slice(0, 10);
  }
  const shortDate = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
  const monthYear = new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });
  function dateSections(today) {
    const dayMs = 86400000, midnight = Date.parse(today + 'T00:00:00Z');
    const now = new Date(midnight);
    const monday = midnight - ((now.getUTCDay() + 6) % 7) * dayMs;
    const lastMonday = monday - 7 * dayMs;
    const monthsStart = Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 11, 1);
    const cache = new Map();
    function describe(day) {
      const time = Date.parse(day + 'T00:00:00Z');
      if (!Number.isFinite(time) || new Date(time).toISOString().slice(0, 10) !== day)
        return { key: '', label: 'Date unknown', rank: 1 };
      let key, label;
      if (time > midnight) { key = 'future'; label = 'Future dates'; }
      else if (time >= midnight - dayMs) {
        key = day; label = (time === midnight ? 'Today' : 'Yesterday') + ' · ' + shortDate.format(time);
      } else if (time >= monday) { key = 'this-week'; label = 'Earlier this week'; }
      else if (time >= lastMonday) {
        key = 'last-week'; label = 'Last week · ' + shortDate.formatRange(lastMonday, monday - dayMs);
      } else if (time >= monthsStart) { key = day.slice(0, 7); label = monthYear.format(time); }
      else { key = day.slice(0, 4); label = key; }
      return { key, label, rank: 0 };
    }
    return { today, get(day) {
      if (!cache.has(day)) cache.set(day, describe(day));
      return cache.get(day);
    } };
  }
  const normalize = s => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const suffixes = new Set(('corporation corp co company ltd limited inc enterprises entertainment industries electronics games gmbh srl s.a japan usa u.s.a america europe').split(' '));
  // Same first-credit / corporate-suffix rule as MZ Arcade's MakerStem.
  function makerStem(raw) {
    const words = String(raw || '').split(/[/(]/, 1)[0].trim().split(/\s+/);
    while (words.length > 1 && suffixes.has(words[words.length - 1].toLowerCase().replace(/^[.,]+|[.,]+$/g, ''))) words.pop();
    return words.join(' ').replace(/[ .,]+$/g, '') || String(raw || '').trim();
  }
  function display(p) {
    return { preset: p.id, sort: [...p.sort], columns: [...p.columns], batches: p.batches,
      section: p.section, sameGames: p.sameGames };
  }
  function validate(value, allowedColumns) {
    if (!value || typeof value !== 'object' || !Array.isArray(value.columns) || !Array.isArray(value.sort)) return null;
    const columns = [...new Set(['title', ...value.columns.filter(k => allowedColumns.includes(k))])];
    const [key, dir] = value.sort;
    if (!allowedColumns.includes(key) || ![1, -1].includes(dir)) return null;
    if (!columns.includes(key)) columns.push(key);
    return { preset: byId.has(value.preset) ? value.preset : '', columns, sort: [key, dir],
      batches: value.batches === true, sameGames: value.sameGames !== false,
      section: sectionForSort(key) };
  }
  function matches(p, state) {
    return p.sort[0] === state.sort[0] && p.sort[1] === state.sort[1] && p.batches === state.batches &&
      p.section === state.section && p.sameGames === state.sameGames &&
      p.columns.length === state.columns.length && p.columns.every(k => state.columns.includes(k));
  }
  // Derived once per catalogue. Counts use the catalogue, so filtering a core
  // down to one game does not move it into Single-game cores.
  function catalogue(rows, coreLabel, sourceLabel = key => key) {
    const counts = new Map(), makers = new Map();
    for (const r of rows) {
      if (r.base === 'Arcade') { const label = coreLabel(r.core); counts.set(label, (counts.get(label) || 0) + 1); }
      const stem = makerStem(r.manufacturer), key = normalize(stem);
      if (!makers.has(key)) makers.set(key, new Map());
      const names = makers.get(key); names.set(stem, (names.get(stem) || 0) + 1);
    }
    const labels = new Map([...makers].map(([key, names]) => [key, [...names].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))[0][0]]));
    return { counts, labels, coreLabel, sourceLabel };
  }
  function sectionOf(row, mode, cat, calendar) {
    if (mode === 'none' || !cat) return null;
    if (isDateSort(mode)) return calendar.get(row[mode]);
    if (mode === 'src' || mode === 'genre') {
      const label = mode === 'src' ? cat.sourceLabel(row.src) : row.genre;
      if (label) return { key: label, label, rank: 0 };
      return { key: '', label: mode === 'src' ? 'Source unknown' : 'No genre', rank: 1 };
    }
    // An umbrella stays one game. Its best matching member supplies a maker
    // or year even where raw credits differ (e.g. Taito / Taito Corporation).
    if (row.grp && (mode === 'maker' || mode === 'year')) {
      const options = row.members.map(r => sectionOf(r, mode, cat));
      return options.sort((a, b) => a.rank - b.rank || (mode === 'year'
        ? b.key.localeCompare(a.key) : a.key.localeCompare(b.key)))[0];
    }
    if (mode === 'letter') {
      const first = normalize(row.title).charAt(0).toUpperCase();
      const label = /^[A-Z]$/.test(first) ? first : /^[0-9]$/.test(first) ? '0–9' : '#';
      return { key: label, label, rank: label === '#' ? 0 : label === '0–9' ? 1 : 2 };
    }
    if (mode === 'year') {
      const year = String(row.year || '').trim();
      return /^[1-9][0-9]{3}$/.test(year) ? { key: year, label: year, rank: 0 }
        : { key: '', label: 'Year unknown', rank: 1 };
    }
    if (mode === 'maker') {
      const key = normalize(makerStem(row.manufacturer));
      return { key, label: cat.labels.get(key) || 'Manufacturer unknown', rank: key ? 0 : 1 };
    }
    const label = cat.coreLabel(row.core);
    const rank = row.base === 'Arcade' ? !label ? 2 : cat.counts.get(label) < 2 ? 1 : 0
      : row.base === 'Console' ? 3 : row.base === 'Computer' ? 4 : 5;
    const group = [label, 'Single-game cores', 'Core unknown', 'Console cores', 'Computer cores', 'Other cores'][rank];
    return { key: group, label: group, rank };
  }
  const api = { presets, standard, genres, byId, sections, sectionForSort, isDateSort, localDay, dateSections,
    display, validate, matches, catalogue, sectionOf, makerStem };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.MZViewPresets = api;
})(typeof globalThis === 'undefined' ? this : globalThis);
