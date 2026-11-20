"""Cached DeepL translation of shortened statements and incident cards (no daily limit, lifetime safety cap)."""
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

# One-time DeepL credit of 1,000,000 characters. There is no daily limit:
# news arrives unevenly (0 to 5+ items a day), so every new item is translated
# on the next run. TOTAL_BUDGET is only a lifetime safety cap that keeps a
# 100,000-character reserve; the DeepL usage dashboard is authoritative.
#
# Costs are kept low by translating short versions only: the site always
# links to the original source for the full text.
TOTAL_BUDGET = 900_000
TITLE_CHARS = 200
SUMMARY_CHARS = 260
INCIDENT_FIELD_CHARS = {'summary': 300, 'attribution_details': 220, 'type': 60,
                        'method': 80, 'location': 100, 'locationPrecision': 120}
# Generic placeholder text added by the news indexer; not worth translating.
PLACEHOLDER_SUMMARIES = ('News headline from the linked source',)
USAGE_FILE = DATA / 'translation_usage.json'
today = datetime.now(timezone.utc).date()
try:
    stored = json.loads(USAGE_FILE.read_text(encoding='utf-8'))
except (FileNotFoundError, ValueError):
    stored = {}
# Never discard characters already spent: the counter only grows.
usage = {
    'start_date': stored.get('start_date') or today.isoformat(),
    'characters_reserved': max(0, int(stored.get('characters_reserved', 0))),
    'budget_characters': TOTAL_BUDGET,
}
elapsed = max(0, (today - date.fromisoformat(usage['start_date'])).days)
allowed_today = TOTAL_BUDGET  # kept for log messages; no daily pacing any more

