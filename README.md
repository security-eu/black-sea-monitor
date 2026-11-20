# EU Black Sea / Maritime Security Monitor

Independent maritime-security reference site focusing on Romania and Bulgaria. This repository publishes a single-page EN/BG/RO interface, a sourced incident archive, interactive map, provenance-tagged political/institutional records, dated trends and machine-readable feeds.

## Publication model

- **Published** incident records: `data/incidents.json`. Published statements: `data/statements.json`. Sources and dates are displayed, but the site is **not a government or EU institution**.
- **Automatically stored discovery leads (not shown as verified statements or mapped incidents)**: `data/incident_candidates.json` and `data/statement_candidates.json`; these files are intentionally **not read by the public frontend**.
- `.github/workflows/statement-monitor.yml` checks feeds approximately every 6 hours and commits validated published datasets and discovery-candidate files directly to `main`, **without Pull Requests**. The separate `translate-after-merge.yml` workflow uses DeepL **after a published dataset changes**, immediately writing cached translations and cumulative usage into main to avoid re-spending on repeated scheduled checks. Scheduled GitHub Actions can be delayed or suspended.
- For news: `kind` is `official` (direct institutional source), `news` (media account) or `auto` (unverified discovery). The default list includes **only official records flagged `reviewed`**. Never convert a Google News discovery URL into an official citation.
- Any direct source link must resolve to the **publisher's original article or institutional release**. Google News RSS links remain in *candidate* files only. These candidates are stored automatically but do not appear as verified official statements or mapped attacks. An editor must separately verify event/statement dates, authors and identities before they can be promoted to verified status.

## Attribution standard

`attribution_status` is independent of the existence of an incident:

- `claimed`: a specifically identifiable party makes an allegation; the field `attribution_details` should name that party and explain its claim.
- `authority_confirmed`: responsible authorities have publicly confirmed attribution. The source of that confirmation **must** be identified (not merely a media headline).
- `undetermined`: attribution is not established by the available evidence.

Existing records inherited from the previous site are **not retrospectively certified**; check the original linked evidence. Inherited 2026 records require an additional audit before treating them as verified. Claims of responsibility and independent establishment of responsibility are distinct.

## Map / data methodology

- Categories: `vessel_strike`, `mine`, `drone_debris`, `port_attack`, `mine_action`.
- Records with `event_kind=response` (e.g. MCM Black Sea activations) are **not attacks** and are excluded from incident trend counts.
- Map markers can be approximate administrative/offshore anchors. They are **not validated impact locations**. Unlocated automatic leads are never mapped, and report publication dates must **not** be substituted for dates of incidents.
- Historical source-linked entries were added for Romanian drifting mines in March, July and December 2022, Bulgarian mines near Varna in June 2022, Cape Kochan in January 2023 and Pasha Dere in May 2024; a mine washed ashore in Romania in January 2023; drone fragments reported near Plauru in September 2023; the multinational MCM group's launch in July 2024; and Romania's MCM group command in July 2025. Official sources appear on each card. The map is intentionally restricted to Romanian and Bulgarian relevance; seven inherited Ukrainian vessel records remain in the dataset as an archival reference but do not display on the EU-coast map.
- Data is incomplete; apparent trends reflect published records and the editorial selection, not exhaustive incident totals.

## Structure

- `index.html`: **single application** for EN, BG and RO, language by `?lang=en|bg|ro` without page navigation. Language switching preserves active screen and open incident.
- `bg.html`, `ro.html`: minimal backwards-compatibility redirects only, not independent site copies.
- `about.html`: user-visible methodological/editorial policy (and a declared, not invented, responsible editor status).
- `assets/style.css`: a single stylesheet; `js/app.js`: single application module.
- `i18n/en.json`, `i18n/bg.json`, `i18n/ro.json`: interface dictionaries.
- `data/incidents.{ro,bg}.json`, `data/statements.{ro,bg}.json`: cached DeepL translations; DO NOT delete these on upgrades.
- `data/translation_usage.json`: **shared cumulative DeepL budget**. DO NOT reset it. 900,000-character lifetime safety cap, no daily limit. Only shortened texts are translated (title up to 200 characters, summary up to 260 in whole sentences, short incident fields); identical strings are translated once and failed requests are refunded. The site links to the original source for full text; DeepL's provider-reported quota is authoritative, and other uses of the API key are not visible to this site.
- `scripts/migrate_and_enrich.py`: idempotent structured data migration/curated historical records; preserves other live source records.
- `scripts/validate_data.py` and `schemas/*.json`: publication schema checks.
- `scripts/generate_feeds.py`: RSS/CSV and last-updated metadata. Run after editing the datasets.
- `rss.xml`, `data/incidents.csv`, `sitemap.xml`, Open Graph image, small favicon are included.

