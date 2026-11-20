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

## Always-visible political statements

Desktop: statements occupy a fixed right-hand column next to the interactive map. Mobile: statements appear directly below the map in a permanently visible scrollable feed. Existing scheduled review workflow is unchanged.


## Mobile design
On screens up to 750px, the Map and Statements tabs show one panel at a time, avoiding stacked overlays. The archive remains a collapsed drawer over the map. Desktop retains a persistent left news column.

## Automated updates: what actually happens
The included GitHub Actions workflow runs every 6 hours (UTC, subject to GitHub scheduling delays), or manually via Actions → Discover Black Sea official statements → Run workflow. It searches Google News RSS for candidates, saves `data/statement_candidates.json`, and opens/updates a pull request for review. **It does not publish candidates to `data/statements.json` automatically.** After reviewing a candidate against its original source, manually add it to `data/statements.json` and commit. GitHub Pages then rebuilds.

To enable: repository Settings → Actions → General → Workflow permissions → Read and write permissions; allow GitHub Actions to create and approve pull requests (if the setting is available). In Settings → Pages select Deploy from a branch, main, /(root). Check Actions runs for errors; some repositories restrict PR creation by the built-in token. Public feeds are not guaranteed complete or available.

## Fully automatic news updates
The workflow `.github/workflows/statement-monitor.yml` runs approximately every 6 hours and directly commits new indexed RSS headlines into `data/statements.json`. GitHub Pages then deploys the change. GitHub Actions requires repository Settings → Actions → General → Workflow permissions → Read and write.

**Editorial distinction:** Automated entries are marked "automated news index" and contain headline and source link only; they are NOT verified political quotations or independently verified statements. Previously curated summaries remain unchanged. Google News RSS can return aggregator links and may miss news; the pipeline has no paid API dependency. Scheduled runs may be delayed or paused by GitHub. RSS availability and third-party coverage are not guaranteed.

## Languages

The site has four interface languages: English (`index.html`), Bulgarian (`bg.html`), Romanian (`ro.html`), and Ukrainian (`uk.html`). Switcher appears in the header. Filters retain their original underlying data values. Existing source summaries and automatically indexed news headlines remain in their original English/source language; the interface and dynamic UI messages are translated. Future editorial translation of content requires a separate multilingual data pipeline. Upload all four HTML pages to the GitHub Pages repository root.

## Automatic translations (DeepL)
The workflow fetches news, then runs `scripts/translate_statements.py` to translate titles and summaries into Bulgarian, Romanian and Ukrainian. English remains the source feed. The translation job caches by original title+summary+URL and only re-translates changed or new records. The originals and source links remain in the JSON.

**Required setup:** GitHub repository → Settings → Secrets and variables → Actions → New repository secret → name `DEEPL_API_KEY`, value your DeepL API key. Free DeepL API accounts use the default endpoint. For paid API accounts, set Actions repository variable `DEEPL_API_URL` to `https://api.deepl.com/v2/translate`. Then go to Actions → Auto-update Black Sea news → Run workflow. Keep Actions Workflow permissions = Read and write. Never commit your API key.

Without a valid API key, the workflow still updates news but displays the original text with a translation-unavailable note. New records are automatically translated on the next run after a key is added. DeepL usage may incur charges/quotas; translation API support for the chosen languages depends on your DeepL account. Machine translations are not editorially verified quotations.

## Translation cost safeguards

- Translates only the headline and short description, at most **500 source characters total per news item per language**. The full article remains available via the original source link.
- Translation is **cached by source URL and hash of the capped source text**; unchanged entries are not translated again.
- Monthly local budget is **400,000 source characters** across Bulgarian, Romanian and Ukrainian, leaving a 100,000-character buffer relative to DeepL API Free's commonly advertised 500,000-character monthly quota.
- The file `data/translation_usage.json` tracks characters reserved before API calls and is committed by GitHub Actions. Do not delete or reset it during a billing month. DeepL's billing month may differ from the UTC calendar month; this local budget is an approximation, not a guarantee against hitting the provider limit. If DeepL rejects requests, the site displays the source text and retries on a later run.
- The source headline and summary remain in `data/statements.json`; translations are stored in `data/statements.bg.json`, `data/statements.ro.json`, and `data/statements.uk.json`.
- DeepL does not automatically translate full linked articles. Existing translations may be refreshed once because the cache signature now reflects the capped source text.

## One-time Developer credit: 90-day pacing

This version caps DeepL calls to **900,000 source characters total** and releases a cumulative allowance of **10,000 characters per UTC day**, measured from the first deployment of this version. The remaining 100,000 characters of the advertised one-time 1,000,000 credit are kept as a reserve. Unused daily allowance rolls forward, but the lifetime cap **does not reset after 90 days**. Existing translation cache is reused and no more than 500 characters of title+summary are sent per news item, per target language. If the daily or total limit is reached, the source-language text remains visible and translations resume when pacing allows.

**Important:** This does not ensure the DeepL provider credit will last 90 days if the same key is used elsewhere, if provider billing counts characters differently, or if prior API use is not recorded in `data/translation_usage.json`. The start date is established from the committed usage file; do not delete or reset that file. DeepL API usage dashboard is authoritative.
