"""Quick pins and public card previews against the preserved local preview."""
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect
import custom_lists_preview as preview


def main():
    state = json.loads((preview.DEFAULT_STATE / 'state.json').read_text(encoding='utf-8'))
    base, api = state['site'], state['api']
    assert all(urlparse(url).hostname in {'localhost', '127.0.0.1'} for url in (base, api))
    auth = {'Authorization': 'Bearer ' + state['tester_token']}
    shots = Path.home() / '.codex/project-notes/misterzine/custom-lists-workspace-qa'
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        request, fixtures, errors = context.request, [], []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def human_content():
            return [request.get(api + path, headers={'Authorization': 'Bearer ' + state[token]}).json()
                    for token in ('token', 'follower_token') for path in ('/collections', '/favorites')]

        original = human_content()

        def create(title, keys, public=False):
            response = request.post(api + '/lists', headers=auth, data={'title': title, 'keys': keys})
            assert response.status == 201
            row = response.json()
            fixtures.append(row['id'])
            if public:
                response = request.put(api + '/lists/' + row['id'], headers=auth, data={**row, 'visibility': 'public'})
                assert response.status == 200
                row = response.json()
            return row

        def pin(row):
            return page.locator('#collection-menu [data-pin="' + row['id'] + '"]')

        def card(row):
            return page.locator('#lib-directory-cards .list-card').filter(has=page.get_by_role('heading', name=row['title'], exact=True))

        try:
            request.put(api + '/me/profile', headers=auth, data={'display_name': 'Preview curator'})
            rows = [row for row in request.get(base + '/releases/data.json').json() if row.get('k') and row.get('core')][:10]
            keys = [rows[0]['k'], 'preview_missing_key'] + [row['k'] for row in rows[1:]]
            sample = create('Shortcut preview arcade picks', keys, True)
            empty = create('Shortcut preview empty collection', [], True)
            private = create('A long private collection name for the quick pin menu', [])
            page.goto(base + '/__preview__/tester')
            page.goto(base + '/releases/?collection=all')
            page.wait_for_function('booted')
            if page.locator('#panel .close').is_visible():
                page.locator('#panel .close').click()
            page.evaluate('window.sameDocument = 321')
            page.locator('#collection-summary').click()
            pin(sample).focus()
            pin(sample).press('Enter')
            expect(pin(sample)).to_have_attribute('aria-pressed', 'true')
            expect(pin(sample)).to_have_attribute('aria-disabled', 'false')
            expect(pin(sample)).to_be_focused()
            expect(page.locator('#collection-picker')).to_have_attribute('open', '')
            expect(page.locator('#collection-all')).to_have_attribute('aria-current', 'page')
            expect(page.locator('#collection-pins a[data-id="' + sample['id'] + '"]')).to_be_visible()
            assert page.evaluate('window.sameDocument') == 321
            assert page.locator('#collection-pins [title], #collection-menu [title]').count() == 0

            page.locator('#collection-menu [data-collection="' + sample['id'] + '"]').click()
            expect(page.locator('#clname')).to_have_text(sample['title'])
            page.locator('#collection-summary').click()
            pin(sample).click()
            expect(pin(sample)).to_have_attribute('aria-pressed', 'false')
            expect(page.locator('#collection-summary')).to_have_class(re.compile(r'\bactive\b'))
            expect(page.locator('#collection-menu [data-collection][aria-current=page]')).to_have_text(sample['title'])
            expect(page.locator('#clpin')).to_have_text('Pin as tab')

            # A failed write leaves the list and menu usable, including keyboard focus.
            page.route('**/pins/' + sample['id'], lambda route: route.abort())
            pin(sample).click()
            expect(page.locator('#collection-notice')).to_contain_text('Could not reach')
            expect(pin(sample)).to_have_attribute('aria-disabled', 'false')
            expect(pin(sample)).to_have_attribute('aria-pressed', 'false')
            expect(pin(sample)).to_be_focused()
            page.unroute('**/pins/' + sample['id'])
            pin(sample).click()
            expect(pin(sample)).to_have_attribute('aria-pressed', 'true')
            pin(private).click()
            expect(pin(private)).to_have_attribute('aria-pressed', 'true')
            for width in (1440, 390, 320):
                page.set_viewport_size({'width': width, 'height': 844})
                expect(pin(private)).to_be_visible()
                page.wait_for_function("(() => { const b = document.getElementById('collection-menu').getBoundingClientRect(); return b.left >= 0 && b.right <= innerWidth; })()")
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                if width < 400:
                    expect(page.locator('#collection-pins a[data-id="' + private['id'] + '"]')).to_be_hidden()
                    expect(page.locator('#collection-menu .collection-group').get_by_text('Pinned', exact=True)).to_be_visible()
                    page.wait_for_function("id => document.querySelector('[data-pin=\"' + id + '\"]')?.getBoundingClientRect().width >= 44", arg=private['id'])
                page.mouse.move(0, 0)
                page.screenshot(path=str(shots / f'quick-pins-{width}.png'))
            pin(private).click()
            expect(pin(private)).to_have_attribute('aria-pressed', 'false')
            expect(page.locator('#collection-picker')).to_have_attribute('open', '')
            page.locator('#collection-summary').click()
            print('PASS quick pins, keyboard focus, current list, narrow folding, failed writes and no navigation')

            # No full-list request is made until a card is expanded.
            reads = []
            page.on('request', lambda req: reads.append(req.url) if '/public/lists/' in req.url else None)
            page.set_viewport_size({'width': 1440, 'height': 900})
            page.locator('#collection-browse').click()
            page.locator('#lib-search').fill('Shortcut preview')
            expect(page.locator('#lib-directory-cards .list-card')).to_have_count(2)
            expect(card(sample)).to_be_visible()
            expect(card(empty)).to_be_visible()
            assert reads == []
            details = card(sample).locator('.list-preview')
            summary = details.locator('summary')
            summary.focus()
            summary.press('Enter')
            expect(details.locator('li')).to_have_count(8)
            expect(details).to_contain_text(rows[0]['title'])
            expect(details).to_contain_text(rows[0]['core'])
            expect(details).to_contain_text('Unavailable entry')
            expect(details).to_contain_text('Showing 8 of 11 entries')
            expect(page.locator('#collection-browse')).to_have_attribute('aria-current', 'page')
            assert page.evaluate('window.sameDocument') == 321
            expect(summary).to_be_focused()
            card(empty).locator('summary').click()
            expect(card(empty)).to_contain_text('This list has no games yet.'); card(empty).get_by_role('button', name='Close preview').click(); summary.click(); expect(details.locator('li')).to_have_count(8)
            for width in (1440, 390, 320):
                page.set_viewport_size({'width': width, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                details.scroll_into_view_if_needed()
                page.screenshot(path=str(shots / f'game-preview-{width}.png'))
            details.get_by_role('button', name='Close preview').click()
            expect(details.locator('li')).to_have_count(0)
            page.route('**/public/lists/' + sample['id'], lambda route: route.abort())
            summary.click()
            expect(details.get_by_role('button', name='Retry preview')).to_be_visible()
            page.unroute('**/public/lists/' + sample['id'])
            details.get_by_role('button', name='Retry preview').click()
            expect(details.locator('li')).to_have_count(8)

            # A collapsed or abandoned request cannot put stale games back on screen.
            details.get_by_role('button', name='Close preview').click()
            held = []
            page.route('**/public/lists/' + sample['id'], lambda route: held.append(route))
            summary.click()
            expect(details).to_contain_text('Loading games...')
            page.wait_for_timeout(100)
            assert held
            page.locator('#collection-all').click()
            held[0].fulfill(status=200, content_type='application/json', body=json.dumps(sample))
            page.unroute('**/public/lists/' + sample['id'])
            page.locator('#collection-browse').click()
            expect(details).not_to_have_attribute('open', '')
            expect(details.locator('li')).to_have_count(0)

            # Reopening fetches edited content and checks whether sharing was withdrawn.
            response = request.put(api + '/lists/' + sample['id'], headers=auth, data={**sample, 'keys': [rows[-1]['k']]})
            assert response.status == 200
            sample = response.json()
            summary.click()
            expect(details.locator('li')).to_have_count(1)
            expect(details).to_contain_text(rows[-1]['title'])
            details.get_by_role('button', name='Close preview').click()
            response = request.put(api + '/lists/' + sample['id'], headers=auth, data={**sample, 'visibility': 'private'})
            assert response.status == 200
            sample = response.json()
            summary.click()
            expect(details).to_contain_text('no longer shared')
            expect(details.locator('li')).to_have_count(0)
            print('PASS lazy previews, exact entries, missing/empty lists, limits, retry, cancellation and withdrawn sharing')

            response = request.put(api + '/lists/' + sample['id'], headers=auth, data={**sample, 'visibility': 'public'})
            assert response.status == 200
            sample = response.json()
            page.goto(base + '/__preview__/anonymous')
            page.goto(base + '/releases/?collection=browse')
            page.locator('#lib-search').fill(sample['title'])
            card(sample).locator('summary').click()
            expect(card(sample).locator('.list-preview li')).to_have_count(1)
            card(sample).get_by_role('link', name='Preview curator', exact=True).click()
            curator = page.locator('#lib-curator-cards .list-card').filter(has=page.get_by_role('heading', name=sample['title'], exact=True))
            curator.locator('summary').click()
            expect(curator.locator('.list-preview li')).to_have_count(1)
            page.goto(base + '/lists/?q=' + sample['title'])
            legacy = page.locator('#directory-cards .list-card').filter(has=page.get_by_role('heading', name=sample['title'], exact=True))
            legacy.locator('summary').click()
            expect(legacy.locator('.list-preview li')).to_have_count(1)
            assert not errors, errors
            print('PASS anonymous and curator previews, standalone library, zero JavaScript errors')
        finally:
            for ident in fixtures:
                request.delete(api + '/pins/' + ident, headers=auth)
                response = request.get(api + '/lists/' + ident, headers=auth)
                if response.status == 200:
                    request.delete(api + '/lists/' + ident, headers=auth, data={'version': response.json()['version']})
            assert human_content() == original, 'Owner or follower content changed'
            browser.close()


if __name__ == '__main__':
    main()
