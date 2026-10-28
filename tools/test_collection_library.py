import re
"""Exercise Browse/Manage as tracker tabs, including responsive layouts."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import custom_lists_preview as preview

def main():
 state=json.loads((preview.DEFAULT_STATE/'state.json').read_text()); base,api=state['site'],state['api']; auth={'Authorization':'Bearer '+state['tester_token']}; fixtures=[]
 shots=Path.home()/'.codex/project-notes/misterzine/custom-lists-workspace-qa'
 with sync_playwright() as p:
  b=p.chromium.launch(); context=b.new_context(viewport={'width':1440,'height':900}); page=context.new_page(); errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  try:
   context.request.put(api+'/me/profile',headers=auth,data={'display_name':'Preview curator'})
   key=next(r['k'] for r in context.request.get(base+'/releases/data.json').json() if r.get('title')=='1942 (Revision B)')
   row=context.request.post(api+'/lists',headers=auth,data={'title':'Library tab workflow','keys':[key],'description':'A collection for browser workflow checks.'}).json();fixtures.append(row['id'])
   res=context.request.put(api+'/lists/'+row['id'],headers=auth,data={**row,'visibility':'public'});assert res.status==200
   page.goto(base+'/__preview__/tester');page.goto(base+'/releases/?collection=all');page.wait_for_function('booted');page.evaluate('window.noReload = 123');page.locator('#q').fill('1942')
   page.locator('#collection-browse').click();expect(page.locator('#lib-directory')).to_be_visible();expect(page.locator('#cllayout')).to_be_hidden();expect(page.locator('#cols')).to_be_hidden();expect(page.locator('#resizer')).to_be_hidden()
   page.locator('#lib-search').fill('Library tab workflow');expect(page.locator('#lib-directory-cards')).to_contain_text(row['title']);page.locator('#lib-directory-cards .list-card').filter(has=page.get_by_role('heading',name=row['title'],exact=True)).get_by_role('link',name='View games',exact=True).click();expect(page.locator('#clname')).to_have_text(row['title']);assert page.evaluate('window.noReload')==123
   expect(page.locator('#collection-summary')).to_have_text('Your lists');expect(page.locator('#collection-summary')).to_have_class(re.compile('(^| )active( |$)'));assert page.locator('#collection-summary').evaluate("e=>getComputedStyle(e).borderBottomColor == getComputedStyle(e).backgroundColor")
   page.locator('#clpin').click();expect(page.locator('#collection-summary')).to_have_text('Your lists');expect(page.locator('#collection-summary')).not_to_have_class(re.compile('(^| )active( |$)'))
   page.locator('#collection-browse').click();expect(page.locator('#lib-search')).to_have_value('Library tab workflow');expect(page.locator('#lib-directory-cards')).to_contain_text(row['title'])
   page.locator('#lib-directory-cards').get_by_role('link',name='Preview curator',exact=True).click();expect(page.locator('#lib-curator-view')).to_be_visible();page.locator('#collection-browse').click();expect(page.locator('#lib-directory')).to_be_visible();
   page.locator('#collection-manage').click();expect(page.locator('#lib-library')).to_be_visible();page.locator('#lib-owned-cards').get_by_role('heading',name=row['title']).wait_for();assert page.evaluate('window.noReload')==123
   card=page.locator('#lib-owned-cards .list-card').filter(has=page.get_by_role('heading',name=row['title'],exact=True));card.get_by_role('button',name='Delete',exact=True).click();expect(page.locator('#lib-delete-dialog')).to_be_visible();page.locator('#lib-delete-cancel').click();expect(card).to_be_visible()
   page.go_back();expect(page.locator('#lib-directory')).to_be_visible();page.go_forward();expect(page.locator('#lib-library')).to_be_visible()
   for width,height in [(1440,900),(1024,768),(390,844),(320,700)]:
    page.set_viewport_size({'width':width,'height':height});page.locator('#collection-manage').click();expect(page.locator('#collection-library')).to_be_visible();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    page.locator('#collection-summary').click();expect(page.locator('#collection-menu')).to_be_visible();page.wait_for_function("(()=>{const b=document.getElementById('collection-menu').getBoundingClientRect();return b.left>=0 && b.right<=innerWidth+1})()")
    assert page.locator('#collection-menu').get_by_text('Manage your lists...',exact=True).count()==0
    page.locator('#collection-summary').click();page.screenshot(path=str(shots/f'library-manage-{width}.png'))
    page.locator('#collection-browse').click();page.screenshot(path=str(shots/f'library-browse-{width}.png'))
    print('PASS library tabs and dropdown bounds',width,height)
   page.locator('#collection-all').click();expect(page.locator('#q')).to_have_value('1942')
   page.locator('#collection-manage').click();card.get_by_role('button',name='Delete',exact=True).click();page.locator('#lib-delete-confirm').click();expect(card).to_have_count(0);expect(page.locator('#lib-message')).to_contain_text('List deleted');
   page.goto(base+'/__preview__/anonymous');page.goto(base+'/releases/?collection=manage');expect(page.locator('#lib-out')).to_be_visible();page.locator('#collection-browse').click();expect(page.locator('#lib-directory')).to_be_visible()
   assert not errors,errors
   print('PASS no reload, card navigation, history, table search retention, pinned dropdown and signed-out management')
  finally:
   for ident in fixtures:
    context.request.delete(api+'/pins/'+ident,headers=auth);r=context.request.get(api+'/lists/'+ident,headers=auth).json();
    if 'version' in r: context.request.delete(api+'/lists/'+ident,headers=auth,data={'version':r['version']})
   b.close()
if __name__=='__main__':main()
