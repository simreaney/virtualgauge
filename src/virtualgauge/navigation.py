"""River navigability for a whole basin from SWOT (English or French: vg.set_language).

    import virtualgauge as vg
    congo = vg.river_survey("congo")     # download and clean the SWOT levels of every reach in the Congo basin
    congo.coverage()                     # how many good levels each reach has
    congo.cleaning()                     # which levels are removed, and why
    congo.ranges()                       # the lowest and highest level recorded on each reach, and the range
    congo.navigability()                 # the index today: 0 = lowest level recorded, 100 = highest
    congo.map()                          # interactive map of the current navigability
    congo.profile()                      # along the Lualaba and the Congo, down to the sea
    congo.reach("13273000011")           # one reach: its levels, range and index
    congo.ports()                        # the index through time at river ports
    congo.history()                      # how much of the network was at low or high water, month by month
    congo.export()                       # CSV, GeoPackage (QGIS) and GeoJSON in outputs/
    congo.download_geopackage()          # the GeoPackage to your computer (Colab: your Downloads folder)

Navigability index of a reach, from its own record of SWOT levels since July 2023:

    index = 100 × (latest level − lowest level) / (highest level − lowest level)

so 0 means the river is as low as SWOT has ever seen it there (poorest navigability) and 100 as high (best).
Data: SWOT L2 HR RiverSP reach product, Version D (NASA/CNES, PO.DAAC), through Hydrocron — no login.
"""
import gzip
import hashlib
import html as html_mod
import io
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import download, settings, store
from .i18n import Both, Day, M, _pair, fmt_int, say, t
from .locations import _km, reach_index
from .messages import MESSAGES
from .processing import robust_spread, utc_naive
from .results import Result, reason_label

START = "2023-07-01"                 # SWOT science orbit: from 26 July 2023
SURVEY_FIELDS = ["reach_id", "time_str", "cycle_id", "pass_id", "wse", "wse_u", "width", "reach_q", "xovr_cal_q",
                 "dark_frac", "ice_clim_f", "partial_f", "n_good_nod", "obs_frac_n", "p_dist_out", "p_length",
                 "rch_id_up", "rch_id_dn"]
LEVEL_COLS = ["reach_id", "time", "cycle_id", "pass_id", "wse", "wse_u", "width", "reach_q", "xovr_cal_q",
              "dark_frac", "ice_clim_f", "partial_f", "n_good_nod", "obs_frac_n"]
REACH_COLS = ["reach_id", "status", "n_passes", "dist_out_km", "length_km", "rch_id_up", "rch_id_dn", "downloaded_utc"]
SWORD_TYPES = {1: "river", 3: "lake on river", 4: "dam or waterfall", 5: "unreliable topology", 6: "ghost reach"}

# Index bands: (lowest index, message key, colour). Red = low water (poor), grey = middle, blue = high water (good).
# The two arms are matched in lightness (OKLab L 0.49 / 0.77 red, 0.76 / 0.48 blue) so neither end shouts louder.
BANDS = [(0, "nv_band_0", "#a8302c"), (20, "nv_band_1", "#f19a8c"), (40, "nv_band_2", "#b9b7ae"),
         (60, "nv_band_3", "#86b6ef"), (80, "nv_band_4", "#1c5cab")]
NO_INDEX_C = "#dcdad3"

REGIONS = {
    "congo": dict(name=M("nv_region_congo"), basin=132, main_start=13279900061, main_name=M("nv_main_congo"),
                  ports=[  # (name, river, SWOT reach): the ready-made stations, plus Bumba and Ilebo
                      ("Kindu", "Lualaba", 13279900051), ("Kisangani", "Congo", 13279300031),
                      ("Bumba", "Congo", 13275700241), ("Mbandaka", "Congo", 13273000011),
                      ("Bangui", "Ubangi", 13263100051), ("Ouesso", "Sangha", 13245000311),
                      ("Ilebo", "Kasai", 13227000021), ("Kwamouth", "Kasai", 13221000021),
                      ("Kinshasa", "Congo", 13217000081)]),
}


@dataclass(frozen=True)
class SurveyParams:
    """Settings for cleaning the levels and for the index.

    max_reach_q    keep levels whose reach quality flag is at most this (0 good, 1 suspect, 2 degraded, 3 bad)
    max_xovr_q     keep levels whose crossover-calibration quality flag is at most this
    max_dark_frac  remove levels where more than this share of the reach's water was 'dark' (too little radar
                   echo, e.g. very calm water). 1 (the default) keeps them: on the Congo a limit of 0.5 removes a
                   fifth of the good levels and leaves records such as Kindu and Ouesso full of gaps
    k_mad          remove levels further than k robust spreads from the median level of their reach
    min_spread_m   ... counting the spread as at least this (m), so steady lakes keep their levels
    jump_m, jump_k remove a level further from the median of the levels within ±jump_days of it than jump_k times
                   the reach's usual change between passes a few days apart, and at least jump_m (m)
    jump_days      ... (the first and latest levels, with neighbours on one side only, are compared with the trend
                   of their two nearest neighbours, and may be twice as far)
    min_levels     a reach needs at least this many good levels for an index
    min_span_days  ... spread over at least this many days, so that low and high water are both in the record
    min_range_m    ... and a range of at least this (m): a smaller range is close to SWOT's own noise
    max_noise_m    a reach is too noisy when levels at most noise_days apart typically differ by more than this (m)
    max_noise_frac ... or by more than this share of its range (then one pass can move the index by 20 points)
    noise_days     how close in time two levels must be to measure the noise
    max_age_days   the current level must be at most this many days old
    """
    max_reach_q: int = 1
    max_xovr_q: int = 1
    max_dark_frac: float = 1.0
    k_mad: float = 5.0
    min_spread_m: float = 0.25
    jump_m: float = 0.5
    jump_k: float = 4.0
    jump_days: int = 15
    min_levels: int = 10
    min_span_days: int = 365
    min_range_m: float = 0.5
    max_noise_m: float = 1.0
    max_noise_frac: float = 0.2
    noise_days: int = 6
    max_age_days: int = 30


def band_of(index):
    """Band number 0–4 of each index value (−1 when there is no index)"""
    x = np.asarray(index, dtype=float)
    return np.where(np.isfinite(x), np.clip(np.floor(np.nan_to_num(x) / 20), 0, 4), -1).astype(int)


def band_label(b):
    return t(BANDS[int(b)][1]) if pd.notna(b) and b >= 0 else t("nv_no_index")


def band_colour(b):
    return BANDS[int(b)][2] if pd.notna(b) and b >= 0 else NO_INDEX_C


