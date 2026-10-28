"""Check empty collections and explicit unfollow/unpin behavior with isolated fixtures."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import custom_lists_preview as preview
s=json.loads((preview.DEFAULT_STATE/'state.json').read_text());base,api=s['site'],s['api']
a={'Authorization':'Bearer '+s['follower_token']};t={'Authorization':'Bearer '+s['tester_token']}
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':1280,'height':800});r=page.request
 f=r.post(api+'/lists',headers=a,data={'title':'Empty community collection check','keys':[]}).json()
 try:
  f=r.put(api+'/lists/'+f['id'],headers=a,data={**f,'visibility':'public'}).json()
  page.goto(base+'/__preview__/tester');page.goto(base+'/releases/?list='+f['id']);expect(page.locator('#clempty')).to_contain_text('no entries yet');expect(page.locator('#clclearfilters')).to_be_hidden()
  page.locator('#clpin').click();expect(page.locator('#clfollow')).to_have_text('Unfollow & unpin');page.locator('#clpin').click();expect(page.locator('#clstatus')).to_contain_text('still in Your lists');expect(page.locator('#clfollow')).to_have_text('Unfollow')
  page.locator('#clpin').click();expect(page.locator('#clfollow')).to_have_text('Unfollow & unpin');page.locator('#clfollow').click();expect(page.locator('#clfollow')).to_have_text('Follow list');expect(page.locator('#collection-pins a')).to_have_count(0)
  page.locator('#clpin').click();expect(page.locator('#clfollow')).to_have_text('Unfollow & unpin');page.locator('#collection-manage').click();page.locator('#lib-following-cards .list-card').filter(has=page.get_by_role('heading',name=f['title'],exact=True)).get_by_role('button',name='Following',exact=True).click();expect(page.locator('#lib-following-cards')).to_contain_text(f['title']);page.locator('#collection-all').click();page.locator('#collection-manage').click();expect(page.locator('#lib-following-cards')).not_to_contain_text(f['title']);expect(page.locator('#collection-pins a')).to_have_count(0)
  print('PASS empty list, unpin retains follow, viewer and Manage unfollow remove pin')
 finally:
  r.delete(api+'/pins/'+f['id'],headers=t);r.delete(api+'/following/'+f['id'],headers=t);r.delete(api+'/lists/'+f['id'],headers=a,data={'version':f['version']});b.close()
