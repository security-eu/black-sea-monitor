// EU Black Sea Monitor — single application module for EN / BG / RO.
const $ = id => document.getElementById(id);
const LANGS = ['en', 'bg', 'ro'];
const LOCALE = { en: 'en-GB', bg: 'bg-BG', ro: 'ro-RO' };
const COUNTRIES = ['Romania', 'Bulgaria'];
const CATEGORIES = ['vessel_strike', 'mine', 'drone_debris', 'port_attack', 'mine_action'];
const STATUSES = ['claimed', 'authority_confirmed', 'undetermined'];
const CAT_COLOR = { vessel_strike: '#ff6b5b', mine: '#f4b740', drone_debris: '#b48cff', port_attack: '#ff9548', mine_action: '#8193a6' };
const DEFAULT_VIEW = { center: [43.6, 29.0], zoom: 7 };
const mqMobile = window.matchMedia('(max-width:900px)');

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } }
};
const params = new URLSearchParams(location.search);
const state = {
  lang: LANGS.includes(params.get('lang')) ? params.get('lang') : (LANGS.includes(store.get('bsm-lang')) ? store.get('bsm-lang') : 'en'),
  pane: 'incidents', view: 'map',
  period: 'all', category: 'all', country: 'all', status: 'all', search: '',
  kind: 'official', region: 'all',
  selected: null
};
let dict = {}, incidents = [], statements = [], updated = {};
const tr = { incidents: {}, statements: {} };
let map = null; const markers = new Map();

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const t = (k, vars) => { let s = dict[k] ?? k; if (vars) for (const [a, b] of Object.entries(vars)) s = s.replace('{' + a + '}', b); return s; };
const fmtDate = d => { try { return new Date(d + 'T12:00:00Z').toLocaleDateString(LOCALE[state.lang], { day: 'numeric', month: 'short', year: 'numeric' }); } catch { return d; } };
const isIncident = r => r.event_kind !== 'response';
const host = u => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch { return ''; } };

async function getJson(path, fallback) {
  try {
    const r = await fetch(path, { cache: 'no-cache' });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) { console.warn('Could not load', path, e); return fallback; }
}
const rows = v => Array.isArray(v) ? v : Array.isArray(v?.items) ? v.items : [];

/* ---------- data normalisation ---------- */
function normIncident(r) {
  let lat = r.lat ?? r.latitude, lon = r.lon ?? r.lng ?? r.longitude;
  lat = typeof lat === 'string' ? Number(lat.replace(',', '.')) : lat;
  lon = typeof lon === 'string' ? Number(lon.replace(',', '.')) : lon;
  return {
    ...r, lat, lon,
    category: CATEGORIES.includes(r.category) ? r.category : 'vessel_strike',
    event_kind: r.event_kind || (r.category === 'mine_action' ? 'response' : 'incident'),
    attribution_status: STATUSES.includes(r.attribution_status) ? r.attribution_status : 'undetermined'
  };
}
function normStatement(r) {
  if (['official', 'news', 'auto'].includes(r.kind)) return r;
  const h = host(r.url);
  const auto = h === 'news.google.com' || /News headline from the linked source/.test(r.summary || '');
  return { ...r, kind: auto ? 'auto' : 'news', reviewed: false };
}
const mappable = r => Number.isFinite(r.lat) && Number.isFinite(r.lon) && r.position_status !== 'unlocated' && !r.auto_discovered;

function localIncident(r) {
  const s = tr.incidents[state.lang]?.get(r.id);
  if (!s || !s._translated) return { ...r, _orig: state.lang !== 'en' };
  const out = { ...r };
  for (const k of ['type', 'method', 'location', 'summary', 'locationPrecision', 'attribution_details']) if (s[k]) out[k] = s[k];
  return out;
}
function localStatement(r) {
  const m = tr.statements[state.lang];
  const s = m?.get(r.url) || m?.get(r.id);
  if (!s || !s._translated) return { ...r, _orig: state.lang !== 'en' };
  return { ...r, title: s.title || r.title, summary: s.summary || r.summary };
}

