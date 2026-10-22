#!/usr/bin/env python3
"""Exercise Custom Lists against the isolated preview, never a deployed site.

Start tools/custom_lists_preview.py first. Requires Python Playwright + Chromium.
The test creates its own list, exercises both signed-in and anonymous browsers,
then deletes only that test list. Optional --screenshots saves review images.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8633")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    assert urlparse(base).hostname in {"localhost", "127.0.0.1"}, "Only local previews may be tested."
    title = "Preview test " + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        owner = browser.new_context(viewport={"width": 1440, "height": 1080})
        anonymous = browser.new_context(viewport={"width": 1440, "height": 1080})
        page = owner.new_page()
        public = anonymous.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        public.on("pageerror", lambda error: errors.append(str(error)))
        list_id = None
        api = token = None
        try:
            page.goto(base + "/__preview__/owner")
            expect(page.locator("#library")).to_be_visible()
            api = page.evaluate("localStorage.getItem('mz-api')")
            token = page.evaluate("localStorage.getItem('mz-token')")
            assert urlparse(api).hostname in {"localhost", "127.0.0.1"}
            page.locator("#new-title").fill(title)
            page.locator("#new-byline").fill("Local preview")
            page.locator("#new-description").fill("Two precise core choices, kept separate from favorites.")
            page.locator("#create-submit").click()
            page.wait_for_url("**/releases/?editList=*")
            list_id = parse_qs(urlparse(page.url).query)["editList"][0]
            expect(page.locator("#clname")).to_have_text(title)
            assert anonymous.request.get(api + "/public/lists/" + list_id).status == 404
            print("PASS create draft and deny anonymous draft access")

            page.locator("#q").fill("1942")
            expect(page.locator(".clpick").first).to_be_visible()
            expect(page.locator(".clpick").first).to_have_attribute("aria-label", re.compile("1942"))
            first_key = page.locator(".clpick").first.get_attribute("data-list-key")
            page.locator(f'.clpick[data-list-key="{first_key}"]').check()
            page.locator("#q").fill("1943")
            expect(page.locator(".clpick").first).to_be_visible()
            expect(page.locator(".clpick").first).to_have_attribute("aria-label", re.compile("1943"))
            second_key = page.locator(".clpick").first.get_attribute("data-list-key")
            assert second_key != first_key
            page.locator(f'.clpick[data-list-key="{second_key}"]').check()
            expect(page.locator("#clselected")).to_have_text("Selected (2)")
            page.locator("#clsave").click()
            expect(page.locator("#clstate")).to_have_text("Private draft · Saved")
            assert anonymous.request.get(api + "/public/lists/" + list_id).status == 404
            print("PASS select entries across searches and save private draft")

            page.locator("#clpublish").click()
            expect(page.locator("#clconfirm")).to_be_visible()
            page.locator("#clconfirmyes").click()
            expect(page.locator("#clstate")).to_have_text("Public list · Saved")
            response = anonymous.request.get(api + "/public/lists/" + list_id)
            assert response.status == 200
            assert response.json()["keys"] == [first_key, second_key]
            assert "user_id" not in response.json() and "email" not in response.json()
            print("PASS publish exact entries without account identity")

            public.goto(base + "/__preview__/anonymous")
            expect(public.locator("#out")).to_be_visible()
            public.goto(base + "/lists/?id=" + list_id)
            expect(public.locator("#public-title")).to_have_text(title)
            expect(public.locator("#public-id")).to_have_text(list_id)
            expect(public.locator("#entries > li")).to_have_count(2)
            assert public.evaluate("localStorage.getItem('mz-token')") is None
            if args.screenshots:
                public.evaluate("document.fonts.ready")
                public.screenshot(path=str(args.screenshots / "public-list.png"), full_page=True)
            print("PASS anonymous public page resolves both selected games")

            page.locator("#q").fill("1944")
            expect(page.locator(".clpick").first).to_be_visible()
            expect(page.locator(".clpick").first).to_have_attribute("aria-label", re.compile("1944"))
            third_key = page.locator(".clpick").first.get_attribute("data-list-key")
            page.locator(f'.clpick[data-list-key="{third_key}"]').check()
            expect(page.locator("#clselected")).to_have_text("Selected (3)")
            page.locator("#clsave").click()
            expect(page.locator("#clstate")).to_have_text("Public list · Saved")
            public.reload()
            expect(public.locator("#entries > li")).to_have_count(3)
            expect(public.locator("#public-id")).to_have_text(list_id)
            public.locator("#view-tracker").click()
            expect(public.locator("#clname")).to_have_text(title)
            expect(public.locator("#cledit")).to_be_hidden()
            expect(public.locator(".clpick")).to_have_count(0)
            if args.screenshots:
                page.locator("#q").fill("")
                page.locator("#clselected").click()
                page.evaluate("document.fonts.ready")
                page.screenshot(path=str(args.screenshots / "tracker-editor.png"), full_page=True)
            print("PASS saved owner update reaches same public ID and read-only Tracker view")

            page.goto(base + "/lists/")
            card = page.locator(".list-card").filter(has=page.get_by_role("heading", name=title, exact=True))
            expect(card).to_be_visible()
            card.get_by_role("button", name="Delete", exact=True).click()
            expect(page.locator("#delete-dialog")).to_be_visible()
            page.locator("#delete-confirm").click()
            expect(card).to_have_count(0)
            assert anonymous.request.get(api + "/public/lists/" + list_id).status == 404
            list_id = None
            assert not errors, "Browser errors: " + json.dumps(errors)
            print("PASS delete list removes public access; no browser JavaScript errors")
        finally:
            if list_id and api and token:
                headers = {"Authorization": "Bearer " + token}
                response = owner.request.get(api + "/lists/" + list_id, headers=headers)
                if response.status == 200 and response.json().get("title") == title:
                    owner.request.delete(api + "/lists/" + list_id, headers=headers, data={"version": response.json()["version"]})
            browser.close()


if __name__ == "__main__":
    main()
