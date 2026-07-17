"""Fetch a page through a real (Playwright Chromium) browser from this machine.

Many sites 403 plain HTTP fetchers but serve a browser on a residential IP
fine (retrorgb.com, misterfpga.org, aliexpress.com all verified 2026-07-16).
Reddit still refuses headless traffic - don't burn time on it.

Usage:  python tools/fetch_page.py <url> [needle] [--headed]
Prints HTTP status, <title>, and the page's visible text (first 12000 chars);
if a needle is given, also whether it appears. Made for landscape sweeps.

--headed launches the user's REAL Chrome with a visible window (it will
flash up on their screen - warn them first). This is the ONLY way through
Reddit: headless (any flavor, any UA) gets 403; headed real Chrome gets
old.reddit.com search results fine (verified 2026-07-16).
"""
import sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

args = [a for a in sys.argv[1:] if a != '--headed']
headed = '--headed' in sys.argv
url = args[0]
needle = args[1] if len(args) > 1 else None

with sync_playwright() as pw:
    if headed:
        b = pw.chromium.launch(channel='chrome', headless=False)
        pg = b.new_context(locale='en-US').new_page()
    else:
        b = pw.chromium.launch()
        pg = b.new_context(user_agent=UA, locale='en-US').new_page()
    r = pg.goto(url, wait_until='domcontentloaded', timeout=30000)
    pg.wait_for_timeout(2500)
    print('HTTP', r.status, '|', pg.title())
    body = pg.inner_text('body')
    if needle:
        print('needle', repr(needle), 'found:', needle.lower() in body.lower())
    print(body[:12000])
    b.close()
