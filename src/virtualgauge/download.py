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
from pathlib import Path

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


# --- SWOT raster (flood mapping) -----------------------------------------------------------------------------
# English only for now. Search: NASA CMR (no login). Download: PO.DAAC, free NASA Earthdata login (earthaccess).
CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"
RASTER_SHORT = "SWOT_L2_HR_Raster_100m_D"
RASTER_VARS = {"wse": "wse", "wse_qual": "wse_qual", "wse_uncert": "wse_uncert", "water_frac": "water_frac",
               "dark_frac": "dark_frac", "layover": "layover_impact"}
_RASTER_ID = re.compile(r"_x_x_x_(\d{3})_(\d{3})_(\d{3})([FP])_(\d{8}T\d{6})_")


class NeedLogin(RuntimeError):
    """Raised when a SWOT raster download needs a NASA Earthdata login."""


class MissingExtras(RuntimeError):
    """Raised when the optional flood libraries (earthaccess, xarray, h5netcdf, rasterio) are not installed."""


def earthaccess_session(interactive=False, persist=False):
    """Log in to NASA Earthdata without prompting (environment, then ~/.netrc), or with a prompt if interactive.
    Returns the earthaccess module, or raises NeedLogin / MissingExtras."""
    try:
        import earthaccess
    except ImportError as e:
        raise MissingExtras(str(e)) from e
    auth = getattr(earthaccess, "__auth__", None)
    if auth is not None and auth.authenticated:
        return earthaccess
    for strategy in ("environment", "netrc") + (("interactive",) if interactive else ()):
        try:
            earthaccess.login(strategy=strategy, persist=persist and strategy == "interactive")
        except Exception:
            continue
        if earthaccess.__auth__.authenticated:
            return earthaccess
    raise NeedLogin("NASA Earthdata login needed")


def _ring(poly_str):
    """CMR polygon string 'lat lon lat lon …' -> [(lon, lat), …]"""
    v = list(map(float, poly_str.split()))
    return list(zip(v[1::2], v[0::2]))


def _unwrap(coords, lon0):
    return [(lon0 + ((x - lon0 + 180) % 360) - 180, y) for x, y in coords]


def raster_scenes(entries, polygon_ll):
    """CMR entries -> one row per SWOT raster scene that touches the polygon (duplicates and false matches removed).
    CMR matches scenes that cross the 180° meridian to every search box, so the real footprint is tested here."""
    from shapely.geometry import Polygon
    lon0 = polygon_ll.centroid.x
    rows = []
    for e in entries:
        m = _RASTER_ID.search(e.get("title", ""))
        if not m or not e.get("polygons"):
            continue
        foot = Polygon(_unwrap(_ring(e["polygons"][0][0]), lon0))
        if not foot.is_valid or not foot.intersects(polygon_ll):
            continue
        cycle, pass_, scene, _, start = m.groups()
        rows.append(dict(cycle=cycle, pass_id=pass_, scene=scene, time=pd.Timestamp(e["time_start"]).tz_convert(None),
                         footprint=foot.wkt, url=e["url"], updated=e.get("updated", ""), title=e["title"],
                         mb=float(e.get("granule_size") or 0)))
    cols = ["cycle", "pass_id", "scene", "time", "footprint", "url", "updated", "title", "mb"]
    d = pd.DataFrame(rows, columns=cols)
    if d.empty:
        return d
    d = d.sort_values("updated").drop_duplicates(["cycle", "pass_id", "scene"], keep="last")
    return d.sort_values(["time", "scene"]).reset_index(drop=True)


def swot_raster_search(name, polygon_ll, start, end, refresh=None):
    """SWOT raster scenes over a polygon between two dates (NASA CMR, no login) · cached as `name`."""
    lon0 = polygon_ll.centroid.x
    w, s, e, n = polygon_ll.bounds

    def fetch():
        entries, page = [], 1
        while True:
            r = http_get(CMR_GRANULES, dict(short_name=RASTER_SHORT, bounding_box=f"{w:.5f},{s:.5f},{e:.5f},{n:.5f}",
                                            temporal=f"{start}T00:00:00Z,{end}T23:59:59Z", page_size=2000,
                                            page_num=page), timeout=120)
            r.raise_for_status()
            feed = r.json()["feed"]["entry"]
            for x in feed:
                url = next((lk["href"] for lk in x.get("links", []) if lk["href"].endswith(".nc")
                            and lk["href"].startswith("https://")), None)
                if url:
                    entries.append(dict(title=x["title"], time_start=x["time_start"], updated=x.get("updated", ""),
                                        polygons=x.get("polygons"), granule_size=x.get("granule_size"), url=url))
            if len(feed) < 2000:
                break
            page += 1
        kept = raster_scenes(entries, polygon_ll)                 # save only the scenes that touch the polygon
        titles = set(kept.title)
        return [en for en in entries if en["title"] in titles], f"NASA CMR {RASTER_SHORT} {start}..{end}"
    entries = store.load_or_fetch(name, lambda p: json.loads(p.read_text()), fetch,
                                  lambda d, p: p.write_text(json.dumps(d)), refresh=refresh)
    return raster_scenes(entries, polygon_ll)


