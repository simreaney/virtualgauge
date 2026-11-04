import os

import matplotlib
import pytest

matplotlib.use("Agg")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test: no internet, empty cache and output folders, bilingual messages."""
    import requests
    import virtualgauge as vg
    from virtualgauge import settings, store

    def no_network(*a, **k):
        raise requests.ConnectionError("network blocked in tests")

    monkeypatch.setattr(requests, "get", no_network)
    monkeypatch.setattr(requests, "post", no_network)
    monkeypatch.setattr(settings, "_state", {"cache_dir": str(tmp_path / "cache"), "out_dir": str(tmp_path / "outputs"),
                                             "data_dir": str(tmp_path / "data"), "offline": True, "refresh": False})
    store.ORIGINS.clear()
    vg.set_language("both")
    yield tmp_path


@pytest.fixture(scope="session")
def congo():
    import virtualgauge as vg
    from virtualgauge import settings
    old = dict(settings._state)
    settings._state.update(offline=True, cache_dir="/nonexistent-cache-for-tests")
    st = vg.build_station("congo_kinshasa")
    settings._state.clear(); settings._state.update(old)
    return st


@pytest.fixture(scope="session")
def rewa():
    import virtualgauge as vg
    from virtualgauge import settings
    old = dict(settings._state)
    settings._state.update(offline=True, cache_dir="/nonexistent-cache-for-tests")
    st = vg.build_station("rewa_fiji")
    settings._state.clear(); settings._state.update(old)
    return st


TRAINER = os.path.join(os.path.dirname(__file__), "..", "Virtual_River_Gauges_DRC_Fiji.ipynb")
GOLDEN = os.path.join(os.path.dirname(__file__), "golden")
