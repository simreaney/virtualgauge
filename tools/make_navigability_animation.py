"""Animate the navigability index map through time: one frame a week since SWOT began (no internet needed).

Animer la carte de l'indice de navigabilité : une image par semaine depuis le début de SWOT (sans internet).

Usage: python tools/make_navigability_animation.py [congo|amazon] [--lang en|fr] [--days 7] [--fps 8] [--out FOLDER]
       writes <out>/<region>_navigability_<lang>.mp4 (1920 × 1080) and .gif (960 × 540); default out: outputs/

Each frame is the map survey.navigability(date) draws for that date: every reach coloured by its latest good SWOT
level of the previous 30 days, placed between the lowest (0) and highest (100) level of its whole record. Beside it:
the share of the river length in each band on that date, and the same shares through time (as survey.history()).
Uses the survey in the cache folder, else the copy bundled with the package. Needs ffmpeg.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))           # draw with this checkout, not an installed copy
os.environ.setdefault("VG_OFFLINE", "1")

import numpy as np                              # noqa: E402
import pandas as pd                             # noqa: E402
from matplotlib import dates as mdates          # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.figure import Figure            # noqa: E402
from matplotlib.lines import Line2D             # noqa: E402

import virtualgauge as vg                       # noqa: E402
from virtualgauge import navigation as nv       # noqa: E402
from virtualgauge import navplots               # noqa: E402
from virtualgauge.i18n import MONTHS, Day, fmt_int, t  # noqa: E402
from virtualgauge.style import COL, styled      # noqa: E402

W, H, DPI = 12.8, 7.2, 150                      # 1920 × 1080 pixels
X0, X1 = 0.585, 0.975                           # the column beside the map (figure fraction)
HOLD_START, HOLD_END = 1.0, 3.0                 # seconds on the first and last frame

# The few words the package does not have yet · les quelques mots que le paquet n'a pas encore
WORDS = {
    "eyebrow": ("{name} · SWOT satellite", "{name} · satellite SWOT"),
    "bars": ("Share of river length in each band", "Part de la longueur des rivières dans chaque classe"),
    "count": ("{n} of {total} reaches have an index on this date", "{n} tronçons sur {total} ont un indice à cette date"),
    "time": ("Through time", "Au fil du temps"),
    "credit": ("Each reach: its latest good SWOT level of the previous {days} days. Levels: SWOT L2 HR RiverSP reach, "
               "Version D (NASA/CNES, PO.DAAC), via Hydrocron. River network: SWORD v17b. Made with virtualgauge.",
               "Chaque tronçon : son dernier bon niveau SWOT des {days} jours précédents. Niveaux : SWOT L2 HR RiverSP "
               "reach, version D (NASA/CNES, PO.DAAC), via Hydrocron. Réseau : SWORD v17b. Fait avec virtualgauge."),
}


def w(key, lang, **kw):
    return WORDS[key][lang == "fr"].format(**kw)


def pct(v, lang):
    return f"{v:.0f} %" if lang == "fr" else f"{v:.0f}%"


def month_label(d, lang):
    """The year in January, else the month in short: "May", "Sep" · "mai", "sept." """
    if d.month == 1:
        return str(d.year)
    name = MONTHS[lang][d.month - 1]
    return name[:3] if lang == "en" else (name if len(name) <= 4 else name[:4] + ".")


def frames(survey, step_days):
    """For each date: the band of every reach, the share of river length in each band, and the reaches with an
    index. Dates as survey.history(): from max_age_days after the first level, to the day of the survey."""
    p, tab = survey.params, survey.table
    t0 = survey.levels.loc[survey.levels.reason == "kept", "time"].min()
    days = list(pd.date_range(pd.Timestamp(t0).normalize() + pd.Timedelta(days=p.max_age_days),
                              survey.as_of.normalize(), freq=f"{step_days}D"))
    if days[-1] < survey.as_of.normalize():
        days.append(survey.as_of.normalize())
    km = tab.set_index("reach_id").length_km
    km = km.fillna(km.median())
    out = []
    for day in days:
        now = nv.index_at(tab, survey.levels, nv._date(day), p)
        band = now.band
        has = band >= 0
        total = km.reindex(now.index)[has].sum()
        share = [100 * km.reindex(now.index)[band == b].sum() / total if total else 0.0 for b in range(5)]
        out.append(dict(day=day, band=band, share=share, n=int(has.sum())))
    return out


class Animation:
    """The figure, drawn once; each frame only recolours the rivers and moves the numbers."""

    def __init__(self, survey, frames, lang):
        self.lang, self.n_reaches = lang, len(survey.table)
        tab = survey.table
        self.fig = Figure(figsize=(W, H), dpi=DPI)
        FigureCanvasAgg(self.fig)
        self._map(survey, tab)
        self._header(survey)
        self._bars()
        self._timeline(frames)
        self.fig.text(X0, 0.022, "\n".join(textwrap.wrap(w("credit", lang, days=survey.params.max_age_days), 108)),
                      fontsize=6.6, color=COL["muted"], va="bottom", linespacing=1.35)

    def _map(self, survey, tab):
        ax = self.fig.add_axes([0.012, 0.025, 0.545, 0.95])
        navplots._base(ax, navplots._extent(tab))
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_anchor("W")
        seg, lone = survey._network()
        lw = pd.Series(navplots._width_lw(tab.width_m), index=tab.reach_id.to_numpy())
        seg = seg.assign(w=seg.reach_id.map(lw)).sort_values("w", kind="stable").reset_index(drop=True)
        self.seg_ids, self.seg_w = seg.reach_id.to_numpy(), seg.w.to_numpy()
        self.lines = LineCollection(np.stack([seg[["x0", "y0"]].to_numpy(), seg[["x1", "y1"]].to_numpy()], axis=1),
                                    capstyle="round", zorder=2)
        ax.add_collection(self.lines)
        self.lone_ids = lone.reach_id.to_numpy()
        self.lone = ax.scatter(lone.lon, lone.lat, s=4, linewidths=0, zorder=2) if len(lone) else None
        navplots._ports(ax, survey._ports(), fontsize=8)
        self.colours = np.array([c for _, _, c in nv.BANDS] + [nv.NO_INDEX_C])      # band −1 → the last one

    def _header(self, survey):
        f, lang = self.fig, self.lang
        f.text(X0, 0.945, w("eyebrow", lang, name=survey.name), fontsize=10.5, color=COL["ink2"], va="top")
        f.text(X0, 0.905, t("nv_lab_index"), fontsize=21, fontweight="bold", color=COL["ink"], va="top")
        f.text(X0, 0.835, t("nv_sub_index").replace(", 100", ",\n100"), fontsize=9.5, color=COL["ink2"],
               va="top", linespacing=1.35)
        self.date = f.text(X0, 0.745, "", fontsize=28, fontweight="bold", color=COL["ink"], va="top")

    def _bars(self):
        ax = self.fig.add_axes([X0, 0.385, X1 - X0, 0.255])
        ax.set_xlim(0, 100)
        ax.set_ylim(-0.6, 4.75)
        ax.axis("off")
        ax.text(0, 4.75, w("bars", self.lang), fontsize=10.5, fontweight="bold", color=COL["ink"], va="bottom")
        self.bars, self.values = [], []
        for b, (_, key, colour) in enumerate(nv.BANDS):
            y = b - 0.15                                  # very good on top, as in the map's legend
            ax.text(0, y + 0.22, t(key), fontsize=8.5, color=COL["ink2"], va="bottom")
            ax.barh(y, 100, height=0.34, color=COL["grid"], linewidth=0, alpha=0.6)
            self.bars.append(ax.barh(y, 0, height=0.34, color=colour, linewidth=0)[0])
            self.values.append(ax.text(0, y, "", fontsize=9, color=COL["ink"], va="center", fontweight="bold"))
        self.fig.add_artist(Line2D([X0, X0 + 0.02], [0.356, 0.356], color=nv.NO_INDEX_C, lw=1.2,
                                   solid_capstyle="round"))
        self.count = self.fig.text(X0 + 0.026, 0.356, "", fontsize=8.5, color=COL["muted"], va="center")

    def _timeline(self, frames):
        ax = self.fig.add_axes([X0 + 0.028, 0.115, X1 - X0 - 0.028, 0.165])
        x = [f["day"] for f in frames]
        y = np.array([f["share"] for f in frames]).T
        ax.stackplot(x, *y, colors=[c for _, _, c in nv.BANDS], edgecolor=COL["bg"], linewidth=0.4)
        ax.set_xlim(x[0], x[-1])
        ax.set_ylim(0, 100)
        ax.set_yticks([0, 50, 100])
        ax.yaxis.set_major_formatter(lambda v, _: pct(v, self.lang))
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 5, 9)))
        ax.xaxis.set_major_formatter(lambda v, _: month_label(mdates.num2date(v), self.lang))
        ax.tick_params(labelsize=8, length=0)
        ax.grid(False)
        ax.text(-0.075, 1.07, w("time", self.lang), transform=ax.transAxes, fontsize=10.5, fontweight="bold",
                color=COL["ink"], va="bottom")
        self.x_end = mdates.date2num(x[-1])
        self.future = ax.axvspan(x[0], x[-1], color=COL["bg"], alpha=0.72, linewidth=0, zorder=3)
        self.cursor = ax.axvline(x[0], color=COL["ink"], linewidth=1.4, zorder=4)

    def show(self, f):
        """Set every changing part to frame f"""
        band = f["band"]
        b_seg = band.reindex(self.seg_ids).fillna(-1).astype(int).to_numpy()
        self.lines.set_colors(self.colours[b_seg])
        self.lines.set_linewidths(np.where(b_seg >= 0, self.seg_w, 0.5))
        if self.lone is not None:
            self.lone.set_facecolors(self.colours[band.reindex(self.lone_ids).fillna(-1).astype(int).to_numpy()])
        self.date.set_text(str(Day(f["day"])))
        for bar, text, v in zip(self.bars, self.values, f["share"]):
            bar.set_width(v)
            text.set_x(v + 1.2)
            text.set_text(pct(v, self.lang))
        self.count.set_text(f"{t('nv_no_index')} · "
                            + w("count", self.lang, n=fmt_int(f["n"]), total=fmt_int(self.n_reaches)))
        x = mdates.date2num(f["day"])
        self.cursor.set_xdata([x, x])
        self.future.set_x(x)
        self.future.set_width(self.x_end - x)

    def save(self, path):
        self.fig.savefig(path, dpi=DPI, facecolor=COL["bg"])


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("region", nargs="?", default="congo", choices=sorted(nv.REGIONS))
    a.add_argument("--lang", default="en", choices=["en", "fr"])
    a.add_argument("--days", type=int, default=7, help="days between frames (default 7)")
    a.add_argument("--fps", type=float, default=8, help="frames per second (default 8)")
    a.add_argument("--cache", default=str(ROOT / "cache"), help="cache folder with the survey (default ./cache)")
    a.add_argument("--out", default=str(ROOT / "outputs"), help="folder for the MP4 and GIF (default ./outputs)")
    args = a.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is needed to make the video · ffmpeg est nécessaire pour faire la vidéo")

    vg.configure(cache_dir=args.cache, offline=True)
    vg.set_language(args.lang)
    survey = vg.river_survey(args.region, download=False)
    print(survey)
    if survey.error:
        raise SystemExit(survey.error)
    fr = frames(survey, args.days)
    print(f"{len(fr)} frames, {fr[0]['day']:%Y-%m-%d} to {fr[-1]['day']:%Y-%m-%d}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"{args.region}_navigability_{args.lang}"
    with styled(), tempfile.TemporaryDirectory() as tmp:
        anim = Animation(survey, fr, args.lang)
        for i, f in enumerate(fr):
            anim.show(f)
            anim.save(Path(tmp) / f"{i:04d}.png")
            if i % 25 == 0:
                print(f"  frame {i + 1}/{len(fr)}  {f['day']:%Y-%m-%d}", flush=True)
        anim.save(stem.with_suffix(".png"))                      # the last frame, as a still
        frames_in = ["-framerate", str(args.fps), "-i", str(Path(tmp) / "%04d.png")]
        hold = (f"tpad=start_mode=clone:start_duration={HOLD_START}:"
                f"stop_mode=clone:stop_duration={HOLD_END}")
        ffmpeg(*frames_in, "-vf", hold, "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(stem.with_suffix(".mp4")))
        ffmpeg(*frames_in, "-vf", f"{hold},scale=960:-1:flags=lanczos,split[a][b];"
                                  "[a]palettegen=max_colors=96:stats_mode=full[p];[b][p]paletteuse=dither=none",
               "-loop", "0", str(stem.with_suffix(".gif")))
    for suffix in (".mp4", ".gif", ".png"):
        f = stem.with_suffix(suffix)
        print(f"{f}  {f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
