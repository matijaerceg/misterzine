// Small bridge into the Tracker: its filters/rows remain the source of truth.
// No list contents are kept in browser storage or mixed with favorites.
window.MZLists = (() => {
  const params = new URLSearchParams(location.search);
  const editing = params.has('editList');
  const id = (params.get(editing ? 'editList' : 'list') || '').trim().toUpperCase();
  const active = editing || params.has('list');
  let hooks, list = null, selected = new Set(), selectedOnly = false;
  let dirty = false, busy = false, started = false;
  const $ = id => document.getElementById(id);
  const safe = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const known = () => new Set(hooks.rows().map(d => d.k));
  const missing = () => { const keys = known(); return [...selected].filter(k => !keys.has(k)); };
  function status(message, error = false) {
    $('clstatus').textContent = message;
    $('clstatus').classList.toggle('error', error);
  }
  function sync() {
    if (!started || !list) return;
    $('clname').textContent = list.title;
    $('clstate').textContent = (list.published ? 'Public list' : 'Private draft') + (dirty ? ' · Unsaved changes' : ' · Saved');
    $('clselected').textContent = 'Selected (' + selected.size + ')';
    $('clselected').setAttribute('aria-pressed', selectedOnly);
    $('clsave').textContent = list.published ? 'Save changes' : 'Save draft';
    $('clsave').disabled = busy || !dirty;
    $('clpublish').hidden = list.published;
    $('clprivate').hidden = !list.published;
    $('clshare').hidden = !list.published;
    $('clshare').href = '../lists/?id=' + encodeURIComponent(list.id);
    $('clcopy').hidden = !list.published;
    $('clnote').textContent = editing
      ? 'Choose exact Tracker entries with the checkboxes. Filters help you find entries; they do not change your selection. ' + (list.published ? 'Saving changes updates the public list.' : 'Only you can see this draft until you publish it.')
      : (list.byline ? 'By ' + list.byline + '. ' : '') + selected.size + ' entries · Updated ' + new Date(list.updated_at).toLocaleDateString() + '. Filters narrow this list only.';
    const n = missing().length;
    $('clmissing').hidden = !n;
    $('clmissing').disabled = busy;
    $('clmissing').textContent = n + (n === 1 ? ' saved entry is' : ' saved entries are') + ' not shown in the Tracker' + (editing ? ' · Review' : ' · View list details');
    for (const el of $('cledit').querySelectorAll('button')) if (el.id !== 'clsave') el.disabled = busy;
    const count = hooks.visible().length;
    $('cladd').textContent = 'Add matching (' + count + ')';
    $('clremove').textContent = 'Remove matching';
    $('cladd').disabled = busy || !count;
    $('clremove').disabled = busy || !hooks.visible().some(d => selected.has(d.k));
  }
  function redraw() { hooks.repaint(); sync(); }
  function changed() { dirty = true; status('Changes are not saved yet.'); redraw(); }
  function checkbox(d) {
    if (!editing || !list || d.grp || !d.k) return '';
    return '<input class="clpick" type="checkbox" data-list-key="' + safe(d.k) + '" aria-label="Include ' + safe(d.title) + (d.src ? ' (' + safe(hooks.source(d.src)) + ')' : '') + ' in this list"' + (selected.has(d.k) ? ' checked' : '') + (busy ? ' disabled' : '') + '>';
  }
  function matches(d) {
    if (!active) return true;
    if (!list) return false;
    return editing && !selectedOnly || selected.has(d.k);
  }
  function toggle(key, checked) {
    if (!editing || !list || busy) return;
    if (checked && selected.size >= 5000) { status('A list can hold up to 5,000 entries.', true); redraw(); return; }
    if (checked) selected.add(key); else selected.delete(key);
    changed();
  }
  async function request(path, options) {
    const token = hooks.token();
    const fail = (message, status) => { const error = new Error(message); error.status = status; throw error; };
    if (editing && !token) fail('Sign in to edit this list. Any unsaved changes are still here.', 401);
    const res = await fetch(hooks.api() + path, { ...options, headers: {
      ...(editing ? { Authorization: 'Bearer ' + token } : {}),
      ...(options ? { 'Content-Type': 'application/json' } : {})
    }});
    if (res.status === 401) fail('Your sign-in has expired. Sign in again; your unsaved changes are still here.', 401);
    if (res.status === 404) throw new Error(editing ? 'This list was deleted or belongs to another account.' : 'This list is private, was deleted, or the ID is incorrect.');
    if (res.status === 409) throw new Error('This list changed in another tab. Your changes have not been saved. Open the latest version in a new tab before replacing anything.');
    if (!res.ok) throw new Error('Could not save or load this list. Please try again.');
    return res.json();
  }
  async function load() {
    if (busy) return;
    busy = true; $('clretry').disabled = true; status('Loading list…');
    try {
      list = await request((editing ? '/lists/' : '/public/lists/') + encodeURIComponent(id));
      selected = new Set(list.keys); dirty = false;
      $('cledit').hidden = !editing;
      $('clretry').hidden = true;
      $('clsignin').hidden = true;
      status(editing ? 'Select entries, then save your list.' : 'This view uses the owner’s latest saved list.');
    } catch (err) {
      status(err instanceof TypeError ? 'Could not reach the list service. Check your connection and try again.' : err.message, true);
      $('clretry').hidden = false;
      $('clsignin').hidden = !editing || err.status !== 401;
    } finally { busy = false; $('clretry').disabled = false; redraw(); }
  }
  async function save(published) {
    if (busy || !list) return;
    busy = true; redraw(); status('Saving…');
    try {
      const updated = await request('/lists/' + encodeURIComponent(id), { method: 'PUT', body: JSON.stringify({
        title: list.title, description: list.description, byline: list.byline,
        keys: [...selected], published, version: list.version
      }) });
      list = updated; selected = new Set(list.keys); dirty = false;
      status(published ? 'Saved. Anyone with the list link or ID can see these entries.' : 'Saved privately. Only your account can see this list.');
      $('clsignin').hidden = true;
    } catch (err) {
      status(err instanceof TypeError ? 'Could not reach the list service. Your changes are still here; try saving again.' : err.message, true);
      $('clsignin').hidden = err.status !== 401;
    } finally { busy = false; redraw(); }
  }
  function confirmVisibility(published) {
    $('clconfirmtitle').textContent = published ? 'Publish this list?' : 'Make this list private?';
    $('clconfirmtext').textContent = published
      ? 'The title, description, curator name and selected entries will be visible to anyone with the link or ID. Your sign-in details stay private. Future saved edits update this same list.'
      : 'The public link and ID will stop returning this list. Copies someone already downloaded cannot be withdrawn. Your current edits will be saved privately.';
    $('clconfirmyes').textContent = published ? 'Publish list' : 'Make private';
    $('clconfirmyes').onclick = () => { $('clconfirm').close(); save(published); };
    $('clconfirm').showModal();
  }
  function showDetails() {
    if (!list || busy) return;
    $('cltitle').value = list.title; $('clbyline').value = list.byline; $('cldescription').value = list.description;
    $('cldetails').showModal();
  }
  function showMissing() {
    if (busy || !list) return;
    if (!editing) { location.href = '../lists/?id=' + encodeURIComponent(id); return; }
    $('clmissingrows').replaceChildren();
    for (const key of missing()) {
      const li = document.createElement('li'); li.append(document.createTextNode(key));
      const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Remove';
      button.onclick = () => { if (busy) return; selected.delete(key); li.remove(); changed(); if (!missing().length) $('clmissingdialog').close(); };
      li.append(button); $('clmissingrows').append(li);
    }
    $('clmissingdialog').showModal();
  }
  function start(bridge) {
    hooks = bridge;
    if (!active || started) return;
    started = true;
    $('clbar').hidden = false;
    $('clback').textContent = editing ? 'My lists' : 'List details';
    $('clback').href = '../lists/' + (editing ? '' : '?id=' + encodeURIComponent(id));
    $('clsignin').href = '../account/?r=' + encodeURIComponent('/releases/?editList=' + id);
    $('clname').textContent = editing ? 'Edit custom list' : 'Custom list';
    $('clretry').onclick = load;
    $('clselected').onclick = () => { selectedOnly = !selectedOnly; redraw(); };
    $('cladd').onclick = () => {
      const keys = hooks.visible().map(d => d.k).filter(Boolean);
      if (new Set([...selected, ...keys]).size > 5000) { status('A list can hold up to 5,000 entries. Narrow the filters before adding.', true); return; }
      keys.forEach(k => selected.add(k)); changed();
    };
    $('clremove').onclick = () => { hooks.visible().forEach(d => selected.delete(d.k)); changed(); };
    $('clsave').onclick = () => save(list.published);
    $('clpublish').onclick = () => confirmVisibility(true);
    $('clprivate').onclick = () => confirmVisibility(false);
    $('cldetailsbtn').onclick = showDetails;
    $('cldetailsform').onsubmit = e => {
      e.preventDefault();
      const title = $('cltitle').value.trim();
      if (!title) { $('cltitle').setCustomValidity('Enter a list title.'); $('cltitle').reportValidity(); return; }
      list.title = title; list.byline = $('clbyline').value.trim(); list.description = $('cldescription').value.trim();
      $('cldetails').close(); changed();
    };
    $('cltitle').oninput = () => $('cltitle').setCustomValidity('');
    $('clmissing').onclick = showMissing;
    $('clcopy').onclick = async () => {
      try { await navigator.clipboard.writeText(id); status('List ID copied: ' + id); }
      catch { status('List ID: ' + id); }
    };
    for (const b of document.querySelectorAll('[data-clclose]')) b.onclick = () => b.closest('dialog').close();
    window.addEventListener('beforeunload', e => { if (editing && (dirty || busy)) { e.preventDefault(); e.returnValue = ''; } });
    if (!/^[0-9A-HJKMNP-TV-Z]{12}$/.test(id)) { status('That list ID is not valid. Open My lists or check the link.', true); redraw(); return; }
    load();
  }
  return { start, sync, checkbox, matches, toggle };
})();
