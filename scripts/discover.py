"""Scheduled discovery (every 6 hours).

1. Statements from first-party institutional sites (EU, Romania, Bulgaria) are
   published straight to data/statements.json, with a direct link.
2. Press reports and possible new incidents become GitHub Issues labelled
   `review`. The editor approves them with the `approve` label (see
   scripts/apply_review.py) or rejects them with `reject`.

Run locally without GITHUB_TOKEN to see what would happen (dry run).
"""
import os
import re
from collections import defaultdict
from datetime import date

from bsm_common import (NOW, ATTACK, VESSEL, JUNK, decode_google_news, ensure_labels,
                        gh, guess_place, host_of, incident_country, load_json, norm_title,
                        official_region, page_description, save_json, short_id, shorten, strip_publisher,
                        vessel_name)

DRY = not os.getenv('GITHUB_TOKEN')
MAX_NEW_ISSUES = int(os.getenv('MAX_NEW_ISSUES', '12'))

OFFICIAL_QUERIES = {
    'EU': '(site:consilium.europa.eu OR site:ec.europa.eu OR site:commission.europa.eu OR site:eeas.europa.eu) "Black Sea"',
    'Bulgaria': '(site:mfa.bg OR site:gov.bg OR site:government.bg OR site:president.bg OR site:mod.bg) ("Black Sea" OR "Черно море")',
    'Romania': '(site:gov.ro OR site:presidency.ro OR site:mae.ro OR site:mai.gov.ro OR site:mapn.ro OR site:navy.ro) ("Black Sea" OR "Marea Neagră")',
}
PRESS_STATEMENT_QUERIES = {
    'Romania': 'site:agerpres.ro "Black Sea" (security OR drone OR ship OR attack)',
    'Bulgaria': 'site:bta.bg ("Black Sea" OR "Черно море") (security OR drone OR ship OR сигурност OR дрон)',
}
# Incident searches in English, Bulgarian and Romanian.
INCIDENT_QUERIES = [
    ('Romania', 'Black Sea ship attacked drone Romania', 'en'),
    ('Romania', 'navă lovită dronă Marea Neagră', 'ro'),
    ('Romania', 'mină marină Marea Neagră Constanța', 'ro'),
    ('Bulgaria', 'Black Sea ship attacked drone Bulgaria', 'en'),
    ('Bulgaria', 'кораб ударен дрон Черно море', 'bg'),
    ('Bulgaria', 'морска мина Черно море Варна', 'bg'),
]
LOCALE = {'en': ('en', 'US', 'US:en'), 'bg': ('bg', 'BG', 'BG:bg'), 'ro': ('ro', 'RO', 'RO:ro')}


def gnews(query, lang='en', days=14):
    import urllib.parse
    from bsm_common import http_get, parse_feed
    hl, gl, ceid = LOCALE[lang]
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode(
        {'q': query, 'hl': hl, 'gl': gl, 'ceid': ceid, 'when': f'{days}d'})
    body, _ = http_get(url)
    return [x for x in parse_feed(body) if x['date'] <= NOW and (NOW - x['date']).days <= days]


def safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as exc:  # network trouble must never break the whole run
        print(f'  ! {fn.__name__} failed: {type(exc).__name__}: {exc}')
        return []


# ------------------------------------------------------------ state
state = load_json('review_state.json', {'seen_urls': [], 'issues': {}})
seen_urls = set(state.get('seen_urls', []))
statements = load_json('statements.json', [])
incidents = load_json('incidents.json', [])
pub_titles = {norm_title(s.get('title')) for s in statements}
pub_urls = {s.get('url', '').split('?')[0].rstrip('/') for s in statements}


def words(t):
    return {w for w in norm_title(t).split() if len(w) > 3}


def similar_published(title, day):
    # Same story under a different headline (e.g. agency vs. institution wording).
    w = words(title)
    for s in statements:
        if abs((date.fromisoformat(s.get('date', '1970-01-01')) - day).days) <= 2:
            o = words(s.get('title'))
            if w and o and len(w & o) / min(len(w), len(o)) >= 0.6:
                return True
    return False


