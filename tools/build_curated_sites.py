"""Choose and download the ready-made example stations shipped with the package (run once, needs internet).

For each target town: take the nearby SWOT reaches on the main river, count their good SWOT levels (Hydrocron),
make a Site from the best one, find the GEOGloWS main-stem river (largest upstream area), download everything, and
keep the site if it has enough data. Sites are merged into src/virtualgauge/data/locations/sites.json, and only the
files of the kept sites are copied into the package (with tools/sync_bundled_data.py).

Usage: python tools/build_curated_sites.py <build cache folder> <group or station key> [...]
groups: congo, botswana, world
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import virtualgauge as vg
from virtualgauge import download
from virtualgauge.locations import _km, _near, reach_index, region_reaches

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_location_data import good_obs          # noqa: E402
import sync_bundled_data                          # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "src" / "virtualgauge" / "data" / "locations" / "sites.json"
ESRI = "https://livefeeds3.arcgis.com/arcgis/rest/services/GEOGLOWS/GlobalWaterModel_Medium/MapServer/0/query"


def T(key, short, river, lat, lon, en, fr, **kw):
    return dict(key=key, short=short, river=river, lat=lat, lon=lon, name=f"{en} · {fr}", **kw)


GROUPS = {
    "congo": [
        T("congo_kisangani", "Congo – Kisangani", "Congo", 0.50, 25.15,
          "Congo River near Kisangani (DR Congo)", "Fleuve Congo près de Kisangani (RD Congo)"),
        T("congo_mbandaka", "Congo – Mbandaka", "Congo", 0.05, 18.25,
          "Congo River near Mbandaka (DR Congo)", "Fleuve Congo près de Mbandaka (RD Congo)"),
        T("ubangi_bangui", "Ubangi – Bangui", "Ubangi", 4.36, 18.58,
          "Ubangi River at Bangui (CAR / DR Congo)", "Rivière Oubangui à Bangui (RCA / RD Congo)"),
        T("kasai_kwamouth", "Kasai – Kwamouth", "Kasai", -3.15, 16.40,
          "Kasai River near Kwamouth (DR Congo)", "Rivière Kasaï près de Kwamouth (RD Congo)"),
        T("lualaba_kindu", "Lualaba – Kindu", "Lualaba", -2.95, 25.92,
          "Lualaba (upper Congo) at Kindu (DR Congo)", "Lualaba (haut Congo) à Kindu (RD Congo)"),
        T("sangha_ouesso", "Sangha – Ouesso", "Sangha", 1.62, 16.05,
          "Sangha River near Ouesso (Rep. Congo)", "Rivière Sangha près de Ouesso (Rép. du Congo)"),
    ],
    # Botswana's large rivers are on its borders, except the Okavango, which flows in from Namibia to its delta.
    "botswana": [
        T("okavango_mohembo", "Okavango – Mohembo", "Okavango", -18.27, 21.79,
          "Okavango River at Mohembo (Botswana)", "Rivière Okavango à Mohembo (Botswana)",
          match="okavango", radius_km=15, min_q=50,
          published_mean_m3s=[263, 292], published_mean_at="Mohembo"),    # gauge records 1933– and 1974–1998
        T("okavango_seronga", "Okavango – Seronga", "Okavango", -18.82, 22.42,
          "Okavango Panhandle near Seronga (Botswana)", "Okavango (Panhandle) près de Seronga (Botswana)",
          match="okavango", radius_km=15, geoglows=False),      # water spreads into the swamps: one channel ≠ all the flow
        T("chobe_kasane", "Chobe – Kasane", "Chobe", -17.80, 25.15,
          "Chobe River at Kasane (Botswana / Namibia)", "Rivière Chobe à Kasane (Botswana / Namibie)",
          match="chobe", radius_km=15, geoglows=False),         # the Zambezi is 5 km away: no automatic model
        T("zambezi_kazungula", "Zambezi – Kazungula", "Zambezi", -17.78, 25.27,
          "Zambezi River at Kazungula (Botswana / Zambia)", "Fleuve Zambèze à Kazungula (Botswana / Zambie)",
          reaches=["12279000211", "12279000221"],                # below the Chobe confluence
          swot_up="12291100011",                                 # the Zambezi, not the Chobe (SWORD lists both)
          published_mean_m3s=[1066, 1088], published_mean_at="Victoria Falls"),   # 70 km downstream, 1971–2000
        T("limpopo_pontdrift", "Limpopo – Pont Drift", "Limpopo", -22.22, 29.13,
          "Limpopo River near Pont Drift (Botswana / South Africa)",
          "Fleuve Limpopo près de Pont Drift (Botswana / Afrique du Sud)", match="limpopo", radius_km=25,
          geoglows=False),                                       # often dry: the model has zero flow on 1 day in 4
    ],
    "world": [
        T("niger_niamey", "Niger – Niamey", "Niger", 13.51, 2.11,
          "Niger River near Niamey (Niger)", "Fleuve Niger près de Niamey (Niger)",
          published_mean_m3s=[740, 950], published_mean_at="Niamey"),     # GRDC 1929–1991: 893; NBA 2007/08: 949
        T("senegal_bakel", "Senegal – Bakel", "Senegal", 14.90, -12.46,
          "Senegal River near Bakel (Senegal / Mauritania / Mali)", "Fleuve Sénégal près de Bakel (Sénégal / Mauritanie / Mali)"),
        T("ogooue_lambarene", "Ogooué – Lambaréné", "Ogooué", -0.70, 10.23,
          "Ogooué River at Lambaréné (Gabon)", "Fleuve Ogooué à Lambaréné (Gabon)", match="ogowe"),
        T("nile_malakal", "White Nile – Malakal", "White Nile", 9.53, 31.66,
          "White Nile below Malakal (South Sudan)", "Nil Blanc en aval de Malakal (Soudan du Sud)",
          published_mean_m3s=[880, 1040], published_mean_at="Malakal"),   # the Sudd swamps evaporate about half
        T("amazon_manaus", "Amazon – Manaus", "Amazon", -3.12, -59.88,
          "Amazon River below Manaus, after the Rio Negro joins (Brazil)",
          "Fleuve Amazone en aval de Manaus, après le Rio Negro (Brésil)",
          reaches=["62270000481", "62270000491"]),               # at Óbidos SWOT flags most levels as poor
        T("orinoco_ciudad_bolivar", "Orinoco – Ciudad Bolívar", "Orinoco", 8.14, -63.55,
          "Orinoco River near Ciudad Bolívar (Venezuela)", "Fleuve Orénoque près de Ciudad Bolívar (Venezuela)"),
        T("parana_corrientes", "Paraná – Corrientes", "Paraná", -27.47, -58.85,
          "Paraná River at Corrientes (Argentina)", "Fleuve Paraná à Corrientes (Argentine)"),
        T("mississippi_vicksburg", "Mississippi – Vicksburg", "Mississippi", 32.32, -90.91,
          "Mississippi River near Vicksburg (USA)", "Fleuve Mississippi près de Vicksburg (États-Unis)"),
        T("danube_bezdan", "Danube – Bezdan", "Danube", 45.99, 18.69,              # searched from Mohács (Hungary)
          "Danube near Bezdan (Serbia / Croatia)", "Danube près de Bezdan (Serbie / Croatie)"),
        T("mekong_kratie", "Mekong – Kratie", "Mekong", 12.49, 106.02,
          "Mekong River near Kratie (Cambodia)", "Fleuve Mékong près de Kratie (Cambodge)"),
        T("brahmaputra_bahadurabad", "Brahmaputra – Bahadurabad", "Brahmaputra", 25.18, 89.67,
          "Brahmaputra (Jamuna) near Bahadurabad (Bangladesh)", "Brahmapoutre (Jamuna) près de Bahadurabad (Bangladesh)"),
        # Yangtze near Datong and Amazon at Óbidos were tried: SWOT flags almost all their levels as poor (2026-11-04)
        T("karnali_chisapani", "Karnali – Chisapani", "Karnali", 28.64, 81.29,
          "Karnali River at Chisapani (Nepal)", "Rivière Karnali à Chisapani (Népal)",
          reaches=["45244500251", "45244500261"],              # where it leaves the hills; SWORD calls it Ghaghara
          published_mean_m3s=[1353, 1392], published_mean_at="Chisapani"),   # GRDC 1962–1993: 1353
        # West Java: the Citarum was tried first (2026-11-04) — between its weirs SWOT levels are held flat (0.3 m a
        # year), below Walahar SWOT sees only 4–16 m of water and jumps by metres, below Jatiluhur it scatters ±1 m.
        T("cimanuk_rentang", "Cimanuk – Rentang", "Cimanuk", -6.70, 108.20,
          "Cimanuk River above the Rentang weir (West Java, Indonesia)",
          "Rivière Cimanuk en amont du barrage de Rentang (Java occidental, Indonésie)",
          reaches=["51501500181"],                               # SWORD has no names for West Java rivers
          h_range=(20.0, 28.0),           # SWOT 20.5–26.3 m; ICESat-2 also hits the water below the weir and the banks
          slope_correction=False),        # a weir pool: the one long ICESat-2 pass "slope" is the step at the weir
        T("fly_obo", "Fly – Obo", "Fly", -7.59, 141.32,
          "Fly River near Obo (Papua New Guinea)", "Fleuve Fly près d'Obo (Papouasie-Nouvelle-Guinée)", match="fly"),
    ],
}


def geoglows_main_stem(lat, lon, d=0.08):
    p = dict(geometry=f"{lon - d},{lat - d},{lon + d},{lat + d}", geometryType="esriGeometryEnvelope", inSR=4326,
             spatialRel="esriSpatialRelIntersects", outFields="comid,upstreamarea,streamorder",
             returnGeometry="false", f="json")
    feats = requests.get(ESRI, params=p, timeout=120).json().get("features", [])
    if not feats:
        return None, None
    best = max(feats, key=lambda f: f["attributes"]["upstreamarea"])["attributes"]
    return int(best["comid"]), float(best["upstreamarea"]) / 1e6


def candidates(tg, region):
    """Nearby main-river reaches with their good-SWOT counts, best first."""
    if tg.get("reaches"):
        c = reach_index()
        c = c[c.reach_id.astype(str).isin(tg["reaches"])].copy()
        c["km"] = _km(tg["lat"], tg["lon"], c.lat, c.lon)
    else:
        c = _near(tg["lat"], tg["lon"], tg.get("radius_km", 30))
        c = c[c.type == 1]
        if tg.get("match"):
            c = c[c.river_name.astype(str).str.lower().str.contains(tg["match"])]
        c = c[c.facc_km2 >= 0.5 * c.facc_km2.max()]                       # main stem, not side channels
        c = c.sort_values("width_m", ascending=False).head(6).copy()
    known = region_reaches(region) if region in ("congo", "botswana") else None
    if known is not None:
        c["good_obs"] = c.reach_id.map(known.set_index("reach_id").good_obs)
    if "good_obs" not in c or c.good_obs.isna().any():
        counts = {rid: good for rid, _, good in map(good_obs, c.reach_id)}
        c["good_obs"] = c.reach_id.map(counts)
    return c.sort_values(["good_obs", "km"], ascending=[False, True])


def files_of(site):
    names = [f"atl13_{site.key}.parquet", f"swot_reach_{site.swot_reach}_line.geojson",
             f"swot_reach_{site.swot_reach}_info.csv"]
    names += [f"swot_reach_{r}.csv" for r in (site.swot_reach, site.swot_up, site.swot_down) if r]
    if site.geoglows_id:
        names.append(f"geoglows_{site.geoglows_id}.csv")
    return names


def main(cache, groups):
    vg.configure(cache_dir=cache)
    old = json.loads(OUT.read_text()) if OUT.exists() else []
    for d in old:
        d.setdefault("region", "congo")
    by_key = {d["key"]: d for d in old}
    ship = []
    jobs = [(g, tg) for g, tgs in GROUPS.items() for tg in tgs if g in groups or tg["key"] in groups]
    for group, tg in jobs:
        tg = dict(tg)
        opts = {k: tg.pop(k) for k in ["match", "radius_km", "reaches", "geoglows", "min_q"] if k in tg}
        c = candidates({**tg, **opts}, group)
        if c.empty or not (c.good_obs.fillna(0) > 0).any():
            print(tg["key"], "no candidate reach with SWOT levels"); continue
        print(f"{tg['key']}: candidates", c[["reach_id", "width_m", "km", "good_obs"]].to_dict("records"))
        rid = str(int(c.reach_id.iloc[0]))
        site = vg.Site.from_reach(rid, region=group, **{k: v for k, v in tg.items() if k not in ("lat", "lon")})
        gid = None
        if opts.get("geoglows", True):
            gid, area = geoglows_main_stem(site.lat, site.lon)
            if gid:
                q = download.geoglows_daily(gid)
                print(f"  GEOGloWS {gid}: upstream area {area:,.0f} km², mean {q.mean():,.0f} m³/s")
                if area < 20000 or q.mean() < opts.get("min_q", 300):
                    gid = None
                else:   # ship 2015 onwards only (keeps the package small)
                    f = Path(cache) / f"geoglows_{gid}.csv"
                    full = pd.read_csv(f, index_col=0)
                    full[full.index >= "2015-01-01"].to_csv(f)
        site.geoglows_id = gid
        st = vg.build_station(site)
        if st.error:
            print(" ", tg["key"], "ERROR", st.error); continue
        n_ice, n_swot = len(st.data.vs_ice), len(st.data.swot_ok)
        print(f"  → reach {rid} ({c.km.iloc[0]:.1f} km away, {c.width_m.iloc[0]:.0f} m wide, "
              f"{c.good_obs.iloc[0]} good SWOT obs): ICESat-2 {n_ice}, SWOT kept {n_swot}, "
              f"neighbours {site.swot_up}/{site.swot_down}, h_range {site.h_range}, geoglows {gid}", flush=True)
        if n_swot >= 20 and n_ice + n_swot >= 30:
            d = asdict(site)
            d["h_range"] = list(d["h_range"])
            by_key[site.key] = d
            ship += files_of(site)
        else:
            print("  not kept: too few levels")
    order = {g: i for i, g in enumerate(["congo", "botswana", "world"])}
    kept = sorted(by_key.values(), key=lambda d: order.get(d.get("region"), 9))
    OUT.write_text(json.dumps(kept, indent=1, ensure_ascii=False))
    print("sites.json:", len(kept), "sites →", OUT)
    sync_bundled_data.main([cache], only=set(ship))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:] or ["congo"])