# --- which reaches ---------------------------------------------------------------------------------------------
def region_reach_list(region="congo", reach_ids=None, min_width_m=0):
    """Every SWORD v17b reach of a region (ghost reaches, type 6, left out), from the bundled index."""
    idx = reach_index()
    if reach_ids is not None:
        ids = {int(r) for r in reach_ids}
        d = idx[idx.reach_id.isin(ids)]
    else:
        if region not in REGIONS:
            raise ValueError(f"Unknown region {region!r}. Known: {list(REGIONS)}, or give reach_ids=[...]")
        d = idx[(idx.reach_id // 10**8 == REGIONS[region]["basin"]) & (idx.type != 6)]
    if min_width_m:
        d = d[d.width_m >= min_width_m]
    return d.sort_values("reach_id").reset_index(drop=True)


# --- download -------------------------------------------------------------------------------------------------
def survey_folder():
    """One file per reach, shared by every survey · un fichier par tronçon"""
    return settings.cache_dir() / "survey_reaches"


def _reach_file(folder, rid):
    return folder / f"{rid}.csv.gz"


def fetch_reach(rid, folder, end=None, timeout=90, tries=4):
    """Download the SWOT record of one reach from Hydrocron into folder/<reach>.csv.gz (an empty file = no data).
    Returns (reach_id, "ok" | "no data" | "failed")."""
    params = dict(feature="Reach", feature_id=str(rid), output="csv", fields=",".join(SURVEY_FIELDS),
                  start_time=f"{START}T00:00:00Z", end_time=f"{end or download.today()}T23:59:59Z")
    text = None
    for i in range(tries):
        try:
            r = requests.get(download.HYDROCRON, params=params, timeout=timeout)
            if r.status_code == 400:                 # Hydrocron answers 400 when there is no data for the reach
                text = ""
                break
            if r.ok:
                text = r.json()["results"]["csv"]
                break
        except (requests.RequestException, ValueError, KeyError):
            pass
        time.sleep(3 * (i + 1))                       # 429 or 5xx: slow down and try again
    if text is None:
        return rid, "failed"
    f = _reach_file(folder, rid)
    tmp = f.with_name(f.name + ".part")
    tmp.write_bytes(gzip.compress(text.encode()) if text else b"")
    os.replace(tmp, f)
    return rid, ("ok" if text else "no data")


def _fresh(f, days):
    return f.exists() and (time.time() - f.stat().st_mtime) < days * 86400


def download_reaches(reach_ids, folder, update_days=3, workers=8, progress=True):
    """Download every reach not saved in the last `update_days` days, `workers` at a time (resumable).
    Returns a dict with the counts: saved (already fresh), ok, no data, failed."""
    folder.mkdir(parents=True, exist_ok=True)
    todo = [r for r in reach_ids if not _fresh(_reach_file(folder, r), update_days)]
    counts = {"saved": len(reach_ids) - len(todo), "ok": 0, "no data": 0, "failed": 0}
    if not todo:
        return counts
    if progress:
        say("nv_downloading", n=fmt_int(len(todo)), saved=fmt_int(counts["saved"]), workers=workers,
            min=max(1, round(len(todo) * 1.3 / workers / 60)))
    t0, end = time.time(), download.today()
    with ThreadPoolExecutor(workers) as ex:
        jobs = [ex.submit(fetch_reach, r, folder, end) for r in todo]
        for i, job in enumerate(as_completed(jobs), 1):
            counts[job.result()[1]] += 1
            if progress and (i % 25 == 0 or i == len(todo)):
                left = (time.time() - t0) / i * (len(todo) - i)
                line = t("nv_progress", i=fmt_int(i), n=fmt_int(len(todo)), ok=fmt_int(counts["ok"]),
                         none=fmt_int(counts["no data"]), failed=counts["failed"], min=f"{left / 60:.0f}")
                print("\r" + line + "   ", end="", flush=True)
    if progress:
        print()
    return counts


def _split_ids(s):
    if not isinstance(s, str):
        return ""
    return ",".join(x.strip() for x in s.split(",") if x.strip().isdigit())


def combine(reach_ids, folder):
    """All saved reach files -> (levels, reaches): one row per SWOT level, one row per reach."""
    frames, rows = [], []
    for rid in reach_ids:
        f = _reach_file(folder, rid)
        info = dict(reach_id=int(rid), status="not downloaded", n_passes=0, dist_out_km=np.nan, length_km=np.nan,
                    rch_id_up="", rch_id_dn="", downloaded_utc="")
        if f.exists():
            info["downloaded_utc"] = pd.Timestamp(f.stat().st_mtime, unit="s").strftime("%Y-%m-%dT%H:%M:%SZ")
            raw = f.read_bytes()
            if not raw:
                info["status"] = "no data"
            else:
                d = pd.read_csv(io.StringIO(gzip.decompress(raw).decode()), dtype={"reach_id": "int64"})
                first = d.iloc[0]
                info.update(status="ok", n_passes=len(d), rch_id_up=_split_ids(first.get("rch_id_up")),
                            rch_id_dn=_split_ids(first.get("rch_id_dn")),
                            dist_out_km=float(first.get("p_dist_out", np.nan)) / 1000,
                            length_km=float(first.get("p_length", np.nan)) / 1000)
                d = d[(d.time_str != "no_data") & (pd.to_numeric(d.wse, errors="coerce") > -1e10)]
                if len(d):
                    d = d.assign(time=utc_naive(d.time_str))
                    frames.append(d[[c for c in LEVEL_COLS if c in d]])
        rows.append(info)
    levels = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=LEVEL_COLS)
    reaches = pd.DataFrame(rows, columns=REACH_COLS)
    for c in ("dist_out_km", "length_km"):
        reaches[c] = reaches[c].where(reaches[c] > 0)              # SWORD writes −9999 when unknown
    return compact(levels), reaches


def compact(levels):
    """Small dtypes, so a whole basin fits in a few MB"""
    out = levels.copy()
    out["reach_id"] = out.reach_id.astype("int64")
    out["time"] = pd.to_datetime(out.time).astype("datetime64[s]")
    for c in ["cycle_id", "pass_id", "n_good_nod"]:
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(-1).astype("int16")
    for c in ["reach_q", "xovr_cal_q", "ice_clim_f", "partial_f"]:
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(-1).astype("int8")
    for c in ["wse", "wse_u", "width", "dark_frac", "obs_frac_n"]:
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce").astype("float64" if c == "wse" else "float32")
    out["wse"] = out.wse.round(3)        # mm, as in the copy shipped with the package (SWOT is good to a few cm)
    return out.sort_values(["reach_id", "time"]).reset_index(drop=True)


def _names(key):
    return f"survey_{key}_levels.parquet", f"survey_{key}_reaches.parquet"


def _save(key, levels, reaches):
    for name, d in zip(_names(key), (levels, reaches)):
        p = settings.cache_dir() / name
        p.parent.mkdir(parents=True, exist_ok=True)
        d.to_parquet(p.with_name(p.name + ".part"), index=False, compression="zstd")
        os.replace(p.with_name(p.name + ".part"), p)
    store.log_download(_names(key)[0], f"Hydrocron — SWOT RiverSP reach (Version D), {len(reaches)} reaches")


def write_compact(levels, path):
    """The levels in a small file for the package: heights in mm, dark water in %, only the columns the survey uses
    (3 MB for the whole Congo instead of 10)."""
    c = pd.DataFrame({"reach_id": levels.reach_id.astype("int64"), "time": levels.time.astype("datetime64[s]"),
                      "wse_mm": (levels.wse * 1000).round().astype("int32"),
                      "reach_q": levels.reach_q.astype("int8"), "xovr_cal_q": levels.xovr_cal_q.astype("int8"),
                      "dark_pct": (levels.dark_frac.fillna(-0.01) * 100).round().astype("int8")})
    c.to_parquet(path, index=False, compression="zstd", compression_level=19)


def read_levels(path):
    """Read a combined levels file, full or compact"""
    d = pd.read_parquet(path)
    if "wse_mm" in d:
        d = d.assign(wse=d.wse_mm / 1000.0, dark_frac=(d.dark_pct / 100.0).where(d.dark_pct >= 0).astype("float32"))
        d = d.drop(columns=["wse_mm", "dark_pct"])
    d["time"] = d.time.astype("datetime64[s]")
    d["wse"] = d.wse.round(3)
    return d


def _saved(key, reach_ids):
    """The last combined copy: your cache first, then the copy shipped with the package. A list of reaches inside
    the Congo is also found in the Congo survey; the reach files of an interrupted download are combined."""
    ids = set(int(r) for r in reach_ids)
    for origin, folder in (("cache", settings.cache_dir()), ("bundled", store.bundle_dir())):
        names = [_names(key)] + [_names(f.name[len("survey_"):-len("_reaches.parquet")])
                                 for f in sorted(folder.glob("survey_*_reaches.parquet")) if f.name != _names(key)[1]]
        for levels_name, reaches_name in names:
            paths = [folder / levels_name, folder / reaches_name]
            if not all(p.exists() for p in paths):
                continue
            reaches = pd.read_parquet(paths[1])
            if ids <= set(reaches.reach_id):
                levels = read_levels(paths[0])
                return (levels[levels.reach_id.isin(ids)].reset_index(drop=True),
                        reaches[reaches.reach_id.isin(ids)].reset_index(drop=True), origin)
        if origin == "cache" and all(_reach_file(survey_folder(), r).exists() for r in ids):
            levels, reaches = combine(sorted(ids), survey_folder())
            return levels, reaches, "cache"
    return None, None, None


# --- cleaning ---------------------------------------------------------------------------------------------------
def pass_noise(ok, days=6, min_pairs=5):
    """Typical change (median, m) between good levels at most `days` apart: SWOT noise, as the river barely moves
    in a few days. NaN when a reach has fewer than min_pairs such pairs."""
    k = ok.sort_values(["reach_id", "time"])
    same = k.reach_id.eq(k.reach_id.shift())
    close = (k.time - k.time.shift()).dt.total_seconds() <= days * 86400
    d = pd.DataFrame({"reach_id": k.reach_id, "dh": (k.wse - k.wse.shift()).abs()})[same & close]
    g = d.groupby("reach_id").dh
    return g.median()[g.size() >= min_pairs]


def _spikes(k, limit_m, jump_days, max_k=3):
    """Labels of levels that jump away from the levels around them in time.

    Within ±jump_days (or twice that when a level has no neighbour so close):
    - a level with neighbours on both sides is compared with the median of itself and the same number of neighbours
      on each side (up to max_k), so a steady rise or fall is never mistaken for a spike;
    - the first and latest levels (neighbours on one side only) are compared with a prediction from their two nearest
      neighbours — half-way between 'no change' and 'the same trend' — with twice the limit, so a real rise is kept.
    A level is removed when it is further than limit_m (one limit per reach) from that reference."""
    bad = []
    day = 86400.0
    for rid, g in k.sort_values(["reach_id", "time"]).groupby("reach_id", sort=False):
        n = len(g)
        if n < 3:
            continue
        tt = g.time.to_numpy().astype("datetime64[s]").astype("int64") / day
        h = g.wse.to_numpy(float)
        lim = limit_m.get(rid, np.nan)
        dt = tt[None, :] - tt[:, None]
        win = np.where((np.abs(dt) <= jump_days).sum(1) > 1, jump_days, 2 * jump_days)[:, None]
        nb = ((dt < 0) & (-dt <= win)).sum(1)
        na = ((dt > 0) & (dt <= win)).sum(1)
        ref = np.full(n, np.nan)
        kk = np.minimum(np.minimum(nb, na), max_k)
        pad = np.r_[np.full(max_k, np.nan), h, np.full(max_k, np.nan)]
        for j in range(1, max_k + 1):                       # centred medians of 3, 5, 7 levels
            if 2 * j + 1 > n:
                break
            med = np.median(np.lib.stride_tricks.sliding_window_view(pad, 2 * j + 1), axis=1)
            med = med[max_k - j: max_k - j + n]
            ref = np.where(kk == j, med, ref)
        two_sided = kk >= 1
        limit = np.where(two_sided, lim, 2 * lim)
        for side, count in ((-1, nb), (1, na)):              # one-sided: the latest levels use the two before
            use = ~two_sided & (count >= 1)
            i1 = np.clip(np.arange(n) + side, 0, n - 1)
            i2 = np.clip(np.arange(n) + 2 * side, 0, n - 1)
            trend = h[i1] + (h[i1] - h[i2]) * (tt - tt[i1]) / np.where(tt[i1] != tt[i2], tt[i1] - tt[i2], np.inf)
            pred = np.where(count >= 2, (h[i1] + trend) / 2, h[i1])
            ref = np.where(use & np.isnan(ref), pred, ref)
        bad.extend(g.index[np.abs(h - ref) > limit])
    return pd.Index(bad)


def clean_levels(levels, params):
    """Label each SWOT level as kept or removed, with the reason (as in the virtual-station notebook)."""
    s = levels.reset_index(drop=True).copy()
    s["reason"] = "kept"
    if s.empty:
        return s
    s.loc[s.duplicated(["reach_id", "time"]), "reason"] = "0 duplicate"
    k = s.reason == "kept"
    s.loc[k & (s.reach_q > params.max_reach_q), "reason"] = f"2 reach_q > {params.max_reach_q}"
    k = s.reason == "kept"
    s.loc[k & (s.xovr_cal_q > params.max_xovr_q), "reason"] = f"3 xovr_cal_q > {params.max_xovr_q}"
    k = s.reason == "kept"
    s.loc[k & (s.dark_frac > params.max_dark_frac), "reason"] = "4 dark water"
    k = s.reason == "kept"
    if k.any():
        g = s[k].groupby("reach_id").wse
        med, spr = g.transform("median"), g.transform(robust_spread)
        far = (s.loc[k, "wse"] - med).abs() > params.k_mad * np.maximum(spr, params.min_spread_m)
        s.loc[far.index[far.to_numpy()], "reason"] = "5 far from other levels"
    k = s[s.reason == "kept"]
    noise = pass_noise(k, params.noise_days).reindex(k.reach_id.unique())
    limit = np.maximum(params.jump_m, params.jump_k * noise).fillna(2 * params.jump_m)   # unknown noise: 2 × jump_m
    s.loc[_spikes(k, limit, params.jump_days), "reason"] = "6 spike"
    return s


# --- per reach: record, range, index -------------------------------------------------------------------------
def reach_table(meta, reaches, levels, params):
    """One row per reach: where it is, how many levels, the lowest and highest, and whether it can have an index."""
    tab = meta[["reach_id", "river_name", "lat", "lon", "width_m", "facc_km2", "type"]].copy()
    tab["river_name"] = tab.river_name.astype(str).replace("", "—")
    tab = tab.merge(reaches, on="reach_id", how="left")
    tab["status"] = tab.status.fillna("not downloaded")
    tab["n_passes"] = tab.n_passes.fillna(0).astype(int)
    valid = levels.groupby("reach_id").size()
    ok = levels[levels.reason == "kept"]
    g = ok.groupby("reach_id")
    stats = pd.DataFrame({"n_good": g.size(), "first": g.time.min(), "last": g.time.max()})
    if len(ok):
        lo, hi = g.wse.idxmin(), g.wse.idxmax()
        stats["low_m"] = ok.loc[lo.to_numpy(), "wse"].to_numpy()
        stats["low_date"] = ok.loc[lo.to_numpy(), "time"].to_numpy()
        stats["high_m"] = ok.loc[hi.to_numpy(), "wse"].to_numpy()
        stats["high_date"] = ok.loc[hi.to_numpy(), "time"].to_numpy()
    else:
        for c in ("low_m", "high_m"):
            stats[c] = pd.Series(dtype=float)
        for c in ("low_date", "high_date"):
            stats[c] = pd.Series(dtype="datetime64[s]")
    tab = tab.merge(stats, left_on="reach_id", right_index=True, how="left")
    tab["n_levels"] = tab.reach_id.map(valid).fillna(0).astype(int)
    tab["n_good"] = tab.n_good.fillna(0).astype(int)
    tab["range_m"] = tab.high_m - tab.low_m
    tab["noise_m"] = tab.reach_id.map(pass_noise(ok, params.noise_days))
    span = (tab["last"] - tab["first"]).dt.days
    noisy = (tab.noise_m > params.max_noise_m) | (tab.noise_m > params.max_noise_frac * tab.range_m)
    why = np.select(
        [tab.status != "ok", tab.n_levels == 0, tab.n_good < params.min_levels,
         span.fillna(0) < params.min_span_days, tab.range_m < params.min_range_m, noisy],
        ["no SWOT data", "never measured", "too few good levels", "record too short", "range too small",
         "too noisy"], "")
    tab["why"] = np.where((tab.status == "not downloaded") & (why == "no SWOT data"), "not downloaded", why)
    return tab


def index_at(tab, levels, date, params):
    """The navigability index of every reach on `date`, from its latest good level at most max_age_days old."""
    ok = levels[(levels.reason == "kept") & (levels.time <= date)]
    last = ok.groupby("reach_id").tail(1).set_index("reach_id")
    out = pd.DataFrame(index=tab.reach_id.to_numpy())
    out["now_m"] = last.wse.reindex(out.index).to_numpy()
    out["now_date"] = last.time.reindex(out.index).to_numpy()
    out["age_days"] = ((date - pd.to_datetime(out.now_date)).dt.total_seconds() / 86400).round(1).to_numpy()
    lo, hi, why = (tab.set_index("reach_id")[c].reindex(out.index) for c in ("low_m", "high_m", "why"))
    why = why.where(why != "", np.where(out.now_m.isna() | (out.age_days > params.max_age_days), "no recent level", ""))
    out["index"] = np.where(why == "", np.clip(100 * (out.now_m - lo) / (hi - lo), 0, 100), np.nan)
    out["band"] = band_of(out["index"])
    out["why"] = why.to_numpy()
    return out.rename_axis("reach_id")


def series_index(levels, tab, rid):
    """Every good level of one reach turned into an index (using the reach's whole record)"""
    row = tab.set_index("reach_id").loc[int(rid)]
    k = levels[(levels.reach_id == int(rid)) & (levels.reason == "kept")]
    return k.assign(index=100 * (k.wse - row.low_m) / (row.high_m - row.low_m))


# --- the river network, for maps ---------------------------------------------------------------------------------
def network(tab, max_km=60):
    """Each reach as half-segments: from its centre half-way to each neighbour (SWORD topology from Hydrocron).
    Returns (segments, lone): segments = reach_id, x0, y0, x1, y1; lone = reaches with no neighbour to draw to."""
    idx = reach_index()
    pos = dict(zip(idx.reach_id.to_numpy(), zip(idx.lon.to_numpy(float), idx.lat.to_numpy(float))))
    known = set(tab.reach_id)
    edges = set()
    for r, ups, dns in zip(tab.reach_id, tab.rch_id_up.fillna(""), tab.rch_id_dn.fillna("")):
        edges.update((int(u), r) for u in ups.split(",") if u)
        edges.update((r, int(d)) for d in dns.split(",") if d)
    rows = []
    for a, b in edges:
        if a not in pos or b not in pos or a == b:
            continue
        (xa, ya), (xb, yb) = pos[a], pos[b]
        if _km(ya, xa, [yb], [xb])[0] > max_km:
            continue
        xm, ym = (xa + xb) / 2, (ya + yb) / 2
        oa = a if a in known else b                  # a ghost or outside reach takes its neighbour's colour
        ob = b if b in known else a
        if oa in known:
            rows.append((oa, xa, ya, xm, ym))
        if ob in known:
            rows.append((ob, xm, ym, xb, yb))
    seg = pd.DataFrame(rows, columns=["reach_id", "x0", "y0", "x1", "y1"]).drop_duplicates()
    lone = tab[~tab.reach_id.isin(seg.reach_id)][["reach_id", "lon", "lat"]]
    return seg, lone


def _next_down(idx, r, seen, max_km=30):
    """A reach with no topology (never measured, e.g. at a waterfall): take the nearest reach within max_km that
    drains more (the same river name first). None at the sea."""
    here = idx.loc[r]
    box = idx[(idx.lat - here.lat).abs().lt(0.3) & (idx.lon - here.lon).abs().lt(0.3)
              & (idx.facc_km2 > here.facc_km2) & ~idx.index.isin(seen)]
    if box.empty:
        return None
    km = pd.Series(_km(here.lat, here.lon, box.lat, box.lon), index=box.index)
    km = km[km <= max_km]
    if km.empty:
        return None
    same = km[box.river_name.reindex(km.index).astype(str) == str(here.river_name)]
    return int((same if len(same) else km).idxmin())


def main_stem(tab, start, max_steps=2000):
    """Walk downstream from `start` to the sea, reach by reach (the widest way at each fork)."""
    by = tab.set_index("reach_id")
    idx = reach_index().set_index("reach_id")
    down = {}
    for r, dns in zip(tab.reach_id, tab.rch_id_dn.fillna("")):
        down.setdefault(r, set()).update(int(d) for d in dns.split(",") if d)
    for r, ups in zip(tab.reach_id, tab.rch_id_up.fillna("")):       # also learn 'down' from the reach below
        for u in (int(x) for x in ups.split(",") if x):
            down.setdefault(u, set()).add(r)
    path, r = [], int(start)
    while r is not None and r not in path and len(path) < max_steps:
        path.append(r)
        nxt = [d for d in down.get(r, ()) if d in idx.index and d not in path]
        r = (max(nxt, key=lambda d: (idx.facc_km2.get(d, 0), idx.width_m.get(d, 0))) if nxt
             else _next_down(idx, r, set(path)))
    p = idx.loc[path, ["lon", "lat", "river_name", "type"]].reset_index()
    dist = by.dist_out_km.reindex(path).to_numpy(float)
    along = np.cumsum(np.r_[0, _km(p.lat.to_numpy()[:-1], p.lon.to_numpy()[:-1], p.lat.to_numpy()[1:],
                                   p.lon.to_numpy()[1:])]) if len(p) > 1 else np.zeros(len(p))
    ok = np.isfinite(dist)
    if ok.any():          # where SWORD gives no distance (reach never measured), count along the walk instead
        dist = np.where(ok, dist, np.interp(along, along[ok], dist[ok] + along[ok]) - along)
    else:
        dist = along[-1] - along if len(p) else dist
    p["dist_out_km"] = dist
    return p


# --- the survey ------------------------------------------------------------------------------------------------
def _date(d):
    """The end of that day, in UTC without a time zone (like the SWOT times)"""
    ts = pd.Timestamp(d)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    return ts.normalize() + pd.Timedelta(hours=23, minutes=59, seconds=59)


def _day(ts):
    """"16 November 2026" · "16 novembre 2026", in the language of each message ("—" when missing)"""
    return Day(None if pd.isna(ts) else pd.Timestamp(ts))


def _why(code):
    """The reason a reach has no index, as a message"""
    return M("nv_why_" + (str(code).replace(" ", "_") or "index_possible"))


def _why_list(counts):
    """"12 with no SWOT data, 40 too noisy …" in each language"""
    parts = [(fmt_int(n), _pair("nv_why_" + str(k).replace(" ", "_"), {})) for k, n in counts.items()]
    return Both(*(", ".join(f"{n} {p[i]}" for n, p in parts) for i in (0, 1)))


def _columns(df, names):
    """A function giving the table with its column names in the chosen language (.table keeps the English names)"""
    return lambda: df.rename(columns={c: t("nv_col_" + k) for c, k in names.items()})


def _needs_data(method):
    def wrapper(self, *a, **kw):
        if self.error:
            return Result(("nv_h_survey", {"name": self.name}), [("nv_unavailable", {"why": self.error})])
        return method(self, *a, **kw)
    wrapper.__name__, wrapper.__doc__ = method.__name__, method.__doc__
    return wrapper


class RiverSurvey:
    """Every SWOT reach of a basin, its levels, its range and its navigability index.
    Build it with vg.river_survey("congo").

    Steps: .coverage() .cleaning() .ranges() .navigability() .map() .profile() .reach(id) .ports() .history() .export()
    Data:  .table (one row per reach), .levels (every SWOT level, with the reason it is kept or removed),
           .to_dataframe(date) (the table with the index on that date), .params (settings)
    """

    def __init__(self, key, name, meta, reaches, levels, params, origin="", counts=None, error=None):
        self.key, self.name, self.params, self.origin, self.counts, self.error = key, name, params, origin, counts, error
        self.region = REGIONS.get(key, {})
        self._meta, self._reaches, self._raw = meta, reaches, levels
        self._net = None
        if error:
            return
        self.levels = clean_levels(levels, params)
        self.table = reach_table(meta, reaches, self.levels, params)
        dl = pd.to_datetime(reaches.downloaded_utc.replace("", None), errors="coerce").dropna()
        self.as_of = _date(dl.max()) if len(dl) else _date(self.levels.time.max())

    @classmethod
    def unavailable(cls, key, name, why):
        return cls(key, name, None, None, None, SurveyParams(), error=why)

    def with_settings(self, **changes):
        """The same data with other settings, e.g. congo.with_settings(max_age_days=45)"""
        return RiverSurvey(self.key, self.name, self._meta, self._reaches, self._raw, replace(self.params, **changes),
                           self.origin, self.counts)

    # --- overview ---------------------------------------------------------------------------------------------
    def _card(self):
        if self.error:
            return Result(("nv_h_survey", {"name": self.name}), [("nv_unavailable", {"why": self.error})])
        tab, lv = self.table, self.levels
        with_data = int((tab.n_levels > 0).sum())
        kept = lv[lv.reason == "kept"]
        lines = [("nv_card_reaches", dict(n=fmt_int(len(tab)), with_data=fmt_int(with_data),
                                          levels=fmt_int(len(kept)), first=_day(kept.time.min()),
                                          last=_day(kept.time.max())))]
        c = self.counts
        if self.origin == "download" and c:
            lines.append(("nv_card_download", dict(new=fmt_int(c["ok"] + c["no data"]), saved=fmt_int(c["saved"]),
                                                   failed=c["failed"], date=_day(self.as_of))))
        else:
            lines.append(("nv_card_saved", dict(where=t("nv_origin_" + (self.origin or "cache")), date=_day(self.as_of))))
        if c and c["failed"]:
            lines.append(("nv_card_failed", dict(n=c["failed"])))
        lines.append(("nv_card_next", {}))
        return Result(("nv_h_survey", {"name": self.name}), lines)

    def _repr_html_(self):
        return self._card()._repr_html_()

    def __repr__(self):
        return repr(self._card())

    def to_dataframe(self, date=None):
        """One row per reach: record, lowest and highest level, and the index on `date` (default: today)"""
        d = self.as_of if date is None else _date(date)
        now = index_at(self.table, self.levels, d, self.params)
        out = self.table.drop(columns=["why"]).merge(now.reset_index(), on="reach_id", how="left")
        out["band_name"] = [band_label(b) if b >= 0 else "" for b in out.band]
        out["type_name"] = out.type.map(SWORD_TYPES)
        return out

    def _network(self):
        if self._net is None:
            self._net = network(self.table)
        return self._net

    # --- steps ------------------------------------------------------------------------------------------------
    @_needs_data
    def coverage(self):
        """How many good SWOT levels each reach has · map and counts"""
        from . import navplots
        tab = self.table
        why = tab.why.replace("", "index possible")
        counts = why.value_counts().rename_axis("reach").rename("reaches").reset_index()
        shown = counts.assign(reach=[t("nv_why_" + w.replace(" ", "_")) for w in counts.reach])
        good = tab[tab.n_good > 0]
        per_year = good.n_good / ((self.as_of - pd.Timestamp("2023-07-26")).days / 365.25)
        lines = [("nv_cov_line", dict(n=fmt_int(len(tab)), measured=fmt_int(int((tab.n_levels > 0).sum())),
                                      none=fmt_int(int((tab.n_levels == 0).sum())),
                                      median=f"{good.n_good.median():.0f}" if len(good) else "0",
                                      per_year=f"{per_year.median():.0f}" if len(good) else "0")),
                 ("nv_cov_width", dict(**_width_split(tab)))]
        return Result(("nv_h_coverage", {"name": self.name}), lines,
                      figure=lambda: navplots.fig_coverage(tab, self._network(), self.name),
                      table=counts, display_table=_columns(shown, {"reach": "why", "reaches": "reaches"}),
                      values=dict(reaches=len(tab), measured=int((tab.n_levels > 0).sum())))

    @_needs_data
    def cleaning(self):
        """Which SWOT levels are removed, and why"""
        lv = self.levels
        counts = lv.reason.value_counts().rename("count").rename_axis("reason").reset_index()
        kept = int((lv.reason == "kept").sum())

        def shown():
            return pd.DataFrame({t("nv_col_reason"): counts.reason.map(reason_label), t("nv_col_levels"): counts["count"],
                                 "%": (100 * counts["count"] / max(len(lv), 1)).round(1)})
        p = self.params
        dark = M("nv_clean_dark", dark=round(100 * p.max_dark_frac)) if p.max_dark_frac < 1 else ""
        return Result(("nv_h_cleaning", {}),
                      [("nv_clean_line", dict(kept=fmt_int(kept), total=fmt_int(len(lv)), pct=f"{100 * kept / max(len(lv), 1):.0f}")),
                       ("nv_clean_rules", dict(q=p.max_reach_q, x=p.max_xovr_q, dark=dark, k=p.k_mad,
                                              jump=p.jump_m, k_jump=p.jump_k, days=p.jump_days))],
                      table=counts, display_table=shown,
                      values=dict(kept=kept, total=len(lv), reasons={str(r): int(n) for r, n in zip(counts.reason, counts["count"])}))

    @_needs_data
    def ranges(self):
        """The lowest and highest level recorded on each reach, and the range between them"""
        from . import navplots
        tab = self.table
        ok = tab[tab.why == ""]
        p = self.params
        by_river = (ok[ok.river_name != "—"].groupby("river_name", observed=True)
                    .agg(reaches=("reach_id", "size"), median_range_m=("range_m", "median"),
                         largest_range_m=("range_m", "max"))
                    .query("reaches >= 5").sort_values("median_range_m", ascending=False).round(2))
        lines = [("nv_range_line", dict(n=fmt_int(len(ok)), med=f"{ok.range_m.median():.1f}" if len(ok) else "—",
                                        lo=f"{ok.range_m.quantile(0.1):.1f}" if len(ok) else "—",
                                        hi=f"{ok.range_m.quantile(0.9):.1f}" if len(ok) else "—")),
                 ("nv_range_rules", dict(n=p.min_levels, days=p.min_span_days, m=p.min_range_m, noise=p.max_noise_m,
                                         frac=round(100 * p.max_noise_frac), n_noisy=fmt_int(int((tab.why == "too noisy").sum()))))]
        if len(by_river):
            top = by_river.head(3)
            lines.append(("nv_range_rivers", dict(rivers=", ".join(f"{r} ({v:.1f} m)" for r, v in top.median_range_m.items()))))
        return Result(("nv_h_ranges", {"name": self.name}), lines,
                      figure=lambda: navplots.fig_ranges(tab, self._network(), self.name),
                      table=by_river, table_rows=15,
                      display_table=_columns(by_river.rename_axis(t("nv_col_river")),
                                             {"reaches": "reaches", "median_range_m": "median_range",
                                              "largest_range_m": "largest_range"}),
                      values=dict(reaches=len(ok), median_range_m=float(ok.range_m.median()) if len(ok) else np.nan))

    @_needs_data
    def navigability(self, date=None):
        """The navigability index on `date` (default: today): a map, and how much of the river is in each band"""
        from . import navplots
        d = self.as_of if date is None else _date(date)
        df = self.to_dataframe(d)
        has = df[df["index"].notna()]
        km = has.length_km.fillna(has.length_km.median() if has.length_km.notna().any() else 10)
        bands = pd.DataFrame({"band": [t(k) for _, k, _ in BANDS],
                              "reaches": [int((has.band == i).sum()) for i in range(5)],
                              "river km": [int(round(km[has.band == i].sum())) for i in range(5)]})
        bands["% of river km"] = (100 * bands["river km"] / max(bands["river km"].sum(), 1)).round(0)
        lines = [("nv_index_line", dict(n=fmt_int(len(has)), total=fmt_int(len(df)), km=fmt_int(round(km.sum())),
                                        date=_day(d), days=self.params.max_age_days)),
                 ("nv_index_formula", {})]
        if len(has):
            lines.append(("nv_index_median", dict(med=f"{has['index'].median():.0f}",
                                                  low=f"{100 * km[has.band <= 1].sum() / km.sum():.0f}",
                                                  high=f"{100 * km[has.band >= 3].sum() / km.sum():.0f}")))
            rivers = (has[has.river_name != "—"].groupby("river_name", observed=True)["index"]
                      .agg(["median", "size"]).query("size >= 5").sort_values("median"))
            k = min(3, len(rivers) // 2)                     # never the same river in both lists
            if k:
                lines.append(("nv_index_rivers", dict(
                    date=_day(d), low=", ".join(f"{r} ({v:.0f})" for r, v in rivers["median"].head(k).items()),
                    high=", ".join(f"{r} ({v:.0f})" for r, v in rivers["median"].tail(k)[::-1].items()))))
        why = df[df["index"].isna()].why.value_counts()
        if len(why):
            lines.append(("nv_index_none", dict(n=fmt_int(int(why.sum())), why=_why_list(why))))
        return Result(("nv_h_index", {"name": self.name, "date": _day(d)}), lines,
                      figure=lambda: navplots.fig_index_map(df, self._network(), self.name, _day(d), self._ports()),
                      table=bands, display_table=_columns(bands, {"band": "band", "reaches": "reaches",
                                                                  "river km": "river_km", "% of river km": "pct_km"}),
                      values=dict(date=f"{d:%Y-%m-%d}", reaches=len(has),
                                               median_index=float(has["index"].median()) if len(has) else np.nan,
                                               bands=dict(zip(bands.band, bands.reaches))))

    @_needs_data
    def map(self, date=None):
        """Interactive map of the navigability index: click a river for its numbers"""
        from . import navplots
        d = self.as_of if date is None else _date(date)
        return navplots.index_folium(self.to_dataframe(d), self._network(), self.name, _day(d), self._ports())

    def _find(self, reach_id):
        rid = int(str(reach_id).strip())
        if rid not in set(self.table.reach_id):
            raise KeyError(rid)
        return rid

    @_needs_data
    def reach(self, reach_id, date=None):
        """One reach: its SWOT levels, lowest and highest level, and its index"""
        from . import navplots
        try:
            rid = self._find(reach_id)
        except (KeyError, ValueError):
            return Result(("nv_h_reach", {"reach": reach_id, "river": "?"}), [("nv_reach_unknown", dict(reach=reach_id))])
        d = self.as_of if date is None else _date(date)
        row = self.to_dataframe(d).set_index("reach_id").loc[rid]
        lv = self.levels[self.levels.reach_id == rid]
        lines = [("nv_reach_where", dict(river=row.river_name, lat=f"{row.lat:.3f}", lon=f"{row.lon:.3f}",
                                         width=fmt_int(row.width_m) if np.isfinite(row.width_m) else "—",
                                         type=M(f"nv_type_{int(row.type)}") if f"nv_type_{int(row.type)}" in MESSAGES
                                         else row.type_name))]
        if row.n_good:
            lines.append(("nv_reach_record", dict(good=row.n_good, total=row.n_levels, first=_day(row["first"]),
                                                  last=_day(row["last"]))))
            lines.append(("nv_reach_range", dict(lo=f"{row.low_m:.2f}", lo_date=_day(row.low_date), hi=f"{row.high_m:.2f}",
                                                 hi_date=_day(row.high_date), range=f"{row.range_m:.2f}",
                                                 noise=f"{row.noise_m:.2f}" if np.isfinite(row.noise_m) else "—")))
        if np.isfinite(row["index"]):
            lines.append(("nv_reach_index", dict(now=f"{row.now_m:.2f}", date=_day(row.now_date), index=f"{row['index']:.0f}",
                                                 band=M(BANDS[int(row.band)][1]))))
        else:
            lines.append(("nv_reach_no_index", dict(why=_why(row.why))))
        lines.append(("nv_reach_station", dict(reach=rid)))
        return Result(("nv_h_reach", {"reach": rid, "river": row.river_name}), lines,
                      figure=(lambda: navplots.fig_reach(lv, row, rid, d)) if len(lv) else None,
                      values=dict(reach_id=rid, index=float(row["index"]), range_m=float(row.range_m),
                                  low_m=float(row.low_m), high_m=float(row.high_m)))

    def _ports(self):
        ids = set(self.table.reach_id)
        idx = reach_index().set_index("reach_id")
        return [dict(name=n, river=r, reach_id=rid, lat=float(idx.lat[rid]), lon=float(idx.lon[rid]))
                for n, r, rid in self.region.get("ports", []) if rid in ids]

    @_needs_data
    def ports(self, date=None):
        """The index through time at river ports, one panel each"""
        from . import navplots
        d = self.as_of if date is None else _date(date)
        ports = self._ports()
        if not ports:
            return Result(("nv_h_ports", {"name": self.name}), [("nv_ports_none", {})])
        now = self.to_dataframe(d).set_index("reach_id")
        rows, series = [], {}
        for p in ports:
            r = now.loc[p["reach_id"]]
            rows.append({"port": p["name"], "river": p["river"], "reach": p["reach_id"],
                         "range (m)": round(float(r.range_m), 2) if np.isfinite(r.range_m) else np.nan,
                         "latest level": f"{_day(r.now_date)}" if pd.notna(r.now_date) else "—",
                         "index": round(float(r["index"])) if np.isfinite(r["index"]) else np.nan,
                         "band": band_label(int(r.band)) if r.band >= 0 else t("nv_why_" + r.why.replace(" ", "_"))})
            if r.why in ("", "no recent level") and np.isfinite(r.range_m):
                series[f"{p['name']} ({p['river']})"] = (series_index(self.levels, self.table, p["reach_id"]), r)
        table = pd.DataFrame(rows)
        return Result(("nv_h_ports", {"name": self.name}), [("nv_ports_line", dict(date=_day(d)))],
                      figure=(lambda: navplots.fig_ports(series, d)) if series else None,
                      table=table, values=dict(zip(table.port, table["index"])),
                      display_table=_columns(table, {"port": "port", "river": "river", "reach": "reach",
                                                     "range (m)": "range", "latest level": "latest", "index": "index",
                                                     "band": "band"}))

    @_needs_data
    def profile(self, date=None, start=None):
        """Along the main river, down to the sea: the range of levels and the index on `date`"""
        from . import navplots
        d = self.as_of if date is None else _date(date)
        start = start or self.region.get("main_start")
        if not start:
            return Result(("nv_h_profile", {"river": "?"}), [("nv_profile_none", {})])
        path = main_stem(self.table, start)
        now = self.to_dataframe(d).set_index("reach_id")
        path = path.join(now[["range_m", "low_m", "high_m", "now_m", "index", "band", "why"]], on="reach_id")
        path["band"] = path.band.fillna(-1).astype(int)
        path["why"] = path.why.fillna("ghost reach")
        river = self.region.get("main_name", M("nv_main_default"))
        has = path[path["index"].notna()]
        lines = [("nv_profile_line", dict(river=river, n=len(path), km=fmt_int(round(path.dist_out_km.max())),
                                          with_index=len(has), date=_day(d)))]
        return Result(("nv_h_profile", {"river": river}), lines,
                      figure=lambda: navplots.fig_profile(path, self._ports(), river, _day(d)),
                      table=path[["reach_id", "river_name", "dist_out_km", "range_m", "index"]].round(1),
                      display_table=_columns(path.assign(dist_out_km=path.dist_out_km.round().astype(int))[
                          ["reach_id", "river_name", "dist_out_km", "range_m", "index"]].round(1),
                          {"reach_id": "reach", "river_name": "river", "dist_out_km": "dist", "range_m": "range",
                           "index": "index"}),
                      values=dict(reaches=len(path), with_index=len(has)))

    @_needs_data
    def history(self, freq="MS"):
        """How much of the river network was at low or high water, through time (every first of the month)"""
        from . import navplots
        t0 = self.levels[self.levels.reason == "kept"].time.min()
        dates = pd.date_range(pd.Timestamp(t0).normalize() + pd.Timedelta(days=self.params.max_age_days),
                              self.as_of, freq=freq)
        km = self.table.set_index("reach_id").length_km
        km = km.fillna(km.median() if km.notna().any() else 10)
        rows = []
        for day in list(dates) + [self.as_of]:
            now = index_at(self.table, self.levels, _date(day), self.params)
            w = km.reindex(now.index)
            has = now.band >= 0
            total = w[has].sum()
            rows.append({"date": pd.Timestamp(day).normalize(), "reaches": int(has.sum()),
                         **{t(BANDS[b][1]): 100 * w[now.band == b].sum() / total if total else np.nan for b in range(5)}})
        hist = pd.DataFrame(rows).drop_duplicates("date", keep="last").set_index("date")
        low = hist[[t(BANDS[0][1]), t(BANDS[1][1])]].sum(axis=1)
        worst = low.idxmax() if low.notna().any() else None
        lines = [("nv_hist_line", dict(n=len(hist), days=self.params.max_age_days))]
        if worst is not None:
            lines.append(("nv_hist_worst", dict(date=Day(worst, month=True), pct=f"{low.max():.0f}",
                                                now=f"{low.iloc[-1]:.0f}")))
        return Result(("nv_h_history", {"name": self.name}), lines,
                      figure=lambda: navplots.fig_history(hist, self.name), table=hist.round(0).tail(12),
                      display_table=_columns(hist.round(0).tail(12), {"reaches": "reaches"}),
                      values=dict(months=len(hist)))

    @_needs_data
    def export(self, date=None, levels=False):
        """Write into outputs/ the table (CSV), the rivers with their index (GeoPackage for QGIS, and GeoJSON) and
        the settings (JSON). levels=True also puts every SWOT level into the GeoPackage (about 30 MB more)."""
        from . import geopackage, navplots
        d = self.as_of if date is None else _date(date)
        df = self.to_dataframe(d)
        out = settings.out_dir()
        out.mkdir(parents=True, exist_ok=True)
        stem = f"navigability_{self.key}_{d:%Y-%m-%d}"
        cols = ["reach_id", "river_name", "lat", "lon", "width_m", "type_name", "n_good", "first", "last", "low_m",
                "low_date", "high_m", "high_date", "range_m", "noise_m", "now_m", "now_date", "age_days", "index", "band_name",
                "why"]
        f_csv = out / f"{stem}.csv"
        df[cols].round({"low_m": 3, "high_m": 3, "range_m": 3, "now_m": 3}).to_csv(f_csv, index=False)
        meta = {"date": f"{d:%Y-%m-%d}", "index": "100 × (latest level − lowest level) / (highest − lowest)",
                "source": "SWOT L2 HR RiverSP reach, Version D (NASA/CNES, PO.DAAC), via Hydrocron",
                "params": asdict(self.params)}
        f_gpkg = out / f"{stem}.gpkg"
        layers = geopackage.write(f_gpkg, df, self._network(), self._ports(), BANDS, NO_INDEX_C,
                                  levels=self.levels if levels else None,
                                  about={"title": f"{self.name} — {t('nv_lab_index')} {d:%Y-%m-%d}",
                                         **{k: v for k, v in meta.items() if k != "params"},
                                         **{f"param_{k}": v for k, v in meta["params"].items()}})
        f_geo = out / f"{stem}.geojson"
        f_geo.write_text(json.dumps(navplots.index_geojson(df, self._network(), full=True)))
        f_meta = out / f"{stem}_metadata.json"
        f_meta.write_text(json.dumps(meta, indent=1))
        lines = [("export_line", dict(path=str(f))) for f in (f_csv, f_gpkg, f_geo, f_meta)]
        lines.append(("nv_export_qgis", dict(layers=", ".join(layers))))
        return Result(("h_export", {}), lines, values=dict(csv=str(f_csv), gpkg=str(f_gpkg), geojson=str(f_geo),
                                                           metadata=str(f_meta)))

    @_needs_data
    def download_geopackage(self, date=None, levels=False):
        """Save the GeoPackage (rivers, ports and their index; levels=True: every SWOT level too) on your computer.
        On Colab the browser downloads it; on your own computer it is already in outputs/ — click the link."""
        f = Path(self.export(date, levels=levels).values["gpkg"])
        size = f"{f.stat().st_size / 1e6:.1f}"
        if _on_colab():
            from google.colab import files
            files.download(str(f))
            lines = [("nv_dl_colab", dict(name=f.name, size=size))]
            link = None
        else:
            lines = [("nv_dl_local", dict(path=str(f.resolve()), size=size))]
            link = _link(f)
        layers = "reaches, ports" + (", levels" if levels else "")
        return Result(("nv_h_download", {}), lines + [("nv_export_qgis", dict(layers=layers))], extra_html=link,
                      values=dict(gpkg=str(f)))


def _on_colab():
    return "google.colab" in sys.modules


def _link(f):
    """A download link to a file under the notebook's folder (Jupyter serves it), else nothing"""
    rel = os.path.relpath(f.resolve(), Path.cwd())
    if rel.startswith(".."):
        return None
    href = html_mod.escape(Path(rel).as_posix(), quote=True)
    return (f'<a href="{href}" download="{html_mod.escape(f.name, quote=True)}" style="font-family:system-ui,sans-serif">'
            f'⬇ {html_mod.escape(t("nv_dl_link", name=f.name))}</a>')


def _width_split(tab):
    measured = tab.why == ""
    narrow = tab.width_m < 100
    return dict(wide=f"{100 * measured[~narrow].mean():.0f}" if (~narrow).any() else "—",
                narrow=f"{100 * measured[narrow].mean():.0f}" if narrow.any() else "—")


def river_survey(region="congo", *, reach_ids=None, download=True, update_days=3, workers=8, name=None,
                 **settings_):
    """Every SWOT reach of a basin: download (or update) the levels, clean them, find the range and the index.

    region        "congo" (every SWORD reach of the Congo basin), or give reach_ids=[...] for your own list
    download      True: download every reach not saved in the last `update_days` days (about 10 min for the whole
                  Congo the first time; an interrupted download continues where it stopped). False: use the saved copy.
    workers       how many reaches to download at the same time
    name          a title for your own list of reaches
    other keywords change the settings (see vg.SurveyParams), e.g. max_age_days=45, min_levels=20, jump_m=0.5
    """
    names = {f.name for f in fields(SurveyParams)}
    unknown = sorted(set(settings_) - names)
    if unknown:
        raise TypeError(f"Unknown setting(s): {unknown}. Settings: {sorted(names)}")
    params = replace(SurveyParams(), **settings_)
    key = region if reach_ids is None else "custom_" + hashlib.sha1(
        ",".join(sorted(str(int(r)) for r in reach_ids)).encode()).hexdigest()[:10]
    title = name or (REGIONS[region]["name"] if reach_ids is None and region in REGIONS else M("nv_your_reaches"))
    try:
        meta = region_reach_list(region, reach_ids)
    except ValueError as e:
        return RiverSurvey.unavailable(key, title, str(e))
    if meta.empty:
        return RiverSurvey.unavailable(key, title, t("nv_err_no_reaches"))
    ids = list(meta.reach_id)
    counts, origin = None, None
    if download and not settings.offline():
        folder = survey_folder()
        counts = download_reaches(ids, folder, update_days=update_days, workers=workers)
        if counts["ok"] + counts["no data"] + counts["saved"]:
            new = counts["ok"] + counts["no data"]
            cached = [settings.cache_dir() / n for n in _names(key)]
            if not new and all(p.exists() for p in cached):
                levels, reaches, origin = _saved(key, ids)
            if origin is None:
                levels, reaches = combine(ids, folder)
                _save(key, levels, reaches)
                origin = "download" if new else "cache"
        else:
            say("nv_download_failed")
    if origin is None:
        levels, reaches, origin = _saved(key, ids)
        if origin is None:
            why = t("nv_err_offline") if (settings.offline() or not download) else t("nv_err_download")
            return RiverSurvey.unavailable(key, title, why)
    return RiverSurvey(key, title, meta, reaches, levels, params, origin=origin, counts=counts)
