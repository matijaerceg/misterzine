"""Check both Browse views against the local Trending API."""
import json
from playwright.sync_api import sync_playwright, expect
import custom_lists_preview as preview


def main():
    state = json.loads((preview.DEFAULT_STATE / 'state.json').read_text())
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(state['site'] + '/__preview__/anonymous')
        page.goto(state['site'] + '/releases/?collection=browse')
        with page.expect_response(lambda r: '/public/lists?' in r.url and 'sort=trending' in r.url) as result:
            page.locator('#lib-sort').select_option('trending')
        assert result.value.status == 200
        expect(page.locator('#lib-sort option')).to_have_text(['Recently updated', 'Newest lists', 'Trending'])
        page.goto(state['site'] + '/lists/?sort=trending')
        expect(page.locator('#sort')).to_have_value('trending')
        expect(page.locator('#loading')).to_be_hidden()
        expect(page.locator('#message')).to_have_text('')
        assert not errors, errors
        browser.close()
        print('PASS Trending in integrated and standalone Browse')


if __name__ == '__main__':
    main()
