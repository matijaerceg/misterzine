/* Site feedback form, shared by every page with the site Menu (linked after
   theme.js, styled in nav.css under "site feedback"). It adds three things:
   - a "Feedback" row in the Menu (just before Traffic),
   - a small tab on the right edge of the viewport (a round button at the
     bottom-right on phones, same element, nav.css switches the look),
   - the form itself, a native modal <dialog>.
   It posts to the account service, POST <API>/feedback (api/src/feedback.js
   in the repo has the contract): text, contact, page, key, theme and the
   honeypot "website", with the sign-in token as a bearer when there is one
   (a stale token just sends anonymously, the service never answers 401).
   The API base follows the tracker's rule: api.misterzine.fyi, overridable
   ONLY on localhost/127.0.0.1 through localStorage 'mz-api'.
   Page hooks, both optional:
   - window.mzFeedbackGame() -> {key, title} or null: the game whose panel is
     open (the tracker sets it); the form offers to attach it.
   - [data-fb-clear] on an element: the edge tab stays below it (the
     tracker's jump buttons sit at the same right edge). */
(function () {
  'use strict';
  var LOCAL = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  var API = 'https://api.misterzine.fyi';
  if (LOCAL) { try { API = localStorage.getItem('mz-api') || API; } catch (e) {} }
  var TEXT_MAX = 4000, COUNT_FROM = 3500, CLOSE_AFTER = 1600;
  // Lucide "message-square" (ISC), the icon set the tracker already uses
  var ICON = '<svg class="fbico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' +
    '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';

  // ---- the edge tab / phone button -----------------------------------------
  var tab = document.createElement('button');
  tab.type = 'button';
  tab.className = 'fbtab';
  tab.setAttribute('aria-haspopup', 'dialog');
  tab.setAttribute('aria-label', 'Feedback');
  tab.innerHTML = ICON + '<span class="fbtxt">Feedback</span>';
  document.body.appendChild(tab);

  // keep the tab vertically centred, but below anything marked data-fb-clear
  function place() {
    var minTop = 0;
    var els = document.querySelectorAll('[data-fb-clear]');
    for (var i = 0; i < els.length; i++) {
      var r = els[i].getBoundingClientRect();
      if (r.height) minTop = Math.max(minTop, r.bottom + 12);
    }
    var h = tab.offsetHeight;
    var top = Math.max((innerHeight - h) / 2, minTop);
    tab.style.setProperty('--fb-top', Math.round(Math.min(top, innerHeight - h - 8)) + 'px');
  }
  addEventListener('resize', place);
  // the marked elements can move without the window resizing (a header that
  // wraps once the data lands): watch them and the boxes they sit in
  if (window.ResizeObserver) {
    var ro = new ResizeObserver(place);
    ro.observe(document.body);
    var clr = document.querySelectorAll('[data-fb-clear]');
    for (var c = 0; c < clr.length; c++) {
      ro.observe(clr[c]);
      if (clr[c].offsetParent) ro.observe(clr[c].offsetParent);
    }
  }
  place();

  // ---- the Menu row ---------------------------------------------------------
  var menu = document.getElementById('menudd');
  var mlist = menu && menu.querySelector('.mlist');
  var row = null;
  if (mlist) {
    row = document.createElement('button');
    row.type = 'button';
    row.className = 'fbmenu';
    row.setAttribute('aria-haspopup', 'dialog');
    row.setAttribute('data-tip', 'Tell the developer about a bug, a wrong entry or an idea');
    row.textContent = 'Feedback';
    var before = mlist.querySelector('a[href*="goatcounter"]');
    if (before && before.parentNode === mlist) mlist.insertBefore(row, before);
    else mlist.appendChild(row);
  }

  // ---- the form -------------------------------------------------------------
  var dlg = document.createElement('dialog');
  dlg.className = 'fbdlg';
  dlg.setAttribute('aria-labelledby', 'fbh');
  dlg.innerHTML =
    '<form class="fb-in" novalidate>' +
      '<h2 id="fbh">Feedback</h2>' +
      '<p class="fb-note">A bug, a wrong entry, a missing core or an idea: it goes straight to the developer.</p>' +
      '<label class="fb-lbl" for="fbtext">Your message</label>' +
      '<textarea id="fbtext" name="text" rows="6" maxlength="' + TEXT_MAX + '" required aria-describedby="fbcount"></textarea>' +
      '<div class="fb-count" id="fbcount"></div>' +
      '<label class="fb-lbl" for="fbcontact">How to reach you (optional)</label>' +
      '<input type="text" id="fbcontact" name="contact" maxlength="200" autocomplete="email" placeholder="Email or Discord name">' +
      '<p class="fb-att" id="fbatt"></p>' +
      '<label class="fb-game" hidden><input type="checkbox" id="fbgame" checked> <span>The game you have open: <b id="fbgamet"></b></span></label>' +
      '<p class="fb-note fb-hv">Proposals for the Hardware Verified seal are welcome here too: name the game and link the evidence.</p>' +
      '<div class="fb-hp" aria-hidden="true"><label>Website <input type="text" id="fbweb" name="website" tabindex="-1" autocomplete="off"></label></div>' +
      '<p class="fb-msg" id="fbmsg" role="status" aria-live="polite"></p>' +
      '<div class="fb-act"><button type="button" class="fb-cancel">Cancel</button><button type="submit" class="fb-send">Send</button></div>' +
    '</form>' +
    '<div class="fb-thanks" hidden><h2 tabindex="-1">Thanks</h2><p>Your message is on its way.</p></div>';
  document.body.appendChild(dlg);
  var form = dlg.querySelector('form');
  var ta = dlg.querySelector('#fbtext');
  var contact = dlg.querySelector('#fbcontact');
  var count = dlg.querySelector('#fbcount');
  var att = dlg.querySelector('#fbatt');
  var gameRow = dlg.querySelector('.fb-game');
  var gameBox = dlg.querySelector('#fbgame');
  var web = dlg.querySelector('#fbweb');
  var msg = dlg.querySelector('#fbmsg');
  var send = dlg.querySelector('.fb-send');
  var thanks = dlg.querySelector('.fb-thanks');
  var opener = null, game = null, busy = false, closeT = 0;

  function themeSlug() { return document.documentElement.getAttribute('data-theme') || 'eva'; }
  function themeName(slug) {
    var b = document.querySelector('#themedd button[data-set="' + slug + '"]');
    return b ? b.textContent.trim() : slug;
  }
  function say(text, isErr) { msg.textContent = text; msg.classList.toggle('err', !!isErr); }
  function syncCount() {
    var n = ta.value.length;
    count.textContent = n >= COUNT_FROM ? n + ' / ' + TEXT_MAX + (n >= TEXT_MAX ? ', the limit' : '') : '';
  }
  ta.addEventListener('input', syncCount);
  // an error answers the message as it was; editing either box retires it
  function clearErr() { if (!busy && msg.classList.contains('err')) say(''); }
  ta.addEventListener('input', clearErr);
  contact.addEventListener('input', clearErr);

  function open(from) {
    clearTimeout(closeT);
    opener = from || document.activeElement;
    if (menu) menu.open = false;   // the row lives in the Menu; the form replaces it
    game = null;
    try { if (typeof window.mzFeedbackGame === 'function') game = window.mzFeedbackGame(); } catch (e) {}
    att.textContent = 'Sent with it: the link to this page and your theme (' + themeName(themeSlug()) + ')' + (game ? ', and' : '.');
    gameRow.hidden = !game;
    if (game) { dlg.querySelector('#fbgamet').textContent = game.title; gameBox.checked = true; }
    form.hidden = false; thanks.hidden = true;
    if (!busy) say('');
    syncCount();
    dlg.showModal();
    ta.focus();
  }
  tab.addEventListener('click', function () { open(tab); });
  if (row) row.addEventListener('click', function () { open(row); });

  // focus goes back where it came from; a Menu row is gone with its closed
  // Menu, so its summary takes the focus instead
  dlg.addEventListener('close', function () {
    clearTimeout(closeT);
    var back = opener === row ? document.getElementById('menusum') : opener;
    if (back && document.contains(back) && back.focus) back.focus({ preventScroll: true });
    if (!thanks.hidden) { form.hidden = false; thanks.hidden = true; }
  });
  // light dismiss: a click on the backdrop (the dialog box itself has no
  // padding, so only the backdrop can be the target). Both ends of the click
  // must be out there, or a text selection dragged past the edge would close
  // the form.
  var downOut = false;
  dlg.addEventListener('pointerdown', function (e) { downOut = e.target === dlg; });
  dlg.addEventListener('click', function (e) { if (e.target === dlg && downOut) dlg.close(); });
  dlg.querySelector('.fb-cancel').addEventListener('click', function () { dlg.close(); });
  // a modal dialog already keeps the page inert; this keeps Tab cycling inside
  // the form instead of escaping to the browser chrome. Escape is the
  // dialog's own close; it stops here so page shortcuts never see it.
  function focusables() {
    var all = dlg.querySelectorAll('button, input, textarea, [tabindex]');
    var out = [];
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (el.disabled || el.tabIndex < 0 || !el.getClientRects().length) continue;
      out.push(el);
    }
    return out;
  }
  dlg.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { e.stopPropagation(); return; }
    if (e.key !== 'Tab') return;
    var f = focusables();
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  var ERR = {
    no_text: 'Write a message first.',
    text_too_long: 'That message is longer than ' + TEXT_MAX + ' characters.',
    too_many_links: 'That message has more than five links. Please trim a few.',
    contact_too_long: 'The contact box takes up to 200 characters.',
    bad_contact: 'That contact could not be read. Try an email address or a Discord name.'
  };
  function done() {
    busy = false;
    send.disabled = false;
    send.textContent = 'Send';
  }
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (busy) return;
    if (!ta.value.trim()) { say(ERR.no_text, true); ta.focus(); return; }
    busy = true;
    send.disabled = true;
    send.textContent = 'Sending...';
    say('');
    var withGame = !!(game && gameBox.checked);
    // an unticked game must not ride along in the page link's #key either
    var page = withGame ? location.href : location.href.split('#')[0];
    var body = { text: ta.value, contact: contact.value, page: page, theme: themeSlug(), website: web.value };
    if (withGame) body.key = game.key;
    var headers = { 'Content-Type': 'application/json' };
    var tok = null;
    try { tok = localStorage.getItem('mz-token'); } catch (e2) {}
    if (tok) headers.Authorization = 'Bearer ' + tok;
    fetch(API + '/feedback', { method: 'POST', headers: headers, body: JSON.stringify(body), credentials: 'omit' })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) { return { status: r.status, j: j || {} }; });
      })
      .then(function (res) {
        done();
        if (res.status === 201) {
          ta.value = ''; contact.value = ''; syncCount();
          if (!dlg.open) return;   // closed while sending: it still went through
          form.hidden = true; thanks.hidden = false;
          thanks.querySelector('h2').focus();
          closeT = setTimeout(function () { if (dlg.open) dlg.close(); }, CLOSE_AFTER);
          return;
        }
        var t;
        if (res.status === 400) t = ERR[res.j.error] || 'Could not send.';
        else if (res.status === 429) {
          var m = Math.max(1, Math.ceil((+res.j.retry_after || 60) / 60));
          t = 'Too many messages, try again in ' + m + (m === 1 ? ' minute.' : ' minutes.');
        } else if (res.status === 503) t = 'Feedback is off right now.';
        else t = 'Could not send.';
        say(t, true);
      }, function () {
        done();
        say('Could not send.', true);
      });
  });
})();
