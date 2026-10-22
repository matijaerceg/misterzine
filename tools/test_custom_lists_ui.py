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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8633")
    parser.add_argument("--state-dir", type=Path, default=preview.DEFAULT_STATE)
    parser.add_argument("--screenshots", type=Path)
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
    ], cwd=directory, env=preview.isolated_env(), capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert reset.returncode == 0, "Could not initialize the dedicated test profile."
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
            page.goto(base + "/__preview__/tester")
            page.wait_for_function("typeof booted !== 'undefined' && booted")
            expect(page.locator("#collection-create")).to_be_visible()
            for control in ["#collection-all", "#collection-favorites", "#collection-select", "#collection-browse"]:
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
            expect(page.locator("#clselected")).to_have_text("Selected (2)")
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
            print("PASS follow/count, own/followed views remembered, explicit link overrides favorites")

            page.goto(base + "/releases/?editList=" + list_id)
            expect(page.locator("#clname")).to_have_text(title)
            keys.append(select_game("1944"))
            page.locator("#clsave").click()
            saved()
            assert public_list()["keys"] == keys
            following.reload()
            expect(following.locator("#clattribution")).to_contain_text("3")
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
            expect(following.locator("#collection-notice")).to_be_visible()
            expect(following.locator("#clbar")).to_be_hidden()
            following.goto(base + "/lists/?view=mine")
            expect(following.locator("#following-cards")).to_contain_text("Unavailable list")
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
            expect(following.locator("#collection-notice")).to_be_visible()
            assert not errors, "Browser errors: " + json.dumps(errors)
            print("PASS confirmed delete, deleted-view fallback; no JavaScript errors")
        finally:
            if list_id:
                follower.request.delete(api + "/following/" + list_id, headers=auth(follower_token))
                response = owner.request.get(api + "/lists/" + list_id, headers=auth())
                if response.status == 200 and response.json().get("title") == title:
                    owner.request.delete(api + "/lists/" + list_id, headers=auth(), data={"version": response.json()["version"]})
            browser.close()


if __name__ == "__main__":
    main()
