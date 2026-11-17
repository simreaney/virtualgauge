// The rules of the navigability index, as in src/virtualgauge/navigation.py (clean_levels, _spikes, index_at).
// No page or network code here, so the same file is checked against the Python package by tests/test_navigability_site.py.

export const DAY = 86400;

/** Hydrocron CSV -> rows {t (s since 1970), wse (m), reach_q, xovr_cal_q, dark_frac}; fill values are dropped. */
export function parseLevels(csv) {
  const lines = (csv || "").trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const col = Object.fromEntries(lines[0].split(",").map((name, i) => [name.trim(), i]));
  const rows = [];
  for (const line of lines.slice(1)) {
    const c = line.split(",");
    const t = Date.parse(c[col.time_str]) / 1000;
    const wse = Number(c[col.wse]);
    if (!Number.isFinite(t) || !Number.isFinite(wse) || wse <= -1e10) continue;
    rows.push({ t: Math.floor(t), wse: Math.round(wse * 1000) / 1000, reach_q: Number(c[col.reach_q]),
                xovr_cal_q: Number(c[col.xovr_cal_q]), dark_frac: Number(c[col.dark_frac]) });
  }
  return rows.sort((a, b) => a.t - b.t);
}

/** Rows -> [[t, wse], ...] that pass the quality flags and are not far from the reach's other levels. */
export function screen(rows, reach, params) {
  const out = [];
  let last = null;
  for (const r of rows) {
    if (r.t === last) continue;                                            // duplicate
    last = r.t;
    if (r.reach_q > params.max_reach_q || r.xovr_cal_q > params.max_xovr_q) continue;
    if (r.dark_frac > params.max_dark_frac) continue;
    if (reach.median != null && Math.abs(r.wse - reach.median) > reach.far) continue;
    out.push([r.t, r.wse]);
  }
  return out;
}

function median(values) {
  const v = [...values].sort((a, b) => a - b);
  const m = v.length >> 1;
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

/** Which levels jump away from the levels around them in time (true = spike). levels = [[t, wse], ...] by time. */
export function spikes(levels, limit, jumpDays, maxK = 3) {
  const n = levels.length;
  const bad = new Array(n).fill(false);
  if (n < 3) return bad;
  const tt = levels.map((l) => l[0] / DAY);
  const h = levels.map((l) => l[1]);
  for (let i = 0; i < n; i++) {
    let near = 0;
    for (let j = 0; j < n; j++) if (Math.abs(tt[j] - tt[i]) <= jumpDays) near++;
    const win = near > 1 ? jumpDays : 2 * jumpDays;
    let nb = 0, na = 0;
    for (let j = 0; j < n; j++) {
      const dt = tt[j] - tt[i];
      if (dt < 0 && -dt <= win) nb++;
      if (dt > 0 && dt <= win) na++;
    }
    const k = Math.min(nb, na, maxK);
    let ref = NaN;
    if (k >= 1) {
      ref = median(h.slice(i - k, i + k + 1));                             // neighbours on both sides
    } else {
      for (const [side, count] of [[-1, nb], [1, na]]) {                   // first or latest level: one side only
        if (count < 1 || !Number.isNaN(ref)) continue;
        const i1 = i + side;
        const i2 = Math.min(Math.max(i + 2 * side, 0), n - 1);
        const trend = tt[i1] !== tt[i2] ? h[i1] + (h[i1] - h[i2]) * (tt[i] - tt[i1]) / (tt[i1] - tt[i2]) : h[i1];
        ref = count >= 2 ? (h[i1] + trend) / 2 : h[i1];
      }
    }
    bad[i] = Math.abs(h[i] - ref) > (k >= 1 ? limit : 2 * limit);
  }
  return bad;
}

/** The good levels of a reach: its saved ones before `start`, then the new ones that are not spikes. */
export function judge(saved, fresh, reach, params, start) {
  const context = saved.filter((l) => l[0] < start);
  const all = context.concat(fresh.filter((l) => l[0] >= start));
  const bad = spikes(all, reach.jump, params.jump_days);
  return all.filter((_, i) => i < context.length || !bad[i]);
}

export function bandOf(index) {
  return Number.isFinite(index) ? Math.min(Math.max(Math.floor(index / 20), 0), 4) : -1;
}

/** The index at time `now` from the latest good level, if it is at most maxAgeDays old. */
export function indexAt(levels, low, high, now, maxAgeDays) {
  let last = null;
  for (const l of levels) if (l[0] <= now) last = l;
  if (!last) return { index: null, band: -1, why: "no recent level" };
  const age = (now - last[0]) / DAY;
  const out = { t: last[0], wse: last[1], age };
  if (age > maxAgeDays) return { ...out, index: null, band: -1, why: "no recent level" };
  const raw = 100 * (last[1] - low) / (high - low);
  const index = Math.min(Math.max(raw, 0), 100);
  return { ...out, raw, index, band: bandOf(index), why: "" };
}

/** The reaches of the data file (docs/navigability/data/congo.json, column by column) as one object per reach. */
export function unpack(d) {
  const r = d.reaches;
  return r.id.map((id, i) => ({
    i, id, river: d.rivers[r.river[i]], lon: r.lon[i], lat: r.lat[i], width: r.width[i], km: r.km[i],
    why: d.why[r.why[i]], n: r.n[i], low: r.low[i], high: r.high[i], lowT: r.low_t[i], highT: r.high_t[i],
    median: r.median[i], far: r.far[i], jump: r.jump[i], saved: r.recent[i], levels: r.recent[i], line: r.line[i],
    live: false, now: null,
  }));
}
