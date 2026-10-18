const { test } = require('node:test');
const assert = require('node:assert/strict');
const { siteSourceRows } = require('../docs/releases/source-visibility');
const row = (src, sn, title = 'Game', family = sn, extra = {}) =>
  ({ src, sn, title, family, base: 'Arcade', ...extra });

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
