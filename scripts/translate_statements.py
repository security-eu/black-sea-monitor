"""Cached DeepL translation: Romanian priority, 500-char items, one 90-day shared budget."""
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

# Cache by source identity, not translated title. Romanian is processed first so
# a tight daily budget cannot be consumed entirely by Bulgarian beforehand.
LANGUAGES = [('ro', 'RO'), ('bg', 'BG')]

def load_rows(name):
    try:
        value = json.loads((DATA / name).read_text(encoding='utf-8'))
        return value if isinstance(value, list) else []
    except (FileNotFoundError, ValueError, TypeError):
        return []

incident_source = [r for r in load_rows('incidents.json')
                   if r.get('country') in ('Romania', 'Bulgaria')]
incident_fields = ('summary', 'attribution_details', 'type', 'method', 'location', 'locationPrecision')

# Preserve existing translated objects across temporary API outages and
# no-key runs. Never claim the English fallback is translated.
def available(cost):
    return bool(KEY and cost > 0 and
                usage['characters_reserved'] + cost <= allowed_today)

def reserved_translate(parts, target):
    cost = sum(len(p) for p in parts)
    if not available(cost):
        return None
    usage['characters_reserved'] += cost
    save_usage()   # pessimistically reserve before making any external request
    return translate(parts, target)

for lang, target in LANGUAGES:
    print(f'Processing language {lang} ({target}), usage reserved '
          f'{usage["characters_reserved"]:,}/{allowed_today:,} allowed so far')

    prior_incidents = {r['id']: r for r in load_rows(f'incidents.{lang}.json')
                       if r.get('id')}
    new_incidents = []
    translated_incidents = 0
    for row in incident_source:
        remaining = MAX_ITEM_CHARS
        trimmed = {}
        for field in incident_fields:
            trimmed[field] = str(row.get(field) or '').strip()[:remaining]
            remaining -= len(trimmed[field])
        signature = hashlib.sha256(json.dumps(trimmed, sort_keys=True,
                   ensure_ascii=False).encode('utf-8')).hexdigest()
        prior = prior_incidents.get(row.get('id'))
        if prior and prior.get('_source_hash') == signature and prior.get('_translated'):
            new_incidents.append(prior)
            translated_incidents += 1
            continue
        parts = [trimmed[k] for k in incident_fields if trimmed[k]]
        answer = reserved_translate(parts, target)
        if answer:
            translated = dict(trimmed)
            translated.update(zip([k for k in incident_fields if trimmed[k]], answer))
            new_incidents.append({'id':row['id'], **translated,
                                  '_source_hash':signature,'_translated':True})
            translated_incidents += 1
        else:
            if prior and prior.get('_source_hash') == signature:
                new_incidents.append(prior)
            else:
                new_incidents.append({'id':row['id'], **trimmed,
                                      '_source_hash':signature,'_translated':False})
    path = DATA / f'incidents.{lang}.json'
    serialized = json.dumps(new_incidents, ensure_ascii=False, indent=2)+'\n'
    if not path.exists() or path.read_text(encoding='utf-8') != serialized:
        path.write_text(serialized, encoding='utf-8')

    prior_news = {r['url']:r for r in load_rows(f'statements.{lang}.json')
                  if r.get('url')}
    new_news = []
    translated_news = 0
    # Newest news first: current source file is usually sorted, but do not rely on it.
    for row in sorted(SOURCE, key=lambda r:r.get('date',''), reverse=True):
        title, summary = trimmed_fields(row)
        signature = hashlib.sha256((title+'\0'+summary).encode('utf-8')).hexdigest()
        prior = prior_news.get(row.get('url'))
        if prior and prior.get('_source_hash') == signature and prior.get('_translated'):
            new_news.append({**row, 'title':prior['title'], 'summary':prior['summary'],
                             '_source_hash':signature,'_translated':True})
            translated_news += 1
            continue
        parts = [t for t in (title,summary) if t]
        answer = reserved_translate(parts, target)
        if answer:
            new_news.append({**row,'title':answer[0],
                             'summary':answer[1] if len(answer)>1 else '',
                             '_source_hash':signature,'_translated':True})
            translated_news += 1
        else:
            if prior and prior.get('_source_hash') == signature:
                new_news.append(prior)
            else:
                new_news.append({**row, 'title':title,'summary':summary,
                                 '_source_hash':signature,'_translated':False})
    path = DATA / f'statements.{lang}.json'
    serialized = json.dumps(new_news,ensure_ascii=False,indent=2)+'\n'
    if not path.exists() or path.read_text(encoding='utf-8') != serialized:
        path.write_text(serialized,encoding='utf-8')
    print(f'{lang}: translated {translated_incidents}/{len(new_incidents)} visible incident cards; '
          f'{translated_news}/{len(new_news)} news items')

print(f'90-day pacing: day {elapsed+1}, reserved '
      f'{usage["characters_reserved"]:,}/{allowed_today:,} allowed today; '
      f'lifetime hard cap {TOTAL_BUDGET:,}')
if not KEY:
    print('DEEPL_API_KEY missing: cannot create new translations; caches preserved')
if usage['characters_reserved'] >= allowed_today:
    print('Pacing allowance exhausted today: new translations resume as cumulative allowance grows')
