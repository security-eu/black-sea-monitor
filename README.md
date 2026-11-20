# Black Sea Maritime Security Monitor

Static English-language Leaflet map of **selected, sourced civilian-vessel incidents**, with date filters and a searchable archive. This is an **initial sample**, not an exhaustive or live feed. Last editorial update: 20 November 2026.

## Publish with GitHub Pages

1. Sign in at https://github.com/new and create a **public** repository, for example `black-sea-monitor`.
2. Upload `index.html`, `data/incidents.json`, and this `README.md` into the repository, preserving the `data/` folder. Alternatively upload the ZIP's *contents*, not the ZIP itself.
3. Go to **Settings → Pages → Build and deployment**. Choose **Deploy from a branch**, branch **main**, folder **/(root)**, then **Save**.
4. Wait for the deployment. The site URL will normally be `https://YOUR-USERNAME.github.io/black-sea-monitor/`.
5. To add records, edit `data/incidents.json` in GitHub and commit; Pages will redeploy automatically.

To test locally, run `python -m http.server 8000` in this directory and open `http://localhost:8000`. Opening `index.html` directly with `file://` may block JSON loading.

## Editorial policy

- Record dates and vessel identities as reported by cited sources. Where sources disagree, explain the discrepancy.
- `confirmed` means credible reports identify a Russian strike; it does **not** mean a court has established legal responsibility. `reported` indicates contested or not independently verified attribution or vessel identity.
- Map points are **illustrative locations** (port centres or approximate maritime areas), **not verified strike coordinates**. Do not use for navigation or operational decisions.
- The coastal-area filter refers to the **location of the incident**, not the vessel's flag. Izmail is a Ukrainian Danube port near Romania.
- A separate row for a second strike on the same vessel is intentional.
- Data is manually curated; no automatic verification or live updates.

## Technology

HTML, CSS, JavaScript, Leaflet and OpenStreetMap tiles; no server or account database required. An internet connection is required to load Leaflet and map tiles.


## Political statements feed (new)

The **Statements** button opens a reverse-chronological feed from `data/statements.json`, with region and year filters. Seed entries link directly to official sources. No Romania-specific entry has been added without a verified official source.

### Automatic discovery (every six hours)

`.github/workflows/statement-monitor.yml` runs `scripts/update_statements.py` on a schedule (GitHub Actions cron can be delayed). It discovers possible Bulgaria/Romania/EU statements via Google News RSS search, writes `data/statement_candidates.json`, and opens a review pull request. **It does not automatically publish candidate claims**. Verify source, speaker, event date and summary, then add approved records to `data/statements.json`. Merge to publish via GitHub Pages.

In GitHub Settings → Actions → General, allow workflows to create pull requests if needed. GitHub Pages must be configured to deploy from main. Google News RSS is a discovery service, not an authoritative source; results may be missing or unavailable.

## Expanded political archive

The political statements archive contains 17 sourced records, including Romania-specific statements from AGERPRES and the Romanian Ministry of Internal Affairs, plus EU institutional releases. Entries are summaries, not verbatim quotations. The RSS workflow generates review candidates, not automatic publication. Editorial verification remains required.
