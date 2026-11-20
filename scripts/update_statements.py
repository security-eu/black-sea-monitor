"""Discover leads, never publish Google News RSS URLs as source evidence.

This runs ONLY in a PR workflow. A candidate needs an editor to review its original
source URL, actor, event/date and to set kind=official/news and reviewed=true.
"""
import json, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data'
QUERIES={
 'Bulgaria':'(site:mfa.bg OR site:government.bg OR site:bta.bg) ("Black Sea" OR "Черно море") (security OR maritime OR сигурност)',
 'Romania':'(site:mae.ro OR site:presidency.ro OR site:gov.ro OR site:mai.gov.ro OR site:agerpres.ro) ("Marea Neagra" OR "Black Sea") (securitate OR security OR nave OR maritime)',
 'EU':'(site:consilium.europa.eu OR site:ec.europa.eu OR site:eeas.europa.eu) "Black Sea" (maritime OR security OR shipping)'
}
def load(name,default):
 try:return json.loads((DATA/name).read_text(encoding='utf8'))
 except(FileNotFoundError,ValueError):return default

def run():
 published=load('statements.json',[]);old=load('statement_candidates.json',{}).get('candidates',[])
 seen={str(x.get('title','')).strip().casefold() for x in published}
 found={(x.get('region'),x.get('title','').casefold()):x for x in old}
 now=datetime.now(timezone.utc)
 for region,query in QUERIES.items():
  rss='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':query,'hl':'en','gl':'US','ceid':'US:en','when':'14d'})
  try:
   req=urllib.request.Request(rss,headers={'User-Agent':'EUBlackSeaResearch/3.0'})
   with urllib.request.urlopen(req,timeout=20) as res:root=ET.fromstring(res.read(2_000_000))
  except (OSError,ET.ParseError) as e:
   print(region,'feed unavailable:',type(e).__name__);continue
  for item in root.findall('./channel/item'):
   title=(item.findtext('title') or '').strip();link=(item.findtext('link') or '').strip()
   if not title or title.casefold() in seen or not link or not re.search(r'black sea|marea neagr|черно море|maritim|shipping|морск',title,re.I):continue
   try:date=parsedate_to_datetime(item.findtext('pubDate')).astimezone(timezone.utc)
   except(TypeError,ValueError,IndexError):continue
   if date>now or now-date>timedelta(days=14):continue
   source=item.find('source');publisher=(source.text or '').strip() if source is not None else ''
   if not publisher:continue
   # Google News is ONLY a discovery lead, not a direct publisher link.
   candidate={'region':region,'title':title,'discovery_url':link,'publisher':publisher,'date_reported':date.date().isoformat(),
    'kind':'auto','reviewed':False,'direct_url':None,'status':'Needs direct source URL, date and official-source verification'}
   found[(region,title.casefold())]=candidate
 output={'checked_at':now.isoformat(),'candidates':list(found.values())[-150:]}
 old_out=load('statement_candidates.json',{})
 if old_out.get('candidates')==output['candidates']:
  print('No new statement leads; preserving prior review state');return
 path=DATA/'statement_candidates.json'
 value=json.dumps(output,ensure_ascii=False,indent=2)+'\n'
 if not path.exists() or path.read_text(encoding='utf8')!=value:path.write_text(value,encoding='utf8')
 print('Unpublished leads:',len(output['candidates']))
if __name__=='__main__':run()
