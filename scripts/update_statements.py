"""Index recent Black Sea news headlines directly; never call them verified quotations."""
import json, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
BASE = Path(__file__).resolve().parents[1]
QUERIES = {
  "Bulgaria": '(site:mfa.bg OR site:government.bg OR site:bta.bg) ("Black Sea" OR "Черно море") (security OR maritime OR сигурност)',
  "Romania": '(site:mae.ro OR site:presidency.ro OR site:gov.ro OR site:mai.gov.ro OR site:agerpres.ro) ("Marea Neagra" OR "Black Sea") (securitate OR security OR nave OR maritime)',
  "EU": '(site:consilium.europa.eu OR site:ec.europa.eu OR site:eeas.europa.eu) "Black Sea" (maritime OR security OR shipping)',
}
existing = json.loads((BASE/'data/statements.json').read_text())
known = {x['url'].split('?')[0].rstrip('/') for x in existing}
seen_titles={(x.get('region',''),x.get('title','').lower()) for x in existing}
added=0
now=datetime.now(timezone.utc)
for region, query in QUERIES.items():
    url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':query,'hl':'en','gl':'US','ceid':'US:en'})
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'BlackSeaMonitor/1.0 (research archive)'})
        with urllib.request.urlopen(req,timeout=20) as res: data=res.read()
        root=ET.fromstring(data)
        for item in root.findall('./channel/item'):
            title=(item.findtext('title') or '').strip()
            link=(item.findtext('link') or '').strip()
            if not link or link.split('?')[0].rstrip('/') in known: continue
            if not re.search(r'black sea|marea neagr|черно море|maritime|shipping|морск',title,re.I): continue
            try:
                published=parsedate_to_datetime(item.findtext('pubDate')).astimezone(timezone.utc)
            except (TypeError, ValueError, IndexError):
                continue
            if published>now or (now-published).days>14: continue
            source_node=item.find('source')
            publisher=(source_node.text or '').strip() if source_node is not None else ''
            if not publisher: continue
            # Automatically published entries are explicitly labeled as indexed news
            # headlines, NOT verified quotations or independently established facts.
            normalized=(region,title.lower())
            if normalized in seen_titles: continue
            seen_titles.add(normalized)
            existing.append({'date':published.date().isoformat(),'region':region,
              'source':publisher,
              'title':title[:220],
              'summary':'News headline from the linked source. Open the original report for details and context.',
              'url':link})
            known.add(link.split('?')[0].rstrip('/'))
            added+=1
    except Exception as exc:
        print(f'{region}: RSS retrieval unavailable: {exc}')
# Google News links are news-discovery leads, not proof of an official statement.
existing.sort(key=lambda x:x.get('date',''),reverse=True)
if added:
    (BASE/'data/statements.json').write_text(json.dumps(existing,ensure_ascii=False,indent=2)+'\n')
print('New automatically indexed headlines:',added)
