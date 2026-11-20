"""Incremental DeepL translation with a 500-char item cap and 90-day lifetime pacing."""
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
SOURCE = json.loads((DATA / 'statements.json').read_text(encoding='utf-8'))
KEY = os.getenv('DEEPL_API_KEY', '').strip()
ENDPOINT = os.getenv('DEEPL_API_URL', 'https://api-free.deepl.com/v2/translate').strip()
if ENDPOINT not in ('https://api-free.deepl.com/v2/translate', 'https://api.deepl.com/v2/translate'):
    raise SystemExit('Invalid DeepL API endpoint')

# Developer plan: one-time 1,000,000-character credit (not monthly).
# We deliberately spend at most 900,000 characters over the first 90 UTC days.
# This is a local conservative budget; check the actual DeepL usage dashboard.
TOTAL_BUDGET = 900_000
DAYS = 90
DAILY_ALLOWANCE = TOTAL_BUDGET // DAYS  # 10,000 chars/day
MAX_ITEM_CHARS = 500
USAGE_FILE = DATA / 'translation_usage.json'
today = datetime.now(timezone.utc).date()
try:
    stored = json.loads(USAGE_FILE.read_text(encoding='utf-8'))
except (FileNotFoundError, ValueError):
    stored = {}
# Migrate old monthly counter conservatively: do not discard previously
# reserved characters if this is an upgrade from the old implementation.
old_reserved = int(stored.get('characters_reserved', 0))
start_string = stored.get('start_date')
try:
    start_date = date.fromisoformat(start_string) if start_string else today
except (TypeError, ValueError):
    start_date = today
usage = {
    'start_date': start_date.isoformat(),
    'characters_reserved': max(0, old_reserved),
    'budget_characters': TOTAL_BUDGET,
    'duration_days': DAYS,
}
# Pacing is cumulative, so unused daily allowance carries forward. The total
# never resets automatically; a fresh free API credit is not assumed.
elapsed = max(0, (today - start_date).days)
allowed_today = min(TOTAL_BUDGET, (elapsed + 1) * DAILY_ALLOWANCE)

