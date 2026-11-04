"""Sites (virtual stations) and processing settings · Sites (stations virtuelles) et réglages de traitement."""
import json
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

import numpy as np

from . import settings, store


@dataclass
class Site:
    """Everything needed to build one virtual station · Tout ce qu'il faut pour une station virtuelle.

    key            short name without spaces, used for file names · nom court sans espaces
    name           full name (may be bilingual) · nom complet
    lat, lon       approximate position · position approximative
    swot_reach     SWOT/SWORD v17b reach ID (11 digits) · identifiant du tronçon (11 chiffres)
    swot_up/down   neighbouring reaches, for the "water flows downhill" check · tronçons voisins
    mask_width_m   typical water width (m) · largeur typique du plan d'eau (m)
    mask_frac      share of the width used on each side of the centre-line · part de la largeur
    h_range        possible water levels (m, EGM2008) · niveaux possibles
    published_mean_m3s, published_mean_at
                   long-term mean flow measured nearby, used to warn when the model is far from it ·
                   débit moyen mesuré à proximité, pour avertir quand le modèle s'en écarte
    """
    key: str
    name: str
    lat: float
    lon: float
    swot_reach: str
    swot_up: str = None
    swot_down: str = None
    mask_width_m: float = 300.0
    mask_frac: float = 0.45
    h_range: tuple = (-100.0, 9000.0)
    slope_correction: bool = True
    geoglows_id: int = None
    short: str = ""
    t0: str = "2018-10-14"
    dahiti_ids: list = field(default_factory=list)
    compare: dict = field(default_factory=dict)          # label -> reach ID, for compare_reaches()
    recommended_exclude_months: list = field(default_factory=list)
    river: str = ""
    region: str = ""                                     # congo, botswana, fiji or world (for maps and lists)
    published_mean_m3s: list = None                      # [low, high] long-term mean measured nearby (m³/s)
    published_mean_at: str = ""                          # where it was measured (a place name)

    def __post_init__(self):
        self.short = self.short or self.name.split(" · ")[0]
        self.h_range = tuple(self.h_range)
        self.swot_reach = str(self.swot_reach)

    @property
    def gauge_file(self) -> Path:
        return settings.data_dir() / f"gauge_{self.key}.csv"

    @classmethod
    def from_reach(cls, reach_id, **overrides):
        """Build a site from a SWOT reach ID alone (uses Hydrocron) · Créer un site à partir d'un identifiant SWOT.

        Width, neighbours and possible levels are read from SWOT; the result can be changed with keyword arguments.
        """
        from .download import reach_info
        reach_id = str(reach_id).strip()
        info = reach_info(reach_id)
        if info is None or info.empty:
            raise ValueError(f"No SWOT data for reach {reach_id} · Pas de données SWOT pour le tronçon {reach_id}")
        valid = info[(info.time_str != "no_data") & (info.wse > -1e10)]
        width = float(valid.width[valid.width > 0].median()) if len(valid) else float(info.p_width.iloc[0])
        width = width if np.isfinite(width) and width > 0 else float(info.p_width.iloc[0])
        lo, hi = (np.percentile(valid.wse, [1, 99]) if len(valid) >= 5 else (-100, 9000))

        def first_id(s):
            ids = [x.strip() for x in str(s).split(",") if x.strip() not in ("", "no_data", "nan")]
            return ids[0] if ids else None
        river = str(info.river_name.iloc[0]) if "river_name" in info else ""
        kw = dict(key=f"reach_{reach_id}", name=f"{river} — reach {reach_id}", short=f"{river} {reach_id}",
                  lat=float(info.p_lat.iloc[0]), lon=float(info.p_lon.iloc[0]), swot_reach=reach_id,
                  swot_up=first_id(info.rch_id_up.iloc[0]), swot_down=first_id(info.rch_id_dn.iloc[0]),
                  mask_width_m=round(width), mask_frac=0.45 if width >= 300 else 0.6,
                  h_range=(float(np.floor(lo - 10)), float(np.ceil(hi + 10))), river=river)
        kw.update(overrides)
        return cls(**kw)


