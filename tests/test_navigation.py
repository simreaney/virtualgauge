"""River navigability survey: download, cleaning, range, index, network and the bundled Congo survey (offline)."""
import gzip
import io
import json

import numpy as np
import pandas as pd
import pytest
import requests

import virtualgauge as vg
from virtualgauge import navigation as nv, settings, store
from virtualgauge.messages import MESSAGES
from virtualgauge.results import reason_label

# three real Congo reaches in a row (upstream → downstream) and one more, used with synthetic levels
UP, MID, DOWN, OTHER = 13273000021, 13273000011, 13271000091, 13245000311


def _hydrocron_csv(rid, times, wse, up="no_data", dn="no_data", reach_q=None):
    n = len(times)
    d = pd.DataFrame({"reach_id": rid, "time_str": [f"{t:%Y-%m-%dT%H:%M:%SZ}" for t in times], "cycle_id": 1,
                      "pass_id": 236, "wse": wse, "wse_u": 0.1, "width": 1500.0,
                      "reach_q": reach_q if reach_q is not None else [1] * n, "xovr_cal_q": 0, "dark_frac": 0.02,
                      "ice_clim_f": 0, "partial_f": 0, "n_good_nod": 40, "obs_frac_n": 1.0,
                      "p_dist_out": 1_140_000.0, "p_length": 9431.0, "rch_id_up": f"{up}, no_data, no_data, no_data",
                      "rch_id_dn": f"{dn}, no_data, no_data, no_data", "wse_units": "m"})
    return d.to_csv(index=False)


def _seasonal(start="2023-08-01", end="2026-11-10", every=7, base=300.0, amp=2.0, seed=0):
    t = pd.date_range(start, end, freq=f"{every}D")
    rng = np.random.default_rng(seed)
    h = base + amp * np.sin(2 * np.pi * (t.dayofyear / 365.25)) + rng.normal(0, 0.05, len(t))
    return list(t), h


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code, self._payload = status, payload
        self.ok = status == 200
        self.text = json.dumps(payload or {})

    def json(self):
        return self._payload


@pytest.fixture
def fake_hydrocron(monkeypatch):
    """Hydrocron answers for UP, MID, DOWN (seasonal levels), OTHER (no data); a reach not listed fails."""
    t, h = _seasonal()
    h_mid = np.array(h)
    h_mid[40] += 4.0                                   # a spike
    q = [1] * len(t)
    q[60] = 3                                          # a bad quality flag
    answers = {UP: _hydrocron_csv(UP, t, np.array(h) + 1, dn=MID),
               MID: _hydrocron_csv(MID, t, h_mid, up=UP, dn=DOWN, reach_q=q),
               DOWN: _hydrocron_csv(DOWN, t, np.array(h) - 1, up=MID)}
    calls = []

    def get(url, params=None, timeout=None):
        rid = int(params["feature_id"])
        calls.append(rid)
        if rid in answers:
            return FakeResponse(200, {"results": {"csv": answers[rid]}})
        if rid == OTHER:
            return FakeResponse(400, {"error": "not found"})
        return FakeResponse(503)

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(nv.time, "sleep", lambda s: None)
    settings.configure(offline=False)
    return calls


# --- download and combine -----------------------------------------------------------------------------------------
def test_download_combine_and_resume(fake_hydrocron):
    s = vg.river_survey(reach_ids=[UP, MID, DOWN, OTHER], name="test", workers=2)
    assert not s.error and s.origin == "download"
    assert s.counts == {"saved": 0, "ok": 3, "no data": 1, "failed": 0}
    tab = s.table.set_index("reach_id")
    assert tab.loc[OTHER, "status"] == "no data" and tab.loc[OTHER, "why"] == "no SWOT data"
    assert tab.loc[MID, "rch_id_up"] == str(UP) and tab.loc[MID, "rch_id_dn"] == str(DOWN)
    assert tab.loc[MID, "dist_out_km"] == pytest.approx(1140.0)
    # a second call within update_days downloads nothing and reads the saved copy
    n_calls = len(fake_hydrocron)
    again = vg.river_survey(reach_ids=[UP, MID, DOWN, OTHER], name="test")
    assert len(fake_hydrocron) == n_calls and again.origin == "cache"
    assert again.counts["saved"] == 4


def test_failed_reach_is_reported_and_retried(fake_hydrocron):
    bad = 13273000031                                 # a real reach the fake service does not know
    s = vg.river_survey(reach_ids=[UP, MID, bad], name="test")
    assert s.counts["failed"] == 1
    assert s.table.set_index("reach_id").loc[bad, "why"] == "not downloaded"
    assert "could not be downloaded" in repr(s)
    assert fake_hydrocron.count(bad) == 4              # four tries


