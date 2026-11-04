"""Your own files: agency gauge records and GRDC downloads · Vos fichiers : stations du service et GRDC."""
import pandas as pd

from .processing import utc_naive


def load_gauge(path):
    """Read an agency gauge file (date, stage_m, discharge_m3s) · Lire un fichier de station"""
    g = pd.read_csv(path)
    g["date"] = utc_naive(g["date"]).dt.normalize()
    for c in ["stage_m", "discharge_m3s"]:
        g[c] = pd.to_numeric(g.get(c), errors="coerce")
    return g.groupby("date")[["stage_m", "discharge_m3s"]].mean()


def load_grdc_daily(path):
    """Read a GRDC daily file (header lines start with '#') · Lire un fichier journalier GRDC.
    Written from the GRDC file format; not tested with a real file · non testé avec un vrai fichier."""
    df = pd.read_csv(path, sep=";", comment="#", skipinitialspace=True, encoding="latin-1")
    df.columns = [c.strip() for c in df.columns]
    date_col = next(c for c in df.columns if c.upper().startswith("YYYY"))
    val_col = next(c for c in df.columns if c.lower() in ("value", "original", "calculated"))
    q = pd.Series(pd.to_numeric(df[val_col], errors="coerce").to_numpy(), index=utc_naive(df[date_col]), name="Q_m3s")
    return q[q >= 0]
