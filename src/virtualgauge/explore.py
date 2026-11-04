"""Interactive exploration with widgets · Exploration interactive avec des widgets.

explore()            settings sliders + dashboard for one station
explore_map()        click a dot on a map → that station's graphs, settings and export
explore_locations()  the same without the map (a list and a box for a reach ID)
"""
import math
import sys

import pandas as pd

from .i18n import M, fmt_int, get_language, set_language, t
from .rating import residuals_by_month
from .style import to_png
from . import plots

MAX_POINTS = 3000


def _layout_display(widget, show):
    widget.layout.display = "flex" if show else "none"


class _Dashboard:
    """Settings sliders and the 2×2 dashboard for one station · Curseurs et tableau de bord d'une station."""

    def __init__(self, with_language=True):
        import ipywidgets as W
        wide = {"description_width": "initial"}
        self.lang = W.ToggleButtons(options=[("EN", "en"), ("FR", "fr"), ("EN+FR", "both")], value=get_language(),
                                    description=t("w_language"), style=wide) if with_language else None
        self.cloud = W.IntSlider(2, 0, 5, description=t("w_cloud"), continuous_update=False, style=wide)
        self.kmad = W.FloatSlider(3.0, min=1.5, max=8.0, step=0.5, description=t("w_kmad"), continuous_update=False,
                                  style=wide)
        self.slope = W.Checkbox(True, description=t("w_slope"), style=wide)
        self.reachq = W.IntSlider(1, 0, 3, description=t("w_reachq"), continuous_update=False, style=wide)
        self.tol = W.FloatSlider(0.3, min=0.1, max=3.0, step=0.1, description=t("w_tol"), continuous_update=False,
                                 style=wide)
        self.neigh = W.Checkbox(True, description=t("w_neigh"), style=wide)
        self.months = [W.ToggleButton(value=True, description=str(m), layout=W.Layout(width="44px"))
                       for m in range(1, 13)]
        self.reset = W.Button(description=t("w_reset"))
        self.info = W.HTML()
        self.out = W.Output()
        self.memo, self.site, self.busy = {}, None, False
        for w in [self.cloud, self.kmad, self.slope, self.reachq, self.tol, self.neigh] + self.months:
            w.observe(self.update, names="value")
        if self.lang is not None:
            self.lang.observe(self.update, names="value")
        self.reset.on_click(self._on_reset)
        self.body = W.VBox([W.HBox([W.VBox([self.cloud, self.kmad, self.slope]),
                                    W.VBox([self.reachq, self.tol, self.neigh])]),
                            W.HTML(f"<i>{t('w_months')}</i>"), W.HBox(self.months), self.reset, self.info, self.out])

    def _key(self):
        return (self.site.key, self.cloud.value, self.kmad.value, self.slope.value, self.reachq.value,
                self.neigh.value, self.tol.value)

    def _has_reference(self):
        return bool(self.site.geoglows_id) or self.site.gauge_file.exists()

    def _defaults(self):
        s = self.site
        self.busy = True
        self.slope.value = s.slope_correction
        for i, b in enumerate(self.months):
            b.value = (i + 1) not in (s.recommended_exclude_months or [])
            b.disabled = not self._has_reference()
        self.busy = False

    def set_site(self, site, station=None):
        """Show this site; `station`, if given, is a build with the default settings (saves rebuilding it)."""
        self.site = site
        self._defaults()
        if station is not None and not station.error:
            self.memo.setdefault(self._key(), station)
        self.update()

    def _station(self):
        from .station import build_station
        key = self._key()
        if key not in self.memo:
            self.memo[key] = build_station(self.site, max_cloud=self.cloud.value, k_mad=self.kmad.value,
                                           slope_correction=self.slope.value, max_reach_q=self.reachq.value,
                                           neighbour_check=self.neigh.value, tol_m=self.tol.value)
        return self.memo[key]

    def update(self, *_):
        from IPython.display import Image, clear_output, display
        if self.busy or self.site is None:
            return
        if self.lang is not None:
            set_language(self.lang.value)
        st = self._station()
        cr = None
        with self.out:
            clear_output(wait=True)
            if st.error:
                display(st)
                self.info.value = ""
                return
            excl = [i + 1 for i, b in enumerate(self.months) if not b.value]
            if self._has_reference():
                st.rating(exclude_months=excl, n_boot=200)
                cr = st.current_rating
            fig = plots.fig_dashboard(st, cr["p"] if cr else None,
                                      residuals_by_month(cr["pairs"], cr["p"]) if cr else None,
                                      cr["use"] if cr else None, cr["excluded"] if cr else None,
                                      cr["boot"] if cr else None)
            display(Image(to_png(fig)))
        vs = st.data.vs
        rtxt = f" · b = {cr['p']['b']:.2f} · n = {cr['p']['n']} {t('w_boot_note')}" if cr else ""
        self.info.value = "<b>" + t("w_numbers", n_swot=int((vs.source == "SWOT").sum()),
                                    n_ice=int((vs.source == "ICESat-2").sum()), offset=st.data.offset,
                                    cm=st.data.slope * 100, rating=rtxt) + "</b>"

    def _on_reset(self, _):
        self.busy = True
        self.cloud.value, self.kmad.value, self.reachq.value, self.tol.value, self.neigh.value = 2, 3.0, 1, 0.3, True
        self.busy = False
        self._defaults()
        self.update()


