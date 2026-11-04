"""Explore more locations: the whole Congo, then the world · Explorer d'autres lieux : tout le Congo, puis le monde."""
import math

import folium
import numpy as np
import pandas as pd

from . import store
from .i18n import t
from .maps import base_map
from .results import Result
from . import plots

_CACHE = {}
RAMP = ["#c3c2b7", "#9ec5f4", "#5598e7", "#256abf", "#0d366b"]   # light → dark (unknown = grey)


def reach_index():
    """Every SWOT/SWORD v17b reach in the world (bundled) · Tous les tronçons SWORD v17b du monde"""
    if "index" not in _CACHE:
        _CACHE["index"] = pd.read_parquet(store.bundle_dir() / "locations" / "reach_index.parquet")
    return _CACHE["index"]


REGIONS = ("congo", "botswana")         # regions with a bundled table of reaches and their good-SWOT counts


def region_reaches(region):
    """Reaches of a region with their number of good SWOT levels (bundled) · Tronçons d'une région"""
    if region not in REGIONS:
        raise ValueError(f"Unknown region · Région inconnue : {region!r}. Known · Connues : {list(REGIONS)} + 'world'")
    if region not in _CACHE:
        _CACHE[region] = pd.read_parquet(store.bundle_dir() / "locations" / f"{region}_reaches.parquet")
    return _CACHE[region]


def region_outline(region):
    """Country outline as GeoJSON, if bundled (Natural Earth, public domain) · Contour du pays, s'il est fourni"""
    import json
    p = store.bundle_dir() / "locations" / f"{region}_outline.geojson"
    return json.loads(p.read_text()) if p.exists() else None


def congo_reaches():
    return region_reaches("congo")


def _km(lat, lon, lats, lons):
    lat1, lon1 = np.radians(lat), np.radians(lon)
    lat2, lon2 = np.radians(np.asarray(lats, float)), np.radians(np.asarray(lons, float))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def _near(lat, lon, radius_km, min_width_m=0):
    idx = reach_index()
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.05))
    lon_w = ((idx.lon - lon + 180) % 360) - 180          # handles the 180° meridian (Fiji)
    box = idx[(idx.lat.between(lat - dlat, lat + dlat)) & (lon_w.abs() <= dlon) & (idx.type != 6)
              & (idx.width_m >= min_width_m)].copy()
    box["km"] = _km(lat, lon, box.lat, box.lon)
    return box[box.km <= radius_km].sort_values("km")


def reaches_near(lat, lon, radius_km=25, min_width_m=0, n=15):
    """SWOT reaches near a point, nearest first · Tronçons SWOT proches d'un point, du plus proche au plus loin"""
    d = _near(lat, lon, radius_km, min_width_m).head(n)
    table = pd.DataFrame({"reach_id": d.reach_id.astype(str), "river": d.river_name.astype(str),
                          "width_m": d.width_m.round(0).astype(int), "km": d.km.round(1),
                          "lat": d.lat.round(4), "lon": d.lon.round(4),
                          "build": [f'vg.build_station("{r}")' for r in d.reach_id]})
    return Result(("h_reaches_near", {}), [], table=table.reset_index(drop=True), table_rows=n,
                  values=dict(reach_ids=list(table.reach_id)))


def _colour(v, bins):
    if v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v):
        return RAMP[0]
    for i, b in enumerate(bins):
        if v < b:
            return RAMP[i + 1] if i + 1 < len(RAMP) else RAMP[-1]
    return RAMP[-1]


def _points_layer(df, colour_col, bins, name, extra_fields):
    feats = []
    for r in df.itertuples(index=False):
        v = getattr(r, colour_col)
        props = {"reach_id": str(r.reach_id), "river": str(r.river_name) or "—",
                 "width_m": int(round(float(r.width_m))), "build": f'vg.build_station("{r.reach_id}")',
                 "_c": _colour(None if pd.isna(v) else float(v), bins),
                 "_r": float(np.clip(2 + np.log10(max(float(r.width_m), 100)) * 1.2, 3, 8))}
        for f in extra_fields:
            val = getattr(r, f)
            props[f] = "—" if pd.isna(val) else int(val)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(r.lon), float(r.lat)]},
                      "properties": props})
    fields = ["reach_id", "river", "width_m"] + list(extra_fields) + ["build"]
    aliases = ["reach_id", t("map_river"), t("map_width")] + [t("map_good_obs") for _ in extra_fields] + [t("map_code")]
    return folium.GeoJson(
        {"type": "FeatureCollection", "features": feats}, name=name,
        marker=folium.CircleMarker(radius=4, fill=True, fill_opacity=0.9, weight=0.5, color="#ffffff"),
        style_function=lambda f: {"fillColor": f["properties"]["_c"], "radius": f["properties"]["_r"],
                                  "color": "#ffffff", "weight": 0.5, "fillOpacity": 0.9},
        popup=folium.GeoJsonPopup(fields=fields, aliases=aliases))


