"""Figures and maps for river navigability (English or French: vg.set_language).

Index colours (navigation.BANDS): a diverging red ↔ blue scale with a neutral grey middle — red = low water
(poor navigability), blue = high water (good). The two arms are matched in lightness. Reaches with no index are drawn
thin and pale, behind everything. Counts and ranges use one blue, light → dark.
"""
import json

import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from . import store
from .i18n import t, title
from .navigation import BANDS, NO_INDEX_C, band_colour, band_label
from .style import COL, dots, new_figure, removed_style, styled

LAND, SEA, BORDER = "#f1f0eb", COL["bg"], "#c9c7bf"
LIGHT_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
LIGHT_ATTR = "Esri, HERE, Garmin, © OpenStreetMap contributors"
SEQ = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]          # sequential blue, steps 250 → 700 (ordinal on light)


def _width_lw(w):
    w = np.asarray(w, float)
    return np.clip(0.5 + 1.0 * np.log10(np.maximum(np.nan_to_num(w, nan=100), 50) / 50), 0.6, 3.0)


def _countries():
    p = store.bundle_dir() / "locations" / "congo_countries.geojson"
    return json.loads(p.read_text())["features"] if p.exists() else []


def _rings(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        yield np.asarray(poly[0])


def _base(ax, extent):
    """Land, borders and a light frame · fond de carte"""
    from matplotlib.patches import Polygon as MPoly
    ax.set_facecolor(SEA)
    for f in _countries():
        for ring in _rings(f["geometry"]):
            ax.add_patch(MPoly(ring, closed=True, facecolor=LAND, edgecolor=BORDER, linewidth=0.6, zorder=0))
    w, e, s, n = extent
    ax.set_xlim(w, e)
    ax.set_ylim(s, n)
    ax.set_aspect(1 / np.cos(np.radians((s + n) / 2)))
    ax.grid(False)
    ax.tick_params(labelsize=8.5)
    ax.xaxis.set_major_formatter(lambda v, _: f"{abs(v):.0f}°{'E' if v >= 0 else 'W'}")
    ax.yaxis.set_major_formatter(lambda v, _: f"{abs(v):.0f}°{'N' if v > 0 else ('S' if v < 0 else '')}")
    for side in ("top", "right"):
        ax.spines[side].set_visible(True)


def _extent(tab, pad=0.6):
    return (float(tab.lon.min()) - pad, float(tab.lon.max()) + pad, float(tab.lat.min()) - pad, float(tab.lat.max()) + pad)


def _draw(ax, net, colour, width, zorder=2):
    """Half-segments of the reaches in `colour` (reach_id -> colour); narrow rivers first, wide ones on top."""
    seg, lone = net
    s = seg[seg.reach_id.isin(colour.index)].copy()
    if len(s):
        s["c"] = s.reach_id.map(colour)
        s["w"] = s.reach_id.map(width)
        s = s.sort_values("w")
        lc = LineCollection(np.stack([s[["x0", "y0"]].to_numpy(), s[["x1", "y1"]].to_numpy()], axis=1),
                            colors=s.c.to_list(), linewidths=s.w.to_numpy(), capstyle="round", zorder=zorder)
        ax.add_collection(lc)
    lo = lone[lone.reach_id.isin(colour.index)]
    if len(lo):
        ax.scatter(lo.lon, lo.lat, s=4, c=lo.reach_id.map(colour).to_list(), linewidths=0, zorder=zorder)


def _ports(ax, ports, fontsize=8.5):
    for p in ports:
        ax.plot(p["lon"], p["lat"], marker="o", ms=4.5, mfc=COL["ink"], mec=COL["bg"], mew=1.0, ls="none", zorder=5)
        ax.annotate(p["name"], (p["lon"], p["lat"]), xytext=(5, 3), textcoords="offset points", fontsize=fontsize,
                    color=COL["ink2"], zorder=6,
                    bbox=dict(boxstyle="round,pad=0.15", fc=COL["bg"], ec="none", alpha=0.75))


def _legend(ax, handles, loc="lower left", title_=None):
    leg = ax.legend(handles=handles, loc=loc, fontsize=8.5, title=title_, title_fontsize=8.5, frameon=True,
                    framealpha=0.92, facecolor=COL["bg"], edgecolor=COL["grid"], alignment="left")
    leg.get_frame().set_linewidth(0.6)
    return leg


def _line(c, lw=2.5):
    return dict(color=c, lw=lw, solid_capstyle="round")


def _binned_map(tab, net, values, bins, labels, none_label, ttl):
    """A map of reaches in four blue classes (light → dark), pale where there is no value."""
    with styled():
        fig, ax = new_figure(9, 8.6)
        _base(ax, _extent(tab))
        v = pd.Series(np.asarray(values, float), index=tab.reach_id.to_numpy())
        cls = pd.Series(np.digitize(v.fillna(-np.inf), bins) - 1, index=v.index)
        cls[v.isna()] = -1
        width = pd.Series(_width_lw(tab.width_m), index=tab.reach_id.to_numpy())
        none = cls.index[cls < 0]
        _draw(ax, net, pd.Series(NO_INDEX_C, index=none), pd.Series(0.5, index=none), zorder=1)
        have = cls.index[cls >= 0]
        _draw(ax, net, cls[have].map(lambda i: SEQ[min(i, 3)]), width[have], zorder=2)
        handles = [Line2D([], [], **_line(SEQ[i]), label=f"{lab}  ({int((cls == i).sum())})") for i, lab in enumerate(labels)]
        handles.append(Line2D([], [], **_line(NO_INDEX_C, 1.2), label=f"{none_label}  ({len(none)})"))
        _legend(ax, handles)
        ax.set_title(title(ttl[0], **ttl[1]))
    return fig


def fig_coverage(tab, net, name):
    n = tab.n_good.where(tab.n_good > 0)
    return _binned_map(tab, net, n, [1, 50, 90, 110], ["1–49", "50–89", "90–109", t("nv_lab_or_more", n=110)],
                       t("nv_lab_none_measured"), ("nv_ttl_coverage", dict(name=name)))


def fig_ranges(tab, net, name):
    r = tab.range_m.where(tab.why == "")
    return _binned_map(tab, net, r, [0, 2, 4, 6], [t("nv_lab_less_than", v="2 m"), "2–4 m", "4–6 m",
                                                   t("nv_lab_more_than", v="6 m")],
                       t("nv_lab_no_range"), ("nv_ttl_ranges", dict(name=name)))


def fig_index_map(df, net, name, day, ports):
    with styled():
        fig, ax = new_figure(9, 9.2)
        _base(ax, _extent(df))
        ids = df.reach_id.to_numpy()
        band = pd.Series(df.band.to_numpy(), index=ids)
        width = pd.Series(_width_lw(df.width_m), index=ids)
        none = band.index[band < 0]
        _draw(ax, net, pd.Series(NO_INDEX_C, index=none), pd.Series(0.5, index=none), zorder=1)
        have = band.index[band >= 0]
        _draw(ax, net, band[have].map(band_colour), width[have], zorder=2)
        _ports(ax, ports)
        handles = [Line2D([], [], **_line(c), label=f"{t(k)}  ({int((band == i).sum())})")
                   for i, (_, k, c) in reversed(list(enumerate(BANDS)))]
        handles.append(Line2D([], [], **_line(NO_INDEX_C, 1.2), label=f"{t('nv_no_index')}  ({len(none)})"))
        _legend(ax, handles, title_=t("nv_lab_index"))
        ax.set_title(title("nv_ttl_index", name=name, date=day) + "\n" + t("nv_sub_index"))
        ax.title.set_fontsize(12)
    return fig


def fig_reach(lv, row, rid, date):
    with styled():
        fig, ax = new_figure(10, 4.2)
        rem, kep = lv[lv.reason != "kept"], lv[lv.reason == "kept"]
        if len(rem):
            ax.plot(rem.time, rem.wse, **removed_style(), label=t("lab_removed"))
        ax.plot(kep.time, kep.wse, color=COL["axis"], lw=0.8, zorder=1)
        ax.plot(kep.time, kep.wse, **dots(COL["SWOT"], ms=5), label=t("nv_lab_good"), zorder=2)
        if np.isfinite(row.low_m):
            for v, key in ((row.low_m, "nv_lab_lowest"), (row.high_m, "nv_lab_highest")):
                ax.axhline(v, color=COL["ink2"], lw=0.9, ls=(0, (4, 3)), zorder=1)
                ax.annotate(f"{t(key)}: {v:.2f} m", (0.005, v), xycoords=("axes fraction", "data"), xytext=(0, 3),
                            textcoords="offset points", fontsize=8.5, color=COL["ink2"])
        if np.isfinite(row["index"]):
            c = band_colour(int(row.band))
            ax.plot([row.now_date], [row.now_m], marker="o", ms=11, mfc=c, mec=COL["ink"], mew=1.2, ls="none",
                    zorder=3, label=f"{t('nv_lab_now')}: {t('nv_lab_index').lower()} {row['index']:.0f}")
        ax.set_ylabel(t("lab_level"))
        if len(kep):
            pad = max(0.15 * (kep.wse.max() - kep.wse.min()), 0.2)
            ax.set_ylim(kep.wse.min() - pad, kep.wse.max() + 1.6 * pad)
        ax.legend(loc="upper right", ncols=3, fontsize=9)
        ax.set_title(title("nv_ttl_reach", river=row.river_name, reach=rid))
    return fig


def fig_ports(series, date):
    n = len(series)
    ncols = 3 if n > 4 else n
    nrows = int(np.ceil(n / ncols))
    with styled():
        fig, axes = new_figure(10.5, 2.3 * nrows + 0.6, nrows, ncols, sharex=True, sharey=True, squeeze=False)
        for ax in axes.flat[n:]:
            ax.set_visible(False)
        for ax, (name, (s, row)) in zip(axes.flat, series.items()):
            s = s.sort_values("time")
            for y in (20, 40, 60, 80):
                ax.axhline(y, color=COL["grid"], lw=0.8, zorder=0)
            ax.plot(s.time, s["index"], color=COL["axis"], lw=0.9, zorder=1)
            ax.scatter(s.time, s["index"], s=14, c=[band_colour(b) for b in np.clip(s["index"] // 20, 0, 4).astype(int)],
                       linewidths=0.4, edgecolors=COL["bg"], zorder=2)
            last = s[s.time <= date].tail(1)
            if len(last):
                b = int(np.clip(last["index"].iloc[0] // 20, 0, 4))
                ax.plot(last.time, last["index"], marker="o", ms=9, mfc=band_colour(b), mec=COL["ink"], mew=1.1,
                        ls="none", zorder=3)
            now = f"{row['index']:.0f}" if np.isfinite(row["index"]) else "—"
            ax.set_title(t("nv_ttl_port", port=name, index=now), fontsize=10)
            ax.set_ylim(-5, 105)
            ax.set_yticks([0, 50, 100])
            ax.grid(False)
        import matplotlib.dates as mdates
        for ax in axes.flat[:n]:
            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
            ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[4, 7, 10]))
        fig.suptitle(t("nv_ttl_ports"), x=0.01, ha="left", fontweight="bold", fontsize=12)
    return fig


def fig_profile(path, ports, river, day):
    p = path.sort_values("dist_out_km", ascending=False)
    with styled():
        fig, (a1, a2) = new_figure(10.5, 6.2, 2, 1, sharex=True, height_ratios=[1.25, 1])
        x = p.dist_out_km.to_numpy()
        rng = p.range_m.where(p.why.isin(["", "no recent level"]))
        a1.fill_between(x, 0, rng.to_numpy(), color="#dfe8f3", lw=0, step="mid", label=t("nv_lab_range_band"))
        a1.plot(x, rng.to_numpy(), color=COL["SWOT"], lw=1.0, drawstyle="steps-mid")
        has = p[p["index"].notna()]
        for a, y in ((a1, has.now_m - has.low_m), (a2, has["index"])):
            a.scatter(has.dist_out_km, y, s=16, c=[band_colour(b) for b in has.band], linewidths=0.4,
                      edgecolors=COL["ink2"], zorder=3, label=t("nv_lab_now") if a is a1 else None)
        a1.set_ylabel(t("nv_lab_above_low"))
        a1.set_ylim(0, max(float(np.nanmax(rng.to_numpy())) if rng.notna().any() else 1, 1) * 1.12)
        for y in (20, 40, 60, 80):
            a2.axhline(y, color=COL["grid"], lw=0.8, zorder=0)
        a2.grid(False)
        a2.set_ylim(-5, 105)
        a2.set_yticks([0, 20, 40, 60, 80, 100])
        a2.set_ylabel(t("nv_lab_index"))
        a2.set_xlabel(t("nv_lab_dist"))
        a2.set_xlim(x.max() + 20 if len(x) else 1, -20)
        a2.legend(handles=[Patch(facecolor="#dfe8f3", edgecolor=COL["SWOT"], label=t("nv_lab_range_band")),
                           Line2D([], [], marker="o", ls="none", mfc=BANDS[2][2], mec=COL["ink2"], ms=6,
                                  label=t("nv_lab_now"))],
                  loc="upper left", fontsize=9, ncols=2)
        from .locations import _km
        for port in ports:
            d = _km(port["lat"], port["lon"], p.lat, p.lon)
            if len(d) and d.min() <= 20:
                xp = float(p.dist_out_km.iloc[int(np.argmin(d))])
                for a in (a1, a2):
                    a.axvline(xp, color=COL["axis"], lw=0.8, ls=(0, (2, 2)), zorder=0)
                a1.annotate(port["name"], (xp, 1.0), xycoords=("data", "axes fraction"), xytext=(2, -2),
                            textcoords="offset points", fontsize=8.5, color=COL["ink2"], va="top")
        a1.set_title(title("nv_ttl_profile", river=river, date=day))
    return fig


def fig_history(hist, name):
    cols = [t(k) for _, k, _ in BANDS]
    h = hist[cols].fillna(0)
    with styled():
        fig, ax = new_figure(10.5, 4.2)
        ax.stackplot(h.index, *[h[c].to_numpy() for c in cols], colors=[c for _, _, c in BANDS],
                     labels=cols, edgecolor=COL["bg"], linewidth=0.8)
        ax.set_ylim(0, 100)
        ax.set_xlim(h.index.min(), h.index.max())
        ax.set_ylabel(t("nv_lab_share"))
        handles = [Patch(facecolor=c, label=t(k)) for _, k, c in reversed(BANDS)]
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=9, frameon=False)
        ax.set_title(title("nv_ttl_history", name=name))
    return fig


# --- interactive map and GeoJSON ------------------------------------------------------------------------------
def _fmt(v, nd=2):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) or pd.isna(v) else f"{v:.{nd}f}"


def index_geojson(df, net, full=False):
    """One feature per reach (its half-segments as a MultiLineString) with its numbers"""
    seg, lone = net
    lines = {rid: g[["x0", "y0", "x1", "y1"]].round(4).to_numpy().tolist() for rid, g in seg.groupby("reach_id")}
    pts = dict(zip(lone.reach_id, zip(lone.lon.round(4), lone.lat.round(4))))
    feats = []
    for r in df.rename(columns={"index": "idx"}).itertuples(index=False):
        rid = int(r.reach_id)
        if rid in lines:
            geom = {"type": "MultiLineString", "coordinates": [[[a, b], [c, d]] for a, b, c, d in lines[rid]]}
        elif rid in pts:
            geom = {"type": "Point", "coordinates": [float(pts[rid][0]), float(pts[rid][1])]}
        else:
            continue
        b = int(r.band)
        props = {"reach_id": str(rid), "river": str(r.river_name),
                 "index": "—" if b < 0 else f"{r.idx:.0f}",
                 "band": band_label(b) if b >= 0 else t("nv_why_" + str(r.why).replace(" ", "_")),
                 "latest": "—" if pd.isna(r.now_date) else f"{_fmt(r.now_m)} m, {pd.Timestamp(r.now_date):%Y-%m-%d}",
                 "range": "—" if not np.isfinite(r.range_m) else
                          f"{_fmt(r.low_m)} – {_fmt(r.high_m)} m ({_fmt(r.range_m)} m)",
                 "good_levels": int(r.n_good),
                 "_c": band_colour(b), "_w": float(_width_lw([r.width_m])[0]) + 0.6 if b >= 0 else 1.0}
        if full:
            props.update(index_value=None if b < 0 else round(float(r.idx), 1), width_m=None if pd.isna(r.width_m)
                         else round(float(r.width_m)), low_m=None if pd.isna(r.low_m) else round(float(r.low_m), 3),
                         high_m=None if pd.isna(r.high_m) else round(float(r.high_m), 3), why=str(r.why))
            props.pop("_w")
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
    return {"type": "FeatureCollection", "features": feats}


def index_folium(df, net, name, day, ports):
    import folium
    from .maps import ESRI, ESRI_ATTR
    m = folium.Map(location=[float(df.lat.mean()), float(df.lon.mean())], zoom_start=5, tiles=None)
    folium.TileLayer(tiles=LIGHT_TILES, attr=LIGHT_ATTR, name=t("nv_map_grey")).add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.TileLayer(tiles=ESRI, attr=ESRI_ATTR, name=t("map_image")).add_to(m)
    m.fit_bounds([[float(df.lat.min()), float(df.lon.min())], [float(df.lat.max()), float(df.lon.max())]])
    gj = index_geojson(df.sort_values("band"), net)     # reaches with no index first, so they sit underneath
    fields = ["river", "reach_id", "index", "band", "latest", "range", "good_levels"]
    aliases = [t(k) for k in ("nv_col_river", "nv_col_reach", "nv_col_index", "nv_col_band", "nv_col_latest",
                              "nv_col_range_popup", "nv_lab_good")]
    folium.GeoJson(gj, name=t("nv_map_layer"),
                   style_function=lambda f: {"color": f["properties"]["_c"], "weight": f["properties"]["_w"],
                                             "opacity": 0.95},
                   marker=folium.CircleMarker(radius=3, fill=True, fill_opacity=0.9, weight=0),
                   highlight_function=lambda f: {"weight": 6, "color": COL["ink"]},
                   tooltip=folium.GeoJsonTooltip(fields=["river", "index"], aliases=aliases[:1] + aliases[2:3]),
                   popup=folium.GeoJsonPopup(fields=fields, aliases=aliases)).add_to(m)
    fg = folium.FeatureGroup(name=t("nv_lab_ports"))
    for p in ports:
        r = df.loc[df.reach_id == p["reach_id"]].iloc[0]
        idx = "—" if r.band < 0 else f"{r['index']:.0f}"
        word = t("nv_col_index")
        folium.CircleMarker([p["lat"], p["lon"]], radius=5, color=COL["bg"], weight=1.5, fill=True,
                            fill_color=COL["ink"], fill_opacity=1,
                            tooltip=f"{p['name']} ({p['river']}): {word} {idx}",
                            popup=folium.Popup(f"<b>{p['name']}</b> ({p['river']})<br>{word} {idx}<br>"
                                               f"<code>congo.reach(\"{p['reach_id']}\")</code>", max_width=300)).add_to(fg)
    fg.add_to(m)
    sw = "".join(f'<div style="white-space:nowrap"><span style="display:inline-block;width:22px;height:5px;'
                 f'border-radius:3px;background:{c};margin:0 6px 2px 0;vertical-align:middle"></span>{t(k)}</div>'
                 for _, k, c in reversed(BANDS))
    sw += (f'<div style="white-space:nowrap"><span style="display:inline-block;width:22px;height:3px;border-radius:2px;'
           f'background:{NO_INDEX_C};margin:0 6px 2px 0;vertical-align:middle"></span>{t("nv_no_index")}</div>')
    m.get_root().html.add_child(folium.Element(
        f'<div style="position:absolute;z-index:9999;bottom:18px;left:12px;max-width:300px;background:#fcfcfbee;'
        f'padding:8px 10px;border-radius:8px;font:12px system-ui,sans-serif;color:#2e3a46">'
        f'<div style="margin-bottom:4px">{t("nv_map_legend", date=day)}</div>{sw}</div>'))
    folium.LayerControl().add_to(m)
    return m
