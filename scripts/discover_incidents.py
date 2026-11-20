"""Conservative research-lead discovery. Never infer an event date or map point
from publication date, and never auto-publish unverified attacks or actor claims.
"""
import json,re,urllib.parse,urllib.request,xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data';NOW=datetime.now(timezone.utc)
queries={'Romania':['Romania Black Sea vessel attacked missile drone ship','Marea Neagra nava atacata drona Constanta'],
         'Bulgaria':['Bulgaria Black Sea vessel attacked drone missile Varna Burgas','Черно море България кораб атакуван дрон']}
search_terms=re.compile(r'attack|drone|missile|mine|struck|explos|атак|дрон|ракет|мина',re.I)

def run():
 candidates={};errors=[]
 for country,terms in queries.items():
  for q in terms:
   url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q,'hl':'en','gl':'US','ceid':'US:en','when':'14d'})
   try:
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'EUBlackSeaResearch/3.0'}),timeout=20) as r:root=ET.fromstring(r.read(2_000_000))
   except(OSError,ET.ParseError) as e:errors.append(f'{country}: {type(e).__name__}');continue
   for item in root.findall('./channel/item'):
    title=(item.findtext('title') or '').strip();link=(item.findtext('link') or '').strip()
    try:dt=parsedate_to_datetime(item.findtext('pubDate')).astimezone(timezone.utc)
    except (ValueError,TypeError,IndexError):continue
    if not title or not link or dt>NOW or NOW-dt>timedelta(days=14) or not search_terms.search(title):continue
    publisher=(item.findtext('source') or '').strip()
    key=(country,title.casefold())
    candidates[key]={'country':country,'headline':title,'discovery_url':link,'publisher':publisher,'publication_date':dt.date().isoformat(),
     'incident_date':None,'coordinates':None,'actor_attribution':None,'status':'Unverified lead; verify direct sources, event date and location manually'}
 path=DATA/'incident_candidates.json'
 new={'checked_at':NOW.isoformat(),'candidates':list(candidates.values())[:200],'fetch_errors':errors}
 try:prior=json.loads(path.read_text(encoding='utf8'))
 except(FileNotFoundError,ValueError):prior={}
 if prior.get('candidates')==new['candidates'] and prior.get('fetch_errors')==new['fetch_errors']:
  print('No new incident leads');return
 value=json.dumps(new,ensure_ascii=False,indent=2)+'\n'
 if not path.exists() or path.read_text(encoding='utf8')!=value:path.write_text(value,encoding='utf8')
 print('Unmapped incident leads:',len(candidates),'errors:',len(errors))
if __name__=='__main__':run()
