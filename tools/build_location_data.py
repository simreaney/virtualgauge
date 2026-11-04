"""Build the bundled location data (run once, needs internet).

1. reach_index.parquet  — every SWORD v17b reach worldwide (slim columns), from per-continent files made by
                          extracting the SWORD GeoPackages (see tools/extract_sword.py).
2. congo_reaches.parquet — Congo-basin reaches ≥ 200 m wide, with the number of good SWOT observations
                          (Hydrocron, reach_q ≤ 1 and xovr_cal_q ≤ 1) for reaches ≥ 300 m wide.

Usage: python tools/build_location_data.py <folder with *_reaches_slim.parquet> [--counts]
"""
import io
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


def build_congo(idx, counts=False):
    c = idx[(idx.reach_id.astype(str).str[:3] == "132") & (idx.width_m >= 200) & (idx.type != 6)].copy()
    c["valid_obs"] = pd.NA
    c["good_obs"] = pd.NA
    if counts:
        partial = OUT / "_congo_counts_partial.csv"
        done = pd.read_csv(partial) if partial.exists() else pd.DataFrame(columns=["reach_id", "valid", "good"])
        todo = [r for r in c[c.width_m >= 300].sort_values("width_m", ascending=False).reach_id.head(1500)
                if r not in set(done.reach_id)]
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
        m = done.set_index("reach_id")
        c["valid_obs"] = c.reach_id.map(m["valid"])
        c["good_obs"] = c.reach_id.map(m["good"])
    c["valid_obs"] = pd.to_numeric(c["valid_obs"]).astype("Int16")
    c["good_obs"] = pd.to_numeric(c["good_obs"]).astype("Int16")
    c.to_parquet(OUT / "congo_reaches.parquet", compression="zstd", index=False)
    print("congo_reaches:", len(c), "reaches; with counts:", int(c.good_obs.notna().sum()))


if __name__ == "__main__":
    idx = build_index(sys.argv[1])
    build_congo(idx, counts="--counts" in sys.argv)
