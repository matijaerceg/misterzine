"""Firefox regression checks for mature visibility, preferences and shared views.

Run: python tools/test_mature_ui.py
Serves docs on an ephemeral localhost port; uses isolated browser profiles.
"""
import functools
import http.server
import json
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright, expect


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


ROOT = Path(__file__).resolve().parents[1]


def main():
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(ROOT / "docs")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/releases/"
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.firefox.launch()

            def new_page(seed=None, width=1440, height=1000):
                context = browser.new_context(viewport={"width": width, "height": height})
                # No account or remote media is needed for filter checks.
                context.route("**/*", lambda route: route.continue_()
                              if route.request.url.startswith(base.split('/releases/')[0])
                              else route.abort())
                if seed:
                    context.add_init_script("if (!sessionStorage.getItem('seeded')) {"
                        + "for (const [k,v] of Object.entries(" + json.dumps(seed)
                        + ")) localStorage.setItem(k,v); sessionStorage.setItem('seeded','1');}")
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                load(page)
                return page

            def load(page, url=base):
                page.goto(url)
                page.wait_for_function("typeof booted !== 'undefined' && booted")
                page.wait_for_function("document.getElementById('maturemenu') !== null")

            def source(page):
                if not page.locator('#srcdd').evaluate('(el) => el.open'):
                    page.locator('#srcsummary').click()

            def choose(page, value):
                source(page)
                page.locator(f'input[name=maturity][value={value}]').check()
                expect(page.locator(f'input[name=maturity][value={value}]')).to_be_checked()

            def rows(page):
                return page.evaluate('view.flatMap(d => d.grp ? d.members : [d]).map(d => ({k:d.k, mat:!!d.mat}))')

            page = new_page()
            source(page)
            expect(page.locator('input[name=maturity][value=hide]')).to_be_checked()
            expect(page.locator('#matureblur')).to_be_disabled()
            expect(page.locator('#matseg, #typemenu input[data-m]')).to_have_count(0)
            assert rows(page) and not any(r['mat'] for r in rows(page))
            choose(page, 'include')
            all_rows = rows(page)
            mature_rows = [r for r in all_rows if r['mat']]
            assert mature_rows and len(mature_rows) < len(all_rows)
            expect(page.locator('#matureblur')).to_be_checked()
            expect(page.locator('html')).to_have_attribute('data-mature', 'blur')
            page.locator('#matureblur').uncheck()
            choose(page, 'only')
            assert rows(page) == mature_rows
            expect(page.locator('#srcsummary')).to_contain_text('Mature')
            page.locator('#srcsummary').click()
            page.locator('#clear').click()
            assert page.evaluate('matureChoice') == 'include'
            assert rows(page) == all_rows
            expect(page.locator('html')).to_have_attribute('data-mature', 'show')
            choose(page, 'hide')
            page.locator('#srcsummary').click()
            page.locator('#q').fill('galaga')
            expect(page.locator('#clear')).to_be_enabled()
            page.locator('#clear').click()
            assert page.evaluate('matureChoice') == 'hide'
            load(page)
            choose(page, 'include')
            expect(page.locator('#matureblur')).not_to_be_checked()
            print('PASS modes, exact row sets, Clear filters, blur and reload')

            # Only mature is remembered by Source; Type All cannot reset it.
            choose(page, 'only')
            page.locator('[data-remember=src]').check()
            load(page)
            assert page.evaluate('matureChoice') == 'only'
            page.locator('#typesummary').click()
            page.locator('input[data-t=Console]').uncheck()
            page.locator('#typeall').click()
            assert page.evaluate('matureChoice') == 'only'
            preference_snapshot = "['mz-mature','mz-mature-blur','mz-filters-v1'].map(k => localStorage.getItem(k))"
            before = page.evaluate(preference_snapshot)
            load(page, base + '?view=1&m=clean')
            assert page.evaluate('matureChoice') == 'hide'
            choose(page, 'include')
            page.locator('#matureblur').check()
            load(page)
            assert page.evaluate('matureChoice') == 'include'
            expect(page.locator('html')).to_have_attribute('data-mature', 'blur')
            assert page.evaluate(preference_snapshot) == before
            page.locator('#restoresavedfilters').click()
            assert page.evaluate('matureChoice') == 'only'
            expect(page.locator('html')).to_have_attribute('data-mature', 'show')
            print('PASS Source memory, Type independence, shared refresh and revert')

            for old, choice, mode in [('hide', 'hide', 'hide'), ('show', 'include', 'show'), ('blur', 'include', 'blur')]:
                old_page = new_page({'mz-mature': old})
                assert old_page.evaluate('matureChoice') == choice
                expect(old_page.locator('html')).to_have_attribute('data-mature', mode)
                old_page.context.close()
            legacy = {'type': {'off': [], 'patchesOff': [], 'maturityOff': ['clean']}}
            old_page = new_page({'mz-mature': 'show', 'mz-filters-v1': json.dumps(legacy)})
            assert old_page.evaluate('matureChoice') == 'only'
            choose(old_page, 'include')
            load(old_page)
            assert old_page.evaluate('matureChoice') == 'include'
            old_page.context.close()
            print('PASS old Show/Blur/Hide and superseding old Type preference')

            # Shared maturity selections work even in a browser defaulting to Hide.
            visitor = new_page()
            for value, choice in [('mature', 'only'), ('-clean', 'only'), ('all', 'include'), ('clean', 'hide')]:
                load(visitor, base + '?view=1&m=' + value)
                assert visitor.evaluate('matureChoice') == choice
                if choice == 'only':
                    assert rows(visitor) and all(r['mat'] for r in rows(visitor))
                assert visitor.evaluate('localStorage.getItem("mz-mature")') is None
            print('PASS current and legacy shared links without changing preferences')

            phone = new_page(width=390, height=844)
            phone.locator('#filterssum').click()
            choose(phone, 'only')
            assert rows(phone) and all(r['mat'] for r in rows(phone))
            expect(phone.locator('#matureheading')).to_be_visible()
            assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
            print('PASS narrow Firefox layout and controls')
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
