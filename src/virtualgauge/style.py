"""One look for every figure · Un même style pour toutes les figures."""
import io
from contextlib import contextmanager

import matplotlib
from matplotlib.figure import Figure

COL = {"SWOT": "#2a78d6", "ICESat-2": "#eb6834", "Q": "#1baf7a",
       "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
       "grid": "#e1e0d9", "axis": "#c3c2b7", "bg": "#fcfcfb", "removed": "#b5b3ab"}
# Extra colours for comparing several stations (never used for satellites or discharge)
STATION_COLOURS = ["#13293d", "#6250d6", "#008300", "#c98500", "#e87ba4", "#e34948"]

STYLE = {
    "figure.facecolor": COL["bg"], "axes.facecolor": COL["bg"], "savefig.facecolor": COL["bg"],
    "axes.edgecolor": COL["axis"], "axes.linewidth": 0.8, "axes.labelcolor": COL["ink2"],
    "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
    "axes.grid": True, "grid.color": COL["grid"], "grid.linewidth": 0.8, "grid.linestyle": "-",
    "xtick.color": COL["axis"], "ytick.color": COL["axis"],
    "xtick.labelcolor": COL["ink2"], "ytick.labelcolor": COL["ink2"],
    "text.color": COL["ink"], "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "font.size": 10.5, "lines.linewidth": 1.6, "lines.solid_capstyle": "round", "legend.frameon": False,
    "date.converter": "concise",
}


@contextmanager
def styled():
    """Apply the style only while a figure is drawn · Appliquer le style seulement pendant le tracé"""
    with matplotlib.rc_context(STYLE):
        yield


def new_figure(w=10, h=4.2, nrows=1, ncols=1, **kw):
    fig = Figure(figsize=(w, h), dpi=110, layout="constrained")
    axes = fig.subplots(nrows, ncols, **kw)
    return fig, axes


def dots(color, ms=6):
    """Filled marker with a thin light ring · Marqueur plein avec un fin anneau clair"""
    return dict(marker="o", ms=ms, mfc=color, mec=COL["bg"], mew=0.8, ls="none")


def removed_style():
    return dict(marker="x", ms=4.5, ls="none", color=COL["removed"])


def to_png(fig, dpi=110):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    return buf.getvalue()


def use_style():
    """Use the package style for your own matplotlib figures · Utiliser ce style pour vos propres figures"""
    matplotlib.rcParams.update(STYLE)
