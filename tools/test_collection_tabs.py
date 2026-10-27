"""Exercise local collection tabs without changing the owner's data."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import custom_lists_preview as preview

def main():
 state=json.loads((preview.DEFAULT_STATE/'state.json').read_text()); base,api=state['site'],state['api']; auth={'Authorization':'Bearer '+state['tester_token']}
 with sync_playwright() as p:
  browser=p.chromium.launch(); page=browser.new_page(viewport={'width':1280,'height':800}); errors=[]; page.on('pageerror',lambda e: errors.append(str(e)))
  request=page.request
  keys=[r['k'] for r in request.get(base+'/releases/data.json').json() if r.get('k')][:30]
  fixture=request.post(api+'/lists',headers=auth,data={'title':'Tab workflow check','keys':keys}).json()
  try:
   page.goto(base+'/__preview__/tester'); page.goto(base+'/releases/?collection=all'); page.wait_for_function('booted'); page.evaluate('window.sameDocument = 123')
   page.locator('#q').fill('194'); page.wait_for_timeout(200)
   page.locator('#collection-favorites').click(); expect(page.locator('#favmanagement')).to_be_visible(); expect(page.locator('#q')).to_have_value('')
   page.locator('#collection-all').click(); expect(page.locator('#q')).to_have_value('194'); assert page.evaluate('window.sameDocument')==123
   page.go_back(); expect(page.locator('#favmanagement')).to_be_visible(); page.go_forward(); expect(page.locator('#q')).to_have_value('194')
   page.locator('#collection-summary').click(); page.locator('#collection-menu').get_by_role('button', name=fixture['title'], exact=True).click(); expect(page.locator('#clname')).to_have_text(fixture['title']); expect(page.locator('#q')).to_have_value(''); assert page.evaluate('sortKey')=='title'
   page.locator('#clpin').click(); expect(page.locator('#collection-pins a')).to_have_text(fixture['title'])
   page.locator('#collection-all').click(); expect(page.locator('#q')).to_have_value('194'); page.locator('#collection-pins a').click(); expect(page.locator('#clname')).to_have_text(fixture['title'])
   page.locator('#srcsummary').click(); page.locator('#srcfavorites').check(); page.locator('#srcsummary').click(); expect(page.locator('#favchip')).to_be_visible(); page.locator('#favchip').click(); expect(page.locator('#favchip')).to_be_hidden()
   page.locator('#collection-all').click(); page.locator('#q').fill(''); page.wait_for_timeout(150); page.locator('.tablewrap').evaluate('(e)=>e.scrollTop=1000'); top=page.locator('.tablewrap').evaluate('(e)=>e.scrollTop'); assert top>100
   page.locator('#collection-favorites').click(); page.locator('#collection-all').click(); page.wait_for_timeout(150); assert abs(page.locator('.tablewrap').evaluate('(e)=>e.scrollTop')-top)<2
   # Quick switches must ignore responses from a previous collection.
   page.locator('#collection-pins a').click(); page.locator('#collection-favorites').click(); expect(page.locator('#clbar')).to_be_hidden(); expect(page.locator('#collection-favorites')).to_have_attribute('aria-current','page')
   page.reload(); page.wait_for_function('booted'); page.locator('#collection-all').click(); expect(page.locator('#q')).to_have_value(''); assert page.locator('.tablewrap').evaluate('(e)=>e.scrollTop')==0
   assert page.locator('#collection-select option[value=""]').count()==0
   shots=Path.home()/'.codex/project-notes/misterzine/custom-lists-workspace-qa'
   for width in [1280,390]:
    page.set_viewport_size({'width':width,'height':800}); page.screenshot(path=str(shots/f'folder-tabs-{width}.png')); assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
   page.set_viewport_size({'width':1280,'height':800}); page.locator('#collection-pins a').click(); expect(page.locator('#clpin')).to_have_text('Unpin tab'); page.locator('#clpin').click(); expect(page.locator('#collection-pins a')).to_have_count(0)
   # Failed loads keep the pin and offer a retry, never a deletion warning.
   page.route('**/lists/'+fixture['id'],lambda route:route.abort())
   page.locator('#collection-all').click(); page.locator('#clpin').wait_for(state='hidden'); page.locator('#collection-pins a').count()
   page.goto(base+'/releases/?list='+fixture['id']); expect(page.locator('#clstatus')).to_contain_text('Could not load this list'); expect(page.locator('#clretry')).to_be_visible(); page.screenshot(path=str(shots/'list-load-error.png'))
   page.unroute('**/lists/'+fixture['id']); page.locator('#clretry').click(); expect(page.locator('#clpin')).to_be_visible()
   page.locator('#q').fill('zzzz-no-such-game'); expect(page.locator('#clclearfilters')).to_be_visible(); page.screenshot(path=str(shots/'list-filter-empty.png')); page.locator('#clclearfilters').click(); expect(page.locator('#clclearfilters')).to_be_hidden()
   # A deleted pin keeps its title and opens an explanatory removal state.
   page.locator('#clpin').click(); expect(page.locator('#collection-pins a')).to_have_count(1)
   request.delete(api+'/lists/'+fixture['id'],headers=auth,data={'version':fixture['version']})
   page.locator('#collection-all').click(); page.locator('#collection-pins a').click()
   expect(page.locator('#clstatus')).to_contain_text('deleted or is no longer shared'); expect(page.locator('#collection-pins a')).to_contain_text('Unavailable')
   for width in [1280,390]:
    page.set_viewport_size({'width':width,'height':800}); page.screenshot(path=str(shots/f'list-unavailable-{width}.png'))
   page.locator('#clremoveunavailable').click(); expect(page.locator('#collection-pins a')).to_have_count(0); expect(page.locator('#collection-all')).to_have_attribute('aria-current','page'); expect(page.locator('#collection-notice')).to_contain_text('removed from your lists')
   page.locator('#collection-manage').click(); page.wait_for_url('**/releases/?collection=manage'); expect(page.locator('#lib-library')).to_be_visible()
   assert not errors,errors
   print('PASS in-place tabs, Back/Forward, per-view search/sort/scroll, visit-only memory, account pins, Source filter, mobile overflow')
  finally:
   request.delete(api+'/pins/'+fixture['id'],headers=auth)
   latest=request.get(api+'/lists/'+fixture['id'],headers=auth).json();
   if 'version' in latest: request.delete(api+'/lists/'+fixture['id'],headers=auth,data={'version':latest['version']})
   browser.close()
if __name__=='__main__': main()
