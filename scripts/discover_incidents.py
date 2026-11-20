"""Conservative automatic maritime-incident discovery from public RSS headlines.

A provisional map record requires two distinct publishing outlets independently
naming the same vessel and associating an attack with Romania or Bulgaria.
Coordinates are intentionally generic offshore *display anchors*, never alleged
impact coordinates. No actor responsibility is inferred by this pipeline.
"""
import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
NOW = datetime.now(timezone.utc)
QUERIES = {
 'Romania': [
  'Romania Black Sea merchant ship tanker cargo vessel hit attacked missile drone coast Constanta',
  'Romanian waters Black Sea vessel struck attacked explosion ship',
  'Marea Neagra nava petrolier atacata lovita drona Constanta'],
 'Bulgaria': [
  'Bulgaria Black Sea cargo ship tanker vessel attacked struck drone missile Varna Burgas',
  'Bulgarian coast ship vessel hit explosion attack Black Sea',
  'Черно море България кораб танкер ударен атакуван Варна Бургас']
}
COUNTRY_WORDS = {
 'Romania': r'romania|romanian|români|români[aei]|românia|constan[tț]a|sulina|mangalia',
 'Bulgaria': r'bulgaria|bulgarian|българ|варна|бургас|varna|burgas|българск'
}
ATTACK = re.compile(r'attack(?:ed)?|struck|strike|hit by|missile|drone|explosion|bombard|torpedo|удар|атак|пораз|взрив|атакат|ловит[ао]|експлоз|ракет|дрон',re.I)
VESSEL = re.compile(r'\b(ship|vessel|tanker|freighter|bulk carrier|cargo ship|merchant ship|nav[ăa]|nava|petrolier|кораб|танкер|судно)\b',re.I)
PAST = re.compile(r'last year|anniversary|years ago|historical|exercise|drill|training',re.I)
# Deliberately require a named vessel in a *ship-related* title. Unnamed
# ships and reports about port attacks are queued, not plotted.
NAME_PATTERNS = [
 re.compile(r"(?:ship|vessel|tanker|freighter|nav[ăa]|nava|petrolier|кораб|танкер|судно)\s+[\"“„«']([A-Za-z0-9][A-Za-z0-9 .-]{1,35})[\"”»']",re.I),
 re.compile(r"[\"“„«']([A-Z][A-Za-z0-9 .-]{2,35})[\"”»']\s+(?:ship|vessel|tanker|кораб)",re.I),
 re.compile(r'\b(?:ship|vessel|tanker|freighter|nav[ăa]|nava|petrolier|кораб|танкер)\s+([A-Z][A-Z0-9-]{2,24})\b')]

STOP = {'BLACK','SEA','ROMANIA','BULGARIA','UKRAINE','RUSSIA','NATO','COAST','DRONE','MISSILE','PORT','WAR','NEWS','NAVY'}
ANCHORS = {'Romania': (43.83, 29.60, 'Illustrative Romanian Black Sea offshore anchor; actual incident location is not established'),
           'Bulgaria': (42.65, 28.55, 'Illustrative Bulgarian Black Sea offshore anchor; actual incident location is not established')}

def extract_name(title):
 for pat in NAME_PATTERNS:
  match=pat.search(title)
  if match:
   name=re.sub(r'\s+',' ',match.group(1)).strip().upper()
   if name not in STOP and len(name)>=3:
    return name
 return None

def fetch_feed(query):
 url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':query,'hl':'en','gl':'US','ceid':'US:en','when':'14d'})
 req=urllib.request.Request(url,headers={'User-Agent':'EUBlackSeaMonitor/2.0 (public maritime research)'})
 with urllib.request.urlopen(req,timeout=22) as response:
  body=response.read(2_000_000)
 root=ET.fromstring(body)
 output=[]
 for item in root.findall('./channel/item'):
  title=(item.findtext('title') or '').strip()
  link=(item.findtext('link') or '').strip()
  publisher=(item.findtext('source') or '').strip()
  try: pub=parsedate_to_datetime(item.findtext('pubDate')).astimezone(timezone.utc)
  except (ValueError,TypeError,IndexError):continue
  if not title or not link or not publisher or not pub or pub>NOW or NOW-pub>timedelta(days=14):continue
  output.append({'title':title,'url':link,'source':publisher,'date':pub.date().isoformat()})
 return output

