"""Interactive maps (folium) · Cartes interactives (folium)."""
import folium
import geopandas as gpd

from .i18n import t
from .style import COL

ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_ATTR = "Esri, Maxar, Earthstar Geographics"


def base_map(lat, lon, zoom=12, satellite_first=True):
    m = folium.Map(location=[lat, lon], zoom_start=zoom, tiles=None)
    layers = [folium.TileLayer(tiles=ESRI, attr=ESRI_ATTR, name=t("map_image")),
              folium.TileLayer("OpenStreetMap", name="OpenStreetMap")]
    for layer in (layers if satellite_first else layers[::-1]):
        layer.add_to(m)
    return m


def site_map(site, geo, points=None, max_points=800):
    """Mask, centre-line and (optionally) ICESat-2 points · Masque, ligne centrale et points ICESat-2"""
    m = base_map(site.lat, site.lon)
    folium.GeoJson(geo["mask_ll"].__geo_interface__, name=t("map_mask"),
                   style_function=lambda f: {"color": "#ffffff", "weight": 1.5, "fillOpacity": 0.05}).add_to(m)
    cl = gpd.GeoSeries([geo["line_utm"]], crs=geo["utm"]).to_crs(4326).iloc[0]
    folium.GeoJson(cl.__geo_interface__, name=t("map_centre"),
                   style_function=lambda f: {"color": COL["SWOT"], "weight": 3}).add_to(m)
    if points is not None and len(points):
        pts = points.to_crs(4326)
        pts = pts.sample(min(max_points, len(pts)), random_state=0)
        fg = folium.FeatureGroup(name="ICESat-2")
        for gx, gy in zip(pts.geometry.x, pts.geometry.y):
            folium.CircleMarker([gy, gx], radius=2, color=COL["ICESat-2"], fill=True, weight=0,
                                fill_opacity=0.9).add_to(fg)
        fg.add_to(m)
    folium.Marker([site.lat, site.lon], tooltip=site.short).add_to(m)
    folium.LayerControl().add_to(m)
    return m
