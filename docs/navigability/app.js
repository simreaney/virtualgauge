// Navigability index of a river basin: draws the pre-processed river network (data/<region>.json, written by
// tools/build_navigability_site.py), then asks Hydrocron for the SWOT levels measured since that snapshot.
// The basin is the page's <html data-region="…">: index.html is the Congo, amazon.html the Amazon.
// In English or French (i18n.js); the index on the map can be saved as a GeoPackage for QGIS (gpkg.js).
import { DAY, parseLevels, screen, judge, indexAt, unpack } from "./core.js";
import { pickLanguage, saveLanguage, translator } from "./i18n.js";
import { navigabilityLayers, writeGeoPackage } from "./gpkg.js";

const WORKERS = 8;                 // requests to Hydrocron at the same time (as the Python package)
const OVERLAP_DAYS = 10;           // re-read the last days before the snapshot: SWOT levels can arrive late
const KEEP_DAYS = 75;              // never ask for more than this
const FRESH_HOURS = 6;             // a reach checked less than this long ago is not asked again
const FIELDS = "reach_id,time_str,wse,reach_q,xovr_cal_q,dark_frac";
const REGION = document.documentElement.dataset.region || "congo";

const $ = (id) => document.getElementById(id);
// Every text from the data (river and port names, reach IDs) goes through esc() before it is put into HTML
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const endOfToday = () => Math.floor(Date.now() / 1000 / DAY) * DAY + DAY - 1;

// the words and number formats of the chosen language
let lang, t, int, metres, percent, dayFmt, shortFmt, clockFmt, attribution = "";
function setLanguage(l) {
  lang = l;
  t = translator(l, REGION);
  const locale = t("locale");
  int = new Intl.NumberFormat(locale);
  metres = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  percent = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 0 });
  dayFmt = new Intl.DateTimeFormat(locale, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  shortFmt = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  clockFmt = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" });
}
const day = (s) => dayFmt.format(new Date(s * 1000));
const shortDay = (s) => shortFmt.format(new Date(s * 1000));
const m = (v) => `${metres.format(v)} m`;
const pct = (v) => percent.format(v / 100);
const riverName = (r) => (r.river === "—" ? t("unnamed") : r.river);

let data, P, reaches, byId, map, lines, halo, selected = null, zoomScale = 1, colours = {};
const now = endOfToday();

// ---------------------------------------------------------------------------------------------- data
/** Has the reach a level that was not in the snapshot? */
const isNew = (r) => r.live && r.now.t != null && !r.saved.some((l) => l[0] === r.now.t);

function rate(r) {
  r.now = r.why ? { index: null, band: -1, why: r.why } : indexAt(r.levels, r.low, r.high, now, P.max_age_days);
}

// ---------------------------------------------------------------------------------------------- words on the page
/** The fixed words of the page (data-i18n: text, data-i18n-html: trusted markup, data-i18n-aria: label). */
function words() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nAria)));
  document.querySelector('meta[name="description"]').content = t("description");
  document.querySelectorAll(".lang button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
  if (!data) { document.title = t("title"); return; }
  const name = data.name[lang];
  $("date").textContent = `${name}, ${day(now)}`;
  document.title = t("titleDated", { name, date: day(now) });
  $("about-data").textContent = t("aboutData", {
    first: day(Date.parse(data.first) / 1000), last: day(data.as_of_t), days: P.max_age_days,
    n: int.format(reaches.filter((r) => !r.why).length), total: int.format(reaches.length) });
  if (map) {
    map.attributionControl.removeAttribution(attribution);
    attribution = t("attribution");
    map.attributionControl.addAttribution(attribution);
  }
}

function switchLanguage(l) {
  if (l === lang) return;
  setLanguage(l);
  saveLanguage(l);
  const url = new URL(location.href);
  if (url.searchParams.has("lang")) { url.searchParams.set("lang", l); history.replaceState(null, "", url); }
  words();
  if (!data) return;
  summary();
  reachPanel();
  update.report();
}

