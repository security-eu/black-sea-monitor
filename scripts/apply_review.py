"""Publish or discard a reviewed issue. Triggered by the `approve` / `reject` labels.

Reads the ```review block of the issue, appends the record to
data/statements.json or data/incidents.json, then comments and closes the
issue. Usage (in Actions): ISSUE_NUMBER=12 LABEL=approve python scripts/apply_review.py
"""
import os
import re
import sys

from bsm_common import (NOW, decode_google_news, geocode, gh, host_of, load_json, official_region, save_json,
                        short_id, shorten, slug)

CATEGORIES = {'vessel_strike', 'mine', 'drone_debris', 'port_attack', 'mine_action'}
STATUSES = {'undetermined', 'claimed', 'authority_confirmed'}
COUNTRIES = {'romania': 'Romania', 'bulgaria': 'Bulgaria', 'ro': 'Romania', 'bg': 'Bulgaria'}
REGIONS = {'eu': 'EU', **COUNTRIES}
SITE = 'https://security-eu.github.io/black-sea-monitor/'


def parse_block(body):
    m = re.search(r'```review\s*\n(.*?)```', body or '', re.S)
    if not m:
        raise ValueError('No ```review block found in the issue.')
    fields, sources, in_sources = {}, [], False
    for line in m.group(1).splitlines():
        if in_sources and line.strip().startswith('-'):
            url = line.strip()[1:].strip()
            if url:
                sources.append(url)
            continue
        key, sep, value = line.partition(':')
        if not sep:
            continue
        key = key.strip().lower()
        in_sources = key == 'sources'
        if not in_sources:
            fields[key] = value.strip()
    fields['sources'] = sources
    return fields


def direct(url):
    url = (url or '').strip()
    if not re.match(r'^https://', url):
        return None
    if host_of(url) == 'news.google.com':
        return decode_google_news(url)
    return url


def build_statement(f, number):
    url = direct(f.get('url'))
    if not url:
        raise ValueError('`url:` must be the publisher’s direct https link (not Google News).')
    title = f.get('title', '').strip()
    date = f.get('date', '').strip()
    if len(title) < 5 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise ValueError('`title:` and `date:` (YYYY-MM-DD) are required.')
    region = REGIONS.get(f.get('region', '').strip().lower()) or official_region(url) or 'EU'
    off = official_region(url)
    return 'statements.json', {
        'id': 'statement-' + short_id(date, title), 'date': date, 'region': region,
        'source': f.get('source') or host_of(url), 'title': shorten(title, 220),
        'summary': shorten(f.get('summary', ''), 400), 'url': url,
        'kind': 'official' if off else 'news', 'reviewed': True,
        'source_type': 'institution' if off else 'press', 'review_issue': number}


def build_incident(f, number):
    country = COUNTRIES.get(f.get('country', '').strip().lower())
    date = f.get('date', '').strip()
    if not country or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise ValueError('`country:` (Romania/Bulgaria) and `date:` (YYYY-MM-DD) are required.')
    sources = []
    for u in f['sources']:
        d = direct(u)
        if d:
            sources.append({'label': host_of(d), 'url': d})
    if not sources:
        raise ValueError('Add at least one https source under `sources:`.')
    category = f.get('category', 'vessel_strike').strip()
    category = category if category in CATEGORIES else 'vessel_strike'
    status = f.get('attribution', 'undetermined').strip()
    status = status if status in STATUSES else 'undetermined'
    place = f.get('place', '').strip()
    vessel = f.get('vessel', '').strip() or ('Unnamed vessel' if category == 'vessel_strike' else category.replace('_', ' ').title())
    try:
        lat, lon = float(f.get('lat', '').replace(',', '.')), float(f.get('lon', '').replace(',', '.'))
        precision = 'Approximate position given by the editor; not a verified strike coordinate'
    except ValueError:
        lat, lon, precision = geocode(place, country)
    details = f.get('attribution_details', '').strip() or {
        'undetermined': 'No responsible party has been established in the cited sources.',
        'claimed': 'Responsibility has been claimed or alleged; see the cited sources. A claim is not a confirmed finding.',
        'authority_confirmed': 'Attribution confirmed by authorities, as stated in the cited sources.'}[status]
    rid = slug(f'{vessel}-{date}', 'incident-' + short_id(date, vessel))
    return 'incidents.json', {
        'id': rid, 'vessel': vessel, 'date': date, 'country': country, 'category': category,
        'event_kind': 'response' if category == 'mine_action' else 'incident',
        'attribution_status': status, 'attribution': 'unknown', 'attribution_details': details,
        'flag': f.get('flag', '').strip() or 'Not verified', 'type': f.get('object', '').strip() or 'Merchant vessel',
        'method': f.get('method', '').strip() or 'Reported attack',
        'summary': shorten(f.get('summary', ''), 500),
        'location': f'Off {place}' if place else f'{country} Black Sea area',
        'locationPrecision': precision, 'location_precision': precision,
        'lat': round(lat, 3), 'lon': round(lon, 3), 'position_status': 'approximate',
        'reviewed': True, 'sources': sources[:6], 'review_issue': number}


def main():
    number = int(os.environ['ISSUE_NUMBER'])
    label = os.environ.get('LABEL', '').lower()
    issue = gh('GET', f'/issues/{number}')
    state = load_json('review_state.json', {'seen_urls': [], 'issues': {}})
    entry = next((v for v in state['issues'].values() if v.get('issue') == number), None)

    if label == 'reject':
        gh('POST', f'/issues/{number}/comments', {'body': 'Rejected: not published. / Отклонено.'})
        gh('PATCH', f'/issues/{number}', {'state': 'closed', 'state_reason': 'not_planned'})
        if entry:
            entry['status'] = 'rejected'
            save_json('review_state.json', state)
        return

    try:
        fields = parse_block(issue.get('body', ''))
        kind = fields.get('type', '').lower()
        target, record = (build_incident if kind == 'incident' else build_statement)(fields, number)
    except ValueError as exc:
        gh('POST', f'/issues/{number}/comments', {'body': f'⚠️ Not published: {exc}\n\nFix the block above (✏️ Edit), then add **approve** again. / Исправь блок и снова поставь **approve**.'})
        try:
            gh('DELETE', f'/issues/{number}/labels/approve')
        except Exception:
            pass
        sys.exit(0)

    rows = load_json(target, [])
    ids = {r.get('id') for r in rows}
    if record['id'] in ids:
        record['id'] = record['id'] + '-' + short_id(number)
    rows.append(record)
    rows.sort(key=lambda r: r.get('date', ''), reverse=True)
    save_json(target, rows)
    link = f"{SITE}#{record['id']}" if target == 'incidents.json' else record['url']
    gh('POST', f'/issues/{number}/comments', {'body': f'✅ Published / Опубликовано: {link}\n\nThe site updates within a few minutes.'})
    gh('PATCH', f'/issues/{number}', {'state': 'closed', 'state_reason': 'completed'})
    if entry:
        entry['status'] = 'approved'
    save_json('review_state.json', state)
    print('Published', target, record['id'])


if __name__ == '__main__':
    main()