def test_offline_without_saved_copy_explains():
    s = vg.river_survey(reach_ids=[55200000051], name="test")       # a reach in Fiji: not in the bundled survey
    assert s.error and "offline" in s.error
    assert "Not available" in s.navigability()._repr_html_()


def test_unknown_setting_and_region():
    with pytest.raises(TypeError):
        vg.river_survey("congo", max_level=3)
    assert vg.river_survey("amazonia").error


# --- cleaning, range and index ------------------------------------------------------------------------------------
def _survey(levels_by_reach, as_of="2026-11-16", **settings_):
    rows, reaches = [], []
    for rid, (t, h) in levels_by_reach.items():
        rows.append(pd.DataFrame({"reach_id": rid, "time": t, "cycle_id": 1, "pass_id": 1, "wse": h, "wse_u": 0.1,
                                  "width": 1000.0, "reach_q": 1, "xovr_cal_q": 0, "dark_frac": 0.0, "ice_clim_f": 0,
                                  "partial_f": 0, "n_good_nod": 40, "obs_frac_n": 1.0}))
        reaches.append(dict(reach_id=rid, status="ok", n_passes=len(t), dist_out_km=np.nan, length_km=10.0,
                            rch_id_up="", rch_id_dn="", downloaded_utc=f"{as_of}T12:00:00Z"))
    meta = nv.region_reach_list(reach_ids=list(levels_by_reach))
    return nv.RiverSurvey("test", "test", meta, pd.DataFrame(reaches), nv.compact(pd.concat(rows)),
                          nv.SurveyParams(**settings_), origin="cache")


