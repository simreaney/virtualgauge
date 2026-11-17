"""Write the data file of the navigability web page (docs/navigability/), a static site for GitHub Pages.

Usage: python tools/build_navigability_site.py [cache folder] [--no-download]     (default cache: ./cache)

The page shows the navigability index of every SWOT reach of the Congo basin. This tool does the slow part once:
it downloads (or updates) the whole SWOT record, cleans it and writes, for every reach, its place on the map, the
lowest and highest level recorded, and what the page needs to judge new levels with the same rules as the package
(docs/navigability/data/congo.json, about 1 MB). The page then asks Hydrocron only for the levels since this
snapshot, so it stays up to date without being rebuilt. Rebuild now and then, so the ranges include new extremes.
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import virtualgauge as vg                                   # noqa: E402
from virtualgauge import navigation, store                  # noqa: E402
from virtualgauge import geopackage                         # noqa: E402
from virtualgauge.i18n import _pair                         # noqa: E402

SITE = ROOT / "docs" / "navigability"
WHY = ["", "no SWOT data", "not downloaded", "never measured", "too few good levels", "record too short",
       "range too small", "too noisy"]
N_RECENT = 8            # good levels kept per reach: the latest one is shown at once, the others judge new levels


def _secs(s):
    """Times as whole seconds since 1970 (None where missing)"""
    v = pd.to_datetime(s).astype("datetime64[s]").astype("int64")
    return [None if pd.isna(x) else int(i) for x, i in zip(s, v)]


def _num(s, nd):
    return [None if not np.isfinite(x) else round(float(x), nd) for x in np.asarray(s, float)]


def build(survey):
    p, tab, lv = survey.params, survey.table.reset_index(drop=True), survey.levels
    ids = tab.reach_id.to_numpy()

    # the limits used to judge a new level, exactly as navigation.clean_levels computes them
    q_ok = lv[lv.reason.isin(["kept", "5 far from other levels", "6 spike"])].groupby("reach_id").wse
    median = q_ok.median().reindex(ids)
    far = (p.k_mad * np.maximum(q_ok.agg(navigation.robust_spread), p.min_spread_m)).reindex(ids)
    before_spikes = lv[lv.reason.isin(["kept", "6 spike"])]
    noise = navigation.pass_noise(before_spikes, p.noise_days).reindex(ids)
    jump = np.maximum(p.jump_m, p.jump_k * noise).fillna(2 * p.jump_m)

    kept = lv[lv.reason == "kept"].sort_values(["reach_id", "time"])
    tail = kept.groupby("reach_id").tail(N_RECENT)
    tail = tail.assign(s=tail.time.astype("datetime64[s]").astype("int64"))
    recent = {rid: [[int(a), round(float(b), 3)] for a, b in zip(g.s, g.wse)] for rid, g in tail.groupby("reach_id")}

    seg, lone = survey._network()
    lines = {rid: g[["x0", "y0", "x1", "y1"]].round(4).to_numpy().ravel().tolist() for rid, g in seg.groupby("reach_id")}

    rivers = sorted(set(tab.river_name))
    river_i = {r: i for i, r in enumerate(rivers)}
    km = tab.length_km.fillna(tab.length_km.median())
    reaches = {
        "id": [str(r) for r in ids],
        "river": [river_i[r] for r in tab.river_name],
        "lon": _num(tab.lon, 4), "lat": _num(tab.lat, 4),
        "width": [None if not np.isfinite(w) or w <= 0 else int(round(w)) for w in tab.width_m],
        "km": _num(km, 1),
        "why": [WHY.index(w) for w in tab.why],
        "n": [int(n) for n in tab.n_good],
        "low": _num(tab.low_m, 3), "high": _num(tab.high_m, 3),
        "low_t": _secs(tab.low_date), "high_t": _secs(tab.high_date),
        "median": _num(median, 3), "far": _num(far, 3), "jump": _num(jump, 3),
        "recent": [recent.get(r, []) for r in ids],
        "line": [lines.get(r, []) for r in ids],
    }
    return {
        "name": _both(survey.name), "region": survey.key,
        "as_of": f"{survey.as_of:%Y-%m-%d}", "as_of_t": int(survey.as_of.timestamp()),
        "first": f"{kept.time.min():%Y-%m-%d}",
        "source": "SWOT L2 HR RiverSP reach, Version D (NASA/CNES, PO.DAAC), via Hydrocron",
        "hydrocron": vg.download.HYDROCRON,
        "params": {k: getattr(p, k) for k in ("max_reach_q", "max_xovr_q", "max_dark_frac", "jump_days", "max_age_days")},
        "bands": [{"from": lo, "label": _both_key(key), "colour": c} for lo, key, c in navigation.BANDS],
        "no_index": _both_key("nv_no_index"), "no_index_colour": navigation.NO_INDEX_C,
        "why": WHY, "rivers": rivers,
        "ports": [{**port, "reach_id": str(port["reach_id"])} for port in survey._ports()],
        "reaches": reaches,
    }


def _both_key(key):
    """A message in English and French: {"en": …, "fr": …} (the page shows one, src/virtualgauge/messages.py has both)"""
    return dict(zip(("en", "fr"), _pair(key, {})))


def _both(text):
    return dict(zip(("en", "fr"), text.pair() if hasattr(text, "pair") else (str(text), str(text))))


def qgis_styles():
    """The QGIS styles the page puts into its GeoPackage, as the package writes them (band names in each language)"""
    reaches = {}
    for lang in ("en", "fr"):
        vg.set_language(lang)
        reaches[lang] = geopackage.reaches_style(navigation.BANDS, navigation.NO_INDEX_C)
    vg.set_language("en")
    return {"geometry_column": geopackage.GEOM, "reaches": reaches, "ports": geopackage.ports_style()}


def main(cache="cache", download=True):
    vg.configure(cache_dir=cache, offline=not download)
    vg.set_language("en")
    survey = vg.river_survey("congo", download=download)
    print(survey)
    if survey.error:
        raise SystemExit(survey.error)
    data = SITE / "data"
    data.mkdir(parents=True, exist_ok=True)
    out = data / "congo.json"
    out.write_text(json.dumps(build(survey), separators=(",", ":"), allow_nan=False))
    shutil.copy2(store.bundle_dir() / "locations" / "congo_countries.geojson", data / "countries.geojson")
    (data / "qgis.json").write_text(json.dumps(qgis_styles(), separators=(",", ":"), ensure_ascii=False))
    print(f"{out.relative_to(ROOT)}  {out.stat().st_size / 1e6:.2f} MB, levels to {survey.as_of:%Y-%m-%d}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(*args[:1], download="--no-download" not in sys.argv)
