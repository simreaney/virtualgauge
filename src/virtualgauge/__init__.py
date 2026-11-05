"""virtualgauge — virtual river gauges from satellite altimetry, in a few lines.

virtualgauge — des stations hydrométriques virtuelles par altimétrie satellitaire, en quelques lignes.

    import virtualgauge as vg
    congo = vg.build_station("congo_kinshasa")
    congo.levels()
    congo.rating(exclude_months=[3, 4, 5, 6])
    congo.discharge()
"""
import pandas as pd

from . import settings, store
from .explore import explore, explore_locations, explore_map
from .i18n import get_language, set_language, t
from .local_files import load_gauge, load_grdc_daily
from .locations import compare_stations, congo_map, reaches_near, world_map
from .results import Result
from .settings import configure
from .sites import PRESETS, Params, Site, sites
from .station import Station, build_station, flood_catch
from .style import use_style

__version__ = "0.1.1"

__all__ = ["build_station", "Station", "Site", "Params", "sites", "flood_catch", "compare_stations", "congo_map",
           "world_map", "reaches_near", "explore", "explore_map", "explore_locations", "set_language", "get_language", "configure",
           "status", "credits", "load_gauge", "load_grdc_daily", "use_style", "Result"]


def status():
    """Where each data file would be read from, and when it was downloaded · Provenance des fichiers de données"""
    man = store.manifest().get("files", {})
    rows = []
    for name, info in sorted(man.items()):
        cache = settings.cache_dir() / name
        where = "cache" if cache.exists() and not settings.refresh() else "bundled"
        rows.append(dict(file=name, read_from=where, bundled_date=info.get("downloaded_utc", "")[:10],
                         source=info.get("source", "")[:70]))
    table = pd.DataFrame(rows)
    lines = [("card_data", dict(origin=f"offline={settings.offline()}, refresh={settings.refresh()}, "
                                        f"cache={settings.cache_dir()}"))]
    return Result(("status_head", {}), lines, table=table, table_rows=60)


def credits():
    """Data credits and licences · Crédits et licences des données"""
    return Result(("credits", {}), [])