def explore(site="congo_kinshasa"):
    """Change the settings and watch the results update · Modifier les réglages et voir les résultats changer.
    site: a ready-made key, or any 11-digit SWOT reach ID · une clé ou tout identifiant SWOT"""
    import ipywidgets as W
    from .sites import PRESETS
    from .station import build_station

    sites = dict(PRESETS)
    options = [(s.short, k) for k, s in PRESETS.items()]
    first = None
    if str(site) not in PRESETS:
        st0 = build_station(site)
        if st0.error:
            return st0                                      # shows the explanation instead of an error
        first = st0
        sites[st0.site.key] = st0.site
        options.insert(0, (st0.site.short, st0.site.key))
    key0 = first.site.key if first else str(site)
    dash = _Dashboard(with_language=True)
    dd = W.Dropdown(options=options, value=key0, description=t("w_site"), style={"description_width": "initial"})
    dd.observe(lambda ch: dash.set_site(sites[ch.new]), names="value")
    dash.set_site(sites[key0], first)
    return W.VBox([W.HBox([dd, dash.lang]), dash.body])


class _StationPanel:
    """Tabs with every graph of one station, its settings and an export button · Onglets d'une station."""
    TABS = ["levels", "map", "cleaning", "slope", "swot", "agreement", "discharge", "settings"]

    def __init__(self):
        import ipywidgets as W
        self.header = W.Output()
        self.outs = [W.Output() for _ in self.TABS]
        self.tabs = W.Tab(children=self.outs)
        for i, k in enumerate(self.TABS):
            self.tabs.set_title(i, t(f"w_tab_{k}", sep="/"))                  # short enough for the tab
        self.tabs.observe(self._on_tab, names="selected_index")
        self.export_btn = W.Button(description=t("w_export"), icon="download")
        self.export_btn.on_click(self._export)
        self.export_out = W.Output()
        self.body = W.VBox([self.tabs, self.export_btn, self.export_out])
        _layout_display(self.body, False)
        self.ui = W.VBox([self.header, self.body])
        self.st, self.done, self.dash = None, set(), None

    def show(self, st):
        from IPython.display import clear_output, display
        self.st, self.done = st, set()
        with self.header:
            clear_output(wait=True)
            card = st._card()
            card.lines = [ln for ln in card.lines if ln[0] != "card_next"]     # no code hints inside the widget
            display(card)
        for o in self.outs + [self.export_out]:
            o.clear_output()
        _layout_display(self.body, not st.error)
        if not st.error:
            self.render(self.tabs.selected_index or 0)

    def _on_tab(self, change):
        if change["new"] is not None:
            self.render(change["new"])

    def render(self, i):
        """Draw tab i the first time it is opened · Dessiner l'onglet i à sa première ouverture"""
        from IPython.display import clear_output, display
        if self.st is None or self.st.error or i in self.done:
            return
        self.done.add(i)
        key = self.TABS[i]
        with self.outs[i]:
            clear_output(wait=True)
            if key == "settings":
                if self.dash is None:
                    self.dash = _Dashboard(with_language=False)
                display(self.dash.body)
                self.dash.set_site(self.st.site, self.st)
            elif key == "discharge":
                display(self.st.rating())
                if self.st.current_rating:
                    display(self.st.discharge())
            else:
                display(getattr(self.st, key)())

    def _export(self, _):
        from IPython.display import clear_output, display
        if self.st is None or self.st.error:
            return
        with self.export_out:
            clear_output(wait=True)
            display(self.st.export())


