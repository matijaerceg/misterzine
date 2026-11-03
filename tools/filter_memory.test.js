const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createFilterMemory, rememberedFilterKeys } = require('../docs/releases/filter-memory');

function storage() {
  const data = new Map();
  return { getItem: k => data.get(k) ?? null, setItem: (k, v) => data.set(k, v), removeItem: k => data.delete(k) };
}
const filters = () => ({
  type: { off: ['Console'], patchesOff: ['translation'], maturityOff: ['mature'] },
  src: { off: ['coinop'], access: 'public' },
  genre: { off: ['Maze'] },
  year: { from: 1980, to: 1989 },
});

test('each dropdown opts in independently and survives a fresh page instance', () => {
  const local = storage(), session = storage();
  let memory = createFilterMemory(() => local, () => session);
  const values = filters();
  memory.save('src', values.src);
  assert.deepEqual(memory.saved(), {});
  for (const group of Object.keys(values)) assert.equal(memory.remember(group, values[group]), true);
  memory = createFilterMemory(() => local, () => session);
  assert.deepEqual(memory.saved(), values);
  memory.forget('type');
  assert.deepEqual(Object.keys(memory.saved()).sort(), ['genre', 'src', 'year']);
  memory.save('src', { off: [], access: 'all' });
  assert.deepEqual(memory.saved().src, { off: [], access: 'all' });
  assert.deepEqual(memory.saved().year, values.year);
});

test('a shared session blocks every preference write, including after refresh, until revert', () => {
  const local = storage(), session = storage();
  let memory = createFilterMemory(() => local, () => session);
  const saved = filters();
  for (const group of Object.keys(saved)) memory.remember(group, saved[group]);
  const temporary = filters(); temporary.src = { off: ['jtbindb'], access: 'early' };
  memory.startTemporary(temporary, 'q=1942&s=title');
  for (let refresh = 0; refresh < 2; refresh++) {
    memory = createFilterMemory(() => local, () => session);
    assert.deepEqual(memory.temporary, { filters: temporary, params: 'q=1942&s=title' });
    assert.equal(memory.remember('src', temporary.src), false);
    assert.equal(memory.forget('src'), false);
    memory.save('src', temporary.src);
    assert.deepEqual(memory.saved(), saved);
  }
  memory.endTemporary();
  assert.equal(createFilterMemory(() => local, () => session).temporary, null);
  memory.save('src', temporary.src);
  assert.deepEqual(memory.saved().src, temporary.src);
});

test('shared sessions are tab-local and preferences are browser-local', () => {
  const local = storage(), firstTab = storage(), secondTab = storage();
  const first = createFilterMemory(() => local, () => firstTab);
  first.remember('year', filters().year);
  first.startTemporary(filters());
  const second = createFilterMemory(() => local, () => secondTab);
  assert.equal(second.temporary, null);
  assert.deepEqual(second.saved().year, filters().year);
  assert.deepEqual(createFilterMemory(() => storage(), () => storage()).saved(), {});
});

test('excluded sources stay excluded and new sources are selected, even after selecting none', () => {
  assert.deepEqual(rememberedFilterKeys(['known', 'excluded', 'new'], ['excluded']), ['known', 'new']);
  assert.deepEqual(rememberedFilterKeys(['known', 'new'], ['known', 'retired']), ['new']);
  assert.deepEqual(rememberedFilterKeys(['returned', 'new'], ['returned']), ['new']);
});

test('malformed and blocked browser storage cannot break the filters', () => {
  const local = storage(), session = storage();
  local.setItem('mz-filters-v1', '{broken');
  session.setItem('mz-shared-filters-v1', '{}');
  const memory = createFilterMemory(() => local, () => session);
  assert.deepEqual(memory.saved(), {});
  assert.equal(memory.temporary, null);
  local.setItem('mz-filters-v1', JSON.stringify({ src: { off: 'bad', access: 'all' }, year: { from: '1980', to: null }, genre: filters().genre }));
  assert.deepEqual(memory.saved(), { genre: filters().genre });
  const denied = () => { throw new Error('Storage denied'); };
  const blocked = createFilterMemory(denied, denied);
  assert.deepEqual(blocked.saved(), {});
  assert.equal(blocked.remember('src', filters().src), false);
  blocked.startTemporary(filters());
  assert.deepEqual(blocked.temporary.filters, filters());
  assert.equal(blocked.remember('src', filters().src), false);
  assert.equal(blocked.endTemporary(), true);
  assert.equal(blocked.temporary, null);
});
