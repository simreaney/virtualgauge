"""The package must reproduce the trainer notebook's results exactly · Le package doit reproduire le notebook formateur."""
import os

import numpy as np
import pandas as pd
import pytest

import virtualgauge as vg
from conftest import GOLDEN


def test_congo_levels(congo):
    d = congo.data
    assert len(d.raw) == 6520
    assert (d.points.reason == "kept").sum() == 6225
    assert round(d.slope * 100, 1) == 8.1 and len(d.slopes) == 10
    assert len(d.vs_ice) == 21
    assert len(d.swot_ok) == 62
    observed = d.swot_main[~d.swot_main.reason.str.startswith("0")]
    assert (observed.reason != "kept").sum() == 46
    assert round(d.offset, 2) == -0.11 and len(d.pairs) == 5


def test_congo_rating(congo):
    r_all = congo.rating()
    assert r_all.values["b"] == 1.0 and r_all.values["b_at_bound"]
    assert ("warn_months", {"months": [3, 4, 5, 6]}) in r_all.warnings
    by_month = congo.residuals_by_month().values
    assert by_month["high"] == [3, 4, 5, 6] and by_month["low"] == [8, 9, 10, 11]
    r = congo.rating(exclude_months=[3, 4, 5, 6])
    assert r.values["n"] == 54
    assert abs(r.values["b"] - 2.4205) < 1e-3 and abs(r.values["h0"] - 263.223) < 1e-2
    assert abs(r.values["nse"] - 0.882) < 1e-3
    s = congo.split_test("2025-01-01").values
    assert abs(s["test_nse"] - 0.329) < 1e-3 and abs(s["test_pbias"] + 22.1) < 0.1


def test_rewa(rewa):
    d = rewa.data
    assert (d.points.reason == "kept").sum() == 875
    assert len(d.swot_ok) == 82
    assert (d.swot_main.reason == "4 higher than upstream").sum() == 6
    assert round(d.offset, 2) == 0.07
    r = rewa.rating()                                   # no discharge: explanation, not an error
    assert r.lines[0][0] == "msg_no_reference" and rewa.current_rating is None


def test_flood_catch(congo, rewa):
    tab = (vg.flood_catch(congo, rewa).table * 100).round(0)
    assert list(tab["Congo – Kinshasa: SWOT"]) == [5, 11, 16, 26, 48, 96]
    assert list(tab["Rewa – Fiji: SWOT + ICESat-2"]) == [7, 14, 21, 35, 63, 97]


def test_exports_equal_trainer(congo, rewa, isolated):
    congo.rating(exclude_months=[3, 4, 5, 6])
    f = congo.export().values["csv"]
    pd.testing.assert_frame_equal(pd.read_csv(f), pd.read_csv(os.path.join(GOLDEN, "congo_kinshasa_virtual_gauge.csv")))
    rewa.current_rating = None
    f = rewa.export().values["csv"]
    pd.testing.assert_frame_equal(pd.read_csv(f), pd.read_csv(os.path.join(GOLDEN, "rewa_fiji_virtual_gauge.csv")))


@pytest.mark.parametrize("lang", ["en", "fr", "both"])
def test_every_step_displays(congo, rewa, lang):
    vg.set_language(lang)
    for st in (congo, rewa):
        st.current_rating = None
        for m in ["raw_points", "cleaning", "slope", "icesat_levels", "swot", "agreement", "levels",
                  "reference_discharge", "rating", "residuals_by_month", "split_test", "discharge", "compare_reaches"]:
            html = getattr(st, m)()._repr_html_()
            assert "Traceback" not in html
        assert st._repr_html_()
        assert st.map()._repr_html_()
    assert vg.flood_catch(congo, rewa)._repr_html_()


def test_table_columns_do_not_change_with_language(congo):
    vg.set_language("en")
    a = congo.cleaning().table.columns.tolist()
    vg.set_language("fr")
    assert congo.cleaning().table.columns.tolist() == a


def test_settings_change_results():
    st = vg.build_station("rewa_fiji", slope_correction=False)
    assert st.data.slope == 0.0
    st = vg.build_station("rewa_fiji", neighbour_check=False)
    assert (st.data.swot_main.reason == "4 higher than upstream").sum() == 0
    with pytest.raises(TypeError):
        vg.build_station("rewa_fiji", not_a_setting=1)
