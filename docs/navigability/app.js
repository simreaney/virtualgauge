// Navigability index of the Congo basin: draws the pre-processed river network (data/congo.json, written by
// tools/build_navigability_site.py), then asks Hydrocron for the SWOT levels measured since that snapshot.
import { DAY, parseLevels, screen, judge, indexAt } from "./core.js";

const WORKERS = 8;                 // requests to Hydrocron at the same time (as the Python package)
const OVERLAP_DAYS = 10;           // re-read the last days before the snapshot: SWOT levels can arrive late
const KEEP_DAYS = 75;              // never ask for more than this
const FRESH_HOURS = 6;             // a reach checked less than this long ago is not asked again
const FIELDS = "reach_id,time_str,wse,reach_q,xovr_cal_q,dark_frac";
const WHY = {
  "no SWOT data": "No SWOT data for this reach", "not downloaded": "No SWOT data for this reach",
  "never measured": "SWOT has never measured this reach", "too few good levels": "Too few good levels for an index",
  "record too short": "The record is shorter than a year", "range too small": "The range of levels is too small to trust",
  "too noisy": "The levels are too noisy for an index", "no recent level": "No good level in the last 30 days",
};

const $ = (id) => document.getElementById(id);
const int = new Intl.NumberFormat("en-GB");
const dayFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
const shortFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const clockFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });
const day = (t) => dayFmt.format(new Date(t * 1000));
const shortDay = (t) => shortFmt.format(new Date(t * 1000));
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const endOfToday = () => Math.floor(Date.now() / 1000 / DAY) * DAY + DAY - 1;

let data, P, reaches, byId, map, lines, halo, selected = null, zoomScale = 1, colours = {};
const now = endOfToday();

// ---------------------------------------------------------------------------------------------- data
function unpack(d) {
  const r = d.reaches;
  return r.id.map((id, i) => ({
    i, id, river: d.rivers[r.river[i]], lon: r.lon[i], lat: r.lat[i], width: r.width[i], km: r.km[i],
    why: d.why[r.why[i]], n: r.n[i], low: r.low[i], high: r.high[i], lowT: r.low_t[i], highT: r.high_t[i],
    median: r.median[i], far: r.far[i], jump: r.jump[i], saved: r.recent[i], levels: r.recent[i], line: r.line[i],
    live: false, now: null,
  }));
}

/** Has the reach a level that was not in the snapshot? */
const isNew = (r) => r.live && r.now.t != null && !r.saved.some((l) => l[0] === r.now.t);

function rate(r) {
  r.now = r.why ? { index: null, band: -1, why: r.why } : indexAt(r.levels, r.low, r.high, now, P.max_age_days);
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
  map.attributionControl.addAttribution("Levels: SWOT (NASA/CNES) via Hydrocron · rivers: SWORD · borders: Natural Earth");
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
  for (const p of data.ports) {
    L.circleMarker([p.lat, p.lon], { pane: "ports", renderer: svg, radius: 4.5, className: "port", fillOpacity: 1 })
      .bindTooltip(p.name, { permanent: true, direction: "right", offset: [6, -1], className: "port-label" })
      .on("click", (e) => { L.DomEvent.stopPropagation(e); select(byId.get(p.reach_id), true); })
      .addTo(map);
  }
  basemaps(countries);
}

const scaleFor = (z) => Math.min(Math.max(1.22 ** (z - 5.5), 0.8), 3.2);

