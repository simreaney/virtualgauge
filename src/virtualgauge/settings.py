"""Where files go, and whether the package may use the internet.

Où vont les fichiers, et si le package peut utiliser internet.
"""
import os
from pathlib import Path

_state = {"cache_dir": None, "out_dir": None, "data_dir": None, "offline": None, "refresh": False}


def configure(cache_dir=None, out_dir=None, data_dir=None, offline=None, refresh=None):
    """Change settings · Modifier les réglages.

    cache_dir : folder for downloaded data (default ``./cache``)
    out_dir   : folder for exported results (default ``./outputs``)
    data_dir  : folder for your own gauge files (default ``./data``)
    offline   : True = never use the internet
    refresh   : True = download again instead of using saved copies
    """
    for k, v in dict(cache_dir=cache_dir, out_dir=out_dir, data_dir=data_dir,
                     offline=offline, refresh=refresh).items():
        if v is not None:
            _state[k] = v


def cache_dir() -> Path:
    return Path(_state["cache_dir"] or os.environ.get("VG_CACHE_DIR", "cache"))


def out_dir() -> Path:
    return Path(_state["out_dir"] or os.environ.get("VG_OUT_DIR", "outputs"))


def data_dir() -> Path:
    return Path(_state["data_dir"] or os.environ.get("VG_DATA_DIR", "data"))


def offline() -> bool:
    if _state["offline"] is not None:
        return bool(_state["offline"])
    return os.environ.get("VG_OFFLINE", "").strip().lower() in ("1", "true", "yes")


def refresh() -> bool:
    return bool(_state["refresh"])