def save_usage():
    USAGE_FILE.write_text(json.dumps(usage, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def shorten(text, limit):
    """Cut to whole sentences within limit; fall back to a word boundary with an ellipsis."""
    text = ' '.join(str(text or '').split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind('. '), cut.rfind('! '), cut.rfind('? '))
    if end >= limit * 0.45:
        return cut[:end + 1]
    space = cut.rfind(' ')
    return (cut[:space] if space > limit * 0.6 else cut[:limit - 1]).rstrip(' ,;:-') + '…'

def trimmed_fields(row):
    title = shorten(row.get('title'), TITLE_CHARS)
    summary = str(row.get('summary') or '').strip()
    if summary.startswith(PLACEHOLDER_SUMMARIES):
        summary = ''
    return title, shorten(summary, SUMMARY_CHARS)


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

# Identical strings (e.g. the same location disclaimer on many cards) are
# translated once per language and reused, so they cost budget only once.
memo = {target: {} for _, target in LANGUAGES}

def reserved_translate(parts, target):
    """Translate parts, reusing cached strings. Returns None if any part cannot be translated now."""
    cache = memo[target]
    missing = list(dict.fromkeys(p for p in parts if p not in cache))
    if missing:
        cost = sum(len(p) for p in missing)
        if not available(cost):
            return None
        usage['characters_reserved'] += cost
        save_usage()   # pessimistically reserve before making any external request
        answer = translate(missing, target)
        if not answer:
            # DeepL does not bill failed requests: give the reservation back.
            usage['characters_reserved'] -= cost
            save_usage()
            return None
        cache.update(zip(missing, answer))
    return [cache[p] for p in parts]

def remember(target, source_parts, translated_parts):
    for s, t in zip(source_parts, translated_parts):
        if s and t:
            memo[target].setdefault(s, t)

def incident_parts(row):
    return {field: shorten(row.get(field), INCIDENT_FIELD_CHARS[field]) for field in incident_fields}

# Seed the string cache from translations already stored on disk.
for lang, target in LANGUAGES:
    by_id = {r['id']: r for r in load_rows(f'incidents.{lang}.json') if r.get('id') and r.get('_translated')}
    for row in incident_source:
        prior = by_id.get(row.get('id'))
        if prior:
            src = incident_parts(row)
            remember(target, [src[k] for k in incident_fields], [prior.get(k) for k in incident_fields])

def translate_news(lang, target):
    prior_news = {r['url']: r for r in load_rows(f'statements.{lang}.json') if r.get('url')}
    new_news, done = [], 0
    for row in sorted(SOURCE, key=lambda r: r.get('date', ''), reverse=True):
        title, summary = trimmed_fields(row)
        signature = hashlib.sha256((title + '\0' + summary).encode('utf-8')).hexdigest()
        prior = prior_news.get(row.get('url'))
        if prior and prior.get('_source_hash') == signature and prior.get('_translated'):
            new_news.append({**row, 'title': prior['title'], 'summary': prior['summary'],
                             '_source_hash': signature, '_translated': True})
            done += 1
            continue
        parts = [t for t in (title, summary) if t]
        answer = reserved_translate(parts, target)
        if answer:
            new_news.append({**row, 'title': answer[0],
                             'summary': answer[1] if len(answer) > 1 else '',
                             '_source_hash': signature, '_translated': True})
            done += 1
        elif prior and prior.get('_source_hash') == signature:
            new_news.append(prior)
        else:
            new_news.append({**row, 'title': title, 'summary': summary,
                             '_source_hash': signature, '_translated': False})
    write_if_changed(DATA / f'statements.{lang}.json', new_news)
    return done, len(new_news)

def translate_incidents(lang, target):
    prior_incidents = {r['id']: r for r in load_rows(f'incidents.{lang}.json') if r.get('id')}
    new_incidents, done = [], 0
    for row in incident_source:
        trimmed = incident_parts(row)
        signature = hashlib.sha256(json.dumps(trimmed, sort_keys=True,
                   ensure_ascii=False).encode('utf-8')).hexdigest()
        prior = prior_incidents.get(row.get('id'))
        if prior and prior.get('_source_hash') == signature and prior.get('_translated'):
            new_incidents.append(prior)
            done += 1
            continue
        keys = [k for k in incident_fields if trimmed[k]]
        answer = reserved_translate([trimmed[k] for k in keys], target)
        if answer:
            translated = dict(trimmed)
            translated.update(zip(keys, answer))
            new_incidents.append({'id': row['id'], **translated,
                                  '_source_hash': signature, '_translated': True})
            done += 1
        elif prior and prior.get('_source_hash') == signature:
            new_incidents.append(prior)
        else:
            new_incidents.append({'id': row['id'], **trimmed,
                                  '_source_hash': signature, '_translated': False})
    write_if_changed(DATA / f'incidents.{lang}.json', new_incidents)
    return done, len(new_incidents)

def write_if_changed(path, rows):
    serialized = json.dumps(rows, ensure_ascii=False, indent=2) + '\n'
    if not path.exists() or path.read_text(encoding='utf-8') != serialized:
        path.write_text(serialized, encoding='utf-8')

# Statements are short and the most visible, so both languages get them first;
# incident cards use whatever daily allowance is left.
for lang, target in LANGUAGES:
    done, total = translate_news(lang, target)
    print(f'{lang}: {done}/{total} statements translated '
          f'(reserved {usage["characters_reserved"]:,}/{allowed_today:,} allowed so far)')
for lang, target in LANGUAGES:
    done, total = translate_incidents(lang, target)
    print(f'{lang}: {done}/{total} incident cards translated '
          f'(reserved {usage["characters_reserved"]:,}/{allowed_today:,} allowed so far)')

print(f'DeepL characters used so far: {usage["characters_reserved"]:,} of the {TOTAL_BUDGET:,} safety cap')
if not KEY:
    print('DEEPL_API_KEY missing: cannot create new translations; caches preserved')
if usage['characters_reserved'] >= TOTAL_BUDGET:
    print('Lifetime safety cap reached: raise TOTAL_BUDGET only if the DeepL dashboard shows credit left')
