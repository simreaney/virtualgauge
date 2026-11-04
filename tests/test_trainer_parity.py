"""Run the trainer notebook's own functions on the bundled data and compare with the package.

Exécuter les fonctions du notebook formateur sur les données fournies et comparer avec le package.
"""
import ast
import inspect
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest

import virtualgauge as vg
from virtualgauge import store
from conftest import TRAINER

pytestmark = pytest.mark.skipif(not os.path.exists(TRAINER), reason="trainer notebook not present")


def trainer_namespace(cache_dir):
    """Definitions (imports, functions, constants) from the trainer's code cells, nothing else."""
    nb = json.load(open(TRAINER))
    ns = {}
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        tree = ast.parse("".join(cell["source"]))
        for node in tree.body:
            keep = isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)) or (
                isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and (t.id.isupper() or t.id.startswith("_"))
                                                     for t in node.targets))
            if keep:
                try:
                    exec(compile(ast.Module([node], []), "trainer", "exec"), ns)
                except Exception:
                    pass        # constants that depend on earlier results (e.g. SLOPE) are not needed
    ns["CACHE"] = Path(cache_dir)
    ns["LOG"] = Path(cache_dir) / "download_log.json"
    return ns


@pytest.fixture(scope="module")
def trainer(tmp_path_factory):
    cache = tmp_path_factory.mktemp("trainer_cache")
    for f in store.bundle_dir().iterdir():
        if f.is_file():
            shutil.copy(f, cache / f.name)
    return trainer_namespace(cache)


@pytest.mark.parametrize("key", ["congo_kinshasa", "rewa_fiji"])
def test_build_matches_trainer(trainer, key):
    cwd = os.getcwd()
    os.chdir(trainer["CACHE"].parent)
    try:
        old = trainer["build_virtual_station"](key)
    finally:
        os.chdir(cwd)
    new = vg.build_station(key).data
    assert np.isclose(old["slope"], new.slope)
    assert np.isclose(old["offset"], new.offset)
    np.testing.assert_allclose(old["vs"].wse_m.to_numpy(), new.vs.wse_m.to_numpy())
    assert list(old["vs"].source) == list(new.vs.source)
    assert list(old["swot_main"].reason) == list(new.swot_main.reason)
    assert list(old["points"].reason) == list(new.points.reason)


def test_rating_matches_trainer(trainer):
    st = vg.build_station("congo_kinshasa")
    r = st.rating(exclude_months=[3, 4, 5, 6])
    use = st.current_rating["use"]
    old = trainer["fit_rating"](use.wse_m, use.Q_ref)
    for k in ("a", "h0", "b"):
        assert np.isclose(old[k], r.values[k])


def test_default_settings_match_trainer(trainer):
    def defaults(name):
        return {k: v.default for k, v in inspect.signature(trainer[name]).parameters.items()
                if v.default is not inspect.Parameter.empty}
    p = vg.Params()
    d = defaults("prepare_atl13")
    assert (p.max_cloud, p.k_mad, p.min_spread) == (d["max_cloud"], d["k_mad"], d["min_spread"])
    d = defaults("estimate_slope")
    assert (p.min_points_slope, p.min_span_km) == (d["min_points"], d["min_span_km"])
    d = defaults("per_pass_levels")
    assert (p.min_points_pass, p.u_floor) == (d["min_points"], d["u_floor"])
    d = defaults("clean_swot")
    assert (p.max_reach_q, p.max_xovr_q) == (d["max_reach_q"], d["max_xovr_q"])
    assert p.tol_m == defaults("hydraulic_check")["tol_m"]
    assert p.max_days == defaults("intermission_pairs")["max_days"]
    d = defaults("bootstrap_rating")
    assert (p.n_boot, p.seed) == (d["n_boot"], d["seed"])
