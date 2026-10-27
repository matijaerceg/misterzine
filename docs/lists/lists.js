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
  var directoryReady = false;
  var offset = 0, busy = false, retryMore = false, seen = new Set();
  function readToken() { try { token = localStorage.getItem('mz-token'); } catch (e) { token = null; } }
  readToken();
  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }
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
      throw err;
    }
    return res.status === 204 ? null : res.json();
  }
  function signedOut(expired) {
    $('library').hidden = true; $('out').hidden = false; $('loading').hidden = true;
    if (expired) {
      sessionVersion++; generation++; deleting = null; $('delete-dialog').close(); $('create-submit').disabled = false;
      token = null; try { localStorage.removeItem('mz-token'); } catch (e) {}
      message('Your sign-in has expired. Sign in again to manage your lists.', true);
    }
  }
  function unfollowButton(list) {
    var control = button('Stop following', async function (event) {
      var b = event.currentTarget, session = sessionVersion; b.disabled = true;
      try {
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
    if (list.title) control.setAttribute('aria-label', 'Stop following ' + list.title);
    return control;
  }
  function card(list, own, followed) {
    var item = el('li', undefined, 'list-card');
    if (list.unavailable) {
      item.append(el('h3', list.title || 'Unavailable list'), el('p', 'This list is no longer available. Its games cannot be viewed or copied. You can remove it from your followed lists.', 'muted'));
      var remove = unfollowButton(list); remove.textContent = 'Remove'; item.append(remove);
      return item;
    }
    var href = '../releases/?list=' + encodeURIComponent(list.id);
    var heading = el('div', undefined, 'card-title'), title = el('h3');
    title.append(link(list.title, href)); heading.append(title);
    if (own) heading.append(el('span', { private: 'Private', unlisted: 'Unlisted', public: 'Public' }[list.visibility] || 'Private', 'state' + (list.visibility === 'public' ? ' published' : '')));
    item.append(heading);
    if (!own && list.curator && list.curator.name) {
      var by = el('p', 'By ', 'muted');
      if (list.visibility === 'public' && list.curator.id) by.append(link(list.curator.name, '?curator=' + encodeURIComponent(list.curator.id)));
      else by.append(document.createTextNode(list.curator.name));
      item.append(by);
    }
    if (list.description) item.append(el('p', list.description, 'description'));
    item.append(el('p', [countLabel(list.count || 0, 'entry'), countLabel(list.follower_count || 0, 'follower')].join(' · '), 'muted'));
    item.append(el('p', [dateLabel(list.updated_at, 'Updated'), dateLabel(list.created_at, 'Created')].filter(Boolean).join(' · '), 'muted'));
    var actions = el('div', undefined, 'actions');
    actions.append(link(root ? 'View games' : 'View in Tracker', href, 'btn'));
    if (own) {
      actions.append(link('Edit', '../releases/?editList=' + encodeURIComponent(list.id), 'btn'));
      if (list.visibility !== 'private') actions.append(button('Copy link', function () { copy(location.origin + '/releases/?list=' + encodeURIComponent(list.id)); }));
      actions.append(button('Delete', function () { confirmDelete(list); }, 'btn danger'));
    }
    if (followed) actions.append(unfollowButton(list));
    item.append(actions); return item;
  }
  async function loadLibrary(keepMessage) {
    var attempt = ++generation; readToken();
    if (!keepMessage) message('');
    $('retry').hidden = true;
    if (!token) return signedOut(false);
    $('loading').hidden = false; $('out').hidden = true; $('library').hidden = true;
    try {
      var data = await request('/collections', {}, true);
      if (attempt !== generation) return;
      $('owned-cards').replaceChildren(); $('following-cards').replaceChildren();
      data.owned.forEach(function (list) { $('owned-cards').append(card(list, true)); });
      data.following.forEach(function (list) { $('following-cards').append(card(list, false, true)); });
      $('owned-empty').hidden = data.owned.length > 0; $('following-empty').hidden = data.following.length > 0;
      $('owned-count').textContent = countLabel(data.owned.length, 'list'); $('following-count').textContent = countLabel(data.following.length, 'list');
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
      var data = await request('/public/lists?' + p.toString());
      if (attempt !== generation) return;
      data.lists.forEach(function (list) { if (!seen.has(list.id)) { seen.add(list.id); $('directory-cards').append(card(list, false)); } });
      offset += data.lists.length;
      $('results-count').textContent = countLabel(data.total, 'public list');
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
      $('curator-name').textContent = data.profile.display_name; if (!root) document.title = data.profile.display_name + ' - Custom Lists - MisterZine';
      $('curator-cards').replaceChildren(); data.lists.forEach(function (list) { $('curator-cards').append(card(list, false)); });
      $('curator-count').textContent = countLabel(data.lists.length, 'public list'); $('loading').hidden = true; $('curator-view').hidden = false;
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
      sessionVersion++; deleting = null; readToken(); $('create-submit').disabled = false;
      if (mode === 'mine') { $('delete-dialog').close(); loadLibrary(); }
    }
  });
  function show(next, curator) {
    clearTimeout(timer); generation++; busy = false; retryMore = false;
    mode = curator ? 'curator' : next === 'manage' ? 'mine' : 'directory'; curatorID = curator;
    readToken(); message(''); $('retry').hidden = true;
    ['directory','mine-intro','library','out','curator-view','loading'].forEach(function(name) { $(name).hidden = true; });
    $('directory').hidden = mode !== 'directory'; $('mine-intro').hidden = mode !== 'mine';
    if (mode === 'mine') return loadLibrary();
    if (mode === 'curator') return loadCurator();
    if (directoryReady) return Promise.resolve();
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
    return {show, hide: function() { clearTimeout(timer); generation++; if (busy) directoryReady = false; busy = false; }};
  }
  $('directory').hidden = mode !== 'directory'; $('mine-intro').hidden = mode !== 'mine';
  if (mode !== 'curator') $(mode === 'mine' ? 'nav-mine' : 'nav-directory').setAttribute('aria-current', 'page');
  if (mode === 'mine') { document.title = 'My Lists - MisterZine'; loadLibrary(); }
  else if (mode === 'curator') loadCurator();
  else {
    $('search').value = (params.get('q') || '').slice(0, 200);
    $('sort').value = ['updated', 'created', 'followers'].includes(params.get('sort')) ? params.get('sort') : 'updated';
    loadDirectory(false);
  }
};
if (!document.getElementById('collection-library')) window.MZListLibrary();