// ---------------------------------------------------------------------------------------------- map
function readColours() {
  colours = { bands: [0, 1, 2, 3, 4].map((b) => css(`--b${b}`)), none: css("--none") };
}
const colourOf = (r) => (r.now.band >= 0 ? colours.bands[r.now.band] : colours.none);
function weightOf(r) {
  if (r.now.band < 0) return 1 * zoomScale;
  const w = 0.5 + Math.log10(Math.max(r.width || 100, 50) / 50);
  return (Math.min(Math.max(w, 0.6), 3) + 0.6) * zoomScale;
}
const styleOf = (r) => ({ color: colourOf(r), weight: weightOf(r), opacity: 1 });
const latlngs = (r) => {
  const out = [];
  for (let k = 0; k < r.line.length; k += 4) out.push([[r.line[k + 1], r.line[k]], [r.line[k + 3], r.line[k + 2]]]);
  return out;
};

function drawMap(countries) {
  const bounds = L.latLngBounds(reaches.map((r) => [r.lat, r.lon]));
  map = L.map("map", { preferCanvas: true, zoomControl: false, zoomSnap: 0.25, minZoom: 4, maxZoom: 13,
                       maxBounds: bounds.pad(0.6), renderer: L.canvas({ tolerance: 7, padding: 0.4 }) });
  map.attributionControl.setPrefix('<a href="https://leafletjs.com" rel="noopener">Leaflet</a>');
  attribution = t("attribution");
  map.attributionControl.addAttribution(attribution);
  L.control.zoom({ position: "topright" }).addTo(map);
  L.control.scale({ position: "bottomright", imperial: false }).addTo(map);
  map.fitBounds(bounds, { padding: [24, 24] });
  zoomScale = scaleFor(map.getZoom());

  map.createPane("land").style.zIndex = 250;
  L.geoJSON(countries, { pane: "land", renderer: L.svg({ pane: "land" }), interactive: false, className: "land" }).addTo(map);

  lines = L.featureGroup().addTo(map);
  const order = [...reaches].sort((a, b) => (a.now.band >= 0) - (b.now.band >= 0) || (a.width || 0) - (b.width || 0));
  for (const r of order) {                                        // narrow rivers first, wide ones on top
    r.layer = r.line.length ? L.polyline(latlngs(r), styleOf(r))
                            : L.circleMarker([r.lat, r.lon], { ...styleOf(r), radius: 2, fill: true, fillOpacity: 1 });
    r.layer.reach = r;
    lines.addLayer(r.layer);
  }
  lines.bindTooltip((layer) => tip(layer.reach), { sticky: true, direction: "top", offset: [0, -6] });
  lines.on("click", (e) => { L.DomEvent.stopPropagation(e); select(e.propagatedFrom.reach); });
  lines.on("mouseover", (e) => e.propagatedFrom.setStyle({ weight: weightOf(e.propagatedFrom.reach) + 2.5 }));
  lines.on("mouseout", (e) => e.propagatedFrom.setStyle({ weight: weightOf(e.propagatedFrom.reach) }));
  map.on("click", () => select(null));
  map.on("zoomend", () => {
    const s = scaleFor(map.getZoom());
    if (s === zoomScale) return;
    zoomScale = s;
    for (const r of reaches) r.layer.setStyle({ weight: weightOf(r) });
    drawHalo();
  });

  map.createPane("halo").style.zIndex = 420;
  map.getPane("halo").style.pointerEvents = "none";
  halo = L.layerGroup().addTo(map);

  map.createPane("ports").style.zIndex = 450;
  const svg = L.svg({ pane: "ports" });
  const ports = data.ports.map((p) =>
    L.circleMarker([p.lat, p.lon], { pane: "ports", renderer: svg, radius: 4.5, className: "port", fillOpacity: 1 })
      .bindTooltip(esc(p.name), { permanent: true, direction: "right", offset: [6, -1], className: "port-label" })   // Leaflet sets it as HTML
      .on("click", (e) => { L.DomEvent.stopPropagation(e); select(byId.get(p.reach_id), true); })
      .addTo(map));
  placeNames(ports);
  map.on("zoomend", () => placeNames(ports));
  basemaps(countries);
}

/** Each port's name to the right of it, or else to the left, above or below, where it covers no other name or port.
 *  Where it would cover one on every side, the name is hidden until the map is zoomed in (the port can still be
 *  selected). Ports earlier in the list first. */
const SIDES = { right: [6, -1], left: [-6, -1], top: [0, -4], bottom: [0, 4] };
function placeNames(ports) {
  const clash = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
  const dots = ports.map((m) => m.getElement().getBoundingClientRect());
  const taken = [];
  ports.forEach((m, i) => {
    const label = m.getTooltip();
    let box = null;
    for (const [side, offset] of Object.entries(SIDES)) {
      Object.assign(label.options, { direction: side, offset });
      label.update();
      const b = label.getElement().getBoundingClientRect();
      if (!taken.some((o) => clash(b, o)) && !dots.some((d, j) => j !== i && clash(b, d))) { box = b; break; }
    }
    if (box) taken.push(box);
    label.getElement().style.visibility = box ? "" : "hidden";
  });
}