def run():
 path=DATA/'incidents.json'
 rows=json.loads(path.read_text(encoding='utf-8'))
 existing=[(r.get('country'),(r.get('vessel') or '').upper(),r.get('date') or '') for r in rows]
 mentions=defaultdict(dict)
 candidates=[]
 errors=[]
 for country,searches in QUERIES.items():
  for query in searches:
   try: records=fetch_feed(query)
   except Exception as ex:
    errors.append({'region':country,'error':type(ex).__name__});continue
   for rec in records:
    title=rec['title']
    if not ATTACK.search(title) or not VESSEL.search(title) or PAST.search(title):continue
    # Country must be indicated in the *headline*, not just search query.
    if not re.search(COUNTRY_WORDS[country],title,re.I):continue
    name=extract_name(title)
    if not name:
     candidates.append({**rec,'country':country,'status':'Insufficient named-vessel evidence; not mapped'})
     continue
    key=(country,name)
    # One publisher is not multiple independent sources; RSS duplicates are ignored.
    publisher=rec['source'].lower()
    mentions[key].setdefault(publisher,rec)
 for (country,vessel),sources in sorted(mentions.items()):
  evidence=sorted(sources.values(),key=lambda x:x['date'],reverse=True)
  # Suppress reports of the same event but allow a later independent attack
  # on the same vessel to be recorded separately.
  if any(c==country and v==vessel and d and abs((datetime.fromisoformat(d)-datetime.fromisoformat(evidence[0]['date'])).days)<=7 for c,v,d in existing):continue
  if len(evidence)<2:
   candidates.append({'country':country,'vessel':vessel,'status':'Awaiting a second independent source','sources':evidence})
   continue
  # Multiple reports published over >3 days can describe unrelated events.
  top=evidence[0]
  corroborating=[s for s in evidence if abs((datetime.fromisoformat(top['date'])-datetime.fromisoformat(s['date'])).days)<=3]
  if len(corroborating)<2:
   candidates.append({'country':country,'vessel':vessel,'status':'Reports not sufficiently close in time','sources':evidence})
   continue
  lat,lon,precision=ANCHORS[country]
  event_id='auto-'+hashlib.sha256((country+'|'+vessel+'|'+top['date']).encode()).hexdigest()[:16]
  rows.append({'id':event_id,'vessel':vessel,'date':top['date'],'country':country,
   'attribution':'reported','flag':'Not verified','type':'Merchant vessel (type unverified)',
   'method':'Reported attack; method not independently verified',
   'summary':f'At least two separate outlets reported an apparent attack involving {vessel} in the {country} Black Sea area. Date is the latest report publication date, not a verified strike date. These headlines have not been independently verified.',
   'location':f'{country} Black Sea area (illustrative, not verified)',
   'locationPrecision':precision,'lat':lat,'lon':lon,
   'auto_discovered':True,'location_is_illustrative':True,'reported_not_verified':True,
   'sources':[{'label':s['source'],'url':s['url']} for s in corroborating[:4]]})
  existing.append((country,vessel,top['date']))
  print('Provisional mapped incident:',country,vessel,'corroborating outlets',len(corroborating))
 rows.sort(key=lambda x:x.get('date',''),reverse=True)
 path.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (DATA/'incident_candidates.json').write_text(json.dumps({'checked_at':NOW.isoformat(),'candidates':candidates[:150],'feed_errors':errors},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Incident records:',len(rows),'unmapped candidates:',len(candidates),'feed errors:',len(errors))

if __name__=='__main__':run()
