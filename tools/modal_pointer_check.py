import ast
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
parsed=ast.parse((ROOT/'tools/ui_release_check.py').read_text(encoding='utf-8'))
MOCK=next(ast.literal_eval(n.value) for n in parsed.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MOCK' for t in n.targets))
html='<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+ (ROOT/'app/static/style.css').read_text(encoding='utf-8')+'</style></head><body><div id="app"></div><script>'+MOCK+'</script><script>'+(ROOT/'app/static/app.js').read_text(encoding='utf-8')+'</script></body></html>'
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True)
 for mobile in [False,True]:
  context=b.new_context(viewport={'width':390 if mobile else 1440,'height':950},has_touch=mobile,is_mobile=mobile)
  page=context.new_page();page.route('**/*',lambda route:route.fulfill(content_type='text/html; charset=utf-8',body=html))
  page.goto('http://giftcircle.test/#exchanges/1')
  def open_dialog():
   page.get_by_role('button',name='New exchange',exact=False).first.click()
   expect(page.locator('#invitation-message')).to_be_visible()
  open_dialog()
  text=page.locator('#invitation-message');text.fill('Please preserve this welcome message while I select text.')
  box=text.bounding_box();x,y=box['x']+50,box['y']+25
  page.mouse.move(x,y);page.mouse.down();page.mouse.move(5,y,steps=12);page.mouse.up()
  expect(page.locator('#modal-root')).to_be_visible()
  expect(text).to_have_value('Please preserve this welcome message while I select text.')
  page.mouse.click(x,y)
  expect(page.locator('#modal-root')).to_be_visible()
  page.mouse.move(5,y);page.mouse.down();page.mouse.move(x,y,steps=12);page.mouse.up()
  expect(page.locator('#modal-root')).to_be_visible()
  if mobile:page.touchscreen.tap(5,5)
  else:page.mouse.click(5,5)
  expect(page.locator('#modal-root')).to_have_count(0)
  open_dialog();page.locator('#modal-cancel').click();expect(page.locator('#modal-root')).to_have_count(0)
  open_dialog();page.locator('#modal-close').click();expect(page.locator('#modal-root')).to_have_count(0)
  print(('Touch/mobile' if mobile else 'Desktop')+': PASS inside-to-outside drag preserved, outside-to-inside drag preserved, inside click preserved, outside click/tap closes, Cancel and X close')
  context.close()
 b.close()