const scaleFor = (z) => Math.min(Math.max(1.22 ** (z - 5.5), 0.8), 3.2);

function tip(r) {
  const n = r.now;
  const value = n.band >= 0 ? t("tipIndex", { index: Math.round(n.index) }) : t("noIndex");
  return `<b>${esc(riverName(r))}</b> · ${value}`;
}

function basemaps() {
  const tiles = {
    streets: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                         { maxZoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright" rel="noopener">OpenStreetMap</a>' }),
    satellite: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                           { maxZoom: 19, attribution: "Imagery: Esri, Maxar, Earthstar Geographics" }),
  };
  const buttons = document.querySelectorAll(".basemap button");
  buttons.forEach((b) => b.addEventListener("click", () => {
    buttons.forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    Object.values(tiles).forEach((layer) => layer.remove());
    const layer = tiles[b.dataset.base];
    if (layer) layer.addTo(map);
    $("map").classList.toggle("tiles", Boolean(layer));
  }));
}

function restyle(r) {
  r.layer.setStyle(styleOf(r));
  if (r.now.band >= 0) r.layer.bringToFront();
}

function drawHalo() {
  halo.clearLayers();
  if (!selected) return;
  const r = selected, w = weightOf(r);
  const svg = L.svg({ pane: "halo" });
  const shape = (o) => (r.line.length ? L.polyline(latlngs(r), o) : L.circleMarker([r.lat, r.lon], { ...o, radius: 3 }));
  halo.addLayer(shape({ pane: "halo", renderer: svg, interactive: false, className: "halo", weight: w + 7, opacity: 1 }));
  halo.addLayer(shape({ pane: "halo", renderer: svg, interactive: false, color: colourOf(r), weight: w + 2.5, opacity: 1 }));
}

// ---------------------------------------------------------------------------------------------- side panel
function summary() {
  const has = reaches.filter((r) => r.now.band >= 0);
  const count = [0, 0, 0, 0, 0], km = [0, 0, 0, 0, 0];
  for (const r of has) { count[r.now.band]++; km[r.now.band] += r.km; }
  const total = km.reduce((a, b) => a + b, 0) || 1;
  const sorted = has.map((r) => r.now.index).sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  const median = sorted.length ? (sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2) : null;
  $("s-median").textContent = median == null ? "–" : Math.round(median);
  $("s-low").textContent = pct(Math.round(100 * (km[0] + km[1]) / total));
  $("s-high").textContent = pct(Math.round(100 * (km[3] + km[4]) / total));

  const share = $("share");
  if (!share.children.length) share.innerHTML = "<span></span>".repeat(5);
  [...share.children].forEach((el, b) => {
    el.style.cssText = `flex: ${km[b] / total} 1 0; background: var(--b${b})`;
    el.title = t("shareTitle", { band: data.bands[b].label[lang], pct: pct(Math.round(100 * km[b] / total)) });
  });
  const rows = [4, 3, 2, 1, 0].map((b) => `<tr><td><span class="swatch" style="background:var(--b${b})"></span>${esc(data.bands[b].label[lang])}</td>
    <td class="num">${int.format(count[b])}</td><td class="num">${pct(Math.round(100 * km[b] / total))}</td></tr>`);
  rows.push(`<tr class="none"><td><span class="swatch" style="background:var(--none)"></span>${esc(data.no_index[lang])}</td>
    <td class="num">${int.format(reaches.length - has.length)}</td><td class="num"></td></tr>`);
  $("bands").tBodies[0].innerHTML = rows.join("");

  $("ports").innerHTML = data.ports.map((p) => {
    const n = byId.get(p.reach_id).now;
    const meter = n.band >= 0 ? `<i style="left:${n.index}%;background:var(--b${n.band})"></i>` : "";
    return `<li><button data-reach="${esc(p.reach_id)}" aria-current="${selected?.id === p.reach_id}">
      <span><span class="port-name">${esc(p.name)}</span><span class="port-river">${esc(p.river)}</span></span>
      <span class="meter">${meter}</span><span class="port-index">${n.band >= 0 ? Math.round(n.index) : "–"}</span></button></li>`;
  }).join("");
}