@dataclass
class Params:
    """Processing settings (same defaults as the trainer notebook) · Réglages (mêmes valeurs que le notebook formateur)"""
    max_cloud: int = 2            # ICESat-2: keep cloud flag 0–2 · garder l'indicateur de nuages 0–2
    k_mad: float = 3.0            # ICESat-2: outlier factor · facteur des valeurs aberrantes
    min_spread: float = 0.15      # ICESat-2: smallest spread used by the outlier test (m)
    min_points_slope: int = 20
    min_span_km: float = 2.0
    min_points_pass: int = 5
    u_floor: float = 0.10
    max_reach_q: int = 1          # SWOT: keep reach_q 0–1 · garder reach_q 0–1
    max_xovr_q: int = 1
    neighbour_check: bool = True  # SWOT: water flows downhill check · contrôle amont/aval
    tol_m: float = 0.3
    max_days: int = 3
    n_boot: int = 500
    seed: int = 1


SITE_FIELDS = {f.name for f in fields(Site)}
PARAM_FIELDS = {f.name for f in fields(Params)}

PRESETS = {
    "congo_kinshasa": Site(
        key="congo_kinshasa",
        name="Congo River at Kinshasa–Brazzaville (DR Congo) · Fleuve Congo à Kinshasa–Brazzaville (RD Congo)",
        short="Congo – Kinshasa", river="Congo", lat=-4.270, lon=15.336,
        swot_reach="13217000081", swot_up="13217000101", swot_down="13217000071",
        mask_width_m=3600, mask_frac=0.45, h_range=(260, 280), slope_correction=True,
        geoglows_id=130798640, dahiti_ids=[12153, 13227],
        compare={"Downstream · Aval (071)": "13217000071", "Kinshasa (081)": "13217000081",
                 "Pool Malebo (101)": "13217000101"},
        recommended_exclude_months=[3, 4, 5, 6], region="congo"),
    "rewa_fiji": Site(
        key="rewa_fiji",
        name="Rewa River, Viti Levu (Fiji) · Rivière Rewa, Viti Levu (Fidji)",
        short="Rewa – Fiji", river="Rewa", lat=-17.961, lon=178.435,
        swot_reach="55200000051", swot_up="55200000061", swot_down="55200000041",
        mask_width_m=150, mask_frac=0.6, h_range=(-3, 20), slope_correction=True, geoglows_id=None,
        compare={"Nausori (tidal · marée)": "55200000031", "Main · Principal (051)": "55200000051",
                 "Upstream · Amont (061)": "55200000061"}, region="fiji"),
}


def _load_curated():
    """Example sites shipped with the package (Congo, Botswana, world) · Sites d'exemple fournis avec le package"""
    p = store.bundle_dir() / "locations" / "sites.json"
    if p.exists():
        for d in json.loads(p.read_text()):
            PRESETS.setdefault(d["key"], Site(**d))


_load_curated()


def sites(region=None):
    """Table of ready-made sites, optionally for one region · Tableau des sites prêts, éventuellement d'une région

    region: "congo", "botswana", "fiji" or "world" (None = all · tous)"""
    import pandas as pd
    return pd.DataFrame([dict(key=s.key, name=s.short, region=s.region, river=s.river, lat=s.lat, lon=s.lon,
                              swot_reach=s.swot_reach, discharge_model=bool(s.geoglows_id))
                         for s in PRESETS.values() if region in (None, s.region)]).set_index("key")


def preset_for_reach(reach_id):
    """The ready-made station on this SWOT reach, if there is one · La station prête sur ce tronçon, s'il y en a une"""
    rid = str(reach_id).strip()
    return next((s for s in PRESETS.values() if s.swot_reach == rid), None)


def resolve(site, **kw):
    """Turn a key, a reach ID or a Site into a Site plus Params · Transformer une clé, un identifiant ou un Site"""
    unknown = set(kw) - SITE_FIELDS - PARAM_FIELDS
    if unknown:
        raise TypeError(f"Unknown setting(s) · Réglage(s) inconnu(s) : {sorted(unknown)}")
    site_kw = {k: v for k, v in kw.items() if k in SITE_FIELDS}
    param_kw = {k: v for k, v in kw.items() if k in PARAM_FIELDS}
    if isinstance(site, Site):
        s = site
    elif str(site) in PRESETS:
        s = PRESETS[str(site)]
    elif str(site).strip().isdigit() and len(str(site).strip()) == 11:
        s = preset_for_reach(site) or Site.from_reach(str(site).strip())   # a ready-made station's reach → its settings
    else:
        raise ValueError(f"Unknown site · Site inconnu : {site!r}. Known · Connus : {sorted(PRESETS)}")
    if site_kw:
        s = replace(s, **site_kw)
    return s, Params(**param_kw)
