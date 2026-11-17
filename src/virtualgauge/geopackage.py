"""A river survey as a GeoPackage for QGIS, with a ready-made style · Un relevé en GeoPackage pour QGIS, déjà stylé.

Layers · couches:
    reaches      one line per SWOT reach with its numbers (lowest, highest and latest level, index, band)
    ports        the river ports, with the index of their reach
    levels       (optional) every SWOT level, kept or removed, with its reason — a table without geometry
    layer_styles QGIS reads it by itself: the rivers open coloured by their index, the ports with their names

The lines join each reach centre (SWORD v17b) half-way to its neighbours, as on the notebook maps: they show the river
network, not the exact course of the river.
"""
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .i18n import t

GEOM = "geom"                                  # the geometry column GDAL gives a GeoPackage layer
REACH_COLS = ["reach_id", "river_name", "lat", "lon", "width_m", "type_name", "n_good", "first", "last", "low_m",
              "low_date", "high_m", "high_date", "range_m", "noise_m", "now_m", "now_date", "age_days", "index", "band",
              "band_name", "why", "colour"]
# Line width in QGIS (mm), as on the notebook maps: wider rivers drawn thicker, reaches with no index thin.
WIDTH_MM = ('CASE WHEN "band" < 0 THEN 0.15 ELSE max(0.2, min(1.05, 0.18 + 0.35 * log10(max(coalesce("width_m", 100), 50) / 50))) END')


def _lines(net):
    """reach_id -> (Multi)LineString from its half-segments"""
    import shapely
    seg, _ = net
    out = {}
    for rid, g in seg.groupby("reach_id"):
        parts = shapely.linestrings(g[["x0", "y0", "x1", "y1"]].to_numpy().reshape(-1, 2, 2))
        out[int(rid)] = shapely.line_merge(shapely.multilinestrings(parts))
    return out


def _rgba(hex_colour, alpha=255):
    h = hex_colour.lstrip("#")
    return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4)) + f",{alpha}"


def _option_map(parent, items, name=None):
    m = ET.SubElement(parent, "Option", ({"name": name} if name else {}) | {"type": "Map"})
    for k, v in items.items():
        ET.SubElement(m, "Option", name=k, type="QString", value=str(v))
    return m


def _qml(renderer, labels=None):
    root = ET.Element("qgis", version="3.28.0", styleCategories="Symbology|Labeling",
                      labelsEnabled="1" if labels is not None else "0")
    root.append(renderer)
    if labels is not None:
        root.append(labels)
    return "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n" + ET.tostring(root, encoding="unicode")


def _line_symbol(name, colour):
    sym = ET.Element("symbol", type="line", name=str(name), alpha="1", clip_to_extent="1", force_rhr="0")
    lay = ET.SubElement(sym, "layer", {"class": "SimpleLine", "enabled": "1", "locked": "0", "pass": "0"})
    _option_map(lay, {"line_color": _rgba(colour), "line_width": "0.5", "line_width_unit": "MM", "line_style": "solid",
                      "capstyle": "round", "joinstyle": "round"})
    ddp = ET.SubElement(lay, "data_defined_properties")
    top = ET.SubElement(ddp, "Option", type="Map")
    ET.SubElement(top, "Option", name="name", type="QString", value="")
    props = ET.SubElement(top, "Option", name="properties", type="Map")
    width = ET.SubElement(props, "Option", name="outlineWidth", type="Map")
    ET.SubElement(width, "Option", name="active", type="bool", value="true")
    ET.SubElement(width, "Option", name="expression", type="QString", value=WIDTH_MM)
    ET.SubElement(width, "Option", name="type", type="int", value="3")
    ET.SubElement(top, "Option", name="type", type="QString", value="collection")
    return sym


def reaches_style(bands, no_index_colour):
    """QML: reaches coloured by their index band (navigation.BANDS), wide rivers on top"""
    r = ET.Element("renderer-v2", type="categorizedSymbol", attr="band", enableorderby="1", forceraster="0",
                   symbollevels="0")
    cats, syms = ET.SubElement(r, "categories"), ET.SubElement(r, "symbols")
    rows = [(b, key, c) for b, (_, key, c) in reversed(list(enumerate(bands)))] + [(-1, "nv_no_index", no_index_colour)]
    for i, (value, key, colour) in enumerate(rows):
        ET.SubElement(cats, "category", value=str(value), label=t(key), symbol=str(i), render="true", type="long")
        syms.append(_line_symbol(i, colour))
    order = ET.SubElement(r, "orderby")
    clause = ET.SubElement(order, "orderByClause", asc="1", nullhead="1")
    clause.text = 'CASE WHEN "band" < 0 THEN -1 ELSE coalesce("width_m", 0) END'
    return _qml(r)


