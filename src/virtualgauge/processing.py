"""Steps 0–5: from satellite points to a virtual-station water-level series.

Étapes 0 à 5 : des points satellitaires à la série de niveaux d'une station virtuelle.

Copied from the trainer notebook (Steps 0, 2, 3, 4, 5 and Part C `build_virtual_station`). The only changes:
settings arrive as arguments instead of notebook globals, and summary tables use English keys.
"""
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry.polygon import orient
from scipy import stats


def utc_naive(x):
    """Convert times to UTC without time-zone · Convertir les dates en UTC sans fuseau"""
    t = pd.to_datetime(x, utc=True, errors="coerce")
    if isinstance(t, pd.Series):
        return t.dt.tz_convert(None).dt.as_unit("ns")
    return t.tz_convert(None).as_unit("ns")


def robust_spread(x):
    """1.4826 × MAD ≈ standard deviation for well-behaved data · ≈ écart-type pour des données régulières"""
    x = np.asarray(x, float)
    return 1.4826 * np.median(np.abs(x - np.median(x)))


# --- Step 0 ----------------------------------------------------------------------------------------------
def channel_mask(line_gdf, width_m, frac):
    """Widen the centre-line into a water-mask polygon · Élargir la ligne centrale en masque d'eau"""
    utm = line_gdf.estimate_utm_crs()
    line_utm = line_gdf.to_crs(utm).geometry.iloc[0]
    mask_utm = line_utm.buffer(width_m * frac, cap_style="flat")
    mask_ll = gpd.GeoSeries([mask_utm], crs=utm).to_crs(4326).iloc[0]
    mask_ll = orient(mask_ll.simplify(0.0003), 1.0)
    return dict(utm=utm, line_utm=line_utm, mask_utm=mask_utm, mask_ll=mask_ll,
                length_km=line_utm.length / 1000)


# --- Step 2 ----------------------------------------------------------------------------------------------
def prepare_atl13(gdf, geo, h_range=None, max_cloud=2, k_mad=3.0, min_spread=0.15):
    """Label every ICESat-2 point as kept or removed (with the reason), add distance along the river.
    Étiqueter chaque point ICESat-2 (gardé ou retiré, avec la raison), ajouter la distance le long de la rivière."""
    p = gdf.to_crs(geo["utm"]).reset_index()
    p = p[p.within(geo["mask_utm"])].reset_index(drop=True)
    p["time"] = utc_naive(p["time_ns"] if "time_ns" in p else p[p.columns[0]])
    p["s_km"] = [geo["line_utm"].project(pt) / 1000 for pt in p.geometry]
    p["pass_id"] = p["time"].dt.strftime("%Y-%m-%d") + "_rgt" + p["rgt"].astype(str)
    p["reason"] = "kept"
    lo, hi = h_range or (-np.inf, np.inf)
    p.loc[(p.ht_ortho < lo) | (p.ht_ortho > hi), "reason"] = "1 impossible level"
    kept = p.reason == "kept"
    p.loc[kept & (p.inland_water_body_type != 5), "reason"] = "2 not river"
    kept = p.reason == "kept"
    p.loc[kept & (p.cloud_flag_asr_atl09 > max_cloud), "reason"] = "3 cloudy"
    kept = p.reason == "kept"
    if kept.any():
        grp = p[kept].groupby("pass_id").ht_ortho
        med, spr = grp.transform("median"), grp.transform(robust_spread)
        outlier = (p.loc[kept, "ht_ortho"] - med).abs() > k_mad * np.maximum(spr, min_spread)
        p.loc[outlier.index[outlier], "reason"] = "4 outlier in pass"
    return p


# --- Step 3 ----------------------------------------------------------------------------------------------
def estimate_slope(p, min_points=20, min_span_km=2.0):
    """Water-surface slope (m/km, positive = rising upstream) for each long-enough pass.
    Pente de la surface de l'eau (m/km, positive = montée vers l'amont) pour chaque passage assez long."""
    rows = []
    for pid, g in p[p.reason == "kept"].groupby("pass_id"):
        span = g.s_km.max() - g.s_km.min()
        if len(g) >= min_points and span >= min_span_km:
            rows.append(dict(pass_id=pid, slope_m_per_km=stats.theilslopes(g.ht_ortho, g.s_km)[0],
                             n_points=len(g), span_km=span))
    return pd.DataFrame(rows, columns=["pass_id", "slope_m_per_km", "n_points", "span_km"])


