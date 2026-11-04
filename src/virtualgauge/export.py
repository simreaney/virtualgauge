"""Write the virtual-gauge record (trainer Step 8) · Écrire l'enregistrement de la station virtuelle."""
import json
from datetime import datetime, timezone

from . import settings


def export_virtual_gauge(site, flow, rating, extra=None):
    """Write `<key>_virtual_gauge.csv` and its metadata · Écrire le CSV et ses métadonnées"""
    out_dir = settings.out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = flow.assign(date=flow.time.dt.strftime("%Y-%m-%d"), time_utc=flow.time.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    cols = ["date", "time_utc", "source", "wse_m", "wse_u_m"] + [c for c in ["Q_m3s", "Q_lo", "Q_hi"] if c in out]
    f = out_dir / f"{site.key}_virtual_gauge.csv"
    out[cols].round(3).to_csv(f, index=False)
    meta = {"site": site.name, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "height_reference": "EGM2008 geoid (orthometric), metres",
            "level_sources": f"SWOT RiverSP Version D reach {site.swot_reach} (Hydrocron); ICESat-2 ATL13 v007 (SlideRule)",
            "rating_curve": rating, "notes": extra or {}, "made_with": "virtualgauge"}
    mf = out_dir / f"{site.key}_virtual_gauge_metadata.json"
    mf.write_text(json.dumps(meta, indent=1, default=str))
    return f, mf
