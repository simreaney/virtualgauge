"""Messages, data lookup, bundle, locations and widgets · Messages, données, cartes et widgets."""
import hashlib
import json
import string
import time
import warnings

import pytest

import virtualgauge as vg
from virtualgauge import download, settings, store
from virtualgauge.messages import MESSAGES


def _fields(s):
    return sorted({f for _, f, _, _ in string.Formatter().parse(s) if f})


def test_messages_complete_and_matching():
    for key, pair in MESSAGES.items():
        assert isinstance(pair, tuple) and len(pair) == 2, key
        assert _fields(pair[0]) == _fields(pair[1]), key


def test_every_reason_has_a_label():
    for code in ["kept", "0 not observed", "0 duplicate", "1 impossible level", "2 not river", "3 cloudy",
                 "4 outlier in pass", "4 higher than upstream", "4 lower than downstream"]:
        assert f"reason_{code}" in MESSAGES


def test_bundle_matches_manifest_and_has_no_restricted_data():
    man = store.manifest()["files"]
    for name, info in man.items():
        p = store.bundle_dir() / name
        assert hashlib.sha256(p.read_bytes()).hexdigest() == info["sha256"], name
    names = [p.name.lower() for p in store.bundle_dir().rglob("*")]
    assert not [n for n in names if n.startswith(("grdc", "gauge", "dahiti"))]


def test_offline_unknown_reach_explains_instead_of_failing():
    st = vg.build_station("12345678901")
    assert st.error
    assert "Not available" in st.levels()._repr_html_()


def test_refresh_falls_back_to_saved_copy():
    settings.configure(offline=False, refresh=True)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        df = download.hydrocron_reach("13217000081")
    assert len(df) == 108
    assert any("saved copy" in str(x.message) for x in w)


def test_user_cache_is_used_first(isolated):
    cache = isolated / "cache"
    cache.mkdir()
    (cache / "swot_reach_13217000081.csv").write_text("reach_id,time_str,wse\n13217000081,no_data,1\n")
    assert len(download.hydrocron_reach("13217000081")) == 1
    assert store.ORIGINS["swot_reach_13217000081.csv"]["origin"] == "cache"


def test_nothing_written_into_the_package(isolated):
    before = {p: p.stat().st_mtime for p in store.bundle_dir().rglob("*") if p.is_file()}
    st = vg.build_station("congo_kinshasa")
    st.rating(exclude_months=[3, 4, 5, 6])
    st.export()
    after = {p: p.stat().st_mtime for p in store.bundle_dir().rglob("*") if p.is_file()}
    assert before == after


def test_reaches_near_and_from_reach():
    near = vg.reaches_near(-4.27, 15.34).values["reach_ids"]
    assert near[0] == "13217000081"
    assert "55200000051" in vg.reaches_near(-17.96, 178.43, radius_km=10).values["reach_ids"]
    s = vg.Site.from_reach("13221000021")          # bundled curated reach (works offline)
    curated = vg.PRESETS["kasai_kwamouth"]
    assert (s.swot_up, s.swot_down, s.h_range) == (curated.swot_up, curated.swot_down, curated.h_range)


def test_curated_sites_build_offline():
    curated = [k for k in vg.PRESETS if k not in ("congo_kinshasa", "rewa_fiji")]
    assert len(curated) >= 5
    for k in curated:
        st = vg.build_station(k)
        assert not st.error, k
        assert len(st.data.vs) >= 10, k


def test_compare_stations_and_maps():
    r = vg.compare_stations(["congo_kisangani", "ubangi_bangui", "congo_kinshasa"])
    assert len(r.lines) == 3 and r._repr_html_()
    for m in [vg.congo_map(), vg.world_map(), vg.world_map(lat=-17.96, lon=178.43, radius_km=150)]:
        assert len(m._repr_html_()) < 3_000_000


