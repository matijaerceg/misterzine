// Read-only audit: node tools/audit_ongo.js [catalogue.json]
// Candidates are evidence to review, never instructions to hide a row.
const fs = require('node:fs');
const path = require('node:path');
const { siteSourceRows, siteGameTitle, siteRenamedMirror } = require('../docs/releases/source-visibility');
const rows = JSON.parse(fs.readFileSync(process.argv[2] || path.join(__dirname, '../docs/releases/data.json'), 'utf8'));
const originals = rows.filter(r => r.src !== 'ongo' && r.base === 'Arcade' && !r.deprecated);
const ongo = rows.filter(r => r.src === 'ongo' && r.base === 'Arcade');
const visible = new Set(siteSourceRows(rows).map(r => r.k));
const evidence = (r, o) => ({
  original: o.k,
  sameTitle: !!siteGameTitle(r) && siteGameTitle(r) === siteGameTitle(o),
  sameBuild: !!r.bh && r.bh.toLowerCase() === (o.bh || '').toLowerCase(),
  sourceSuffix: !!o.sn && r.sn === o.sn + '_' + o.src,
  sameCore: !!r.core && r.core.toLowerCase() === (o.core || '').toLowerCase(),
});
const renamed = ongo.flatMap(r => {
  const matches = originals.filter(o => siteRenamedMirror(r, o) && r.sn !== o.sn);
  return matches.length ? [{ key: r.k, matches: matches.map(o => evidence(r, o)) }] : [];
});
const review = ongo.filter(r => visible.has(r.k)).flatMap(r => {
  const matches = originals.map(o => evidence(r, o)).filter(e => e.sameTitle || e.sameBuild || e.sourceSuffix || e.sameCore);
  return matches.length ? [{ key: r.k, title: r.title, matches }] : [];
});
console.log(JSON.stringify({ total: ongo.length, hidden: ongo.filter(r => !visible.has(r.k)).length,
  visible: ongo.filter(r => visible.has(r.k)).length, renamed, review }, null, 2));
