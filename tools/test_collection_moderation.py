"""In-place moderation regression; mutate disposable fixtures only."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import custom_lists_preview as preview
state=json.loads((preview.DEFAULT_STATE/'state.json').read_text())
base,api=state['site'],state['api']
assert base.startswith('http://localhost:') and api.startswith('http://localhost:')
with sync_playwright() as p:
 b=p.chromium.launch(); context=b.new_context(viewport={'width':1280,'height':900}); page=context.new_page(); r=page.request
 auth={'Authorization':'Bearer '+state['tester_token']}; errors=[]; fixture=None
 page.on('pageerror',lambda e:errors.append(str(e)))
 try:
  fixture=r.post(api+'/lists',headers=auth,data={'title':'Moderation disposable fixture','description':'A fixture for moderation checks.','keys':[]}).json()
  fixture=r.put(api+'/lists/'+fixture['id'],headers=auth,data={**fixture,'visibility':'public'}).json(); assert 'id' in fixture
  assert r.get(base+'/lists/admin.html').status==404
  page.goto(base+'/__preview__/tester'); page.goto(base+'/releases/?collection=browse'); page.locator('#menusum').click();expect(page.locator('#mz-admin-toggle')).to_have_count(0)
  page.goto(base+'/__preview__/admin');page.evaluate("localStorage.removeItem('mz-admin-mode')");page.goto(base+'/releases/?collection=browse');page.locator('#menusum').click()
  toggle=page.get_by_role('button',name='Admin: off',exact=True);expect(toggle).to_be_visible();expect(page.locator('[data-moderate]')).to_have_count(0);toggle.click();expect(page.get_by_role('button',name='Admin: on',exact=True)).to_have_attribute('aria-pressed','true');page.locator('#menusum').click()
  page.locator('#lib-search').fill(fixture['title']);c=page.locator('#lib-directory-cards .list-card').filter(has_text=fixture['title']);c.get_by_role('button',name='Moderate list',exact=True).click()
  d=page.locator('.mz-moderation');expect(d).to_be_visible();d.get_by_role('button',name='Hide list',exact=True).click();assert r.get(api+'/public/lists/'+fixture['id']).status==200
  d.get_by_role('textbox',name='Reason (visible to the author)').fill('Test moderation reason');d.get_by_role('button',name='Hide list',exact=True).click();expect(d.get_by_role('button',name='Restore list',exact=True)).to_be_visible();assert r.get(api+'/public/lists/'+fixture['id']).status==404
  d.get_by_role('button',name='Close',exact=True).click();expect(c).to_be_visible();expect(c.get_by_role('button',name='Hidden - moderate')).to_be_visible()
  page.reload();page.get_by_role('checkbox',name='Hidden lists only').check();expect(c).to_be_visible();c.get_by_role('button',name='Hidden - moderate').or_(c.get_by_role('button',name='Moderate list',exact=True)).click();expect(d.get_by_role('button',name='Restore list',exact=True)).to_be_visible()
  for width in [1280,390,320]:
   page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(Path.home()/f'.codex/project-notes/misterzine/custom-lists-workspace-qa/moderation-inline-{width}.png'))
  d.get_by_role('button',name='Restore list',exact=True).click();expect(d.get_by_role('button',name='Hide list',exact=True)).to_be_visible();assert r.get(api+'/public/lists/'+fixture['id']).status==200;d.get_by_role('button',name='Close',exact=True).click()
  page.set_viewport_size({'width':1280,'height':900});page.goto(base+'/releases/?list='+fixture['id']);page.locator('.clviewactions [data-moderate]').click();expect(d).to_be_visible();d.get_by_role('button',name='Close',exact=True).click()
  other=context.new_page();other.goto(base+'/');other.locator('#menusum').click();expect(other.get_by_role('button',name='Admin: on',exact=True)).to_be_visible();other.get_by_role('button',name='Admin: on',exact=True).click();expect(page.locator('[data-moderate]')).to_have_count(0);other.close()
  page.reload();page.locator('#menusum').click();expect(page.get_by_role('button',name='Admin: off',exact=True)).to_be_visible()
  page.evaluate("localStorage.removeItem('mz-token');window.dispatchEvent(new StorageEvent('storage',{key:'mz-token'}))");expect(page.locator('#mz-admin-toggle')).to_be_hidden();expect(page.locator('[data-moderate]')).to_have_count(0)
  assert not errors,errors
  print('PASS account gating, menu toggle, in-place hide/restore, retained cards, hidden filter, full-view controls, site-wide persistence and cross-tab clearing; desktop/mobile layouts')
 finally:
  if fixture and 'id' in fixture:
   current=r.get(api+'/lists/'+fixture['id'],headers=auth)
   if current.status==200:r.delete(api+'/lists/'+fixture['id'],headers=auth,data={'version':current.json()['version']})
  b.close()