def remember(urls):
    for u in urls:
        seen_urls.add(u)


# ------------------------------------------------------------ 1. official statements
published = 0
press_leads = []
for kind, queries in (('official', OFFICIAL_QUERIES), ('press', PRESS_STATEMENT_QUERIES)):
    for region, query in queries.items():
        for item in safe(gnews, query):
            if item['url'] in seen_urls:
                continue
            title = strip_publisher(item['title'], item['publisher'])
            if norm_title(title) in pub_titles or similar_published(title, item['date'].date()) or not re.search(r'black sea|marea neagr|черно море|maritim|морск', title, re.I):
                remember([item['url']])
                continue
            direct = decode_google_news(item['url'])
            if direct and direct.split('?')[0].rstrip('/') in pub_urls:
                remember([item['url']])
                continue
            off_region = official_region(direct) if direct else None
            if off_region:
                summary = page_description(direct)
                row = {'id': 'statement-' + short_id(item['date'].date(), title), 'date': item['date'].date().isoformat(),
                       'region': off_region, 'source': item['publisher'] or host_of(direct), 'title': shorten(title, 220),
                       'summary': summary, 'url': direct, 'kind': 'official', 'reviewed': False,
                       'source_type': 'institution', 'auto_published': True}
                statements.append(row)
                pub_titles.add(norm_title(title))
                pub_urls.add(direct.split('?')[0].rstrip('/'))
                published += 1
                print(f'+ official [{off_region}] {title[:90]}')
            else:
                press_leads.append({'kind': 'statement', 'region': region, 'title': title, 'date': item['date'].date().isoformat(),
                                    'publisher': item['publisher'], 'urls': [direct or item['url']], 'discovery': [item['url']]})
            remember([item['url']])

if published:
    statements.sort(key=lambda r: r.get('date', ''), reverse=True)
    save_json('statements.json', statements)
print(f'Official statements published: {published}; press statement leads: {len(press_leads)}')

# ------------------------------------------------------------ 2. incident leads
known = [(r.get('country'), (r.get('vessel') or '').upper(), r.get('date', '')) for r in incidents]
known_names = {v for _, v, _ in known if v}


def near_known(country, day, days=3):
    # Unnamed reports within a few days of a mapped incident are most likely about it.
    for c, _, d in known:
        try:
            gap = abs((date.fromisoformat(d) - day).days)
            if (c == country and gap <= days) or gap <= 1:
                return True
        except ValueError:
            continue
    return False


raw, raw_keys = [], set()
for country, query, lang in INCIDENT_QUERIES:
    for item in safe(gnews, query, lang):
        title = strip_publisher(item['title'], item['publisher'])
        dedupe = (item['publisher'].casefold(), norm_title(title))
        if item['url'] in seen_urls or dedupe in raw_keys:
            continue
        raw_keys.add(dedupe)
        if JUNK.search(title) or not (ATTACK.search(title) and VESSEL.search(title)):
            continue
        raw.append({**item, 'title': title, 'country': incident_country(title, country)})

clusters = defaultdict(list)
for item in raw:
    name = vessel_name(item['title'])
    if name and any(name in k or k in name for k in known_names if len(k) > 3):
        remember([item['url']])  # already on the map
        continue
    if name:
        key = (item['country'], name)
    else:
        if near_known(item['country'], item['date'].date()):
            remember([item['url']])  # most likely one of the incidents already mapped
            continue
        key = (item['country'], 'unnamed-' + item['date'].date().isoformat())
    clusters[key].append(item)

incident_leads = []
for (country, name), items in clusters.items():
    items.sort(key=lambda x: x['date'])
    publishers = {i['publisher'].casefold() for i in items}
    if name.startswith('unnamed-') and len(publishers) < 2:
        continue  # an unnamed ship needs at least two outlets before it is worth a review
    vessel = None if name.startswith('unnamed-') else name.title() if name.isupper() and len(name) > 4 else name
    text = ' '.join(i['title'] for i in items)
    incident_leads.append({
        'kind': 'incident', 'country': country, 'vessel': vessel or '', 'date': items[0]['date'].date().isoformat(),
        'place': guess_place(text), 'title': items[0]['title'], 'publishers': sorted(publishers),
        'urls': [i['url'] for i in items][:5], 'discovery': [i['url'] for i in items],
        'headlines': [f"{i['date'].date()} · {i['publisher']} · {i['title']}" for i in items][:6]})
