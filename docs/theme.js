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
  if (mdd && mlist) {
    mdd.addEventListener('toggle', function () {
      if (mdd.open) capMenu();
      else if (dd && dd.open) dd.open = false;
    });
    document.addEventListener('click', function (e) {
      if (mdd.open && !mdd.contains(e.target)) mdd.open = false;
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && mdd.open) {
        mdd.open = false;
        e.stopImmediatePropagation();
        e.preventDefault();
      }
    }, true);
  }

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

  var saved = 'eva';
  try { saved = localStorage.getItem('mz-theme') || 'eva'; } catch (e) {}
  applyTheme(saved);
})();
