"""Shared helpers for discovery and review: feeds, Google News link decoding,
GitHub API, filtering and a small coastal gazetteer.

Standard library only, so the GitHub Actions job needs no extra installs.
"""
import base64
import hashlib
import html
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
UA = 'Mozilla/5.0 (compatible; EUBlackSeaSecurityMonitor/4.0; +https://security-eu.github.io/black-sea-monitor/)'
NOW = datetime.now(timezone.utc)

# First-party institutional sites: items from these are published automatically.
OFFICIAL_DOMAINS = {
    'consilium.europa.eu': 'EU', 'ec.europa.eu': 'EU', 'commission.europa.eu': 'EU',
    'eeas.europa.eu': 'EU', 'europarl.europa.eu': 'EU',
    'mfa.bg': 'Bulgaria', 'gov.bg': 'Bulgaria', 'government.bg': 'Bulgaria',
    'president.bg': 'Bulgaria', 'mod.bg': 'Bulgaria', 'mvr.bg': 'Bulgaria', 'navy.mod.bg': 'Bulgaria',
    'gov.ro': 'Romania', 'presidency.ro': 'Romania', 'mae.ro': 'Romania', 'mai.gov.ro': 'Romania',
    'mapn.ro': 'Romania', 'navy.ro': 'Romania', 'dsu.mai.gov.ro': 'Romania', 'isu.ro': 'Romania',
}


def load_json(name, default):
    try:
        return json.loads((DATA / name).read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return default


def save_json(name, value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    path = DATA / name
    if not path.exists() or path.read_text(encoding='utf-8') != text:
        path.write_text(text, encoding='utf-8')
        return True
    return False


def host_of(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or '').lower().removeprefix('www.')
    except ValueError:
        return ''


def official_region(url):
    h = host_of(url)
    for domain, region in OFFICIAL_DOMAINS.items():
        if h == domain or h.endswith('.' + domain):
            return region
    return None


def norm_title(s):
    s = unicodedata.normalize('NFKC', str(s or '')).casefold()
    return re.sub(r'\W+', ' ', s).strip()


def strip_publisher(title, publisher):
    """Google News appends ' - Publisher' to titles."""
    if publisher and title.endswith(' - ' + publisher):
        return title[: -len(publisher) - 3].strip()
    return re.sub(r'\s+-\s+[^-]{2,60}$', '', title).strip() if ' - ' in title else title


def slug(text, fallback):
    s = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:60]
    return s if len(s) >= 3 else fallback


def short_id(*parts):
    return hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:10]


# ---------------------------------------------------------------- HTTP / feeds
def http_get(url, timeout=20, limit=3_000_000):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en,ro;q=0.8,bg;q=0.7'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit), r.geturl()


def parse_feed(body):
    """RSS 2.0 or Atom -> list of {title, url, date, publisher}."""
    root = ET.fromstring(body)
    out = []
    atom = '{http://www.w3.org/2005/Atom}'
    items = root.findall('./channel/item') or root.findall(f'{atom}entry')
    for it in items:
        title = (it.findtext('title') or it.findtext(f'{atom}title') or '').strip()
        link = (it.findtext('link') or '').strip()
        if not link:
            el = it.find(f'{atom}link')
            link = el.get('href', '') if el is not None else ''
        raw = it.findtext('pubDate') or it.findtext(f'{atom}updated') or it.findtext(f'{atom}published') or ''
        try:
            dt = parsedate_to_datetime(raw) if ',' in raw else datetime.fromisoformat(raw.replace('Z', '+00:00'))
            dt = dt.astimezone(timezone.utc)
        except (TypeError, ValueError, IndexError):
            continue
        src = it.find('source')
        publisher = (src.text or '').strip() if src is not None and src.text else ''
        if title and link:
            out.append({'title': html.unescape(title), 'url': link, 'date': dt, 'publisher': publisher})
    return out


def google_news(query, days=14):
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode(
        {'q': query, 'hl': 'en', 'gl': 'US', 'ceid': 'US:en', 'when': f'{days}d'})
    body, _ = http_get(url)
    return [x for x in parse_feed(body) if x['date'] <= NOW and (NOW - x['date']).days <= days]


