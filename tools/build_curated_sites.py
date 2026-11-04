"""Choose and download extra Congo sites to ship with the package (run once, needs internet).

For each target town: pick the nearby SWOT reach with the most good observations, make a Site from it, find the
GEOGloWS main-stem river (largest upstream area), download everything, and keep the site if it has enough data.
Writes src/virtualgauge/data/locations/sites.json; then run tools/sync_bundled_data.py on the build cache.

Usage: python tools/build_curated_sites.py <build cache folder>
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import virtualgauge as vg
from virtualgauge import download
from virtualgauge.locations import _km, congo_reaches

OUT = Path(__file__).resolve().parents[1] / "src" / "virtualgauge" / "data" / "locations" / "sites.json"
ESRI = "https://livefeeds3.arcgis.com/arcgis/rest/services/GEOGLOWS/GlobalWaterModel_Medium/MapServer/0/query"

TARGETS = [
    dict(key="congo_kisangani", short="Congo – Kisangani", river="Congo", lat=0.50, lon=25.15,
         name="Congo River near Kisangani (DR Congo) · Fleuve Congo près de Kisangani (RD Congo)"),
    dict(key="congo_mbandaka", short="Congo – Mbandaka", river="Congo", lat=0.05, lon=18.25,
         name="Congo River near Mbandaka (DR Congo) · Fleuve Congo près de Mbandaka (RD Congo)"),
    dict(key="ubangi_bangui", short="Ubangi – Bangui", river="Ubangi", lat=4.36, lon=18.58,
         name="Ubangi River at Bangui (CAR / DR Congo) · Rivière Oubangui à Bangui (RCA / RD Congo)"),
    dict(key="kasai_kwamouth", short="Kasai – Kwamouth", river="Kasai", lat=-3.15, lon=16.40,
         name="Kasai River near Kwamouth (DR Congo) · Rivière Kasaï près de Kwamouth (RD Congo)"),
    dict(key="lualaba_kindu", short="Lualaba – Kindu", river="Lualaba", lat=-2.95, lon=25.92,
         name="Lualaba (upper Congo) at Kindu (DR Congo) · Lualaba (haut Congo) à Kindu (RD Congo)"),
    dict(key="sangha_ouesso", short="Sangha – Ouesso", river="Sangha", lat=1.62, lon=16.05,
         name="Sangha River near Ouesso (Rep. Congo) · Rivière Sangha près de Ouesso (Rép. du Congo)"),
]


def geoglows_main_stem(lat, lon, d=0.08):
    p = dict(geometry=f"{lon - d},{lat - d},{lon + d},{lat + d}", geometryType="esriGeometryEnvelope", inSR=4326,
             spatialRel="esriSpatialRelIntersects", outFields="comid,upstreamarea,streamorder",
             returnGeometry="false", f="json")
    feats = requests.get(ESRI, params=p, timeout=120).json().get("features", [])
    if not feats:
        return None, None
    best = max(feats, key=lambda f: f["attributes"]["upstreamarea"])["attributes"]
    return int(best["comid"]), float(best["upstreamarea"]) / 1e6


def main(cache):
    vg.configure(cache_dir=cache)
    c = congo_reaches()
    kept = []
    for tg in TARGETS:
        c2 = c.assign(km=_km(tg["lat"], tg["lon"], c.lat, c.lon))
        cand = c2[(c2.km <= 30) & c2.good_obs.notna()].sort_values(["good_obs", "width_m"], ascending=False)
        if cand.empty:
            print(tg["key"], "no candidate reach"); continue
        rid = str(int(cand.reach_id.iloc[0]))
        site = vg.Site.from_reach(rid, key=tg["key"], name=tg["name"], short=tg["short"], river=tg["river"])
        gid, area = geoglows_main_stem(site.lat, site.lon)
        if gid:
            q = download.geoglows_daily(gid)
            print(f"  GEOGloWS {gid}: upstream area {area:,.0f} km², mean {q.mean():,.0f} m³/s")
            if area < 20000 or q.mean() < 300:
                gid = None
            else:   # ship 2015 onwards only (keeps the package small)
                f = Path(cache) / f"geoglows_{gid}.csv"
                full = pd.read_csv(f, index_col=0)
                full[full.index >= "2015-01-01"].to_csv(f)
        site.geoglows_id = gid
        st = vg.build_station(site)
        if st.error:
            print(tg["key"], "ERROR", st.error); continue
        n_ice, n_swot = len(st.data.vs_ice), len(st.data.swot_ok)
        print(f"{tg['key']}: reach {rid} ({cand.km.iloc[0]:.1f} km away, {cand.width_m.iloc[0]:.0f} m wide, "
              f"{int(cand.good_obs.iloc[0])} good SWOT obs) → ICESat-2 {n_ice}, SWOT kept {n_swot}, "
              f"neighbours {site.swot_up}/{site.swot_down}, h_range {site.h_range}, geoglows {gid}")
        if n_swot >= 20 and n_ice + n_swot >= 30:
            d = asdict(site)
            d["h_range"] = list(d["h_range"])
            kept.append(d)
    OUT.write_text(json.dumps(kept, indent=1))
    print("kept", len(kept), "sites →", OUT)


if __name__ == "__main__":
    main(sys.argv[1])