function reachPanel() {
  const box = $("reach");
  box.hidden = !selected;
  if (!selected) return;
  const r = selected, n = r.now;
  const port = data.ports.find((p) => p.reach_id === r.id);
  const name = riverName(r);
  const title = port ? `${esc(port.name)} <span class="soft">· ${esc(port.river)}</span>` : esc(name);
  let html = `<p class="reach-title">${title}</p><p class="reach-sub">${t("reachSub", { id: esc(r.id) })}${port && port.river !== name ? ` · ${esc(name)}` : ""}</p>`;
  if (n.band >= 0) {
    html += `<div class="reach-index"><b>${Math.round(n.index)}</b>
      <span class="chip"><i style="background:var(--b${n.band})"></i>${esc(data.bands[n.band].label[lang].replace(/^[\d–]+ /, ""))}</span></div>`;
  } else {
    html += `<p class="note">${esc(t(`why.${n.why}`, { days: P.max_age_days }))}.</p>`;
  }
  if (r.low != null && r.high != null) {
    const at = n.t != null ? Math.min(Math.max(100 * (n.wse - r.low) / (r.high - r.low), 0), 100) : null;
    html += `<div class="gauge"><div class="gauge-track">${[0, 1, 2, 3, 4].map((b) => `<span style="background:var(--b${b})"></span>`).join("")}
      ${n.band >= 0 ? `<i style="left:${at}%"></i>` : ""}</div>
      <div class="gauge-ends"><span>${m(r.low)}<small>${t("lowest")} · ${shortDay(r.lowT)}</small></span>
      <span>${m(r.high)}<small>${t("highest")} · ${shortDay(r.highT)}</small></span></div></div>`;
  }
  const facts = [];
  if (n.t != null) {
    const age = Math.max(0, Math.floor(n.age));
    const ago = age === 0 ? t("today") : age === 1 ? t("daysAgo1") : t("daysAgo", { n: age });
    facts.push([t("latest"), `${m(n.wse)} <span class="soft">· ${shortDay(n.t)}, ${ago}</span>`
      + (isNew(r) ? `<span class="tag live">${t("newTag")}</span>` : "")]);
  }
  if (r.low != null && r.high != null) facts.push([t("range"), `${m(r.high - r.low)} <span class="soft">${t("rangeNote")}</span>`]);
  if (r.n) facts.push([t("record"), t("goodLevels", { n: int.format(r.n) })]);
  if (r.width) facts.push([t("width"), t("about_m", { n: int.format(r.width) })]);
  html += `<dl class="facts">${facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>`;
  if (n.band >= 0 && n.raw < 0) html += `<p class="note">${t("newLowest", { m: m(r.low - n.wse) })}</p>`;
  if (n.band >= 0 && n.raw > 100) html += `<p class="note">${t("newHighest", { m: m(n.wse - r.high) })}</p>`;
  if (!r.why && !r.live && update.running) html += `<p class="hint">${t("checkingReach")}</p>`;
  $("reach-body").innerHTML = html;
}

function select(r, fly = false) {
  selected = r || null;
  drawHalo();
  reachPanel();
  document.querySelectorAll("#ports button").forEach((b) => b.setAttribute("aria-current", String(b.dataset.reach === selected?.id)));
  history.replaceState(null, "", selected ? `#reach=${encodeURIComponent(selected.id)}` : location.pathname + location.search);
  if (!selected) return;
  update.first(selected);
  if (fly) map.flyTo([selected.lat, selected.lon], Math.max(map.getZoom(), 7.5), { duration: 0.8 });
}

// ---------------------------------------------------------------------------------------------- GeoPackage
let sqlReady = null, stylesReady = null;

/** sql.js (SQLite in WebAssembly, ~0.7 MB), loaded the first time a file is made */
function loadSql() {
  sqlReady ??= new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = "vendor/sql.js/sql-wasm.js";
    s.onload = () => window.initSqlJs({ locateFile: (f) => `vendor/sql.js/${f}` }).then(ok, fail);
    s.onerror = () => fail(new Error("vendor/sql.js/sql-wasm.js"));
    document.head.append(s);
  });
  return sqlReady;
}