def _colab_widgets():
    """Colab shows third-party widgets (the map) only after this call · Colab : activer les widgets externes"""
    if "google.colab" in sys.modules:
        try:
            from google.colab import output
            output.enable_custom_widget_manager()
        except Exception:
            pass


def _view(bounds, width_px=900, height_px=460):
    """Centre and zoom that show the bounds [[south, west], [north, east]] · Centre et zoom"""
    (s, w), (n, e) = bounds
    span_lon, span_lat = max(e - w, 0.01), max(n - s, 0.01)
    z = math.floor(4 * math.log2(min(width_px * 360 / (256 * span_lon), height_px * 360 / (256 * span_lat)))) / 4
    return [(s + n) / 2, (w + e) / 2], min(12.0, max(2.0, z))              # quarter steps fill the frame better


def _region_view(region, lat, lon, radius_km):
    """Reaches to draw, map bounds and colouring for a region · Tronçons, limites et couleurs d'une région"""
    from .locations import REGIONS, _near, reach_index, region_outline, region_reaches
    width_legend = (["< 300 m", "300–1000 m", "1–3 km", "> 3 km"], "map_legend_title_world")
    if lat is not None and lon is not None:
        d = _near(lat, lon, radius_km, 0).sort_values("width_m", ascending=False).head(MAX_POINTS)
        dlat = radius_km / 111.32
        dlon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.1))
        return d, [[lat - dlat, lon - dlon], [lat + dlat, lon + dlon]], "width_m", [300, 1000, 3000, 10000], \
            "osm", width_legend
    region = str(region).strip().lower()
    if region == "world":
        idx = reach_index()
        d = idx[(idx.type == 1) & (idx.width_m >= 2000)].sort_values("width_m", ascending=False).head(MAX_POINTS)
        return d, [[-45.0, -150.0], [65.0, 170.0]], "width_m", [300, 1000, 3000, 10000], "satellite", width_legend
    if region not in REGIONS:
        raise ValueError(t("w_unknown_region", region=region, known=", ".join(list(REGIONS) + ["world"])))
    d = region_reaches(region)
    lats, lons = [float(d.lat.min()), float(d.lat.max())], [float(d.lon.min()), float(d.lon.max())]
    outline = region_outline(region)
    if outline:                                                  # frame the whole country, not only its rivers
        from shapely.geometry import shape
        w, s, e, n = shape(outline["geometry"]).bounds
        lats, lons = [min(lats[0], s), max(lats[1], n)], [min(lons[0], w), max(lons[1], e)]
    bounds = [[lats[0] - 0.3, lons[0] - 0.3], [lats[1] + 0.3, lons[1] + 0.3]]
    labels = ([t("map_not_counted", sep=" / ")] if d.good_obs.isna().any() else [""]) + ["0–9", "10–29", "30–59", "60+"]
    return d, bounds, "good_obs", [10, 30, 60], "satellite", (labels, "map_legend_title_obs")


def _in_bounds(site, bounds, lon0=None):
    (s, w), (n, e) = bounds
    x = site.lon if lon0 is None else lon0 + ((site.lon - lon0 + 180) % 360) - 180
    return s <= site.lat <= n and w <= x <= e


