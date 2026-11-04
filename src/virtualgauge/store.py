"""Find data: your cache first, then the copy shipped with the package, then the internet.

Trouver les données : d'abord votre cache, puis la copie fournie avec le package, puis internet.
"""
import json
import os
import warnings
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from . import settings
from .i18n import t, M

ORIGINS = {}          # name -> dict(origin, path, date)
_MEMO = {}            # (path, mtime) -> object, so the widgets re-use files already read


class OfflineError(RuntimeError):
    """Raised when data are needed but the package is offline and has no copy."""


class DownloadError(RuntimeError):
    """Raised when a download fails and no saved copy exists."""


def bundle_dir() -> Path:
    return Path(str(resources.files("virtualgauge") / "data"))


def bundled_path(name):
    p = bundle_dir() / name
    return p if p.is_file() else None


def manifest():
    p = bundle_dir() / "MANIFEST.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _log_path():
    return settings.cache_dir() / "download_log.json"


def log_download(name, source):
    """Record what was downloaded, from where and when · Noter quoi, d'où et quand."""
    f = _log_path()
    f.parent.mkdir(parents=True, exist_ok=True)
    log = json.loads(f.read_text()) if f.exists() else {}
    log[name] = {"source": source, "downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    f.write_text(json.dumps(log, indent=1))


def _date_of(name, origin):
    if origin == "bundled":
        return manifest().get("files", {}).get(name, {}).get("downloaded_utc", "")[:10]
    f = _log_path()
    if f.exists():
        return json.loads(f.read_text()).get(name, {}).get("downloaded_utc", "")[:10]
    return ""


def _read(path, read):
    key = (str(path), os.path.getmtime(path))
    if key not in _MEMO:
        _MEMO[key] = read(path)
    return _MEMO[key]


def load_or_fetch(name, read, fetch, write, source="", refresh=None):
    """Return the data called `name`.

    read(path) -> object ; fetch() -> (object or None, source) ; write(object, path).
    Order: user cache -> bundled copy -> (offline? stop) -> download into the cache.
    """
    refresh = settings.refresh() if refresh is None else refresh
    cache = settings.cache_dir() / name
    candidates = [(cache, "cache"), (bundled_path(name), "bundled")]
    if not refresh:
        for path, origin in candidates:
            if path is not None and Path(path).exists():
                try:
                    obj = _read(path, read)
                except Exception:
                    warnings.warn(t("msg_cache_unreadable", name=name))
                    continue
                ORIGINS[name] = dict(origin=origin, path=str(path), date=_date_of(name, origin))
                return obj
    if settings.offline():
        err = OfflineError(t("msg_offline_missing", name=name))
        err.msg = M("msg_offline_missing", name=name)       # shown later in the reader's language, once
        raise err
    try:
        obj, src = fetch()
    except Exception as e:
        if refresh:
            for path, origin in candidates:
                if path is not None and Path(path).exists():
                    warnings.warn(t("msg_refresh_failed", name=name, date=_date_of(name, origin)))
                    ORIGINS[name] = dict(origin=origin, path=str(path), date=_date_of(name, origin))
                    return _read(path, read)
        raise DownloadError(t("msg_download_failed", name=name)) from e
    if obj is None:                      # e.g. "no data" answers are not cached
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_name(cache.name + ".part")
    write(obj, tmp)
    os.replace(tmp, cache)
    log_download(name, src or source)
    ORIGINS[name] = dict(origin="download", path=str(cache), date=_date_of(name, "download"))
    return obj