/* ---------- filtering ---------- */
function visibleIncidents() {
  const now = Date.now(), q = state.search.trim().toLowerCase();
  return incidents.filter(r => {
    if (state.country !== 'all' && r.country !== state.country) return false;
    if (state.category !== 'all' && r.category !== state.category) return false;
    if (state.status !== 'all' && r.attribution_status !== state.status) return false;
    if (state.period !== 'all' && now - Date.parse(r.date + 'T00:00:00Z') > Number(state.period) * 864e5) return false;
    if (q) {
      const l = localIncident(r);
      const hay = [r.vessel, r.title, r.summary, l.summary, r.location, l.location, r.type, r.flag, r.country, t(r.country)].join(' ').toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}
function visibleStatements() {
  return statements
    .filter(r => state.region === 'all' || r.region === state.region)
    .filter(r => state.kind === 'all' || r.kind === state.kind)
    .sort((a, b) => b.date.localeCompare(a.date));
}

/* ---------- rendering ---------- */
function fillSelect(el, allKey, values, labelFn, current) {
  el.innerHTML = `<option value="all">${esc(t(allKey))}</option>` + values.map(v => `<option value="${esc(v)}">${esc(labelFn(v))}</option>`).join('');
  el.value = current;
}
function renderStatic() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  $('fSearch').placeholder = t('searchPh');
  document.querySelectorAll('[data-lang]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.lang === state.lang)));
  const about = 'about.html?lang=' + state.lang;
  $('aboutLink').href = about; $('footerAbout').href = about; $('brandLink').href = './?lang=' + state.lang;
  const usedCats = CATEGORIES.filter(c => incidents.some(r => r.category === c));
  fillSelect($('fCategory'), 'allCategories', usedCats, c => t('cat_' + c), state.category);
  fillSelect($('fCountry'), 'allCountries', COUNTRIES, c => t(c), state.country);
  fillSelect($('fStatus'), 'allStatuses', STATUSES, s => t('st_' + s), state.status);
  fillSelect($('fRegion'), 'allRegions', ['Romania', 'Bulgaria', 'EU'], c => t(c), state.region);
  $('fRegion').querySelector('option[value="all"]').textContent = t('allRegions');
  $('legend').innerHTML = usedCats.map(c => `<span><i style="background:${CAT_COLOR[c]}" class="${c === 'mine_action' ? 'ring' : ''}"></i>${esc(t('cat_' + c))}</span>`).join('');
  document.title = `${t('siteName')} · ${t('tagline')}`;
}
function renderKpis() {
  const inc = incidents.filter(isIncident), now = Date.now();
  $('kpiTotal').textContent = inc.length;
  $('kpi30').textContent = inc.filter(r => now - Date.parse(r.date + 'T00:00:00Z') <= 30 * 864e5).length;
  $('kpiRo').textContent = inc.filter(r => r.country === 'Romania').length;
  $('kpiBg').textContent = inc.filter(r => r.country === 'Bulgaria').length;
  $('kpiMines').textContent = inc.filter(r => r.category === 'mine').length;
  const u = updated.updated_at ? new Date(updated.updated_at) : null;
  $('updatedAt').textContent = u && !isNaN(u) ? u.toLocaleString(LOCALE[state.lang], { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '–';
}
function renderIncidents() {
  const list = visibleIncidents();
  $('countIncidents').textContent = list.length;
  $('resultCount').textContent = t('results', { n: list.length, total: incidents.length });
  document.querySelectorAll('[data-period]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.period === state.period)));
  $('incidentList').innerHTML = list.length ? list.map(r => {
    const chip = r.event_kind === 'response' ? `<span class="chip response">${esc(t('responseNote').replace(/\.$/, ''))}</span>`
      : r.attribution_status !== 'undetermined' ? `<span class="chip ${r.attribution_status}">${esc(t('st_' + r.attribution_status))}</span>` : '';
    return `<li><button type="button" class="row" data-id="${esc(r.id)}" aria-current="${r.id === state.selected}">
      <span class="dot" style="background:${CAT_COLOR[r.category]}"></span>
      <span><span class="row-title">${esc(r.vessel || r.title || r.id)}</span>
      <span class="row-meta"><span>${esc(fmtDate(r.date))}</span><span class="sep">·</span><span>${esc(t(r.country))}</span><span class="sep">·</span><span>${esc(t('cat_' + r.category))}</span>${chip}</span></span>
    </button></li>`;
  }).join('') : `<li class="empty">${esc(t('noIncidents'))}</li>`;
  $('incidentList').querySelectorAll('[data-id]').forEach(b => b.onclick = () => select(b.dataset.id, { fly: true }));
  renderMarkers(list);
}
function renderStatements() {
  const list = visibleStatements();
  $('countStatements').textContent = list.length;
  document.querySelectorAll('[data-kind]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.kind === state.kind)));
  const kindLabel = { official: 'kindOfficial', news: 'kindNews', auto: 'kindAuto' };
  $('newsList').innerHTML = list.length ? list.map(raw => {
    const r = localStatement(raw);
    return `<li class="news"><div class="news-meta"><span class="chip ${esc(r.kind)}">${esc(t(kindLabel[r.kind]))}</span><span>${esc(t(r.region))}</span><span>·</span><time datetime="${esc(r.date)}">${esc(fmtDate(r.date))}</time>${r.kind === 'official' && !r.reviewed ? `<span class="chip pending">${esc(t('awaitingReview'))}</span>` : ''}</div>
      <h3>${esc(r.title)}</h3>${r.summary ? `<p>${esc(r.summary)}</p>` : ''}${r.kind === 'auto' ? `<p class="warn">${esc(t('autoNote'))}</p>` : ''}
      <a class="src" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.source || host(r.url))} ↗</a>${r._orig ? `<br><span class="untranslated">${esc(t('untranslated'))}</span>` : ''}</li>`;
  }).join('') : `<li class="empty">${esc(t('noNews'))}</li>`;
}
function renderChart() {
  const months = new Map();
  for (const r of incidents) {
    if (!isIncident(r) || !/^\d{4}-\d{2}/.test(r.date)) continue;
    const k = r.date.slice(0, 7), v = months.get(k) || { Romania: 0, Bulgaria: 0 };
    if (r.country in v) v[r.country]++;
    months.set(k, v);
  }
  if (!months.size) { $('chart').innerHTML = ''; return; }
  const keys = [...months.keys()].sort();
  let [y, m] = keys[0].split('-').map(Number);
  const end = new Date(), series = [];
  while ((y < end.getUTCFullYear() || (y === end.getUTCFullYear() && m <= end.getUTCMonth() + 1)) && series.length < 240) {
    const k = `${y}-${String(m).padStart(2, '0')}`;
    series.push([k, months.get(k) || { Romania: 0, Bulgaria: 0 }]);
    if (++m > 12) { m = 1; y++; }
  }
  const max = Math.max(1, ...series.map(([, v]) => v.Romania + v.Bulgaria));
  const monthName = k => new Date(k + '-15T12:00:00Z').toLocaleDateString(LOCALE[state.lang], { month: 'long', year: 'numeric' });
  $('chart').innerHTML = series.map(([k, v], i) => {
    const label = `${monthName(k)}: ${t('Romania')} ${v.Romania}, ${t('Bulgaria')} ${v.Bulgaria}`;
    const yr = k.endsWith('-01') || i === 0 ? `<span class="yr">${k.slice(0, 4)}</span>` : '';
    return `<div class="bar" title="${esc(label)}"><span class="r" style="height:${v.Romania / max * 100}%"></span><span class="b" style="height:${v.Bulgaria / max * 100}%"></span>${yr}</div>`;
  }).join('');
  $('chart').setAttribute('aria-label', t('chartTitle'));
  $('chart').scrollLeft = $('chart').scrollWidth;
}

/* ---------- map ---------- */
function initMap() {
  if (typeof L === 'undefined') { $('map').innerHTML = `<div class="map-msg">${esc(t('mapUnavailable'))}</div>`; return; }
  map = L.map('map', { zoomControl: false, worldCopyJump: false, minZoom: 5 }).setView(DEFAULT_VIEW.center, DEFAULT_VIEW.zoom);
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(map);
}
function markerStyle(r, active) {
  const resp = r.category === 'mine_action';
  return { radius: active ? 11 : 7, color: active ? '#ffffff' : resp ? CAT_COLOR.mine_action : '#ffffff', weight: active ? 3 : 2, fillColor: CAT_COLOR[r.category], fillOpacity: resp ? 0.15 : 0.95 };
}
function renderMarkers(list) {
  if (!map) return;
  markers.forEach(m => m.remove()); markers.clear();
  const seen = new Map();
  for (const r of list.filter(mappable)) {
    // Spread exactly overlapping markers slightly so each one stays clickable.
    const key = r.lat.toFixed(3) + ',' + r.lon.toFixed(3), n = seen.get(key) || 0; seen.set(key, n + 1);
    const pos = n ? [r.lat + 0.04 * Math.sin(n * 2.1), r.lon + 0.05 * Math.cos(n * 2.1)] : [r.lat, r.lon];
    const m = L.circleMarker(pos, markerStyle(r, r.id === state.selected)).addTo(map);
    m.bindTooltip(esc(r.vessel || r.title || r.id), { direction: 'top', offset: [0, -8], className: 'tip' });
    m.on('click', () => select(r.id, { fly: false }));
    markers.set(r.id, m);
  }
  markers.get(state.selected)?.bringToFront();
}
function fitAll() {
  if (!map) return;
  const pts = visibleIncidents().filter(mappable).map(r => [r.lat, r.lon]);
  if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(0.15), { maxZoom: 9 });
  else map.setView(DEFAULT_VIEW.center, DEFAULT_VIEW.zoom);
}

/* ---------- detail card ---------- */
function detailHtml(raw) {
  const r = localIncident(raw);
  const src = (r.sources || []).filter(s => /^https:\/\//.test(s.url || ''));
  const facts = [
    ['vesselType', r.type], ['country', t(r.country)],
    ...(r.flag && !/^(see source|not verified)$/i.test(r.flag) ? [['flag', r.flag]] : []),
    ['category', t('cat_' + r.category)]
  ].filter(([, v]) => v);
  return `<header class="d-head">
      <span class="d-cat" style="color:${CAT_COLOR[r.category]}"><i style="background:${CAT_COLOR[r.category]}"></i>${esc(t('cat_' + r.category))}</span>
      <h2 id="detailTitle">${esc(r.vessel || r.title || r.id)}</h2>
      <div class="d-sub">${esc(fmtDate(r.date))}${r.location ? ' · ' + esc(r.location) : ''}</div>
    </header>
    <div class="d-body">
      <dl class="facts">${facts.map(([k, v]) => `<div><dt>${esc(t(k))}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>
      ${r.event_kind === 'response' ? `<div class="d-callout">${esc(t('responseNote'))}</div>` : ''}
      <section class="d-section"><h3>${esc(t('overview'))}</h3><p>${esc(r.summary || '—')}</p>${r._orig ? `<span class="untranslated">${esc(t('untranslated'))}</span>` : ''}</section>
      <section class="d-section"><div class="d-status"><h3>${esc(t('attribution'))}</h3><span class="chip ${r.attribution_status}">${esc(t('st_' + r.attribution_status))}</span></div>${r.attribution_details ? `<p>${esc(r.attribution_details)}</p>` : ''}</section>
      <section class="d-section"><h3>${esc(t('precision'))}</h3><p>${esc(r.locationPrecision || r.location_precision || t('approx'))}</p>${mappable(r) ? '' : `<div class="d-callout">${esc(t('archiveOnly'))}</div>`}</section>
      <section class="d-section"><h3>${esc(t('sources'))}</h3><ul class="d-sources">${src.map(s => `<li><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"><span>${esc(s.label || host(s.url))}</span><small>${esc(host(s.url))} ↗</small></a></li>`).join('') || '<li>—</li>'}</ul></section>
      <div class="d-actions"><button type="button" class="btn" id="copyLink"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>${esc(t('permalink'))}</button></div>
    </div>`;
}
let lastFocus = null;
function select(id, { fly = false, push = true } = {}) {
  const r = incidents.find(x => x.id === id);
  if (!r) return;
  const prev = state.selected; state.selected = id;
  if (prev && markers.get(prev)) markers.get(prev).setStyle(markerStyle(incidents.find(x => x.id === prev), false)).setRadius(7);
  const m = markers.get(id);
  if (m) { m.setStyle(markerStyle(r, true)); m.setRadius(11); m.bringToFront(); }
  document.querySelectorAll('.row[aria-current="true"]').forEach(el => el.setAttribute('aria-current', 'false'));
  document.querySelector(`.row[data-id="${CSS.escape(id)}"]`)?.setAttribute('aria-current', 'true');
  if (fly && map && mappable(r)) {
    const z = Math.max(map.getZoom(), 8);
    if (mqMobile.matches) map.setView([r.lat, r.lon], z); else map.flyTo([r.lat, r.lon], z, { duration: 0.6 });
  }
  lastFocus = document.activeElement;
  $('detailBody').innerHTML = detailHtml(r);
  $('detailBody').scrollTop = 0;
  $('detail').hidden = false;
  $('scrim').hidden = !mqMobile.matches;
  $('detail').focus({ preventScroll: true });
  $('copyLink').onclick = copyLink;
  if (push) syncUrl();
}
function closeDetail() {
  if ($('detail').hidden) return;
  const prev = state.selected; state.selected = null;
  if (prev && markers.get(prev)) markers.get(prev).setStyle(markerStyle(incidents.find(x => x.id === prev), false)).setRadius(7);
  document.querySelectorAll('.row[aria-current="true"]').forEach(el => el.setAttribute('aria-current', 'false'));
  $('detail').hidden = true; $('scrim').hidden = true;
  syncUrl();
  if (lastFocus && document.contains(lastFocus)) lastFocus.focus({ preventScroll: true });
}
async function copyLink() {
  const url = new URL(location.href); url.hash = state.selected || '';
  try { await navigator.clipboard.writeText(url.href); toast(t('copied')); } catch { prompt('URL', url.href); }
}
let toastTimer;
function toast(msg) { const el = $('toast'); el.textContent = msg; el.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 1800); }

/* ---------- navigation ---------- */
function syncUrl() {
  const url = new URL(location.href);
  if (state.lang === 'en') url.searchParams.delete('lang'); else url.searchParams.set('lang', state.lang);
  url.hash = state.selected ? encodeURIComponent(state.selected) : '';
  history.replaceState(null, '', url.pathname + url.search + url.hash);
}
function setPane(p) {
  state.pane = p;
  $('app').dataset.pane = p;
  $('paneIncidents').hidden = p !== 'incidents';
  $('paneStatements').hidden = p !== 'statements';
  $('tabIncidents').setAttribute('aria-selected', String(p === 'incidents'));
  $('tabStatements').setAttribute('aria-selected', String(p === 'statements'));
  syncMobileTabs();
}
function setView(v) {
  state.view = v; $('app').dataset.view = v; syncMobileTabs();
  if (v === 'map' && map) requestAnimationFrame(() => map.invalidateSize());
}
function syncMobileTabs() {
  const active = state.view === 'map' ? 'map' : state.pane;
  document.querySelectorAll('[data-mtab]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mtab === active)));
}
async function setLang(lang) {
  if (!LANGS.includes(lang)) return;
  state.lang = lang; store.set('bsm-lang', lang);
  dict = await getJson(`i18n/${lang}.json`, dict);
  renderAll();
  if (state.selected) select(state.selected, { push: false });
  syncUrl();
}
function renderAll() { renderStatic(); renderKpis(); renderIncidents(); renderStatements(); renderChart(); }

function bind() {
  document.querySelectorAll('[data-lang]').forEach(b => b.onclick = () => setLang(b.dataset.lang));
  document.querySelectorAll('[data-pane-btn]').forEach(b => b.onclick = () => setPane(b.dataset.paneBtn));
  document.querySelectorAll('[data-mtab]').forEach(b => b.onclick = () => {
    if (b.dataset.mtab === 'map') setView('map'); else { setPane(b.dataset.mtab); setView('list'); }
  });
  document.querySelectorAll('[data-period]').forEach(b => b.onclick = () => { state.period = b.dataset.period; renderIncidents(); });
  document.querySelectorAll('[data-kind]').forEach(b => b.onclick = () => { state.kind = b.dataset.kind; renderStatements(); });
  $('fCategory').onchange = e => { state.category = e.target.value; renderIncidents(); };
  $('fCountry').onchange = e => { state.country = e.target.value; renderIncidents(); };
  $('fStatus').onchange = e => { state.status = e.target.value; renderIncidents(); };
  $('fRegion').onchange = e => { state.region = e.target.value; renderStatements(); };
  let timer; $('fSearch').oninput = e => { clearTimeout(timer); timer = setTimeout(() => { state.search = e.target.value; renderIncidents(); }, 120); };
  $('resetFilters').onclick = () => {
    Object.assign(state, { period: 'all', category: 'all', country: 'all', status: 'all', search: '' });
    $('fSearch').value = ''; $('fCategory').value = $('fCountry').value = $('fStatus').value = 'all';
    renderIncidents(); fitAll();
  };
  $('fitMap').onclick = fitAll;
  $('detailClose').onclick = closeDetail;
  $('scrim').onclick = closeDetail;
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail(); });
  window.addEventListener('hashchange', () => {
    const id = decodeURIComponent(location.hash.slice(1));
    if (id && id !== state.selected && incidents.some(r => r.id === id)) select(id, { fly: true, push: false });
    else if (!id) closeDetail();
  });
  mqMobile.addEventListener('change', () => {
    if (!$('detail').hidden) $('scrim').hidden = !mqMobile.matches;
    if (map) requestAnimationFrame(() => map.invalidateSize());
  });
}

async function init() {
  bind();
  setPane('incidents');
  const [inc, st, ibg, iro, sbg, sro, upd, d] = await Promise.all([
    getJson('data/incidents.json', null), getJson('data/statements.json', []),
    getJson('data/incidents.bg.json', []), getJson('data/incidents.ro.json', []),
    getJson('data/statements.bg.json', []), getJson('data/statements.ro.json', []),
    getJson('data/updated.json', {}), getJson(`i18n/${state.lang}.json`, null)
  ]);
  dict = d || await getJson('i18n/en.json', {});
  if (!Array.isArray(inc)) {
    renderStatic();
    $('incidentList').innerHTML = `<li class="empty">${esc(t('dataError'))}</li>`;
    return;
  }
  incidents = inc.map(normIncident).filter(r => COUNTRIES.includes(r.country)).sort((a, b) => b.date.localeCompare(a.date));
  statements = rows(st).map(normStatement);
  tr.incidents.bg = new Map(rows(ibg).filter(r => r?.id).map(r => [r.id, r]));
  tr.incidents.ro = new Map(rows(iro).filter(r => r?.id).map(r => [r.id, r]));
  const smap = v => new Map(rows(v).flatMap(r => [[r.url, r], [r.id, r]].filter(x => x[0])));
  tr.statements.bg = smap(sbg); tr.statements.ro = smap(sro);
  updated = upd || {};
  const id = decodeURIComponent(location.hash.slice(1));
  initMap();
  renderAll();
  syncUrl();
  if (id && incidents.some(r => r.id === id)) select(id, { fly: true, push: false });
}
init().catch(err => { console.error(err); $('incidentList').innerHTML = `<li class="empty">${esc(t('dataError'))}</li>`; });
