"""Downloads from open services (no login) · Téléchargements depuis des services ouverts (sans compte).

Copied from the trainer notebook (cells: download helpers, Step 1, Step 4, Step 5 DAHITI, Step 7 GEOGloWS,
Part D lookup). Only changes: files go through `store.load_or_fetch`, messages through `i18n`.
"""
import io
import json
import logging
import os
import re
import time

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import shape

from . import store
from .i18n import t

HYDROCRON = "https://soto.podaac.earthdatacloud.nasa.gov/hydrocron/v1/timeseries"
GEOGLOWS = "https://geoglows.ecmwf.int/api/v2"
SWOT_GIS = ("https://gis.earthdata.nasa.gov/portal/rest/services/C3233944997_POCLOUD/"
            "SWOT_L2_HR_RiverSP_reach_vD_Attributes/FeatureServer/1/query")
SWOT_FIELDS = ["reach_id", "time_str", "cycle_id", "pass_id", "wse", "wse_u", "wse_r_u", "width", "slope",
               "reach_q", "reach_q_b", "dark_frac", "xovr_cal_q", "ice_clim_f", "partial_f", "n_good_nod",
               "obs_frac_n", "xtrk_dist", "p_lat", "p_lon", "p_width", "river_name", "crid"]
ATL13_EXTRA = ["inland_water_body_type", "cloud_flag_asr_atl09"]
_DTYPES = {"reach_id": str, "cycle_id": str, "pass_id": str}


def today():
    return pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")


def http_get(url, params=None, timeout=120, tries=3):
    """GET request with a few retries · Requête GET avec quelques nouvelles tentatives"""
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code < 500:
                return r
        except requests.RequestException as e:
            print(f"  {t('msg_retry')} ({e.__class__.__name__})")
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"{t('msg_download_failed', name=url)}")


# --- SWOT (Hydrocron) --------------------------------------------------------------------------------------
def reach_line(reach_id, refresh=None):
    """Centre-line of a SWOT/SWORD reach (from Hydrocron GeoJSON) · Ligne centrale d'un tronçon"""
    def fetch():
        params = dict(feature="Reach", feature_id=reach_id, output="geojson",
                      fields="reach_id,time_str,river_name,p_width,p_length,geometry",
                      start_time="2023-07-01T00:00:00Z", end_time=f"{today()}T23:59:59Z")
        r = http_get(HYDROCRON, params)
        r.raise_for_status()
        feats = [ft for ft in r.json()["results"]["geojson"]["features"]
                 if ft.get("geometry") and ft["geometry"].get("coordinates")]
        props = {k: feats[0]["properties"].get(k) for k in ["reach_id", "river_name", "p_width", "p_length"]}
        return gpd.GeoDataFrame([props], geometry=[shape(feats[0]["geometry"])], crs=4326), r.url
    return store.load_or_fetch(f"swot_reach_{reach_id}_line.geojson", gpd.read_file, fetch,
                               lambda g, p: g.to_file(p, driver="GeoJSON"), refresh=refresh)


def hydrocron_reach(reach_id, start="2023-07-01", end=None, refresh=None):
    """SWOT time series for one river reach (Hydrocron, no login).
    Série temporelle SWOT d'un tronçon (Hydrocron, sans identifiant)."""
    def fetch():
        params = dict(feature="Reach", feature_id=reach_id, output="csv", fields=",".join(SWOT_FIELDS),
                      start_time=f"{start}T00:00:00Z", end_time=f"{end or today()}T23:59:59Z")
        r = http_get(HYDROCRON, params)
        if r.status_code == 400:      # Hydrocron answers 400 when there is no data · 400 = pas de données
            print(t("msg_no_swot", reach=reach_id))
            return None, r.url
        r.raise_for_status()
        return pd.read_csv(io.StringIO(r.json()["results"]["csv"]), dtype=_DTYPES), r.url
    df = store.load_or_fetch(f"swot_reach_{reach_id}.csv", lambda p: pd.read_csv(p, dtype=_DTYPES), fetch,
                             lambda d, p: d.to_csv(p, index=False), refresh=refresh)
    return pd.DataFrame(columns=SWOT_FIELDS) if df is None else df