def test_widgets_build_and_update_quickly():
    from virtualgauge import plots
    from virtualgauge.rating import residuals_by_month
    ui = vg.explore()
    assert ui is not None and vg.explore_locations() is not None
    t0 = time.time()
    st = vg.build_station("congo_kinshasa", max_cloud=1, k_mad=2.5)
    st.rating(exclude_months=[3, 4, 5, 6], n_boot=200)
    cr = st.current_rating
    plots.fig_dashboard(st, cr["p"], residuals_by_month(cr["pairs"], cr["p"]), cr["use"], cr["excluded"], cr["boot"])
    assert time.time() - t0 < 2.0


def test_explore_map_click_builds_station_and_every_tab():
    vg.set_language("both")
    ex = vg.explore_map().explorer
    assert len(ex.data) == 1355 and ex.map is not None
    gj = [layer for layer in ex.map.layers if type(layer).__name__ == "GeoJSON"][0]
    f = next(ft for ft in gj.data["features"] if ft["properties"]["reach_id"] == "13279300031")
    ex._on_hover(feature=f)
    assert ex.hover.value.count("good SWOT levels") == 1          # nested message translated once
    t0 = time.time()
    ex._on_click(feature=f, event="click")                        # the reach of a ready-made station → its preset
    assert ex.selected.site.key == "congo_kisangani" and not ex.selected.error
    for i in range(len(ex.panel.TABS)):
        ex.panel.render(i)
    ex.panel._export(None)
    assert time.time() - t0 < 15
    st = ex.select("14410300131")                                 # not shipped, offline → explanation, no exception
    assert st.error and ex.panel.body.layout.display == "none"
    fiji = vg.explore_map(lat=-17.96, lon=178.43, radius_km=150).explorer
    assert len(fiji.data) > 10 and fiji.map.zoom >= 7
    assert vg.explore_map("world").explorer.map.zoom == 2


def test_botswana_and_world_examples():
    vg.set_language("both")
    bw = vg.sites(region="botswana")
    assert len(bw) >= 3 and len(vg.sites(region="world")) >= 8
    ex = vg.explore_map("botswana").explorer
    assert len(ex.data) == len(vg.locations.region_reaches("botswana")) and ex.data.good_obs.notna().all()
    assert {k for _, k in ex.dd.options if k} == set(bw.index)          # the list shows this region's stations
    assert any(type(layer).__name__ == "GeoJSON" and layer.name == "Botswana" for layer in ex.map.layers)
    assert "not counted" not in ex.legend                               # every Botswana reach has a count
    world = vg.explore_map("world").explorer
    pins = [layer for layer in world.map.layers if type(layer).__name__ == "GeoJSON" and len(layer.data["features"]) == len(vg.PRESETS)]
    assert pins and len(world.dd.options) == len(vg.PRESETS) + 1
    st = world.select("amazon_manaus" if "amazon_manaus" in vg.PRESETS else vg.sites(region="world").index[0])
    assert not st.error and len(st.data.vs) >= 10
    with pytest.raises(ValueError, match="Unknown region"):
        vg.explore_map("atlantis")


def test_world_map_shows_every_reach_when_zoomed_in():
    ex = vg.explore_map("world").explorer
    assert ex.dynamic and len(ex.data) == 3000 and "widest" in ex.count.value      # far out: the widest rivers only
    ex.map.zoom = 8
    ex._on_bounds({"new": ((-4.6, 15.0), (-4.0, 15.7))})                           # Kinshasa, as a pan/zoom does
    assert "13217000081" in set(ex.data.reach_id.astype(str)) and "All" in ex.count.value
    assert len(ex.gj.data["features"]) == len(ex.data) < 3000
    ex.show_view(((-19.0, 176.0), (-16.0, 182.0)), 8)                              # across the 180° meridian
    assert "55200000051" in set(ex.data.reach_id.astype(str)) and ex.data.x.between(176, 182).all()
    n = len(ex.data)
    ex.show_view(((-18.5, 177.0), (-17.0, 179.0)), 9)                              # inside a complete view: no reload
    assert len(ex.data) == n
    assert not vg.explore_map().explorer.dynamic                                    # the Congo map keeps its table


def test_reach_id_of_ready_made_station_uses_its_settings():
    assert vg.build_station("13217000081").site.key == "congo_kinshasa"
    assert vg.explore("13279300031") is not None
