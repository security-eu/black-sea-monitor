# EU Black Sea — REVIEW PATCH (not deployed)

This upgrade adds responsive incident cards, EN/RO/BG saved translations,
and automated public-source discovery of vessel attack reports around Romania
and Bulgaria. It does not change map boundaries or add country overlays.

## Important: preserve live GitHub data

Upload ONLY the files supplied in this patch to the matching paths in your
GitHub repository. **Do not delete or overwrite** the live files:
`data/incidents.json`, `data/statements.json`, `data/statements.bg.json`,
`data/statements.ro.json`, or `data/translation_usage.json`. Those files hold
live incidents, newly indexed news, saved DeepL translations, and the cumulative
one-time credit ledger. The new workflow will generate
`data/incidents.bg.json`, `data/incidents.ro.json`, and
`data/incident_candidates.json` on its first run. Do not manually pre-fill
these files.

Workflow: `Auto-update Black Sea news`, about every six hours or manual run.
The new task queries public Google News RSS headlines and creates a provisional
map incident ONLY when two distinct news outlets mention the same named vessel
and a related attack near the coast of Romania or Bulgaria within 3 days.
Uncertain reports are left in the candidate queue. The marker is a generic
illustrative coastal anchor, NOT a verified attack location. Date is publication
not confirmed attack time. This automated source matching is not independent
fact-checking, and false positives remain possible.

Incident translations and news translations SHARE the existing total 900,000
character lifetime reservation ledger and 90-day pacing at 10,000 characters
per UTC day. DeepL key remains in GitHub Actions secret `DEEPL_API_KEY`.
Nothing in this package contains your DeepL key. Translation is performed at
workflow run time, not before the upload. The website falls back to English
until translations exist.

This patch is for your approval; nothing has been published to GitHub.
