"""Bundle a snapshot of the Congo river survey (every SWOT reach of the basin), so the navigability notebook also
works offline. Needs internet once (about 10 minutes, no login).

Usage: python tools/build_navigability_data.py [cache folder]     (default: ./cache)

Downloads every reach not saved in the last 3 days into <cache>/survey_reaches/, combines them, writes the compact
copy (heights in mm, ~3 MB) and copies it into src/virtualgauge/data/ with its checksum in MANIFEST.json.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import virtualgauge as vg                                   # noqa: E402
from virtualgauge import navigation, store                  # noqa: E402
import sync_bundled_data                                    # noqa: E402


def main(cache="cache", region="congo"):
    vg.configure(cache_dir=cache, offline=False)
    vg.set_language("en")
    survey = vg.river_survey(region)
    print(survey)
    if survey.error:
        raise SystemExit(survey.error)
    levels_name, reaches_name = navigation._names(region)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        navigation.write_compact(survey._raw, tmp / levels_name)
        shutil.copy2(Path(cache) / reaches_name, tmp / reaches_name)
        log = json.loads((Path(cache) / "download_log.json").read_text())
        import pandas as pd
        date = pd.to_datetime(survey._reaches.downloaded_utc).max().strftime("%Y-%m-%dT%H:%M:%S+00:00")
        entry = {"source": log.get(levels_name, {}).get("source", "Hydrocron — SWOT RiverSP reach (Version D)"),
                 "downloaded_utc": date}
        (tmp / "download_log.json").write_text(json.dumps({levels_name: entry, reaches_name: entry}))
        sync_bundled_data.main([tmp], only=[levels_name, reaches_name])
    for n in (levels_name, reaches_name):
        print(n, round((store.bundle_dir() / n).stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main(*sys.argv[1:])
