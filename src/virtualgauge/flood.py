"""Flood extent and depth from SWOT, before and after a flood (English only for now).

    import virtualgauge as vg
    area = vg.flood_area("kinshasa_2024")        # or vg.flood_area(polygon=[(lon, lat), ...])
    area.passes()                                # when did SWOT look? (no login)
    flood = vg.flood_event("kinshasa_2024")      # or vg.flood_event(area, before="2023-09-21", after="2024-01-03")
    flood.extent(); flood.water_levels(); flood.depth(); flood.summary()

Data: SWOT L2 HR Raster 100 m, Version D (NASA/CNES, PO.DAAC; free NASA Earthdata login to download) and the
Copernicus GLO-30 DEM (no login). Both heights are above the EGM2008 geoid, so depth = water surface − ground.
"""
import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import Polygon, box, mapping, shape

from . import download, settings, store
from .i18n import M, fmt_int, t
from .results import Result

RES = 100.0                       # grid cell (m), the SWOT raster resolution
OFF = 0.0                         # where SWOT raster cell edges sit, modulo RES (checked on real granules)
MAX_AREA_KM2 = 10000
MIN_AREA_KM2 = 1
SWOT_MAX_LAT = 77.6               # SWOT sees from 77.6° S to 77.6° N
SWATH_M = (10000.0, 60000.0)      # each swath: 10–60 km from the ground track (the 20 km in between is not seen)
INCLINATION = 77.6

# cell classes · classes des cellules
OUTSIDE, UNSEEN, DRY, WATER, FLOODED, RECEDED = 0, 1, 2, 3, 4, 5
# cleaning reasons for water cells · raisons du nettoyage
REASONS = {0: "fl_reason_kept", 1: "fl_reason_no_level", 2: "fl_reason_quality", 3: "fl_reason_dark",
           4: "fl_reason_layover", 5: "fl_reason_ice", 6: "fl_reason_outlier"}

EXAMPLES = {
    "kinshasa_2024": dict(
        name="The Congo at Kinshasa–Brazzaville, Dec 2023–Jan 2024",
        about="the highest Congo flood at Kinshasa since 1961",
        polygon=[(15.25, -4.40), (15.60, -4.40), (15.60, -4.05), (15.25, -4.05)],
        window=("2023-07-26", "2024-03-31"), before="003_570", after="008_570", flood_date="2024-01-03",
        station="congo_kinshasa"),
    "okavango_2025": dict(
        name="The Okavango Delta near Seronga, the 2025 flood pulse",
        about="the yearly flood that spreads into the Delta from Angola",
        polygon=[(22.35, -19.15), (22.70, -19.15), (22.70, -18.80), (22.35, -18.80)],
        window=("2024-09-01", "2025-08-31"), before="024_514", after="034_514", flood_date="2025-05-15",
        station="okavango_seronga"),
}


@dataclass(frozen=True)
class FloodParams:
    """Settings for cleaning and depth · Réglages.

    max_wse_qual   keep SWOT water levels with a quality flag up to this (0 good, 1 suspect, 2 degraded, 3 bad)
    min_water_frac a cell is water when at least this fraction of it is water
    max_dark_frac  remove levels where more than this fraction of the water was 'dark' (badly measured)
    max_layover_m  remove levels with a layover error estimate larger than this (m)
    k_mad          remove levels further than k robust spreads from their neighbours
    window_m       size of the neighbourhood for that test (m)
    smooth_m       average the water surface within this distance before subtracting the ground (0 = no averaging)
    max_depth_m    drop depths larger than this (m) as impossible
    """
    max_wse_qual: int = 1
    min_water_frac: float = 0.5
    max_dark_frac: float = 0.5
    max_layover_m: float = 1.0
    k_mad: float = 3.0
    window_m: float = 1000.0
    smooth_m: float = 500.0
    max_depth_m: float = 15.0


# --- the grid --------------------------------------------------------------------------------------------------
class Grid:
    """A 100 m grid in the UTM zone of the area · Une grille de 100 m dans la zone UTM de la zone d'étude"""

    def __init__(self, polygon_ll, res=RES):
        import geopandas as gpd
        gs = gpd.GeoSeries([polygon_ll], crs=4326)
        self.crs = gs.estimate_utm_crs()
        self.poly = gs.to_crs(self.crs).iloc[0]
        minx, miny, maxx, maxy = self.poly.bounds
        self.res = res
        self.x0 = math.floor((minx - OFF) / res) * res + OFF
        self.y1 = math.ceil((maxy - OFF) / res) * res + OFF
        self.nx = int(math.ceil((maxx - self.x0) / res))
        self.ny = int(math.ceil((self.y1 - miny) / res))
        xx, yy = self.mesh()
        self.inside = shapely.contains_xy(self.poly, xx, yy)

    @property
    def zone(self):
        return self.crs.utm_zone or self.crs.name

    def centres(self):
        return (self.x0 + (np.arange(self.nx) + 0.5) * self.res,
                self.y1 - (np.arange(self.ny) + 0.5) * self.res)

    def mesh(self):
        return np.meshgrid(*self.centres())

    def transform(self):
        from affine import Affine
        return Affine(self.res, 0, self.x0, 0, -self.res, self.y1)

    def index(self, x, y):
        """Row and column of the cells containing x, y (and whether they are on the grid)"""
        c = np.rint((np.asarray(x) - self.x0) / self.res - 0.5).astype("int64")
        r = np.rint((self.y1 - np.asarray(y)) / self.res - 0.5).astype("int64")
        return r, c, (c >= 0) & (c < self.nx) & (r >= 0) & (r < self.ny)

    def bounds_ll(self, pad_deg=0.0):
        from pyproj import Transformer
        tr = Transformer.from_crs(self.crs, 4326, always_xy=True)
        xs = [self.x0, self.x0 + self.nx * self.res]
        ys = [self.y1 - self.ny * self.res, self.y1]
        lon, lat = tr.transform(np.repeat(xs, 2), np.tile(ys, 2))
        return min(lon) - pad_deg, min(lat) - pad_deg, max(lon) + pad_deg, max(lat) + pad_deg

    def extent_km(self):
        """Map extent in km from the south-west corner · Étendue en km depuis le coin sud-ouest"""
        return 0, self.nx * self.res / 1000, 0, self.ny * self.res / 1000

    def outline_km(self):
        """Polygon outline(s) in the same km coordinates"""
        y0 = self.y1 - self.ny * self.res
        geoms = getattr(self.poly, "geoms", [self.poly])
        return [((np.array(g.exterior.xy[0]) - self.x0) / 1000, (np.array(g.exterior.xy[1]) - y0) / 1000)
                for g in geoms]

    def cell_km2(self):
        return self.res * self.res / 1e6

    def to_grid(self, table, col, dtype="float32"):
        a = np.full((self.ny, self.nx), np.nan, dtype=dtype)
        if len(table):
            a[table.r.to_numpy(), table.c.to_numpy()] = table[col].to_numpy()
        return a


