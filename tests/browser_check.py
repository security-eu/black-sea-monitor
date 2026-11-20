"""Optional headed/headless browser check. Requires playwright and Chromium."""
import sys,threading,functools,http.server,os
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
os.chdir(root)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(root)))
threading.Thread(target=server.serve_forever,daemon=True).start()
url=f'http://127.0.0.1:{server.server_port}/'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--allow-file-access-from-files','--disable-web-security'])
 for width,height in [(1440,900),(390,844)]:
  page=browser.new_page(viewport={'width':width,'height':height})
  page.goto((root/'index.html').as_uri(),wait_until='domcontentloaded');page.wait_for_timeout(1500)
  assert page.locator('#newsTitle').count()==1
  page.locator('[data-switch="ro"]').click();page.wait_for_timeout(800)
  assert page.locator('html').get_attribute('lang')=='ro'
  if width<700:
   page.locator('[data-tab="statements"]').click();page.locator('[data-switch="bg"]').click();page.wait_for_timeout(400)
   assert 'mobile-statements' in (page.locator('#layout').get_attribute('class') or '')
  page.screenshot(path=str(root/f'tests/layout-{width}.png'),full_page=False)
  page.close()
 browser.close()
server.shutdown()
print('Browser layout / language-state smoke tests passed')