def decode_google_news(url):
    """Best effort: turn a news.google.com/rss/articles/... link into the publisher's URL.
    Returns None when it cannot be decoded (Google changes this format from time to time)."""
    if host_of(url) != 'news.google.com':
        return url
    m = re.search(r'/articles/([^?/#]+)', url)
    if not m:
        return None
    article_id = m.group(1)
    # Older ids embed the URL directly in the base64 payload.
    try:
        raw = base64.urlsafe_b64decode(article_id + '=' * (-len(article_id) % 4))
        found = re.search(rb'https?://[\x21-\x7e]+', raw)
        if found and b'AU_yqL' not in raw[:12]:
            cand = found.group(0).decode('ascii', 'ignore')
            if host_of(cand) and host_of(cand) != 'news.google.com':
                return cand
    except (ValueError, base64.binascii.Error):
        pass
    # Newer ids need a signed batchexecute call.
    try:
        page, _ = http_get(f'https://news.google.com/articles/{article_id}', timeout=15)
        page = page.decode('utf-8', 'ignore')
        sig = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not (sig and ts):
            return None
        inner = ['garturlreq', [['X', 'X', ['X', 'X'], None, None, 1, 1, 'US:en', None, 1, None, None, None, None, None, 0, 1],
                                'X', 'X', 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0], article_id, int(ts.group(1)), sig.group(1)]
        payload = [[['Fbv4je', json.dumps(inner), None, 'generic']]]
        data = urllib.parse.urlencode({'f.req': json.dumps(payload)}).encode()
        req = urllib.request.Request('https://news.google.com/_/DotsSplashUi/data/batchexecute', data=data, headers={
            'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'})
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read(500_000).decode('utf-8', 'ignore')
        chunk = json.loads(text.split('\n\n', 1)[1])
        decoded = json.loads(chunk[0][2])[1]
        return decoded if host_of(decoded) and host_of(decoded) != 'news.google.com' else None
    except (OSError, ValueError, IndexError, TypeError, KeyError):
        return None


def page_description(url, limit=260):
    """og:description / meta description of a page, shortened; '' on failure."""
    try:
        body, _ = http_get(url, timeout=15, limit=600_000)
    except (OSError, ValueError):
        return ''
    text = body.decode('utf-8', 'ignore')
    for pat in (r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description',
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)'):
        m = re.search(pat, text, re.I)
        if m:
            return shorten(html.unescape(m.group(1)), limit)
    return ''


def shorten(text, limit):
    text = ' '.join(str(text or '').split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind('. '), cut.rfind('! '), cut.rfind('? '))
    if end >= limit * 0.45:
        return cut[:end + 1]
    space = cut.rfind(' ')
    return (cut[:space] if space > limit * 0.6 else cut[:limit - 1]).rstrip(' ,;:-') + '…'


# ---------------------------------------------------------------- GitHub API
def gh(method, path, body=None):
    token, repo = os.getenv('GITHUB_TOKEN'), os.getenv('GITHUB_REPOSITORY')
    if not token or not repo:
        raise RuntimeError('GITHUB_TOKEN / GITHUB_REPOSITORY not set')
    url = f'https://api.github.com/repos/{repo}{path}'
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': UA, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 422 and path.startswith('/labels'):
            return {}  # label already exists
        raise


def ensure_labels():
    for name, color, desc in (('review', '5cc8e0', 'Waiting for editor review'),
                              ('approve', '2ea44f', 'Publish this record on the site'),
                              ('reject', 'd73a4a', 'Do not publish')):
        gh('POST', '/labels', {'name': name, 'color': color, 'description': desc})


# ---------------------------------------------------------------- incidents
ATTACK = re.compile(
    r'\b(struck|strikes?|hit|hits|attack(?:ed|s)?|damaged|sunk|sinks|sank|explosion|exploded|mine)\b'
    r'|lovit|atacat|scufundat|avariat|explozi|mină'
    r'|удар|атакуван|потъна|потопен|взрив|мина\b', re.I)
VESSEL = re.compile(
    r'\b(ship|ships|vessel|vessels|tanker|freighter|carrier|cargo|bulker)\b'
    r'|\bnav[aăe]\b|petrolier|cargou|nava-cistern'
    r'|кораб|танкер|плавателн|съд\b', re.I)
JUNK = re.compile(
    r'wheat|grain market|price|premium|insurance|stocks?\b|opinion|analysis|podcast|explainer|why |how |what |\?'
    r'|de ce |защо |трябва ли|юрист|опозиция|такса|cost[ăa]?\b|recuperare', re.I)