# --- reading SWOT raster scenes (used by download.swot_raster_pass) -------------------------------------------
def _footprint_cells(grid, footprint_wkt):
    from pyproj import Transformer
    from shapely import wkt
    tr = Transformer.from_crs(4326, grid.crs, always_xy=True)
    foot = shapely.transform(wkt.loads(footprint_wkt), lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
    xx, yy = grid.mesh()
    return shapely.contains_xy(foot, xx, yy)


def clip_scene(path, grid, footprint_wkt):
    """One SWOT raster file -> the grid cells it sees, with the variables we use.
    A cell is 'seen' when it lies in the scene and 10–60 km from the ground track (estimated from the scene's own
    cross-track distances), or when SWOT gave it a value."""
    import xarray as xr
    from pyproj import CRS, Transformer
    with xr.open_dataset(path, engine="h5netcdf", mask_and_scale=True) as ds:
        crs = CRS.from_wkt(ds["crs"].attrs["crs_wkt"])
        x, y = ds["x"].values.astype("float64"), ds["y"].values.astype("float64")
        arrays = {k: ds[v].values.astype("float32") for k, v in download.RASTER_VARS.items() if v in ds}
        ice = [ds[v].values.astype("float32") for v in ("ice_clim_flag", "ice_dyn_flag") if v in ds]
        arrays["ice"] = np.fmax(*ice) if len(ice) == 2 else (ice[0] if ice else np.zeros_like(arrays["wse"]))
        ct = ds["cross_track"].values.astype("float64")
    xx, yy = grid.mesh()
    if crs.equals(grid.crs):
        sx, sy = xx, yy
    else:
        sx, sy = Transformer.from_crs(grid.crs, crs, always_xy=True).transform(xx, yy)
    ix = np.rint((sx - x[0]) / (x[1] - x[0])).astype("int64")
    iy = np.rint((sy - y[0]) / (y[1] - y[0])).astype("int64")
    on = (ix >= 0) & (ix < len(x)) & (iy >= 0) & (iy < len(y))
    ixc, iyc = np.clip(ix, 0, len(x) - 1), np.clip(iy, 0, len(y) - 1)

    # the two swaths: fit cross-track distance as a plane over the whole scene, then keep 10–60 km
    ok = np.isfinite(ct)
    seen = np.zeros(xx.shape, bool)
    if ok.sum() > 100:
        jy, jx = np.nonzero(ok)
        pick = np.random.default_rng(0).choice(len(jx), min(len(jx), 50000), replace=False)
        A = np.c_[np.ones(len(pick)), x[jx[pick]], y[jy[pick]]]
        coef = np.linalg.lstsq(A, ct[jy[pick], jx[pick]], rcond=None)[0]
        lo, hi = np.percentile(np.abs(ct[ok]), [0.5, 99.5])
        lo, hi = max(lo, 0.8 * SWATH_M[0]), min(hi, 1.1 * SWATH_M[1])
        ct_hat = np.abs(coef[0] + coef[1] * sx + coef[2] * sy)
        seen = (ct_hat >= lo) & (ct_hat <= hi) & _footprint_cells(grid, footprint_wkt)
    vals = {k: np.where(on, a[iyc, ixc], np.nan) for k, a in arrays.items()}
    has_value = np.isfinite(vals["wse"]) | np.isfinite(vals["water_frac"])
    seen = (seen & on) | has_value
    r, c = np.nonzero(seen)
    out = pd.DataFrame({"r": r.astype("int32"), "c": c.astype("int32")})
    for k, v in vals.items():
        out[k] = v[r, c].astype("float32")
    return out


def merge_scenes(frames):
    """Join the scenes of one pass; where scenes overlap keep the cell that has a water level."""
    d = pd.concat(frames, ignore_index=True)
    d = d.assign(_k=d.wse.isna()).sort_values(["_k"]).drop_duplicates(["r", "c"]).drop(columns="_k")
    return d.sort_values(["r", "c"]).reset_index(drop=True)


# --- where SWOT looks: the swaths of a pass, from the scene footprints (before downloading) ---------------------
def _swath_band(foot_utm, odd_pass, lat):
    """The part of a scene 10–60 km either side of the ground track · La partie vue d'une scène"""
    from shapely.geometry import LineString
    pts = np.array(foot_utm.exterior.coords)[:4]
    if len(pts) < 4:
        return foot_utm
    alpha = math.degrees(math.asin(min(1.0, math.cos(math.radians(INCLINATION)) / max(math.cos(math.radians(lat)), 1e-6))))
    track = alpha if odd_pass else 180 - alpha                      # ascending (odd) heads NE, descending SE
    edges = [(pts[i], pts[(i + 1) % 4]) for i in range(4)]

    def orient(e):
        d = e[1] - e[0]
        return math.degrees(math.atan2(d[0], d[1])) % 180

    def gap(a, b):
        return min(abs(a - b) % 180, 180 - abs(a - b) % 180)
    pair_a = gap(orient(edges[0]), track) + gap(orient(edges[2]), track)
    pair_b = gap(orient(edges[1]), track) + gap(orient(edges[3]), track)
    cross = [edges[1], edges[3]] if pair_a < pair_b else [edges[0], edges[2]]   # the edges across the track
    m1, m2 = (cross[0][0] + cross[0][1]) / 2, (cross[1][0] + cross[1][1]) / 2
    d = (m2 - m1) / max(np.hypot(*(m2 - m1)), 1)
    nadir = LineString([m1 - d * 2e5, m2 + d * 2e5])
    band = nadir.buffer(SWATH_M[1], cap_style="flat").difference(nadir.buffer(SWATH_M[0], cap_style="flat"))
    return band.intersection(foot_utm)


def pass_table(scenes, grid, polygon_ll):
    """Scenes -> one row per pass, with the share of the area inside the swaths (an estimate before download)"""
    import geopandas as gpd
    from shapely import wkt
    cols = ["pass", "date", "time_utc", "track", "cycle", "scenes", "seen_pct", "mb"]
    if scenes.empty:
        return pd.DataFrame(columns=cols)
    area = grid.poly.area
    lat = polygon_ll.centroid.y
    rows = []
    for (cycle, pass_), g in scenes.groupby(["cycle", "pass_id"], sort=False):
        feet = gpd.GeoSeries([wkt.loads(f) for f in g.footprint], crs=4326).to_crs(grid.crs)
        seen = shapely.union_all([_swath_band(f, int(pass_) % 2 == 1, lat) for f in feet])
        tm = g.time.min()
        rows.append({"pass": f"{cycle}_{pass_}", "date": tm.strftime("%Y-%m-%d"), "time_utc": tm.strftime("%H:%M"),
                     "track": int(pass_), "cycle": int(cycle), "scenes": len(g),
                     "seen_pct": round(100 * seen.intersection(grid.poly).area / area),
                     "mb": round(float(g.mb.sum()))})
    return pd.DataFrame(rows, columns=cols).sort_values("date").reset_index(drop=True)


# --- one pass on the grid --------------------------------------------------------------------------------------
class PassGrid:
    def __init__(self, grid, table, info):
        self.info = info                                    # a row of the pass table
        self.label = info["pass"]
        self.time = pd.Timestamp(f"{info['date']} {info['time_utc']}")
        self.seen = np.zeros((grid.ny, grid.nx), bool)
        if len(table):
            self.seen[table.r.to_numpy(), table.c.to_numpy()] = True
        for k in ["wse", "wse_qual", "wse_uncert", "water_frac", "dark_frac", "layover", "ice"]:
            setattr(self, k, grid.to_grid(table, k) if k in table else np.full((grid.ny, grid.nx), np.nan, "float32"))


def _local_reference(wse, ok, res, window_m):
    """Median and robust spread of the water levels around each cell (3 × 3 blocks of window_m)."""
    r, c = np.nonzero(ok)
    v = wse[r, c].astype("float64")
    bs = max(1, int(round(window_m / res)))
    br, bc = r // bs, c // bs
    long = pd.concat([pd.DataFrame({"br": br + i, "bc": bc + j, "v": v, "own": (i == 0) & (j == 0)})
                      for i in (-1, 0, 1) for j in (-1, 0, 1)], ignore_index=True)
    g = long.groupby(["br", "bc"]).v
    med, n = g.median().rename("med"), g.size().rename("n")
    long = long.join(med, on=["br", "bc"])
    mad = (long.v - long.med).abs().groupby([long.br, long.bc]).median().rename("mad")
    ref = pd.DataFrame({"br": br, "bc": bc}).join(med, on=["br", "bc"]).join(mad, on=["br", "bc"]).join(n, on=["br", "bc"])
    return r, c, v, ref.med.to_numpy(), 1.4826 * ref.mad.to_numpy(), ref.n.to_numpy()


def clean_pass(p, params, res=RES):
    """Water cells, and why each water level is kept or removed · Cellules d'eau et raisons du nettoyage"""
    water = p.seen & (np.nan_to_num(p.water_frac, nan=-1.0) >= params.min_water_frac)
    reason = np.full(water.shape, -1, "int8")
    reason[water] = 0

    def flag(mask, code):
        reason[(reason == 0) & mask] = code
    flag(~np.isfinite(p.wse), 1)
    flag(np.nan_to_num(p.wse_qual, nan=9) > params.max_wse_qual, 2)
    flag(np.nan_to_num(p.dark_frac, nan=0) > params.max_dark_frac, 3)
    flag(np.abs(np.nan_to_num(p.layover, nan=0)) > params.max_layover_m, 4)
    flag(np.nan_to_num(p.ice, nan=0) > 0, 5)
    ok = reason == 0
    if ok.sum() >= 5:
        r, c, v, med, spread, n = _local_reference(p.wse, ok, res, params.window_m)
        bad = (n >= 5) & (np.abs(v - med) > np.maximum(params.k_mad * spread, 0.25))
        reason[r[bad], c[bad]] = 6
    wse_ok = np.where(reason == 0, p.wse, np.nan)
    return water, reason, wse_ok


def _smooth(values, radius_cells):
    """Average of the finite values within a square window (NaN where there are none)"""
    from scipy.ndimage import uniform_filter
    if radius_cells <= 0:
        return values
    size = 2 * radius_cells + 1
    ok = np.isfinite(values)
    s = uniform_filter(np.where(ok, values, 0.0).astype("float64"), size=size, mode="constant")
    n = uniform_filter(ok.astype("float64"), size=size, mode="constant")
    return np.where(n > 0.5 / size ** 2, s / np.maximum(n, 1e-12), np.nan)


def analyse(grid, before, after, dem, params):
    """Everything the figures and the summary need · Tout ce dont les figures et le résumé ont besoin"""
    wb, rb, okb = clean_pass(before, params, grid.res)
    wa, ra, oka = clean_pass(after, params, grid.res)
    inside = grid.inside
    both = before.seen & after.seen & inside
    cls = np.full(inside.shape, OUTSIDE, "int8")
    cls[inside] = UNSEEN
    cls[both & ~wb & ~wa] = DRY
    cls[both & wb & wa] = WATER
    cls[both & ~wb & wa] = FLOODED
    cls[both & wb & ~wa] = RECEDED
    rise = np.where(cls == WATER, oka - okb, np.nan)
    surface = _smooth(np.where(wa & inside, oka, np.nan), int(round(params.smooth_m / grid.res)))
    surface = np.where(np.isfinite(surface), surface, oka)
    depth_all = np.where(cls == FLOODED, surface - dem, np.nan) if dem is not None else np.full(cls.shape, np.nan)
    too_deep = depth_all > params.max_depth_m
    below = depth_all < 0
    depth = np.where(too_deep, np.nan, np.where(below, 0.0, depth_all))
    return dict(cls=cls, seen_before=before.seen, seen_after=after.seen, water_before=wb, water_after=wa, reason_before=rb, reason_after=ra, wse_before=okb,
                wse_after=oka, rise=rise, surface=surface, depth=depth, depth_raw=np.where(too_deep, np.nan, depth_all),
                n_below=int(below.sum()), n_too_deep=int(too_deep.sum()), dem=dem)


def summarise(grid, a, before, after):
    """Key numbers · Chiffres clés"""
    k = grid.cell_km2()
    cls, inside = a["cls"], grid.inside
    n_in = int(inside.sum())
    both = cls >= DRY
    n_flood = int((cls == FLOODED).sum())
    d = a["depth"][cls == FLOODED]
    d = d[np.isfinite(d)]
    rise = a["rise"][np.isfinite(a["rise"])]
    v = dict(area_km2=n_in * k,
             seen_before_pct=100 * (before.seen & inside).sum() / max(n_in, 1),
             seen_after_pct=100 * (after.seen & inside).sum() / max(n_in, 1),
             seen_both_pct=100 * both.sum() / max(n_in, 1), seen_both_km2=both.sum() * k,
             water_before_km2=((cls == WATER) | (cls == RECEDED)).sum() * k,
             water_after_km2=((cls == WATER) | (cls == FLOODED)).sum() * k,
             flooded_km2=n_flood * k, receded_km2=(cls == RECEDED).sum() * k,
             rise_median_m=float(np.median(rise)) if len(rise) else np.nan,
             rise_q25_m=float(np.percentile(rise, 25)) if len(rise) else np.nan,
             rise_q75_m=float(np.percentile(rise, 75)) if len(rise) else np.nan, rise_n=int(len(rise)),
             depth_median_m=float(np.median(d)) if len(d) else np.nan,
             depth_p90_m=float(np.percentile(d, 90)) if len(d) else np.nan, depth_n=int(len(d)),
             depth_cover_pct=100 * len(d) / max(n_flood, 1),
             below_ground_pct=100 * a["n_below"] / max(n_flood, 1), too_deep_n=a["n_too_deep"],
             volume_mm3=float(d.sum() * grid.res ** 2 / 1e6),
             days=(after.time - before.time).total_seconds() / 86400)
    return v


# --- areas ------------------------------------------------------------------------------------------------------
def _unavailable(heading, key, **kw):
    return Result(heading, [(key, kw)])


def _origin_line(names):
    dates = [store.ORIGINS.get(n) for n in names if store.ORIGINS.get(n)]
    if not dates:
        return None
    o = dates[0]
    okey = {"bundled": "origin_bundled", "cache": "origin_cache"}.get(o.get("origin"), "origin_download")
    return ("card_data", dict(origin=M(okey, date=o.get("date") or "?")))


class FloodArea:
    """The area you want to map · La zone à cartographier"""

    def __init__(self, polygon_ll=None, key=None, name=None, example=None, error=None):
        self.polygon, self.key, self.name, self.example, self.error = polygon_ll, key, name, example, error
        self.grid = Grid(polygon_ll) if error is None else None
        self.last_passes = None                             # the pass table of the last search

    # --- display
    def _card(self):
        h = ("fl_h_area", {"name": self.name or "—"})
        if self.error:
            return Result(h, [self.error])
        c = self.polygon.centroid
        lines = [("fl_card_area", dict(km2=fmt_int(round(self.area_km2)), lat=f"{c.y:.3f}", lon=f"{c.x:.3f}",
                                       nx=self.grid.nx, ny=self.grid.ny, zone=self.grid.zone))]
        if self.example:
            lines.append(("fl_card_example", dict(about=EXAMPLES[self.key]["about"])))
        lines.append(("fl_card_area_next", {}))
        return Result(h, lines, values=dict(area_km2=self.area_km2))

    def _repr_html_(self):
        return self._card()._repr_html_()

    def __repr__(self):
        return repr(self._card())

    @property
    def area_km2(self):
        return float(self.grid.poly.area / 1e6) if self.grid else 0.0

    def code(self):
        """The line that rebuilds this area · La ligne qui reconstruit cette zone"""
        geoms = getattr(self.polygon, "geoms", [self.polygon])
        pts = ", ".join(f"({x:.4f}, {y:.4f})" for x, y in list(geoms[0].exterior.coords)[:-1])
        line = f"area = vg.flood_area(polygon=[{pts}])"
        return Result(("fl_h_code", {}), [("fl_code_line", dict(code=line))], values=dict(code=line))

    def map(self):
        """The area on a satellite image · La zone sur une image satellite"""
        import folium
        from .maps import base_map
        if self.error:
            return self._card()
        c = self.polygon.centroid
        m = base_map(c.y, c.x, zoom=10)
        folium.GeoJson(mapping(self.polygon), name=t("fl_map_area"),
                       style_function=lambda f: {"color": "#ffffff", "weight": 2, "fillOpacity": 0.05}).add_to(m)
        hy = self._hydro_reach()
        if hy is not None:
            folium.Marker([hy["lat"], hy["lon"]], tooltip=t("fl_map_reach", reach=hy["reach"], river=hy["river"])
                          ).add_to(m)
        w, s, e, n = self.polygon.bounds
        m.fit_bounds([[s, w], [n, e]])
        folium.LayerControl().add_to(m)
        return m

    # --- passes
    def _search_name(self, start, end):
        if self.example and (start, end) == tuple(EXAMPLES[self.key]["window"]):
            return f"flood_{self.key}_search.json"
        return f"flood_{self.key}_search_{start}_{end}.json"

    def pass_table(self, start, end):
        if self.example:                                    # inside the example's period: use its saved search
            w0, w1 = EXAMPLES[self.key]["window"]
            if w0 <= start and end <= w1:
                scenes = download.swot_raster_search(self._search_name(w0, w1), self.polygon, w0, w1)
                day = scenes.time.dt.strftime("%Y-%m-%d")
                scenes = scenes[(day >= start) & (day <= end)].reset_index(drop=True)
                tab = pass_table(scenes, self.grid, self.polygon)
                self.last_passes = (tab, scenes)
                return tab, scenes
        scenes = download.swot_raster_search(self._search_name(start, end), self.polygon, start, end)
        tab = pass_table(scenes, self.grid, self.polygon)
        self.last_passes = (tab, scenes)
        return tab, scenes

    def _window(self, start, end, flood_date):
        if start and end:
            return str(start)[:10], str(end)[:10]
        if self.example and not (start or end or flood_date):
            return tuple(EXAMPLES[self.key]["window"])
        d = pd.Timestamp(flood_date) if flood_date else pd.Timestamp.now().normalize()
        s = pd.Timestamp(start) if start else d - pd.Timedelta(days=90)
        e = pd.Timestamp(end) if end else min(d + pd.Timedelta(days=60), pd.Timestamp.now().normalize())
        return f"{s:%Y-%m-%d}", f"{e:%Y-%m-%d}"

    def _hydro_reach(self):
        """The widest SWOT river reach in the area (for the hydrograph) · Le plus large tronçon SWOT de la zone"""
        from .locations import reach_index
        from .sites import PRESETS
        if self.example:
            st = PRESETS[EXAMPLES[self.key]["station"]]
            return dict(reach=st.swot_reach, river=st.short, lat=st.lat, lon=st.lon, width=None)
        idx = reach_index()
        w, s, e, n = self.polygon.bounds
        d = idx[idx.lon.between(w, e) & idx.lat.between(s, n) & (idx.type != 6) & (idx.width_m >= 30)]
        if d.empty:
            return None
        d = d[shapely.contains_xy(self.polygon, d.lon.to_numpy(), d.lat.to_numpy())]
        if d.empty:
            return None
        r = d.sort_values("width_m").iloc[-1]
        river = r.river_name if isinstance(r.river_name, str) and r.river_name not in ("", "NODATA") else "—"
        return dict(reach=str(r.reach_id), river=river, lat=float(r.lat), lon=float(r.lon), width=float(r.width_m))

    def hydrograph(self):
        """SWOT water levels of that reach (Hydrocron, no login), or None"""
        from .processing import clean_swot
        hy = self._hydro_reach()
        if hy is None:
            return None
        try:
            df = download.hydrocron_reach(hy["reach"])
        except Exception:
            return None
        if df is None or df.empty:
            return None
        s = clean_swot(df)
        s = s[s.reason == "kept"]
        if len(s) < 3:
            return None
        return dict(hy, series=s.set_index("time").wse.sort_index())

    def passes(self, start=None, end=None, flood_date=None):
        """When did SWOT look at this area? (no login) · Quand SWOT a-t-il regardé cette zone ?"""
        from . import floodplots
        h = ("fl_h_passes", {"name": self.name or "—"})
        if self.error:
            return self._card()
        start, end = self._window(start, end, flood_date)
        try:
            tab, _ = self.pass_table(start, end)
        except store.OfflineError:
            return _unavailable(h, "fl_err_offline")
        except Exception:
            return _unavailable(h, "fl_err_search")
        if tab.empty:
            return Result(h, [("fl_passes_none", dict(start=start, end=end))])
        hydro = self.hydrograph()
        chosen = {}
        if self.example and flood_date is None and (start, end) == tuple(EXAMPLES[self.key]["window"]):
            ex = EXAMPLES[self.key]
            chosen = {"before": ex["before"], "after": ex["after"]}
            flood_date = ex["flood_date"]
        lines = [("fl_passes_found", dict(n=len(tab), start=start, end=end, tracks=tab.track.nunique())),
                 ("fl_passes_seen", {})]
        lines.append(("fl_passes_hydro", dict(reach=hydro["reach"], river=hydro["river"])) if hydro
                     else ("fl_passes_no_hydro", {}))
        if chosen:
            lines.append(("fl_passes_example", chosen))
        else:
            lines.append(("fl_passes_next", {}))
        table = tab.drop(columns=["cycle"]).rename(columns={"seen_pct": "seen_%"})
        return Result(h, lines, table=table, table_rows=40, values=dict(passes=tab),
                      figure=lambda: floodplots.fig_passes(tab, hydro, chosen, flood_date, self.name))


def _polygon_from(where):
    """A shapely polygon (lon/lat) from a list of points, a GeoJSON dict, a file or a shapely shape"""
    if isinstance(where, (Polygon,)) or hasattr(where, "geom_type"):
        return where
    if isinstance(where, dict):
        if where.get("type") == "FeatureCollection":
            return shapely.union_all([shape(f["geometry"]) for f in where["features"]])
        if where.get("type") == "Feature":
            return shape(where["geometry"])
        return shape(where)
    if isinstance(where, (str, Path)) and Path(where).exists():
        import geopandas as gpd
        g = gpd.read_file(where)
        g = g.to_crs(4326) if g.crs else g
        return shapely.union_all(list(g.geometry))
    pts = [tuple(map(float, p)) for p in where]
    return Polygon(pts)


def flood_area(where=None, *, polygon=None, bbox=None, name=None):
    """The area to map · La zone à cartographier.

    flood_area("kinshasa_2024")                         a ready-made example (works offline)
    flood_area(polygon=[(lon, lat), (lon, lat), ...])   your own polygon (longitude first)
    flood_area(bbox=(west, south, east, north))         a rectangle
    flood_area("my_area.geojson")                       a GeoJSON/KML/shapefile, or a GeoJSON dict
    """
    if isinstance(where, str) and where in EXAMPLES:
        ex = EXAMPLES[where]
        return FloodArea(Polygon(ex["polygon"]), key=where, name=ex["name"], example=True)
    src = polygon if polygon is not None else (box(*bbox) if bbox is not None else where)
    if src is None:
        return FloodArea(name=name, error=("fl_err_no_area", dict(examples=", ".join(EXAMPLES))))
    try:
        poly = _polygon_from(src)
        poly = shapely.make_valid(poly) if not poly.is_valid else poly
        if poly.geom_type not in ("Polygon", "MultiPolygon"):
            poly = poly.convex_hull if poly.geom_type == "GeometryCollection" else poly
    except Exception:
        return FloodArea(name=name, error=("fl_err_bad_polygon", {}))
    if poly.is_empty or poly.geom_type not in ("Polygon", "MultiPolygon"):
        return FloodArea(name=name, error=("fl_err_bad_polygon", {}))
    w, s, e, n = poly.bounds
    if max(abs(s), abs(n)) > SWOT_MAX_LAT or abs(w) > 360 or abs(e) > 360:
        return FloodArea(name=name, error=("fl_err_latitude", dict(lat=f"{max(abs(s), abs(n)):.1f}")))
    tmp = FloodArea(poly, key="tmp", name=name)
    km2 = tmp.area_km2
    if km2 > MAX_AREA_KM2:
        return FloodArea(name=name, error=("fl_err_too_big", dict(km2=fmt_int(km2), max=fmt_int(MAX_AREA_KM2))))
    if km2 < MIN_AREA_KM2:
        return FloodArea(name=name, error=("fl_err_too_small", dict(km2=f"{km2:.2f}")))
    rounded = json.dumps([[round(x, 5), round(y, 5)] for g in getattr(poly, "geoms", [poly])
                          for x, y in g.exterior.coords])
    tmp.key = "area_" + hashlib.sha1(rounded.encode()).hexdigest()[:8]
    tmp.name = name or t("fl_your_area")
    return tmp


# --- flood events -----------------------------------------------------------------------------------------------
def _needs_data(method):
    def wrapper(self, *a, **kw):
        if self.error:
            return self._card()
        return method(self, *a, **kw)
    wrapper.__doc__, wrapper.__name__ = method.__doc__, method.__name__
    return wrapper


class FloodEvent:
    """Before and after a flood, in one area · Avant et après une crue, dans une zone"""

    def __init__(self, area, params, before=None, after=None, dem=None, error=None, origins=()):
        self.area, self.params, self.before, self.after, self.dem = area, params, before, after, dem
        self.error, self.origins = error, list(origins)
        self._memo = {}

    def with_settings(self, **changes):
        """The same event with other settings (no new download) · Le même événement avec d'autres réglages"""
        ev = FloodEvent(self.area, replace(self.params, **changes), self.before, self.after, self.dem, self.error,
                        self.origins)
        ev._memo = self._memo
        return ev

    def _a(self):
        key = tuple(asdict(self.params).values())
        if key not in self._memo:
            self._memo[key] = analyse(self.area.grid, self.before, self.after, self.dem, self.params)
        return self._memo[key]

    @property
    def values(self):
        return {} if self.error else summarise(self.area.grid, self._a(), self.before, self.after)

    # --- display
    def _card(self):
        h = ("fl_h_event", {"name": self.area.name or "—"})
        if self.error:
            return Result(h, [self.error])
        v = self.values
        b, a = self.before, self.after
        lines = [("fl_card_before", dict(date=f"{b.time:%Y-%m-%d}", label=b.label, seen=round(v["seen_before_pct"]))),
                 ("fl_card_after", dict(date=f"{a.time:%Y-%m-%d}", label=a.label, seen=round(v["seen_after_pct"]),
                                        days=round(v["days"])))]
        tb, ta = b.info["track"], a.info["track"]
        lines.append(("fl_card_same_track", dict(track=tb)) if tb == ta else
                     ("fl_card_other_track", dict(t1=tb, t2=ta)))
        lines.append(("fl_card_both", dict(pct=round(v["seen_both_pct"]), km2=fmt_int(round(v["seen_both_km2"])))))
        if self.dem is None:
            lines.append(("fl_card_no_dem", {}))
        o = _origin_line(self.origins)
        if o:
            lines.append(o)
        lines.append(("fl_card_event_next", {}))
        return Result(h, lines, values=v)

    def _repr_html_(self):
        return self._card()._repr_html_()

    def __repr__(self):
        return repr(self._card())

    def _dates(self):
        return dict(before=f"{self.before.time:%Y-%m-%d}", after=f"{self.after.time:%Y-%m-%d}")

    # --- steps
    @_needs_data
    def extent(self):
        """Where was water before, after, and what is new? · Où était l'eau avant, après, et qu'est-ce qui est nouveau ?"""
        from . import floodplots
        v, a, g = self.values, self._a(), self.area.grid

        def r1(x):
            return f"{x:,.1f}".replace(",", " ")
        lines = [("fl_extent_line", dict(wb=r1(v["water_before_km2"]), wa=r1(v["water_after_km2"]),
                                         both=r1(v["seen_both_km2"]), **self._dates())),
                 ("fl_extent_new", dict(new=r1(v["flooded_km2"]), gone=r1(v["receded_km2"])))]
        k = g.cell_km2()
        table = pd.DataFrame({"class": [t(x) for x in ("fl_cls_water", "fl_cls_flooded", "fl_cls_receded",
                                                       "fl_cls_dry", "fl_cls_unseen")],
                              "km2": [round(float((a["cls"] == c).sum() * k), 1)
                                      for c in (WATER, FLOODED, RECEDED, DRY, UNSEEN)]})
        return Result(("fl_h_extent", {}), lines, table=table, values=v,
                      figure=lambda: floodplots.fig_extent(g, a, self._dates()))

    @_needs_data
    def cleaning(self):
        """Which SWOT water levels can we trust? · Quels niveaux SWOT sont fiables ?"""
        from . import floodplots
        a, g = self._a(), self.area.grid
        rows = []
        for code, key in REASONS.items():
            rows.append({"reason": t(key, q=self.params.max_wse_qual, dark=self.params.max_dark_frac,
                                     lay=self.params.max_layover_m, k=self.params.k_mad),
                         "before": int(((a["reason_before"] == code) & g.inside).sum()),
                         "after": int(((a["reason_after"] == code) & g.inside).sum())})
        table = pd.DataFrame(rows)
        n_after = int(table.after.sum())
        kept = int(table.after.iloc[0])
        lines = [("fl_cleaning_line", dict(n=fmt_int(n_after), kept=fmt_int(kept),
                                           pct=round(100 * kept / max(n_after, 1))))]
        top = table.iloc[1:].sort_values("after").iloc[-1]
        if top.after > 0:
            lines.append(("fl_cleaning_top", dict(reason=top.reason, n=fmt_int(top.after))))
        return Result(("fl_h_cleaning", {}), lines, table=table, values=dict(table=table),
                      figure=lambda: floodplots.fig_cleaning(g, a, self._dates()))

    @_needs_data
    def water_levels(self):
        """How much did the water already there rise? · De combien l'eau déjà présente est-elle montée ?"""
        from . import floodplots
        v, a, g = self.values, self._a(), self.area.grid
        if not v["rise_n"]:
            return Result(("fl_h_levels", {}), [("fl_levels_none", {})])
        lines = [("fl_levels_line", dict(median=f"{v['rise_median_m']:.2f}", n=fmt_int(v["rise_n"]),
                                         q25=f"{v['rise_q25_m']:.2f}", q75=f"{v['rise_q75_m']:.2f}"))]
        ref = self._reach_rise()
        if ref:
            lines.append(("fl_levels_reach", ref))
        return Result(("fl_h_levels", {}), lines, values=v,
                      figure=lambda: floodplots.fig_levels(g, a, self._dates(), ref))

    def _reach_rise(self):
        hy = self.area.hydrograph()
        if hy is None:
            return None
        s = hy["series"]

        def near(tm):
            i = np.argmin(np.abs((s.index - tm).total_seconds()))
            return s.index[i], float(s.iloc[i])
        (t0, h0), (t1, h1) = near(self.before.time), near(self.after.time)
        if abs((t0 - self.before.time).days) > 3 or abs((t1 - self.after.time).days) > 3:
            return None
        return dict(reach=hy["reach"], river=hy["river"], rise=f"{h1 - h0:.2f}", rise_m=h1 - h0)

    @_needs_data
    def ground(self):
        """How high is the ground under the flood? · Quelle est la hauteur du sol sous la crue ?"""
        from . import floodplots
        a, g = self._a(), self.area.grid
        if self.dem is None:
            return Result(("fl_h_ground", {}), [("fl_card_no_dem", {})])
        fl = a["cls"] == FLOODED
        ground = self.dem[fl & np.isfinite(self.dem)]
        surf = a["surface"][fl & np.isfinite(a["surface"])]
        lines = []
        if len(ground) and len(surf):
            lines.append(("fl_ground_line", dict(ground=f"{np.median(ground):.1f}", surface=f"{np.median(surf):.1f}")))
        lines += [("fl_ground_datum", {}), ("fl_ground_dsm", {})]
        return Result(("fl_h_ground", {}), lines, figure=lambda: floodplots.fig_ground(g, a, self._dates()))

    @_needs_data
    def depth(self, smooth_m=None):
        """How deep is the new flood water? · Quelle est la profondeur de l'eau de crue ?

        smooth_m: average the SWOT water surface within this distance first (0 = each cell's own level)"""
        from . import floodplots
        if smooth_m is not None and smooth_m != self.params.smooth_m:
            return self.with_settings(smooth_m=float(smooth_m)).depth()
        v, a, g, p = self.values, self._a(), self.area.grid, self.params
        if self.dem is None:
            return Result(("fl_h_depth", {}), [("fl_card_no_dem", {})])
        if not v["depth_n"]:
            return Result(("fl_h_depth", {}), [("fl_depth_none", {})])
        lines = [("fl_depth_line", dict(median=f"{v['depth_median_m']:.1f}", p90=f"{v['depth_p90_m']:.1f}",
                                        n=fmt_int(v["depth_n"]), cover=round(v["depth_cover_pct"]))),
                 ("fl_depth_volume", dict(vol=f"{v['volume_mm3']:,.0f}".replace(",", " ")
                                          if v["volume_mm3"] >= 10 else f"{v['volume_mm3']:.1f}")),
                 ("fl_depth_smooth", dict(m=round(p.smooth_m))) if p.smooth_m > 0 else ("fl_depth_raw", {})]
        warns = []
        if v["below_ground_pct"] >= 1:
            warns.append(("fl_warn_below", dict(pct=round(v["below_ground_pct"]))))
        if v["too_deep_n"]:
            warns.append(("fl_warn_deep", dict(n=fmt_int(v["too_deep_n"]), max=p.max_depth_m)))
        return Result(("fl_h_depth", {}), lines, warnings=warns, values=v,
                      figure=lambda: floodplots.fig_depth(g, a, self._dates(), p.max_depth_m))

    @_needs_data
    def summary(self):
        """Before and after, in numbers · Avant et après, en chiffres"""
        v = self.values
        b, a = self.before, self.after
        rows = [("Before: SWOT pass", f"{b.label} ({b.time:%Y-%m-%d %H:%M} UTC)", ""),
                ("After: SWOT pass", f"{a.label} ({a.time:%Y-%m-%d %H:%M} UTC)", ""),
                ("Days between", f"{v['days']:.1f}", "days"),
                ("Area", f"{v['area_km2']:.1f}", "km²"),
                ("Seen by both passes", f"{v['seen_both_pct']:.0f}", "% of area"),
                ("Water before", f"{v['water_before_km2']:.1f}", "km²"),
                ("Water after", f"{v['water_after_km2']:.1f}", "km²"),
                ("Newly flooded", f"{v['flooded_km2']:.1f}", "km²"),
                ("Water gone (receded)", f"{v['receded_km2']:.1f}", "km²"),
                ("Rise of water already there (median)", f"{v['rise_median_m']:.2f}", "m"),
                ("Flood depth on new land (median)", f"{v['depth_median_m']:.2f}", "m"),
                ("Flood depth on new land (90th percentile)", f"{v['depth_p90_m']:.2f}", "m"),
                ("New land with a depth estimate", f"{v['depth_cover_pct']:.0f}", "%"),
                ("Water below the DEM ground (set to 0 m)", f"{v['below_ground_pct']:.0f}", "% of new land"),
                ("Water stored on new land", f"{v['volume_mm3']:.1f}", "million m³")]
        table = pd.DataFrame(rows, columns=["quantity", "value", "unit"])
        return Result(("fl_h_summary", {"name": self.area.name or "—"}), [("fl_summary_line", self._dates())],
                      table=table, table_rows=len(table), values=v)

    @_needs_data
    def map(self):
        """Interactive map: water before, after, and flood depth · Carte interactive"""
        from .floodmap import event_map
        return event_map(self)

    @_needs_data
    def export(self, download=False):
        """Save the summary and the maps in outputs/ · Enregistrer le résumé et les cartes dans outputs/"""
        from .floodmap import export_event
        files = export_event(self)
        if download:
            try:
                from google.colab import files as colab_files
                for f in files:
                    colab_files.download(str(f))
            except Exception:
                pass
        return Result(("fl_h_export", {}), [("fl_export_line", dict(files=", ".join(str(f) for f in files)))],
                      values=dict(files=files))


def _choose(tab, when, side):
    """The pass to use for `when` (a date, or a 'cycle_pass' label) · Le passage à utiliser"""
    when = str(when)
    if "_" in when and when.replace("_", "").isdigit():
        hit = tab[tab["pass"] == when]
        return hit.iloc[0] if len(hit) else None
    d = pd.Timestamp(when)
    good = tab[tab.seen_pct >= min(50, tab.seen_pct.max())] if len(tab) else tab
    dates = pd.to_datetime(good.date)
    cand = good[dates <= d] if side == "before" else good[dates >= d]
    if cand.empty:
        return None
    gap = (pd.to_datetime(cand.date) - d).abs()
    return cand.loc[gap.idxmin()]


def choose_pair(tab, flood_date):
    """Suggested passes around a flood date: the first good pass on or after it, and the last good pass before it,
    on the same track if possible (same viewing geometry) · Passages suggérés autour d'une date de crue"""
    if tab is None or tab.empty:
        return None, None
    d = pd.Timestamp(flood_date)
    good = tab[tab.seen_pct >= min(50, tab.seen_pct.max())]
    dates = pd.to_datetime(good.date)
    after = good[dates >= d]
    if after.empty:
        return None, None
    a = after.loc[dates[dates >= d].idxmin()]
    earlier = good[dates < d]
    same = earlier[earlier.track == a.track]
    pool = same if len(same) else earlier
    b = pool.loc[pd.to_datetime(pool.date).idxmax()] if len(pool) else None
    return b, a


def _cause(e):
    while e is not None:
        if isinstance(e, (download.NeedLogin, download.MissingExtras, store.OfflineError)):
            return e
        e = e.__cause__
    return None


def flood_event(area, before=None, after=None, **settings_):
    """Water before and after a flood in one area · L'eau avant et après une crue dans une zone.

    flood_event("kinshasa_2024")                                      a ready-made example (offline)
    flood_event(area, before="2023-09-21", after="2024-01-03")        dates: the nearest good SWOT pass on each side
    flood_event(area, before="003_570", after="008_570")              or exact passes (cycle_pass) from area.passes()
    Settings (see FloodParams): max_wse_qual, min_water_frac, max_dark_frac, max_layover_m, k_mad, window_m,
    smooth_m, max_depth_m.
    """
    params = FloodParams(**settings_)
    if not isinstance(area, FloodArea):
        area = flood_area(area)
    if area.error:
        return FloodEvent(area, params, error=area.error)
    if area.example and before is None and after is None:
        before, after = EXAMPLES[area.key]["before"], EXAMPLES[area.key]["after"]
    if before is None or after is None:
        return FloodEvent(area, params, error=("fl_err_need_dates", {}))
    # the passes: the example's search, the last search, or a new search around the two dates
    try:
        tab, scenes = None, None
        if area.last_passes is not None and all(_choose(area.last_passes[0], w, s) is not None
                                                for w, s in ((before, "before"), (after, "after"))):
            tab, scenes = area.last_passes
        elif area.example:
            tab, scenes = area.pass_table(*EXAMPLES[area.key]["window"])
        if tab is None or _choose(tab, before, "before") is None or _choose(tab, after, "after") is None:
            ds = [pd.Timestamp(x) for x in (before, after) if "_" not in str(x)]
            if not ds:
                return FloodEvent(area, params, error=("fl_err_pass_unknown", dict(label=f"{before}, {after}")))
            start, end = f"{min(ds) - pd.Timedelta(days=30):%Y-%m-%d}", f"{max(ds) + pd.Timedelta(days=30):%Y-%m-%d}"
            tab, scenes = area.pass_table(start, end)
    except ValueError:                                     # a date that cannot be read
        return FloodEvent(area, params, error=("fl_err_need_dates", {}))
    except Exception as e:
        c = _cause(e)
        return FloodEvent(area, params, error=("fl_err_offline", {}) if isinstance(c, store.OfflineError)
                          else ("fl_err_search", {}))
    pb, pa = _choose(tab, before, "before"), _choose(tab, after, "after")
    if pb is None or pa is None:
        return FloodEvent(area, params, error=("fl_err_no_pass", dict(before=before, after=after)))
    if pb["pass"] == pa["pass"]:
        return FloodEvent(area, params, error=("fl_err_same_pass", dict(label=pb["pass"])))
    grid = area.grid
    passes, names = [], []
    for info in (pb, pa):
        name = f"flood_{area.key}_{info['pass']}.parquet"
        names.append(name)
        sc = scenes[(scenes.cycle + "_" + scenes.pass_id) == info["pass"]]
        try:
            table = download.swot_raster_pass(name, grid, sc)
        except Exception as e:
            c = _cause(e)
            key = ("fl_err_login" if isinstance(c, download.NeedLogin) else
                   "fl_err_extras" if isinstance(c, download.MissingExtras) else
                   "fl_err_offline_pass" if isinstance(c, store.OfflineError) else "fl_err_download")
            own = area.example and info["pass"] in (EXAMPLES[area.key]["before"], EXAMPLES[area.key]["after"])
            if own and key != "fl_err_download":
                key = "fl_err_example_missing"                # this copy of the package lacks the example's files
            return FloodEvent(area, params, error=(key, dict(label=info["pass"], mb=round(float(info["mb"])))))
        passes.append(PassGrid(grid, table, dict(info)))
    dem = None
    dem_name = f"flood_{area.key}_dem.parquet"
    try:
        dem = grid.to_grid(download.copernicus_dem(dem_name, grid), "dem")
        names.append(dem_name)
    except Exception:
        dem = None
    return FloodEvent(area, params, passes[0], passes[1], dem, origins=names)


def _in_notebook():
    try:
        from IPython import get_ipython
        return get_ipython() is not None and hasattr(get_ipython(), "kernel")
    except ImportError:
        return False


def _login_form():
    """Username and password boxes, so 'Run all' never stops to wait for typing"""
    import os
    import ipywidgets as W
    user = W.Text(description="Username", style={"description_width": "initial"})
    pwd = W.Password(description="Password", style={"description_width": "initial"})
    keep = W.Checkbox(True, description="Remember me on this computer (~/.netrc)", indent=False)
    btn = W.Button(description="Log in", button_style="primary", icon="sign-in")
    msg = W.HTML("")

    def go(_):
        old = {k: os.environ.get(k) for k in ("EARTHDATA_USERNAME", "EARTHDATA_PASSWORD")}
        os.environ["EARTHDATA_USERNAME"], os.environ["EARTHDATA_PASSWORD"] = user.value.strip(), pwd.value
        try:
            import earthaccess
            earthaccess.login(strategy="environment", persist=keep.value)
            ok = earthaccess.__auth__.authenticated
        except Exception:
            ok = False
        finally:
            for k, v in old.items():                        # do not leave the password in the environment
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            pwd.value = ""
        msg.value = Result(("fl_h_login", {}), [("fl_login_ok", {}) if ok else ("fl_login_failed", {})])._repr_html_()
    btn.on_click(go)
    intro = W.HTML(Result(("fl_h_login", {}), [("fl_login_ask", {})])._repr_html_())
    return W.VBox([intro, user, pwd, keep, btn, msg])


def earthdata_login(ask=None):
    """Log in to NASA Earthdata (free) so SWOT raster files can be downloaded · Connexion à NASA Earthdata.

    Uses EARTHDATA_USERNAME / EARTHDATA_PASSWORD or ~/.netrc if they exist. Otherwise, in a notebook, it shows a
    login form (so 'Run all' does not stop); elsewhere it asks in the terminal.
    Register at https://urs.earthdata.nasa.gov/users/new"""
    h = ("fl_h_login", {})
    try:
        download.earthaccess_session()
        return Result(h, [("fl_login_ok", {})])
    except download.MissingExtras:
        return Result(h, [("fl_err_extras", dict(label="", mb=0))])
    except download.NeedLogin:
        pass
    if ask is None and _in_notebook():
        return _login_form()
    try:
        download.earthaccess_session(interactive=True, persist=True)
    except download.NeedLogin:
        return Result(h, [("fl_login_failed", {})])
    return Result(h, [("fl_login_ok", {})])


def flood_examples():
    """The ready-made flood examples (offline) · Les exemples prêts"""
    table = pd.DataFrame([{"key": k, "name": e["name"], "before": e["before"], "after": e["after"],
                           "use": f'vg.flood_event("{k}")'} for k, e in EXAMPLES.items()])
    return Result(("fl_h_examples", {}), [], table=table)


__all__ = ["flood_area", "flood_event", "flood_examples", "earthdata_login", "FloodParams", "FloodArea", "FloodEvent",
           "EXAMPLES"]