async function download() {
  const button = $("download"), note = $("download-note");
  button.disabled = true;
  note.hidden = false;
  note.textContent = t("downloadBusy");
  try {
    stylesReady ??= getJSON("data/qgis.json");
    const [SQL, styles] = await Promise.all([loadSql(), stylesReady]);
    const bytes = writeGeoPackage(SQL, navigabilityLayers(data, reaches, t, lang, isNew),
                                  [{ table: "reaches", qml: styles.reaches[lang] }, { table: "ports", qml: styles.ports }]);
    const file = `navigability_${data.region}_${new Date(now * 1000).toISOString().slice(0, 10)}.gpkg`;
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/geopackage+sqlite3" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: file });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    const left = reaches.filter((r) => !r.why && !r.live).length;
    note.textContent = t("downloadDone", { file, size: t("mb", { n: (bytes.length / 1e6).toLocaleString(t("locale"), { maximumFractionDigits: 1 }) }) })
      + (left ? ` ${t("downloadPartial", { left: int.format(left), date: day(data.as_of_t) })}` : "");
  } catch (e) {
    sqlReady = null;
    stylesReady = null;
    note.textContent = t("downloadFailed", { error: e.message || e });
    console.error(e);
  } finally {
    button.disabled = false;
  }
}

// ---------------------------------------------------------------------------------------------- live levels
const update = {
  running: false, queue: [], done: 0, total: 0, failed: [], abort: null, cache: {}, dirty: false, strikes: 0,
  key: () => `vg-navigability:${data.region}:${data.as_of_t}`,      // one per basin and snapshot
  start: () => Math.floor(Math.max(data.as_of_t - OVERLAP_DAYS * DAY, now - KEEP_DAYS * DAY) / DAY) * DAY,

  load() {
    try {
      const mine = `vg-navigability:${data.region}:`;                 // an older snapshot of this basin (not the others)
      for (const k of Object.keys(localStorage)) if (k.startsWith(mine) && k !== this.key()) localStorage.removeItem(k);
      this.cache = JSON.parse(localStorage.getItem(this.key())) || {};
    } catch { this.cache = {}; }
  },
  save() {
    try { localStorage.setItem(this.key(), JSON.stringify(this.cache)); } catch { /* private window or full: carry on */ }
  },

  /** Put the new levels of a reach on the map */
  apply(r, fresh) {
    const band = r.now.band;
    r.levels = judge(r.saved, fresh, r, P, this.start());
    r.live = true;
    rate(r);
    if (r.now.band !== band) restyle(r);
    if (r === selected) { drawHalo(); reachPanel(); }
    this.dirty = true;
  },

  async fetch(r, signal) {
    const iso = (s) => new Date(s * 1000).toISOString().slice(0, 19) + "Z";
    const q = new URLSearchParams({ feature: "Reach", feature_id: r.id, output: "csv", start_time: iso(this.start()),
                                    end_time: iso(now), fields: FIELDS });
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const res = await fetch(`${data.hydrocron}?${q}`, { signal });
        if (res.status === 400) return [];                              // Hydrocron answers 400 when there is no data
        if (res.ok) return screen(parseLevels((await res.json()).results.csv), r, P);
      } catch (e) {
        if (e.name === "AbortError") throw e;
      }
      await new Promise((ok) => setTimeout(ok, 1500 * (attempt + 1)));    // busy or offline: wait and try again
    }
    throw new Error("no answer");
  },

  async worker(signal) {
    while (this.running && this.queue.length) {
      const r = this.queue.shift();
      try {
        const fresh = await this.fetch(r, signal);
        this.cache[r.id] = [Math.floor(Date.now() / 1000), fresh];
        this.apply(r, fresh);
        this.strikes = 0;
      } catch (e) {
        if (e.name === "AbortError") { this.queue.unshift(r); return; }
        this.failed.push(r);
        if (++this.strikes >= WORKERS) { this.stop(); return; }           // Hydrocron cannot be reached at all
      }
      this.done++;
    }
  },

  async run(force = false) {
    const targets = reaches.filter((r) => !r.why);
    const ports = new Set(data.ports.map((p) => p.reach_id));
    targets.sort((a, b) => ports.has(b.id) - ports.has(a.id) || (b.width || 0) - (a.width || 0));   // big rivers first
    const fresh = Date.now() / 1000 - FRESH_HOURS * 3600;
    Object.assign(this, { queue: [], done: 0, total: targets.length, failed: [], strikes: 0, running: true });
    for (const r of targets) {
      const hit = force ? null : this.cache[r.id];
      if (hit && hit[0] > fresh) { if (!r.live) this.apply(r, hit[1]); this.done++; } else this.queue.push(r);
    }
    this.go();
  },
  async go() {
    this.running = true;
    this.abort = new AbortController();
    const ticker = setInterval(() => this.report(), 500);
    const saver = setInterval(() => this.save(), 8000);
    this.report();
    await Promise.all(Array.from({ length: WORKERS }, () => this.worker(this.abort.signal)));
    clearInterval(ticker);
    clearInterval(saver);
    this.running = false;
    this.save();
    this.report();
    reachPanel();
  },
  stop() { this.running = false; this.abort?.abort(); },
  first(r) {                                                            // a selected reach jumps the queue
    const k = this.queue.indexOf(r);
    if (k > 0) this.queue.unshift(...this.queue.splice(k, 1));
  },

  report() {
    if (this.dirty) { summary(); this.dirty = false; }
    const dot = $("status-dot"), text = $("status-text"), action = $("status-action"), note = $("status-note");
    const left = this.queue.length, snapshot = day(data.as_of_t);
    const set = (cls, msg, label, fn, extra) => {
      dot.className = `dot ${cls}`;
      text.textContent = msg;
      action.hidden = !label; action.textContent = label || ""; action.onclick = fn || null;
      note.hidden = !extra; note.textContent = extra || "";
      $("progress").hidden = cls !== "busy" && !(left && this.done);
      $("progress-bar").style.width = `${100 * this.done / Math.max(this.total, 1)}%`;
    };
    const changed = reaches.filter(isNew).length;
    const newer = changed === 0 ? t("newerNone", { date: snapshot })
      : changed === 1 ? t("newer1", { date: snapshot }) : t("newer", { n: int.format(changed), date: snapshot });
    const counts = { done: int.format(this.done), total: int.format(this.total) };
    const live = reaches.filter((r) => r.live).length;                  // reaches that did get an answer
    if (this.running) {
      set("busy", t("checking", counts), t("pause"), () => this.stop(), t("checkingNote", { newer }));
    } else if (this.strikes >= WORKERS) {
      set("bad", t("unreachable"), t("retry"), () => { this.queue.unshift(...this.failed); this.failed = []; this.strikes = 0; this.go(); },
          live ? t("unreachableNoteSome", { date: snapshot, n: int.format(live) }) : t("unreachableNote", { date: snapshot }));
    } else if (left) {
      set("", t("paused", counts), t("resume"), () => this.go(), newer);
    } else if (this.failed.length) {
      set("bad", this.failed.length === 1 ? t("failed1") : t("failed", { n: int.format(this.failed.length) }), t("retry"),
          () => { this.queue = this.failed; this.failed = []; this.done = this.total - this.queue.length; this.go(); }, newer);
    } else {
      set("ok", t("upToDate", { time: clockFmt.format(new Date()) }), t("again"), () => this.run(true), newer);
    }
  },
};

