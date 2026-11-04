"""Isolated release UI checks. No live accounts, emails or production data."""
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tools/release-check';OUT.mkdir(exist_ok=True)
MOCK=r'''
window.qa={removed:false,signedIn:true,finalised:false,profileWrites:0,own:[{id:11,title:'A good book',details:'Science fiction',price:'$20'}],recipient:[{id:12,title:'A board game',details:'Something for game night',price:'$40',reserved:false,reserved_by_me:false,purchased_by_me:false}],messages:[]};
const me={id:1,email:'alex@example.com',name:'Alex',notify_email:true,name_confirmed:true};
const family={id:1,name:'Test group',owner_id:1,members:[{id:1,name:'Alex'},{id:2,name:'Jamie'},{id:3,name:'Morgan'}],pending:[]};
const exchanges=[1,2].map(id=>({id,name:id===1?'Game night':'Birthday gifts',family_id:1,family_name:'Test group',owner:true,drawn:true,budget:50,exchange_date:'2027-06-10',participants:family.members,reservation_mode:'show',my_recipient:{id:2,name:'Jamie'},my_assignment:{assignment_id:20,recipient_id:2,name:'Jamie'},my_santa_conversation:21}));
window.fetch=async(url,opts={})=>{
 const path=String(url).replace('/api',''),method=opts.method||'GET',data=opts.body?JSON.parse(opts.body):{};let result={ok:true};
 const response=(data,ok=true)=>({ok,json:async()=>data});
 if(path==='/reveal'){qa.revealCalls=(qa.revealCalls||0)+1;return response({exchange_name:'Game night',group_name:'Test group',recipient_name:'Jamie',budget:50,exchange_date:'2027-06-10'})}
 if(path==='/auth/logout'){qa.signedIn=false;return response(result)}
 if(!qa.signedIn)return response({detail:'Please sign in'},false);
 if(path==='/me'){if(method==='PATCH'){qa.profileWrites++;Object.assign(me,data)}result=me}
 else if(path==='/messages/unread')result={total:0,exchanges:{}};
 else if(/\/messages\/read\//.test(path))result={ok:true};
 else if(path==='/families')result=qa.removed?[]:[family];
 else if(path==='/families/1')result=family;
 else if(path==='/invites'||path==='/notifications')result=[];
 else if(path==='/exchanges')result=qa.removed?[]:exchanges;
 else if(/^\/exchanges\/\d+$/.test(path))result=exchanges.find(e=>e.id===Number(path.split('/')[2]));
 else if(/\/wish-list\/finalise$/.test(path))qa.finalised=true;
 else if(/\/wish-list\/draft$/.test(path))qa.finalised=false;
 else if(/\/wish-list\/\d+$/.test(path))result={status:qa.finalised?'finalised':'draft'};
 else if(/\/wishes$/.test(path)&&method==='POST'){qa.own.push({id:13,...data});qa.finalised=false}
 else if(/\/wishes\/11$/.test(path)&&method==='DELETE')qa.own=qa.own.filter(w=>w.id!==11);
 else if(/\/wishes\/1$/.test(path))result=qa.own;
 else if(/\/wishes\/2$/.test(path))result=qa.recipient;
 else if(/\/wishes\/12\/reserve$/.test(path)){const w=qa.recipient[0];w.reserved=w.reserved_by_me=!w.reserved_by_me;w.purchased_by_me=false}
 else if(/\/wishes\/12\/purchase$/.test(path))qa.recipient[0].purchased_by_me=!qa.recipient[0].purchased_by_me;
 else if(/\/messages\/20$/.test(path)){if(method==='POST')qa.messages.push({id:1,content:data.content,mine:true,created_at:new Date().toISOString()});result={label:'Jamie',messages:qa.messages}}
 else if(/\/messages\/21$/.test(path))result={label:'Your Mystery Gifter',messages:[]};
 else if(/\/group-messages$/.test(path))result=[];
 else throw Error('Unhandled mock request: '+method+' '+path);
 return response(JSON.parse(JSON.stringify(result)));
};
'''
def overflow(page):
    result=page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
    assert result['scroll']<=result['width']+1,result