def reach_info(reach_id, refresh=None):
    """Neighbours and prior position of a reach (Hydrocron) · Voisins et position a priori d'un tronçon"""
    fields = "reach_id,time_str,wse,width,p_lat,p_lon,p_width,river_name,rch_id_up,rch_id_dn"

    def fetch():
        params = dict(feature="Reach", feature_id=reach_id, output="csv", fields=fields,
                      start_time="2023-07-01T00:00:00Z", end_time=f"{today()}T23:59:59Z")
        r = http_get(HYDROCRON, params)
        if r.status_code == 400:
            return None, r.url
        r.raise_for_status()
        return pd.read_csv(io.StringIO(r.json()["results"]["csv"]), dtype={"reach_id": str}), r.url
    return store.load_or_fetch(f"swot_reach_{reach_id}_info.csv", lambda p: pd.read_csv(p, dtype={"reach_id": str}),
                               fetch, lambda d, p: d.to_csv(p, index=False), refresh=refresh)


def find_swot_reaches(lat, lon, radius_m=3000, days=30):
    """SWOT reaches observed near a point in a recent month (NASA Earthdata GIS service — slow, 1–3 min).
    Tronçons SWOT observés près d'un point au cours d'un mois récent (service SIG NASA — lent, 1 à 3 min)."""
    t1 = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=10)
    t0 = t1 - pd.Timedelta(days=days)
    params = dict(where="1=1", geometry=f"{lon},{lat}", geometryType="esriGeometryPoint", inSR=4326,
                  distance=radius_m, units="esriSRUnit_Meter", spatialRel="esriSpatialRelIntersects",
                  time=f"{int(t0.timestamp() * 1000)},{int(t1.timestamp() * 1000)}",
                  outFields="reach_id,river_name", returnGeometry="false", f="json")
    r = http_get(SWOT_GIS, params, timeout=300, tries=1)
    feats = r.json().get("features", [])
    return pd.DataFrame([f["attributes"] for f in feats]).drop_duplicates("reach_id") if feats else pd.DataFrame()


# --- ICESat-2 (SlideRule) ----------------------------------------------------------------------------------
class _Collect(logging.Handler):
    """Collect SlideRule server messages instead of printing them · Collecter les messages du serveur"""
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


_sliderule_ready = {"value": False}


def fetch_atl13(site_key, mask_ll, t0, t1=None, refresh=None):
    """ICESat-2 ATL13 points inside the water mask (SlideRule, no login).
    Points ICESat-2 ATL13 dans le masque d'eau (SlideRule, sans identifiant)."""
    name = f"atl13_{site_key}.parquet"
    meta_name = f"atl13_{site_key}.json"
    meta = {"bounds": [round(b, 4) for b in mask_ll.bounds], "t0": t0}

    # For custom sites, a changed mask or start date means the saved points no longer fit.
    meta_file = store.settings.cache_dir() / meta_name
    if meta_file.exists() and json.loads(meta_file.read_text()) != meta and not store.settings.offline():
        refresh = True

    def fetch():
        from sliderule import sliderule
        if not _sliderule_ready["value"]:
            sliderule.init(verbose=False, loglevel=logging.CRITICAL)
            _sliderule_ready["value"] = True
        poly = [{"lon": x, "lat": y} for x, y in mask_ll.exterior.coords]
        collector = _Collect()
        lg = logging.getLogger("sliderule")
        lg.addHandler(collector)
        lg.propagate = False
        try:
            gdf = sliderule.run("atl13x", {"poly": poly, "t0": f"{t0}T00:00:00Z",
                                           "t1": f"{t1 or today()}T23:59:59Z",
                                           "atl13": {"anc_fields": ATL13_EXTRA}})
        finally:
            lg.removeHandler(collector)
        failed = sorted({m.group(1) for m in (re.search(r"resource (\S+\.h5)", x) for x in collector.messages) if m})
        if failed:
            print(t("msg_atl13_failed", n=len(failed)))
        meta_file.parent.mkdir(parents=True, exist_ok=True)
        meta_file.write_text(json.dumps(meta))
        return gdf, "SlideRule atl13x — ICESat-2 ATL13 v007"
    return store.load_or_fetch(name, gpd.read_parquet, fetch, lambda g, p: g.to_parquet(p), refresh=refresh)