def per_pass_levels(p, slope_m_per_km, s_ref_km, min_points=5, u_floor=0.10):
    """One water level per satellite pass: the virtual-station time series.
    Un niveau d'eau par passage : la série temporelle de la station virtuelle."""
    k = p[p.reason == "kept"].copy()
    k["h_corr"] = k.ht_ortho - slope_m_per_km * (k.s_km - s_ref_km)
    vs = (k.groupby("pass_id")
            .agg(time=("time", "median"), wse_m=("h_corr", "median"), n_points=("h_corr", "size"),
                 spread_m=("h_corr", robust_spread), span_km=("s_km", lambda s: s.max() - s.min()))
            .reset_index())
    vs = vs[vs.n_points >= min_points].sort_values("time").reset_index(drop=True)
    vs["wse_u_m"] = np.sqrt((1.253 * vs.spread_m) ** 2 / vs.n_points + u_floor ** 2)
    vs["source"] = "ICESat-2"
    return vs


def sampling_summary(times):
    """How often is the river observed? · À quelle fréquence la rivière est-elle observée ?"""
    t = pd.Series(pd.to_datetime(times)).sort_values()
    if len(t) < 2:
        return dict(observations=len(t), first=None, last=None, per_year=np.nan,
                    median_gap_days=np.nan, longest_gap_days=np.nan)
    gaps = t.diff().dt.total_seconds() / 86400
    years = (t.max() - t.min()).days / 365.25
    return dict(observations=len(t), first=f"{t.min():%Y-%m-%d}", last=f"{t.max():%Y-%m-%d}",
                per_year=round(len(t) / years, 1) if years > 0 else np.nan,
                median_gap_days=round(gaps.median(), 1), longest_gap_days=round(gaps.max(), 1))


# --- Step 4 ----------------------------------------------------------------------------------------------
def clean_swot(df, h_range=None, max_reach_q=1, max_xovr_q=1):
    """Label each SWOT observation as kept or removed (with the reason).
    Étiqueter chaque observation SWOT comme gardée ou retirée (avec la raison)."""
    s = df.copy().reset_index(drop=True)
    s["reason"] = "kept"
    if s.empty:
        s["time"] = pd.Series(dtype="datetime64[ns]")
        return s
    nodata = (s.time_str == "no_data") | (s.wse < -1e10)
    s.loc[nodata, "reason"] = "0 not observed"
    s["time"] = utc_naive(s.time_str.where(~nodata))
    s.loc[~nodata & s.duplicated(subset=["time_str"]), "reason"] = "0 duplicate"
    lo, hi = h_range or (-np.inf, np.inf)
    k = s.reason == "kept"
    s.loc[k & ((s.wse < lo) | (s.wse > hi)), "reason"] = "1 impossible level"
    k = s.reason == "kept"
    s.loc[k & (s.reach_q > max_reach_q), "reason"] = f"2 reach_q > {max_reach_q}"
    k = s.reason == "kept"
    s.loc[k & (s.xovr_cal_q > max_xovr_q), "reason"] = f"3 xovr_cal_q > {max_xovr_q}"
    return s


def hydraulic_check(main, up=None, down=None, tol_m=0.3):
    """Flag passes where the reach is higher than the reach upstream, or lower than the reach downstream.
    Signaler les passages où le tronçon est plus haut que l'amont, ou plus bas que l'aval."""
    m = main.copy()
    key = ["cycle_id", "pass_id"]
    for nb, sign, label in [(up, 1, "4 higher than upstream"), (down, -1, "4 lower than downstream")]:
        if nb is None or nb.empty or m.empty:
            continue
        nbk = nb[nb.reason == "kept"][key + ["wse"]].drop_duplicates(key).rename(columns={"wse": "wse_nb"})
        j = m[key].merge(nbk, on=key, how="left")
        bad = (m.reason == "kept").to_numpy() & (sign * (m.wse.to_numpy() - j.wse_nb.to_numpy()) > tol_m)
        m.loc[bad, "reason"] = label
    return m