def _legend(m, key, labels):
    swatches = "".join(f'<span style="white-space:nowrap"><span style="display:inline-block;width:12px;height:12px;'
                       f'border-radius:6px;background:{c};margin:0 4px 0 10px;vertical-align:middle"></span>{lab}</span> '
                       for c, lab in zip(RAMP, labels) if lab)
    m.get_root().html.add_child(folium.Element(
        f'<div style="position:absolute;z-index:9999;bottom:18px;left:12px;max-width:520px;background:#fcfcfbee;'
        f'padding:8px 10px;border-radius:8px;font:12px system-ui,sans-serif;color:#2e3a46">'
        f'{t(key, sep=" / ")}<br>{swatches}</div>'))


def _site_markers(m):
    from .sites import PRESETS
    fg = folium.FeatureGroup(name=t("map_sites"))
    for s in PRESETS.values():
        folium.Marker([s.lat, s.lon], tooltip=s.short,
                      popup=folium.Popup(f'<b>{s.short}</b><br><code>vg.build_station("{s.key}")</code>', max_width=320),
                      icon=folium.Icon(color="orange", icon="info-sign")).add_to(fg)
    fg.add_to(m)


def congo_map():
    """The whole Congo and its large tributaries, every SWOT reach marked · Tout le Congo, chaque tronçon SWOT"""
    c = congo_reaches()
    m = base_map(-2.0, 22.0, zoom=5, satellite_first=False)
    m.fit_bounds([[float(c.lat.min()) - 0.5, float(c.lon.min()) - 0.5], [float(c.lat.max()) + 0.5, float(c.lon.max()) + 0.5]])
    _points_layer(c, "good_obs", [10, 30, 60], t("map_reaches"), ["good_obs"]).add_to(m)
    _site_markers(m)
    _legend(m, "map_legend_congo", [t("map_not_counted", sep=" / "), "0–9", "10–29", "30–59", "60+"])
    folium.LayerControl().add_to(m)
    return m


def world_map(lat=None, lon=None, radius_km=300, min_width_m=None, max_points=3000):
    """World overview, or every reach within radius_km of a point · Vue du monde, ou les tronçons autour d'un point"""
    idx = reach_index()
    if lat is None or lon is None:
        d = idx[(idx.type == 1) & (idx.width_m >= (min_width_m or 2000))]
        d = d.sort_values("width_m", ascending=False).head(max_points)
        m = base_map(10, 20, zoom=2, satellite_first=False)
    else:
        d = _near(lat, lon, radius_km, min_width_m or 0)
        if len(d) > max_points:
            print(t("map_too_many", n=max_points))
            d = d.sort_values("width_m", ascending=False).head(max_points)
        m = base_map(lat, lon, zoom=8)
        dlat = radius_km / 111.32
        dlon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.1))
        m.fit_bounds([[lat - dlat, lon - dlon], [lat + dlat, lon + dlon]])   # the whole circle fits any window
    _points_layer(d, "width_m", [300, 1000, 3000, 10000], t("map_reaches"), []).add_to(m)
    _site_markers(m)
    _legend(m, "map_legend_world", ["", "< 300 m", "300–1000 m", "1–3 km", "> 3 km"])
    folium.LayerControl().add_to(m)
    return m


def compare_stations(keys, **settings_):
    """Water levels at several stations, one panel each · Niveaux de plusieurs stations, un panneau chacune"""
    from .station import build_station
    levels, lines, stations = {}, [], {}
    for k in keys:
        st = build_station(k, **settings_)
        stations[k] = st
        if st.error or len(st.data.vs) == 0:
            continue
        vs = st.data.vs
        levels[st.site.short] = vs
        month = (vs.assign(a=vs.wse_m - vs.wse_m.median(), m=vs.time.dt.month).groupby("m").a.median().idxmax())
        lines.append(("stations_peak", dict(label=st.site.short, month=int(month))))
    return Result(("h_compare_stations", {}), lines,
                  figure=(lambda: plots.fig_compare_stations(levels)) if levels else None,
                  values=dict(stations=stations))
