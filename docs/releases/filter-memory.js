// Browser-local dropdown preferences. Shared views use tab-local session storage
// and cannot write preferences until the visitor explicitly reverts.
function createFilterMemory(local = () => localStorage, session = () => sessionStorage) {
  const savedKey = 'mz-filters-v1', temporaryKey = 'mz-shared-filters-v1';
  const groups = ['type', 'src', 'genre', 'year'];
  const strings = value => Array.isArray(value) && value.every(v => typeof v === 'string');
  const bound = value => value === null || (Number.isInteger(value) && value >= 1 && value <= 9999);
  const valid = (group, value) => {
    if (!value || typeof value !== 'object') return false;
    if (group === 'year') return bound(value.from) && bound(value.to);
    if (!strings(value.off)) return false;
    if (group === 'type') return strings(value.patchesOff) && strings(value.maturityOff);
    return group !== 'src' || (['all', 'public', 'early'].includes(value.access)
      && (value.maturity === undefined || ['hide', 'include', 'only'].includes(value.maturity))
      && (value.blur === undefined || typeof value.blur === 'boolean'));
  };
  const clean = values => Object.fromEntries(groups.filter(g => valid(g, values?.[g])).map(g => [g, values[g]]));
  const read = (storage, key) => {
    try { return JSON.parse(storage().getItem(key)); } catch (_) { return null; }
  };
  const write = (storage, key, value) => {
    try {
      if (value === null) storage().removeItem(key);
      else storage().setItem(key, JSON.stringify(value));
      return true;
    } catch (_) { return false; }
  };
  const stored = read(session, temporaryKey);
  let temporary = stored && typeof stored.params === 'string' && groups.every(g => valid(g, stored.filters?.[g]))
    ? { filters: clean(stored.filters), params: stored.params } : null;
  let sessionPersisted = !!temporary;
  const saved = () => clean(read(local, savedKey));
  return {
    saved,
    get temporary() { return temporary; },
    remember(group, value) {
      if (temporary || !groups.includes(group) || !valid(group, value)) return false;
      return write(local, savedKey, { ...saved(), [group]: value });
    },
    forget(group) {
      if (temporary) return false;
      const values = saved(); delete values[group];
      return write(local, savedKey, values);
    },
    save(group, value) {
      return temporary || !Object.hasOwn(saved(), group) ? true : this.remember(group, value);
    },
    startTemporary(filters, params = '') {
      temporary = { filters: clean(filters), params };
      const ok = write(session, temporaryKey, temporary);
      sessionPersisted = sessionPersisted || ok;
      return ok;
    },
    endTemporary() {
      // With storage blocked from the outset, the temporary view is memory-only
      // and can still be dismissed. A persisted snapshot must actually be removed.
      if (!write(session, temporaryKey, null) && sessionPersisted) return false;
      temporary = null;
      sessionPersisted = false;
      return true;
    },
  };
}

// Remember exclusions, so newly introduced sources are included automatically.
function rememberedFilterKeys(keys, off = []) {
  const excluded = new Set(off);
  return keys.filter(key => !excluded.has(key));
}

if (typeof module !== 'undefined') module.exports = { createFilterMemory, rememberedFilterKeys };
