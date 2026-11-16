"""Download the data of the ready-made flood examples and copy them into the package.

Usage: python tools/build_flood_examples.py [cache folder]   (default: ./cache_flood_examples)

Needs a free NASA Earthdata login for the SWOT raster files (environment variables EARTHDATA_USERNAME and
EARTHDATA_PASSWORD, or ~/.netrc — e.g. python -c "import earthaccess; earthaccess.login(persist=True)").
The Copernicus DEM and the NASA CMR search need no login. The examples are defined in virtualgauge/flood.py (EXAMPLES).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import virtualgauge as vg                     # noqa: E402
from virtualgauge import download, flood      # noqa: E402
import sync_bundled_data                      # noqa: E402


def main(cache):
    cache = Path(cache).resolve()
    vg.configure(cache_dir=str(cache), offline=False)
    vg.set_language("en")
    download.earthaccess_session()            # fail early, with a clear message, if there is no login
    keep = []
    for key, ex in flood.EXAMPLES.items():
        print(f"== {key}: {ex['name']}")
        area = vg.flood_area(key)
        res = area.passes()
        print(res.table.to_string())
        ev = vg.flood_event(key)
        print(repr(ev))
        if ev.error:
            raise SystemExit(f"{key}: {ev.error}")
        print(ev.summary().table.to_string())
        keep += [f"flood_{key}_search.json", f"flood_{key}_dem.parquet",
                 f"flood_{key}_{ex['before']}.parquet", f"flood_{key}_{ex['after']}.parquet"]
    sync_bundled_data.main([cache], only=set(keep))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "cache_flood_examples")
