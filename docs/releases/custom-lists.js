// Collections select the catalogue; the Tracker's filters work within it.
// Browser storage remembers only a collection reference, never private list contents.
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
  const $ = id => document.getElementById(id);
  const safe = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const visibility = () => list.visibility || (list.published ? 'unlisted' : 'private');
  const visibilityLabel = value => ({private: 'Private draft', unlisted: 'Unlisted', public: 'Public'})[value];
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
  function changed() { dirty = snapshot() !== original; status(dirty ? 'Changes are not saved yet.' : 'No unsaved changes.'); redraw(); }
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
        const option = new Option(row.unavailable ? 'Unavailable list' : row.title, row.id);
        option.disabled = !!row.unavailable; group.append(option);
      }
      picker.append(group);
    }
    if (mode === 'list' && list && ![...picker.options].some(o => o.value === id)) picker.append(new Option(list.title, id));
    picker.append(new Option(hooks.token() ? 'Manage your lists...' : 'Sign in for your lists...', 'manage'));
    picker.value = mode === 'list' && list ? id : '';
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
    $('collection-all').setAttribute('aria-current', mode === 'all' ? 'page' : 'false');
    $('collection-favorites').setAttribute('aria-current', mode === 'favorites' ? 'page' : 'false');
    if (!list) {
      $('clname').textContent = editing ? 'Edit list' : 'Loading collection...';
      $('clstate').textContent = ''; $('clattribution').replaceChildren();
      $('cldescriptionview').textContent = '';
      for (const element of ['cldescriptionfold', 'cledit', 'cldone', 'cleditlink', 'cllinkcopy', 'clfollow', 'clmissing', 'cllatest']) $(element).hidden = true;
      return;
    }
    $('clname').textContent = list.title;
    $('clstate').textContent = visibilityLabel(visibility()) + (editing ? dirty ? ' · Unsaved changes' : ' · Saved' : '');
    $('cledit').hidden = !editing || !owner; $('cldone').hidden = !editing;
    $('cldone').href = listPath();
    $('cleditlink').hidden = editing || !owner; $('cleditlink').href = editPath();
    $('cllinkcopy').hidden = visibility() === 'private';
    $('clfollow').hidden = editing || owner || visibility() === 'private';
    $('clfollow').disabled = followBusy;
    $('clfollow').textContent = following ? 'Unfollow' : 'Follow list';
    $('clfollow').setAttribute('aria-pressed', String(following));
    $('clselected').textContent = 'Selected (' + selected.size + ')';
    $('clselected').setAttribute('aria-pressed', selectedOnly);
    $('clsave').textContent = visibility() === 'private' ? 'Save draft' : 'Save changes';
    $('clsave').disabled = busy || !dirty;
    $('clpublish').textContent = visibility() === 'private' ? 'Share / publish...' : 'Sharing...';
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
      ? 'Tick exact entries, or add everything matching your filters. Expand a grouped row to choose a specific core. ' + (visibility() === 'private' ? 'Your draft stays private until you share it.' : 'Saving changes updates the same shared list.')
      : 'Search and filters apply within this collection.';
    const n = missing().length;
    $('clmissing').hidden = !n; $('clmissing').disabled = busy;
    $('clmissing').textContent = n + (n === 1 ? ' saved entry is' : ' saved entries are') + ' not shown in the Tracker · Review';
    for (const button of $('cledit').querySelectorAll('button')) if (button.id !== 'clsave') button.disabled = busy;
    const matching = hooks.visible();
    $('cladd').textContent = 'Add matching (' + matching.length + ')';
    $('cladd').disabled = busy || !matching.length;
    $('clremove').disabled = busy || !matching.some(d => selected.has(d.k));
  }
  function checkbox(d) {
    if (!editing || !list || !owner || d.grp || !d.k) return '';
    return '<input class="clpick" type="checkbox" data-list-key="' + safe(d.k) + '" aria-label="Include ' + safe(d.title) + (d.src ? ' (' + safe(hooks.source(d.src)) + ')' : '') + ' in this list"' + (selected.has(d.k) ? ' checked' : '') + (busy ? ' disabled' : '') + '>';
  }
  function matches(d) {
    if (mode === 'all') return true;
    if (mode === 'favorites') return !!hooks && hooks.isFavorite(d);
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
      if (!retained) { list = value; selected = new Set(value.keys); dirty = false; original = snapshot(); }
      $('clretry').hidden = true; $('clsignin').hidden = true;
      status(retained ? 'Your unsaved edits are still here.' : editing ? 'Select entries, then save your list.' : '');
      if (retained && list.version !== value.version) {
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
    $('clconfirmyes').textContent = value === 'public' ? 'Publish to Browse lists' : value === 'unlisted' ? 'Save as unlisted' : 'Save privately';
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
      const latest = await request('/public/lists/' + id);
      if (session === sessionVersion && list) list.follower_count = latest.follower_count;
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
    if (!hooks.token()) { location.assign(signIn('/releases/?createList=1')); return; }
    $('clcreate').showModal(); $('clnewtitle').focus();
  }
  async function create(event) {
    event.preventDefault(); if (createBusy) return;
    const session = sessionVersion;
    const title = $('clnewtitle').value.trim();
    if (!title) { $('clcreatestatus').textContent = 'Enter a list name.'; return; }
    createBusy = true; $('clcreateyes').disabled = true; $('clcreatestatus').textContent = 'Creating your private draft...';
    try {
      const created = await request('/lists', {method: 'POST', body: JSON.stringify({title, description: $('clnewdescription').value.trim(), keys: []})}, true);
      if (session !== sessionVersion) return;
      location.assign('/releases/?editList=' + encodeURIComponent(created.id));
    } catch (err) {
      if (session !== sessionVersion) return;
      $('clcreatestatus').textContent = err.status === 401 ? errorText(err) : 'Could not confirm creation. Check My lists before trying again.';
      createBusy = false; $('clcreateyes').disabled = false;
    }
  }
  function sessionChanged() {
    if (!started) return;
    sessionVersion++; collectionsVersion++; loadVersion++; profile = null; profileLoaded = false;
    collections = {owned: [], following: []}; following = false; owner = false;
    followBusy = false; createBusy = false;
    for (const dialog of document.querySelectorAll('dialog.cldialog[open]')) dialog.close();
    for (const control of $('clvisibilityform').querySelectorAll('button,input')) control.disabled = false;
    $('clcreateyes').disabled = false;
    updatePicker();
    if (editing) {
      // Never discard an in-progress selection during sign-in/out in another tab.
      busy = false; status("Your sign-in changed. Sign in to the list owner's account, then retry to continue.", true);
      $('clsignin').hidden = false; $('clretry').hidden = false;
      redraw();
    } else if (mode === 'list') {
      busy = false; list = null; selected.clear(); hooks.closePanel(); redraw(); load();
    }
    refreshCollections();
  }
  function start(bridge) {
    hooks = bridge;
    if (started) return;
    started = true;
    $('collection-select').onchange = event => {
      const value = event.target.value;
      if (value === 'manage') location.assign(hooks.token() ? '../lists/?view=mine' : signIn('/lists/?view=mine'));
      else if (validID(value)) location.assign('/releases/?list=' + encodeURIComponent(value));
    };
    $('collection-create').onclick = showCreate;
    $('collection-create').disabled = false;
    $('collection-select').disabled = false;
    $('clcreateform').onsubmit = create;
    $('collection-dismiss').onclick = () => { $('collection-intro').hidden = true; try { localStorage.setItem(INTRO, '1'); } catch (_) {} };
    try { $('collection-intro').hidden = localStorage.getItem(INTRO) === '1' || editing || mode === 'list'; } catch (_) {}
    $('clbar').hidden = mode !== 'list';
    if (mode === 'list') {
      $('clname').textContent = editing ? 'Edit list' : 'Loading collection...';
      $('clsignin').href = signIn(editing ? editPath() : listPath());
      $('cllatest').href = editPath();
    }
    $('clretry').onclick = load;
    $('clselected').onclick = () => { selectedOnly = !selectedOnly; redraw(); };
    $('cladd').onclick = () => {
      const keys = hooks.visible().map(d => d.k).filter(Boolean);
      if (new Set([...selected, ...keys]).size > 5000) { status('A list can hold up to 5,000 entries. Narrow the filters before adding.', true); return; }
      keys.forEach(key => selected.add(key)); changed();
    };
    $('clremove').onclick = () => { hooks.visible().forEach(d => selected.delete(d.k)); changed(); };
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
    let lastRefresh = Date.now();
    document.addEventListener('visibilitychange', () => {
      if (document.hidden || editing || Date.now() - lastRefresh < 30000) return;
      lastRefresh = Date.now(); refreshCollections();
      if (mode === 'list' && !busy) load();
    });
  }
  return {start, sync, checkbox, matches, toggle, sessionChanged, isFavorites: () => mode === 'favorites', favoritesClick: () => {
    if (mode === 'list') return false;
    location.assign('?collection=' + (mode === 'favorites' ? 'all' : 'favorites')); return true;
  }};
})();
