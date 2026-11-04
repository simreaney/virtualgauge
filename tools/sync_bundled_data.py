"""Copy real downloaded data from a cache folder into the package, with a manifest.

Usage: python tools/sync_bundled_data.py <cache folder> [<cache folder> ...]
(tools/build_curated_sites.py calls main() with `only`, the files of the stations it keeps)
Only open data are copied (SWOT, ICESat-2, GEOGloWS). Never GRDC, DAHITI or agency gauge files.
"""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / "src" / "virtualgauge" / "data"
ALLOWED = [r"^atl13_[\w-]+\.parquet$", r"^swot_reach_\d+(_line\.geojson|_info\.csv)?\.?(csv)?$",
           r"^geoglows_\d+\.csv$", r"^geoglows_lookup_[-\d.]+_[-\d.]+\.json$"]


def allowed(name):
    return any(re.match(p, name) for p in ALLOWED)


def main(caches, only=None):
    DEST.mkdir(parents=True, exist_ok=True)
    man_path = DEST / "MANIFEST.json"
    man = json.loads(man_path.read_text()) if man_path.exists() else {"files": {}}
    for cache in map(Path, caches):
        log = json.loads((cache / "download_log.json").read_text()) if (cache / "download_log.json").exists() else {}
        for f in sorted(cache.iterdir()):
            if not f.is_file() or not allowed(f.name) or (only is not None and f.name not in only):
                continue
            shutil.copy2(f, DEST / f.name)
            man["files"][f.name] = {"sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                                    "bytes": f.stat().st_size,
                                    "source": log.get(f.name, {}).get("source", ""),
                                    "downloaded_utc": log.get(f.name, {}).get("downloaded_utc", "")}
    man_path.write_text(json.dumps(man, indent=1, sort_keys=True))
    total = sum(v["bytes"] for v in man["files"].values())
    print(f"{len(man['files'])} files, {total / 1e6:.1f} MB in {DEST}")


if __name__ == "__main__":
    main(sys.argv[1:])
