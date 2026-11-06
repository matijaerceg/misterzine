"""Headless Firefox checks against a local static preview; no account writes."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:11176/releases/')
    parser.add_argument('--output', default=str(Path.home() / '.codex/scratch/20261104-view-presets'))
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as pw:
        browser = pw.firefox.launch()

        def context(**options):
            ctx = browser.new_context(viewport={'width': 1440, 'height': 1000}, **options)
            ctx.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))
            return ctx

        def load(page, url=args.url):
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof booted !== 'undefined' && booted && presetRemember && DATA.length > 2000")

        def choose(page, preset):
            if not page.locator('#presets').evaluate('(el) => el.open'):
                page.locator('#presets > summary').click()
            page.locator(f'[data-preset="{preset}"]').click()
            expect(page.locator('#presetname')).not_to_contain_text('modified')

        def state(page):
            return page.evaluate('capturePresetDisplay()')

        def keys(page):
            return page.evaluate('view.flatMap(r => r.grp ? r.members : [r]).map(r => r.k).sort()')

        ctx = context()
        page = ctx.new_page()
        load(page)
        assert not errors, errors
        baseline = keys(page)
        expect(page.locator('#presetname')).to_have_text('Build date')
        section_band = page.locator('#rows .preset-section th').first.evaluate('el => getComputedStyle(el).backgroundColor')
        group_band = page.locator('#rows .grp td').first.evaluate('el => getComputedStyle(el).backgroundColor')
        plain = page.locator('#rows tr[data-i]:not(.grp) td').first.evaluate('el => getComputedStyle(el).backgroundColor')
        assert len({section_band, group_band, plain}) == 3
        expect(page.locator('#sectionpin span')).to_have_css('background-color', section_band)
        checks.append('Section, group and release backgrounds are distinct; the pinned heading matches its section')

        # A group's arrow acts independently of row selection, including on
        # phones where a second tap on the title opens the overlay panel.
        for phone, batch in [(False, False), (False, True), (True, False), (True, True)]:
            controls = ctx.new_page()
            if phone:
                controls.set_viewport_size({'width': 390, 'height': 844})
            load(controls)
            index = controls.evaluate('batch => flat.findIndex(r => r.grp && Boolean(r.bat) === batch)', batch)
            assert index >= 0
            controls.evaluate("i => revealIndex(i, 'center')", index)
            row = controls.locator(f'#rows tr.grp[data-i="{index}"]')
            for cell in row.locator('td').all():
                expect(cell).to_have_css('background-color', group_band)
            count = controls.evaluate('i => flat[i].members.length', index)
            unit = 'game' if batch else 'core'
            expect(row.locator('.gc')).to_have_text(f"{count} {unit}{'s' if count != 1 else ''}")
            arrow = row.get_by_role('button', expanded=False)
            bounds = arrow.bounding_box()
            height = row.bounding_box()['height']
            assert abs(bounds['width'] - height) < 1 and abs(bounds['height'] - height) < 1
            # Both header styles use the same compact icon and first-line inset,
            # even when the row (and hence the clickable square) is taller.
            icon = arrow.locator('svg').bounding_box()
            rem = controls.evaluate('parseFloat(getComputedStyle(document.documentElement).fontSize)')
            assert abs(icon['width'] - .5 * rem) < 1 and abs(icon['height'] - .5 * rem) < 1
            assert abs(icon['x'] - bounds['x'] - .75 * rem) < 1
            assert abs(icon['y'] - bounds['y'] - .75 * rem) < 1
            # Activate opposite corners well outside the glyph.
            arrow.click(position={'x': 1, 'y': 1})
            arrow = row.locator('.tw')
            expect(arrow).to_have_attribute('aria-expanded', 'true')
            expect(arrow.locator('svg')).to_have_css('transform', 'matrix(0, 1, -1, 0, 0, 0)')
            assert controls.locator('#rows tr.member').count() > 0
            expect(controls.locator('#rows tr.member td').first).to_have_css('background-color', plain)
            assert controls.evaluate('openRow === null')
            arrow.click(position={'x': bounds['width'] - 2, 'y': height - 2})
            expect(arrow).to_have_attribute('aria-expanded', 'false')
            assert controls.locator('#rows tr.member').count() == 0
            arrow.focus()
            controls.keyboard.press('Enter')
            expect(arrow).to_be_focused()
            expect(arrow).to_have_attribute('aria-expanded', 'true')
            controls.keyboard.press('Space')
            expect(arrow).to_have_attribute('aria-expanded', 'false')
            row.locator('.group-label').click()
            expect(arrow).to_have_attribute('aria-expanded', 'true')
            if phone:
                assert controls.evaluate('openRow === null')
                row.locator('.group-label').click()
                assert controls.evaluate("document.body.classList.contains('panel-open')")
            else:
                assert controls.evaluate('openRow?.grp')
                row.locator('.group-label').click()
                expect(arrow).to_have_attribute('aria-expanded', 'false')
            controls.close()
        checks.append('Game and core-batch headers share a small aligned arrow and independently toggle from the full square on desktop and phone')
        # Every catalogue-wide preset must preserve the complete visible catalogue.
        for preset in ['updated', 'debut', 'alphabetical', 'maker', 'year', 'core', 'cabinet']:
            choose(page, preset)
            assert keys(page) == baseline, preset
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), preset
            assert page.locator('#rows .preset-section').count() > 0, preset
            if preset == 'core':
                assert page.evaluate('view.every(r => !r.grp)')
                assert page.evaluate("new Set(view.map(r => currentPresetSection(r).label)).has('Single-game cores')")
            page.screenshot(path=str(output / f'desktop-{preset}.png'), animations='disabled')
        checks.append('Seven catalogue presets preserve every visible entry and render sections')

        # Ordinary column clicks get the same headings as presets, even when
        # starting from the date view. Core sections keep both implementations.
        choose(page, 'updated')
        columns = state(page)['columns']
        for key, mode in [('manufacturer', 'maker'), ('year', 'year'), ('core', 'core'), ('title', 'letter')]:
            header = page.locator(f'#hrow th[data-k="{key}"]')
            for _ in range(2):
                header.click()
                assert state(page)['section'] == mode
                assert state(page)['columns'] == columns and keys(page) == baseline
                assert page.locator('#rows .preset-section').count() > 0
                if key == 'core':
                    assert page.evaluate('view.every(r => !r.grp)')
        assert page.evaluate("""sortDir === -1 && view.filter(r => /^S/i.test(r.title))
          .map(r => r.title).every((title, i, arr) => i === 0 || COLL.compare(arr[i-1], title) >= 0)""")
        page.locator('#hrow th[data-k="title"]').click()  # A–Z
        checks.append('Direct Title, Maker, Year and Core sorts group both directions and preserve entries and columns')

        # Put a real row at a measured offset below the sticky column headings.
        # The second step makes the test independent of estimated virtual heights.
        def scroll_to_row(index, offset=0):
            page.evaluate("""([index, offset]) => {
                revealIndex(index, 'center');
                const row = ROWS.rows[index - vwA + 1];
                const edge = document.querySelector('#hrow th').getBoundingClientRect().bottom;
                WRAP.scrollTop += row.getBoundingClientRect().top - edge - offset;
            }""", [index, offset])
            page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')

        s, t = page.evaluate("['S','T'].map(letter => flat.findIndex(r => r.section && r.title === letter))")
        assert t - s > 150
        scroll_to_row(s + 110)
        pin = page.locator('#sectionpin')
        expect(pin.locator('span')).to_be_visible()
        expect(pin).to_have_text('S')
        assert page.evaluate('(s) => vwA > s', s)
        assert page.evaluate("""Math.abs(pinnedLabel.getBoundingClientRect().top -
            document.querySelector('#hrow th').getBoundingClientRect().bottom) < 1""")
        # The approaching T header physically pushes S out before taking over.
        scroll_to_row(t, 8)
        expect(pin).to_have_text('S')
        assert page.evaluate('pinnedHeight > 6 && pinnedHeight < 10'), page.evaluate('pinnedHeight')
        scroll_to_row(t + 4)
        expect(pin).to_have_text('T')
        scroll_to_row(s + 110)
        expect(pin).to_have_text('S')
        page.mouse.move(20, 40)
        page.screenshot(path=str(output / 'pinned-section-desktop.png'), animations='disabled')
        page.set_viewport_size({'width': 390, 'height': 844})
        scroll_to_row(s + 110)
        page.evaluate('WRAP.scrollLeft = WRAP.scrollWidth')
        page.wait_for_function('WRAP.scrollLeft > 0')
        expect(pin).to_have_text('S')
        expect(page.locator('#count')).to_have_text(str(len(baseline)))
        assert page.evaluate('Math.abs(pinnedLabel.getBoundingClientRect().left - WRAP.getBoundingClientRect().left) < 1')
        assert page.evaluate("document.querySelector('.jumps').getBoundingClientRect().top >= pinnedLabel.getBoundingClientRect().bottom")
        page.screenshot(path=str(output / 'pinned-section-phone.png'), animations='disabled')
        page.locator('#q').fill('zzzz-no-such-section-game')
        expect(page.locator('#rows .nomatch')).to_be_visible()
        expect(pin).to_have_attribute('hidden', '')
        page.locator('#qx').click()
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.locator('#hrow th[data-k="typesort"]').click()
        assert state(page)['section'] == 'none' and page.locator('#rows .preset-section').count() == 0
        expect(pin).to_have_attribute('hidden', '')
        checks.append('Sticky label tracks off-screen sections, slides out at boundaries, survives sideways scroll and clears on empty or unsectioned views')

        choose(page, 'updated')
        page.locator('#cols > summary').click()
        for key in ['mz', 'src', 'genre']:
            page.locator(f'#colsmenu input[data-k="{key}"]').check()
        page.locator('#cols > summary').click()
        for key in ['updated', 'date', 'mz', 'src', 'genre']:
            for _ in range(2):
                page.locator(f'#hrow th[data-k="{key}"]').click()
                assert state(page)['section'] == key and keys(page) == baseline
                # Every visible heading must start exactly one contiguous section.
                assert page.evaluate("""() => {
                    const labels = flat.filter(r => r.section).map(r => r.title);
                    return labels.length > 1 && new Set(labels).size === labels.length;
                }"""), key
                if key in ['updated', 'date', 'mz']:
                    assert page.evaluate("""() => {
                        const dates = view.map(row => row[sortKey] || '');
                        return dates.every((v, i) => !i || !v || dates[i-1] && sortDir * dates[i-1].localeCompare(v) <= 0);
                    }"""), key
                if key == 'src':
                    assert page.evaluate('view.every(r => !r.grp && (!r.src || currentPresetSection(r).label === (SRC_NAMES[r.src] || r.src)))')
        checks.append('Calendar, Source and Genre sorts preserve every entry, contiguous sections and chronological order in both directions')

        # Test the visible labels across local midnight while the page stays open.
        dates = context(timezone_id='America/Vancouver').new_page()
        dates.clock.set_fixed_time(dates.evaluate('new Date(2026, 10, 4, 23, 59, 59).toISOString()'))
        load(dates)
        dates.evaluate("""ingest([['a','2026-11-04'],['b','2026-11-03']].map(([k, updated]) =>
            ({k, title:k, base:'Computer', updated, src:'distribution_mister'})))""")
        expect(dates.locator('#rows .preset-section')).to_have_text(['Today · Nov 4', 'Yesterday · Nov 3'])
        dates.clock.set_fixed_time(dates.evaluate('new Date(2026, 10, 5, 0, 0, 1).toISOString()'))
        dates.evaluate('tickMeta()')
        expect(dates.locator('#rows .preset-section')).to_have_text(['Yesterday · Nov 4', 'Earlier this week'])
        dates.context.close()
        checks.append('Calendar headings roll over at the reader’s local midnight on an open page')

        # Filtering must retain the display label; adjusting columns must not.
        choose(page, 'maker')
        page.locator('#q').fill('donkey kong')
        page.wait_for_function('view.length > 0 && view.length < 10')
        expect(page.locator('#presetname')).to_have_text('Manufacturer')
        assert page.evaluate("view.some(r => r.grp && r.g === 'dkong')")
        page.locator('#cols > summary').click()
        page.locator('#colsmenu input[data-k="src"]').check()
        expect(page.locator('#presetname')).to_have_text('Manufacturer · modified')
        page.locator('#presets > summary').click()
        page.locator('#presetreset').click()
        expect(page.locator('#q')).to_have_value('donkey kong')
        expect(page.locator('#presetname')).to_have_text('Manufacturer')
        page.locator('#qx').click()
        checks.append('Search preserves preset; column edits mark modified; reset preserves search')

        # Sections must survive long virtual scrolls; keyboard skips headings.
        for preset in ['alphabetical', 'maker', 'year', 'core']:
            choose(page, preset)
            for fraction in [.25, .75, 1, 0]:
                page.evaluate('(f) => { WRAP.scrollTop = f * WRAP.scrollHeight; vWindow(); }', fraction)
                page.wait_for_timeout(100)
                assert page.evaluate("[...ROWS.querySelectorAll('tr[data-i]')].every(tr => rowEl(+tr.dataset.i) === tr)")
            page.evaluate('openRow = null')
            page.locator('#q').blur()
            page.keyboard.press('ArrowDown')
            assert page.evaluate('!!openRow && !openRow.section'), preset
            page.keyboard.press('Escape')
        checks.append('Virtual scrolling and keyboard navigation remain aligned with group headings')

        # Preserve existing same-game links under the core preset, which lists
        # members individually. The old group panel remains directly reachable.
        load(page, args.url + '?preset=core#misterzine-nonexistent')
        page.evaluate("location.hash = 'g:dkong'")
        page.wait_for_function("openRow && openRow.g === 'dkong'")
        expect(page.locator('#panel h3 a.openm')).to_have_count(2)
        page.keyboard.press('Escape')
        page.locator('#restoresavedfilters').click()
        checks.append('Existing same-game group permalinks still open both implementations')

        choose(page, 'cabinet')
        page.locator('#cols > summary').click()
        page.locator('#colsmenu input[data-k="src"]').check()
        expected = state(page)
        page.reload(wait_until='domcontentloaded')
        page.wait_for_function('booted && presetRemember')
        assert state(page) == expected
        expect(page.locator('#presetname')).to_have_text('Cabinet setup · modified')
        shared = page.evaluate('shareURL()')

        # Shared display is exact, visit-only, survives reload, and restores the
        # recipient's own preset and columns after Revert.
        recipient = context().new_page()
        load(recipient)
        choose(recipient, 'maker')
        saved = recipient.evaluate("localStorage.getItem('mz-view-preset')")
        load(recipient, shared)
        assert state(recipient) == expected
        assert recipient.evaluate("localStorage.getItem('mz-view-preset')") == saved
        recipient.reload(wait_until='domcontentloaded')
        recipient.wait_for_function('booted && presetRemember')
        assert state(recipient) == expected
        recipient.locator('#cols > summary').click()
        recipient.locator('#colsmenu input[data-k="flip"]').check()
        assert recipient.evaluate("localStorage.getItem('mz-view-preset')") == saved
        recipient.locator('#restoresavedfilters').click()
        assert state(recipient) == {k: v for k, v in json.loads(saved).items() if k != 'filterActive'}
        checks.append('Modified presets persist; shared display survives reload without replacing saved settings')

        # A maturity change rebuilds the catalogue during Revert. That render
        # must not replace the saved preset with the shared view being dismissed.
        saved_display = state(recipient)
        saved_preference = recipient.evaluate("localStorage.getItem('mz-view-preset')")
        load(recipient, args.url + '?preset=cabinet&m=all')
        assert recipient.evaluate("presetId === 'cabinet' && matureChoice === 'include'")
        recipient.reload(wait_until='domcontentloaded')
        recipient.wait_for_function('booted && presetRemember')
        assert recipient.evaluate("localStorage.getItem('mz-view-preset')") == saved_preference
        recipient.locator('#restoresavedfilters').click()
        assert recipient.evaluate("matureChoice === 'hide'")
        assert state(recipient) == saved_display
        assert recipient.evaluate("localStorage.getItem('mz-view-preset')") == saved_preference
        checks.append('Reverting a shared view restores saved display even when mature visibility rebuilds the catalogue')

        # Old shares still mean the canonical date order, even for someone
        # whose own view is now remembered as Manufacturer.
        load(recipient, args.url + '?view=1&q=donkey+kong')
        assert recipient.evaluate("sortKey === 'updated' && sortDir === -1 && sectionMode === 'updated'")
        recipient.locator('#restoresavedfilters').click()
        expect(recipient.locator('#presetname')).to_have_text('Manufacturer')
        # In-page collection navigation saves and restores display along with
        # existing query/filter state. No account or external writes involved.
        recipient.locator('#collection-favorites').click()
        choose(recipient, 'cabinet')
        recipient.locator('#collection-all').click()
        expect(recipient.locator('#presetname')).to_have_text('Manufacturer')
        recipient.locator('#collection-favorites').click()
        expect(recipient.locator('#presetname')).to_have_text('Cabinet setup')
        recipient.go_back()
        expect(recipient.locator('#presetname')).to_have_text('Manufacturer')
        checks.append('Legacy shared links and collection Back/Forward preserve their intended view')

        # Preserve access, type, source, year and search restrictions on apply.
        load(recipient, args.url + '?view=1&access=public&t=arcade&src=coinop&y=1980-2000&q=1941')
        restrictions = recipient.evaluate('JSON.stringify(captureDropdownFilters())')
        choose(recipient, 'core')
        assert recipient.evaluate('JSON.stringify(captureDropdownFilters())') == restrictions
        expect(recipient.locator('#q')).to_have_value('1941')
        assert recipient.evaluate("accessMode === 'public'")
        checks.append('Preset changes preserve search, access, type, source and year restrictions')

        # Genre options are opt-in, remembered locally, and only change the
        # explicit genre filter. Switching display keeps that narrowing.
        page.locator('#presets > summary').click()
        page.locator('#presetedit').click()
        expect(page.locator('[data-available="favorites"]')).to_have_count(0)
        page.locator('[data-available="shmups"]').check()
        page.locator('#presetavailabledone').click()
        choose(page, 'shmups')
        assert page.evaluate("view.every(r => r.genre === \"Shoot 'em up\")")
        choose(page, 'year')
        assert page.evaluate("enabledGenres.size === 1 && enabledGenres.has(\"Shoot 'em up\")")
        checks.append('Optional genre presets select their filter and preserve it when switching display')

        # Favorites are implementations, not umbrella rows; empty favorites
        # show a useful empty state and remain escapable through Clear filters.
        page.evaluate("clearAllFilters(); FAVS.clear(); FAVS.add('dkong'); FAVS.add('donkey-kong'); syncFavSummary(); apply()")
        choose(page, 'core')
        expect(page.locator('[data-preset="favorites"]')).to_have_count(0)
        page.locator('#favchip').click()
        assert keys(page) == ['dkong', 'donkey-kong']
        assert page.evaluate('view.every(r => !r.grp)')
        page.evaluate('FAVS.clear(); syncFavSummary(); apply()')
        expect(page.locator('#rows .nomatch')).to_be_visible()
        page.evaluate('clearAllFilters()')
        expect(page.locator('#presetname')).to_have_text('Core')
        assert keys(page) == baseline, page.evaluate('({types:[...enabledTypes], genres:[...enabledGenres], patches:[...enabledPatches], matureChoice, matureBlur, sources:[...enabledSrcs], yearFrom, yearTo, accessMode, favOnly, rows:view.length})')
        checks.append('Favorites retain independent core entries and empty state can be cleared')

        # Tablet, narrow docked pane and phone: controls and menus stay within
        # the viewport; the display row follows search and filters on phones.
        choose(page, 'maker')
        for width in [1440, 1100, 900, 768, 390, 320]:
            page.set_viewport_size({'width': width, 'height': 900})
            page.wait_for_timeout(120)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
            patreon = page.locator('header a[data-patreon]')
            expect(patreon).to_have_count(1)
            expect(patreon).to_be_visible()
            expect(patreon.locator('svg')).to_be_visible()
            assert patreon.inner_text().strip().lower() == 'patreon'
            assert page.locator('h1').evaluate('el => el.scrollWidth <= el.clientWidth + 1'), width
            for href in ['../frontend/', '../plex/', '../jellyfin/']:
                expect(page.locator(f'header a[href="{href}"]')).to_be_hidden()
            page.locator('#menusum').click()
            for href in ['../frontend/', '../plex/', '../jellyfin/']:
                expect(page.locator(f'#menudd a[href="{href}"]')).to_be_visible()
            expect(page.locator('#menudd [aria-current="page"]')).to_have_text('Core Tracker')
            page.keyboard.press('Escape')
            patreon.focus()
            page.keyboard.press('Enter')
            expect(page.locator('.patpop .ppgo')).to_have_attribute('href', 'https://www.patreon.com/MisterZine')
            page.keyboard.press('Escape')
            expect(patreon).to_be_focused()
            if width in [1440, 390, 320]:
                page.screenshot(path=str(output / f'header-{width}.png'), animations='disabled')
            page.locator('#presets > summary').click()
            menu = page.locator('#presetmenu').bounding_box()
            assert menu['x'] >= 0 and menu['x'] + menu['width'] <= width + 1, (width, menu)
            assert menu['y'] + menu['height'] <= 901, (width, menu)
            page.screenshot(path=str(output / f'menu-{width}.png'), animations='disabled')
            page.keyboard.press('Escape')
        checks.append('Preset controls and menu fit desktop, tablet and 320px phone widths')
        checks.append('Site destinations live in Menu and the labelled Patreon icon opens its dialog at every tested width')

        # Keyboard chooser keeps focus away from the underlying catalogue.
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.locator('#presets > summary').focus()
        page.keyboard.press('Enter')
        page.keyboard.press('ArrowDown')
        assert page.locator('[data-preset="updated"]').evaluate('(el) => document.activeElement === el')
        page.keyboard.press('Enter')
        expect(page.locator('#presetname')).to_have_text('Build date')
        checks.append('Chooser supports keyboard selection and returns focus to its button')
        # Unavailable storage and malformed preferences must leave a working
        # chooser, including reset and sharing.
        blocked_ctx = context()
        blocked_ctx.add_init_script("Storage.prototype.setItem = function() { throw new DOMException('Blocked', 'SecurityError'); }")
        blocked = blocked_ctx.new_page()
        load(blocked)
        choose(blocked, 'core')
        assert keys(blocked) == baseline
        assert 'preset=core' in blocked.evaluate('shareURL()')
        malformed_ctx = context()
        malformed_ctx.add_init_script("localStorage.setItem('mz-view-preset', JSON.stringify({preset:'bad',columns:'bad'})); localStorage.setItem('mz-presets-off', '{}')")
        malformed = malformed_ctx.new_page()
        load(malformed)
        choose(malformed, 'maker')
        assert keys(malformed) == baseline
        checks.append('Blocked storage and malformed saved presets do not break catalogue browsing')
        assert not errors, errors
        browser.close()
    report = {'browser': 'Firefox', 'url': args.url, 'checks': checks, 'page_errors': errors}
    (output / 'firefox-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