function tip(r) {
  const n = r.now;
  const value = n.band >= 0 ? `index <b>${Math.round(n.index)}</b>` : "no index";
  return `<b>${esc(r.river === "—" ? "Unnamed river" : r.river)}</b> · ${value}`;
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
    Object.values(tiles).forEach((t) => t.remove());
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
  $("s-low").textContent = `${Math.round(100 * (km[0] + km[1]) / total)}%`;
  $("s-high").textContent = `${Math.round(100 * (km[3] + km[4]) / total)}%`;

  const share = $("share");
  if (!share.children.length) share.innerHTML = "<span></span>".repeat(5);
  [...share.children].forEach((el, b) => {
    el.style.cssText = `flex: ${km[b] / total} 1 0; background: var(--b${b})`;
    el.title = `${data.bands[b].label}: ${Math.round(100 * km[b] / total)}% of river length`;
  });
  const rows = [4, 3, 2, 1, 0].map((b) => `<tr><td><span class="swatch" style="background:var(--b${b})"></span>${esc(data.bands[b].label)}</td>
    <td class="num">${int.format(count[b])}</td><td class="num">${Math.round(100 * km[b] / total)}%</td></tr>`);
  rows.push(`<tr class="none"><td><span class="swatch" style="background:var(--none)"></span>no index</td>
    <td class="num">${int.format(reaches.length - has.length)}</td><td class="num"></td></tr>`);
  $("bands").tBodies[0].innerHTML = rows.join("");

  $("ports").innerHTML = data.ports.map((p) => {
    const n = byId.get(p.reach_id).now;
    const meter = n.band >= 0 ? `<i style="left:${n.index}%;background:var(--b${n.band})"></i>` : "";
    return `<li><button data-reach="${p.reach_id}" aria-current="${selected?.id === p.reach_id}">
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
  const name = r.river === "—" ? "Unnamed river" : r.river;
  const title = port ? `${port.name} <span class="soft">· ${esc(port.river)}</span>` : esc(name);
  const m = (v) => `${v.toFixed(2)} m`;
  let html = `<p class="reach-title">${title}</p><p class="reach-sub">SWOT reach ${r.id}${port && port.river !== name ? ` · ${esc(name)}` : ""}</p>`;
  if (n.band >= 0) {
    html += `<div class="reach-index"><b>${Math.round(n.index)}</b>
      <span class="chip"><i style="background:var(--b${n.band})"></i>${esc(data.bands[n.band].label.replace(/^[\d–]+ /, ""))}</span></div>`;
  } else {
    html += `<p class="note">${esc(WHY[n.why] || n.why)}.</p>`;
  }
  if (r.low != null && r.high != null) {
    const at = n.t != null ? Math.min(Math.max(100 * (n.wse - r.low) / (r.high - r.low), 0), 100) : null;
    html += `<div class="gauge"><div class="gauge-track">${[0, 1, 2, 3, 4].map((b) => `<span style="background:var(--b${b})"></span>`).join("")}
      ${n.band >= 0 ? `<i style="left:${at}%"></i>` : ""}</div>
      <div class="gauge-ends"><span>${m(r.low)}<small>lowest · ${shortDay(r.lowT)}</small></span>
      <span>${m(r.high)}<small>highest · ${shortDay(r.highT)}</small></span></div></div>`;
  }
  const facts = [];
  if (n.t != null) {
    const age = Math.max(0, Math.floor(n.age));
    facts.push(["Latest level", `${m(n.wse)} <span class="soft">· ${shortDay(n.t)}, ${age === 0 ? "today" : `${age} day${age === 1 ? "" : "s"} ago`}</span>`
      + (isNew(r) ? '<span class="tag live">new</span>' : "")]);
  }
  if (r.low != null && r.high != null) facts.push(["Range", `${m(r.high - r.low)} <span class="soft">between lowest and highest</span>`]);
  if (r.n) facts.push(["Record", `${int.format(r.n)} good SWOT levels`]);
  if (r.width) facts.push(["Width", `about ${int.format(r.width)} m`]);
  html += `<dl class="facts">${facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>`;
  if (n.band >= 0 && n.raw < 0) html += `<p class="note">This is the lowest level SWOT has recorded here: ${m(r.low - n.wse)} below the previous lowest.</p>`;
  if (n.band >= 0 && n.raw > 100) html += `<p class="note">This is the highest level SWOT has recorded here: ${m(n.wse - r.high)} above the previous highest.</p>`;
  if (!r.why && !r.live && update.running) html += `<p class="hint">Checking Hydrocron for a newer level…</p>`;
  $("reach-body").innerHTML = html;
}

function select(r, fly = false) {
  selected = r || null;
  drawHalo();
  reachPanel();
  document.querySelectorAll("#ports button").forEach((b) => b.setAttribute("aria-current", String(b.dataset.reach === selected?.id)));
  history.replaceState(null, "", selected ? `#reach=${selected.id}` : location.pathname + location.search);
  if (!selected) return;
  update.first(selected);
  if (fly) map.flyTo([selected.lat, selected.lon], Math.max(map.getZoom(), 7.5), { duration: 0.8 });
}

// ---------------------------------------------------------------------------------------------- live levels
const update = {
  running: false, queue: [], done: 0, total: 0, failed: [], abort: null, cache: {}, dirty: false, strikes: 0,
  key: () => `vg-navigability:${data.region}:${data.as_of_t}`,
  start: () => Math.floor(Math.max(data.as_of_t - OVERLAP_DAYS * DAY, now - KEEP_DAYS * DAY) / DAY) * DAY,

  load() {
    try {
      for (const k of Object.keys(localStorage)) if (k.startsWith("vg-navigability:") && k !== this.key()) localStorage.removeItem(k);
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
    const iso = (t) => new Date(t * 1000).toISOString().slice(0, 19) + "Z";
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
    const newer = changed ? `${int.format(changed)} reach${changed === 1 ? " has" : "es have"} a newer level than the snapshot of ${snapshot}.`
                               : `No level newer than the snapshot of ${snapshot} so far.`;
    if (this.running) {
      set("busy", `Checking SWOT for new levels: ${int.format(this.done)} of ${int.format(this.total)} reaches`, "Pause", () => this.stop(),
          `${newer} The largest rivers are checked first.`);
    } else if (this.strikes >= WORKERS) {
      set("bad", "Hydrocron cannot be reached", "Try again", () => { this.queue.unshift(...this.failed); this.failed = []; this.strikes = 0; this.go(); },
          `The map shows the levels saved on ${snapshot}${this.done ? `, updated for ${int.format(this.done)} reaches` : ""}.`);
    } else if (left) {
      set("", `Paused: ${int.format(this.done)} of ${int.format(this.total)} reaches checked`, "Continue", () => this.go(), newer);
    } else if (this.failed.length) {
      set("bad", `${int.format(this.failed.length)} reach${this.failed.length === 1 ? "" : "es"} could not be checked`, "Try again",
          () => { this.queue = this.failed; this.failed = []; this.done = this.total - this.queue.length; this.go(); }, newer);
    } else {
      set("ok", `Up to date: every reach checked at ${clockFmt.format(new Date())}`, "Check again", () => this.run(true), newer);
    }
  },
};

// ---------------------------------------------------------------------------------------------- start
async function main() {
  const get = async (url) => {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url}: ${res.status}`);
    return res.json();
  };
  let countries;
  try {
    [data, countries] = await Promise.all([get("data/congo.json"), get("data/countries.geojson")]);
  } catch (e) {
    $("status-dot").className = "dot bad";
    $("status-text").textContent = "The river data could not be loaded. Reload the page to try again.";
    console.error(e);
    return;
  }
  P = data.params;
  reaches = unpack(data);
  byId = new Map(reaches.map((r) => [r.id, r]));
  reaches.forEach(rate);
  readColours();

  $("date").textContent = `${data.name}, ${day(now)}`;
  document.title = `${data.name} navigability, ${day(now)}`;
  $("scale-bar").innerHTML = [0, 1, 2, 3, 4].map((b) => `<span style="background:var(--b${b})"></span>`).join("");
  $("about-data").textContent = `The lowest and highest levels come from every good SWOT level between ${day(Date.parse(data.first) / 1000)} `
    + `and ${day(data.as_of_t)} (${int.format(reaches.filter((r) => !r.why).length)} of ${int.format(reaches.length)} reaches have a record good enough for an index). `
    + `Your browser then asks NASA's Hydrocron service for the levels measured since, and judges them with the same quality rules. `
    + `A reach needs a good level from the last ${P.max_age_days} days to be coloured.`;

  drawMap(countries);
  summary();
  $("ports").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-reach]");
    if (b) select(byId.get(b.dataset.reach), true);
  });
  $("reach-close").addEventListener("click", () => select(null));
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