# --- GEOGloWS ------------------------------------------------------------------------------------------------
def geoglows_daily(river_id, refresh=None):
    """GEOGloWS v2 retrospective daily discharge (no login) · Débit journalier rétrospectif GEOGloWS v2"""
    def fetch():
        r = http_get(f"{GEOGLOWS}/retrospectivedaily/{river_id}", timeout=240)
        r.raise_for_status()
        return pd.read_csv(io.StringIO(r.text), index_col=0), r.url
    q = store.load_or_fetch(f"geoglows_{river_id}.csv", lambda p: pd.read_csv(p, index_col=0), fetch,
                            lambda d, p: d.to_csv(p), refresh=refresh)
    from .processing import utc_naive
    q = q.iloc[:, 0].rename("Q_m3s")
    q.index = utc_naive(q.index).normalize()
    return q


def geoglows_auto_lookup(lat, lon, refresh=None):
    """Ask GEOGloWS for the river nearest a point, and that river's mean flow (cached).
    Demander à GEOGloWS la rivière la plus proche d'un point, et son débit moyen (mis en cache)."""
    def fetch():
        rid = http_get(f"{GEOGLOWS}/getriverid", dict(lat=lat, lon=lon), timeout=60, tries=1).json()["river_id"]
        r = http_get(f"{GEOGLOWS}/retrospectivemonthly/{rid}", timeout=60, tries=1)
        info = {"river_id": rid, "mean_m3s": float(pd.read_csv(io.StringIO(r.text), index_col=0).iloc[:, 0].mean())}
        return info, r.url
    return store.load_or_fetch(f"geoglows_lookup_{lat:.3f}_{lon:.3f}.json", lambda p: json.loads(p.read_text()),
                               fetch, lambda d, p: p.write_text(json.dumps(d)), refresh=refresh)


# --- DAHITI (optional, free API key) -------------------------------------------------------------------------
def dahiti_levels(dahiti_id, api_key=None, refresh=None):
    """DAHITI water-level series (free API key needed) · Série DAHITI (clé API gratuite nécessaire).
    Written from DAHITI's documentation; not tested with a key · non testé avec une clé."""
    api_key = api_key or os.environ.get("DAHITI_API_KEY", "")

    def fetch():
        if not api_key:
            raise store.OfflineError(t("msg_no_dahiti_key"))
        r = requests.post("https://dahiti.dgfi.tum.de/api/v2/download-water-level/",
                          json=dict(api_key=api_key, dahiti_id=dahiti_id, format="json"), timeout=120)
        r.raise_for_status()
        df = pd.DataFrame(r.json()["data"]).rename(columns={"date": "time", "wse": "wse_m", "wse_u": "wse_u_m"})
        from .processing import utc_naive
        df["time"] = utc_naive(df.time)
        df["source"] = f"DAHITI {dahiti_id}"
        return df, f"DAHITI API v2 download-water-level {dahiti_id}"
    return store.load_or_fetch(f"dahiti_{dahiti_id}.csv", lambda p: pd.read_csv(p, parse_dates=["time"]), fetch,
                               lambda d, p: d.to_csv(p, index=False), refresh=refresh)
