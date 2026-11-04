import ast
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
parsed=ast.parse((ROOT/'tools/ui_release_check.py').read_text(encoding='utf-8'))
MOCK=next(ast.literal_eval(n.value) for n in parsed.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MOCK' for t in n.targets))
html='<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+ (ROOT/'app/static/style.css').read_text(encoding='utf-8')+'</style></head><body><div id="app"></div><script>'+MOCK+'</script><script>'+(ROOT/'app/static/app.js').read_text(encoding='utf-8')+'</script></body></html>'
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True)
 for width in [1440,390]:
  page=b.new_page(viewport={'width':width,'height':950})
  page.route('**/*',lambda route:route.fulfill(content_type='text/html; charset=utf-8',body=html))
  page.goto('http://giftcircle.test/#exchanges/1')
  page.get_by_role('button',name='New exchange',exact=False).first.click()
  box=page.locator('#invitation-message');expect(box).to_be_visible()
  size=box.evaluate('e=>{const p=e.parentElement,c=getComputedStyle(p);return {width:e.getBoundingClientRect().width,available:p.clientWidth-parseFloat(c.paddingLeft)-parseFloat(c.paddingRight),resize:getComputedStyle(e).resize}}')
  assert abs(size['width']-size['available'])<2,size
  assert size['resize']=='vertical'
  box.fill('Welcome everyone!\nBring a thoughtful gift and join the fun.\n'+'A longer line to check comfortable wrapping. '*5)
  assert page.locator('.modal').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
  page.locator('.welcome-message-panel').screenshot(path=str(ROOT/f'tools/release-check/welcome-{width}.png'))
  print(f'{width}px: full-width textarea, wrapping, vertical resizing and no overflow passed')
  page.close()
 b.close()
