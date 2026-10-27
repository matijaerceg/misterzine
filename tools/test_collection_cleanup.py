"""Local browser checks for account favorites, collection controls, and list copying."""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect
import custom_lists_preview as preview


def main():
    state = json.loads((preview.DEFAULT_STATE / 'state.json').read_text(encoding='utf-8'))
    base, api = state['site'], state['api']
    assert all(urlparse(url).hostname in {'localhost', '127.0.0.1'} for url in [base, api])
    prefix = 'Collection cleanup ' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    auth = {'Authorization': 'Bearer ' + state['tester_token']}
    follower_auth = {'Authorization': 'Bearer ' + state['follower_token']}
    shots = Path.home() / '.codex/project-notes/misterzine/custom-lists-workspace-qa'
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        page.on('dialog', lambda d: d.accept())
        errors, fixtures = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        data = context.request.get(base + '/releases/data.json').json()
        first, second = [next(row['k'] for row in data if row.get('k') and row['title'].startswith(title)) for title in ['1944', '1942']]
        original_favs = set(context.request.get(api + '/favorites', headers=auth).json()['keys'])
        try:
            page.goto(base + '/__preview__/anonymous')
            page.wait_for_function("typeof booted !== 'undefined' && booted")
            page.evaluate("key => localStorage.setItem('mz-favs', JSON.stringify([key]))", first)
            page.goto(base + '/releases/?collection=all#' + second)
            page.reload()
            expect(page.locator('#collection-favorites')).to_have_text('Favorites (1)')
            expect(page.locator('#favlegacyinfo')).to_be_visible()
            page.locator('#panel button.fav').first.click()
            expect(page.locator('#favsignin')).to_be_visible()
            assert page.evaluate("JSON.parse(localStorage.getItem('mz-favs'))") == [first]
            page.locator('#favsignin [data-clclose]').click()
            page.locator('#favdd > summary').click()
            expect(page.locator('#favcopy')).to_be_hidden()
            expect(page.locator('#favclearall')).to_be_disabled()
            assert page.locator('#favctl details').count() == 0
            page.locator('#favdd > summary').click()
            page.locator('#favtoggle').click()
            assert 'collection=all' in page.url
            expect(page.locator('#favtoggle')).to_have_attribute('aria-pressed', 'true')
            page.locator('#favtoggle').click()
            page.goto(base + '/releases/?fav=' + second)
            page.locator('#favadd').click()
            expect(page.locator('#favsignin')).to_be_visible()
            assert page.evaluate("JSON.parse(localStorage.getItem('mz-favs'))") == [first]
            page.locator('#favsignin [data-clclose]').click()
            print('PASS signed-out stars and old-link imports require sign-in; legacy favorites remain unchanged; filter has no management controls')

            context.request.put(api + '/favorites/' + second, headers=auth)
            page.goto(base + '/__preview__/tester')
            page.wait_for_function("typeof booted !== 'undefined' && booted")
            page.goto(base + '/releases/?collection=favorites')
            page.locator('#favdd > summary').click()
            expect(page.locator('#favlegacy')).to_be_visible()
            page.locator('#favlegacy').click()
            expect(page.locator('#favlegacy')).to_be_hidden()
            saved = set(context.request.get(api + '/favorites', headers=auth).json()['keys'])
            assert original_favs | {first, second} <= saved
            page.locator('#favdd > summary').click()
            print('PASS explicit browser-favorites import unions with account favorites')

            created = context.request.post(api + '/lists', headers=auth, data={'title': prefix, 'description': 'Independent copy test', 'keys': [first, second]}).json()
            fixtures.append((created['id'], auth))
            page.goto(base + '/releases/?list=' + created['id'])
            expect(page.locator('#clstate')).to_have_text('Private')
            assert 'Saved' not in page.locator('#clbar').inner_text()
            page.locator('#favtoggle').click()
            assert parse_qs(urlparse(page.url).query)['list'] == [created['id']]
            page.locator('#clcopylist').click()
            page.locator('#clcreateyes').click()
            page.wait_for_url('**/releases/?editList=*')
            copy_id = parse_qs(urlparse(page.url).query)['editList'][0]
            fixtures.append((copy_id, auth))
            copied = context.request.get(api + '/lists/' + copy_id, headers=auth).json()
            assert copied['keys'] == created['keys'] and copied['visibility'] == 'private'
            expect(page.locator('#clsave')).to_have_text('Save changes')
            expect(page.locator('.cleditorlabel')).to_be_visible()
            page.screenshot(path=str(shots / 'contained-editor.png'))
            # A normal departure discards; server data is never changed implicitly.
            page.locator('#cldetailsbtn').click()
            page.locator('#cltitle').fill(prefix + ' unsaved')
            page.locator('#cldetailsform button[type=submit]').click()
            page.reload()
            expect(page.locator('#clname')).to_have_text(copied['title'])
            expect(page.locator('#clsave')).to_be_disabled()
            print('PASS private independent copy, editor-only save status, and confirmed browser departure discards changes')

            profile = context.request.get(api + '/me/profile', headers=auth).json()
            if not profile:
                context.request.put(api + '/me/profile', headers=auth, data={'display_name': 'Collection test curator'})
            shared = context.request.put(api + '/lists/' + created['id'], headers=auth, data={**created, 'visibility': 'unlisted'})
            assert shared.status == 200
            created = shared.json()
            visitor = browser.new_context()
            other = visitor.new_page()
            other.on('pageerror', lambda e: errors.append(str(e)))
            other.goto(base + '/__preview__/follower')
            other.wait_for_function("typeof booted !== 'undefined' && booted")
            other.goto(base + '/releases/?list=' + created['id'])
            other.locator('#clcopylist').click()
            other.locator('#clcreateyes').click()
            other.wait_for_url('**/releases/?editList=*')
            follower_copy = parse_qs(urlparse(other.url).query)['editList'][0]
            fixtures.append((follower_copy, follower_auth))
            assert context.request.get(api + '/lists/' + follower_copy, headers=follower_auth).json()['keys'] == created['keys']
            visitor.close()
            print('PASS another signed-in user can make an independent private copy of an accessible unlisted list')
            page.goto(base + '/releases/?list=' + created['id'])
            page.locator('#clcopylist').click()
            context.request.delete(api + '/lists/' + created['id'], headers=auth, data={'version': created['version']})
            page.locator('#clcreateyes').click()
            expect(page.locator('#clcreatestatus')).to_contain_text('No copy was created')
            assert context.request.get(api + '/lists/' + copy_id, headers=auth).json()['keys'] == copied['keys']
            print('PASS withdrawn/deleted originals cannot be copied; existing independent copies remain intact')
            page.locator('#clcreate [data-clclose]').click()
            for width in [390, 1280]:
                page.set_viewport_size({'width': width, 'height': 844})
                page.goto(base + '/releases/?collection=favorites')
                expect(page.locator('#collection-favorites')).to_have_attribute('aria-current', 'page')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(shots / ('collection-tabs-' + str(width) + '.png')))
            assert not errors, errors
            print('PASS desktop/mobile collection tabs and account favorites controls; no JavaScript errors')
        finally:
            for list_id, headers in fixtures:
                current = context.request.get(api + '/lists/' + list_id, headers=headers)
                if current.status == 200 and current.json()['title'].startswith(prefix):
                    context.request.delete(api + '/lists/' + list_id, headers=headers, data={'version': current.json()['version']})
            current = set(context.request.get(api + '/favorites', headers=auth).json()['keys'])
            for key in current - original_favs:
                context.request.delete(api + '/favorites/' + key, headers=auth)
            for key in original_favs - current:
                context.request.put(api + '/favorites/' + key, headers=auth)
            browser.close()


if __name__ == '__main__':
    main()