def swot_raster_pass(name, grid, scenes, refresh=None):
    """Download the scenes of one SWOT pass, keep the cells of `grid`, and save them as a small table `name`.
    Needs a NASA Earthdata login. The large original files are deleted once clipped."""
    def fetch():
        ea = earthaccess_session()
        try:
            import xarray  # noqa: F401
        except ImportError as e:
            raise MissingExtras(str(e)) from e
        from .flood import clip_scene
        tmp = store.settings.cache_dir() / "swot_raster_tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        frames = []
        for sc in scenes.itertuples():
            files = ea.download([sc.url], local_path=str(tmp), show_progress=False)
            if not files:
                raise RuntimeError(f"download failed: {sc.url}")
            try:
                frames.append(clip_scene(files[0], grid, sc.footprint))
            finally:
                for f in files:
                    Path(f).unlink(missing_ok=True)
        from .flood import merge_scenes
        return merge_scenes(frames), f"PO.DAAC {RASTER_SHORT}: " + ", ".join(scenes.title)
    return store.load_or_fetch(name, pd.read_parquet, fetch, lambda d, p: d.to_parquet(p, index=False, compression="zstd"),
                               refresh=refresh)


def _dem_tile(lat, lon):
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    n = f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"
    return f"https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif"


def copernicus_dem(name, grid, refresh=None):
    """Copernicus GLO-30 ground heights (EGM2008) averaged onto `grid` (AWS open data, no login)."""
    def fetch():
        try:
            import rasterio
            from rasterio.warp import Resampling, reproject
            from rasterio.windows import from_bounds
        except ImportError as e:
            raise MissingExtras(str(e)) from e
        import math
        import numpy as np
        w, s, e, n = grid.bounds_ll(pad_deg=0.01)
        out = np.full((grid.ny, grid.nx), np.nan, dtype="float32")
        # A stalled or cut HTTP range request must fail and be retried, never hang the notebook; no in-memory cache,
        # so a retry fetches the bytes again instead of re-reading a truncated block.
        env = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                   GDAL_HTTP_TIMEOUT="30", GDAL_HTTP_CONNECTTIMEOUT="20", GDAL_HTTP_VERSION="1.1",
                   GDAL_HTTP_MULTIPLEX="NO", GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2",
                   CPL_VSIL_CURL_NON_CACHED="/vsicurl/https://copernicus-dem-30m.s3.amazonaws.com/")

        def read(url, bounds):
            for attempt in range(3):
                try:
                    with rasterio.open("/vsicurl/" + url) as src:
                        win = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
                        arr = src.read(1, window=win, boundless=True, fill_value=np.nan).astype("float32")
                        return arr, src.window_transform(win)
                except rasterio.errors.RasterioIOError:
                    if attempt == 2:
                        raise
                    time.sleep(3 * (attempt + 1))

        urls = []
        with rasterio.Env(**env):
            for lat in range(math.floor(s), math.floor(n) + 1):
                for lon in range(math.floor(w), math.floor(e) + 1):
                    url = _dem_tile(lat, lon)
                    if requests.head(url, timeout=30).status_code in (403, 404):   # no tile here = open sea
                        continue
                    arr, tr = read(url, (max(w, lon), max(s, lat), min(e, lon + 1), min(n, lat + 1)))
                    part = np.full_like(out, np.nan)
                    reproject(arr, part, src_transform=tr, src_crs="EPSG:4326", dst_transform=grid.transform(),
                              dst_crs=grid.crs, resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
                    out = np.where(np.isnan(out), part, out)
                    urls.append(url)
        if not urls:
            raise RuntimeError("no Copernicus DEM tile here")
        r, c = np.nonzero(np.isfinite(out))
        dem = np.round(out[r, c], 1).astype("float32")      # 0.1 m is plenty (the DEM is good to a few metres)
        return (pd.DataFrame({"r": r.astype("int32"), "c": c.astype("int32"), "dem": dem}),
                "Copernicus DEM GLO-30 (AWS open data): " + ", ".join(u.rsplit("/", 1)[1] for u in urls))
    return store.load_or_fetch(name, pd.read_parquet, fetch, lambda d, p: d.to_parquet(p, index=False, compression="zstd"),
                               refresh=refresh)