// ---------------------------------------------------------------------------------------------- start
async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

async function main() {
  setLanguage(pickLanguage());
  words();
  document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => switchLanguage(b.dataset.lang)));
  let countries;
  try {
    [data, countries] = await Promise.all([getJSON(`data/${REGION}.json`), getJSON(`data/${REGION}_countries.geojson`)]);
  } catch (e) {
    $("status-dot").className = "dot bad";
    $("status-text").textContent = t("loadFailed");
    console.error(e);
    return;
  }
  P = data.params;
  reaches = unpack(data);
  byId = new Map(reaches.map((r) => [r.id, r]));
  reaches.forEach(rate);
  readColours();

  $("scale-bar").innerHTML = [0, 1, 2, 3, 4].map((b) => `<span style="background:var(--b${b})"></span>`).join("");
  drawMap(countries);
  words();
  summary();
  $("ports").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-reach]");
    if (b) select(byId.get(b.dataset.reach), true);
  });
  $("reach-close").addEventListener("click", () => select(null));
  $("download").addEventListener("click", download);
  $("download").disabled = false;
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    readColours();
    reaches.forEach((r) => r.layer.setStyle({ color: colourOf(r) }));
    drawHalo();
  });
  const wanted = byId.get(new URLSearchParams(location.hash.slice(1)).get("reach"));
  if (wanted) select(wanted, true);

  update.load();
  update.run();
}

main();
