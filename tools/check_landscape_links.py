import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

d = json.load(open('docs/hardware-landscape/hardware.json', encoding='utf-8'))
targets = []
for o in d['options']:
    if o.get('url'): targets.append(('option ' + o['id'], o['url']))
for pid, p in d['parts'].items():
    if p.get('url'): targets.append(('part ' + pid, p['url']))

BAD = ['page not found', '404', 'not found', 'just a moment', 'access denied', 'nothing was found']
HARD = ['aliexpress', 'retrocastle']  # need the real-Chrome path

def check(pg, url):
    try:
        r = pg.goto(url, wait_until='domcontentloaded', timeout=35000)
        pg.wait_for_timeout(2500)
        title = pg.title()
        status = r.status if r else 0
        flag = 'OK'
        tl = title.lower()
        if status >= 400 or any(b in tl for b in BAD):
            flag = 'SUSPECT'
        return f'{flag} [{status}] {title[:70]}'
    except Exception as e:
        return 'ERROR ' + str(e).splitlines()[0][:80]

with sync_playwright() as pw:
    hb = pw.chromium.launch()
    hpg = hb.new_context(locale='en-US').new_page()
    cb = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    cpg = cb.contexts[0].new_page()
    for name, url in targets:
        pg = cpg if any(h in url for h in HARD) else hpg
        res = check(pg, url)
        print(f'{name:32} {res}')
        if res.startswith(('SUSPECT', 'ERROR')) and pg is hpg:
            res2 = check(cpg, url)
            print(f'{"":32} retry via Chrome: {res2}')
    hb.close()
    cpg.close()
print('done')
