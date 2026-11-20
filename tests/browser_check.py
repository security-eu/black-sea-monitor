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
 browser=p.chromium.launch()
 for width,height in [(1440,900),(390,844)]:
  page=browser.new_page(viewport={'width':width,'height':height})
  page.goto(url,wait_until='domcontentloaded');page.wait_for_timeout(1500)
  page.wait_for_selector('#incidentList .row')
  assert page.locator('.leaflet-interactive').count()>0
  page.locator('[data-lang="ro"]').click();page.wait_for_timeout(800)
  assert page.locator('html').get_attribute('lang')=='ro'
  if width<700:
   page.locator('[data-mtab="statements"]').click();page.locator('[data-lang="bg"]').click();page.wait_for_timeout(400)
   assert page.locator('#app').get_attribute('data-view')=='list' and page.locator('#app').get_attribute('data-pane')=='statements'
  page.screenshot(path=str(root/f'tests/layout-{width}.png'),full_page=False)
  page.close()
 browser.close()
server.shutdown()
print('Browser layout / language-state smoke tests passed')
