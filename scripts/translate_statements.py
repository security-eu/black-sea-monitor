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

for lang, target in [('bg', 'BG'), ('ro', 'RO'), ('uk', 'UK')]:
    path = DATA / f'statements.{lang}.json'
    try:
        previous = json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        previous = []
    cache = {row['url']: row for row in previous if row.get('url')}
    result_rows = []
    newly_translated = 0
    for row in SOURCE:
        title, summary = trimmed_fields(row)
        signature = hashlib.sha256((title + '\0' + summary).encode('utf-8')).hexdigest()
        prior = cache.get(row.get('url'))
        if prior and prior.get('_source_hash') == signature and prior.get('_translated'):
            result_rows.append({**row, 'title': prior['title'], 'summary': prior['summary'],
                                '_source_hash': signature, '_translated': True})
            continue
        text_parts = [x for x in (title, summary) if x]
        cost = sum(map(len, text_parts))
        translated = None
        if KEY and cost and usage['characters_reserved'] + cost <= allowed_today:
            # Reserve before the call. A timeout might still have been billed by DeepL.
            usage['characters_reserved'] += cost
            save_usage()
            translated = translate(text_parts, target)
        if translated:
            result_rows.append({**row, 'title': translated[0],
                                'summary': translated[1] if len(translated) > 1 else '',
                                '_source_hash': signature, '_translated': True})
            newly_translated += 1
        else:
            # Preserve the original content, without falsely claiming translation.
            result_rows.append({**row, 'title': title, 'summary': summary,
                                '_source_hash': signature, '_translated': False})
    path.write_text(json.dumps(result_rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{lang}: {newly_translated} new translations, {len(result_rows)} total records')
print(f'90-day pacing: day {elapsed + 1}, reserved {usage["characters_reserved"]:,} / {allowed_today:,} currently allowed; lifetime cap {TOTAL_BUDGET:,}')
if not KEY:
    print('DEEPL_API_KEY is missing; untranslated originals are retained')
