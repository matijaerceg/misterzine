#!/usr/bin/env python3
"""Check local draft recovery and touch editing against the real preview Worker.

Uses only the dedicated tester account and uniquely named, cleaned-up fixtures.
The human preview owner's account, profile, and lists are never modified.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
import custom_lists_preview as preview


def more(page):
    if not page.locator("#clmore").evaluate("element => element.open"):
        page.locator("#clmoresummary").click()


def change_title(page, value):
    more(page)
    page.locator("#cldetailsbtn").click()
    expect(page.locator("#cldetails")).to_be_visible()
    page.locator("#cltitle").fill(value)
    page.locator('#cldetailsform button[type="submit"]').click()
    expect(page.locator("#clstate")).to_contain_text("Unsaved")


def recovery_tests(browser, base, api, token, follower_token, prefix, screenshots):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.on("dialog", lambda dialog: dialog.accept())
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    auth = {"Authorization": "Bearer " + token}
    created = context.request.post(api + "/lists", headers=auth, data={"title": prefix, "keys": []})
    assert created.status == 201
    list_id = created.json()["id"]
    storage_key = "mz-list-draft:" + list_id
    editor_url = base + "/releases/?editList=" + list_id

    def read():
        response = context.request.get(api + "/lists/" + list_id, headers=auth)
        assert response.status == 200
        return response.json()

    try:
        page.goto(base + "/__preview__/tester")
        page.wait_for_function("typeof booted !== 'undefined' && booted")
        page.goto(editor_url)
        expect(page.locator("#clname")).to_have_text(prefix)
        pending = prefix + " pending"
        change_title(page, pending)
        page.locator("#q").fill("1944")
        expect(page.locator(".clpick").first).to_have_attribute("aria-label", re.compile("1944"))
        chosen = page.locator(".clpick").first.get_attribute("data-list-key")
        page.locator(f'.clpick[data-list-key="{chosen}"]').check()
        more(page)
        expect(page.locator("#cldraftnote")).to_be_visible()
        page.wait_for_function("key => JSON.parse(localStorage.getItem(key)).keys.length === 1", arg=storage_key)
        saved = read()
        assert saved["title"] == prefix and saved["keys"] == []
        page.reload()
        expect(page.locator("#clname")).to_have_text(pending)
        expect(page.locator("#clstate")).to_contain_text("Unsaved")
        expect(page.locator("#clselected")).to_have_text("Selected (1)")
        assert read() == saved, "Reload must not auto-save recovered content."
        page.locator("#clsave").click()
        expect(page.locator("#clstate")).not_to_contain_text("Unsaved")
        assert read()["title"] == pending and read()["keys"] == [chosen]
        assert page.evaluate("key => localStorage.getItem(key)", storage_key) is None
        print("PASS pending title/selection recover after reload; explicit Save writes and clears recovery")

        private_pending = prefix + " private pending"
        change_title(page, private_pending)

        def unavailable_owner(route):
            route.abort()

        page.route(api + "/lists/" + list_id, unavailable_owner)
        page.reload()
        expect(page.locator("#clretry")).to_be_visible()
        assert private_pending not in page.locator("body").inner_text()
        expect(page.locator(".clpick")).to_have_count(0)
        assert page.evaluate("key => localStorage.getItem(key)", storage_key)
        page.unroute(api + "/lists/" + list_id, unavailable_owner)
        page.locator("#clretry").click()
        expect(page.locator("#clname")).to_have_text(private_pending)
        assert read()["title"] == pending
        print("PASS recovery stays hidden until the service successfully verifies list ownership")

        latest = read()
        latest["title"] = prefix + " remote"
        changed = context.request.put(api + "/lists/" + list_id, headers=auth, data={
            key: latest[key] for key in ["title", "description", "keys", "visibility", "version"]
        })
        assert changed.status == 200
        remote = changed.json()
        page.reload()
        expect(page.locator("#clname")).to_have_text(private_pending)
        page.locator("#clsave").click()
        expect(page.locator("#cllatest")).to_be_visible()
        expect(page.locator("#clsave")).to_be_enabled()
        assert read() == remote, "A recovered stale revision must not overwrite a newer save."
        more(page)
        page.locator("#cldiscard").click()
        expect(page.locator("#clname")).to_have_text(remote["title"])
        expect(page.locator("#clstate")).not_to_contain_text("Unsaved")
        assert page.evaluate("key => localStorage.getItem(key)", storage_key) is None
        page.reload()
        expect(page.locator("#clname")).to_have_text(remote["title"])
        print("PASS recovered base version rejects conflicts; discard loads latest and clears recovery")

        isolated = prefix + " owner only"
        change_title(page, isolated)
        page.goto(editor_url + "#" + chosen)
        expect(page.locator("#clname")).to_have_text(isolated)
        expect(page.locator("#panel")).to_be_visible()
        switcher = context.new_page()
        switcher.goto(base + "/__preview__/follower")
        switcher.wait_for_function("typeof booted !== 'undefined' && booted")
        expect(page.locator("#clsignin")).to_be_visible()
        assert isolated not in page.locator("body").inner_text()
        expect(page.locator(".clpick")).to_have_count(0)
        expect(page.locator("#panel")).to_be_hidden()
        # Reload is a new ownership decision, not permission inherited from the
        # previous account's in-memory editor state.
        page.reload()
        expect(page.locator("#clretry")).to_be_visible()
        assert isolated not in page.locator("body").inner_text()
        expect(page.locator(".clpick")).to_have_count(0)
        assert page.evaluate("localStorage.getItem('mz-token')") == follower_token
        assert read() == remote
        switcher.goto(base + "/__preview__/tester")
        switcher.wait_for_function("typeof booted !== 'undefined' && booted")
        page.reload()
        expect(page.locator("#clname")).to_have_text(isolated)
        expect(page.locator("#clstate")).to_contain_text("Unsaved")
        more(page)
        page.locator("#cldiscard").click()
        expect(page.locator("#clname")).to_have_text(remote["title"])
        switcher.close()
        assert not errors, "Recovery JavaScript errors: " + json.dumps(errors)
        print("PASS other-account reload cannot expose/recover pending draft; original owner can recover")
    finally:
        current = context.request.get(api + "/lists/" + list_id, headers=auth)
        if current.status == 200 and current.json()["title"].startswith(prefix):
            context.request.delete(api + "/lists/" + list_id, headers=auth, data={"version": current.json()["version"]})
        context.close()


def mobile_tests(browser, base, api, token, prefix, screenshots):
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on("dialog", lambda dialog: dialog.accept())
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    auth = {"Authorization": "Bearer " + token}
    created = context.request.post(api + "/lists", headers=auth, data={"title": "Touch test " + prefix, "keys": []})
    assert created.status == 201
    fixture = created.json()
    list_id = fixture["id"]

    def capture(name):
        if screenshots:
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(screenshots / name))

    def reachable(dialog, control):
        expect(page.locator(dialog)).to_be_visible()
        page.locator(control).scroll_into_view_if_needed()
        page.locator(control).click(trial=True)
        bounds = page.locator(dialog).bounding_box()
        button = page.locator(control).bounding_box()
        assert bounds["x"] >= -1 and bounds["x"] + bounds["width"] <= 391
        assert bounds["y"] >= -1 and bounds["y"] + bounds["height"] <= 461
        assert 0 <= button["y"] and button["y"] + button["height"] <= 460
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    try:
        page.goto(base + "/__preview__/tester")
        page.wait_for_function("typeof booted !== 'undefined' && booted")
        page.goto(base + "/releases/?editList=" + list_id)
        expect(page.locator("#clname")).to_have_text(fixture["title"])
        page.evaluate("document.fonts.ready")
        expect(page.locator("#cldetailsbtn")).to_be_hidden()
        expect(page.locator("#clsave")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        header = page.locator("#hrow").bounding_box()
        assert header["y"] + header["height"] <= 524, "Phone editing must leave at least 320px for game rows."
        page.locator("#q").fill("1944")
        expect(page.locator(".clpick").first).to_have_attribute("aria-label", re.compile("1944"))
        chosen = page.locator(".clpick").first.get_attribute("data-list-key")
        checkbox = page.locator(f'.clpick[data-list-key="{chosen}"]')
        target = checkbox.locator("..")
        bounds = target.bounding_box()
        assert bounds["width"] >= 44 and bounds["height"] >= 44
        # The generous label's edge, outside the small checkbox, must select
        # exactly the entry and never open the independent game panel.
        target.tap(position={"x": 3, "y": 3})
        expect(checkbox).to_be_checked()
        expect(page.locator("#clselected")).to_have_text("Selected (1)")
        expect(page.locator("#panel")).to_be_hidden()
        assert page.evaluate("document.activeElement.classList.contains('clpick')")
        checkbox.locator("xpath=ancestor::td").tap(position={"x": 100, "y": 15})
        expect(page.locator("#panel")).to_be_visible()
        expect(page.locator("#clselected")).to_have_text("Selected (1)")
        page.locator("#panel .close").tap()
        expect(page.locator("#panel")).to_be_hidden()
        capture("touch-editor-mobile.png")
        print("PASS compact mobile editor leaves game space; 44px edge tap selects while title tap opens panel independently")

        page.locator("#q").fill("194")
        expect(page.locator(".clpick").first).to_have_attribute("aria-label", re.compile("1942"))
        more(page)
        expect(page.locator("#cladd")).to_have_text(re.compile(r"Add matching \(\d+\)"))
        count = int(re.search(r"\((\d+)\)", page.locator("#cladd").inner_text()).group(1))
        assert count > 1
        page.locator("#cladd").tap()
        expect(page.locator("#clselected")).to_have_text("Selected (" + str(count) + ")")
        page.locator("#clundo").tap()
        expect(page.locator("#clselected")).to_have_text("Selected (1)")
        expect(checkbox).to_be_checked()
        page.locator("#clremove").tap()
        expect(page.locator("#clselected")).to_have_text("Selected (0)")
        page.locator("#clundo").tap()
        expect(page.locator("#clselected")).to_have_text("Selected (1)")
        expect(checkbox).to_be_checked()
        assert context.request.get(api + "/lists/" + list_id, headers=auth).json()["keys"] == []
        print("PASS filter-aware bulk counts and one-step add/remove undo restore the exact prior selection without saving")

        page.locator("#clmoresummary").tap()
        page.locator("#clsave").tap()
        expect(page.locator("#clstate")).not_to_contain_text("Unsaved")
        page.set_viewport_size({"width": 390, "height": 460})
        more(page)
        page.locator("#cldetailsbtn").tap()
        page.locator("#cldescription").fill("A description entered while the keyboard leaves a short viewport.")
        reachable("#cldetails", '#cldetailsform button[type="submit"]')
        capture("details-short-viewport.png")
        page.locator('#cldetailsform button[type="submit"]').tap()
        more(page)
        page.locator("#clpublish").tap()
        reachable("#clconfirm", "#clconfirmyes")
        capture("visibility-short-viewport.png")
        page.locator("#clconfirm [data-clclose]").tap()
        page.locator("#collection-create").tap()
        page.locator("#clnewtitle").fill("Keyboard viewport example")
        reachable("#clcreate", "#clcreateyes")
        page.locator("#clcreate [data-clclose]").tap()
        # Quick-add has an extra expandable form; it also must scroll to its
        # submit control without a real soft keyboard in headless Chromium.
        page.goto(base + "/releases/?collection=all#" + chosen)
        page.locator(f'#panel .clentryadd[data-list-entry="{chosen}"]').tap()
        page.locator("#clentrynew summary").tap()
        page.locator("#clentrynewtitle").fill("Short viewport example")
        reachable("#clentrydialog", "#clentrycreateyes")
        capture("quick-add-short-viewport.png")
        assert not errors, "Mobile JavaScript errors: " + json.dumps(errors)
        print("PASS details, visibility, create and quick-add actions remain reachable at 390x460; no mobile JavaScript errors")
    finally:
        current = context.request.get(api + "/lists/" + list_id, headers=auth)
        if current.status == 200 and current.json()["title"] == fixture["title"]:
            context.request.delete(api + "/lists/" + list_id, headers=auth, data={"version": current.json()["version"]})
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=preview.DEFAULT_STATE)
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--mobile-only", action="store_true", help="Run touch and short-viewport checks only.")
    args = parser.parse_args()
    state = json.loads((args.state_dir.resolve() / "state.json").read_text(encoding="utf-8"))
    base, api = state["site"], state["api"]
    assert all(urlparse(url).hostname in {"localhost", "127.0.0.1"} for url in [base, api])
    prefix = "Recovery test " + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            if not args.mobile_only:
                recovery_tests(browser, base, api, state["tester_token"], state["follower_token"], prefix, args.screenshots)
            mobile_tests(browser, base, api, state["tester_token"], prefix, args.screenshots)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
