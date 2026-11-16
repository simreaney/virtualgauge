"""Draw an area, pick a flood date, map the flood (English only for now) · Dessiner une zone, cartographier la crue.

vg.flood_explorer()                              start from the world
vg.flood_explorer(lat=-4.3, lon=15.4, zoom=10)   start somewhere
vg.flood_explorer("kinshasa_2024")               start from a ready-made example
"""
import pandas as pd

from .i18n import t

TABS = [("Extent", "extent"), ("Water levels", "water_levels"), ("Depth", "depth"), ("Cleaning", "cleaning"),
        ("Ground", "ground"), ("Summary", "summary"), ("Map", "map"), ("Export", "export")]


class _FloodExplorer:
    def __init__(self, example=None, lat=None, lon=None, zoom=None):
        import ipywidgets as W
        from .flood import EXAMPLES, flood_area
        wide = {"description_width": "initial"}
        self.area, self.event, self.busy, self.tab, self.done = None, None, False, None, set()
        self.status = W.HTML("")
        self.area_out = W.Output()
        self.passes_out = W.Output()
        self.header = W.Output()
        default_date = pd.Timestamp.now().normalize() - pd.Timedelta(days=30)
        if example in EXAMPLES:
            default_date = pd.Timestamp(EXAMPLES[example]["flood_date"])
        self.date = W.DatePicker(value=default_date.date(), description="Flood date", style=wide)
        self.days = W.IntSlider(60, min=30, max=365, step=15, description="Search ± days", style=wide,
                                continuous_update=False)
        self.find_btn = W.Button(description="Find SWOT passes", icon="search")
        self.find_btn.on_click(lambda _: self.find())
        self.before = W.Dropdown(options=[], description="Before", style=wide, layout=W.Layout(width="420px"))
        self.after = W.Dropdown(options=[], description="After", style=wide, layout=W.Layout(width="420px"))
        self.go_btn = W.Button(description="Map the flood", button_style="primary", icon="map")
        self.go_btn.on_click(lambda _: self.go())
        self.outs = [W.Output() for _ in TABS]
        self.tabs = W.Tab(children=self.outs)
        for i, (name, _) in enumerate(TABS):
            self.tabs.set_title(i, name)
        self.tabs.observe(lambda ch: self.render(ch["new"]) if ch["new"] is not None else None,
                          names="selected_index")
        self.tabs.layout.display = "none"
        self.map = self._make_map(example, lat, lon, zoom)
        hint = W.HTML("<b>1. Draw your area</b> with the polygon or rectangle tool (top left of the map). "
                      "Keep it under about 50 km × 50 km.")
        step2 = W.HTML("<b>2. When was the flood?</b> SWOT passes are searched around this date (no login).")
        step3 = W.HTML("<b>3. Choose the passes</b> (same track = same viewing geometry), then map the flood. "
                       "Downloading needs a NASA Earthdata login: run <code>vg.earthdata_login()</code> first.")
        parts = [hint] + ([self.map] if self.map is not None else
                          [W.HTML("<i>The map needs ipyleaflet. Use vg.flood_area(polygon=[...]) instead.</i>")])
        parts += [self.area_out, step2, W.HBox([self.date, self.days, self.find_btn]), self.passes_out, step3,
                  self.before, self.after, self.go_btn, self.status, self.header, self.tabs]
        self.ui = W.VBox(parts)
        self.ui.explorer = self
        if example in EXAMPLES:
            ring = [list(p) for p in EXAMPLES[example]["polygon"]]
            self._show_shape({"type": "Polygon", "coordinates": [ring + [ring[0]]]})
            self.set_area(flood_area(example))

    # --- map and drawing
    def _make_map(self, example, lat, lon, zoom):
        try:
            import ipyleaflet as L
        except ImportError:
            return None
        from .explore import _colab_widgets
        from .flood import EXAMPLES
        _colab_widgets()
        center, z = [0, 20], 2
        if example in EXAMPLES:
            xs, ys = zip(*EXAMPLES[example]["polygon"])
            center, z = [sum(ys) / len(ys), sum(xs) / len(xs)], 9
        if lat is not None and lon is not None:
            center, z = [lat, lon], 9
        z = zoom or z
        sat = L.basemap_to_tiles(L.basemaps.Esri.WorldImagery)
        sat.name, sat.base = "Satellite image", True
        osm = L.basemap_to_tiles(L.basemaps.OpenStreetMap.Mapnik)
        osm.name, osm.base, osm.visible = "OpenStreetMap (place names)", True, False
        m = L.Map(center=center, zoom=z, basemap=sat, scroll_wheel_zoom=True)
        m.layout.height = "460px"
        add = m.add if hasattr(m, "add") else m.add_layer
        add(osm)
        add(L.LayersControl(position="topright"))
        style = {"color": "#ffffff", "weight": 2, "fillOpacity": 0.08}
        if hasattr(L, "GeomanDrawControl"):
            dc = L.GeomanDrawControl(polygon={"pathOptions": style}, rectangle={"pathOptions": style},
                                     polyline={}, circlemarker={}, marker={}, circle={})
        else:
            dc = L.DrawControl(polygon={"shapeOptions": style}, rectangle={"shapeOptions": style},
                               polyline={}, circlemarker={}, marker={}, circle={})
        dc.on_draw(self._on_draw)
        add(dc)
        self.draw, self._L, self.shape = dc, L, None
        return m

    def _show_shape(self, geometry):
        if self.map is None:
            return
        L = self._L
        add = self.map.add if hasattr(self.map, "add") else self.map.add_layer
        if self.shape is not None:
            (self.map.remove if hasattr(self.map, "remove") else self.map.remove_layer)(self.shape)
        self.shape = L.GeoJSON(data={"type": "Feature", "geometry": geometry, "properties": {}},
                               style={"color": "#EB6834", "weight": 2, "fillOpacity": 0.05})
        add(self.shape)

    def _on_draw(self, target=None, action=None, geo_json=None, **_):
        from .flood import flood_area
        if action in ("vertexadded",) or geo_json is None:
            return
        feats = geo_json if isinstance(geo_json, list) else [geo_json]
        polys = [f["geometry"] for f in feats if isinstance(f, dict)
                 and (f.get("geometry") or {}).get("type") in ("Polygon", "MultiPolygon")]
        if action in ("remove", "deleted") and not polys:
            self.area = None
            with self.area_out:
                self.area_out.clear_output()
            return
        if polys:
            self.set_area(flood_area(polys[-1]))

    def set_area(self, area):
        """Use this area (what drawing does) · Utiliser cette zone"""
        from IPython.display import display
        self.area, self.event = area, None
        self.before.options, self.after.options = [], []
        self.tabs.layout.display = "none"
        for o in [self.passes_out, self.header] + self.outs:
            o.clear_output()
        with self.area_out:
            self.area_out.clear_output(wait=True)
            display(area)
            if not area.error:
                display(area.code())

    # --- passes
    def find(self):
        from IPython.display import display
        from .flood import choose_pair
        if self.area is None or self.area.error:
            self.status.value = "<i>Draw an area on the map first.</i>"
            return
        if self.busy:
            return
        self.busy = True
        self.status.value = "<i>Searching SWOT passes (NASA CMR, no login)…</i>"
        try:
            d = pd.Timestamp(self.date.value or pd.Timestamp.now().normalize())
            today = pd.Timestamp.now().normalize()
            start = d - pd.Timedelta(days=self.days.value)
            end = min(d + pd.Timedelta(days=self.days.value), today)
            res = self.area.passes(f"{start:%Y-%m-%d}", f"{end:%Y-%m-%d}", flood_date=f"{d:%Y-%m-%d}")
            with self.passes_out:
                self.passes_out.clear_output(wait=True)
                display(res)
            tab = res.values.get("passes")
            if tab is None or tab.empty:
                self.status.value = ""
                return
            opts = [(f"{r.date} {r.time_utc} · pass {r['pass']} · track {r.track} · {r.seen_pct}% seen · "
                     f"{r.mb} MB", r["pass"]) for _, r in tab.iterrows()]
            self.before.options, self.after.options = opts, opts
            b, a = choose_pair(tab, f"{d:%Y-%m-%d}")
            if b is not None:
                self.before.value = b["pass"]
            if a is not None:
                self.after.value = a["pass"]
            self.status.value = ""
        finally:
            self.busy = False

    # --- the flood
    def go(self):
        from IPython.display import display
        from .flood import flood_event
        if self.area is None or self.area.error or not self.before.value or not self.after.value:
            self.status.value = "<i>Draw an area and find the SWOT passes first.</i>"
            return
        if self.busy:
            return
        self.busy = True
        self.status.value = "<i>Downloading and mapping (first time: 1–3 min per pass)…</i>"
        try:
            ev = flood_event(self.area, before=self.before.value, after=self.after.value)
            self.event, self.done = ev, set()
            with self.header:
                self.header.clear_output(wait=True)
                display(ev)
            for o in self.outs:
                o.clear_output()
            self.tabs.layout.display = "none" if ev.error else "flex"
            self.status.value = ""
            if not ev.error:
                self.render(self.tabs.selected_index or 0)
        finally:
            self.busy = False

    def render(self, i):
        from IPython.display import display
        if self.event is None or self.event.error or i in self.done:
            return
        self.done.add(i)
        with self.outs[i]:
            self.outs[i].clear_output(wait=True)
            display(getattr(self.event, TABS[i][1])())


def flood_explorer(example=None, lat=None, lon=None, zoom=None):
    """Draw an area on a map, find the SWOT passes around a flood date, and map the flood · Explorateur de crues.

    example: a ready-made example key to start from (e.g. "kinshasa_2024")"""
    return _FloodExplorer(example, lat, lon, zoom).ui
