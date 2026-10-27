// Collections select the catalogue; the Tracker's filters work within it.
// Local recovery copies are read only after the service confirms list ownership.
window.MZLists = (() => {
  const params = new URLSearchParams(location.search);
  const KEY = 'mz-last-collection', INTRO = 'mz-lists-intro';
  const validID = id => /^[0-9A-HJKMNP-TV-Z]{12}$/.test(id || '');
  const editing = params.has('editList');
  let id = (params.get(editing ? 'editList' : 'list') || '').trim().toUpperCase();
  let mode = editing || params.has('list') ? 'list' : params.get('collection') === 'favorites' ? 'favorites' : 'all';
  if (!location.search && !location.hash) {
    try {
      const last = JSON.parse(localStorage.getItem(KEY));
      if (last && last.kind === 'favorites') mode = 'favorites';
      else if (last && last.kind === 'list' && validID(last.id)) { mode = 'list'; id = last.id; }
    } catch (_) {}
  }
  let hooks, list = null, selected = new Set(), selectedOnly = false, original = '';
  let dirty = false, busy = false, started = false, owner = false, following = false;
  let collections = { owned: [], following: [] }, profile = null, profileLoaded = false;
  let loadVersion = 0, collectionsVersion = 0, sessionVersion = 0, followBusy = false, createBusy = false;
  let entryRow = null, entryVersion = 0, entryBusy = false, entryCreateBlocked = false;
  let draftRecord = null, draftAvailable = true;
  let undo = [], redo = [], present = '', memberLimit = 200, memberSignature = '', catalogue = null, catalogueByKey = new Map();
  let marked = new Set(), memberAnchor = null, shownMembers = [], addedKeys = new Set(), pendingNavigation = null;
  let copySource = null;
  let editorPane = 'catalogue', returnPane = 'catalogue', detailFocus = null;
  function setEditorPane(pane) {
    editorPane = pane;
    document.body.classList.toggle('cl-mobile-list', pane === 'list');
    document.body.classList.toggle('cl-detail-view', pane === 'details');
    $('clshowcatalogue').setAttribute('aria-pressed', String(pane === 'catalogue'));
    $('clshowlist').setAttribute('aria-pressed', String(pane === 'list' || pane === 'catalogue' && !$('clshowcatalogue').getClientRects().length));
    $('clshowdetails').setAttribute('aria-pressed', String(pane === 'details'));
  }
  function detailsOpened() {
    if (!editing || mode !== 'list' || !started) return;
    if (editorPane !== 'details') { returnPane = editorPane; detailFocus = document.activeElement; }
    document.body.classList.add('cl-has-details');
    $('clshowdetails').hidden = false;
    setEditorPane('details');
    const hint = $('panel').querySelector('.hint');
    if (hint) hint.textContent = 'Close game details with × or Esc. Your list edits are kept.';
    // On phones the catalogue disappears; move focus out of that hidden pane.
    if (!$('clcatalogue').getClientRects().length) $('clshowdetails').focus({preventScroll: true});
  }
  function detailsClosed() {
    if (!editing || mode !== 'list' || !started) return;
    const restore = $('panel').contains(document.activeElement);
    setEditorPane(returnPane);
    if (restore) {
      const target = detailFocus?.isConnected && detailFocus.matches('button,input,a[href],[tabindex]') && detailFocus.getClientRects().length ? detailFocus : $('clshowcatalogue').getClientRects().length ? $('clshowcatalogue') : $('q');
      target.focus({preventScroll: true});
    }
  }
  function resetHistory() { undo = []; redo = []; present = snapshot(); }
  function travelHistory(back) {
    if (busy || !owner || !editing) return;
    const from = back ? undo : redo, to = back ? redo : undo;
    if (!from.length) return;
    to.push(snapshot());
    const value = from.pop(), [title, description, keys] = JSON.parse(value);
    list = {...list, title, description}; selected = new Set(keys); present = value;
    changed(false);
  }
  const draftKey = () => 'mz-list-draft:' + id;
  function draftNote() {
    if (!$('cldraftnote')) return;
    $('cldraftnote').hidden = !editing || !owner || !dirty;
    $('cldraftnote').textContent = draftAvailable
      ? 'Recovery copy kept on this device.'
      : 'This browser could not keep a recovery copy. Keep this tab open and save your changes before leaving.';
    $('cldiscard').hidden = !editing || !owner;
    $('cldiscard').disabled = busy || !dirty;
  }
  function clearDraft() {
    try { if (draftRecord && localStorage.getItem(draftKey()) === draftRecord) localStorage.removeItem(draftKey()); }
    catch (_) { draftAvailable = false; }
    draftRecord = null;
  }
  function keepDraft() {
    if (!editing || !owner || !list) return;
    if (!dirty) { clearDraft(); draftNote(); return; }
    const value = JSON.stringify({schema: 1, id, version: list.version, title: list.title,
      description: list.description, keys: [...selected], at: Date.now()});
    try { localStorage.setItem(draftKey(), value); draftRecord = value; draftAvailable = true; }
    catch (_) { draftAvailable = false; }
    draftNote();
  }
  function restoreDraft() {
    if (!editing || !owner) return false;
    try {
      const raw = localStorage.getItem(draftKey()), value = JSON.parse(raw);
      if (!value || value.schema !== 1 || value.id !== id || !Number.isSafeInteger(value.version) || value.version < 1 ||
        typeof value.title !== 'string' || !value.title.trim() || value.title.length > 100 ||
        typeof value.description !== 'string' || value.description.length > 2000 ||
        !Array.isArray(value.keys) || value.keys.length > 5000 ||
        !value.keys.every(key => typeof key === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(key))) return false;
      draftRecord = raw;
      const recovered = JSON.stringify([value.title, value.description, [...new Set(value.keys)]]);
      if (recovered === original) { clearDraft(); return false; }
      list = {...list, title: value.title, description: value.description, version: value.version};
      selected = new Set(value.keys); dirty = true; draftAvailable = true;
      return true;
    } catch (_) { draftAvailable = false; return false; }
  }
  async function discardDraft() {
    if (busy || !owner || !dirty || !confirm('Discard your unsaved changes and load the latest saved list?')) return;
    const session = sessionVersion;
    busy = true; redraw();
    try {
      const latest = await request('/lists/' + id, null, true);
      if (session !== sessionVersion) return;
      clearDraft(); list = latest; selected = new Set(latest.keys); original = snapshot(); dirty = false; resetHistory();
      $('cllatest').hidden = true; status('Unsaved changes discarded. Showing the latest saved list.');
    } catch (err) { if (session === sessionVersion) { status(errorText(err), true); $('clsignin').hidden = err.status !== 401; } }
    finally { if (session === sessionVersion) { busy = false; redraw(); } }
  }
  const $ = id => document.getElementById(id);
  const safe = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const visibility = () => list.visibility || (list.published ? 'unlisted' : 'private');
  const visibilityLabel = value => ({private: 'Private', unlisted: 'Unlisted', public: 'Public'})[value];
  const listPath = () => '/releases/?list=' + encodeURIComponent(id);
  const editPath = () => '/releases/?editList=' + encodeURIComponent(id);
  const signIn = path => '/account/?r=' + encodeURIComponent(path);
  const snapshot = () => JSON.stringify([list.title, list.description, [...selected]]);
  const missing = () => { const known = new Set(hooks.rows().map(d => d.k)); return [...selected].filter(k => !known.has(k)); };
  function remember() {
    try { localStorage.setItem(KEY, JSON.stringify(mode === 'list' ? {kind: mode, id} : {kind: mode})); } catch (_) {}
  }
  function notice(text) { $('collection-notice').textContent = text; $('collection-notice').hidden = !text; }
  function status(text, error = false) { $('clstatus').textContent = text; $('clstatus').classList.toggle('error', error); }
  function redraw() { hooks.repaint(); sync(); }
  function changed(record = true) {
    const previousKeys = new Set(present ? JSON.parse(present)[2] : []);
    addedKeys = new Set([...selected].filter(key => !previousKeys.has(key)));
    const next = snapshot();
    if (record && next !== present) {
      if (present) undo.push(present);
      if (undo.length > 100) undo.shift();
      redo = []; present = next;
    }
    dirty = next !== original; keepDraft();
    // The state beside the title already says Saved / Unsaved changes.
    status(dirty && !draftAvailable ? 'Unsaved changes. Save before leaving; local recovery is unavailable.' : '');
    redraw();
  }
  function syncMembers() {
    if (!$('clworkspace')) return;
    const editor = editing && mode === 'list';
    const active = editing && owner && !!list;
    document.body.classList.toggle('cl-editor', editor);
    if (!editor && $('panel').parentElement === $('clworkspace')) {
      document.body.append($('panel'));
      document.body.classList.remove('cl-detail-view', 'cl-mobile-list', 'cl-has-details');
      document.querySelector('.tablezone').prepend(document.querySelector('.jumps'));
    }
    $('clworkspace').hidden = !editor;
    $('clmobiletabs').hidden = !editor;
    $('clbulkbar').hidden = !active;
    $('clmembers').hidden = !active;
    $('clmembertools').hidden = !active;
    $('clmembersearch').disabled = !active;
    $('clmembersmore').hidden = true;
    if (!active) {
      memberSignature = ''; $('clmembercount').textContent = 'Your list'; $('clshowlist').textContent = 'Your list';
      $('clmembers').replaceChildren(); $('clmemberempty').hidden = true; return;
    }
    $('clmembercount').textContent = 'In this list (' + selected.size + ')';
    $('clshowlist').textContent = 'Your list (' + selected.size + ')';
    const rows = hooks.catalogue();
    if (catalogue !== rows) { catalogue = rows; catalogueByKey = new Map(rows.map(row => [row.k, row])); memberSignature = ''; }
    const query = $('clmembersearch').value.trim().toLocaleLowerCase();
    marked = new Set([...marked].filter(key => selected.has(key)));
    $('clmembertools').hidden = !active;
    $('clmarkcount').textContent = marked.size + ' selected';
    for (const name of ['clmarkcount', 'clmarkremove', 'clmarkclear']) $(name).hidden = !marked.size;
    $('clmarkremove').disabled = busy || !marked.size;
    $('clmarkclear').disabled = busy || !marked.size;
    $('clmarkall').disabled = busy;
    $('clclearsearch').hidden = !query;
    $('clshowadded').hidden = !addedKeys.size;
    const signature = JSON.stringify([[...selected], [...marked], [...addedKeys], query, memberLimit, busy]);
    if (signature === memberSignature) {
      $('clmembersmore').hidden = Number($('clmembersmore').dataset.remaining || 0) === 0;
      return;
    }
    memberSignature = signature;
    const entries = [...selected].map(key => ({key, row: catalogueByKey.get(key)}))
      .filter(({key, row}) => !query || [row?.title || key, row?.core, row?.src && hooks.source(row.src)].join(' ').toLocaleLowerCase().includes(query))
      .sort((a, b) => (a.row?.title || a.key).localeCompare(b.row?.title || b.key, undefined, {numeric: true, sensitivity: 'base'}) || a.key.localeCompare(b.key));
    shownMembers = entries.map(entry => entry.key);
    $('clmarkall').disabled = busy || !entries.length;
    const scroll = $('clmembers').parentElement, scrollTop = scroll.scrollTop;
    const focus = document.activeElement, focusedMark = focus?.dataset.clmark, focusedKey = focus?.dataset.clremove;
    const oldIndex = focusedKey ? [...$('clmembers').querySelectorAll('button')].indexOf(focus) : -1;
    const fragment = document.createDocumentFragment();
    for (const {key, row} of entries.slice(0, memberLimit)) {
      const li = document.createElement('li'), text = document.createElement('div'), title = document.createElement('strong'), detail = document.createElement('small'), remove = document.createElement('button');
      const hit = document.createElement('label'), check = document.createElement('input');
      hit.className = 'clmarkhit'; check.type = 'checkbox'; check.dataset.clmark = key;
      check.checked = marked.has(key); check.disabled = busy;
      check.setAttribute('aria-label', 'Select ' + (row?.title || key) + ' for removal' + (row?.core ? ' (' + row.core + ')' : ''));
      hit.append(check);
      li.className = 'clmember'; li.classList.toggle('clnewmember', addedKeys.has(key)); title.textContent = row?.title || 'Unavailable entry';
      detail.textContent = row ? [row.core, row.src && hooks.source(row.src)].filter(Boolean).join(' · ') : key + ' · No longer in the catalogue';
      text.append(title, detail); remove.type = 'button'; remove.textContent = 'Remove'; remove.dataset.clremove = key;
      remove.setAttribute('aria-label', 'Remove ' + (row?.title || key) + (row && detail.textContent ? ' (' + detail.textContent + ')' : '') + ' from this list'); remove.disabled = busy;
      li.append(hit, text, remove); fragment.append(li);
    }
    $('clmembers').replaceChildren(fragment);
    scroll.scrollTop = scrollTop;
    if (focusedMark) [...$('clmembers').querySelectorAll('[data-clmark]')].find(el => el.dataset.clmark === focusedMark)?.focus({preventScroll: true});
    $('clmemberempty').hidden = entries.length > 0;
    $('clmemberempty').textContent = selected.size ? 'No list entries match this search.' : 'Your list is empty. Tick games in the catalogue to add them here.';
    const remaining = Math.max(0, entries.length - memberLimit);
    $('clmembersmore').dataset.remaining = remaining;
    $('clmembersmore').hidden = !remaining;
    $('clmembersmore').textContent = 'Show more (' + remaining + ' remaining)';
    if (oldIndex >= 0) {
      const buttons = [...$('clmembers').querySelectorAll('button')];
      (buttons.find(button => button.dataset.clremove === focusedKey) || buttons[Math.min(oldIndex, buttons.length - 1)] || $('clmembers').parentElement).focus({preventScroll: true});
    }
  }
  function fail(message, status, code) { const error = new Error(message); error.status = status; error.code = code; throw error; }
  async function request(path, options, auth = false) {
    const token = hooks.token();
    if (auth && !token) fail('Sign in to continue. Any unsaved changes are still here.', 401);
    const res = await fetch(hooks.api() + path, {...options, cache: 'no-store', headers: {
      ...(auth ? {Authorization: 'Bearer ' + token} : {}),
      ...(options && options.body ? {'Content-Type': 'application/json'} : {})
    }});
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const text = res.status === 401 ? 'Your sign-in has expired. Sign in again to continue.'
        : data.error === 'profile_required' ? 'Choose a public display name before sharing this list.'
        : res.status === 404 ? 'This list is no longer available.'
        : res.status === 409 ? 'This list changed elsewhere. Your edits are still here; review the latest saved version before continuing.'
        : 'The list service could not complete that request. Please try again.';
      fail(text, res.status, data.error);
    }
    return res.status === 204 ? null : res.json();
  }
  function errorText(err) { return err instanceof TypeError ? 'Could not reach the list service. ' + (editing && dirty ? 'Your unsaved changes are still here; please try again.' : 'Check your connection and try again.') : err.message; }
  function updatePicker() {
    if (!started) return;
    const picker = $('collection-select'); picker.replaceChildren(new Option('Your lists', ''));
    for (const [label, rows] of [['Your lists', collections.owned], ['Following', collections.following]]) {
      if (!rows.length) continue;
      const group = document.createElement('optgroup'); group.label = label;
      for (const row of rows) {
        const option = new Option(row.unavailable ? (row.title || 'Unavailable list') + ' (unavailable)' : row.title, row.id);
        option.disabled = !!row.unavailable; group.append(option);
      }
      picker.append(group);
    }
    const showCurrent = list && (owner || !editing && visibility() !== 'private');
    if (mode === 'list' && showCurrent && ![...picker.options].some(o => o.value === id)) picker.append(new Option(list.title, id));
    picker.append(new Option(hooks.token() ? 'Manage your lists...' : 'Sign in for your lists...', 'manage'));
    picker.value = mode === 'list' && showCurrent ? id : '';
    picker.classList.toggle('active', mode === 'list');
  }
  async function refreshCollections() {
    const generation = ++collectionsVersion, token = hooks.token();
    if (!token) { collections = {owned: [], following: []}; following = false; updatePicker(); sync(); return; }
    try {
      const value = await request('/collections', null, true);
      if (generation !== collectionsVersion || token !== hooks.token()) return;
      collections = value;
      following = collections.following.some(row => row.id === id && !row.unavailable);
      updatePicker(); sync();
    } catch (err) {
      if (generation !== collectionsVersion || token !== hooks.token()) return;
      collections = {owned: [], following: []}; updatePicker();
      notice(err.status === 401 ? 'Sign in again to see your saved lists. You can still browse public collections.' : 'Your saved lists could not be loaded. Browse lists is still available.');
    }
  }
  function sync() {
    if (!started) return;
    syncMembers();
    $('collection-all').setAttribute('aria-current', mode === 'all' ? 'page' : 'false');
    $('collection-favorites').setAttribute('aria-current', mode === 'favorites' ? 'page' : 'false');
    if (!list || editing && !owner) {
      $('clname').textContent = editing ? 'Edit list' : 'Loading collection...';
      $('clstate').textContent = ''; $('clattribution').replaceChildren();
      $('cldescriptionview').textContent = '';
      $('clnote').textContent = '';
      for (const element of ['cldescriptionfold', 'cledit', 'clsecondary', 'cldone', 'cleditlink', 'cllinkcopy', 'clcopylist', 'clfollow', 'clmissing', 'cllatest', 'cldraftnote', 'cldiscard', 'clempty']) $(element).hidden = true;
      return;
    }
    $('clname').textContent = list.title;
    $('clstate').textContent = visibilityLabel(visibility()) + (editing ? dirty ? ' · Unsaved changes' : ' · Saved' : '');
    $('cledit').hidden = !editing || !owner; $('cldone').hidden = !editing;
    $('clsecondary').hidden = !editing || !owner;
    $('clmoresummary').textContent = editing ? 'More' : 'About this list';
    draftNote();
    $('cldone').href = listPath();
    $('cldone').textContent = dirty ? 'Save & done' : 'Done editing';
    $('cldone').setAttribute('aria-disabled', String(busy));
    $('cleditlink').hidden = editing || !owner; $('cleditlink').href = editPath();
    $('cllinkcopy').hidden = visibility() === 'private';
    $('clcopylist').hidden = editing;
    $('clfollow').hidden = editing || owner || visibility() === 'private';
    $('clfollow').disabled = followBusy;
    $('clfollow').textContent = following ? 'Unfollow' : 'Follow list';
    $('clfollow').setAttribute('aria-pressed', String(following));
    $('clselected').textContent = selectedOnly ? 'Show all games' : 'Show only list entries';
    $('clselected').setAttribute('aria-pressed', selectedOnly);
    $('clsave').textContent = 'Save changes';
    $('clsave').disabled = busy || !dirty;
    $('clpublish').textContent = 'Visibility…';
    const attribution = $('clattribution'); attribution.replaceChildren();
    const name = list.curator && list.curator.name || list.byline;
    if (name) {
      attribution.append(document.createTextNode('By '));
      if (list.curator && list.curator.id) {
        const link = document.createElement('a'); link.textContent = name; link.href = '../lists/?curator=' + encodeURIComponent(list.curator.id); attribution.append(link);
      } else attribution.append(document.createTextNode(name));
      attribution.append(document.createTextNode(' · '));
    }
    const followers = list.follower_count || 0;
    attribution.append(document.createTextNode(selected.size + (selected.size === 1 ? ' entry' : ' entries') + ' · ' + followers + (followers === 1 ? ' follower' : ' followers') + ' · Updated ' + new Date(list.updated_at).toLocaleDateString()));
    $('cldescriptionfold').hidden = !list.description;
    $('cldescriptionview').textContent = list.description;
    $('clnote').textContent = editing
      ? 'Tick games in the catalogue to add them. Your list stays visible here as you search and filter. ' + (visibility() === 'private' ? 'Your list is private unless you change its visibility.' : 'Saving updates the same shared list.')
      : !selected.size ? (owner ? 'This list is empty. Choose Edit list to start adding entries.' : 'This list has no entries yet. Its owner can add them later.')
      : !hooks.visible().length ? 'No saved entries are visible with your current filters and visibility settings. Try clearing filters or review entries not shown below.'
      : 'Search and filters apply within this collection.';
    const n = missing().length;
    $('clmissing').hidden = !n; $('clmissing').disabled = busy;
    $('clmissing').textContent = n + (n === 1 ? ' saved entry is' : ' saved entries are') + ' not shown in the Tracker · Review';
    for (const button of document.querySelectorAll('#cledit button, #clsecondary button')) if (button.id !== 'clsave') button.disabled = busy;
    const matching = hooks.visible();
    $('clempty').hidden = editing || matching.length > 0;
    $('clempty').textContent = !selected.size
      ? (owner ? 'This list is empty. Choose Edit list to start adding entries.' : 'This list has no entries yet. Its owner can add them later.')
      : 'No saved entries are visible with your current filters and visibility settings. Try clearing filters or review entries not shown.';
    $('clundo').hidden = !editing || !owner; $('clredo').hidden = !editing || !owner;
    $('clundo').disabled = busy || !undo.length; $('clredo').disabled = busy || !redo.length;
    $('cldiscard').disabled = busy || !dirty;
    const additions = matching.filter(d => !selected.has(d.k)).length;
    $('cladd').textContent = 'Add ' + additions + ' matching…';
    $('cladd').disabled = busy || !additions;
    $('clremove').disabled = busy || !matching.some(d => selected.has(d.k));
    $('clremove').textContent = 'Remove ' + matching.filter(d => selected.has(d.k)).length + ' matching…';
  }
  function checkbox(d) {
    if (!editing || !list || !owner || d.grp || !d.k) return '';
    return '<label class="clpickhit"><input class="clpick" type="checkbox" data-list-key="' + safe(d.k) + '" aria-label="Include ' + safe(d.title) + (d.src ? ' (' + safe(hooks.source(d.src)) + ')' : '') + ' in this list"' + (selected.has(d.k) ? ' checked' : '') + (busy ? ' disabled' : '') + '></label>';
  }
  function matches(d) {
    if (mode === 'all') return true;
    if (mode === 'favorites') return !!hooks && hooks.isFavorite(d);
    if (editing && !owner) return false;
    if (!list) return false;
    return editing && !selectedOnly || selected.has(d.k);
  }
  function toggle(key, checked) {
    if (!editing || !owner || !list || busy) return;
    if (checked && selected.size >= 5000) { status('A list can hold up to 5,000 entries.', true); redraw(); return; }
    if (checked) selected.add(key); else selected.delete(key);
    changed();
  }
  function unavailable(message) {
    list = null; selected.clear(); mode = 'all'; id = ''; owner = false; dirty = false;
    $('clbar').hidden = true; remember(); updatePicker();
    history.replaceState(history.state, '', '/releases/?collection=all');
    hooks.closePanel(); notice(message + ' Showing all entries.'); redraw();
  }
  async function load() {
    if (busy) return;
    const generation = ++loadVersion;
    busy = true; $('clretry').disabled = true; status('Loading collection...');
    try {
      let value, isOwner = false;
      if (hooks.token()) {
        try { value = await request('/lists/' + id, null, true); isOwner = true; }
        catch (err) { if (editing || ![401,404].includes(err.status)) throw err; }
      } else if (editing) fail('Sign in to edit your list.', 401);
      if (!value) value = await request('/public/lists/' + id);
      if (generation !== loadVersion) return;
      const retained = editing && list && dirty;
      owner = isOwner;
      if (!retained) { list = value; selected = new Set(value.keys); dirty = false; original = snapshot(); resetHistory(); }
      const recovered = !retained && restoreDraft();
      if (recovered) { undo.push(present); present = snapshot(); }
      $('clretry').hidden = true; $('clsignin').hidden = true;
      status(recovered ? 'Recovered your unsaved changes from this device. Review them, then save when ready.' : retained ? 'Your unsaved edits are still here.' : '');
      if ((retained || recovered) && list.version !== value.version) {
        status('This list changed elsewhere. Your edits are still here; review the latest saved version before saving.', true);
        $('cllatest').hidden = false;
      }
      remember(); updatePicker();
    } catch (err) {
      if (generation !== loadVersion) return;
      if (err.status === 404 && !editing) unavailable('That collection was deleted, made private, or is not available to this account.');
      else {
        status(errorText(err), true); $('clretry').hidden = false; $('clsignin').hidden = err.status !== 401;
      }
    } finally {
      if (generation === loadVersion) { busy = false; $('clretry').disabled = false; redraw(); }
    }
    if (generation === loadVersion && list && !editing && params.get('follow') === '1') {
      params.delete('follow'); const url = new URL(location.href); url.searchParams.delete('follow'); history.replaceState(history.state, '', url);
      if (hooks.token() && !owner) await setFollowing(true);
      else if (!owner) status('Sign in to follow this collection.');
    }
    if (generation === loadVersion) resumeEntry();
  }
  async function save(value) {
    if (busy || !list || !owner) return false;
    const session = sessionVersion;
    busy = true; redraw(); status('Saving...');
    try {
      const updated = await request('/lists/' + id, {method: 'PUT', body: JSON.stringify({
        title: list.title, description: list.description, keys: [...selected], visibility: value, version: list.version
      })}, true);
      if (session !== sessionVersion) return false;
      list = updated; selected = new Set(updated.keys); dirty = false; original = snapshot();
      clearDraft(); resetHistory();
      status(value === 'private' ? 'Saved privately.' : value === 'unlisted' ? 'Saved. Anyone with your link can view and follow this list.' : 'Saved. Your list now appears in Browse lists and on your curator page.');
      $('clsignin').hidden = true; $('cllatest').hidden = true;
      refreshCollections(); return true;
    } catch (err) {
      if (session !== sessionVersion) return false;
      status(errorText(err), true); $('clsignin').hidden = err.status !== 401;
      $('cllatest').hidden = err.status !== 409 || err.code === 'profile_required';
      if ($('clconfirm').open) $('clvisibilitystatus').textContent = errorText(err);
      return false;
    } finally { if (session === sessionVersion) { busy = false; redraw(); } }
  }
  function visibilityInputs() {
    const value = $('clvisibilityform').elements.visibility.value;
    const needsName = value !== 'private';
    $('clprofilefields').hidden = !needsName || !!profile;
    $('clpublicname').required = needsName && !profile;
    $('clprofilesaved').hidden = !needsName || !profile;
    $('clprofilesaved').textContent = profile ? 'Credited as ' + profile.display_name + '. You can change this on your account page.' : '';
    $('clconfirmyes').disabled = needsName && !profileLoaded;
    $('clconfirmyes').textContent = value === 'public' ? 'Save as public' : value === 'unlisted' ? 'Save as unlisted' : 'Save privately';
  }
  async function showSharing() {
    if (busy || !owner || !list) return;
    $('clvisibilityform').elements.visibility.value = visibility();
    $('clvisibilitystatus').textContent = '';
    $('clconfirm').showModal();
    profileLoaded = false; visibilityInputs();
    const session = sessionVersion;
    try {
      const me = await request('/me', null, true);
      if (session !== sessionVersion) return;
      profile = me.profile; profileLoaded = true; visibilityInputs();
    } catch (err) {
      if (session !== sessionVersion) return;
      $('clvisibilitystatus').textContent = 'Could not load your public name. Close and reopen Sharing to retry. ' + errorText(err);
    }
  }
  async function submitSharing(event) {
    event.preventDefault();
    if (busy || !owner) return;
    const value = $('clvisibilityform').elements.visibility.value;
    const form = $('clvisibilityform'), session = sessionVersion;
    const controls = [...form.querySelectorAll('button,input')];
    controls.forEach(el => el.disabled = true);
    try {
      if (value !== 'private' && !profile) {
        const name = $('clpublicname').value.trim();
        if (!name) { $('clvisibilitystatus').textContent = 'Enter the public name you want people to see.'; return; }
        if (!profileLoaded) return;
        const savedProfile = await request('/me/profile', {method: 'PUT', body: JSON.stringify({display_name: name})}, true);
        if (session !== sessionVersion) return;
        profile = savedProfile;
      }
      if (await save(value)) $('clconfirm').close();
    } catch (err) { if (session === sessionVersion) $('clvisibilitystatus').textContent = errorText(err); }
    finally { if (session === sessionVersion) { controls.forEach(el => el.disabled = false); visibilityInputs(); } }
  }
  async function setFollowing(on) {
    if (!list || owner || followBusy) return;
    if (!hooks.token()) { location.assign(signIn(listPath() + '&follow=1')); return; }
    const session = sessionVersion;
    followBusy = true; sync();
    try {
      await request('/following/' + id, {method: on ? 'PUT' : 'DELETE'}, true);
      if (session !== sessionVersion) return;
      following = on; status(on ? "Following. This collection is now in Your lists and will use the owner's latest saved entries." : 'Unfollowed. This collection has been removed from Your lists.');
      await refreshCollections();
      // Refresh the aggregate without replacing the current selection while browsing.
      try {
        const latest = await request('/public/lists/' + id);
        if (session === sessionVersion && list) list.follower_count = latest.follower_count;
      } catch (_) { /* The follow succeeded; an optional count refresh must not report failure. */ }
    } catch (err) {
      if (session !== sessionVersion) return;
      status(errorText(err), true);
      if (err.status === 401) { $('clsignin').href = signIn(listPath() + '&follow=1'); $('clsignin').hidden = false; }
    } finally { if (session === sessionVersion) { followBusy = false; sync(); } }
  }
  function showDetails() {
    if (!list || busy) return;
    $('cltitle').value = list.title; $('cldescription').value = list.description; $('cldetails').showModal();
  }
  function showMissing() {
    if (busy || !list) return;
    $('clmissingrows').replaceChildren();
    for (const key of missing()) {
      const row = hooks.original(key), li = document.createElement('li');
      li.append(document.createTextNode(row ? row.title + (row.src ? ' (' + hooks.source(row.src) + ')' : '') : 'Unavailable entry: ' + key));
      if (editing && owner) {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Remove';
        button.onclick = () => { if (busy) return; selected.delete(key); li.remove(); changed(); if (!missing().length) $('clmissingdialog').close(); };
        li.append(button);
      }
      $('clmissingrows').append(li);
    }
    $('clmissingdialog').showModal();
  }
  function showCreate() {
    if (editing && dirty) { status('Save or discard your current changes before creating another list.', true); return; }
    copySource = null;
    $('clcreatehint').textContent = 'Your list starts private. Choose entries, then decide who can see it.';
    if (!hooks.token()) { location.assign(signIn('/releases/?createList=1')); return; }
    $('clcreate').showModal(); $('clnewtitle').focus();
  }
  async function create(event) {
    event.preventDefault(); if (createBusy) return;
    const session = sessionVersion;
    const title = $('clnewtitle').value.trim();
    if (!title) { $('clcreatestatus').textContent = 'Enter a list name.'; return; }
    createBusy = true; $('clcreateyes').disabled = true; $('clcreatestatus').textContent = 'Creating your private list...';
    try {
      const source = copySource ? await request((owner ? '/lists/' : '/public/lists/') + copySource, null, owner) : null;
      if (session !== sessionVersion) return;
      const created = await request('/lists', {method: 'POST', body: JSON.stringify({title, description: $('clnewdescription').value.trim(), keys: source ? source.keys : []})}, true);
      if (session !== sessionVersion) return;
      location.assign('/releases/?editList=' + encodeURIComponent(created.id));
    } catch (err) {
      if (session !== sessionVersion) return;
      $('clcreatestatus').textContent = err.status === 404 && copySource ? 'The original list is no longer available. No copy was created.' : err.status === 401 ? errorText(err) : 'Could not confirm creation. Check My lists before trying again.';
      createBusy = false; $('clcreateyes').disabled = false;
    }
  }
  function panelButton(row) {
    if (!row || row.grp || !row.k) return '';
    const label = 'Add ' + row.title + (row.src ? ' (' + hooks.source(row.src) + ')' : '') + ' to a list';
    return '<button type="button" class="clentryadd" data-list-entry="' + safe(row.k) + '" aria-label="' + safe(label) + '">Add to list</button>';
  }
  function entryStatus(text, error = false) {
    $('clentrystatus').textContent = text; $('clentrystatus').classList.toggle('error', error);
  }
  function entryControls() {
    for (const control of $('clentryforms').querySelectorAll('input,textarea,select,button')) control.disabled = entryBusy;
    $('clentryaddyes').disabled = entryBusy || !validID($('clentrytarget').value);
    $('clentrycreateyes').disabled = entryBusy || entryCreateBlocked;
    $('clentryreload').disabled = entryBusy;
  }
  async function entryLists() {
    const attempt = ++entryVersion, session = sessionVersion;
    entryBusy = true; entryControls(); entryStatus('Loading your lists...');
    $('clentrysignin').hidden = true; $('clentryreload').hidden = true; $('clentryforms').hidden = true;
    try {
      const data = await request('/lists', null, true);
      if (attempt !== entryVersion || session !== sessionVersion) return;
      const picker = $('clentrytarget'); picker.replaceChildren(new Option('Choose a list', ''));
      for (const row of data.lists) {
        const current = editing && owner && list && row.id === id;
        picker.append(new Option((current ? list.title : row.title) + (current ? ' (current editor; save required)' : ''), row.id));
      }
      if (editing && owner && list && data.lists.some(row => row.id === id)) picker.value = id;
      $('clentryexisting').hidden = !data.lists.length;
      $('clentryempty').hidden = !!data.lists.length;
      $('clentrynew').open = !data.lists.length;
      $('clentryforms').hidden = false; entryCreateBlocked = false;
      entryStatus('Choose one of your lists, or make a new private list.');
    } catch (err) {
      if (attempt !== entryVersion || session !== sessionVersion) return;
      $('clentrysignin').hidden = err.status !== 401;
      entryStatus(err.status === 401 ? 'Sign in to add this entry to your own lists. Your current view stays open here.' : 'Could not load your lists. Check your connection and try again.', true);
    } finally {
      if (attempt === entryVersion && session === sessionVersion) { entryBusy = false; $('clentryreload').hidden = false; entryControls(); }
    }
  }
  function showEntry(key) {
    const row = hooks.original(key);
    if (!row || row.grp || !row.k) return;
    if (editing && busy) { notice('Wait for the current list to finish saving, then try Add to list again.'); return; }
    entryVersion++; entryRow = row; entryBusy = false; entryCreateBlocked = false;
    $('clentryname').textContent = row.title;
    $('clentrycore').textContent = [row.core ? 'Core: ' + row.core : '', row.src ? 'Source: ' + hooks.source(row.src) : ''].filter(Boolean).join(' · ');
    $('clentrysignin').href = signIn(hooks.entryReturn(row.k));
    $('clentrycreated').hidden = true; $('clentryforms').hidden = true; $('clentryreload').hidden = true;
    $('clentrynewtitle').value = ''; $('clentrynewdescription').value = '';
    $('clentrydialog').showModal();
    if (!hooks.token()) {
      $('clentrysignin').hidden = false;
      entryStatus('Sign in to add this entry to your own lists. Your current view stays open here.');
    } else entryLists();
  }
  function resumeEntry() {
    if (!params.has('addToList') || (editing && (busy || !list || !owner))) return;
    const key = params.get('addToList'), url = new URL(location.href);
    params.delete('addToList'); url.searchParams.delete('addToList'); history.replaceState(history.state, '', url);
    if (hooks.original(key)) showEntry(key); else notice('That entry is no longer in the catalogue. Choose another entry to add to a list.');
  }
  async function addEntry(event) {
    event.preventDefault();
    const target = $('clentrytarget').value, row = entryRow;
    if (entryBusy || !row || !validID(target)) return;
    // The open editor owns its pending state. Never write around its unsaved changes.
    if (editing && target === id) {
      if (!owner || !list || busy) { entryStatus('Retry the current editor with the list owner signed in before adding here.', true); return; }
      if (selected.has(row.k)) { entryStatus('This entry is already in the current selection. Save the list when your edits are ready.'); return; }
      if (selected.size >= 5000) { entryStatus('A list can hold up to 5,000 entries. Remove an entry first.', true); return; }
      selected.add(row.k); changed(); entryStatus('Added to the current selection. Use Save in the editor to save your changes.'); return;
    }
    const attempt = entryVersion, session = sessionVersion;
    entryBusy = true; entryControls(); entryStatus('Adding entry...');
    try {
      const current = await request('/lists/' + target, null, true);
      if (attempt !== entryVersion || session !== sessionVersion) return;
      if (current.keys.includes(row.k)) { entryStatus('This entry is already saved in "' + current.title + '".'); return; }
      if (current.keys.length >= 5000) { entryStatus('This list already has 5,000 entries. Remove an entry before adding another.', true); return; }
      const updated = await request('/lists/' + target, {method: 'PUT', body: JSON.stringify({
        title: current.title, description: current.description, keys: [...current.keys, row.k],
        visibility: current.visibility || (current.published ? 'unlisted' : 'private'), version: current.version
      })}, true);
      if (session !== sessionVersion) return;
      if (!editing && mode === 'list' && target === id) {
        loadVersion++; busy = false; owner = true; list = updated; selected = new Set(updated.keys); original = snapshot(); redraw();
      }
      refreshCollections();
      if (attempt !== entryVersion) return;
      entryStatus('Added to "' + updated.title + '". Saved with its existing visibility.');
    } catch (err) {
      if (attempt !== entryVersion || session !== sessionVersion) return;
      $('clentrysignin').hidden = err.status !== 401;
      const text = err.code === 'profile_required' ? 'Choose a display name on your account page before updating this shared list.'
        : err.status === 409 ? 'This list changed elsewhere. Nothing was overwritten. Choose Add again to use its latest saved version.'
        : err.status === 404 ? 'This list is no longer available to your account. Reload your lists to choose another.'
        : err.status === 401 ? 'Your sign-in expired. Sign in again, then reopen Add to list.'
        : 'Could not confirm the addition. Try Add again to check the saved list; existing entries will not be duplicated.';
      entryStatus(text, true);
    } finally { if (attempt === entryVersion && session === sessionVersion) { entryBusy = false; entryControls(); } }
  }
  async function createEntryList(event) {
    event.preventDefault();
    if (entryBusy || entryCreateBlocked || !entryRow) return;
    const title = $('clentrynewtitle').value.trim();
    if (!title) { entryStatus('Enter a name for your new list.', true); $('clentrynewtitle').focus(); return; }
    const attempt = entryVersion, session = sessionVersion, key = entryRow.k;
    entryBusy = true; entryControls(); entryStatus('Creating your private list...');
    try {
      const created = await request('/lists', {method: 'POST', body: JSON.stringify({title, description: $('clentrynewdescription').value.trim(), keys: [key], visibility: 'private'})}, true);
      if (session !== sessionVersion) return;
      refreshCollections();
      if (attempt !== entryVersion) return;
      $('clentrytarget').append(new Option(created.title, created.id)); $('clentrytarget').value = created.id;
      $('clentryexisting').hidden = false; $('clentryempty').hidden = true; $('clentrynew').open = false;
      $('clentrynewtitle').value = ''; $('clentrynewdescription').value = '';
      $('clentrycreated').href = '/releases/?editList=' + encodeURIComponent(created.id); $('clentrycreated').hidden = false;
      entryStatus('Created "' + created.title + '" privately with this entry. Your current view is unchanged.');
    } catch (err) {
      if (attempt !== entryVersion || session !== sessionVersion) return;
      $('clentrysignin').hidden = err.status !== 401;
      entryCreateBlocked = ![400,401,413].includes(err.status);
      entryStatus(err.status === 401 ? 'Your sign-in expired. Sign in again, then reopen Add to list.'
        : [400,413].includes(err.status) ? 'Use a name up to 100 characters and a description up to 2,000.'
        : 'Could not confirm creation. Reload your lists and check for the new list before creating another.', true);
    } finally { if (attempt === entryVersion && session === sessionVersion) { entryBusy = false; entryControls(); } }
  }
  function sessionChanged() {
    if (!started) return;
    sessionVersion++; collectionsVersion++; loadVersion++; profile = null; profileLoaded = false;
    collections = {owned: [], following: []}; following = false; owner = false;
    followBusy = false; createBusy = false; entryVersion++; entryRow = null; entryBusy = false;
    for (const dialog of document.querySelectorAll('dialog.cldialog[open]')) dialog.close();
    for (const control of $('clvisibilityform').querySelectorAll('button,input')) control.disabled = false;
    $('clcreateyes').disabled = false;
    updatePicker();
    if (editing) {
      // Never discard an in-progress selection during sign-in/out in another tab.
      busy = false; status("Your sign-in changed. Sign in to the list owner's account, then retry to continue.", true);
      $('clsignin').hidden = false; $('clretry').hidden = false;
      hooks.closePanel();
      redraw();
    } else if (mode === 'list') {
      busy = false; list = null; selected.clear(); hooks.closePanel(); redraw(); load();
    }
    refreshCollections();
  }
  function navigate(url) {
    if (!editing || !dirty) { location.assign(url); return; }
    pendingNavigation = url;
    $('clleavesave').disabled = $('clleavediscard').disabled = busy || !owner;
    $('clleave').showModal(); $('clleavekeep').focus(); updatePicker();
  }
  function start(bridge) {
    hooks = bridge;
    if (started) return;
    started = true;
    if (editing) {
      $('clworkspace').prepend($('clbar'), $('clmobiletabs'));
      $('clworkspace').append($('panel'));
      $('cljumps').append(document.querySelector('.jumps'));
    }
    $('clmembers').onclick = event => {
      const check = event.target.closest('input[data-clmark]');
      if (check && !busy && owner) {
        const key = check.dataset.clmark, end = shownMembers.indexOf(key), start = shownMembers.indexOf(memberAnchor);
        const keys = event.shiftKey && start >= 0 ? shownMembers.slice(Math.min(start, end), Math.max(start, end) + 1) : [key];
        keys.forEach(k => check.checked ? marked.add(k) : marked.delete(k));
        memberAnchor = key; syncMembers(); return;
      }
      const button = event.target.closest('button[data-clremove]');
      if (button) toggle(button.dataset.clremove, false);
    };
    $('clmembersearch').oninput = () => { memberAnchor = null; memberLimit = 200; syncMembers(); };
    $('clmarkall').onclick = () => { if (busy || !owner) return; shownMembers.forEach(key => marked.add(key)); syncMembers(); };
    $('clmarkclear').onclick = () => { marked.clear(); memberAnchor = null; syncMembers(); };
    $('clmarkremove').onclick = () => {
      if (busy || !owner || !marked.size) return;
      marked.forEach(key => selected.delete(key)); marked.clear(); memberAnchor = null; changed();
      $('clmembers').parentElement.focus({preventScroll: true});
    };
    $('clclearsearch').onclick = () => { $('clmembersearch').value = ''; memberAnchor = null; syncMembers(); $('clmembersearch').focus(); };
    $('clshowadded').onclick = () => {
      $('clmembersearch').value = ''; memberLimit = 5000; syncMembers(); showPane(true);
      $('clmembers').querySelector('.clnewmember')?.scrollIntoView({block: 'nearest'});
    };
    $('clmembersmore').onclick = () => { memberLimit += 200; syncMembers(); };
    const showPane = showList => {
      if (editorPane === 'details') hooks.closePanel();
      setEditorPane(showList ? 'list' : 'catalogue');
    };
    $('clshowcatalogue').onclick = () => showPane(false);
    $('clshowlist').onclick = () => showPane(true);
    $('clshowdetails').onclick = () => hooks.openDetails();
    showPane(false);
    if (editing) window.addEventListener('resize', () => { if (mode === 'list') setEditorPane(editorPane); });
    document.addEventListener('pointerdown', event => {
      if (!event.target.closest('#clbulktools')) $('clbulktools').open = false;
      if (!event.target.closest('#cljumptools')) $('cljumptools').open = false;
    });
    $('cljumps').addEventListener('click', event => {
      if (event.target.closest('button:not(:disabled)')) $('cljumptools').open = false;
    });
    document.addEventListener('keydown', event => {
      if (!editing || !owner || !(event.ctrlKey || event.metaKey) || event.altKey || event.isComposing ||
        event.target.closest('input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit]),textarea,select,[contenteditable="true"]') || document.querySelector('dialog[open]')) return;
      const key = event.key.toLowerCase();
      if (key !== 'z' && key !== 'y') return;
      event.preventDefault(); event.stopImmediatePropagation(); travelHistory(key === 'z' && !event.shiftKey);
    }, true);
    document.addEventListener('click', event => {
      const link = event.target.closest('a[href]');
      if (!editing || !dirty || event.defaultPrevented || !link || link.id === 'cldone' || link.target === '_blank' || link.hasAttribute('download') || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
      const url = new URL(link.href, location.href);
      if (!['http:', 'https:'].includes(url.protocol) || (url.pathname === location.pathname && url.search === location.search && url.hash)) return;
      event.preventDefault(); navigate(url.href);
    });
    $('clleave').addEventListener('cancel', () => { pendingNavigation = null; });
    $('clleavekeep').onclick = () => { pendingNavigation = null; $('clleave').close(); };
    $('clleavediscard').onclick = () => { if (busy) return; clearDraft(); dirty = false; location.assign(pendingNavigation); };
    $('clleavesave').onclick = async () => {
      if (busy) return;
      const destination = pendingNavigation;
      $('clleavesave').disabled = $('clleavediscard').disabled = true;
      if (await save(visibility())) { if (pendingNavigation === destination) location.assign(destination); return; }
      $('clleave').close(); pendingNavigation = null;
      $('clleavesave').disabled = $('clleavediscard').disabled = false;
    };
    $('collection-select').onchange = event => {
      const value = event.target.value;
      if (value === 'manage') navigate(hooks.token() ? '../lists/?view=mine' : signIn('/lists/?view=mine'));
      else if (validID(value)) navigate('/releases/?list=' + encodeURIComponent(value));
    };
    $('collection-create').onclick = showCreate;
    $('clcopylist').onclick = () => {
      if (!list || editing) return;
      if (!hooks.token()) { location.assign(signIn(listPath())); return; }
      copySource = id;
      $('clnewtitle').value = (list.title + ' (copy)').slice(0, 100);
      $('clnewdescription').value = list.description || '';
      $('clcreatehint').textContent = 'Save an independent private copy. It will not receive updates from the original list.';
      $('clcreate').showModal(); $('clnewtitle').focus();
    };
    $('collection-create').disabled = false;
    $('collection-select').disabled = false;
    $('clcreateform').onsubmit = create;
    $('clentryform').onsubmit = addEntry;
    $('clentrynewform').onsubmit = createEntryList;
    $('clentrytarget').onchange = entryControls;
    $('clentryreload').onclick = entryLists;
    $('clentrydialog').addEventListener('close', () => { entryVersion++; entryBusy = false; });
    $('collection-dismiss').onclick = () => { $('collection-intro').hidden = true; try { localStorage.setItem(INTRO, '1'); } catch (_) {} };
    try { $('collection-intro').hidden = localStorage.getItem(INTRO) === '1' || editing || mode === 'list'; } catch (_) {}
    $('clbar').hidden = mode !== 'list';
    if (mode === 'list') {
      $('clname').textContent = editing ? 'Edit list' : 'Loading collection...';
      $('clsignin').href = signIn(editing ? editPath() : listPath());
      $('cllatest').href = listPath();
    }
    $('clretry').onclick = load;
    $('cldiscard').onclick = discardDraft;
    $('clundo').onclick = () => travelHistory(true);
    $('clredo').onclick = () => travelHistory(false);
    $('clundo').title = 'Undo the last edit (Ctrl/Cmd+Z). History resets after saving.';
    $('clredo').title = 'Redo (Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y).';
    $('cldone').onclick = async event => {
      event.preventDefault();
      if (busy || !owner || !list) return;
      if (!dirty || await save(visibility())) location.assign(listPath());
    };
    $('clselected').onclick = () => { selectedOnly = !selectedOnly; redraw(); };
    $('cladd').onclick = () => {
      if (busy || !owner) return;
      const keys = [...new Set(hooks.visible().map(d => d.k).filter(key => key && !selected.has(key)))];
      if (new Set([...selected, ...keys]).size > 5000) { status('A list can hold up to 5,000 entries. Narrow the filters before adding.', true); return; }
      if (!keys.length || !confirm('Add ' + keys.length + ' matching entries to “' + list.title + '”?\n\nThese changes are not saved yet. You can Undo before saving.')) return;
      $('clbulktools').open = false;
      keys.forEach(key => selected.add(key)); changed();
    };
    $('clremove').onclick = () => {
      if (busy || !owner) return;
      const keys = [...new Set(hooks.visible().map(d => d.k).filter(key => selected.has(key)))];
      if (!keys.length || !confirm('Remove ' + keys.length + ' matching entries from “' + list.title + '”?\n\nThese changes are not saved yet. You can Undo before saving.')) return;
      $('clbulktools').open = false;
      keys.forEach(key => selected.delete(key)); changed();
    };
    $('clsave').onclick = () => save(visibility());
    $('clpublish').onclick = showSharing;
    $('clvisibilityform').onsubmit = submitSharing;
    $('clvisibility').onchange = visibilityInputs;
    $('cldetailsbtn').onclick = showDetails;
    $('cldetailsform').onsubmit = event => {
      event.preventDefault(); const title = $('cltitle').value.trim();
      if (!title) { $('cltitle').setCustomValidity('Enter a list title.'); $('cltitle').reportValidity(); return; }
      list.title = title; list.description = $('cldescription').value.trim(); $('cldetails').close(); changed();
    };
    $('cltitle').oninput = () => $('cltitle').setCustomValidity('');
    $('clmissing').onclick = showMissing;
    $('clfollow').onclick = () => setFollowing(!following);
    $('cllinkcopy').onclick = async () => {
      const url = location.origin + listPath();
      try { await navigator.clipboard.writeText(url); status('Share link copied.'); } catch (_) { status('Copy this link: ' + url); }
    };
    for (const button of document.querySelectorAll('[data-clclose]')) button.onclick = () => button.closest('dialog').close();
    window.addEventListener('beforeunload', event => { if (editing && dirty) { event.preventDefault(); event.returnValue = ''; } });
    // A confirmed browser departure discards edits. A crash does not emit
    // pagehide, so its recovery copy can still be offered to the owner.
    window.addEventListener('pagehide', () => { if (editing && dirty) clearDraft(); });
    window.addEventListener('pageshow', event => {
      if (event.persisted && editing && dirty) { dirty = false; load(); }
    });
    // Make restored state explicit, so Back and links don't re-interpret a bare URL.
    if (!location.search && !location.hash) history.replaceState(history.state, '', mode === 'list' ? listPath() : '?collection=' + mode);
    if (mode === 'list') {
      if (!validID(id)) unavailable('That list link is not valid.'); else load();
    } else { remember(); redraw(); }
    refreshCollections();
    if (params.get('createList') === '1') {
      const url = new URL(location.href); url.searchParams.delete('createList'); url.searchParams.set('collection', 'all'); history.replaceState(history.state, '', url);
      if (hooks.token()) showCreate(); else notice('Sign in, then choose Create a list to start your collection.');
    }
    resumeEntry();
    let lastRefresh = Date.now();
    document.addEventListener('visibilitychange', () => {
      if (document.hidden || editing || Date.now() - lastRefresh < 30000) return;
      lastRefresh = Date.now(); refreshCollections();
      if (mode === 'list' && !busy) load();
    });
  }
  return {start, sync, checkbox, matches, toggle, sessionChanged, panelButton, showEntry, detailsOpened, detailsClosed,
    isListView: () => mode === 'list' && !editing,
    isEditing: () => mode === 'list' && editing,
    isFavorites: () => mode === 'favorites', favoritesClick: () => {
    if (mode === 'list') return false;
    location.assign('?collection=' + (mode === 'favorites' ? 'all' : 'favorites')); return true;
  }};
})();