## GitHub deployment procedure

1. Back up current `data/` and `.github/workflows/` before changing anything.
2. Upload site code, `i18n/`, `assets/`, `scripts/`, `schemas/`, `.github/workflows/`, `about.html`, SEO and feed files to the GitHub Pages publishing branch. **Do not overwrite your current live `data/` with the sample/preview data in the full ZIP.**
3. In the repository root, run `python scripts/migrate_and_enrich.py`, `python scripts/generate_feeds.py`, and `python scripts/validate_data.py` after `python -m pip install jsonschema==4.23.0`; commit the resulting merged data. The scheduled workflow performs migration and validation automatically before committing changes. The sample full ZIP already contains the migrated preview data for local demonstrations.
4. Preserve the existing GitHub Actions secret `DEEPL_API_KEY`; the URL defaults to DeepL's Free API. Set workflow permissions to **Read and write** .
5. Run `Auto-update Black Sea news and incident leads` manually. It validates and commits changes to `main` directly. The separate `Translate published Black Sea records` workflow then translates changed published records, using the shared lifetime budget.
6. Configure `config.json` > `corrections_email` with a real, publicly monitored contact. Until you do, the methodology page transparently says that contact has not been configured.

### Third-party map assets

Leaflet 1.9.4 is vendored in `assets/vendor/leaflet/` (BSD-2 licence included), so the site no longer depends on unpkg. Map tiles come from OpenStreetMap and are shown with a dark CSS filter; OSM usage is subject to its tile-use policy, so heavy traffic should move to a tile provider or self-hosting. The Inter font is loaded from Google Fonts with a system-font fallback.

### Frontend layout (November 2026 redesign)

- Desktop: summary figures under the header; left panel with **Incidents** (period, category, country, attribution, search) and **Statements** (Official / Press / All, region) tabs; map on the right; incident details open in a side card; monthly chart below.
- Mobile: three tabs (Map / Incidents / Statements); incident details open as a bottom sheet.
- Every incident has a permanent link `#<id>`; language is `?lang=en|bg|ro` and is remembered.
- Public URL is `https://security-eu.github.io/black-sea-monitor/`. Canonical, Open Graph, `sitemap.xml`, `robots.txt`, `config.json` and `scripts/generate_feeds.py` use this address.

### Test and translation limitations

Browser tests and JSON-schema checks are included. Some legacy cached translations are English fallback (`_translated:false`) until DeepL next runs with a valid secret and available budget. Do **not** show them as translated. Machine translations are clearly separate from verified quotations. During edits, protect against duplicating a presidential statement from the same date; identical URLs and titles are deduplicated by migration, while semantically similar but different titles still need human review.

## Dates and scope

This build uses the currently available dataset snapshot, which may lag your active GitHub repository. A full ZIP is a local **preview**, not a safe direct overwrite of the live data. The `update` package intentionally excludes data to avoid losing new live rows, translations, and budget history.

### Current preview snapshot

The bundled preview has **33 historical/current dataset rows** (26 relevant to Romanian/Bulgarian coastal security, plus 7 retained but hidden Ukrainian records) and **17 statement rows**. Exactly five institutional statement links were checked against the original pages in this revision; other inherited institutional entries remain labelled as awaiting editorial verification and are excluded from the default statement view. This preview is not guaranteed to match your latest GitHub repository, which may contain additional automatically indexed headlines.

## Automatic publishing policy

There is **no editorial Pull Request gate**: every scheduled check writes valid data/candidate updates directly to `main` when changes exist, and the separate translation workflow runs on changes to published datasets. JSON schema validation blocks malformed published data before any push. Discovery candidates, by design, **are not public official statements or incident markers**; promoting them requires reliable direct sources, an actual event date and justified location. This prevents the automatic workflow from inventing attack coordinates or falsely asserting official status.
