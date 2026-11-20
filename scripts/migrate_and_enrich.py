import json,re,urllib.parse,datetime,hashlib,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'data'
def get(n): return json.loads((D/n).read_text(encoding='utf8'))
def put(n,v): (D/n).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
s=get('statements.json')
# Quarantine Google-News-only links; we cannot safely invent the publisher's direct URL.
leads_path=D/'statement_candidates.json'
try: old_leads=json.loads(leads_path.read_text(encoding='utf8'))
except (FileNotFoundError,ValueError): old_leads={}
existing_leads=list(old_leads.get('candidates',[]))
held=[]
for row in s:
 if 'news.google.com' in (urllib.parse.urlsplit(row.get('url','')).hostname or ''):
  existing_leads.append({'region':row.get('region','EU'),'title':row.get('title',''),
    'discovery_url':row.get('url'),'publisher':row.get('source',''),
    'date_reported':row.get('date'), 'kind':'auto','reviewed':False,
    'direct_url':None,'status':'Needs direct original publisher URL and source verification'})
 else: held.append(row)
if len(held)!=len(s):
 old_leads['candidates']=list({(x.get('region'),x.get('title','').lower()):x for x in existing_leads}.values())
 old_leads.setdefault('checked_at',datetime.datetime.now(datetime.timezone.utc).isoformat())
 put('statement_candidates.json',old_leads)
s=held
# Individually cross-checked institutional records; others remain official-origin
# but not marked editorially reviewed until confirmed by the site operator.
SOURCE_VERIFIED={
 'https://www.mfa.bg/en/news/49680',
 'https://www.mfa.bg/en/news/49545',
 'https://mfa.bg/en/news/49607',
 'https://www.mai.gov.ro/en/press-release-83/',
 'https://www.consilium.europa.eu/en/press/press-releases/2026/11/16/co-chairs-conclusions-on-cross-regional-security-and-connectivity/',
}
# Preserve all existing published rows; a provisional provenance label is not proof of verification.
for row in s:
 host=urllib.parse.urlsplit(row.get('url','')).hostname or ''
 official=any(host==d or host.endswith('.'+d) for d in ['consilium.europa.eu','ec.europa.eu','eeas.europa.eu','mfa.bg','gov.ro','mai.gov.ro','mae.ro','presidency.ro','government.bg'])
 row['kind']='auto' if 'News headline from the linked source' in row.get('summary','') else ('official' if official else 'news')
 row['reviewed']=bool(row.get('reviewed',False) or (official and row['kind']=='official' and row.get('url') in SOURCE_VERIFIED))
 row['source_type']='institution' if official else 'press'
 row['id']=row.get('id') or 'statement-'+hashlib.sha256((row['date']+'|'+row['title']).encode()).hexdigest()[:12]
# Eliminate exact duplicate URLs and same dated name, keeping the richer entry.
seen=set();unique=[]
for r in s:
 key=(r['date'],re.sub(r'\W+','',r['title'].lower()))
 urlkey=urllib.parse.urlsplit(r['url']).path.rstrip('/')
 # Collapse the duplicate 19-Nov Nicușor Dan statement even when a paraphrase title differs.
 dan_key=('dan-president-2026-11-19' if r['date']=='2026-11-19' and r['region']=='Romania' and ('dan' in r.get('source','').lower() or 'dan' in r['title'].lower()) else None)
 if key in seen or urlkey in seen or (dan_key and dan_key in seen):continue
 if dan_key:seen.add(dan_key)
 seen.add(key);seen.add(urlkey);unique.append(r)
# Explicit president duplicate if titles differ: first-party provenance preferred; let editorial audit review.
put('statements.json',unique)
i=get('incidents.json')
for r in i:
 r['category']=r.get('category') or 'vessel_strike'
 r['event_kind']='incident'
 old=r.get('attribution','unknown')
 r['attribution_status']='claimed' if old in ('reported','confirmed') and 'attributed' in (r.get('summary') or '').lower() else 'undetermined'
 r['attribution_details']=r.get('attribution_details') or ("Ukraine attributed this strike to Russia; cited sources should be consulted for the exact claim." if r['id']=='aya-2024' else "No independently verified actor attribution is recorded in the dataset.")
 r['location_precision']=r.get('locationPrecision','')
 r['reviewed']=not r.get('auto_discovered',False)
 r['position_status']='approximate' if r.get('lat') and r.get('lon') else 'unlocated'
# Distinguish gas husky: source wording does not itself establish verified actor attribution.
for r in i:
 if r['id']=='gas-husky-2026':
  r['attribution_status']='claimed';r['attribution_details']='A cited BGNES article reports a claim concerning responsibility. This is a reported claim, not an independently confirmed determination.'
 if r['id']=='aya-2024':
  r['attribution_status']='claimed'
