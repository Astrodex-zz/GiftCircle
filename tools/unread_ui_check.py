"""Synthetic UI verification for unread navigation and narrow mobile layouts."""
import ast
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tools/release-check';OUT.mkdir(exist_ok=True)
tree=ast.parse((ROOT/'tools/ui_release_check.py').read_text(encoding='utf-8'))
MOCK=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MOCK' for t in n.targets))
EXTRA=r'''
const originalFetch=window.fetch;
qa.chats={1:{giver:[{id:1,content:'From my recipient',mine:false}],santa:[{id:2,content:'From my giver',mine:false}],group:[{id:3,content:'Hello group',mine:false,name:'Morgan'}]},2:{giver:[],santa:[],group:[{id:4,content:'Second exchange message',mine:false,name:'Morgan'}]}};
qa.read={};qa.acks=[];
exchanges[0].name='Friday the 13th Spook-o-rama!!!';
window.fetch=async(url,opts={})=>{
 const path=String(url).replace('/api','');const response=result=>({ok:true,json:async()=>JSON.parse(JSON.stringify(result))});
 if(path==='/messages/unread'){
  const result={total:0,exchanges:{}};
  for(const [eid,channels] of Object.entries(qa.chats)){
   const counts={total:0};for(const [channel,rows] of Object.entries(channels)){counts[channel]=rows.filter(m=>!m.mine&&m.id>(qa.read[eid+channel]||0)).length;counts.total+=counts[channel]}
   result.exchanges[eid]=counts;result.total+=counts.total;
  }return response(result);
 }
 const read=path.match(/^\/exchanges\/(\d+)\/messages\/read\/(giver|santa|group)$/);
 if(read){const through=JSON.parse(opts.body).through_id;qa.read[read[1]+read[2]]=through;qa.acks.push([read[1],read[2],through]);return response({ok:true})}
 const chat=path.match(/^\/exchanges\/(\d+)\/(messages\/(20|21)|group-messages)$/);
 if(chat){const channel=chat[2]==='group-messages'?'group':chat[3]==='20'?'giver':'santa';const rows=qa.chats[chat[1]][channel];
  if(opts.method==='POST')rows.push({id:99,content:JSON.parse(opts.body).content,mine:true});
  return response(channel==='group'?rows:{label:channel==='giver'?'Jamie':'Your Mystery Gifter',messages:rows});
 }
 return originalFetch(url,opts);
};
'''
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    for width in [320,390,768,1440]:
        page=browser.new_page(viewport={'width':width,'height':900})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        html='<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+(ROOT/'app/static/style.css').read_text(encoding='utf-8')+'</style></head><body><div id="app"></div><script>'+MOCK+EXTRA+'</script><script>'+(ROOT/'app/static/app.js').read_text(encoding='utf-8')+'</script></body></html>'
        page.route('**/*',lambda r:r.fulfill(content_type='text/html',body=html))
        page.goto('http://giftcircle.test/#home')
        nav=page.locator(('.mobile-bar' if width<=690 else '.nav')+' [data-page=messages]')
        expect(nav.locator('.unread-badge')).to_have_text('4')
        expect(nav).to_have_class('has-unread')
        nav.click()
        expect(page.locator('.chat-body')).to_contain_text('From my recipient')
        expect(page.locator('[data-chat=giver] .unread-badge')).to_be_hidden()
        expect(page.locator('[data-chat=santa] .unread-badge')).to_have_text('1')
        expect(page.locator('[data-chat=group] .unread-badge')).to_have_text('1')
        page.locator('[data-chat=santa]').click()
        expect(page.locator('.chat-body')).to_contain_text('From my giver')
        expect(page.locator('[data-chat=santa] .unread-badge')).to_be_hidden()
        expect(page.locator('[data-chat=group] .unread-badge')).to_have_text('1')
        # New incoming messages update badges without replacing the draft.
        page.locator('#message-form textarea').fill('A work in progress')
        page.evaluate("qa.chats[1].group.push({id:5,content:'New arrival',mine:false,name:'Morgan'});refreshAccess()")
        expect(page.locator('[data-chat=group] .unread-badge')).to_have_text('2')
        expect(page.locator('#message-form textarea')).to_have_value('A work in progress')
        page.get_by_role('button',name='Send message',exact=True).click()
        expect(page.locator('.chat-body')).to_contain_text('A work in progress')
        page.locator('[data-chat=group]').click()
        expect(page.locator('[data-chat=group] .unread-badge')).to_be_hidden()
        expect(nav.locator('.unread-badge')).to_have_text('1')
        nav.click() # jumps to remaining unread conversation in the other exchange
        expect(page.locator('.active-exchange h2')).to_have_text('Birthday gifts')
        expect(page.locator('.chat-body')).to_contain_text('Second exchange message')
        expect(nav.locator('.unread-badge')).to_be_hidden()
        page.locator('[data-chat=santa]').click()
        expect(page.locator('.empty')).to_contain_text('No messages yet')
        bounds=page.locator('#chat-body').bounding_box();icon=page.locator('.chat-body .em-icon').bounding_box()
        assert icon['y']>=bounds['y'] and icon['y']+icon['height']<=bounds['y']+bounds['height'],(width,bounds,icon)
        send=page.locator('.send-message').bounding_box()
        assert 43<=send['width']<=45 and 43<=send['height']<=45,send
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path=str(OUT/f'messages-empty-{width}.png'),full_page=True)
        page.locator('[data-exchange="1"]').evaluate('(el)=>el.click()')
        expect(page.locator('h1')).to_contain_text('Spook-o-rama')
        expect(page.locator('.exchange-message-button')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path=str(OUT/f'exchange-unread-{width}.png'),full_page=True)
        assert not errors,errors
        print(f'{width}px: PASS unread routing/counts, independent tabs, drafts, compact Send, empty icon and layout')
        page.close()
    browser.close()
