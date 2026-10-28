#!/usr/bin/env python3
"""Exercise Tracker collections against local D1 and Worker with real browsers.

Start tools/custom_lists_preview.py first. Requires Python Playwright/Chromium.
Uses a dedicated tester account, preserving the human preview owner's lists and
profile. Only the test's own lists/follows are removed. No deployed site allowed.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import parse_qs, quote, urlparse

from playwright.sync_api import expect, sync_playwright
import custom_lists_preview as preview


def quick_add_tests(owner, anonymous, base, api, token, title, screenshots=None):
    """Add real panel entries without changing the browsing view or stale data."""
    page = owner.new_page()
    errors, fixtures = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    headers = {"Authorization": "Bearer " + token}
    catalogue = owner.request.get(base + "/releases/data.json").json()
    games = [next(row for row in catalogue if row.get("k") and row["title"].startswith(query)) for query in ["1944", "1942", "1943"]]
    first, second, remote = [row["k"] for row in games]

    def read(list_id):
        response = owner.request.get(api + "/lists/" + list_id, headers=headers)
        assert response.status == 200
        return response.json()

    def panel(key):
        page.goto(base + "/releases/?collection=all#" + key)
        expect(page.locator(f'#panel .clentryadd[data-list-entry="{key}"]')).to_be_visible()

    def chooser(key):
        page.locator(f'#panel .clentryadd[data-list-entry="{key}"]').click()
        expect(page.locator("#clentrydialog")).to_be_visible()
        expect(page.locator("#clentryforms")).to_be_visible()

    def close():
        page.locator("#clentrydialog").get_by_role("button", name="Done", exact=True).click()
        expect(page.locator("#clentrydialog")).to_be_hidden()

    def capture(name):
        if screenshots:
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(screenshots / name))

    try:
        existing = owner.request.post(api + "/lists", headers=headers, data={"title": title + " existing", "description": "Quick-add fixture", "keys": []})
        assert existing.status == 201
        existing_id = existing.json()["id"]
        fixtures.append(existing_id)
        page.goto(base + "/__preview__/tester")
        page.wait_for_function("typeof booted !== 'undefined' && booted")
        panel(first)
        page.locator("#q").fill("1944")
        expect(page.locator("#rows")).to_contain_text("1944")
        browsing_url = page.url
        chooser(first)
        expect(page.locator("#clentryname")).to_have_text(games[0]["title"])
        page.locator("#clentrytarget").select_option(existing_id)
        page.locator("#clentryaddyes").click()
        expect(page.locator("#clentrystatus")).to_contain_text('Added to "')
        saved = read(existing_id)
        assert saved["keys"] == [first] and saved["visibility"] == "private"
        assert page.url == browsing_url
        expect(page.locator("#q")).to_have_value("1944")
        expect(page.locator("#clentryaddyes")).to_be_disabled()
        expect(page.locator("#clentryaddyes")).to_have_text("Already in this list")
        unchanged = read(existing_id)
        assert (unchanged["keys"], unchanged["version"], unchanged["updated_at"]) == ([first], saved["version"], saved["updated_at"])
        page.locator("#clentrynew summary").click()
        page.locator("#clentrynewtitle").fill(title + " new")
        page.locator("#clentrynewdescription").fill("Created from the game panel")
        page.locator("#clentrycreateyes").click()
        expect(page.locator("#clentrystatus")).to_contain_text('Created "')
        new_id = parse_qs(urlparse(page.locator("#clentrycreated").get_attribute("href")).query)["editList"][0]
        fixtures.append(new_id)
        created = read(new_id)
        assert created["keys"] == [first] and created["visibility"] == "private"
        assert anonymous.request.get(api + "/public/lists/" + new_id).status == 404
        assert page.url == browsing_url
        # A response can be lost after creation succeeded. The form must stop
        # repeat submission until the owner reloads the saved list inventory.
        page.locator("#clentrynew summary").click()
        uncertain_title = title + " uncertain"
        page.locator("#clentrynewtitle").fill(uncertain_title)
        lost_responses = []

        def lose_create_response(route):
            if route.request.method == "POST":
                result = route.fetch()
                assert result.status == 201
                lost_id = result.json()["id"]
                fixtures.append(lost_id)
                lost_responses.append(lost_id)
                route.abort()
            else:
                route.continue_()

        page.route(api + "/lists", lose_create_response)
        page.locator("#clentrycreateyes").click()
        expect(page.locator("#clentrystatus")).to_contain_text("Could not confirm creation")
        expect(page.locator("#clentrycreateyes")).to_be_disabled()
        assert len(lost_responses) == 1
        page.unroute(api + "/lists", lose_create_response)
        page.locator("#clentryreload").click()
        expect(page.locator("#clentrytarget option", has_text=uncertain_title)).to_have_count(1)
        assert read(lost_responses[0])["keys"] == [first]
        close()
        page.locator("#q").fill("1942")
        expect(page.locator("#rows")).to_contain_text("1942")
        print("PASS panel exact add/new private, duplicate no-op, lost-create recovery, browsing/filter continuity")

        panel(second)
        chooser(second)
        page.locator("#clentrytarget").select_option(existing_id)

        def offline(route):
            if route.request.method == "PUT":
                route.abort()
            else:
                route.continue_()

        page.route(api + "/lists/" + existing_id, offline)
        page.locator("#clentryaddyes").click()
        expect(page.locator("#clentrystatus")).to_contain_text("Could not confirm the addition")
        expect(page.locator("#clentryaddyes")).to_be_enabled()
        assert read(existing_id)["keys"] == [first]
        page.unroute(api + "/lists/" + existing_id, offline)
        injected = []

        def concurrent_update(route):
            if route.request.method == "PUT" and not injected:
                latest = read(existing_id)
                latest["keys"].append(remote)
                change = owner.request.put(api + "/lists/" + existing_id, headers=headers, data={
                    key: latest[key] for key in ["title", "description", "keys", "visibility", "version"]
                })
                assert change.status == 200
                injected.append(True)
            route.continue_()

        page.route(api + "/lists/" + existing_id, concurrent_update)
        page.locator("#clentryaddyes").click()
        expect(page.locator("#clentrystatus")).to_contain_text("Nothing was overwritten")
        assert read(existing_id)["keys"] == [first, remote]
        page.unroute(api + "/lists/" + existing_id, concurrent_update)
        page.locator("#clentryaddyes").click()
        expect(page.locator("#clentrystatus")).to_contain_text('Added to "')
        assert read(existing_id)["keys"] == [first, remote, second]
        close()
        print("PASS interrupted quick-add retry and real version conflict preserve newer entries")

        # Adding to the currently edited list must remain part of its unsaved
        # selection, without writing around other pending editor changes.
        page.goto(base + "/releases/?editList=" + new_id + "#" + second)
        expect(page.locator("#clname")).to_have_text(title + " new")
        chooser(second)
        expect(page.locator("#clentrytarget")).to_have_value(new_id)
        page.locator("#clentryaddyes").click()
        expect(page.locator("#clentrystatus")).to_contain_text("current selection")
        assert read(new_id)["keys"] == [first]
        close()
        expect(page.locator("#clstate")).to_contain_text("Unsaved")
        page.locator("#clsave").click()
        expect(page.locator("#clstate")).not_to_contain_text("Unsaved")
        assert read(new_id)["keys"] == [first, second]
        chooser(second)
        editor_return = parse_qs(urlparse(page.locator("#clentrysignin").get_attribute("href")).query)["r"][0]
        assert parse_qs(urlparse(editor_return).query)["editList"] == [new_id]
        close()
        page.goto(base + editor_return)
        expect(page.locator("#clname")).to_have_text(title + " new")
        expect(page.locator("#clentrydialog")).to_be_visible()
        expect(page.locator("#clentrytarget")).to_have_value(new_id)
        assert read(new_id)["keys"] == [first, second]
        close()
        page.set_viewport_size({"width": 390, "height": 844})
        panel(first)
        chooser(first)
        page.locator("#clentrynew summary").click()
        page.evaluate("document.fonts.ready")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Quick-add mobile overflow"
        bounds = page.locator("#clentrydialog").bounding_box()
        assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
        capture("quick-add-mobile.png")
        close()
        signed_out = anonymous.new_page()
        signed_out.on("pageerror", lambda error: errors.append(str(error)))
        signed_out.goto(base + "/__preview__/anonymous")
        signed_out.wait_for_function("typeof booted !== 'undefined' && booted")
        signed_out.goto(base + "/releases/?collection=all#" + first)
        expect(signed_out.locator(f'#panel .clentryadd[data-list-entry="{first}"]')).to_be_visible()
        signed_out.locator("#q").fill("Q*bert")
        expect(signed_out.locator("#rows")).to_contain_text("Q*bert")
        signed_out.locator(f'#panel .clentryadd[data-list-entry="{first}"]').click()
        expect(signed_out.locator("#clentrysignin")).to_be_visible()
        expect(signed_out.locator("#clentryforms")).to_be_hidden()
        return_path = parse_qs(urlparse(signed_out.locator("#clentrysignin").get_attribute("href")).query)["r"][0]
        assert parse_qs(urlparse(return_path).query)["addToList"] == [first]
        before_resume = read(existing_id)
        page.goto(base + return_path)
        expect(page.locator("#clentrydialog")).to_be_visible()
        expect(page.locator("#clentryname")).to_have_text(games[0]["title"])
        expect(page.locator("#q")).to_have_value("Q*bert")
        assert read(existing_id) == before_resume
        signed_out.close()
        assert not errors, "Quick-add JavaScript errors: " + json.dumps(errors)
        print("PASS pending editor save, mobile chooser, signed-out return/resume without auto-add; no JavaScript errors")
    finally:
        page.close()
        for list_id in fixtures:
            response = owner.request.get(api + "/lists/" + list_id, headers=headers)
            if response.status == 200 and response.json()["title"].startswith(title):
                owner.request.delete(api + "/lists/" + list_id, headers=headers, data={"version": response.json()["version"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8633")
    parser.add_argument("--state-dir", type=Path, default=preview.DEFAULT_STATE)
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--quick-add-only", action="store_true", help="Run only game-panel Add to list coverage.")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    assert urlparse(base).hostname in {"localhost", "127.0.0.1"}, "Only local previews may be tested."
    directory = args.state_dir.resolve()
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert state["site"] == base, "Test must use its own local preview state."
    api = state["api"]
    assert urlparse(api).hostname in {"localhost", "127.0.0.1"}
    token, follower_token = state["tester_token"], state["follower_token"]
    # Reset only the dedicated tester's name to exercise the first-share prompt.
    reset = subprocess.run(preview.wrangler() + [
        "d1", "execute", "misterzine-preview", "--local", "--config", str(directory / "wrangler.toml"),
        "--persist-to", str(directory / "wrangler"), "--command",
        "DELETE FROM public_profiles WHERE user_id IN (SELECT id FROM users WHERE provider='github' AND provider_user_id='local-custom-lists-tester')",
    ], cwd=directory, env=preview.isolated_env(), capture_output=True, text=True, encoding="utf-8", errors="replace") if not args.quick_add_only else None
    assert reset is None or reset.returncode == 0, "Could not initialize the dedicated test profile."
    title = "Preview test " + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    display_name = "Collection test curator"
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        owner = browser.new_context(viewport={"width": 1440, "height": 1080})
        follower = browser.new_context(viewport={"width": 1440, "height": 1080})
        anonymous = browser.new_context(viewport={"width": 1440, "height": 1080})
        page, following, public = owner.new_page(), follower.new_page(), anonymous.new_page()
        errors = []
        for tab in [page, following, public]:
            tab.on("pageerror", lambda error: errors.append(str(error)))
        list_id = None

        def auth(session=token):
            return {"Authorization": "Bearer " + session}

        def get_list():
            response = owner.request.get(api + "/lists/" + list_id, headers=auth())
            assert response.status == 200
            return response.json()

        def public_list():
            response = anonymous.request.get(api + "/public/lists/" + list_id)
            assert response.status == 200
            data = response.json()
            assert not {"user_id", "provider", "email", "followers"}.intersection(data)
            return data

        def select_game(query):
            page.locator("#q").fill(query)
            expect(page.locator(".clpick").first).to_have_attribute("aria-label", re.compile(query))
            key = page.locator(".clpick").first.get_attribute("data-list-key")
            page.locator(f'.clpick[data-list-key="{key}"]').check()
            return key

        def saved():
            expect(page.locator("#clsave")).to_be_disabled()
            expect(page.locator("#clstate")).not_to_contain_text("Unsaved")

        def set_visibility(visibility, name=None):
            page.locator("#clpublish").click()
            expect(page.locator("#clconfirm")).to_be_visible()
            page.locator(f'#clvisibility input[value="{visibility}"]').check()
            if name:
                expect(page.locator("#clpublicname")).to_be_visible()
                page.locator("#clpublicname").fill(name)
            page.locator("#clconfirmyes").click()
            expect(page.locator("#clconfirm")).to_be_hidden()
            saved()
            assert get_list()["visibility"] == visibility

        def capture(tab, name):
            if args.screenshots:
                tab.evaluate("document.fonts.ready")
                tab.screenshot(path=str(args.screenshots / name), full_page=True)

        try:
            if args.quick_add_only:
                quick_add_tests(owner, anonymous, base, api, token, title, args.screenshots)
                return
            page.goto(base + "/__preview__/tester")
            page.wait_for_function("typeof booted !== 'undefined' && booted")
            expect(page.locator("#collection-create")).to_be_visible()
            for control in ["#collection-all", "#collection-favorites", "#collection-summary", "#collection-browse"]:
                expect(page.locator(control)).to_be_visible()
            assert page.evaluate("localStorage.getItem('mz-token')") == token
            page.locator("#collection-create").click()
            expect(page.locator("#clcreate")).to_be_visible()
            page.locator("#clnewtitle").fill(title)
            page.locator("#clnewdescription").fill("Specific core choices for the browser integration test.")
            page.locator("#clcreateyes").click()
            page.wait_for_url("**/releases/?editList=*")
            list_id = parse_qs(urlparse(page.url).query)["editList"][0]
            expect(page.locator("#clname")).to_have_text(title)
            assert anonymous.request.get(api + "/public/lists/" + list_id).status == 404
            keys = [select_game("1942"), select_game("1943")]
            expect(page.locator("#clmembercount")).to_have_text("In this list (2)")
            page.locator("#clsave").click()
            saved()
            assert get_list()["keys"] == keys
            print("PASS visible Tracker collections, private draft, exact selections and save")

            set_visibility("unlisted", display_name)
            shared = public_list()
            assert shared["keys"] == keys and shared["visibility"] == "unlisted"
            assert shared["curator"]["name"] == display_name
            assert shared["curator"]["id"] is None  # unlisted links do not reveal the owner's other lists
            curator_id = owner.request.get(api + "/me", headers=auth()).json()["profile"]["id"]
            catalogue = anonymous.request.get(api + "/public/lists?q=" + quote(title)).json()
            assert not catalogue["lists"]
            profile = anonymous.request.get(api + "/public/curators/" + curator_id)
            assert profile.status == 404 or all(row["id"] != list_id for row in profile.json()["lists"])
            public.goto(base + "/__preview__/anonymous")
            expect(public.locator("#collection-all")).to_be_visible()
            public.goto(base + "/lists/?q=" + quote(title))
            expect(public.locator("#directory-empty")).to_be_visible()
            public.goto(base + "/releases/?list=" + list_id)
            expect(public.locator("#clname")).to_have_text(title)
            expect(public.locator("#clfollow")).to_be_visible()
            public.locator("#clfollow").click()
            public.wait_for_url("**/account/**")
            expect(public.locator("#out")).to_be_visible()
            print("PASS first-share account name, unlisted link, directory/profile exclusion, follow sign-in")

            following.goto(base + "/__preview__/follower")
            following.goto(base + "/releases/?list=" + list_id)
            expect(following.locator("#clname")).to_have_text(title)
            following.locator("#clfollow").click()
            expect(following.locator("#clfollow")).to_have_text(re.compile("Following|Unfollow|Stop following"))
            assert public_list()["follower_count"] == 1
            following.goto(base + "/lists/?view=mine")
            followed_card = following.locator("#following-cards .list-card").filter(has=following.get_by_role("heading", name=title, exact=True))
            followed_card.get_by_role("button", name="Following", exact=True).click()
            expect(followed_card).to_be_visible()
            expect(followed_card.get_by_role("button", name="Follow list", exact=True)).to_be_visible()
            assert public_list()["follower_count"] == 0
            following.goto(base + "/releases/?list=" + list_id)
            following.locator("#clfollow").click()
            expect(following.locator("#clfollow")).to_have_text(re.compile("Following|Unfollow|Stop following"))
            assert public_list()["follower_count"] == 1
            following.goto(base + "/releases/")
            expect(following.locator("#clname")).to_have_text(title)
            following.locator("#collection-favorites").click()
            expect(following.locator("#collection-favorites")).to_have_attribute("aria-current", "page")
            following.goto(base + "/releases/")
            expect(following.locator("#collection-favorites")).to_have_attribute("aria-current", "page")
            following.goto(base + "/releases/?list=" + list_id)
            expect(following.locator("#clname")).to_have_text(title)
            page.goto(base + "/releases/?list=" + list_id)
            expect(page.locator("#clname")).to_have_text(title)
            page.goto(base + "/releases/")
            expect(page.locator("#clname")).to_have_text(title)
            print("PASS follow/count, My lists unfollow, own/followed views remembered, explicit link overrides favorites")

            page.goto(base + "/releases/?editList=" + list_id)
            expect(page.locator("#clname")).to_have_text(title)
            keys.append(select_game("1944"))
            page.locator("#clsave").click()
            saved()
            assert public_list()["keys"] == keys
            following.reload()
            expect(following.locator("#count")).to_contain_text("3")  # the entry count lives in the search tally, not the list header
            before = get_list()
            response = owner.request.put(api + "/lists/" + list_id, headers=auth(), data={
                key: before[key] for key in ["title", "description", "keys", "visibility", "version"]
            })
            assert response.status == 200
            assert (response.json()["version"], response.json()["updated_at"]) == (before["version"], before["updated_at"])
            set_visibility("public")
            public.goto(base + "/lists/?q=" + quote(title))
            expect(public.locator("#directory-cards").get_by_role("heading", name=title)).to_be_visible()
            public.goto(base + "/lists/?curator=" + curator_id)
            expect(public.locator("#curator-name")).to_have_text(display_name)
            expect(public.locator("#curator-cards").get_by_role("heading", name=title)).to_be_visible()
            assert "followers" not in public_list()
            capture(public, "curator-profile.png")
            print("PASS owner updates, no-op preserves date/version, public directory and curator profile")

            following.set_viewport_size({"width": 390, "height": 844})
            following.goto(base + "/releases/?list=" + list_id)
            expect(following.locator("#clname")).to_have_text(title)
            following.evaluate("document.fonts.ready")
            assert following.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile document overflow"
            capture(following, "collection-mobile.png")
            set_visibility("private")
            assert anonymous.request.get(api + "/public/lists/" + list_id).status == 404
            following.goto(base + "/releases/")
            # a followed list that went private keeps its title and offers Remove from your lists, instead of bouncing to All
            expect(following.locator("#clname")).to_have_text(title)
            expect(following.locator("#clremoveunavailable")).to_be_visible()
            following.goto(base + "/lists/?view=mine")
            expect(following.locator("#following-cards")).to_contain_text("no longer available")
            print("PASS mobile fit, private withdrawal, remembered fallback and followed tombstone")

            set_visibility("public")
            following.goto(base + "/releases/?list=" + list_id)
            expect(following.locator("#clname")).to_have_text(title)
            page.goto(base + "/lists/?view=mine")
            card = page.locator("#owned-cards .list-card").filter(has=page.get_by_role("heading", name=title, exact=True))
            expect(card).to_be_visible()
            card.get_by_role("button", name="Delete", exact=True).click()
            page.locator("#delete-confirm").click()
            expect(card).to_have_count(0)
            assert anonymous.request.get(api + "/public/lists/" + list_id).status == 404
            following.goto(base + "/releases/")
            # a deleted followed list stays selected with its remembered title and the Remove from your lists action
            expect(following.locator("#clname")).to_have_text(title)
            expect(following.locator("#clremoveunavailable")).to_be_visible()
            assert not errors, "Browser errors: " + json.dumps(errors)
            print("PASS confirmed delete, deleted-view fallback; no JavaScript errors")
            quick_add_tests(owner, anonymous, base, api, token, title, args.screenshots)
        finally:
            if list_id:
                follower.request.delete(api + "/following/" + list_id, headers=auth(follower_token))
                response = owner.request.get(api + "/lists/" + list_id, headers=auth())
                if response.status == 200 and response.json().get("title") == title:
                    owner.request.delete(api + "/lists/" + list_id, headers=auth(), data={"version": response.json()["version"]})
            browser.close()


if __name__ == "__main__":
    main()
