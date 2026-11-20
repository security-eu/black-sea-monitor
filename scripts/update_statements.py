"""Discover candidate official statements; never publish unverified text."""
import json, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
BASE = Path(__file__).resolve().parents[1]
QUERIES = {
  "Bulgaria": '(site:mfa.bg OR site:government.bg OR site:bta.bg) ("Black Sea" OR "Черно море") (security OR maritime OR сигурност)',
  "Romania": '(site:mae.ro OR site:presidency.ro OR site:gov.ro OR site:mai.gov.ro OR site:agerpres.ro) ("Marea Neagra" OR "Black Sea") (securitate OR security OR nave OR maritime)',
  "EU": '(site:consilium.europa.eu OR site:ec.europa.eu OR site:eeas.europa.eu) "Black Sea" (maritime OR security OR shipping)',
}
existing = json.loads((BASE/'data/statements.json').read_text())
known = {x['url'].split('?')[0].rstrip('/') for x in existing}
queue=[]
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
            queue.append({'region':region,'title':title,'discovery_url':link,'published_raw':item.findtext('pubDate'),'status':'Needs source and date verification'})
    except Exception as exc:
        print(f'{region}: RSS retrieval unavailable: {exc}')
# Google News links are discovery leads, not evidence of official publication.
# Avoid duplicate candidate headlines; review each original official statement manually.
unique={ (x['region'],x['title'].lower()):x for x in queue }
path=BASE/'data/statement_candidates.json'
path.write_text(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),'candidates':list(unique.values())[:80]},ensure_ascii=False,indent=2)+'\n')
print('Candidate statements:',len(unique))