# Precise verified dates and places sourced in Romanian Navy / Romanian MoD news.
history=[
 {'id':'mine-varna-2022-06-30','date':'2022-06-30','country':'Bulgaria','vessel':'Drifting sea mine — Varna offshore','category':'mine','event_kind':'incident','type':'Drifting naval mine','method':'Bulgarian Navy mine neutralisation','summary':'Bulgarian Navy specialists destroyed a floating sea mine sighted on 30 June 2022 some 27 nautical miles east of the Kamchia river mouth, in the vicinity of Varna.','location':'Off Varna / Kamchia river offshore area','lat':43.03,'lon':28.51,'position_status':'approximate','locationPrecision':'Approximate regional map marker only, not reported exact mine position','attribution_status':'undetermined','attribution_details':'No responsible actor for this particular mine was established in the cited report.','sources':[{'label':'Bulgarian News Agency, 1 Jul 2022','url':'https://www.bta.bg/en/news/bulgaria/290913-bisspetsialisti-ot-vms-sa-unishtozhili-plavashta-mina'}],'reviewed':True},
 {'id':'mine-kochan-2023-01-24','date':'2023-01-24','country':'Bulgaria','vessel':'Drifting sea mine — Cape Kochan','category':'mine','event_kind':'incident','type':'Drifting naval mine','method':'Mine neutralisation','summary':'Bulgarian military specialists neutralised a floating moored-type mine after a sighting near Cape Kochan. A separate mine was reported at Tyulenovo during the same period.','location':'Cape Kochan coastal area, Bulgaria','lat':43.53,'lon':28.58,'position_status':'approximate','locationPrecision':'Approximate coast-area marker from media reporting; location must not be used for navigation','attribution_status':'undetermined','attribution_details':'The source describes the mine type and response but does not confirm who laid this particular mine.','sources':[{'label':'Bulgarian National Radio, 24 Jan 2023','url':'https://old-news.bnr.bg/horizont/post/101769244/voenni-ot-vms-otnovo-unishtojiha-mina-plavashti-krai-balgarskia-brag'}],'reviewed':True},
 {'id':'mine-pasha-dere-2024-05-14','date':'2024-05-14','country':'Bulgaria','vessel':'Naval mine — Pasha Dere','category':'mine','event_kind':'incident','type':'Moored naval mine','method':'Mine neutralisation','summary':'Bulgarian sailors found a mine-like object two nautical miles east of Pasha Dere; a minehunter crew classified it as a KPM-type mine and destroyed it in a controlled explosion.','location':'Off Pasha Dere, Bulgaria','lat':43.11,'lon':28.13,'position_status':'approximate','locationPrecision':'Approximate coastal position from the stated area, not exact coordinates','attribution_status':'undetermined','attribution_details':'The responsible actor for this mine was not determined in the cited account.','sources':[{'label':'Bulgarian National Television, 14 May 2024','url':'https://bnt.bg/news/bulgarian-navy-defused-naval-mine-off-the-bulgarian-black-sea-coast-328940news.html'}],'reviewed':True},
 {'id':'mine-capu-midia-2022-03-28','date':'2022-03-28','country':'Romania','vessel':'Drifting sea mine — Capu Midia','category':'mine','event_kind':'incident','type':'Drifting naval mine','method':'Mine neutralisation','summary':'Romanian Naval Forces located and neutralised a drifting mine approximately 39 nautical miles off Capu Midia.','location':'Off Capu Midia, offshore area','lat':44.47,'lon':29.87,'position_status':'approximate','locationPrecision':'Approximate offshore zone based on reported distance; not an exact mine coordinate','attribution_status':'undetermined','attribution_details':'The origin of this specific mine was not established in the cited release.','sources':[{'label':'Romanian Naval Forces (28 Mar 2022)','url':'https://www.navy.ro/comunicat.php?id=567'}],'reviewed':True},
 {'id':'mine-eforie-2022-07-31','date':'2022-07-31','country':'Romania','vessel':'Drifting sea mine — Eforie','category':'mine','event_kind':'incident','type':'Drifting naval mine','method':'Mine neutralisation','summary':'EOD divers neutralised a mine drifting roughly two nautical miles off the Eforie coast.','location':'Off Eforie','lat':44.05,'lon':28.72,'position_status':'approximate','locationPrecision':'Approximate area, source gives distance but no impact coordinates','attribution_status':'undetermined','attribution_details':'Mine provenance not established in the cited account.','sources':[{'label':'Romanian Naval Forces','url':'https://www.navy.ro/comunicat.php?id=622'}],'reviewed':True},
 {'id':'mine-constanta-2022-12-10','date':'2022-12-10','country':'Romania','vessel':'Drifting sea mine — Constanța','category':'mine','event_kind':'incident','type':'Drifting naval mine','method':'Mine sighting / response','summary':'A Turkish-flagged cargo vessel reported a drifting sea mine around 2.5 nautical miles from Constanța port’s northern breakwater.','location':'Off Constanța port','lat':44.18,'lon':28.76,'position_status':'approximate','locationPrecision':'Approximate offshore location from relative distance reported by the navy','attribution_status':'undetermined','attribution_details':'Origin of the mine was not established in the cited release.','sources':[{'label':'Romanian Naval Forces','url':'https://www.navy.ro/comunicat.php?id=670'}],'reviewed':True},
 {'id':'mine-sf-gheorghe-2023-01-26','date':'2023-01-26','country':'Romania','vessel':'Sea mine — Sfântu Gheorghe','category':'mine','event_kind':'incident','type':'Mine washed ashore','method':'Mine neutralisation','summary':'Romanian military personnel conducted a dangerous intervention to neutralise a sea mine washed ashore at Sfântu Gheorghe.','location':'Sfântu Gheorghe beach','lat':44.89,'lon':29.62,'position_status':'approximate','locationPrecision':'Approximate beach area, not the EOD detonation point','attribution_status':'undetermined','attribution_details':'Mine origin is not confirmed by the cited statement.','sources':[{'label':'Romanian Naval Forces','url':'https://www.navy.ro/comunicat.php?id=679'}],'reviewed':True},
 {'id':'drone-plauru-2023-09-05','date':'2023-09-05','country':'Romania','vessel':'Drone fragments — Plauru','category':'drone_debris','event_kind':'incident','type':'Aerial drone debris','method':'Debris discovery','summary':'Romanian investigators discovered elements potentially associated with drone fragments near Plauru on the evening of 5 September; later government statements discussed this incident.','location':'Plauru vicinity, Tulcea County','lat':45.31,'lon':28.92,'position_status':'approximate','locationPrecision':'Approximate locality marker on the Danube, NOT a maritime strike coordinate','attribution_status':'undetermined','attribution_details':'The Romanian Ministry of Defence initially described potentially drone-associated fragments; this record does not independently determine the origin of the object.','sources':[{'label':'Romanian Ministry of Defence, 6 Sep 2023','url':'https://english.mapn.ro/cpresa/6041_press-information'}],'reviewed':True},
 {'id':'mcm-black-sea-2024-07-01','date':'2024-07-01','country':'Bulgaria','vessel':'MCM Black Sea task group operational','category':'mine_action','event_kind':'response','type':'Multinational mine countermeasures','method':'Task group activation','summary':'Bulgaria, Romania and Türkiye launched operations of their multinational mine-countermeasures task group on 1 July 2024. This is a security response milestone, not an attack.','location':'Western Black Sea — multinational operating area','lat':42.65,'lon':27.92,'position_status':'schematic','locationPrecision':'Symbolic Bulgarian coastal marker for a multinational operation; not the site of an incident','attribution_status':'undetermined','attribution_details':'No attacker attribution applies: this is a maritime-security operation.','sources':[{'label':'Romanian Ministry of Defence','url':'https://english.mapn.ro/cpresa/6290_The-Bulgarian%2C-Romanian-and-Turkish-Naval-Forces-work-together-to-counter-the-mine-threat-in-the-Black-Sea-'}],'reviewed':True},
 {'id':'mcm-romania-command-2025-07-09','date':'2025-07-09','country':'Romania','vessel':'MCM Black Sea — Romania assumes command','category':'mine_action','event_kind':'response','type':'Multinational mine countermeasures','method':'Rotational command','summary':'Romania took command of the MCM Black Sea Task Group on 9 July 2025, following Bulgaria’s term. This is an operational milestone, not an attack.','location':'Port of Constanța','lat':44.17,'lon':28.64,'position_status':'approximate','locationPrecision':'Port-level approximate location for the command ceremony','attribution_status':'undetermined','attribution_details':'No attacker attribution applies: this is a security response milestone.','sources':[{'label':'Romanian Ministry of Defence','url':'https://english.mapn.ro/cpresa/6542_Romania-has-taken-over-command-of-the-MCM-Black-Sea-Task-Group'}],'reviewed':True},
]
existing={r['id'] for r in i};i.extend(r for r in history if r['id'] not in existing)
i.sort(key=lambda x:x['date'],reverse=True)
put('incidents.json',i)
# All translated rows remain untouched to preserve prior cache; new IDs translate later.
with (D/'incidents.csv').open('w',newline='',encoding='utf-8-sig') as f:
 writer=csv.writer(f);writer.writerow(['id','date','country','category','event_kind','title','attribution_status','attribution_details','location','lat','lon','source_urls'])
 for r in i:writer.writerow([r.get('id'),r.get('date'),r.get('country'),r.get('category'),r.get('event_kind'),r.get('vessel'),r.get('attribution_status'),r.get('attribution_details'),r.get('location'),r.get('lat'),r.get('lon'),' | '.join(x.get('url','') for x in r.get('sources',[]))])
print('migrated',len(unique),'statements',len(i),'incidents')
