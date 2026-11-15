"""Synthetic organiser overview layout and visibility checks."""
import ast
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tools/release-check';OUT.mkdir(exist_ok=True)
tree=ast.parse((ROOT/'tools/ui_release_check.py').read_text(encoding='utf-8'))
MOCK=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MOCK' for t in n.targets))
EXTRA=r'''
const originalFetch=window.fetch;
qa.statusCalls=0;
window.fetch=async(url,opts={})=>{
 if(String(url).endsWith('/organiser-overview')){
  qa.statusCalls++;
  return {ok:true,json:async()=>({participants:['Alex','Jamie','Morgan','Taylor','Casey','Avery','Jordan','Riley','Robin','A long participant name'].map((name,i)=>({id:i+1,name,reveal_used:i%3===0,wish_count:i%4,list_status:i%4===0||i%2?'draft':'finalised',unread:{giver:i%3,santa:0,group:i%2}}))})};
 }
 return originalFetch(url,opts);
};
'''
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    for width in [320,390,768,1440]:
        page=browser.new_page(viewport={'width':width,'height':950})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        html='<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+(ROOT/'app/static/style.css').read_text(encoding='utf-8')+'</style></head><body><div id="app"></div><script>'+MOCK+EXTRA+'</script><script>'+(ROOT/'app/static/app.js').read_text(encoding='utf-8')+'</script></body></html>'
        page.route('**/*',lambda r:r.fulfill(content_type='text/html',body=html))
        page.goto('http://giftcircle.test/#exchanges/1')
        panel=page.locator('.organiser-overview')
        expect(panel).to_be_visible()
        expect(panel.locator('tbody tr')).to_have_count(10)
        expect(panel).to_contain_text('Finalised')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        assert panel.evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
        panel.screenshot(path=str(OUT/f'organiser-{width}.png'))
        print('Panel height:',width,panel.bounding_box()['height'])
        assert panel.bounding_box()['height']<780
        assert panel.locator('button').count()==0
        assert not panel.locator('a').count()
        panel.screenshot(path=str(OUT/f'organiser-{width}.png'))
        calls=page.evaluate('qa.statusCalls')
        page.reload()
        expect(panel).to_be_visible()
        # An ordinary participant never even requests the organiser endpoint.
        page.evaluate('family.owner_id=99;exchanges.forEach(e=>e.owner=false);sync(true)')
        expect(panel).to_have_count(0)
        assert page.evaluate('qa.statusCalls')==calls
        assert not errors,errors
        print(f'{width}px: PASS 10 compact rows, no overflow/actions, reload, organiser-only visibility')
        page.close()
    browser.close()
