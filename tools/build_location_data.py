"""Build the bundled location data (run once, needs internet).

1. reach_index.parquet     every SWORD v17b reach worldwide (slim columns), from per-continent files made by
                           extracting the SWORD GeoPackages (see tools/extract_sword.py).
2. congo_reaches.parquet   Congo-basin reaches ≥ 200 m wide, with the number of good SWOT observations
                           (Hydrocron, reach_q ≤ 1 and xovr_cal_q ≤ 1) for reaches ≥ 300 m wide.
3. botswana_reaches.parquet + botswana_outline.geojson
                           reaches ≥ 30 m wide inside Botswana or within 25 km of its border (so the border rivers —
                           Chobe, Zambezi, Limpopo, Shashe — are included), all with good-SWOT counts; the country
                           outline comes from Natural Earth 1:50m (public domain).

Usage:
  python tools/build_location_data.py index <folder with *_reaches_slim.parquet>
  python tools/build_location_data.py congo [--counts]
  python tools/build_location_data.py botswana <ne_50m_admin_0_countries.geojson>
"""
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

OUT = Path(__file__).resolve().parents[1] / "src" / "virtualgauge" / "data" / "locations"
HYDROCRON = "https://soto.podaac.earthdatacloud.nasa.gov/hydrocron/v1/timeseries"


def build_index(slim_dir):
    df = pd.concat([pd.read_parquet(f) for f in sorted(Path(slim_dir).glob("*_reaches_slim.parquet"))])
    idx = pd.DataFrame({
        "reach_id": df.reach_id.astype("int64"),
        "lon": df.x.astype("float32"), "lat": df.y.astype("float32"),
        "width_m": df.width.astype("float32"), "facc_km2": df.facc.astype("float32"),
        "river_name": df.river_name.replace("NODATA", "").astype("category"),
        "type": df.type.astype("int8"), "continent": df.continent.astype("category"),
    }).reset_index(drop=True)
    OUT.mkdir(parents=True, exist_ok=True)
    idx.to_parquet(OUT / "reach_index.parquet", compression="zstd", index=False)
    print("reach_index:", len(idx), "reaches,", round((OUT / "reach_index.parquet").stat().st_size / 1e6, 2), "MB")
    return idx


def good_obs(rid):
    """(reach, valid SWOT levels, good SWOT levels) since July 2023; (-1, -1) if Hydrocron failed."""
    params = dict(feature="Reach", feature_id=str(rid), output="csv", fields="reach_id,time_str,wse,reach_q,xovr_cal_q",
                  start_time="2023-07-01T00:00:00Z", end_time=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT23:59:59Z"))
    for i in range(3):
        try:
            r = requests.get(HYDROCRON, params=params, timeout=60)
            if r.status_code == 400:
                return rid, 0, 0
            if r.ok:
                d = pd.read_csv(io.StringIO(r.json()["results"]["csv"]))
                v = d[(d.time_str != "no_data") & (d.wse > -1e10)]
                return rid, len(v), int(((v.reach_q <= 1) & (v.xovr_cal_q <= 1)).sum())
        except Exception:
            pass
        time.sleep(2 * (i + 1))
    return rid, -1, -1


def count_obs(reach_ids, partial):
    """Good-SWOT counts for many reaches, 4 at a time, resumable through the `partial` CSV."""
    done = pd.read_csv(partial) if partial.exists() else pd.DataFrame(columns=["reach_id", "valid", "good"])
    todo = [r for r in reach_ids if r not in set(done.reach_id)]
    print("Hydrocron counts to do:", len(todo), flush=True)
    rows = []
    with ThreadPoolExecutor(4) as ex:
        for i, (rid, valid, good) in enumerate(ex.map(good_obs, todo)):
            rows.append(dict(reach_id=rid, valid=valid, good=good))
            if (i + 1) % 50 == 0:
                pd.concat([done, pd.DataFrame(rows)]).to_csv(partial, index=False)
                print(" ", i + 1, "of", len(todo), flush=True)
    done = pd.concat([done, pd.DataFrame(rows)])
    done.to_csv(partial, index=False)
    return done.drop_duplicates("reach_id", keep="last").set_index("reach_id")


def _with_counts(c, counts):
    for col, src in [("valid_obs", "valid"), ("good_obs", "good")]:
        v = c.reach_id.map(counts[src]) if counts is not None else pd.Series(pd.NA, index=c.index)
        c[col] = pd.to_numeric(v).astype("Int16")
    c.loc[(c.good_obs < 0).fillna(False), ["valid_obs", "good_obs"]] = pd.NA   # Hydrocron failed → unknown
    return c


def build_congo(idx, counts=False):
    c = idx[(idx.reach_id.astype(str).str[:3] == "132") & (idx.width_m >= 200) & (idx.type != 6)].copy()
    m = None
    if counts:
        ids = list(c[c.width_m >= 300].sort_values("width_m", ascending=False).reach_id.head(1500))
        m = count_obs(ids, OUT / "_congo_counts_partial.csv")
    c = _with_counts(c, m)
    c.to_parquet(OUT / "congo_reaches.parquet", compression="zstd", index=False)
    print("congo_reaches:", len(c), "reaches; with counts:", int(c.good_obs.notna().sum()))


def build_botswana(idx, countries_geojson):
    import geopandas as gpd
    ne = gpd.read_file(countries_geojson)
    bw = ne[ne.ADMIN == "Botswana"].to_crs(32735)                      # UTM 35S, metres
    area = bw.buffer(25_000).to_crs(4326).union_all()
    w, s, e, n = area.bounds
    box = idx[idx.lon.between(w, e) & idx.lat.between(s, n) & (idx.type != 6) & (idx.width_m >= 30)]
    pts = gpd.GeoSeries(gpd.points_from_xy(box.lon, box.lat), crs=4326)
    c = box[pts.within(area).to_numpy()].copy()
    m = count_obs(list(c.reach_id), OUT / "_botswana_counts_partial.csv")
    c = _with_counts(c, m)
    c.to_parquet(OUT / "botswana_reaches.parquet", compression="zstd", index=False)
    outline = bw.to_crs(4326).simplify(0.01).iloc[0]
    (OUT / "botswana_outline.geojson").write_text(json.dumps(
        {"type": "Feature", "properties": {"name": "Botswana", "source": "Natural Earth 1:50m (public domain)"},
         "geometry": json.loads(gpd.GeoSeries([outline]).to_json())["features"][0]["geometry"]}))
    print("botswana_reaches:", len(c), "reaches; with counts:", int(c.good_obs.notna().sum()),
          "; ≥10 good:", int((c.good_obs >= 10).sum()))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "index":
        build_index(sys.argv[2])
    else:
        index = pd.read_parquet(OUT / "reach_index.parquet")
        if cmd == "congo":
            build_congo(index, counts="--counts" in sys.argv)
        elif cmd == "botswana":
            build_botswana(index, sys.argv[2])
