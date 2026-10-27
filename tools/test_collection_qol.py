"""Collection empty states, scoped counts, and duplicate preflight at desktop/mobile sizes."""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import custom_lists_preview as preview

def main():
 state=json.loads((preview.DEFAULT_STATE/'state.json').read_text()); base,api=state['site'],state['api']; auth={'Authorization':'Bearer '+state['tester_token']}
 shots=Path.home()/'.codex/project-notes/misterzine/custom-lists-workspace-qa'
 with sync_playwright() as p:
  browser=p.chromium.launch(); context=browser.new_context(); page=context.new_page(); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
  key=next(r['k'] for r in context.request.get(base+'/releases/data.json').json() if r.get('title')=='1942 (Revision B)')
  fixture=context.request.post(api+'/lists',headers=auth,data={'title':'Collection UX checks','keys':[key]}).json()
  try:
   page.goto(base+'/__preview__/tester')
   for width,height in [(1440,1000),(1280,800),(1024,768),(390,844),(320,700)]:
    page.set_viewport_size({'width':width,'height':height}); page.goto(base+'/releases/?list='+fixture['id']); expect(page.locator('#clname')).to_have_text(fixture['title']); expect(page.locator('#count')).to_have_text('1')
    expect(page.locator('#totop')).to_be_hidden(); expect(page.locator('#torow')).to_be_hidden()
    page.locator('#q').fill('no such game xyz'); expect(page.locator('#count')).to_have_text(re.compile(r'^0(?:/| of )1$'),timeout=5000)
    page.locator('#q').fill(''); page.locator('#collection-summary').click(); expect(page.locator('#collection-menu')).to_be_visible(); box=page.locator('#collection-menu').bounding_box(); assert box['x']>=0 and box['x']+box['width']<=width+1
    page.locator('#collection-menu').get_by_role('button',name=fixture['title'],exact=True).click()
    page.screenshot(path=str(shots/f'collection-qol-{width}.png'))
    page.goto(base+'/releases/?list='+fixture['id']+'#'+key); page.locator('#panel .clentryactions button').click(); page.locator('#clentrytarget').select_option(fixture['id']); expect(page.locator('#clentryaddyes')).to_have_text('Already in this list'); expect(page.locator('#clentryaddyes')).to_be_disabled(); expect(page.locator('#clentrystatus')).to_contain_text('already in this list')
    page.locator('#clentrydialog [data-clclose]').click()
    print('PASS scoped counts, short-list shortcuts, dropdown bounds and duplicate preflight',width,height)
   page.goto(base+'/__preview__/anonymous'); page.goto(base+'/releases/?collection=favorites'); expect(page.locator('#rows')).to_contain_text('No favorites yet.'); expect(page.locator('#totop')).to_be_hidden(); page.screenshot(path=str(shots/'favorites-empty-mobile.png'))
   assert not errors,errors
  finally:
   context.request.delete(api+'/lists/'+fixture['id'],headers=auth,data={'version':fixture['version']}); browser.close()
if __name__=='__main__':main()
