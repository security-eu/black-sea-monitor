"""Editorial corrections to existing incident records, applied on every run.

Keeps fixes safe from data uploads: if an older incidents.json is uploaded,
the next workflow run re-applies these. Add new corrections to CORRECTIONS.
"""
from bsm_common import load_json, save_json

SRC_24CHASA = {'label': '24 Chasa, 20 Nov 2026', 'url': 'https://www.24chasa.bg/bulgaria/article/23962953'}

CORRECTIONS = {
    'gas-husky-2026': {
        'flag': 'Liberia',
        'type': 'LPG carrier',
        'summary': 'Liberian-flagged LPG carrier struck on the night of 16–17 November. Not sunk as of 19 November: '
                   'semi-submerged with a 45° list and drifting south-east of Cape Kaliakra. All 19 crew were rescued '
                   'by Bulgarian authorities after a night in a life raft.',
        'location': 'South-east of Cape Kaliakra, Bulgaria (drifting)',
        'lat': 43.25, 'lon': 28.75,
        'add_sources': [SRC_24CHASA],
    },
    'betul-8-2026': {
        'flag': 'Somalia',
        'type': 'General cargo ship',
        'summary': 'Somali-flagged general cargo ship struck on 16 November. As of 19 November it was capsized on its side '
                   'and drifting, about 20 nautical miles south of where it was hit. All 12 crew were rescued by the '
                   'Bulgarian Air Force and Navy.',
        'location': 'Off Cape Kaliakra, Bulgaria (drifting)',
        'add_sources': [SRC_24CHASA],
    },
}


def main():
    rows = load_json('incidents.json', [])
    for r in rows:
        fix = CORRECTIONS.get(r.get('id'))
        if not fix:
            continue
        for k, v in fix.items():
            if k == 'add_sources':
                urls = {s.get('url') for s in r.get('sources', [])}
                r.setdefault('sources', []).extend(s for s in v if s['url'] not in urls)
            else:
                r[k] = v
    if save_json('incidents.json', rows):
        print('Corrections applied')


if __name__ == '__main__':
    main()