class _MapExplorer:
    def __init__(self, region="congo", lat=None, lon=None, radius_km=150, with_map=True):
        import ipywidgets as W
        from .sites import PRESETS
        wide = {"description_width": "initial"}
        self.busy, self.selected = False, None
        self.panel = _StationPanel()
        self.hover = W.HTML("&nbsp;")
        self.status = W.HTML("")
        view = _region_view(region, lat, lon, radius_km) if with_map else None
        here = [k for k, s in PRESETS.items()
                if view is None or str(region).lower() == "world" and lat is None
                or _in_bounds(s, view[1], lon if lat is not None else None)]
        self.dd = W.Dropdown(options=[("—", "")] + [(PRESETS[k].short, k) for k in (here or PRESETS)], value="",
                             description=t("w_choose"), style=wide)
        self.txt = W.Text(placeholder="13217000081", description=t("w_reach"), style=wide)
        self.btn = W.Button(description=t("w_build"), button_style="primary")
        self.btn.on_click(lambda _: self.select(self.txt.value.strip() or self.dd.value))
        self.dd.observe(lambda ch: self.select(ch["new"]) if ch["new"] else None, names="value")
        self.data = None
        parts = []
        if with_map:
            self.map = self._make_map(view, region, lat, lon)
            if self.map is not None:
                parts += [W.HTML(f"<b>{t('w_map_hint')}</b>"), self.map, W.HTML(self.legend), self.hover]
            else:
                parts += [W.HTML(f"<i>{t('w_no_map')}</i>")]
        else:
            self.map = None
        parts += [W.HBox([self.dd, self.txt, self.btn]), self.status, self.panel.ui]
        self.ui = W.VBox(parts)
        self.ui.explorer = self                              # handle for tests and curious trainers

    # --- the map -----------------------------------------------------------------------------------------
    def _make_map(self, view, region, lat, lon):
        try:
            import ipyleaflet as L
        except ImportError:
            return None
        _colab_widgets()
        from .locations import RAMP, _colour, region_outline
        from .sites import PRESETS
        d, bounds, col, bins, base, legend = view
        basemap = L.basemaps.OpenStreetMap.Mapnik if base == "osm" else L.basemaps.Esri.WorldImagery
        legend = dict(zip(legend[0], RAMP if col == "good_obs" else RAMP[1:])), legend[1]
        self.data = d
        lon0 = lon if (lat is not None and lon is not None) else None
        feats = []
        for r in d.itertuples(index=False):
            x = float(r.lon) if lon0 is None else lon0 + ((float(r.lon) - lon0 + 180) % 360) - 180   # across 180° (Fiji)
            v = getattr(r, col)
            obs = getattr(r, "good_obs", None)
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, float(r.lat)]},
                          "properties": {"reach_id": str(r.reach_id),
                                         "river": r.river_name if isinstance(r.river_name, str) and r.river_name else "—",
                                         "width_m": int(round(float(r.width_m))),
                                         "good_obs": None if obs is None or pd.isna(obs) else int(obs),
                                         "_c": _colour(None if pd.isna(v) else float(v), bins)}})
        center, zoom = _view(bounds)
        m = L.Map(center=center, zoom=zoom, basemap=L.basemap_to_tiles(basemap), scroll_wheel_zoom=True,
                  zoom_snap=0.25, zoom_delta=0.5)
        m.layout.height = "460px"
        add = m.add if hasattr(m, "add") else m.add_layer
        outline = region_outline(str(region).lower()) if lat is None else None
        if outline:                                          # the country border, for orientation
            add(L.GeoJSON(data=outline, name=outline["properties"]["name"],
                          style={"color": "#ffffff", "weight": 1.5, "opacity": 0.8, "fill": False, "dashArray": "4 4"}))
        gj = L.GeoJSON(data={"type": "FeatureCollection", "features": feats}, name=t("map_reaches"),
                       point_style={"radius": 5, "weight": 1, "color": "#ffffff", "opacity": 0.9, "fillOpacity": 0.9},
                       style_callback=lambda f: {"fillColor": f["properties"]["_c"]},
                       hover_style={"weight": 3, "color": "#EB6834"})
        gj.on_click(self._on_click)
        gj.on_hover(self._on_hover)
        add(gj)
        pins = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [
                    s.lon if lon0 is None else lon0 + ((s.lon - lon0 + 180) % 360) - 180, s.lat]},
                 "properties": {"key": k, "short": s.short}} for k, s in PRESETS.items()]
        pin_layer = L.GeoJSON(data={"type": "FeatureCollection", "features": pins}, name=t("map_sites"),
                              point_style={"radius": 9, "weight": 2, "color": "#ffffff", "opacity": 1,
                                           "fillColor": "#EB6834", "fillOpacity": 1},
                              hover_style={"weight": 4})
        pin_layer.on_click(lambda feature=None, **_: feature and self.select(feature["properties"]["key"]))
        pin_layer.on_hover(lambda feature=None, **_: feature and setattr(
            self.hover, "value", t("w_hover_pin", name=feature["properties"]["short"])))
        add(pin_layer)
        self.ring = L.CircleMarker(location=center, radius=11, color="#EB6834", weight=4, fill=False, opacity=0)
        add(self.ring)
        labels, title_key = legend
        dots = " ".join(f'<span style="white-space:nowrap"><span style="display:inline-block;width:11px;height:11px;'
                        f'border-radius:6px;background:{c};margin:0 3px 0 8px;vertical-align:middle"></span>{lab}</span>'
                        for lab, c in labels.items() if lab)
        pin = ('<span style="white-space:nowrap"><span style="display:inline-block;width:13px;height:13px;'
               'border-radius:7px;background:#EB6834;margin:0 3px 0 12px;vertical-align:middle"></span>'
               f'{t("map_sites")}</span>')
        self.legend = f"<small>{t(title_key)}: {dots} {pin}</small>"
        return m

    def _on_hover(self, feature=None, **_):
        if not feature:
            return
        p = feature["properties"]
        obs = M("w_hover_obs", n=p["good_obs"]) if p.get("good_obs") is not None else ""
        self.hover.value = t("w_hover", reach=p["reach_id"], river=p["river"], width=fmt_int(p["width_m"]), obs=obs)

    def _on_click(self, feature=None, **_):
        if feature:
            lon, lat = feature["geometry"]["coordinates"][:2]
            self.select(feature["properties"]["reach_id"], where=(lat, lon))

    # --- building a station ------------------------------------------------------------------------------
    def select(self, target, where=None):
        """Build `target` (a ready-made key or a reach ID) and show its tabs · Construire et afficher"""
        from .sites import PRESETS, preset_for_reach
        from .station import build_station
        target = str(target or "").strip()
        if not target:
            return None
        if self.busy:
            self.status.value = f"<i>{t('w_wait')}</i>"
            return None
        self.busy = True
        try:
            preset = PRESETS.get(target) or preset_for_reach(target)
            if preset is not None:
                target, where = preset.key, (preset.lat, preset.lon)
                msg = t("w_loading", name=preset.short)
            else:
                msg = t("w_loading_online", reach=target)
            if where is not None and self.map is not None:
                self.ring.location, self.ring.opacity = list(where), 1.0
            self.status.value = f"<i>{msg}</i>"
            st = build_station(target)
            self.selected = st
            self.status.value = "" if st.error else f"<b>{t('w_ready', name=st.site.short)}</b>"
            self.panel.show(st)
            return st
        finally:
            self.busy = False


def explore_map(region="congo", lat=None, lon=None, radius_km=150):
    """Click a dot on the map to build that station and see its graphs and settings ·
    Cliquez sur un point de la carte pour construire la station et voir ses graphiques et réglages.

    explore_map()                                    the Congo basin · le bassin du Congo
    explore_map("botswana")                          Botswana and its border rivers · le Botswana et ses fleuves frontaliers
    explore_map("world")                             the world's largest rivers · les plus grands fleuves
    explore_map(lat=-17.96, lon=178.43, radius_km=150)  any region · toute région
    """
    return _MapExplorer(region, lat, lon, radius_km).ui


def explore_locations():
    """Pick a ready-made site or type any SWOT reach ID, then see its graphs · Choisir un site ou un identifiant."""
    return _MapExplorer(with_map=False).ui