def ports_style(ink="#0b0d10", paper="#fcfcfb"):
    """QML: ports as dark dots with their names"""
    r = ET.Element("renderer-v2", type="singleSymbol", enableorderby="0", forceraster="0", symbollevels="0")
    syms = ET.SubElement(r, "symbols")
    sym = ET.SubElement(syms, "symbol", type="marker", name="0", alpha="1", clip_to_extent="1", force_rhr="0")
    lay = ET.SubElement(sym, "layer", {"class": "SimpleMarker", "enabled": "1", "locked": "0", "pass": "0"})
    _option_map(lay, {"name": "circle", "color": _rgba(ink), "outline_color": _rgba(paper), "outline_width": "0.4",
                      "outline_width_unit": "MM", "outline_style": "solid", "size": "2.6", "size_unit": "MM"})
    lab = ET.Element("labeling", type="simple")
    st = ET.SubElement(lab, "settings", calloutType="simple")
    ts = ET.SubElement(st, "text-style", fieldName="name", isExpression="0", fontSize="9", fontSizeUnit="Point",
                       textColor=_rgba("#2e3a46"), textOpacity="1", fontWeight="50", namedStyle="Regular")
    ET.SubElement(ts, "text-buffer", bufferDraw="1", bufferSize="0.8", bufferSizeUnits="MM",
                  bufferColor=_rgba(paper), bufferOpacity="0.85", bufferJoinStyle="128")
    ET.SubElement(st, "placement", placement="0", dist="1.2", distUnits="MM", quadOffset="2", priority="5")
    ET.SubElement(st, "rendering", obstacle="1", scaleVisibility="0", displayAll="1", drawLabels="1")
    return _qml(r, lab)


def write(path, df, net, ports, bands, no_index_colour, levels=None, about=None):
    """Write the survey (df: RiverSurvey.to_dataframe) into a GeoPackage at `path`, replacing any older file."""
    import geopandas as gpd
    import pyogrio
    import shapely

    path = str(path)
    for old in (path, path + ".aux.xml"):           # a sidecar left by GDAL or QGIS would mix old metadata in
        if os.path.exists(old):
            os.remove(old)
    meta = {k: str(v) for k, v in (about or {}).items()}

    lines = _lines(net)
    d = df.copy()
    d["band_name"] = [t(bands[b][1]) if b >= 0 else t("nv_why_" + str(w).replace(" ", "_"))
                      for b, w in zip(d.band, d.why)]
    d["colour"] = [bands[b][2] if b >= 0 else no_index_colour for b in d.band]
    d = d[REACH_COLS].round({"lat": 5, "lon": 5, "width_m": 0, "low_m": 3, "high_m": 3, "range_m": 3, "noise_m": 3,
                             "now_m": 3, "age_days": 1, "index": 1})
    for c in ("first", "last", "low_date", "high_date", "now_date"):
        d[c] = pd.to_datetime(d[c]).astype("datetime64[ms]")
    geom = [lines.get(int(r)) for r in d.reach_id]
    reaches = gpd.GeoDataFrame(d, geometry=geom, crs="EPSG:4326")
    pyogrio.write_dataframe(reaches, path, layer="reaches", driver="GPKG", promote_to_multi=True,
                            layer_options={"DESCRIPTION": "SWOT river reaches with their navigability index"},
                            dataset_metadata=meta)

    p = df.set_index("reach_id")
    rows = []
    for port in ports:
        r = p.loc[port["reach_id"]]
        b = int(r.band)
        rows.append({"name": port["name"], "river": port["river"], "reach_id": int(port["reach_id"]),
                     "index": round(float(r["index"]), 1) if b >= 0 else None,
                     "band_name": t(bands[b][1]) if b >= 0 else t("nv_why_" + str(r.why).replace(" ", "_")),
                     "now_m": round(float(r.now_m), 3) if np.isfinite(r.now_m) else None,
                     "now_date": r.now_date, "range_m": round(float(r.range_m), 3) if np.isfinite(r.range_m) else None})
    if rows:
        pt = pd.DataFrame(rows)
        pt["now_date"] = pd.to_datetime(pt.now_date).astype("datetime64[ms]")
        pt = gpd.GeoDataFrame(pt, geometry=shapely.points([[q["lon"], q["lat"]] for q in ports]), crs="EPSG:4326")
        pyogrio.write_dataframe(pt, path, layer="ports", driver="GPKG",
                                layer_options={"DESCRIPTION": "River ports and the index of their reach"})

    layers = ["reaches"] + (["ports"] if rows else [])
    if levels is not None:
        cols = ["reach_id", "time", "wse", "wse_u", "width", "reach_q", "xovr_cal_q", "dark_frac", "reason"]
        lv = levels[[c for c in cols if c in levels]].copy()          # the copy shipped with the package has fewer
        lv["time"] = pd.to_datetime(lv.time).astype("datetime64[ms]")
        lv["reason"] = lv.reason.astype(str)
        lv["kept"] = lv.reason == "kept"
        pyogrio.write_dataframe(lv.round({"wse": 3, "wse_u": 3, "width": 1, "dark_frac": 3}), path, layer="levels",
                                driver="GPKG",
                                layer_options={"DESCRIPTION": "Every SWOT level, kept or removed (reason)"})
        layers.append("levels")

    qml = {"reaches": reaches_style(bands, no_index_colour), "ports": ports_style()}
    styled = [n for n in layers if n in qml]
    now = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None)).floor("s")
    styles = pd.DataFrame({
        "f_table_catalog": "", "f_table_schema": "", "f_table_name": styled, "f_geometry_column": GEOM,
        "styleName": [f"{n} (virtualgauge)" for n in styled], "styleQML": [qml[n] for n in styled],
        "styleSLD": "", "useAsDefault": True, "description": "virtualgauge", "owner": "", "ui": "",
        "update_time": now})
    styles["update_time"] = styles.update_time.astype("datetime64[ms]")
    pyogrio.write_dataframe(styles, path, layer="layer_styles", driver="GPKG")
    return layers