COUNTRY = {'Romania': re.compile(r'romani|român|румън|constan[tț]a|sulina|mangalia|danube delta|delta dun|midia|vadu|tuzla', re.I),
           'Bulgaria': re.compile(r'bulgari|българ|varna|варна|burgas|бургас|byala|бяла|nesebar|sozopol|kaliakra|shabla', re.I)}
NAMED = [
    re.compile(r'\b([A-Z][A-Z0-9]{2,}(?:[ -][A-Z0-9]{1,}){0,3})\b'),  # BETUL 8, GAS HUSKY
    re.compile(r'["“„«\']([A-Z][\w .-]{2,30})["”»\']'),
]
NOT_NAMES = {'NATO', 'EU', 'USA', 'UK', 'US', 'BTA', 'DW', 'GPL', 'LPG', 'UNN', 'RBC', 'CMB', 'KSNS', 'КСНС', 'BBC', 'CNN', 'AFP',
             'TV', 'NEWS', 'P-8', 'ISW', 'UN', 'IMO', 'DSU', 'ISU', 'MAPN', 'MAE', 'MFA'}


def vessel_name(title):
    for pat in NAMED:
        for m in pat.finditer(title):
            name = m.group(1).strip().upper()
            if name not in NOT_NAMES and not re.fullmatch(r'[A-Z]-?\d+', name) and len(name) >= 3:
                return name
    return None


def incident_country(text, fallback):
    hits = [c for c, rx in COUNTRY.items() if rx.search(text)]
    return hits[0] if len(hits) == 1 else fallback


# Approximate offshore positions near named places (never verified strike points).
GAZETTEER = {
    'sulina': (45.15, 29.85, 'Romania'), 'sfantu gheorghe': (44.90, 29.70, 'Romania'), 'sf. gheorghe': (44.90, 29.70, 'Romania'),
    'danube delta': (45.00, 29.80, 'Romania'), 'delta dunarii': (45.00, 29.80, 'Romania'), 'midia': (44.33, 28.75, 'Romania'),
    'navodari': (44.30, 28.70, 'Romania'), 'constanta': (44.15, 28.75, 'Romania'), 'eforie': (44.05, 28.72, 'Romania'),
    'tuzla': (43.99, 28.72, 'Romania'), 'mangalia': (43.80, 28.65, 'Romania'), 'vadu': (44.44, 28.80, 'Romania'),
    'corbu': (44.38, 28.75, 'Romania'),
    'shabla': (43.54, 28.65, 'Bulgaria'), 'kaliakra': (43.36, 28.52, 'Bulgaria'), 'kavarna': (43.40, 28.40, 'Bulgaria'),
    'balchik': (43.38, 28.20, 'Bulgaria'), 'varna': (43.18, 28.05, 'Bulgaria'), 'kamchia': (43.02, 28.00, 'Bulgaria'),
    'byala': (42.88, 28.00, 'Bulgaria'), 'obzor': (42.82, 27.95, 'Bulgaria'), 'nesebar': (42.65, 27.80, 'Bulgaria'),
    'pomorie': (42.55, 27.70, 'Bulgaria'), 'burgas': (42.48, 27.60, 'Bulgaria'), 'sozopol': (42.42, 27.75, 'Bulgaria'),
    'primorsko': (42.27, 27.80, 'Bulgaria'), 'tsarevo': (42.17, 27.90, 'Bulgaria'), 'ahtopol': (42.10, 27.97, 'Bulgaria'),
}
COUNTRY_ANCHOR = {'Romania': (44.40, 29.60), 'Bulgaria': (42.95, 28.40)}


def ascii_fold(s):
    return unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()


def geocode(place, country):
    """(lat, lon, precision text) for a place name, or the country's offshore anchor."""
    key = ascii_fold(place).strip()
    for name, (lat, lon, c) in GAZETTEER.items():
        if name and name in key and (not country or c == country):
            return lat, lon, f'Approximate area off {place}; not a verified strike coordinate'
    lat, lon = COUNTRY_ANCHOR.get(country, (43.6, 29.0))
    return lat, lon, f'Illustrative offshore marker for {country}; exact location not established'


def guess_place(text):
    t = ascii_fold(text)
    for name in GAZETTEER:
        if re.search(r'\b' + re.escape(name) + r'\b', t):
            return name.title()
    return ''
