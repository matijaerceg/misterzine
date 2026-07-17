"""Fetch a page through a real (Playwright Chromium) browser from this machine.

Many sites 403 plain HTTP fetchers but serve a browser on a residential IP
fine (retrorgb.com, misterfpga.org, aliexpress.com all verified 2026-07-16).
Reddit still refuses headless traffic - don't burn time on it.

Usage:  python tools/fetch_page.py <url> [needle]
Prints HTTP status, <title>, and the page's visible text (first 12000 chars);
if a needle is given, also whether it appears. Made for landscape sweeps.
"""
import sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

url = sys.argv[1]
needle = sys.argv[2] if len(sys.argv) > 2 else None

with sync_playwright() as pw:
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
