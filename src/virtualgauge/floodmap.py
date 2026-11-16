"""Interactive flood map (folium) and export (English only for now) · Carte interactive et export."""
import json

import matplotlib
import numpy as np
import pandas as pd

from . import settings
from .i18n import t
from .style import COL


def _to_latlon(grid, rgba):
    """Resample an RGBA image from the UTM grid to a lon/lat image for the web map (nearest cell)"""
    from pyproj import Transformer
    w, s, e, n = grid.bounds_ll()
    h, wd = grid.ny, grid.nx
    lats = n - (np.arange(h) + 0.5) * (n - s) / h
    lons = w + (np.arange(wd) + 0.5) * (e - w) / wd
    lon, lat = np.meshgrid(lons, lats)
    x, y = Transformer.from_crs(4326, grid.crs, always_xy=True).transform(lon, lat)
    r, c, ok = grid.index(x, y)
    out = np.zeros((h, wd, 4))
    out[ok] = rgba[r[ok], c[ok]]
    return out, [[s, w], [n, e]]


def _rgba(mask, colour, alpha=0.85):
    out = np.zeros(mask.shape + (4,))
    out[mask] = matplotlib.colors.to_rgba(colour, alpha)
    return out


def _legend_html(items, depth_max):
    from .floodplots import BLUES
    stops = ", ".join(matplotlib.colors.to_hex(BLUES(x)) for x in np.linspace(0, 1, 7))
    rows = "".join(f'<div><span style="display:inline-block;width:12px;height:12px;background:{c};'
                   f'margin-right:6px;vertical-align:middle"></span>{lab}</div>' for lab, c in items)
    bar = (f'<div style="margin-top:6px">{t("fl_lab_depth")}</div>'
           f'<div style="width:150px;height:10px;background:linear-gradient(to right, {stops})"></div>'
           f'<div style="width:150px;display:flex;justify-content:space-between"><span>0</span>'
           f'<span>{depth_max:.1f}</span></div>')
    return (f'<div style="position:fixed;bottom:24px;left:12px;z-index:9999;background:{COL["bg"]};'
            f'color:{COL["ink"]};padding:8px 10px;border-radius:6px;font:12px system-ui,sans-serif;'
            f'box-shadow:0 1px 4px rgba(0,0,0,.25)">{rows}{bar}</div>')


def event_map(ev):
    """Water before, after, change and depth over a satellite image · Carte sur image satellite"""
    import folium
    from shapely.geometry import mapping
    from .floodplots import BLUES, FLOOD_C, GONE_C, WATER_C
    from .maps import base_map
    g, a = ev.area.grid, ev._a()
    c = ev.area.polygon.centroid
    m = base_map(c.y, c.x, zoom=11)
    d = ev._dates()
    inside = g.inside
    layers = [(t("fl_map_before", date=d["before"]), _rgba(a["water_before"] & inside, WATER_C), False),
              (t("fl_map_after", date=d["after"]), _rgba(a["water_after"] & inside, WATER_C), False)]
    change = _rgba(a["cls"] == 3, WATER_C, 0.6) + _rgba(a["cls"] == 4, FLOOD_C) + _rgba(a["cls"] == 5, GONE_C)
    layers.append((t("fl_map_change"), change, True))
    dep = a["depth"]
    vmax = 1.0
    if np.isfinite(dep).any():
        vmax = max(float(np.nanpercentile(dep, 98)), 0.5)
        rgba = BLUES(np.clip(np.nan_to_num(dep) / vmax, 0, 1))
        rgba[..., 3] = np.where(np.isfinite(dep), 0.9, 0)
        layers.append((t("fl_map_depth"), rgba, True))
    layers.append((t("fl_map_unseen"), _rgba((a["cls"] == 1), "#000000", 0.35), False))
    for name, img, show in layers:
        im, bounds = _to_latlon(g, img)
        folium.raster_layers.ImageOverlay(im, bounds=bounds, name=name, show=show, interactive=False).add_to(m)
    folium.GeoJson(mapping(ev.area.polygon), name=t("fl_map_area"),
                   style_function=lambda f: {"color": "#ffffff", "weight": 2, "fill": False}).add_to(m)
    w, s, e, n = ev.area.polygon.bounds
    m.fit_bounds([[s, w], [n, e]])
    folium.LayerControl(collapsed=False).add_to(m)
    m.get_root().html.add_child(folium.Element(_legend_html(
        [(t("fl_cls_water_short"), WATER_C), (t("fl_cls_flooded"), FLOOD_C), (t("fl_cls_receded"), GONE_C)], vmax)))
    return m


def export_event(ev):
    """Summary CSV, area GeoJSON, and the maps as a GeoTIFF (or a CSV of cells without rasterio)"""
    out = settings.out_dir()
    out.mkdir(parents=True, exist_ok=True)
    g, a = ev.area.grid, ev._a()
    base = f"flood_{ev.area.key}_{ev.before.label}_{ev.after.label}"
    files = []
    p = out / f"{base}_summary.csv"
    ev.summary().table.to_csv(p, index=False)
    files.append(p)
    from shapely.geometry import mapping
    p = out / f"{base}_area.geojson"
    p.write_text(json.dumps({"type": "Feature", "properties": {"name": ev.area.name},
                             "geometry": mapping(ev.area.polygon)}))
    files.append(p)
    bands = {"class": a["cls"].astype("float32"), "depth_m": a["depth"], "rise_m": a["rise"],
             "wse_before_m": a["wse_before"], "wse_after_m": a["wse_after"],
             "ground_m": a["dem"] if a["dem"] is not None else np.full(a["cls"].shape, np.nan)}
    try:
        import rasterio
        p = out / f"{base}_maps.tif"
        with rasterio.open(p, "w", driver="GTiff", height=g.ny, width=g.nx, count=len(bands), dtype="float32",
                           crs=g.crs.to_wkt(), transform=g.transform(), nodata=np.nan, compress="deflate") as dst:
            for i, (name, arr) in enumerate(bands.items(), start=1):
                dst.write(arr.astype("float32"), i)
                dst.set_band_description(i, name)
            dst.update_tags(classes="0 outside, 1 not seen, 2 dry, 3 water before and after, 4 newly flooded, "
                                    "5 water gone", datum="heights in m above the EGM2008 geoid")
        files.append(p)
    except ImportError:
        from pyproj import Transformer
        r, c = np.nonzero(a["cls"] >= 2)
        xc, yc = g.centres()
        lon, lat = Transformer.from_crs(g.crs, 4326, always_xy=True).transform(xc[c], yc[r])
        df = pd.DataFrame({"lon": lon, "lat": lat, **{k: v[r, c] for k, v in bands.items()}})
        p = out / f"{base}_cells.csv"
        df.to_csv(p, index=False, float_format="%.3f")
        files.append(p)
    return files
