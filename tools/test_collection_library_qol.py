"""Local library workflow checks using disposable lists."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import custom_lists_preview as preview

state=json.loads((preview.DEFAULT_STATE/'state.json').read_text())
base,api=state['site'],state['api']
assert base.startswith('http://localhost:') and api.startswith('http://localhost:')
with sync_playwright() as p:
 b=p.chromium.launch(); page=b.new_page(viewport={'width':1280,'height':900}); r=page.request
 auth={'Authorization':'Bearer '+state['tester_token']}; foreign={'Authorization':'Bearer '+state['follower_token']}; fixtures=[]; errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 def create(title,headers,description='',public=False):
  row=r.post(api+'/lists',headers=headers,data={'title':title,'keys':[key],'description':description}).json(); fixtures.append((row['id'],headers))
  if public: row=r.put(api+'/lists/'+row['id'],headers=headers,data={**row,'visibility':'public'}).json()
  return row
 def card(host,row): return page.locator(host+' .list-card').filter(has=page.get_by_role('heading',name=row['title'],exact=True))
 try:
  data=r.get(base+'/releases/data.json').json(); game=next(x for x in data if x.get('k') and x.get('core')); key=game['k']
  own=create('Library QoL A private',auth,'Unique description needle. '+('Long notes about these arcade choices. '*40))
  other=create('Library QoL Z community',foreign,public=True)
  public=create('Library QoL B public',auth,public=True)
  page.goto(base+'/__preview__/tester'); page.goto(base+'/releases/?collection=manage')
  search=page.get_by_role('searchbox',name='Search your saved lists'); sort=page.get_by_role('combobox',name='Sort your saved lists')
  search.fill('description needle'); expect(page.locator('#lib-owned-cards .list-card')).to_have_count(1)
  c=card('#lib-owned-cards',own); expect(c).to_be_visible(); expect(c).not_to_contain_text('0 followers'); expect(c).not_to_contain_text('Created')
  toggle=c.locator('.description-toggle'); expect(toggle).to_be_visible(); toggle.click(); expect(toggle).to_have_attribute('aria-expanded','true'); toggle.click()
  c.locator('.list-preview summary').click(); expect(c.locator('.list-preview li')).to_contain_text(game['title']); c.get_by_role('button',name='Close preview').click()
  search.fill('zz-no-match'); expect(page.locator('#lib-owned-empty')).to_contain_text('match your search'); page.get_by_role('button',name='Clear search',exact=True).click(); expect(c).to_be_visible()
  search.fill('Library QoL'); sort.select_option('title'); expect(page.locator('#lib-owned-cards h3')).to_have_text([own['title'],public['title']]); page.locator('#collection-browse').click(); page.locator('#collection-manage').click(); expect(search).to_have_value('Library QoL'); expect(sort).to_have_value('title')
  page.locator('#collection-browse').click(); page.locator('#lib-search').fill('Library QoL'); expect(page.locator('#lib-directory-cards .list-card')).to_have_count(2)
  public_card=card('#lib-directory-cards',public); preview_button=public_card.locator('.list-preview summary'); view_button=public_card.get_by_role('link',name='Full table view',exact=True); preview_button.hover(); preview_style=preview_button.evaluate('(e)=>[getComputedStyle(e).borderColor,getComputedStyle(e).backgroundColor]'); view_button.hover(); assert view_button.evaluate('(e)=>[getComputedStyle(e).borderColor,getComputedStyle(e).backgroundColor]')==preview_style; assert abs(page.locator('#lib-search').bounding_box()['y']+page.locator('#lib-search').bounding_box()['height']-page.locator('#lib-search-form button').bounding_box()['y']-page.locator('#lib-search-form button').bounding_box()['height'])<2; expect(public_card.get_by_role('button',name='Your list',exact=True)).to_be_disabled()
  before=public_card.bounding_box()['height']; other_card=card('#lib-directory-cards',other); other_card.locator('.list-preview summary').click(); expect(other_card.locator('.list-preview li')).to_have_count(1); assert abs(public_card.bounding_box()['height']-before)<2; popup=other_card.locator('.list-preview-body'); pb=popup.bounding_box(); trigger=other_card.locator('.list-preview summary').bounding_box(); assert pb['x']>=0 and pb['x']+pb['width']<=1280; assert abs(pb['x']-trigger['x'])<500;  other_card.get_by_role('button',name='Close preview').click()
  page.locator('#lib-search').fill(other['title']); expect(page.locator('#lib-directory-cards .list-card')).to_have_count(1)
  c=card('#lib-directory-cards',other); follow=c.get_by_role('button',name='Follow list',exact=True); expect(follow).to_be_enabled()
  page.route('**/following/'+other['id'],lambda route:route.abort()); follow.click(); expect(page.locator('#lib-message')).to_contain_text('Could not follow'); expect(follow).to_be_enabled(); page.unroute('**/following/'+other['id'])
  follow.click(); expect(c.get_by_role('button',name='Following',exact=True)).to_have_attribute('aria-pressed','true'); expect(page.locator('#collection-browse')).to_have_attribute('aria-current','page'); c.get_by_role('button',name='Following',exact=True).click(); expect(c.get_by_role('button',name='Follow list',exact=True)).to_be_enabled(); c.get_by_role('button',name='Follow list',exact=True).click(); expect(c.get_by_role('button',name='Following',exact=True)).to_have_attribute('aria-pressed','true')
  page.locator('#collection-manage').click(); followed=card('#lib-following-cards',other); expect(followed).to_be_visible(); followed.get_by_role('button',name='Following',exact=True).click(); expect(followed).to_be_visible(); expect(followed).to_contain_text('You can follow again'); page.locator('#lib-refresh').click(); expect(followed).to_be_visible(); followed.get_by_role('button',name='Follow list',exact=True).click(); expect(followed.get_by_role('button',name='Following',exact=True)).to_have_attribute('aria-pressed','true'); followed.locator('.list-preview summary').click(); expect(followed.locator('.list-preview li')).to_contain_text(game['title']); followed.get_by_role('button',name='Close preview').click()
  for width in [1280,390,320]:
   page.set_viewport_size({'width':width,'height':900}); expect(search).to_be_visible(); assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   followed.locator('.list-preview summary').click(); expect(followed.locator('.list-preview li')).to_have_count(1); popup=followed.locator('.list-preview-body'); box=popup.bounding_box(); assert box['x']>=0 and box['x']+box['width']<=width+1 and box['y']>=0 and box['y']+box['height']<=901; page.screenshot(path=str(Path.home()/f'.codex/project-notes/misterzine/custom-lists-workspace-qa/library-qol-{width}.png')); followed.get_by_role('button',name='Close preview').click()
  # Account switch must immediately clear an open private preview.
  c=card('#lib-owned-cards',own); c.locator('.list-preview summary').click(); expect(c.locator('.list-preview li')).to_have_count(1)
  page.evaluate("localStorage.removeItem('mz-token'); window.dispatchEvent(new StorageEvent('storage',{key:'mz-token'}))")
  expect(page.locator('#lib-out')).to_be_visible(); expect(page.locator('#lib-owned-cards .list-preview li')).to_have_count(0)
  page.goto(base+'/__preview__/tester'); page.goto(base+'/lists/?view=mine'); page.get_by_role('searchbox',name='Search your saved lists').fill('description needle'); expect(card('#owned-cards',own)).to_be_visible()
  assert not errors,errors
  print('PASS saved-list search/sort retention, descriptions, private/followed previews, direct follow/retry, mobile layout, sign-out clearing and standalone Manage')
 finally:
  for ident,headers in fixtures:
   r.delete(api+'/pins/'+ident,headers=auth); r.delete(api+'/following/'+ident,headers=auth)
   current=r.get(api+'/lists/'+ident,headers=headers)
   if current.status==200:r.delete(api+'/lists/'+ident,headers=headers,data={'version':current.json()['version']})
  b.close()
