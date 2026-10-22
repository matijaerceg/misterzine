(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var LOCAL = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  var API = 'https://api.misterzine.fyi';
  try { if (LOCAL && localStorage.getItem('mz-api')) API = localStorage.getItem('mz-api'); } catch (e) {}
  var token = null, loadNumber = 0, deleting = null;
  // Match the Tracker's source names. Unknown future sources keep their own label.
  var SOURCE_NAMES = {
    ongo: 'Ongo', distribution_mister: 'MiSTer Distribution', jtbindb: 'Jotego (JTcores)',
    coinop: 'Coin-Op Collection', meathax: 'Meathax (MeatCores)', rmcores: 'rmCores (rmonic79)',
    slopcore: 'Slop Cores (TheJesusFish)', kuzecores: 'kuzecores (kuzearcade)', blahm1d: 'blahm1d',
    bazset: 'bazset', rossops: 'rossops (Sega Y Board)', tomsvr: 'TomSVR', decoryah: 'decoryah',
    ppriest: 'ppriest', gm0rk: 'Gm0rk', jlrh: 'jlrh', shmupfan: 'shmupfan',
    theypsilon_unofficial_distribution: 'theypsilon Unofficial Distribution'
  };
  var publicID = (new URLSearchParams(location.search).get('id') || '').trim().toUpperCase();
  var hasPublicID = new URLSearchParams(location.search).has('id');
  function readToken() { try { token = localStorage.getItem('mz-token'); } catch (e) { token = null; } }
  readToken();

  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }
  function link(text, href, cls) { var a = el('a', text, cls); a.href = href; return a; }
  function button(text, action, cls) {
    var b = el('button', text, cls || 'btn'); b.type = 'button'; b.addEventListener('click', action); return b;
  }
  function message(text, error) {
    $('message').textContent = text; $('message').className = 'msg' + (error ? ' err' : '');
  }
  function shareURL(id) { return location.origin + '/lists/?id=' + encodeURIComponent(id); }
  function validID(id) { return /^[0-9A-HJKMNP-TV-Z]{12}$/.test(id); }
  function entriesLabel(count) { return count + (count === 1 ? ' entry' : ' entries'); }
  function updatedLabel(value) {
    if (!value) return '';
    var date = new Date(value);
    return isNaN(date.getTime()) ? '' : 'Updated ' + date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  }
  async function copy(text, label) {
    try {
      await navigator.clipboard.writeText(text);
      message(label + ' copied.');
    } catch (e) {
      message('Copy is unavailable in this browser. Select and copy: ' + text);
    }
  }
  async function request(path, options, auth) {
    options = options || {};
    options.headers = Object.assign({}, options.headers || {});
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
      token = null; try { localStorage.removeItem('mz-token'); } catch (e) {}
      message('Your sign-in has expired. Sign in again to manage your lists.', true);
    }
  }
  function card(list) {
    var item = el('li', undefined, 'list-card');
    var heading = el('div', undefined, 'card-title');
    heading.append(el('h3', list.title), el('span', list.published ? 'Published' : 'Private draft', 'state' + (list.published ? ' published' : '')));
    item.append(heading);
    if (list.byline) item.append(el('p', 'By ' + list.byline, 'muted'));
    if (list.description) item.append(el('p', list.description, 'description'));
    item.append(el('p', [entriesLabel(list.count), updatedLabel(list.updated_at)].filter(Boolean).join(' · '), 'muted'));
    var actions = el('div', undefined, 'actions');
    actions.append(link('Edit list', '../releases/?editList=' + encodeURIComponent(list.id), 'btn'));
    if (list.published) {
      actions.append(link('View public page', '?id=' + encodeURIComponent(list.id), 'btn'));
      actions.append(button('Copy share link', function () { copy(shareURL(list.id), 'Share link'); }));
      actions.append(button('Copy ID', function () { copy(list.id, 'List ID'); }));
    }
    actions.append(button('Delete', function () { confirmDelete(list); }, 'btn danger'));
    item.append(actions); return item;
  }
  async function loadLibrary(keepMessage) {
    var thisLoad = ++loadNumber;
    readToken();
    if (!keepMessage) message('');
    $('retry-library').hidden = true;
    if (!token) return signedOut(false);
    $('loading').hidden = false; $('out').hidden = true; $('library').hidden = true;
    try {
      var data = await request('/lists', {}, true);
      if (thisLoad !== loadNumber) return;
      $('cards').replaceChildren();
      (data.lists || []).forEach(function (list) { $('cards').append(card(list)); });
      $('empty').hidden = data.lists.length > 0;
      $('library-count').textContent = data.lists.length + (data.lists.length === 1 ? ' list' : ' lists');
      $('loading').hidden = true; $('library').hidden = false;
    } catch (err) {
      if (thisLoad !== loadNumber) return;
      if (err.status === 401) return signedOut(true);
      $('loading').hidden = true; $('retry-library').hidden = false;
      message('Could not load your lists. Check your connection and try again.', true);
    }
  }
  $('create').addEventListener('submit', async function (event) {
    event.preventDefault();
    var title = $('new-title').value.trim();
    if (!title) { message('Give your list a name before choosing games.', true); $('new-title').focus(); return; }
    var submit = $('create-submit');
    if (submit.disabled) return;
    submit.disabled = true; message('Creating your private draft...');
    try {
      var list = await request('/lists', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        title: title, description: $('new-description').value.trim(), byline: $('new-byline').value.trim(), keys: []
      }) }, true);
      location.assign('../releases/?editList=' + encodeURIComponent(list.id));
    } catch (err) {
      if (err.status === 401) signedOut(true);
      else if (err.status === 400 || err.status === 413) message('Could not create this list. Use a title up to 100 characters, a description up to 2,000, and a public name up to 80.', true);
      else { message('Could not confirm whether the draft was created. Reload My lists before trying again.', true); $('retry-library').hidden = false; }
      submit.disabled = false;
    }
  });
  function confirmDelete(list) {
    deleting = list;
    $('delete-name').textContent = list.title;
    $('delete-message').textContent = '';
    $('delete-confirm').disabled = false;
    $('delete-dialog').showModal();
    $('delete-cancel').focus();
  }
  $('delete-cancel').addEventListener('click', function () { $('delete-dialog').close(); });
  $('delete-confirm').addEventListener('click', async function () {
    if (!deleting || $('delete-confirm').disabled) return;
    var list = deleting;
    $('delete-confirm').disabled = true; $('delete-message').textContent = 'Deleting...';
    try {
      await request('/lists/' + encodeURIComponent(list.id), { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version: list.version }) }, true);
      $('delete-dialog').close();
      await loadLibrary(true); message('List deleted. Its public page is no longer available.');
    } catch (err) {
      if (err.status === 401) { $('delete-dialog').close(); signedOut(true); }
      else if (err.status === 409 || err.status === 404) {
        $('delete-dialog').close(); await loadLibrary(true);
        message(err.status === 409 ? 'This list changed in another tab or device. Your lists have been refreshed. Review it before deleting again.' : 'This list was already removed. Your lists have been refreshed.', err.status === 409);
      } else {
        $('delete-message').textContent = 'Could not confirm the deletion. Close this dialog and reload My lists to check before trying again.';
      }
    }
  });
  $('retry-library').addEventListener('click', function () { loadLibrary(); });
  $('refresh').addEventListener('click', function () { loadLibrary(); });
  $('open-list').addEventListener('submit', function (event) {
    event.preventDefault(); var id = $('open-id').value.trim().toUpperCase();
    if (!validID(id)) { message('Enter the 12-character list ID.', true); $('open-id').focus(); return; }
    location.assign('?id=' + encodeURIComponent(id));
  });

  async function loadPublic() {
    var thisLoad = ++loadNumber;
    $('public').hidden = true; $('loading').hidden = false; $('retry-public').hidden = true; message('');
    if (!validID(publicID)) {
      $('loading').hidden = true; message('That list ID is not valid. Enter a 12-character ID below.', true); return;
    }
    try {
      var list = await request('/public/lists/' + encodeURIComponent(publicID));
      if (thisLoad !== loadNumber) return;
      $('public-title').textContent = list.title;
      document.title = list.title + ' - Custom Lists - MisterZine';
      $('public-byline').textContent = list.byline ? 'By ' + list.byline : '';
      $('public-byline').hidden = !list.byline;
      $('public-description').textContent = list.description;
      $('public-description').hidden = !list.description;
      $('public-meta').textContent = [entriesLabel(list.keys.length), updatedLabel(list.updated_at)].filter(Boolean).join(' · ');
      $('public-id').textContent = list.id;
      $('view-tracker').href = '../releases/?list=' + encodeURIComponent(list.id);
      $('copy-id').onclick = function () { copy(list.id, 'List ID'); };
      $('copy-link').onclick = function () { copy(shareURL(list.id), 'Share link'); };
      $('loading').hidden = true; $('public').hidden = false;
      $('entries').replaceChildren();
      $('catalogue-message').textContent = 'Loading entries...';
      $('retry-catalogue').hidden = true;
      try {
        var res = await fetch('../releases/data.json');
        if (thisLoad !== loadNumber) return;
        if (!res.ok) throw new Error('catalogue');
        var rows = await res.json(), byKey = new Map();
        if (thisLoad !== loadNumber) return;
        rows.forEach(function (row) { byKey.set(row.k, row); });
        var missing = 0;
        list.keys.forEach(function (key) {
          var row = byKey.get(key), item = el('li');
          if (row) {
            item.append(link(row.title, '../releases/?list=' + encodeURIComponent(list.id) + '#' + encodeURIComponent(key), 'entry-title'));
            item.append(el('span', [row.year, row.manufacturer, row.genre].filter(Boolean).join(' · '), 'entry-meta'));
            item.append(el('span', 'Core: ' + (row.core || row.title) + (row.src ? ' · Source: ' + (SOURCE_NAMES[row.src] || row.src) : '') + (row.repo ? ' · ' + row.repo : ''), 'entry-meta'));
          } else {
            missing++; item.className = 'missing';
            item.append(el('span', key, 'entry-title'));
            item.append(el('span', 'Unavailable in the current catalogue. This saved entry remains in the list.', 'entry-meta'));
          }
          $('entries').append(item);
        });
        $('catalogue-message').textContent = !list.keys.length ? 'This list has no entries yet.' : missing ? entriesLabel(missing) + ' unavailable in the current catalogue.' : '';
      } catch (err) {
        if (thisLoad !== loadNumber) return;
        $('catalogue-message').textContent = 'The catalogue could not be loaded, so game details are unavailable. Your list is still here.';
        $('retry-catalogue').hidden = false;
      }
    } catch (err) {
      if (thisLoad !== loadNumber) return;
      $('loading').hidden = true;
      if (err.status === 404) message('This list is private, has been deleted, or does not exist. Ask its owner for a published link.', true);
      else { message('Could not load this list. Check your connection and try again.', true); $('retry-public').hidden = false; }
    }
  }
  $('retry-public').addEventListener('click', loadPublic);
  $('retry-catalogue').addEventListener('click', loadPublic);
  window.addEventListener('storage', function (event) {
    if (event.key === 'mz-token' || event.key === null) {
      readToken();
      if (!hasPublicID) { $('delete-dialog').close(); loadLibrary(); }
    }
  });
  if (hasPublicID) {
    $('library-intro').hidden = true;
    loadPublic();
  } else loadLibrary();
})();