with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    for width,height in [(1440,1000),(768,1024),(390,844)]:
        page=browser.new_page(viewport={'width':width,'height':height})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        html='<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+ (ROOT/'app/static/style.css').read_text(encoding='utf-8')+'</style></head><body><div id="app"></div><script>'+MOCK+'</script><script>'+(ROOT/'app/static/app.js').read_text(encoding='utf-8')+'</script></body></html>'
        page.route('**/*',lambda route:route.fulfill(content_type='text/html',body=html))
        page.goto('http://giftcircle.test/#exchanges/1')
        expect(page.locator('h1')).to_have_text('Game night')
        expect(page.get_by_text('Gift ideas for Jamie',exact=True)).to_be_visible()
        expect(page.locator('.own-compact-wishlist')).to_contain_text('A good book')
        overflow(page)
        page.get_by_role('button',name='Reserve',exact=True).click()
        page.get_by_role('button',name='Mark bought',exact=True).click()
        expect(page.get_by_role('button',name='Undo bought')).to_be_visible()
        page.get_by_role('button',name='Add a gift').click()
        page.locator('#dialog-form [name=title]').fill('A new puzzle')
        page.get_by_role('button',name='Add to my list',exact=True).click()
        expect(page.locator('.own-compact-wishlist')).to_contain_text('A new puzzle')
        expect(page.locator('h1')).to_have_text('Game night')
        page.get_by_role('button',name='Finalise list',exact=True).click()
        expect(page.get_by_role('button',name='Mark as Draft')).to_be_visible()
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(OUT/f'exchange-{width}.png'),full_page=True)
        overflow(page)
        page.locator('.exchange-message-button').click()
        expect(page.locator('#message-form')).to_be_visible()
        page.locator('#message-form textarea').fill('A draft that must not disappear')
        page.locator('h1').click()
        page.evaluate('refreshAccess()')
        expect(page.locator('#message-form textarea')).to_have_value('A draft that must not disappear')
        page.get_by_role('button',name='Send',exact=False).last.click()
        expect(page.locator('.chat-body')).to_contain_text('A draft that must not disappear')
        # A notification link opens the intended conversation.
        page.goto('http://giftcircle.test/#messages/1/group')
        expect(page.locator('.chat-heading')).to_contain_text('Group conversation')
        page.goto('http://giftcircle.test/#exchanges/1')
        expect(page.locator('h1')).to_have_text('Game night')
        page.reload()
        expect(page.locator('h1')).to_have_text('Game night')
        page.goto('http://giftcircle.test/#exchanges/2')
        expect(page.locator('h1')).to_have_text('Birthday gifts')
        page.reload()
        expect(page.locator('h1')).to_have_text('Birthday gifts')
        page.get_by_role('button',name='New exchange',exact=False).first.click()
        expect(page.locator('.welcome-message-panel')).to_be_visible()
        expect(page.locator('#invitation-message')).to_be_visible()
        assert page.locator('#invitation-message').evaluate('(e)=>e.getBoundingClientRect().height')>=150
        page.locator('#modal-cancel').click()
        page.get_by_role('button',name='Delete exchange',exact=True).click()
        expect(page.locator('#modal-root')).to_contain_text('group and other exchanges remain')
        page.locator('#dialog-form [name=confirm]').fill('Incorrect name')
        page.locator('#modal-submit').click()
        expect(page.locator('#dialog-error')).to_contain_text('exact exchange name')
        page.locator('#modal-cancel').click()
        # Another organiser deleting the group removes stale content on refresh.
        page.evaluate('qa.removed=true;refreshAccess()')
        expect(page.locator('.compact-wishlist')).to_have_count(0)
        expect(page.locator('.exchange-list [data-exchange]')).to_have_count(0)
        page.goto('http://giftcircle.test/#settings')
        expect(page.locator('#profile-form')).to_be_visible()
        page.locator('#profile-form [data-action=logout]').click()
        expect(page.locator('#login-form')).to_be_visible()
        assert page.evaluate('qa.profileWrites')==0
        page.goto('http://giftcircle.test/#reveal=exampleprivatetoken123456789')
        expect(page.locator('#reveal-recipient')).to_be_visible()
        assert page.evaluate('qa.revealCalls||0')==0
        assert 'Jamie' not in page.locator('#app').inner_text()
        page.locator('#reveal-recipient').click()
        expect(page.locator('.revealed-name h2')).to_have_text('Jamie')
        assert page.evaluate('qa.revealCalls')==1
        overflow(page)
        page.screenshot(path=str(OUT/f'reveal-{width}.png'),full_page=True)
        assert errors==[],errors
        print(f'{width}px: PASS compact lists, reserve/buy, add/finalise, messaging, safe draft refresh, deep links, deletion refresh, sign out, prominent welcome, deletion confirmation, private reveal and overflow')
        page.close()
    browser.close()