def save_usage():
    USAGE_FILE.write_text(json.dumps(usage, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def trimmed_fields(row):
    title = str(row.get('title') or '').strip()
    summary = str(row.get('summary') or '').strip()
    if len(title) >= MAX_ITEM_CHARS:
        return title[:MAX_ITEM_CHARS], ''
    return title, summary[:max(0, MAX_ITEM_CHARS - len(title))]

def translate(texts, target):
    payload = urllib.parse.urlencode([('text', s) for s in texts] + [('target_lang', target)]).encode()
    req = urllib.request.Request(ENDPOINT, data=payload, headers={
        'Authorization': 'DeepL-Auth-Key ' + KEY,
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'BlackSeaMonitor/1.1'
    }, method='POST')
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                result = json.loads(response.read())['translations']
            if len(result) != len(texts):
                raise ValueError('Unexpected number of translations')
            return [r['text'] for r in result]
        except urllib.error.HTTPError as exc:
            print(f'{target}: DeepL HTTP {exc.code}')
            if exc.code in (403, 456):
                return None  # invalid key or exhausted provider quota
        except (OSError, ValueError, KeyError) as exc:
            print(f'{target}: DeepL error: {type(exc).__name__}')
        if attempt < 2:
            time.sleep(2 ** attempt)
    return None

# Process each publication across all languages before moving to the next.
# This prevents Bulgarian/Romanian from consuming the entire daily allowance
# before Ukrainian gets a chance to translate anything.
LANGUAGES = [('bg', 'BG'), ('ro', 'RO')]
previous_by_lang = {}
results_by_lang = {lang: [] for lang, _ in LANGUAGES}
new_by_lang = {lang: 0 for lang, _ in LANGUAGES}
for lang, _ in LANGUAGES:
    path = DATA / f'statements.{lang}.json'
    try:
        previous = json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        previous = []
    previous_by_lang[lang] = {row['url']: row for row in previous if row.get('url')}

# Incidents share the SAME usage counter and DeepL key as the news feed.
# Priority is given to new maritime incident cards, whose translations can be
# displayed on the map and in the archive. English originals remain canonical.
incident_source = json.loads((DATA / 'incidents.json').read_text(encoding='utf-8'))
incident_fields = ('type','method','location','summary','locationPrecision')
incident_results = {lang: [] for lang,_ in LANGUAGES}
incident_cache = {}
for lang,_ in LANGUAGES:
    try:
        old_incidents=json.loads((DATA / f'incidents.{lang}.json').read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        old_incidents=[]
    incident_cache[lang]={row['id']:row for row in old_incidents if row.get('id')}
for row in incident_source:
    # Each incident has at most 500 source characters translated per target.
    trimmed={}
    remaining=MAX_ITEM_CHARS
    for field in incident_fields:
        value=str(row.get(field) or '').strip()
        trimmed[field]=value[:remaining]
        remaining-=len(trimmed[field])
    original=[trimmed[f] for f in incident_fields if trimmed[f]]
    cost=sum(map(len,original))
    signature=hashlib.sha256(json.dumps(trimmed,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
    for lang,target in LANGUAGES:
        prior=incident_cache[lang].get(row.get('id'))
        if prior and prior.get('_source_hash')==signature and prior.get('_translated'):
            incident_results[lang].append(prior)
            continue
        translated=None
        if KEY and cost and usage['characters_reserved']+cost<=allowed_today:
            usage['characters_reserved']+=cost
            save_usage()
            translated=translate(original,target)
        translated_fields=dict(trimmed)
        if translated:
            translated_fields.update(zip([f for f in incident_fields if trimmed[f]],translated))
        # Never show a partially translated synopsis as a complete translation.
        incident_results[lang].append({'id':row['id'],**translated_fields,
          '_source_hash':signature,'_translated':bool(translated)})
for lang,_ in LANGUAGES:
    (DATA / f'incidents.{lang}.json').write_text(
        json.dumps(incident_results[lang],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{lang}: translated incident cards {sum(bool(x["_translated"]) for x in incident_results[lang])}/{len(incident_results[lang])}')

for row in SOURCE:
    title, summary = trimmed_fields(row)
    signature = hashlib.sha256((title + '\0' + summary).encode('utf-8')).hexdigest()
    text_parts = [x for x in (title, summary) if x]
    cost = sum(map(len, text_parts))
    for lang, target in LANGUAGES:
        prior = previous_by_lang[lang].get(row.get('url'))
        if prior and prior.get('_source_hash') == signature and prior.get('_translated'):
            results_by_lang[lang].append({**row, 'title': prior['title'],
                'summary': prior['summary'], '_source_hash': signature, '_translated': True})
            continue
        translated = None
        if KEY and cost and usage['characters_reserved'] + cost <= allowed_today:
            usage['characters_reserved'] += cost
            save_usage()
            translated = translate(text_parts, target)
        if translated:
            results_by_lang[lang].append({**row, 'title': translated[0],
                'summary': translated[1] if len(translated) > 1 else '',
                '_source_hash': signature, '_translated': True})
            new_by_lang[lang] += 1
        else:
            results_by_lang[lang].append({**row, 'title': title,
                'summary': summary, '_source_hash': signature, '_translated': False})

for lang, _ in LANGUAGES:
    (DATA / f'statements.{lang}.json').write_text(
        json.dumps(results_by_lang[lang], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{lang}: {new_by_lang[lang]} new translations, {len(results_by_lang[lang])} total records')
print(f'90-day pacing: day {elapsed + 1}, reserved {usage["characters_reserved"]:,} / {allowed_today:,} currently allowed; lifetime cap {TOTAL_BUDGET:,}')
if not KEY:
    print('DEEPL_API_KEY is missing; untranslated originals are retained')
