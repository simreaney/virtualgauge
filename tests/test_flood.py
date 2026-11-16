"""Flood mapping with SWOT: areas, pass search, cleaning, depth, examples and widgets (offline)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import virtualgauge as vg
from virtualgauge import download, flood, settings, store
from virtualgauge.messages import MESSAGES

GOLDEN = Path(__file__).parent / "golden"
EXAMPLE_PASSES = [f"flood_{k}_{e[s]}.parquet" for k, e in flood.EXAMPLES.items() for s in ("before", "after")]
HAVE_EXAMPLES = all(store.bundled_path(n) for n in EXAMPLE_PASSES)


def _cmr_entries():
    return json.loads((GOLDEN / "cmr_raster_kinshasa_2023-12.json").read_text())["entries"]


# --- areas -------------------------------------------------------------------------------------------------------
def test_every_flood_reason_has_a_message():
    for key in flood.REASONS.values():
        assert key in MESSAGES


def test_area_from_list_bbox_geojson_and_file(tmp_path):
    pts = [(15.30, -4.30), (15.40, -4.30), (15.40, -4.20), (15.30, -4.20)]
    a1 = vg.flood_area(polygon=pts)
    a2 = vg.flood_area(bbox=(15.30, -4.30, 15.40, -4.20))
    gj = {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [pts + [pts[0]]]}}
    a3 = vg.flood_area(gj)
    f = tmp_path / "area.geojson"
    f.write_text(json.dumps({"type": "FeatureCollection", "features": [gj]}))
    a4 = vg.flood_area(str(f))
    for a in (a1, a2, a3, a4):
        assert not a.error
        assert 120 < a.area_km2 < 125                     # 0.1° × 0.1° near the equator ≈ 123 km²
    assert a1.key == a3.key == a4.key                      # same polygon, same saved files
    assert "vg.flood_area(polygon=[(15.3000, -4.3000)" in a1.code().values["code"]


@pytest.mark.parametrize("kw, key", [
    (dict(bbox=(10, -10, 20, 0)), "fl_err_too_big"),
    (dict(bbox=(15.3, -4.3, 15.301, -4.299)), "fl_err_too_small"),
    (dict(polygon=[(15.3, -4.3), (15.4, -4.3)]), "fl_err_bad_polygon"),
    (dict(bbox=(10, 78, 11, 79)), "fl_err_latitude"),
    ({}, "fl_err_no_area"),
])
def test_bad_areas_explain_instead_of_failing(kw, key):
    a = vg.flood_area(**kw)
    assert a.error and a.error[0] == key
    assert "Flood area" in a._repr_html_()
    ev = vg.flood_event(a, before="2024-01-01", after="2024-02-01")
    assert ev.error and "Flood" in ev._repr_html_() and "Flood" in ev.depth()._repr_html_()


def test_grid_cells_round_trip():
    g = vg.flood_area("kinshasa_2024").grid
    xx, yy = g.mesh()
    r, c, ok = g.index(xx, yy)
    assert ok.all()
    assert (r == np.arange(g.ny)[:, None]).all() and (c == np.arange(g.nx)[None, :]).all()
    assert g.zone == "33S"


# --- the pass search -----------------------------------------------------------------------------------------------
def test_search_drops_antimeridian_scenes_and_duplicates():
    area = vg.flood_area("kinshasa_2024")
    entries = _cmr_entries()
    assert len(entries) == 4                                # 2 false matches, 1 scene, 1 older duplicate
    scenes = download.raster_scenes(entries, area.polygon)
    assert list(scenes.title.str.slice(0, 41)) == ["SWOT_L2_HR_Raster_100m_UTM33M_N_x_x_x_008"]
    assert scenes.updated.iloc[0] > "2024-01-01"            # the newer copy is kept
    tab = flood.pass_table(scenes, area.grid, area.polygon)
    assert list(tab["pass"]) == ["008_111"] and tab.track.iloc[0] == 111
    assert 40 <= tab.seen_pct.iloc[0] <= 90                 # the 20 km nadir gap is not counted as seen


def test_example_passes_work_offline():
    area = vg.flood_area("kinshasa_2024")
    res = area.passes()
    tab = res.values["passes"]
    assert len(tab) == 19 and set(tab.track) == {111, 570}
    assert {"003_570", "008_570"} <= set(tab["pass"])
    assert tab.groupby("track").seen_pct.nunique().max() == 1   # one footprint per track
    assert "<img" in res._repr_html_()                          # timeline + river level from the bundled reach
    sub, _ = area.pass_table("2023-11-04", "2024-03-03")        # inside the example's period: still offline
    assert sub.date.min() >= "2023-11-04" and sub.date.max() <= "2024-03-03"


def test_offline_search_for_a_new_area_explains():
    res = vg.flood_area(bbox=(22.0, -19.5, 22.2, -19.3)).passes("2025-01-01", "2025-03-01")
    assert "offline" in repr(res)


def test_choose_pair_prefers_the_same_track():
    tab = vg.flood_area("kinshasa_2024").passes().values["passes"]
    b, a = flood.choose_pair(tab, "2024-01-03")
    assert a["pass"] == "008_570" and b["pass"] == "006_570"   # not 008_111, which is on the other track
    assert flood._choose(tab, "2023-09-21", "before")["pass"] == "003_570"
    assert flood._choose(tab, "003_570", "before")["pass"] == "003_570"


# --- reading a SWOT raster file -------------------------------------------------------------------------------------
def _fake_raster(path, crs, x, y, wse, water_frac):
    """A small file shaped like a SWOT L2_HR_Raster granule (only the variables the package reads)."""
    xr = pytest.importorskip("xarray")
    pytest.importorskip("h5netcdf")
    shape = (len(y), len(x))
    ct = np.broadcast_to((x - x.mean())[None, :], shape).astype("float32")      # ground track down the middle
    data = {"wse": wse, "water_frac": water_frac, "wse_qual": np.zeros(shape), "wse_uncert": np.full(shape, 0.1),
            "dark_frac": np.zeros(shape), "layover_impact": np.zeros(shape), "ice_clim_flag": np.zeros(shape),
            "ice_dyn_flag": np.zeros(shape), "cross_track": ct}
    ds = xr.Dataset({k: (("y", "x"), np.asarray(v, "float32")) for k, v in data.items()}, coords={"x": x, "y": y})
    ds["crs"] = xr.DataArray(0, attrs={"crs_wkt": crs.to_wkt()})
    ds.to_netcdf(path, engine="h5netcdf")


def test_clip_scene_same_zone_is_exact(tmp_path):
    area = vg.flood_area(bbox=(15.30, -4.30, 15.40, -4.20))
    g = area.grid
    xc, yc = g.centres()
    x = np.arange(xc[0] - 70000, xc[-1] + 70000, 100.0)      # a scene larger than the area, same 100 m grid
    y = np.arange(yc[0] + 5000, yc[-1] - 5000, -100.0)
    xx, yy = np.meshgrid(x, y)
    wse = (xx / 1e4 + yy / 1e5).astype("float32")           # a value we can predict from x, y
    f = tmp_path / "scene.nc"
    _fake_raster(f, g.crs, x, y, wse, np.ones_like(wse))
    foot = area.polygon.buffer(1.0).wkt
    d = flood.clip_scene(f, g, foot)
    got = g.to_grid(d, "wse")
    gx, gy = g.mesh()
    want = gx / 1e4 + gy / 1e5
    ok = np.isfinite(got)
    assert ok.mean() > 0.99
    assert np.allclose(got[ok], want[ok], atol=1e-3)


def test_clip_scene_other_zone_lands_on_the_nearest_cell(tmp_path):
    from pyproj import CRS, Transformer
    area = vg.flood_area(bbox=(17.85, -4.30, 17.95, -4.20))   # near the edge of UTM zone 33 (12–18° E)
    g = area.grid
    other = CRS.from_epsg(32734)                             # the scene is in zone 34S
    tr = Transformer.from_crs(g.crs, other, always_xy=True)
    xs, ys = tr.transform(*g.mesh())
    x = np.arange(np.floor(xs.min() / 100) * 100 - 2000, xs.max() + 2000, 100.0)
    y = np.arange(np.ceil(ys.max() / 100) * 100 + 2000, ys.min() - 2000, -100.0)
    xx, yy = np.meshgrid(x, y)
    f = tmp_path / "scene34.nc"
    _fake_raster(f, other, x, y, np.full(xx.shape, 300.0), np.ones(xx.shape))
    d = flood.clip_scene(f, g, area.polygon.buffer(1.0).wkt)
    got = g.to_grid(d, "wse")
    assert np.isfinite(got[g.inside]).mean() > 0.99 and np.nanmax(np.abs(got - 300)) < 1e-4


def test_merge_scenes_keeps_cells_with_a_level():
    a = pd.DataFrame({"r": [0, 0], "c": [0, 1], "wse": [np.nan, 2.0]})
    b = pd.DataFrame({"r": [0], "c": [0], "wse": [5.0]})
    m = flood.merge_scenes([a, b])
    assert list(m.wse) == [5.0, 2.0]


# --- the analysis -------------------------------------------------------------------------------------------------
def _synthetic(level_before=1.0, level_after=3.0, gap=False, outliers=0):
    """A sloping valley: ground = x/1000 m. Water up to level_before, then up to level_after."""
    area = vg.flood_area(bbox=(15.30, -4.30, 15.36, -4.24))
    g = area.grid
    gx, _ = g.mesh()
    dem = ((gx - g.x0) / 1000).astype("float32")             # 0 m at the west edge, ~6.7 m at the east edge
    rng = np.random.default_rng(0)

    def one(level, label, date):
        seen = np.ones(dem.shape, bool)
        if gap:
            seen[:, : g.nx // 4] = False
        water = seen & (dem < level)
        wse = np.where(water, level + rng.normal(0, 0.02, dem.shape), np.nan)
        if outliers:
            r, c = np.nonzero(water)
            pick = rng.choice(len(r), outliers, replace=False)
            wse[r[pick], c[pick]] += 4.0
        r, c = np.nonzero(seen)
        tab = pd.DataFrame({"r": r, "c": c, "wse": wse[r, c], "wse_qual": 0.0, "wse_uncert": 0.05,
                            "water_frac": np.where(water, 1.0, 0.0)[r, c], "dark_frac": 0.0, "layover": 0.0,
                            "ice": 0.0})
        info = {"pass": label, "date": date, "time_utc": "12:00", "track": 570, "cycle": int(label[:3]),
                "scenes": 1, "seen_pct": 100, "mb": 30}
        return flood.PassGrid(g, tab, info)
    return flood.FloodEvent(area, flood.FloodParams(), one(level_before, "003_570", "2023-09-21"),
                            one(level_after, "008_570", "2024-01-03"), dem)


def test_depth_rise_and_areas_on_a_known_valley():
    ev = _synthetic()
    v = ev.values
    assert abs(v["rise_median_m"] - 2.0) < 0.05
    assert v["flooded_km2"] > 0 and v["receded_km2"] == 0
    inside, k = ev.area.grid.inside, ev.area.grid.cell_km2()
    assert abs(v["water_before_km2"] - (inside & (ev.dem < 1)).sum() * k) < 0.05
    assert abs(v["water_after_km2"] - (inside & (ev.dem < 3)).sum() * k) < 0.05
    a = ev._a()
    fl = a["cls"] == flood.FLOODED
    dem = ev.dem
    expect = 3.0 - dem[fl]
    got = a["depth"][fl]
    ok = np.isfinite(got) & (expect > 0.3)                    # away from the edge, where smoothing mixes cells
    assert np.allclose(got[ok], expect[ok], atol=0.35)
    assert 0.8 < v["depth_median_m"] < 1.2                    # depths spread evenly from 0 to 2 m
    assert v["volume_mm3"] > 0


def test_without_averaging_depth_is_cell_by_cell():
    ev = _synthetic().with_settings(smooth_m=0)
    a = ev._a()
    fl = (a["cls"] == flood.FLOODED) & np.isfinite(a["depth_raw"])
    assert np.allclose(a["depth_raw"][fl], a["wse_after"][fl] - ev.dem[fl], atol=1e-4)


def test_outliers_are_removed_with_a_reason():
    ev = _synthetic(outliers=40)
    tab = ev.cleaning().table
    assert tab.set_index("reason").after.iloc[-1] >= 35       # 'differs from its neighbours'


def test_unseen_cells_are_not_compared():
    v = _synthetic(gap=True).values
    assert 70 < v["seen_both_pct"] < 80


def test_water_below_ground_is_counted_and_set_to_zero():
    ev = _synthetic()
    ev.dem[:, ev.area.grid.nx // 3] += 10                     # a wall of 'trees' across the new flood water
    ev._memo.clear()
    v = ev.values
    assert v["below_ground_pct"] > 0
    assert np.nanmin(ev._a()["depth"]) >= 0
    assert "below the DEM ground" in repr(ev.depth())


def test_every_step_shows_itself():
    ev = _synthetic()
    for step in ["extent", "cleaning", "water_levels", "ground", "depth", "summary"]:
        r = getattr(ev, step)()
        html = r._repr_html_()
        assert "⚠️" not in html or step == "depth", step
        if step != "summary":
            assert "<img" in html, step
    assert "Before: 2023-09-21" in repr(ev)
    assert ev.map().__class__.__name__ == "Map"


def test_export_writes_summary_area_and_maps(isolated):
    files = _synthetic().export().values["files"]
    names = sorted(Path(f).name for f in files)
    assert names[0].endswith("_area.geojson") and any(n.endswith("_summary.csv") for n in names)
    assert any(n.endswith(("_maps.tif", "_cells.csv")) for n in names)
    assert all(Path(f).parent == settings.out_dir() for f in files)


# --- ready-made examples and logins --------------------------------------------------------------------------------
def test_examples_offline():
    for key in flood.EXAMPLES:
        ev = vg.flood_event(key)
        if HAVE_EXAMPLES:
            v = ev.values
            assert not ev.error
            assert v["flooded_km2"] > 0 and 0 < v["depth_median_m"] < 10 and 0 < v["seen_both_pct"] <= 100
            for step in ["extent", "cleaning", "water_levels", "ground", "depth", "summary"]:
                assert getattr(ev, step)()._repr_html_()
        else:                                                 # pass files not built yet: an explanation, no error
            assert ev.error[0] == "fl_err_example_missing"
            assert "build_flood_examples" in repr(ev)


def test_download_without_login_explains(monkeypatch):
    settings.configure(offline=False)
    entries = _cmr_entries()
    area = vg.flood_area("kinshasa_2024")
    custom = vg.flood_area(polygon=list(area.polygon.exterior.coords)[:-1])

    def search(name, polygon, start, end, refresh=None):
        return download.raster_scenes(entries, polygon)

    def no_login(*a, **k):
        raise download.NeedLogin("no login")
    monkeypatch.setattr(download, "swot_raster_search", search)
    monkeypatch.setattr(download, "earthaccess_session", no_login)
    ev = vg.flood_event(custom, before="2023-12-01", after="2023-12-18")   # only one pass exists: nothing before
    assert ev.error[0] == "fl_err_no_pass"
    assert "Flood" in ev.extent()._repr_html_()


def test_login_needed_card(monkeypatch):
    settings.configure(offline=False)
    entries = _cmr_entries()
    two = [dict(e) for e in entries if "UTM33M" in e["title"]][:1]
    later = dict(two[0], title=two[0]["title"].replace("_008_111_", "_009_111_").replace("20231218", "20240108"),
                 time_start="2024-01-08T02:18:00.000Z")
    monkeypatch.setattr(download, "swot_raster_search",
                        lambda name, polygon, start, end, refresh=None: download.raster_scenes(two + [later], polygon))
    monkeypatch.setattr(download, "earthaccess_session",
                        lambda *a, **k: (_ for _ in ()).throw(download.NeedLogin("no login")))
    area = vg.flood_area(bbox=(15.30, -4.30, 15.40, -4.20))
    assert vg.flood_event(area, before="008_111", after="009_111").error[0] == "fl_err_pass_unknown"
    area.passes("2023-12-01", "2024-01-31")                  # the search that makes pass labels known
    ev = vg.flood_event(area, before="008_111", after="009_111")
    assert ev.error[0] == "fl_err_login"
    assert "vg.earthdata_login()" in repr(ev)


def test_explorer_builds_and_searches_the_example_offline():
    pytest.importorskip("ipywidgets")
    ui = vg.flood_explorer("kinshasa_2024")
    ex = ui.explorer
    assert ex.area is not None and ex.area.key == "kinshasa_2024"
    ex.find()
    assert ex.after.value == "008_570" and ex.before.value == "006_570"
    ex.go()
    assert ex.event is not None
    assert ex.event.error[0] == "fl_err_offline_pass"        # 006_570 is not one of the example's own passes


def test_bad_date_explains():
    ev = vg.flood_event(vg.flood_area(bbox=(15.30, -4.30, 15.40, -4.20)), before="last week", after="2024-01-08")
    assert ev.error[0] == "fl_err_need_dates"