def test_index_is_position_between_lowest_and_highest():
    t = list(pd.date_range("2024-01-01", "2026-11-10", freq="5D"))
    h = np.r_[np.linspace(100, 104, len(t) // 2), np.linspace(104, 101, len(t) - len(t) // 2)]
    s = _survey({MID: (t, h)})
    row = s.to_dataframe().set_index("reach_id").loc[MID]
    assert row.low_m == pytest.approx(100) and row.high_m == pytest.approx(104)
    assert row["index"] == pytest.approx(25, abs=0.5) and row.band == 1
    assert s.reach(MID).values["index"] == pytest.approx(row["index"])


def test_no_recent_level_and_past_dates():
    t, h = _seasonal(end="2026-09-01")
    s = _survey({MID: (t, h)})
    now = s.to_dataframe().set_index("reach_id").loc[MID]
    assert np.isnan(now["index"]) and now.why == "no recent level"
    past = s.to_dataframe("2025-06-01").set_index("reach_id").loc[MID]
    assert 0 <= past["index"] <= 100 and past.age_days <= 7
    assert s.with_settings(max_age_days=90).to_dataframe().set_index("reach_id").loc[MID, "index"] >= 0


def test_spike_removed_but_real_rise_kept():
    t, h = _seasonal(every=5)
    h = np.array(h)
    h[100] += 3.0                                     # a lone spike in the middle of the record
    h[-4:] += np.array([0.6, 1.2, 1.8, 2.4])          # a real, fast rise at the end of the record
    s = _survey({MID: (t, h)})
    lv = s.levels.set_index("time")
    assert lv.loc[t[100], "reason"] == "6 spike"
    assert (lv.loc[t[-4:], "reason"] == "kept").all()
    assert s.to_dataframe().set_index("reach_id").loc[MID, "now_m"] == pytest.approx(h[-1], abs=1e-3)


def test_noisy_and_short_records_get_no_index():
    t, h = _seasonal(every=3)
    rng = np.random.default_rng(1)
    noisy = np.array(h) + rng.normal(0, 2.0, len(t))
    t_short, h_short = _seasonal(start="2026-03-01")
    t_few, h_few = t[-8:], h[-8:]
    s = _survey({MID: (t, noisy), UP: (t_short, h_short), DOWN: (t_few, h_few)})
    why = s.table.set_index("reach_id").why
    assert why[MID] == "too noisy" and why[UP] == "record too short" and why[DOWN] == "too few good levels"


def test_quality_flags_and_duplicates():
    t, h = _seasonal()
    s = _survey({MID: (t + t[:3], list(h) + list(h[:3]))})
    assert (s.levels.reason == "0 duplicate").sum() == 3
    raw = s._raw.copy()
    raw.loc[20, "reach_q"] = 2
    raw.loc[21, "dark_frac"] = 0.9
    s2 = nv.RiverSurvey("test", "test", s._meta, s._reaches, raw, nv.SurveyParams(max_dark_frac=0.5))
    reasons = s2.levels.reason.iloc[[20, 21]].tolist()
    assert reasons == ["2 reach_q > 1", "4 dark water"]
    for code in ["kept", "0 duplicate", "2 reach_q > 1", "4 dark water", "5 far from other levels", "6 spike"]:
        assert reason_label(code) != code or code == "kept"


def test_every_region_names_reaches_of_its_basin():
    """The ports and the start of the main river of each basin (Congo, Amazon) are SWORD reaches of that basin."""
    idx = vg.locations.reach_index().set_index("reach_id")
    for key, region in nv.REGIONS.items():
        assert f"nv_region_{key}" in MESSAGES and f"nv_main_{key}" in MESSAGES
        for name, _, rid in region["ports"]:
            assert rid // 10**8 == region["basin"] and idx.type[rid] != 6, (key, name)
        assert region["main_start"] // 10**8 == region["basin"]
        assert len({p[0] for p in region["ports"]}) == len(region["ports"])


def test_bands_and_messages():
    assert nv.band_of([0, 19.9, 20, 55, 80, 100, np.nan]).tolist() == [0, 0, 1, 2, 4, 4, -1]
    for _, key, _ in nv.BANDS:
        assert key in MESSAGES
    for why in ["no SWOT data", "not downloaded", "never measured", "too few good levels", "record too short",
                "range too small", "too noisy", "no recent level"]:
        assert "nv_why_" + why.replace(" ", "_") in MESSAGES


# --- network ------------------------------------------------------------------------------------------------------
def test_network_splits_each_link_half_way():
    t, h = _seasonal()
    s = _survey({UP: (t, h), MID: (t, h), DOWN: (t, h)})
    tab = s.table.copy()
    tab.loc[tab.reach_id == MID, ["rch_id_up", "rch_id_dn"]] = [str(UP), str(DOWN)]
    seg, lone = nv.network(tab)
    assert sorted(seg.reach_id.value_counts().to_dict().items()) == sorted({UP: 1, MID: 2, DOWN: 1}.items())
    m = seg[seg.reach_id == MID]
    assert len(lone) == 0
    idx = vg.locations.reach_index().set_index("reach_id")
    mid_xy = (float(idx.lon[MID]), float(idx.lat[MID]))
    assert all(np.isclose(m.x0, mid_xy[0]) | np.isclose(m.x1, mid_xy[0]))


# --- the bundled Congo survey -----------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def congo():
    old = dict(settings._state)
    settings._state.update(offline=True, cache_dir="/nonexistent-cache-for-tests")
    vg.set_language("en")
    s = vg.river_survey("congo")
    settings._state.clear()
    settings._state.update(old)
    return s


def test_bundled_congo_survey(congo):
    assert not congo.error and congo.origin == "bundled"
    assert len(congo.table) == 4444
    df = congo.to_dataframe()
    assert df["index"].notna().sum() > 3000
    assert df["index"].dropna().between(0, 100).all()
    ports = {p["name"] for p in congo._ports()}
    assert {"Kinshasa", "Kisangani", "Mbandaka", "Bangui", "Bumba", "Ilebo"} <= ports


def test_main_stem_reaches_the_sea(congo):
    path = nv.main_stem(congo.table, nv.REGIONS["congo"]["main_start"])
    ids = list(path.reach_id)
    for port in (13279300031, 13273000011, 13217000081):          # Kisangani, Mbandaka, Kinshasa
        assert port in ids
    assert ids.index(13279300031) < ids.index(13273000011) < ids.index(13217000081)
    assert path.dist_out_km.iloc[-1] < 20 and path.dist_out_km.is_monotonic_decreasing


def test_every_step_shows_itself(congo, isolated):
    for r in [congo, congo.coverage(), congo.cleaning(), congo.ranges(), congo.navigability(),
              congo.navigability("2025-08-01"), congo.profile(), congo.reach("13273000011"),
              congo.ports(), congo.history()]:
        html = r._repr_html_()
        assert len(html) > 200 and "Not available" not in html
    assert "not in this survey" in congo.reach("123")._repr_html_()
    m = congo.map()
    assert "Navigability index" in m.get_root().render()
    ex = congo.export()
    gj = json.loads(open(ex.values["geojson"]).read())
    assert len(gj["features"]) > 4000
    csv = pd.read_csv(ex.values["csv"])
    assert len(csv) == 4444 and {"index", "low_m", "high_m", "range_m"} <= set(csv.columns)


def test_own_list_inside_the_congo_works_offline():
    ids = vg.reaches_near(-4.3, 15.3, radius_km=40, n=50).values["reach_ids"]
    s = vg.river_survey(reach_ids=ids, name="Around Kinshasa")
    assert not s.error and s.origin == "bundled" and len(s.table) == len(set(int(r) for r in ids))
    assert "Around Kinshasa" in s.navigability()._repr_html_()


# --- French, and the language of the computer ---------------------------------------------------------------------
@pytest.mark.parametrize("hints, lang", [(["fr-CD"], "fr"), (["fr_FR.UTF-8"], "fr"), (["French_France"], "fr"),
                                         (["en-GB", "fr-FR"], "en"), (["", "C.UTF-8", "fr_BE"], "fr"),
                                         (["POSIX", "C"], "en"), ([], "en")])
def test_language_of_the_computer(monkeypatch, hints, lang):
    from virtualgauge import i18n
    monkeypatch.delenv("VG_LANG", raising=False)
    monkeypatch.setattr(i18n, "_language_hints", lambda: iter(hints))
    assert vg.detect_language() == lang
    vg.set_language("auto")
    assert vg.get_language() == lang
    monkeypatch.setenv("VG_LANG", "fr")
    assert vg.detect_language() == "fr"


def test_dates_and_text_in_each_language():
    from virtualgauge.i18n import Day
    assert Day(pd.Timestamp("2026-11-01")).pair() == ("1 November 2026", "1er novembre 2026")
    assert Day(pd.Timestamp("2025-08-16"), month=True).pair() == ("August 2025", "août 2025")
    assert str(Day(pd.NaT)) == "—"
    vg.set_language("fr")
    assert vg.text("Hello", "Bonjour").data == "Bonjour"
    vg.set_language("both")
    assert vg.text("Hello", "Bonjour").data == "Hello\n\n> Bonjour"


def test_every_navigability_message_is_translated():
    same = [k for k, (en, fr) in MESSAGES.items() if k.startswith("nv_") and en == fr and k != "nv_col_port"]
    assert same == []


def test_survey_in_french(congo):
    vg.set_language("fr")
    card = repr(congo)
    assert "Bassin du Congo" in card and "novembre 2026" in card
    nav = congo.navigability("2025-08-01")._repr_html_()
    assert "Indice de navigabilité" in nav and "1er août 2025" in nav and "classe" in nav
    assert "très mauvaise" in repr(congo.reach("13273000011")) or "mauvaise" in repr(congo.reach("13273000011"))
    assert "Le long du Lualaba et du Congo" in repr(congo.profile())
    assert "port" in congo.ports()._repr_html_() and "rivière" in congo.ports()._repr_html_()
    assert "Fond gris clair" in congo.map().get_root().render()
    for r in [congo.coverage(), congo.cleaning(), congo.ranges(), congo.history()]:
        assert "Not available" not in r._repr_html_() and "Non disponible" not in r._repr_html_()
    vg.set_language("both")
    assert "Navigability index · Indice de navigabilité" in repr(congo.navigability()).splitlines()[0] or \
        " · " in repr(congo.navigability()).splitlines()[0]


# --- GeoPackage ---------------------------------------------------------------------------------------------------
def test_geopackage_opens_styled(congo, isolated):
    import pyogrio
    vg.set_language("en")
    ex = congo.export()
    gpkg = ex.values["gpkg"]
    layers = dict(pyogrio.list_layers(gpkg).tolist())
    assert layers == {"reaches": "MultiLineString", "ports": "Point", "layer_styles": None}
    reaches = pyogrio.read_dataframe(gpkg, layer="reaches")
    assert len(reaches) == 4444 and reaches.geometry.notna().sum() >= 4440
    assert {"reach_id", "river_name", "low_m", "high_m", "range_m", "now_m", "now_date", "index", "band", "band_name",
            "colour"} <= set(reaches.columns)
    assert reaches["index"].dropna().between(0, 100).all() and (reaches.band >= -1).all()
    with_index = reaches[reaches.band >= 0]
    assert (with_index.colour == [nv.BANDS[b][2] for b in with_index.band]).all()
    ports = pyogrio.read_dataframe(gpkg, layer="ports")
    assert {"Kinshasa", "Mbandaka", "Bangui"} <= set(ports.name)
    styles = pyogrio.read_dataframe(gpkg, layer="layer_styles")
    assert set(styles.f_table_name) == {"reaches", "ports"} and styles.useAsDefault.all()
    assert (styles.f_geometry_column == "geom").all() and (styles.f_table_schema == "").all()
    qml = dict(zip(styles.f_table_name, styles.styleQML))
    assert 'type="categorizedSymbol"' in qml["reaches"] and 'attr="band"' in qml["reaches"]
    assert "80–100 very good" in qml["reaches"] and 'labelsEnabled="1"' in qml["ports"]
    assert pyogrio.read_info(gpkg, layer="reaches")["dataset_metadata"]["date"] == ex.values["csv"][-14:-4]
    assert "GeoPackage" in repr(ex) and ex.values["gpkg"].endswith(".gpkg")


def test_geopackage_with_every_level(congo, isolated):
    import pyogrio
    gpkg = congo.export(levels=True).values["gpkg"]
    assert "levels" in dict(pyogrio.list_layers(gpkg).tolist())
    lv = pyogrio.read_dataframe(gpkg, layer="levels", max_features=1000)
    assert {"reach_id", "time", "wse", "reason", "kept"} <= set(lv.columns)


def test_download_geopackage_here_and_on_colab(congo, isolated, monkeypatch):
    import sys
    import types
    monkeypatch.chdir(isolated)                       # outputs/ under the notebook's folder: a download link
    here = congo.download_geopackage()
    assert "already saved here" in repr(here) and '<a href="outputs/navigability_congo_' in here._repr_html_()
    sent = []
    colab = types.ModuleType("google.colab")
    colab.files = types.SimpleNamespace(download=sent.append)
    monkeypatch.setitem(sys.modules, "google", types.ModuleType("google"))
    monkeypatch.setitem(sys.modules, "google.colab", colab)
    on_colab = congo.download_geopackage()
    assert sent and sent[0].endswith(".gpkg") and "Downloads folder" in repr(on_colab)


def test_student_notebook_builds(tmp_path):
    import ast
    import subprocess
    import sys
    from pathlib import Path
    import nbformat
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "nav.ipynb"
    subprocess.run([sys.executable, str(root / "tools" / "build_navigability_notebook.py"), str(out)], check=True,
                   capture_output=True)
    nb = nbformat.read(out, as_version=4)
    texts = [c for c in nb.cells if c.cell_type == "code" and c.source.startswith("#@title\nvg.text(")]
    assert len(texts) > 15
    for c in nb.cells:
        if c.cell_type == "code":
            ast.parse("\n".join(l for l in c.source.splitlines() if not l.lstrip().startswith(("%", "!"))))
    for c in texts:                                    # each text cell: English then French, same headings
        en, fr = ast.literal_eval(c.source.split("vg.text(", 1)[1].rsplit(")", 1)[0])
        assert en.count("#") == fr.count("#") and en.count("\n- ") == fr.count("\n- ")
    assert any("download_geopackage" in c.source for c in nb.cells)
    assert 'vg.set_language(language)' in "\n".join(c.source for c in nb.cells)


def test_result_links_are_escaped():
    from virtualgauge.results import Result
    r = Result(("h_export", {}), [], links=[('<script>alert(1)</script>', 'out/a"b.gpkg', 'a"b.gpkg'),
                                           ("click", "javascript:alert(1)", None), None])
    html = r._repr_html_()
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert 'href="out/a&quot;b.gpkg"' in html and 'download="a&quot;b.gpkg"' in html
    assert "javascript:" not in html


@pytest.mark.parametrize("href, shown", [
    ("outputs/navigability_congo_2026-11-16.gpkg", True), ("outputs/a%20b.gpkg", True), ("/files/a.gpkg", True),
    ("https://example.org/a.gpkg", True), ("http://example.org/a.gpkg", True),
    ("//example.org/a.gpkg", False), ("/\\example.org/a.gpkg", False), ("\\\\example.org/a.gpkg", False),
    ("javascript:alert(1)", False), (" javascript:alert(1)", False), ("java\tscript:alert(1)", False),
    ("JAVASCRIPT:alert(1)", False), ("data:text/html,<b>x</b>", False), ("https:example.org", False),
    ("ftp://example.org/a", False), ("", False)])
def test_result_link_addresses(href, shown):
    from virtualgauge.results import Result
    html = Result(("h_export", {}), [], links=[("file", href, None)])._repr_html_()
    assert ("<a href=" in html) == shown
