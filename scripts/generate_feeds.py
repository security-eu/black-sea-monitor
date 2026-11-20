"""Generate public RSS, CSV and metadata from published data only."""
import json,csv,datetime,html,urllib.parse
from pathlib import Path
from email.utils import format_datetime
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data'
statements=json.loads((DATA/'statements.json').read_text(encoding='utf8'))
incidents=json.loads((DATA/'incidents.json').read_text(encoding='utf8'))
BASE='https://security-eu.github.io/'
def esc(v):return html.escape(str(v),quote=True)
def item(s,kind):
 if kind=='incident':
  url=BASE+'#'+urllib.parse.quote(s['id']);title=s.get('vessel',s['id']);description=s.get('summary','')
 else:
  url=s['url'];title=s['title'];description=s.get('summary','')
 dt=datetime.date.fromisoformat(s['date']);ts=format_datetime(datetime.datetime.combine(dt,datetime.time(12),datetime.timezone.utc))
 return f'<item><title>{esc(title)}</title><link>{esc(url)}</link><guid isPermaLink="false">{esc(kind+"-"+s["id"])}</guid><pubDate>{ts}</pubDate><description>{esc(description)}</description></item>'
visible=[i for i in incidents if i.get('country') in ('Romania','Bulgaria') and i.get('event_kind')=='incident']
items=sorted([(x['date'],'incident',x) for x in visible]+[(x['date'],'statement',x) for x in statements if x.get('kind')=='official' and x.get('reviewed')],key=lambda v:v[0],reverse=True)
rss='<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>EU Black Sea — Maritime Security Monitor</title><link>'+BASE+'</link><description>Reviewed maritime incidents and sourced public records relevant to Romania and Bulgaria</description><language>en</language>'+''.join(item(x,k) for _,k,x in items[:100])+'</channel></rss>\n'
(ROOT/'rss.xml').write_text(rss,encoding='utf8')
with (DATA/'incidents.csv').open('w',encoding='utf-8-sig',newline='') as f:
 writer=csv.writer(f);writer.writerow(['id','date','country','category','event_kind','title','attribution_status','attribution_details','location','lat','lon','sources'])
 for r in incidents:
  writer.writerow([r.get('id'),r.get('date'),r.get('country'),r.get('category'),r.get('event_kind'),r.get('vessel'),r.get('attribution_status'),r.get('attribution_details'),r.get('location'),r.get('lat'),r.get('lon'),' | '.join(s.get('url','') for s in r.get('sources',[]))])
# Only update timestamp when data outputs actually changed (avoid empty PRs every six hours).
meta=DATA/'updated.json'
try:prior=json.loads(meta.read_text(encoding='utf8'))
except(FileNotFoundError,ValueError):prior={}
import hashlib
hashes=hashlib.sha256(json.dumps({'incidents':incidents,'statements':statements},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
if hashes!=prior.get('dataset_hash'):
 meta.write_text(json.dumps({'updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'dataset_hash':hashes},indent=2)+'\n',encoding='utf8')
print('RSS items:',len(items[:100]),'CSV rows:',len(incidents))