print(f'Incident leads after filtering and merging: {len(incident_leads)} (from {len(raw)} headlines)')

# ------------------------------------------------------------ 3. issues
def statement_issue(lead):
    direct = [u for u in lead['urls'] if host_of(u) != 'news.google.com']
    block = '\n'.join([
        'type: statement', f"title: {lead['title']}", f"date: {lead['date']}", f"region: {lead['region']}",
        f"source: {lead['publisher']}", f"url: {direct[0] if direct else ''}", 'summary: ',
    ])
    body = [f"**Press report found by the monitor** · {lead['publisher']} · {lead['date']}", '',
            f"[Open article]({lead['urls'][0]})", '']
    if not direct:
        body += ['> ⚠️ Only a Google News link was found. Paste the publisher’s direct link in `url:` before approving.', '']
    return f"[News] {lead['title'][:110]}", body, block


def incident_issue(lead):
    decoded = [decode_google_news(u) or u for u in lead['urls'][:3]]
    lines = [f'- {u}' for u in decoded]
    block = '\n'.join([
        'type: incident', f"vessel: {lead['vessel']}", f"date: {lead['date']}", f"country: {lead['country']}",
        'category: vessel_strike', f"place: {lead['place']}", 'lat: ', 'lon: ', 'object: Merchant vessel',
        'attribution: undetermined', 'attribution_details: ', f"summary: {lead['title']}", 'sources:', *lines,
    ])
    body = [f"**Possible incident near {lead['country']}** · {len(lead['publishers'])} outlet(s)", '',
            '**Headlines:**', *[f'- {h}' for h in lead['headlines']], '']
    title = f"[Incident] {lead['vessel'] or 'Unnamed vessel'} · {lead['country']} · {lead['date']}"
    return title, body, block


FOOTER = [
    '---', '**How to review / Как одобрить**',
    '1. Check the sources. Edit the fields in the block below if needed (✏️ Edit on this issue). '
    '`category`: vessel_strike, mine, drone_debris, port_attack, mine_action. `attribution`: undetermined, claimed, authority_confirmed. '
    '`lat`/`lon` are optional: if empty, the marker is placed by `place` or off the country’s coast.',
    '2. Add the label **approve** to publish, or **reject** to discard.',
    'Проверь источники, при необходимости поправь поля в блоке ниже и поставь метку **approve** (опубликовать) или **reject** (отклонить).',
]

created = 0
leads = incident_leads + press_leads
if not DRY and leads:
    try:
        ensure_labels()
    except Exception as exc:
        print('Could not create labels:', exc)
for lead in leads:
    key = lead['kind'] + ':' + short_id(lead.get('country', lead.get('region')), lead.get('vessel') or norm_title(lead['title']))
    if key in state['issues'] or created >= MAX_NEW_ISSUES:
        if key in state['issues']:
            remember(lead['discovery'])
        continue
    title, body, block = (incident_issue if lead['kind'] == 'incident' else statement_issue)(lead)
    text = '\n'.join(body + ['```review', block, '```', ''] + FOOTER)
    if DRY:
        print('\n=== would open issue:', title, '\n' + text[:900])
        number = None
    else:
        try:
            number = gh('POST', '/issues', {'title': title, 'body': text, 'labels': ['review']})['number']
        except Exception as exc:
            print('Could not open issue:', exc)
            continue
        print(f'Opened issue #{number}: {title}')
    state['issues'][key] = {'issue': number, 'status': 'open', 'created': NOW.date().isoformat()}
    remember(lead['discovery'])
    created += 1

state['seen_urls'] = sorted(seen_urls)[-4000:]
state['checked_at'] = NOW.isoformat()
if not DRY:
    save_json('review_state.json', state)
print(f'New review issues: {created}')
