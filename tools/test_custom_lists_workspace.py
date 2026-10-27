#!/usr/bin/env python3
"""Exercise list workspace/history against the isolated local Worker.

Uses a dedicated tester account, creates unique private fixtures, and removes
only those fixtures. Never resets profiles or the human preview owner's data.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
import custom_lists_preview as preview


def reveal(page, selector):
    if not page.locator(selector).is_visible():
        page.locator("#clmoresummary").click()
    expect(page.locator(selector)).to_be_visible()


def details(page, title=None, description=None):
    reveal(page, "#cldetailsbtn")
    page.locator("#cldetailsbtn").click()
    expect(page.locator("#cldetails")).to_be_visible()
    if title is not None:
        page.locator("#cltitle").fill(title)
    if description is not None:
        page.locator("#cldescription").fill(description)
    if title is not None or description is not None:
        page.locator('#cldetailsform button[type="submit"]').click()


def workspace_tests(browser, base, api, token, prefix, screenshots, mobile=False):
    context = browser.new_context(viewport={"width": 390 if mobile else 1440, "height": 844 if mobile else 1000},
                                  is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    errors, confirmations, puts = [], [], []
    confirm_decision = [True]
    page.on("pageerror", lambda error: errors.append(str(error)))

    def dialog_opened(dialog):
        if dialog.type == "confirm":
            confirmations.append(dialog.message)
            dialog.accept() if confirm_decision[0] else dialog.dismiss()
        else:
            dialog.accept()

    page.on("dialog", dialog_opened)
    auth = {"Authorization": "Bearer " + token}
    catalogue = context.request.get(base + "/releases/data.json").json()
    games = {query: next(row for row in catalogue if row.get("k") and row["title"].startswith(query))
             for query in ["1942", "1943", "1944", "1941"]}
    first, second, third, fourth = [games[query]["k"] for query in ["1942", "1943", "1944", "1941"]]
    missing = "WORKSPACE_TEST_MISSING_ENTRY"
    title = prefix + (" mobile" if mobile else " desktop")
    created = context.request.post(api + "/lists", headers=auth, data={
        "title": title, "description": "Saved description", "keys": [first, second, missing]
    })
    assert created.status == 201
    list_id = created.json()["id"]
    endpoint = api + "/lists/" + list_id
    editor = base + "/releases/?editList=" + list_id
    page.on("request", lambda request: puts.append(request.post_data) if request.url == endpoint and request.method == "PUT" else None)

    def read():
        response = context.request.get(endpoint, headers=auth)
        assert response.status == 200
        return response.json()

    def members():
        return set(page.locator("#clmembers [data-clremove]").evaluate_all("buttons => buttons.map(button => button.dataset.clremove)"))

    def expect_members(keys):
        expect(page.locator("#clmembers [data-clremove]")).to_have_count(len(keys))
        assert members() == set(keys)

    def search(query):
        page.locator("#q").fill(query)
        expect(page.locator(".clpick").first).to_have_attribute("aria-label", re.compile(query))

    def confirm_action(selector, accept=True, count=None):
        if selector in {"#cladd", "#clremove"} and not page.locator("#clbulktools").evaluate("element => element.open"):
            page.locator("#clbulktools > summary").click()
        confirm_decision[0] = accept
        before = len(confirmations)
        page.locator(selector).click()
        assert len(confirmations) == before + 1, selector + " must ask before changing entries"
        if count is not None:
            assert re.search(r"\b" + str(count) + r"\b", confirmations[-1]), confirmations[-1]
        confirm_decision[0] = True

    def capture(name):
        if screenshots:
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(screenshots / name))

    try:
        page.goto(base + "/__preview__/tester")
        page.wait_for_function("typeof booted !== 'undefined' && booted")
        page.goto(editor)
        expect(page.locator("#clname")).to_have_text(title)
        baseline = read()
        for control in ["#clsave", "#cldone", "#cldiscard", "#clundo", "#clredo"]:
            expect(page.locator(control)).to_be_visible()
        expect(page.locator("#clundo")).to_be_disabled()
        expect(page.locator("#clredo")).to_be_disabled()
        if mobile:
            page.locator("#clshowlist").click()
        checks = page.locator("#clmembers [data-clmark]")
        checks.nth(0).click()
        checks.nth(2).click(modifiers=["Shift"])
        expect(page.locator("#clmarkcount")).to_have_text("3 selected")
        expect(page.locator("#clsave")).to_be_disabled()
        page.locator("#clmarkclear").click()
        page.locator("#clmembersearch").fill("1943")
        page.locator("#clmarkall").click()
        expect(page.locator("#clmarkcount")).to_have_text("1 selected")
        page.locator("#clmarkremove").click()
        expect_members([])
        page.locator("#clclearsearch").click()
        expect_members([first, missing])
        page.locator("#clundo").click()
        expect_members([first, second, missing])
        page.locator("#clredo").click()
        expect_members([first, missing])
        page.locator("#clundo").click()
        expect_members([first, second, missing])
        assert read() == baseline and not puts
        if mobile:
            page.locator("#clshowcatalogue").click()
        else:
            details(page, title + " navigation")
            page.locator("#collection-browse").click()
            expect(page.locator("#clleave")).to_be_visible()
            page.locator("#clleavekeep").click()
            assert page.url == editor
            page.locator("#collection-browse").click()
            page.locator("#clleavediscard").click()
            page.wait_for_url("**/lists/")
            assert read() == baseline
            page.goto(editor)
            expect(page.locator("#clname")).to_have_text(title)
            expect(page.locator("#clsave")).to_be_disabled()
        print("PASS range selection, filtered selection, bulk remove/undo/redo and navigation protection")
        # Inspecting a game must not trap the catalogue behind an overlay.
        sizes = [(390, 844), (390, 667), (844, 500)] if mobile else [(1440, 1000), (1280, 720), (1200, 720), (1024, 768)]
        for width, height in sizes:
            print("Checking details layout", width, height, flush=True)
            page.set_viewport_size({"width": width, "height": height})
            search("1944")
            box = page.locator(f'.clpick[data-list-key="{third}"]')
            box.locator("xpath=ancestor::td").click(position={"x": 100, "y": 15})
            expect(page.locator("#panel")).to_be_visible()
            expect(page.locator("#clshowdetails")).to_have_attribute("aria-pressed", "true")
            expect(page.locator("#clshowlist")).to_have_attribute("aria-pressed", "false")
            docked = width >= 1200
            if docked:
                expect(page.locator("#clmembers")).to_be_visible()
            else:
                expect(page.locator("#clmembers")).to_be_hidden()
            for control in (["#cldone", "#panel .close"] if docked else ["#cldone", "#clshowlist", "#panel .close"]):
                page.locator(control).click(trial=True)
            body_box = page.locator("#panel .body").bounding_box()
            assert body_box["height"] >= 100, (width, height, body_box)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            if not docked:
                expect(page.locator("#clcatalogue")).to_be_hidden()
                page.locator("#clshowcatalogue").click()
                expect(page.locator("#panel")).to_be_hidden()
                page.wait_for_function("!location.hash")
                expect(page.locator("#q")).to_have_value("1944")
                box.locator("xpath=ancestor::td").click(position={"x": 100, "y": 15})
                expect(page.locator("#panel")).to_be_visible()
            else:
                table_box = page.locator("#clcatalogue").bounding_box()
                panel_box = page.locator("#panel").bounding_box()
                list_box = page.locator("#clworkspace").bounding_box()
                assert 280 <= panel_box["width"] <= 320
                assert panel_box["x"] + panel_box["width"] <= table_box["x"] + 1
                assert table_box["x"] + table_box["width"] <= list_box["x"] + 1
                assert table_box["width"] >= 400
                page.locator(f'#clmembers [data-clremove="{first}"]').click(trial=True)
                box.check()
                expect(page.locator("#panel")).to_be_visible()
                page.locator("#clundo").click()
                expect(box).not_to_be_checked()
                # Browse another row while details remain docked.
                search("1943")
                page.locator(f'.clpick[data-list-key="{second}"]').locator("xpath=ancestor::td").click(position={"x": 100, "y": 15})
                expect(page.locator("#panel h2")).to_contain_text("1943")
            if width in [1280, 390] and height in [720, 844]:
                capture("details-mobile.png" if mobile else "details-desktop.png")
            page.locator("#panel .close" if docked else "#clshowlist").click()
            expect(page.locator("#clmembers")).to_be_visible()
            expect(page.locator("#panel")).to_be_hidden()
            page.wait_for_function("!location.hash")
            expect_members([first, second, missing])
            page.locator("#clmembersearch").fill("1943")
            page.locator("#clmembersearch").press("ArrowDown")
            expect(page.locator("#panel")).to_be_hidden()
            page.locator("#clmembersearch").press("Escape")
            expect(page.locator("#clmembersearch")).to_have_value("")
            if not docked and mobile:
                page.locator("#clshowcatalogue").click()
            page.locator('.clpick').first.locator("xpath=ancestor::td").click(position={"x": 100, "y": 15})
            # Esc closes details before clearing an unrelated catalogue search.
            page.locator("#panel .close").focus()
            page.keyboard.press("Escape")
            expect(page.locator("#panel")).to_be_hidden()
            page.wait_for_function("!location.hash")
            expect(page.locator("#q")).not_to_have_value("")
            if mobile:
                page.locator("#clshowcatalogue").click()
        if not mobile:
            page.locator("#q").fill("")
            page.wait_for_function("document.querySelectorAll('.clpick').length > 10")
            table_scroll = page.locator(".tablewrap")
            table_scroll.evaluate("element => { element.scrollTop = 500; }")
            page.wait_for_function("document.querySelector('.tablewrap').scrollTop >= 490")
            top = table_scroll.evaluate("element => element.scrollTop")
            details(page, description="Checking catalogue scroll position")
            assert abs(table_scroll.evaluate("element => element.scrollTop") - top) < 2
            page.locator("#clundo").click()
            assert abs(table_scroll.evaluate("element => element.scrollTop") - top) < 2
            page.locator("#cljumptools > summary").click()
            page.locator("#totop").click()
            expect(page.locator("#cljumptools")).not_to_have_attribute("open", "")
            page.wait_for_function("document.querySelector('.tablewrap').scrollTop < 2")
        assert read() == baseline and not puts
        print("PASS docked details, unobscured catalogue, pane switching, reachable controls and keyboard isolation across desktop and narrow screen sizes")
        page.set_viewport_size({"width": 390 if mobile else 1440, "height": 844 if mobile else 1000})
        # A fresh editor also checks the initial layout without a details tab.
        page.goto(editor)
        expect(page.locator("#clname")).to_have_text(title)
        search("1944")

        if mobile:
            expect(page.locator("#clshowcatalogue")).to_be_visible()
            expect(page.locator("#clmembers")).to_be_hidden()
            page.locator("#clshowlist").tap()
            expect(page.locator("#clmembers")).to_be_visible()
            expect_members([first, second, missing])
            page.locator("#clmembersearch").fill("1943")
            expect_members([second])
            page.locator("#clmembersearch").fill("")
            expect_members([first, second, missing])
            page.locator(f'#clmembers [data-clremove="{first}"]').tap()
            expect_members([second, missing])
            page.locator("#clundo").tap()
            expect_members([first, second, missing])
            page.locator("#clshowcatalogue").tap()
            expect(page.locator("#q")).to_have_value("1944")
            page.locator(f'.clpick[data-list-key="{third}"]').check()
            page.locator("#clshowlist").tap()
            expect_members([first, second, third, missing])
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            for control in ["#clsave", "#cldone", "#cldiscard", "#clundo", "#clredo"]:
                expect(page.locator(control)).to_be_visible()
            capture("workspace-mobile-list.png")
            page.set_viewport_size({"width": 390, "height": 460})
            page.locator("#clsave").scroll_into_view_if_needed()
            page.locator("#clsave").click(trial=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert read() == baseline and not puts
            confirm_action("#cldiscard")
            expect_members([first, second, missing])
            expect(page.locator("#clundo")).to_be_disabled()
            assert read() == baseline
            print("PASS mobile catalogue/list tabs, independent member search, exact remove/undo, persistent controls and short viewport")
            return

        expect(page.locator("#clmembers")).to_be_visible()
        expect_members([first, second, missing])
        pane = page.locator("#clworkspace").bounding_box()
        catalogue_box = page.locator("#clcatalogue").bounding_box()
        assert pane["x"] >= catalogue_box["x"] + catalogue_box["width"] - 2
        assert pane["width"] >= 250
        page.locator("#clmembersearch").fill("1943")
        expect_members([second])
        expect(page.locator("#q")).to_have_value("1944")
        page.locator(f'#clmembers [data-clremove="{second}"]').click()
        expect_members([])
        assert page.evaluate("document.activeElement.classList.contains('clmemberscroll')")
        page.keyboard.press("Control+z")
        expect_members([second])
        expect(page.locator("#clmembersearch")).to_have_value("1943")
        page.locator("#clmembersearch").fill("")
        expect_members([first, second, missing])
        page.locator(f'.clpick[data-list-key="{third}"]').check()
        expect_members([first, second, third, missing])
        expect(page.locator("#panel")).to_be_hidden()
        # Checkbox focus must still allow the editor shortcut, and redo restores
        # the exact selection without opening the game's detail panel.
        page.locator(f'.clpick[data-list-key="{third}"]').focus()
        page.keyboard.press("Control+z")
        expect_members([first, second, missing])
        page.keyboard.press("Control+Shift+z")
        expect_members([first, second, third, missing])
        page.locator(f'#clmembers [data-clremove="{first}"]').click()
        expect_members([second, third, missing])
        page.locator("#clundo").click()
        expect_members([first, second, third, missing])
        page.locator("#clredo").click()
        expect_members([second, third, missing])
        page.locator("#clundo").click()
        expect_members([first, second, third, missing])
        changed_title = title + " edited"
        details(page, changed_title, "Pending description")
        expect(page.locator("#clname")).to_have_text(changed_title)
        expect(page.locator("#clredo")).to_be_disabled()
        page.locator("#clundo").click()
        expect(page.locator("#clname")).to_have_text(title)
        details(page)
        expect(page.locator("#cldescription")).to_have_value("Saved description")
        page.locator("#cldetails [data-clclose]").click()
        page.locator("#clredo").click()
        expect(page.locator("#clname")).to_have_text(changed_title)
        details(page)
        expect(page.locator("#cldescription")).to_have_value("Pending description")
        page.locator("#cldetails [data-clclose]").click()
        assert read() == baseline and not puts
        capture("workspace-desktop.png")
        print("PASS desktop full-membership sidepane stays independent of filters; exact selection and title/description undo/redo do not write")

        search("194")
        expect(page.locator(".clpick").first).to_have_attribute("aria-label", re.compile("1942|1941"))
        matches = set(page.locator(".clpick").evaluate_all("boxes => boxes.map(box => box.dataset.listKey)"))
        before_bulk = members()
        affected = len(matches - before_bulk)
        assert affected > 0
        confirm_action("#cladd", accept=False, count=affected)
        expect_members(before_bulk)
        confirm_action("#cladd", count=affected)
        expect_members(before_bulk | matches)
        page.locator("#clundo").click()
        expect_members(before_bulk)
        page.locator("#clredo").click()
        expect_members(before_bulk | matches)
        confirm_action("#clremove", accept=False, count=len(matches))
        expect_members(before_bulk | matches)
        confirm_action("#clremove", count=len(matches))
        expect_members(before_bulk - matches)
        page.locator("#clundo").click()
        expect_members(before_bulk | matches)
        page.locator("#clundo").click()
        expect_members(before_bulk)
        assert read() == baseline and not puts
        print("PASS bulk add/remove explicitly confirm net affected counts; cancel is inert, whole batches undo/redo without server writes")

        search("1941")
        box = page.locator(f'.clpick[data-list-key="{fourth}"]')
        box.locator("xpath=ancestor::td").click(position={"x": 100, "y": 15})
        expect(page.locator(f'#panel .clentryadd[data-list-entry="{fourth}"]')).to_be_visible()
        page.locator(f'#panel .clentryadd[data-list-entry="{fourth}"]').click()
        page.locator("#clentrytarget").select_option(list_id)
        page.locator("#clentryaddyes").click()
        expect(page.locator("#clentrystatus")).to_contain_text("current selection")
        page.locator("#clentrydialog").get_by_role("button", name="Done", exact=True).click()
        page.locator("#panel .close").click()
        expect_members(before_bulk | {fourth})
        page.locator("#clundo").click()
        expect_members(before_bulk)
        page.locator("#clredo").click()
        expect_members(before_bulk | {fourth})
        assert read() == baseline and not puts
        confirm_action("#cldiscard", accept=False)
        expect_members(before_bulk | {fourth})
        # A failed latest-version read must not erase the local work/history.
        def failed_read(route):
            route.abort() if route.request.method == "GET" else route.continue_()

        page.route(endpoint, failed_read)
        confirm_action("#cldiscard")
        expect(page.locator("#cldiscard")).to_be_enabled()
        expect_members(before_bulk | {fourth})
        expect(page.locator("#clstate")).to_contain_text("Unsaved")
        assert read() == baseline
        page.unroute(endpoint, failed_read)
        # Discard must get today's saved version, not a stale opening copy.
        remote = dict(baseline)
        remote["description"] = "Changed remotely while the editor was open"
        response = context.request.put(endpoint, headers=auth, data={key: remote[key] for key in ["title", "description", "keys", "visibility", "version"]})
        assert response.status == 200
        remote = response.json()
        confirm_action("#cldiscard")
        expect(page.locator("#clname")).to_have_text(title)
        expect_members(remote["keys"])
        expect(page.locator("#clundo")).to_be_disabled()
        expect(page.locator("#clredo")).to_be_disabled()
        details(page)
        expect(page.locator("#cldescription")).to_have_value(remote["description"])
        page.locator("#cldetails [data-clclose]").click()
        assert read() == remote and not puts
        print("PASS current-editor quick-add participates in history; discard cancellation preserves edits and accepted discard loads latest saved revision")

        details(page, changed_title, "Ready to save and leave")
        expect(page.locator("#cldone")).to_contain_text("Save")

        def failed_save(route):
            route.abort() if route.request.method == "PUT" else route.continue_()

        page.route(endpoint, failed_save)
        page.locator("#cldone").click()
        expect(page.locator("#clsave")).to_be_enabled()
        expect(page.locator("#clstate")).to_contain_text("Unsaved")
        assert "editList=" + list_id in page.url
        assert read() == remote
        page.unroute(endpoint, failed_save)
        # A stale Save & done must stay in the editor as well as a failed
        # transport. The newer remote revision must remain untouched.
        changed = context.request.put(endpoint, headers=auth, data={
            **{key: remote[key] for key in ["title", "description", "keys", "visibility", "version"]},
            "description": "Another session saved before Done",
        })
        assert changed.status == 200
        remote = changed.json()
        page.locator("#cldone").click()
        expect(page.locator("#cllatest")).to_be_visible()
        expect(page.locator("#clsave")).to_be_enabled()
        expect(page.locator("#clname")).to_have_text(changed_title)
        assert "editList=" + list_id in page.url and read() == remote
        confirm_action("#cldiscard")
        expect(page.locator("#clstate")).not_to_contain_text("Unsaved")
        details(page, changed_title, "Ready to save and leave")
        page.locator("#cldone").click()
        page.wait_for_url("**/releases/?list=" + list_id)
        expect(page.locator("#clname")).to_have_text(changed_title)
        expect(page.locator('#hrow th[data-k="title"]')).to_have_attribute("aria-sort", "ascending")
        assert read()["title"] == changed_title
        page.goto(base + "/releases/?list=" + list_id + "&s=-title")
        expect(page.locator('#hrow th[data-k="title"]')).to_have_attribute("aria-sort", "descending")
        page.goto(base + "/releases/?collection=all")
        expect(page.locator('#hrow th[data-k="updated"]')).to_have_attribute("aria-sort", "descending")
        print("PASS Save & done waits for successful persistence; network/conflict failures retain edits; list defaults A-Z and explicit URL sort wins")
        # A sender's hidden Updated column changes their local default to Date.
        # The shared URL must preserve that sort for a fresh recipient whose
        # default columns still include Updated.
        page.locator("#cols > summary").click()
        page.locator('#colsmenu input[data-k="updated"]').uncheck()
        page.locator("#cols > summary").click()
        expect(page.locator('#hrow th[data-k="date"]')).to_have_attribute("aria-sort", "descending")
        shared_url = page.evaluate("shareURL()")
        assert "s=-date" in shared_url
        recipient = browser.new_context(viewport={"width": 1440, "height": 1000})
        try:
            visitor = recipient.new_page()
            visitor.on("pageerror", lambda error: errors.append(str(error)))
            visitor.goto(base + "/__preview__/anonymous")
            visitor.wait_for_function("typeof booted !== 'undefined' && booted")
            visitor.goto(shared_url)
            expect(visitor.locator('#hrow th[data-k="updated"]')).to_be_visible()
            expect(visitor.locator('#hrow th[data-k="date"]')).to_have_attribute("aria-sort", "descending")
        finally:
            recipient.close()
        print("PASS shared view preserves Date sort across different sender/recipient column preferences")
    finally:
        capture("last-workspace-mobile.png" if mobile else "last-workspace-desktop.png")
        current = context.request.get(endpoint, headers=auth)
        if current.status == 200 and current.json()["title"].startswith(prefix):
            context.request.delete(endpoint, headers=auth, data={"version": current.json()["version"]})
        context.close()
        assert not errors, "Workspace JavaScript errors: " + json.dumps(errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=preview.DEFAULT_STATE)
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    state = json.loads((args.state_dir.resolve() / "state.json").read_text(encoding="utf-8"))
    base, api = state["site"], state["api"]
    assert all(urlparse(url).hostname in {"localhost", "127.0.0.1"} for url in [base, api])
    prefix = "Workspace test " + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            workspace_tests(browser, base, api, state["tester_token"], prefix, args.screenshots)
            workspace_tests(browser, base, api, state["tester_token"], prefix, args.screenshots, mobile=True)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