# --- Step 5 ----------------------------------------------------------------------------------------------
def intermission_pairs(vs_ice, swot_ok, max_days=3):
    """ICESat-2 and SWOT levels measured within max_days of each other.
    Niveaux ICESat-2 et SWOT mesurés à moins de max_days d'intervalle."""
    cols = ["time", "wse_m", "time_swot", "wse_swot", "days_apart", "difference_m"]
    if vs_ice.empty or swot_ok.empty:
        return pd.DataFrame(columns=cols)
    a = vs_ice[["time", "wse_m"]].sort_values("time")
    b = swot_ok[["time", "wse"]].rename(columns={"time": "time_swot", "wse": "wse_swot"}).sort_values("time_swot")
    p = pd.merge_asof(a, b, left_on="time", right_on="time_swot", direction="nearest",
                      tolerance=pd.Timedelta(days=max_days)).dropna(subset=["wse_swot"])
    p["days_apart"] = ((p.time - p.time_swot).dt.total_seconds() / 86400).round(1)
    p["difference_m"] = p.wse_m - p.wse_swot
    return p


def combine_levels(vs_ice, swot_ok, offset_m):
    """One table of levels from both satellites, on SWOT's reference · Une table commune, référence SWOT"""
    cols = ["time", "wse_m", "wse_u_m", "source"]
    a = vs_ice.assign(wse_m=vs_ice.wse_m - offset_m)[cols] if not vs_ice.empty else pd.DataFrame(columns=cols)
    b = (swot_ok.assign(source="SWOT").rename(columns={"wse": "wse_m", "wse_u": "wse_u_m"})[cols]
         if not swot_ok.empty else pd.DataFrame(columns=cols))
    return pd.concat([x for x in (a, b) if len(x)] or [pd.DataFrame(columns=cols)]).sort_values("time").reset_index(drop=True)


def catch_probability(times, start, end, durations=(1, 2, 3, 5, 10, 30)):
    """Share of all D-day windows containing at least one observation · Part des fenêtres de D jours observées"""
    days = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq="D")
    obs = pd.Series(days.isin(pd.to_datetime(pd.Series(times)).dt.normalize()).astype(float), index=days)
    return pd.Series({d: obs.rolling(d).max().shift(-(d - 1)).dropna().mean() for d in durations})


# --- Steps 0–5 together (trainer Part C) ----------------------------------------------------------------------
def build_virtual_station(site, params, loaders):
    """Steps 0–5 for one site: mask, ICESat-2, SWOT, checks, combined levels.
    Étapes 0 à 5 pour un site : masque, ICESat-2, SWOT, contrôles, niveaux combinés.

    `loaders` gives the download functions (so tests can swap them): reach_line, fetch_atl13, hydrocron_reach.
    """
    line = loaders["reach_line"](site.swot_reach)
    geo = channel_mask(line, site.mask_width_m, site.mask_frac)
    raw = loaders["fetch_atl13"](site.key, geo["mask_ll"], site.t0)
    pts = prepare_atl13(raw, geo, h_range=site.h_range, max_cloud=params.max_cloud, k_mad=params.k_mad,
                        min_spread=params.min_spread)
    slopes = estimate_slope(pts, params.min_points_slope, params.min_span_km)
    slope = slopes.slope_m_per_km.median() if (site.slope_correction and len(slopes)) else 0.0
    vs_ice = per_pass_levels(pts, slope, s_ref_km=geo["length_km"] / 2, min_points=params.min_points_pass,
                             u_floor=params.u_floor)
    sw = {rid: clean_swot(loaders["hydrocron_reach"](rid), h_range=site.h_range,
                          max_reach_q=params.max_reach_q, max_xovr_q=params.max_xovr_q)
          for rid in [site.swot_reach, site.swot_up, site.swot_down] if rid}
    if params.neighbour_check:
        main = hydraulic_check(sw[site.swot_reach], sw.get(site.swot_up), sw.get(site.swot_down), tol_m=params.tol_m)
    else:
        main = sw[site.swot_reach]
    swot_ok = main[main.reason == "kept"].sort_values("time").reset_index(drop=True)
    pairs = intermission_pairs(vs_ice, swot_ok, max_days=params.max_days)
    offset = pairs.difference_m.median() if len(pairs) >= 3 else 0.0
    return dict(line=line, geo=geo, raw=raw, points=pts, slopes=slopes, slope=slope, vs_ice=vs_ice,
                swot=sw, swot_main=main, swot_ok=swot_ok, pairs=pairs, offset=offset,
                vs=combine_levels(vs_ice, swot_ok, offset))
