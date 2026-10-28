window.MZListLibrary = function (root, bridge) {
  'use strict';
  var $ = function (id) { return document.getElementById((root ? "lib-" : "") + id); };
  var LOCAL = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  var API = 'https://api.misterzine.fyi';
  try { if (LOCAL && localStorage.getItem('mz-api')) API = localStorage.getItem('mz-api'); } catch (e) {}
  var params = new URLSearchParams(location.search);
  // The Tracker is the one list viewer; keep previously shared links working.
  if (!root && params.has('id')) {
    location.replace('../releases/?list=' + encodeURIComponent((params.get('id') || '').trim().toUpperCase()) + location.hash);
    return;
  }
  var curatorID = params.get('curator');
  var mode = curatorID !== null ? 'curator' : params.get('view') === 'mine' ? 'mine' : 'directory';
  var token = null, generation = 0, deleting = null, timer = null, sessionVersion = 0;
  var directoryReady = false, pinnedIDs = new Set();
  var offset = 0, busy = false, retryMore = false, seen = new Set();

  var cataloguePromise = null, libraryData = null, accountAttempt = 0, accountReady = false, accountExpired = false;
  var ownedIDs = new Set(), followedIDs = new Set(), retainedFollows = new Map();
  var hiddenFilter = el('input'), hiddenLabel = el('label', 'Hidden lists only');
  hiddenFilter.type = 'checkbox'; hiddenFilter.setAttribute('aria-label', 'Hidden lists only');
  hiddenFilter.style.width = 'auto'; hiddenFilter.style.display = 'inline-block';
  hiddenLabel.prepend(hiddenFilter); hiddenLabel.hidden = true; $('search-form').append(hiddenLabel);
  function adminMode() { return !!(window.MZAdmin && window.MZAdmin.active()); }
  hiddenFilter.addEventListener('change', function () { loadDirectory(false); });
  window.addEventListener('mz-admin-mode', function () {
    hiddenLabel.hidden = !adminMode();
    if (!adminMode() && hiddenFilter.checked) { hiddenFilter.checked = false; ++generation; $('directory-cards').replaceChildren(); if (mode === 'directory') loadDirectory(false); }
  });
  hiddenLabel.hidden = !adminMode();

  var manageTools = el('div', undefined, 'manage-tools');
  var manageSearch = el('input'), manageSort = el('select'), clearSearch = button('Clear search', function () { manageSearch.value = ''; renderLibrary(); manageSearch.focus(); });
  manageSearch.type = 'search'; manageSearch.placeholder = 'Find your lists or a curator'; manageSearch.setAttribute('aria-label', 'Search your saved lists');
  manageSort.setAttribute('aria-label', 'Sort your saved lists');
  [['updated', 'Recently updated'], ['title', 'Alphabetical']].forEach(function (option) { var node = el('option', option[1]); node.value = option[0]; manageSort.append(node); });
  manageTools.append(manageSearch, manageSort, clearSearch); $('library').prepend(manageTools);
  manageSearch.addEventListener('input', renderLibrary); manageSort.addEventListener('change', renderLibrary);
  function renderLibrary() {
    if (!libraryData) return;
    closePreviews();
    var query = manageSearch.value.trim().toLocaleLowerCase(); clearSearch.hidden = !query;
    [['owned', true], ['following', false]].forEach(function (group) {
      var all = libraryData[group[0]], rows = all.filter(function (list) { return [list.title, list.description, list.curator && list.curator.name].join(' ').toLocaleLowerCase().includes(query); });
      rows.sort(function (a, b) { return (manageSort.value === 'updated' ? (b.updated_at || '').localeCompare(a.updated_at || '') : 0) || (a.title || '').localeCompare(b.title || '', undefined, {numeric: true, sensitivity: 'base'}); });
      $(group[0] + '-cards').replaceChildren();
      rows.forEach(function (list) { $(group[0] + '-cards').append(card(list, group[1], !group[1])); });
      $(group[0] + '-count').textContent = query ? rows.length + ' of ' + countLabel(all.length, 'list') : countLabel(all.length, 'list');
      var empty = $(group[0] + '-empty'); empty.hidden = !!rows.length;
      if (!empty.dataset.original) empty.dataset.original = empty.innerHTML;
      if (query) empty.textContent = 'No ' + (group[1] ? 'owned' : 'followed') + ' lists match your search.';
      else empty.innerHTML = empty.dataset.original;
    });
    updateFollowControls();
  }
  function updateFollowControls() {
    (root || document).querySelectorAll('[data-follow-list]').forEach(function (control) {
      var id = control.dataset.followList;
      control.textContent = !token || accountExpired ? 'Sign in to follow' : !accountReady ? 'Retry account check' : ownedIDs.has(id) ? 'Your list' : followedIDs.has(id) ? 'Following' : 'Follow list';
      control.disabled = !!token && accountReady && ownedIDs.has(id);
      control.classList.toggle('is-following', followedIDs.has(id)); control.setAttribute('aria-pressed', String(followedIDs.has(id)));
      control.dataset.tip = followedIDs.has(id) ? 'Unfollow this list and remove its pinned tab' : 'Keep this list in Your lists';
      decorate(control, 'checkmark');
      var item = control.closest('.list-card');
      if (item) { var note = item.querySelector('.retained-follow-note'); if (!note) { note = el('p', 'Unfollowed. You can follow again before leaving.', 'muted retained-follow-note'); item.append(note); } note.hidden = !retainedFollows.has(id); }
    });
  }
  async function refreshCardAccount() {
    var attempt = ++accountAttempt, session = sessionVersion; readToken(); var currentToken = token;
    accountReady = false; accountExpired = false; ownedIDs.clear(); followedIDs.clear();
    if (!token) { updateFollowControls(); return; }
    try {
      var data = await request('/collections', {}, true);
      if (attempt !== accountAttempt || session !== sessionVersion || token !== currentToken) return;
      ownedIDs = new Set(data.owned.map(function (row) { return row.id; })); followedIDs = new Set(data.following.map(function (row) { return row.id; })); accountReady = true;
    } catch (err) { if (attempt !== accountAttempt || session !== sessionVersion) return; accountExpired = err.status === 401; }
    updateFollowControls();
  }
  function followControl(list) {
    var control = button('Checking account...', async function () {
      if (!token || accountExpired) { location.assign('../account/?r=' + encodeURIComponent(location.pathname + location.search)); return; }
      if (!accountReady) { control.disabled = true; await refreshCardAccount(); return; }
      var session = sessionVersion, removing = followedIDs.has(list.id); control.disabled = true;
      try {
        if (removing) { await request('/pins/' + encodeURIComponent(list.id), {method: 'DELETE'}, true); if (session !== sessionVersion) return; }
        await request('/following/' + encodeURIComponent(list.id), {method: removing ? 'DELETE' : 'PUT'}, true);
        if (session !== sessionVersion) return;
        if (removing) { followedIDs.delete(list.id); if (mode === 'mine') retainedFollows.set(list.id, list); } else { followedIDs.add(list.id); retainedFollows.delete(list.id); } updateFollowControls();
        message(removing ? 'Removed from your followed lists.' : 'Following ' + list.title + '. It is now in Your lists.');
        if (bridge) bridge.changed();
      } catch (err) {
        if (session !== sessionVersion) return;
        control.disabled = false;
        message(err.status === 429 ? err.message : err.status === 404 ? 'This list is no longer available.' : err.status === 401 ? 'Sign in again to follow this list.' : 'Could not follow this list. Try again.', true);
      }
    });
    control.dataset.followList = list.id; control.disabled = !!token;
    return control;
  }
  function readToken() { try { token = localStorage.getItem('mz-token'); } catch (e) { token = null; } }
  readToken();
  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }
  function decorate(node, name) { var icon = el('span', undefined, 'list-icon icon-' + name); icon.setAttribute('aria-hidden', 'true'); node.prepend(icon); return node; }
  function link(text, href, cls) { var a = el('a', text, cls); a.href = href; return a; }
  function button(text, action, cls) { var b = el('button', text, cls || 'btn'); b.type = 'button'; b.addEventListener('click', action); return b; }
  function message(text, error) { $('message').textContent = text; $('message').className = 'msg' + (error ? ' err' : ''); }
  function countLabel(n, noun) { return n + ' ' + (n === 1 ? noun : noun === 'entry' ? 'entries' : noun + 's'); }
  function dateLabel(value, label) {
    if (!value) return '';
    var date = new Date(value);
    return isNaN(date.getTime()) ? '' : label + ' ' + date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); message('Link copied.'); }
    catch (e) { message('Copy is unavailable in this browser. Select and copy: ' + text); }
  }
  async function request(path, options, auth) {
    options = options || {}; options.headers = Object.assign({}, options.headers || {});
    if (auth) options.headers.Authorization = 'Bearer ' + token;
    options.cache = 'no-store';
    var res = await fetch(API + path, options);
    if (!res.ok) {
      var err = new Error('Request failed'); err.status = res.status;
      try { err.detail = (await res.json()).error; } catch (e) {}
      if (err.status === 429) err.message = 'Too many changes in a short time. Wait a few minutes and try again.';
      if (err.detail === 'list_limit') err.message = 'You can own up to 200 lists. Delete an unused list before creating another.';
      throw err;
    }
    return res.status === 204 ? null : res.json();
  }
  function signedOut(expired) {
    closePreviews(); libraryData = null; $('library').hidden = true; $('out').hidden = false; $('loading').hidden = true;
    if (expired) {
      sessionVersion++; generation++; deleting = null; $('delete-dialog').close(); $('create-submit').disabled = false;
      token = null; try { localStorage.removeItem('mz-token'); } catch (e) {}
      message('Your sign-in has expired. Sign in again to manage your lists.', true);
    }
  }
  function unfollowButton(list) {
    var control = button(pinnedIDs.has(list.id) ? 'Unfollow & unpin' : 'Stop following', async function (event) {
      var b = event.currentTarget, session = sessionVersion; b.disabled = true;
      try {
        await request('/pins/' + encodeURIComponent(list.id), { method: 'DELETE' }, true);
        await request('/following/' + encodeURIComponent(list.id), { method: 'DELETE' }, true);
        if (session !== sessionVersion) return;
        message('Removed from your followed lists.');
        await loadLibrary(true);
      } catch (err) {
        if (session !== sessionVersion) return;
        if (err.status === 401) signedOut(true);
        else { b.disabled = false; message('Could not stop following this list. Try again.', true); }
      }
    });
    if (list.title) control.setAttribute('aria-label', (pinnedIDs.has(list.id) ? 'Unfollow and unpin ' : 'Stop following ') + list.title);
    return control;
  }
  async function previewCatalogue() {
    if (bridge && bridge.catalogue) return bridge.catalogue();
    if (!cataloguePromise) cataloguePromise = fetch('../releases/data.json').then(function (res) {
      if (!res.ok) throw new Error('Catalogue unavailable');
      return res.json();
    }).catch(function (err) { cataloguePromise = null; throw err; });
    return cataloguePromise;
  }
  function closePreviews() {
    (root || document).querySelectorAll('.list-preview').forEach(function (preview) {
      preview.open = false;
      if (preview.querySelector('.list-preview-body').matches(':popover-open')) preview.querySelector('.list-preview-body').hidePopover();
      preview.querySelector('.list-preview-body > div').replaceChildren();
    });
  }
  function gamePreview(list, own) {
    var preview = el('details', undefined, 'list-preview'), summary = el('summary', 'Preview games');
    var body = el('div', undefined, 'list-preview-body'), controller, attempt = 0;
    body.setAttribute('aria-live', 'polite'); body.setAttribute('popover', 'auto'); body.setAttribute('role', 'dialog'); body.setAttribute('aria-label', 'Games in ' + list.title);
    var heading = el('h2', list.title), close = button('Close preview', function () { body.hidePopover(); });
    var content = el('div'); body.append(heading, close, content);
    body.addEventListener('toggle', function () { if (!body.matches(':popover-open')) { if (body.contains(document.activeElement)) summary.focus({preventScroll: true}); preview.open = false; content.replaceChildren(); if (controller) controller.abort(); } });
    function positionPreview() {
      if (!body.matches(':popover-open')) return;
      if (!summary.isConnected) { body.hidePopover(); return; }
      var anchor = summary.getBoundingClientRect(), width = document.documentElement.clientWidth, height = document.documentElement.clientHeight;
      body.style.inset = 'auto'; body.style.margin = '0'; body.style.maxHeight = Math.max(80, height - 24) + 'px';
      var box = body.getBoundingClientRect(), beside = anchor.right + 8 + box.width <= width - 12;
      var left = beside ? anchor.right + 8 : Math.max(12, Math.min(anchor.left, width - box.width - 12));
      var top = beside ? anchor.top : anchor.bottom + 8;
      if (top + box.height > height - 12) top = Math.max(12, beside ? height - box.height - 12 : anchor.top - box.height - 8);
      body.style.left = left + 'px'; body.style.top = top + 'px';
    }
    var previewSize = new ResizeObserver(positionPreview);
    body.addEventListener('toggle', function () {
      if (body.matches(':popover-open')) { previewSize.observe(body); window.addEventListener('resize', positionPreview); document.addEventListener('scroll', positionPreview, true); positionPreview(); }
      else { previewSize.disconnect(); window.removeEventListener('resize', positionPreview); document.removeEventListener('scroll', positionPreview, true); }
    });
    preview.setAttribute('aria-label', 'Games in ' + list.title);
    decorate(summary, 'eye'); preview.append(summary, body);
    async function load() {
      var version = ++attempt, session = sessionVersion, previewToken = token;
      if (controller) controller.abort();
      controller = new AbortController();
      if (body.contains(document.activeElement)) summary.focus({preventScroll: true});
      content.replaceChildren(el('p', 'Loading games...', 'muted'));
      body.setAttribute('aria-busy', 'true');
      try {
        // Recheck access on every open; never keep a snapshot of a withdrawn list.
        var results = await Promise.all([request((own ? '/lists/' : '/public/lists/') + encodeURIComponent(list.id), {signal: controller.signal}, own), previewCatalogue()]);
        if (version !== attempt || session !== sessionVersion || (own && previewToken !== token) || !preview.open || !preview.isConnected) return;
        var keys = results[0].keys, rows = new Map(results[1].map(function (row) { return [row.k, row]; }));
        content.replaceChildren();
        if (!keys.length) { content.append(el('p', 'This list has no games yet.', 'muted')); return; }
        var entries = el('ul', undefined, 'list-preview-entries');
        keys.slice(0, 8).forEach(function (key) {
          var row = rows.get(key), entry = el('li');
          entry.append(el('span', row ? row.title : 'Unavailable entry'));
          entry.append(el('small', row ? [row.core, row.src && (bridge && bridge.source ? bridge.source(row.src) : row.src)].filter(Boolean).join(' - ') : 'No longer in the catalogue'));
          entries.append(entry);
        });
        content.append(entries);
        if (keys.length > 8) content.append(el('p', 'Showing 8 of ' + keys.length + ' entries. Open the list to see all.', 'muted'));
      } catch (err) {
        if (version !== attempt || session !== sessionVersion || (own && previewToken !== token) || !preview.open || !preview.isConnected || err.name === 'AbortError') return;
        content.replaceChildren(el('p', err.status === 404 ? 'This list is no longer shared or has been deleted.' : 'Could not load the games. Try again.', 'muted'));
        if (err.status !== 404) content.append(button('Retry preview', load));
      } finally {
        if (version === attempt) body.setAttribute('aria-busy', 'false');
      }
    }
    preview.addEventListener('toggle', function () {
      summary.textContent = 'Preview games'; decorate(summary, 'eye');
      if (preview.open) { body.showPopover(); positionPreview(); load(); }
      else { if (body.matches(':popover-open')) body.hidePopover(); ++attempt; if (controller) controller.abort(); content.replaceChildren(); body.setAttribute('aria-busy', 'false'); }
    });
    return preview;
  }
  function card(list, own, followed) {
    var item = el('li', undefined, 'list-card');
    item.dataset.listId = list.id;
    if (list.moderation_hidden && !own) { item.append(el('h3', list.title), el('p', list.description), el('p', 'Hidden by admin: ' + list.moderation_reason), el('div', undefined, 'actions')); return item; }
    if (list.unavailable) {
      item.append(el('h3', list.title || 'Unavailable list'), el('p', 'This list is no longer available. Its games cannot be viewed or copied. You can remove it from your followed lists.', 'muted'));
      var remove = unfollowButton(list); remove.textContent = 'Remove from your lists'; remove.setAttribute('aria-label', 'Remove ' + (list.title || 'unavailable list') + ' from your lists'); item.append(remove);
      return item;
    }
    var href = '../releases/?list=' + encodeURIComponent(list.id);
    var heading = el('div', undefined, 'card-title'), title = el('h3');
    title.append(link(list.title, href)); heading.append(title);
    if (own) heading.append(el('span', { private: 'Private', unlisted: 'Unlisted', public: 'Public' }[list.visibility] || 'Private', 'state' + (list.visibility === 'public' ? ' published' : '')));
    item.append(heading);
    if (own && list.moderation_hidden) item.append(el('p', 'Hidden by admin: ' + list.moderation_reason, 'msg err'));
    if (!own && list.curator && list.curator.name) {
      var by = el('p', 'By ', 'muted');
      if (list.visibility === 'public' && list.curator.id) by.append(link(list.curator.name, '?curator=' + encodeURIComponent(list.curator.id)));
      else by.append(document.createTextNode(list.curator.name));
      item.append(by);
    }
    if (list.description) {
      var full = list.description, cut = full.lastIndexOf(' ', 240);
      if (cut < 160) cut = 240;
      var shortened = full.length - cut >= 60 && full.slice(cut).trim().split(/\s+/).length >= 10;
      var description = el('p', shortened ? full.slice(0, cut).trimEnd() + '...' : full, 'description card-description');
      var expand = button('Show more', function () { var open = expand.getAttribute('aria-expanded') !== 'true'; description.textContent = open ? full : full.slice(0, cut).trimEnd() + '...'; expand.textContent = open ? 'Show less' : 'Show more'; expand.setAttribute('aria-expanded', String(open)); }, 'description-toggle');
      expand.hidden = !shortened; expand.setAttribute('aria-expanded', 'false'); item.append(description, expand);
    }
    item.append(el('p', [countLabel(list.count || 0, 'entry'), dateLabel(list.updated_at, 'Updated'), list.follower_count ? countLabel(list.follower_count, 'follower') : ''].filter(Boolean).join(' - '), 'muted card-meta'));
    var actions = el('div', undefined, 'actions');
    actions.append(gamePreview(list, own), decorate(link('Full table view', href, 'btn'), 'list'));
    if (own) {
      actions.append(decorate(link('Edit', '../releases/?editList=' + encodeURIComponent(list.id), 'btn'), 'edit'));
      if (list.visibility !== 'private') actions.append(decorate(button('Copy link', function () { copy(location.origin + '/releases/?list=' + encodeURIComponent(list.id)); }), 'share'));
      actions.append(button('Delete', function () { confirmDelete(list); }, 'btn danger'));
    }
    if (!own) actions.append(followControl(list));
    item.append(actions);

    return item;
  }
  async function loadLibrary(keepMessage) {
    ++accountAttempt;
    var attempt = ++generation; readToken();
    if (!keepMessage) message('');
    $('retry').hidden = true;
    if (!token) return signedOut(false);
    $('loading').hidden = false; $('out').hidden = true; $('library').hidden = true;
    try {
      var data = await request('/collections', {}, true);
      if (attempt !== generation) return;
      pinnedIDs = new Set((data.pins || []).map(function(p) { return p.id; }));
      ownedIDs = new Set(data.owned.map(function (row) { return row.id; })); followedIDs = new Set(data.following.map(function (row) { return row.id; })); accountReady = true;
      retainedFollows.forEach(function (row, id) { if (!followedIDs.has(id)) data.following.push(row); });
      libraryData = data; renderLibrary(); updateFollowControls();
      $('loading').hidden = true; $('library').hidden = false; if (bridge) bridge.changed();
    } catch (err) {
      if (attempt !== generation) return;
      if (err.status === 401) return signedOut(true);
      $('loading').hidden = true; $('retry').hidden = false;
      message('Could not load your lists. Check your connection and try again.', true);
    }
  }
  function setDirectoryURL() {
    if (root) return;
    var p = new URLSearchParams(), q = $('search').value.trim(), sort = $('sort').value;
    if (q) p.set('q', q);
    if (sort !== 'updated') p.set('sort', sort);
    history.replaceState(null, '', location.pathname + (p.size ? '?' + p.toString() : ''));
  }
  async function loadDirectory(more) {
    if (more && busy) return;
    var attempt = ++generation; busy = true; retryMore = !!more;
    $('retry').hidden = true; $('load-more').disabled = true; message('');
    if (!more) {
      directoryReady = false;
      offset = 0; seen.clear(); $('directory-cards').replaceChildren();
      $('directory-empty').hidden = true; $('results-count').textContent = '';
      $('loading').hidden = false; $('load-more').hidden = true;
    }
    var p = new URLSearchParams({ q: $('search').value.trim(), sort: $('sort').value, offset: String(offset), limit: '24' });
    try {
      var hidden = hiddenFilter.checked && adminMode();
      if (hidden) { p.set('hidden', '1'); p.set('shared', '1'); }
      var data = await request((hidden ? '/admin/lists?' : '/public/lists?') + p.toString(), {}, hidden);
      if (attempt !== generation) return;
      data.lists.forEach(function (list) { if (!seen.has(list.id)) { seen.add(list.id); $('directory-cards').append(card(list, false)); } });
      offset += data.lists.length; refreshCardAccount();
      $('results-count').textContent = hidden ? countLabel(offset, 'hidden list') + ' loaded' : countLabel(data.total, 'public list');
      $('directory-empty').textContent = $('search').value.trim() ? 'No public lists match your search. Try a different name or topic.' : 'No public lists yet. Make a list and choose Public to help others find it.';
      $('directory-empty').hidden = data.total > 0;
      $('load-more').hidden = !data.has_more; $('load-more').disabled = false; $('loading').hidden = true; busy = false; directoryReady = true;
    } catch (err) {
      if (attempt !== generation) return;
      directoryReady = false; busy = false; $('loading').hidden = true; $('retry').hidden = false; $('load-more').hidden = true;
      message(more ? 'Could not load more lists. The lists already loaded are still here.' : 'Could not load public lists. Check your connection and try again.', true);
    }
  }
  async function loadCurator() {
    var attempt = ++generation;
    $('loading').hidden = false; $('retry').hidden = true; $('curator-view').hidden = true; message('');
    try {
      var data = await request('/public/curators/' + encodeURIComponent(curatorID));
      if (attempt !== generation) return;
      $('curator-name').textContent = data.profile.display_name; if (!root) document.title = 'MisterZine - ' + data.profile.display_name + ' - Custom Lists';
      $('curator-cards').replaceChildren(); data.lists.forEach(function (list) { $('curator-cards').append(card(list, false)); });
      refreshCardAccount(); $('curator-count').textContent = countLabel(data.lists.length, 'public list'); $('loading').hidden = true; $('curator-view').hidden = false;
    } catch (err) {
      if (attempt !== generation) return;
      $('loading').hidden = true;
      if (err.status === 404) message('This curator has no public lists to show.', true);
      else { message('Could not load this curator\'s lists. Check your connection and try again.', true); $('retry').hidden = false; }
    }
  }
  $('create').addEventListener('submit', async function (event) {
    event.preventDefault(); var title = $('new-title').value.trim();
    if (!title) { message('Give your list a name before choosing games.', true); $('new-title').focus(); return; }
    var submit = $('create-submit'), session = sessionVersion; if (submit.disabled) return;
    submit.disabled = true; message('Creating your private list...');
    try {
      var list = await request('/lists', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: title, description: $('new-description').value.trim(), keys: [], visibility: 'private' }) }, true);
      if (session !== sessionVersion) return;
      location.assign('../releases/?editList=' + encodeURIComponent(list.id));
    } catch (err) {
      if (session !== sessionVersion) return;
      if (err.status === 401) signedOut(true);
      else if (err.status === 429 || err.detail === 'list_limit') message(err.message, true);
      else if (err.status === 400 || err.status === 413) message('Could not create this list. Use a title up to 100 characters and a description up to 2,000.', true);
      else { message('Could not confirm whether the list was created. Reload My lists before trying again.', true); $('retry').hidden = false; }
      submit.disabled = false;
    }
  });
  function confirmDelete(list) {
    deleting = list; $('delete-name').textContent = list.title; $('delete-message').textContent = '';
    $('delete-confirm').disabled = false; $('delete-dialog').showModal(); $('delete-cancel').focus();
  }
  $('delete-cancel').addEventListener('click', function () { $('delete-dialog').close(); });
  $('delete-confirm').addEventListener('click', async function () {
    if (!deleting || $('delete-confirm').disabled) return;
    var list = deleting, session = sessionVersion; $('delete-confirm').disabled = true; $('delete-message').textContent = 'Deleting...';
    try {
      await request('/lists/' + encodeURIComponent(list.id), { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version: list.version }) }, true);
      if (session !== sessionVersion) return;
      $('delete-dialog').close(); await loadLibrary(true); if (session !== sessionVersion) return;
      message('List deleted. Its link no longer works.');
    } catch (err) {
      if (session !== sessionVersion) return;
      if (err.status === 401) { $('delete-dialog').close(); signedOut(true); }
      else if (err.status === 409 || err.status === 404) {
        $('delete-dialog').close(); await loadLibrary(true);
        if (session !== sessionVersion) return;
        message(err.status === 409 ? 'This list changed in another tab or device. Your lists have been refreshed. Review it before deleting again.' : 'This list was already removed. Your lists have been refreshed.', err.status === 409);
      } else $('delete-message').textContent = 'Could not confirm the deletion. Close this dialog and refresh My lists before trying again.';
    }
  });
  $('retry').addEventListener('click', function () { if (mode === 'mine') loadLibrary(); else if (mode === 'curator') loadCurator(); else loadDirectory(retryMore); });
  $('refresh').addEventListener('click', function () { loadLibrary(); });
  $('load-more').addEventListener('click', function () { loadDirectory(true); });
  $('search-form').addEventListener('submit', function (event) { event.preventDefault(); clearTimeout(timer); setDirectoryURL(); loadDirectory(false); });
  $('search').addEventListener('input', function () {
    clearTimeout(timer); ++generation; busy = false; retryMore = false;
    $('retry').hidden = true; $('load-more').hidden = true; $('load-more').disabled = true;
    timer = setTimeout(function () { setDirectoryURL(); loadDirectory(false); }, 300);
  });
  $('sort').addEventListener('change', function () { clearTimeout(timer); setDirectoryURL(); loadDirectory(false); });
  window.addEventListener('storage', function (event) {
    if (event.key === 'mz-token' || event.key === null) {
      sessionVersion++; closePreviews(); retainedFollows.clear(); libraryData = null; manageSearch.value = ''; deleting = null; readToken(); refreshCardAccount(); $('create-submit').disabled = false;
      if (mode === 'mine') { $('delete-dialog').close(); loadLibrary(); }
    }
  });
  function show(next, curator) {
    if (next !== 'manage' || curator) retainedFollows.clear();
    closePreviews();
    clearTimeout(timer); generation++; busy = false; retryMore = false;
    mode = curator ? 'curator' : next === 'manage' ? 'mine' : 'directory'; curatorID = curator;
    readToken(); message(''); $('retry').hidden = true;
    ['directory','mine-intro','library','out','curator-view','loading'].forEach(function(name) { $(name).hidden = true; });
    $('directory').hidden = mode !== 'directory'; $('mine-intro').hidden = mode !== 'mine';
    if (mode === 'mine') return loadLibrary();
    if (mode === 'curator') return loadCurator();
    if (directoryReady) { refreshCardAccount(); return Promise.resolve(); }
    return loadDirectory(false);
  }
  if (root) {
    root.addEventListener('click', function(event) {
      var a = event.target.closest('a[href]');
      if (!a || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button || a.target === '_blank') return;
      var url = new URL(a.href, location.href);
      if (url.origin !== location.origin) return;
      if (url.searchParams.has('curator')) { event.preventDefault(); bridge.navigate('/releases/?collection=browse&curator=' + encodeURIComponent(url.searchParams.get('curator'))); }
      else if (url.pathname === '/releases/') { event.preventDefault(); bridge.navigate(url.href); }
    });
    return {show, hide: function() { retainedFollows.clear(); closePreviews(); clearTimeout(timer); generation++; if (busy) directoryReady = false; busy = false; }};
  }
  $('directory').hidden = mode !== 'directory'; $('mine-intro').hidden = mode !== 'mine';
  if (mode !== 'curator') $(mode === 'mine' ? 'nav-mine' : 'nav-directory').setAttribute('aria-current', 'page');
  if (mode === 'mine') { document.title = 'MisterZine - My Lists'; loadLibrary(); }
  else if (mode === 'curator') loadCurator();
  else {
    $('search').value = (params.get('q') || '').slice(0, 200);
    $('sort').value = ['updated', 'created', 'trending'].includes(params.get('sort')) ? params.get('sort') : 'updated';
    loadDirectory(false);
  }
};
if (!document.getElementById('collection-library')) window.MZListLibrary();
