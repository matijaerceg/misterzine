/* Shared theme picker for all three pages (home, release tracker, hardware).
   Builds the theme menu from THEMES and applies + persists the choice. The
   closed summary is a static "Theme" label straight from the markup (the active
   theme shows via the page itself + the highlighted menu row), so no width
   freeze is needed. The control is a plain <details id="themedd"> on every page
   (the release tracker's used to be a details.cols wired into the filter dropdown
   system; Tier 2 decoupled it). The pre-paint <script> in each <head> (reads
   mz-theme with a /^[a-z]+$/ guard) still sets data-theme before first paint.

   Add a theme = one THEMES entry here + one preview-colour block in theme.css
   (.menu button[data-set="slug"] { --sw1; --sw2 }). Nothing else. */
(function () {
  var THEMES = [
    ['light', 'Light'], ['dark', 'Dark'], ['virtualboy', 'Virtual'],
    ['spectrum', 'ZX'], ['amber', 'Amber'], ['phosphor', 'Phosphor'],
    ['eva', 'Unit-01'], ['vaporwave', 'Synth'], ['punchy', 'MiSTer-y'],
    ['commodore', 'C64'], ['workbench', 'Bench'], ['dmg', 'Game Boy'],
    ['pink', 'Pink'], ['icecream', 'Gelato'], ['riso', 'Riso'],
    ['famicom', 'Famicom'], ['pastel', 'Pastel']
  ];
  // the site Menu (every page, since 2026-09-17): outside click and Escape
  // close it; on open its list is capped to the room below so it stays
  // reachable where the page itself can't scroll (the tracker's app shell).
  // Closing it also folds the theme picker nested inside, so the menu always
  // reopens on its top level.
  var mdd = document.getElementById('menudd');
  var mlist = mdd && mdd.querySelector('.mlist');
  function capMenu() {
    if (!mlist) return;
    mlist.style.maxHeight = '';
    var room = document.documentElement.clientHeight - mlist.getBoundingClientRect().top - 8;
    if (mlist.scrollHeight > room) mlist.style.maxHeight = room + 'px';
  }
  // Hover tips: our own popover for every element carrying data-tip (header
  // buttons, menu rows, the status line), never the native title tooltip. A
  // site-menu row's tip sits beside the menu, to its left, level with the row
  // (under the menu when there's no room, i.e. phones); anything else gets it
  // just below itself, kept on-screen. Click-through, so leaving the element
  // closes it at once. The release tracker's table badges (td *) keep their
  // own popover and are skipped here.
  var tip = null;
  function closeTip() { if (tip) { tip.remove(); tip = null; } }
  function openTip(a) {
    closeTip();
    tip = document.createElement('div');
    tip.className = 'menutip';
    tip.textContent = a.getAttribute('data-tip');
    document.body.appendChild(tip);
    var r = a.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    var list = mlist && mlist.contains(a) ? mlist.getBoundingClientRect() : null;
    if (list && list.left - w - 6 >= 8) {
      tip.style.left = (list.left - w - 6) + 'px';
      tip.style.top = Math.max(8, Math.min(r.top, innerHeight - h - 8)) + 'px';
    } else if (list) {
      tip.style.left = Math.max(8, list.right - w) + 'px';
      tip.style.top = (list.bottom + 6) + 'px';
    } else {
      tip.style.left = Math.max(8, Math.min(r.left, innerWidth - w - 8)) + 'px';
      tip.style.top = (r.bottom + 6 + h <= innerHeight ? r.bottom + 6 : Math.max(8, r.top - h - 6)) + 'px';
    }
  }
  function tipTarget(e) {
    var a = e.target.closest ? e.target.closest('[data-tip]') : null;
    return a && !a.closest('td') ? a : null;
  }
  function leaveTip(e) { var a = tipTarget(e); if (a && !a.contains(e.relatedTarget)) closeTip(); }
  if (matchMedia('(hover: hover)').matches) {
    document.addEventListener('mouseover', function (e) { var a = tipTarget(e); if (a) openTip(a); });
    document.addEventListener('mouseout', leaveTip);
  }
  document.addEventListener('focusin', function (e) { var a = tipTarget(e); if (a) openTip(a); });
  document.addEventListener('focusout', leaveTip);
  document.addEventListener('click', closeTip);  // a click acts; the tip has said its piece
  if (mdd && mlist) {
    mdd.addEventListener('toggle', function () {
      closeTip();
      if (mdd.open) capMenu();
      else if (dd && dd.open) dd.open = false;
    });
    // (a click inside a popover a menu row opened, e.g. the RSS copy buttons,
    // is not an outside click either)
    document.addEventListener('click', function (e) {
      if (mdd.open && !mdd.contains(e.target) && !e.target.closest('.rsspop')) mdd.open = false;
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && mdd.open) {
        mdd.open = false;
        e.stopImmediatePropagation();
        e.preventDefault();
      }
    }, true);
  }

  // Patreon links in the header (the nav's, on every page) carry
  // data-patreon: a click opens a short note on what supporting
  // gets you, with the way through to Patreon, instead of dropping the visitor
  // on another site. They stay plain hrefs, so without JS, or with a modifier
  // key, they go straight there. Closes like the Menu (outside click, Escape
  // first in capture phase) and on the way through. data-patreon names the
  // spot: GoatCounter's 'patreon-<spot>' still counts clicks through to
  // Patreon, as the links' own data-goatcounter-click did before the note.
  var here = (document.currentScript && document.currentScript.src) || location.href;
  var pat = null, patFrom = null, patKey = false;
  function countPat(a) {
    if (window.goatcounter && window.goatcounter.count)
      window.goatcounter.count({ path: 'patreon-' + a.getAttribute('data-patreon'), title: 'Patreon link', event: true });
  }
  function placePat() {
    if (!pat) return;
    if (!patFrom.isConnected) { closePat(); return; }  // its link left the page
    var r = patFrom.getBoundingClientRect(), w = pat.offsetWidth;
    pat.style.left = Math.max(8, Math.min(r.left, innerWidth - w - 8)) + 'px';
    pat.style.top = (r.bottom + 6) + 'px';
  }
  function closePat(refocus) {
    var p = pat, from = patFrom;
    if (!p) return;
    pat = patFrom = null;  // first: removing a focused node can fire focusout into here
    p.remove();
    from.setAttribute('aria-expanded', 'false');
    if (refocus) from.focus();
  }
  function openPat(a, kbd) {
    closePat();
    closeTip();
    patFrom = a;
    pat = document.createElement('div');
    pat.className = 'patpop';
    pat.setAttribute('role', 'dialog');
    pat.setAttribute('aria-label', 'MisterZine on Patreon');
    pat.innerHTML =
      '<p class="pph">MisterZine on Patreon</p>' +
      '<p>Members get early access and additional features, as well as in-app and <a href="' +
      new URL('credits/', here).pathname + '">website credits</a>.</p>' +
      '<a class="ppgo" target="_blank" rel="noopener">Visit Patreon<span>↗</span></a>';
    var go = pat.querySelector('.ppgo');
    go.href = a.href;
    // close after the click has opened Patreon's tab, not during it
    go.addEventListener('click', function () { countPat(a); setTimeout(closePat, 0); });
    // tabbing out closes it; focus going nowhere (a click on its own text,
    // leaving the window) doesn't, and outside clicks close it below
    pat.addEventListener('focusout', function (e) {
      var to = e.relatedTarget;
      if (pat && to && !pat.contains(to) && to !== patFrom) closePat();
    });
    document.body.appendChild(pat);
    a.setAttribute('aria-expanded', 'true');
    placePat();
    if (kbd) go.focus();
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest ? e.target.closest('a[data-patreon]') : null;
    if (a) {
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) { countPat(a); return; }  // asked for Patreon itself
      e.preventDefault();
      if (patFrom === a) closePat(); else openPat(a, patKey || e.detail === 0);
    } else if (pat && !pat.contains(e.target)) closePat();
    patKey = false;
  });
  // opened from the keyboard, focus goes into the note (Firefox reports an
  // Enter-made click with detail 1, so the key itself is the signal)
  document.addEventListener('keydown', function (e) {
    patKey = e.key === 'Enter' && !!(e.target.closest && e.target.closest('a[data-patreon]'));
    if (e.key === 'Escape' && pat) {
      closePat(pat.contains(document.activeElement));  // hand focus back only if it was inside
      e.stopImmediatePropagation();
      e.preventDefault();
    }
  }, true);
  addEventListener('resize', placePat);
  addEventListener('scroll', placePat, true);

  // header logo height (every page with a masthead): the logo spans the title
  // block, top of the title to the bottom of the line under it. Each page's
  // CSS seeds --titleh with the one-line sum; this keeps it equal to the
  // block's real height, so a wrapped title (tablet widths, long titles) or a
  // late-filled byline grows the logo with it.
  var mast = document.querySelector('.masthead');
  var block = mast && mast.querySelector(':scope > :not(.brand)');
  if (mast && block && 'ResizeObserver' in window) {
    new ResizeObserver(function () {
      mast.style.setProperty('--titleh', block.getBoundingClientRect().height + 'px');
    }).observe(block);
  }

  // site-nav labels (nav.css .pill .long/.short): the long ones (CORE TRACKER,
  // ARCADE FRONTEND) only while the nav and the controls beside it (Sign in,
  // Menu) still share one row; otherwise html.navshort swaps in the short ones
  // phones always get. Each check starts from the long labels, so widening the
  // window brings them back. The header is observed rather than the window
  // because the tracker's docked panel narrows it without a resize; the check
  // is a pure function of the header's width, so its own reflow settles.
  var seg = document.querySelector('.segnav');
  var navrow = seg && (seg.closest('.hctl') || seg.parentElement);
  var hdr = seg && seg.closest('header');
  if (navrow && hdr) {
    var fitNav = function () {
      var root = document.documentElement;
      root.classList.remove('navshort', 'navwrap');
      if (getComputedStyle(seg).display === 'none') return;  // folded into the Menu (nav.css .nv): nothing to fit
      var first = navrow.firstElementChild, last = navrow.lastElementChild;
      var below = function () { return last.getBoundingClientRect().top >= first.getBoundingClientRect().bottom - 2; };
      if (below()) root.classList.add('navshort');
      // still below with the short labels (or stacked by page CSS, as the
      // hardware page does at tablet widths): nav.css hides the rule that
      // splits the links from the controls, which would end a line there
      if (below()) root.classList.add('navwrap');
    };
    fitNav();
    if ('ResizeObserver' in window) new ResizeObserver(fitNav).observe(hdr);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitNav);  // the condensed face changes the widths
  }

  var dd = document.getElementById('themedd');
  var sum = document.getElementById('themesum');
  var menu = dd && dd.querySelector('.menu');
  if (!dd || !sum || !menu) return;

  // build the theme buttons and prepend them BEFORE any existing menu content,
  // so the inline shadow-mask row (home + release tracker) stays after them
  var frag = document.createDocumentFragment();
  var btns = THEMES.map(function (t) {
    var b = document.createElement('button');
    b.type = 'button';
    b.dataset.set = t[0];
    b.textContent = t[1];
    frag.appendChild(b);
    return b;
  });
  menu.insertBefore(frag, menu.firstChild);

  var slugs = THEMES.map(function (t) { return t[0]; });
  function applyTheme(t) {
    if (slugs.indexOf(t) < 0) t = 'eva';  // Unit-01 is the site default (since 2026-09-10)
    document.documentElement.setAttribute('data-theme', t);
    btns.forEach(function (b) {
      b.setAttribute('aria-pressed', b.dataset.set === t);
    });
  }

  // picking a theme leaves the menu OPEN on purpose: themes apply live, so the
  // list doubles as a preview you click through (outside-click / Esc dismiss it)
  btns.forEach(function (b) {
    b.addEventListener('click', function () {
      applyTheme(b.dataset.set);  // apply BEFORE persisting: a throwing setItem
      try { localStorage.setItem('mz-theme', b.dataset.set); } catch (e) {}  // (private mode) must not cost the switch itself
    });
  });

  // On open, cap the menu's height to the room below it so the tall list stays
  // reachable where the page itself can't scroll (the release tracker's app
  // shell). Position-aware, so it's correct wherever the control sits in the
  // header (it can wrap to a second row on the release tracker). This is the
  // vertical half of what positionMenu() used to do for it via details.cols; the
  // menu is right-anchored (CSS right:0), so no horizontal clamp is needed.
  dd.addEventListener('toggle', function () {
    if (!dd.open) return;
    if (mdd && mdd.contains(dd)) { capMenu(); return; }  // nested: the fold grows the site menu's list, cap THAT
    menu.style.maxHeight = '';
    var room = document.documentElement.clientHeight - menu.getBoundingClientRect().top - 8;
    if (menu.scrollHeight > room) menu.style.maxHeight = room + 'px';
  });
  // click outside closes the menu
  document.addEventListener('click', function (e) {
    if (dd.open && !dd.contains(e.target)) dd.open = false;
  });
  // Escape closes the menu FIRST, ahead of everything: capture phase + stop, so
  // the release tracker's Esc ladder (clear search / close the panel) never fires
  // while the menu is the topmost open thing. When the menu is closed, do nothing
  // and let the event through to that ladder unchanged.
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && dd.open) {
      dd.open = false;
      e.stopImmediatePropagation();
      e.preventDefault();
    }
  }, true);

  // ---- site notice: a dated card in the corner, shown once per visitor ----
  // To post a new notice: give it a NEW id (letters, digits, dashes), set the
  // first and last day it shows (inclusive, the visitor's local date) and the
  // text. Closing it is remembered in this browser (mz-notice = id) and, when
  // signed in, on the account (PUT /me/notice), so one person sees each notice
  // once across their browsers. Outside the window nothing shows. To look at it
  // regardless of the window or a past close, open any page with ?notice=preview.
  // `page` limits it to one section of the site by path ('/releases/' = the
  // tracker); leave it out to show on every page. Set NOTICE to null when
  // there is nothing to say.
  var NOTICE = {
    id: 'faster-tracker-2026-10',
    page: '/releases/',
    from: '2026-10-20',
    to: '2026-10-24',
    title: 'A faster tracker',
    html: '<p>As of October 20 this page should feel a lot more responsive: scrolling, filtering, sorting, and selection ' +
          'no longer stall. Thanks for continuing to report issues!</p>' +
          '<p>If you find the site useful, consider supporting me on ' +
          '<a href="https://www.patreon.com/MisterZine" target="_blank" rel="noopener">Patreon</a>.</p>' +
          '<p class="snsig">-Matija</p>'
  };
  (function () {
    if (!NOTICE || !/^[a-z0-9-]{1,40}$/.test(NOTICE.id)) return;
    if (NOTICE.page && location.pathname.indexOf(NOTICE.page) !== 0) return;
    var preview = /[?&]notice=preview(&|$)/.test(location.search);
    var d = new Date(), today = d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
    if (!preview && (today < NOTICE.from || today > NOTICE.to)) return;
    var seen = null, token = null;
    try { seen = localStorage.getItem('mz-notice'); token = localStorage.getItem('mz-token'); } catch (e) {}
    if (!preview && seen === NOTICE.id) return;
    // same session + API rules as the tracker: the bearer from /auth/, the live
    // service, overridable only on localhost for testing (mz-api)
    var api = 'https://api.misterzine.fyi';
    var local = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
    try { if (local && localStorage.getItem('mz-api')) api = localStorage.getItem('mz-api'); } catch (e) {}
    if (!token || !/^[A-Za-z0-9_-]{40,}$/.test(token)) token = null;
    function remember() {
      try { localStorage.setItem('mz-notice', NOTICE.id); } catch (e) {}
      if (token) fetch(api + '/me/notice', {
        method: 'PUT', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: NOTICE.id })
      }).catch(function () {});
    }
    function show() {
      if (document.getElementById('sitenote')) return;
      var box = document.createElement('aside');
      box.id = 'sitenote';
      box.className = 'sitenote';
      box.setAttribute('aria-label', 'Site notice');
      box.innerHTML = '<p class="snh"></p><button type="button" class="snx" aria-label="Close">×</button><div class="snb"></div>';
      box.querySelector('.snh').textContent = NOTICE.title;
      box.querySelector('.snb').innerHTML = NOTICE.html;
      box.querySelector('.snx').addEventListener('click', function () { box.remove(); remember(); });
      document.body.appendChild(box);
    }
    if (!token || preview) { show(); return; }
    // signed in: skip it when this account closed it in another browser; a
    // failed or stale check (offline, signed out elsewhere) just shows the card
    fetch(api + '/me', { headers: { Authorization: 'Bearer ' + token } }).then(function (r) {
      return r.ok ? r.json() : null;
    }).then(function (me) {
      if (me && me.notice === NOTICE.id) { try { localStorage.setItem('mz-notice', NOTICE.id); } catch (e) {} return; }
      show();
    }, show);
  })();

  var saved = 'eva';
  try { saved = localStorage.getItem('mz-theme') || 'eva'; } catch (e) {}
  applyTheme(saved);
})();
