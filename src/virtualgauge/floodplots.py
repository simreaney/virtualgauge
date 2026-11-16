"""Figures for flood mapping (English only for now) · Figures de cartographie des crues.

Colours follow the package palette (style.py): blue = water, orange = new flood water, aqua = water gone.
Only three colours share a map (they stay distinct for colour-blind readers); 'not seen' is hatched, not coloured.
"""
import matplotlib
import matplotlib.ticker
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, ListedColormap, TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from .i18n import t, title
from .style import COL, dots, new_figure, styled

WATER_C, FLOOD_C, GONE_C = COL["SWOT"], COL["ICESat-2"], COL["Q"]       # blue, orange, aqua
KEPT_C, REMOVED_C = COL["SWOT"], COL["ICESat-2"]
OLD_WATER_C = "#8f8d86"                                                 # neutral: water already there
BLUES = LinearSegmentedColormap.from_list("depth", ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf",
                                                    "#184f95", "#0d366b"])
DIVERGE = LinearSegmentedColormap.from_list("rise", ["#8f2a29", "#e34948", "#f2a6a2", "#f0efec", "#9ec5f4",
                                                     "#2a78d6", "#104281"])
GROUND = LinearSegmentedColormap.from_list("ground", ["#f0efec", "#c3c2b7", "#898781", "#52514e"])
SHADE = LinearSegmentedColormap.from_list("shade", ["#bdbcb4", "#fcfcfb"])
HATCH = {"hatch.color": COL["muted"], "hatch.linewidth": 0.5}


def hillshade(dem, res=100.0, azimuth=315.0, altitude=45.0, z=4.0):
    """Shaded relief from the DEM, for orientation only · Relief ombré, pour se repérer"""
    if dem is None or not np.isfinite(dem).any():
        return None
    d = np.where(np.isfinite(dem), dem, np.nanmedian(dem)) * z
    dy, dx = np.gradient(d, res)
    slope = np.pi / 2 - np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)
    az, alt = np.radians(360 - azimuth + 90), np.radians(altitude)
    hs = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    return np.clip(hs, 0, 1)


def _mask_img(mask, colour):
    rgba = np.zeros(mask.shape + (4,))
    rgba[mask] = matplotlib.colors.to_rgba(colour)
    return rgba


def _base(ax, grid, dem):
    ext = grid.extent_km()
    hs = hillshade(dem, grid.res)
    if hs is not None:
        ax.imshow(hs, extent=ext, cmap=SHADE, vmin=0, vmax=1, interpolation="nearest")
    return ext


def _finish(ax, grid, unseen, ttl=None):
    """Hatch what was not seen, fade outside the area, draw its outline · Hachurer, estomper, contourer"""
    ext = grid.extent_km()
    xc = (np.arange(grid.nx) + 0.5) * grid.res / 1000
    yc = ext[3] - (np.arange(grid.ny) + 0.5) * grid.res / 1000
    if unseen is not None and unseen.any():
        with matplotlib.rc_context(HATCH):
            ax.contourf(xc, yc, unseen.astype(float), levels=[0.5, 1.5], colors="none", hatches=["////"])
    ax.imshow(_mask_img(~grid.inside, COL["bg"]), extent=ext, alpha=0.7, interpolation="nearest")
    for x, y in grid.outline_km():
        ax.plot(x, y, color=COL["ink"], lw=1.0)
    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])
    ax.set_aspect("equal")
    ax.grid(False)
    ax.set_xlabel(t("fl_lab_km"))
    if ttl:
        ax.set_title(ttl, fontsize=10.5)


def _legend(fig, items, unseen=True, outline=True, ncol=None):
    h = [Patch(facecolor=c, edgecolor="none", label=lab) for lab, c in items]
    if unseen:
        h.append(Patch(facecolor="none", edgecolor=COL["muted"], hatch="////", lw=0.5, label=t("fl_cls_unseen")))
    if outline:
        h.append(Line2D([0], [0], color=COL["ink"], lw=1.0, label=t("fl_map_area")))
    with matplotlib.rc_context(HATCH):
        fig.legend(handles=h, loc="outside lower center", ncol=ncol or len(h), frameon=False, fontsize=9.5)


def fig_passes(tab, hydro, chosen, flood_date, name):
    """When SWOT looked, and the river level at the same time · Quand SWOT a regardé"""
    with styled():
        if hydro:
            fig, (ax1, ax2) = new_figure(10, 5.4, nrows=2, sharex=True, gridspec_kw=dict(height_ratios=[1.6, 1]))
        else:
            fig, ax2 = new_figure(10, 2.9)
            ax1 = None
        when = pd.to_datetime(tab.date + " " + tab.time_utc)
        ax2.plot(when, tab.seen_pct, **dots(COL["SWOT"], ms=7))
        ax2.set_ylim(-8, 112)
        ax2.set_yticks([0, 50, 100])
        ax2.set_ylabel(t("fl_lab_seen_pct"))
        lo, hi = when.min() - pd.Timedelta(days=5), when.max() + pd.Timedelta(days=5)
        if hydro:
            s = hydro["series"]
            s = s[(s.index >= lo - pd.Timedelta(days=60)) & (s.index <= hi + pd.Timedelta(days=60))]
            ax1.plot(s.index, s.values, color=COL["SWOT"], lw=1.4, marker="o", ms=3.5, mfc=COL["SWOT"],
                     mec=COL["bg"], mew=0.6)
            ax1.set_ylabel(t("lab_level"))
            ax1.set_title(title("fl_ttl_hydro", river=hydro["river"], reach=hydro["reach"]))
            if len(s):
                lo, hi = min(lo, s.index.min()), max(hi, s.index.max())
        else:
            ax2.set_title(title("fl_ttl_passes", name=name or ""))
        for key, lab in (("before", t("fl_lab_before")), ("after", t("fl_lab_after"))):
            hit = tab[tab["pass"] == chosen.get(key)]
            if hit.empty:
                continue
            x, y = pd.Timestamp(hit.date.iloc[0] + " " + hit.time_utc.iloc[0]), hit.seen_pct.iloc[0]
            ax2.plot([x], [y], marker="o", ms=13, mfc="none", mec=COL["ink"], mew=1.6, ls="none")
            ax2.annotate(f"{lab}\n{hit['pass'].iloc[0]}", (x, y), xytext=(0, -26), textcoords="offset points",
                         ha="center", va="top", fontsize=9, color=COL["ink2"])
            for ax in [a for a in (ax1, ax2) if a is not None]:
                ax.axvline(x, color=COL["ink2"], lw=0.9, ls=(0, (3, 3)), zorder=0)
        if flood_date:
            fd = pd.Timestamp(flood_date)
            for ax in [a for a in (ax1, ax2) if a is not None]:
                ax.axvline(fd, color=FLOOD_C, lw=1.4, zorder=0)
            top = ax1 if ax1 is not None else ax2
            top.annotate(t("fl_lab_flood_date"), (fd, 1.0), xycoords=("data", "axes fraction"), xytext=(4, -2),
                         textcoords="offset points", va="top", fontsize=9, color=COL["ink2"])
        ax2.set_xlim(lo, hi)
        if not hydro:
            ax2.set_ylim(-60, 112)
    return fig


def _three(w=12.5, h=4.9):
    fig, axes = new_figure(w, h, ncols=3, sharex=True, sharey=True)
    axes[0].set_ylabel(t("fl_lab_km"))
    return fig, axes


def fig_extent(grid, a, dates):
    """Water before, after, and the change · L'eau avant, après, et le changement"""
    inside = grid.inside
    with styled():
        fig, (ax1, ax2, ax3) = _three()
        for ax, water, seen, ttl in ((ax1, a["water_before"], a["seen_before"], title("fl_ttl_before", **dates)),
                                     (ax2, a["water_after"], a["seen_after"], title("fl_ttl_after", **dates))):
            ext = _base(ax, grid, a["dem"])
            ax.imshow(_mask_img(water & inside, WATER_C), extent=ext, interpolation="nearest")
            _finish(ax, grid, inside & ~seen, ttl)
        ext = _base(ax3, grid, a["dem"])
        cls = a["cls"]
        for code, c in ((3, WATER_C), (4, FLOOD_C), (5, GONE_C)):
            ax3.imshow(_mask_img(cls == code, c), extent=ext, interpolation="nearest")
        _finish(ax3, grid, cls == 1, title("fl_ttl_change"))
        _legend(fig, [(t("fl_cls_water_short"), WATER_C), (t("fl_cls_flooded"), FLOOD_C),
                      (t("fl_cls_receded"), GONE_C)])
    return fig


def fig_cleaning(grid, a, dates):
    """Kept and removed SWOT water levels · Niveaux SWOT gardés et retirés"""
    inside = grid.inside
    with styled():
        fig, axes = new_figure(10.5, 5.2, ncols=2, sharex=True, sharey=True)
        axes[0].set_ylabel(t("fl_lab_km"))
        for ax, rk, seen, ttl in ((axes[0], "reason_before", "seen_before", title("fl_ttl_clean_before", **dates)),
                                  (axes[1], "reason_after", "seen_after", title("fl_ttl_clean_after", **dates))):
            ext = _base(ax, grid, a["dem"])
            r = a[rk]
            ax.imshow(_mask_img((r == 0) & inside, KEPT_C), extent=ext, interpolation="nearest")
            ax.imshow(_mask_img((r > 0) & inside, REMOVED_C), extent=ext, interpolation="nearest")
            _finish(ax, grid, inside & ~a[seen], ttl)
        _legend(fig, [(t("fl_lab_kept_level"), KEPT_C), (t("fl_lab_removed_level"), REMOVED_C)])
    return fig


def _sym_limit(v, q=98):
    v = v[np.isfinite(v)]
    return max(float(np.percentile(np.abs(v), q)), 0.1) if len(v) else 1.0


def fig_levels(grid, a, dates, ref=None):
    """Rise of the water already there · Montée de l'eau déjà présente"""
    rise = a["rise"]
    with styled():
        fig, (ax1, ax2) = new_figure(11.5, 4.9, ncols=2, gridspec_kw=dict(width_ratios=[1.15, 1]))
        ext = _base(ax1, grid, a["dem"])
        lim = _sym_limit(rise)
        im = ax1.imshow(np.ma.masked_invalid(rise), extent=ext, cmap=DIVERGE,
                        norm=TwoSlopeNorm(0, -lim, lim), interpolation="nearest")
        _finish(ax1, grid, a["cls"] == 1, title("fl_ttl_rise_map", **dates))
        ax1.set_ylabel(t("fl_lab_km"))
        fig.colorbar(im, ax=ax1, shrink=0.8, label=t("fl_lab_rise"))
        v = rise[np.isfinite(rise)]
        lo, hi = np.percentile(v, [1, 99]) if len(v) else (-1, 1)
        span = max(hi - lo, 0.2)
        ax2.hist(np.clip(v, lo - 0.1 * span, hi + 0.1 * span), bins=60, color=COL["SWOT"], edgecolor=COL["bg"],
                 linewidth=0.4)
        med = float(np.median(v)) if len(v) else 0
        ax2.axvline(med, color=COL["ink"], lw=1.4)
        ax2.annotate(t("fl_lab_median", v=f"{med:.2f}"), (med, 0.97), xycoords=("data", "axes fraction"),
                     xytext=(5, 0), textcoords="offset points", va="top", fontsize=9, color=COL["ink"],
                     bbox=dict(boxstyle="square,pad=0.15", fc=COL["bg"], ec="none", alpha=0.85))
        if ref:
            ax2.axvline(ref["rise_m"], color=COL["ink2"], lw=1.2, ls=(0, (4, 3)))
            ax2.annotate(t("fl_lab_reach_rise", reach=ref["reach"], v=ref["rise"]), (ref["rise_m"], 0.80),
                         xycoords=("data", "axes fraction"), xytext=(-5, 0), textcoords="offset points", va="top",
                         ha="right", fontsize=9, color=COL["ink2"],
                         bbox=dict(boxstyle="square,pad=0.15", fc=COL["bg"], ec="none", alpha=0.85))
        ax2.set_xlabel(t("fl_lab_rise"))
        ax2.set_ylabel(t("fl_lab_cells"))
        ax2.set_title(title("fl_ttl_rise_hist"))
    return fig


def fig_ground(grid, a, dates):
    """Ground height and the flood water surface · Hauteur du sol et surface de l'eau de crue"""
    dem, cls = a["dem"], a["cls"]
    with styled():
        fig, (ax1, ax2) = new_figure(11.5, 4.9, ncols=2, gridspec_kw=dict(width_ratios=[1.15, 1]))
        ext = grid.extent_km()
        vals = dem[grid.inside & np.isfinite(dem)]
        lo, hi = np.percentile(vals, [2, 98]) if len(vals) else (0, 1)
        im = ax1.imshow(np.ma.masked_invalid(dem), extent=ext, cmap=GROUND, vmin=lo, vmax=hi, interpolation="nearest")
        fl = (cls == 4).astype(float)
        xc = (np.arange(grid.nx) + 0.5) * grid.res / 1000
        yc = ext[3] - (np.arange(grid.ny) + 0.5) * grid.res / 1000
        if fl.any():
            ax1.contour(xc, yc, fl, levels=[0.5], colors=[FLOOD_C], linewidths=0.9)
        _finish(ax1, grid, None, title("fl_ttl_ground_map"))
        ax1.set_ylabel(t("fl_lab_km"))
        fig.colorbar(im, ax=ax1, shrink=0.8, label=t("fl_lab_ground"))
        g = dem[(cls == 4) & np.isfinite(dem)]
        s = a["surface"][(cls == 4) & np.isfinite(a["surface"])]
        if len(g):
            ax2.hist(g, bins=50, color=COL["muted"], edgecolor=COL["bg"], linewidth=0.4)
        if len(s):
            ms = float(np.median(s))
            ax2.axvline(ms, color=WATER_C, lw=1.8)
            ax2.annotate(t("fl_lab_surface", v=f"{ms:.1f}"), (ms, 0.97), xycoords=("data", "axes fraction"),
                         xytext=(-5, 0), textcoords="offset points", va="top", ha="right", fontsize=9,
                         color=COL["ink"], bbox=dict(boxstyle="square,pad=0.15", fc=COL["bg"], ec="none", alpha=0.85))
            if len(g):
                lo_, hi_ = float(np.min(g)), max(float(np.max(g)), ms)
                pad = 0.05 * max(hi_ - lo_, 0.5)
                ax2.set_xlim(lo_ - pad, hi_ + pad)
        ax2.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(6))
        ax2.set_xlabel(t("fl_lab_ground"))
        ax2.set_ylabel(t("fl_lab_cells"))
        ax2.set_title(title("fl_ttl_ground_hist", **dates))
        fig.legend(handles=[Line2D([0], [0], color=FLOOD_C, lw=1, label=t("fl_cls_flooded")),
                            Line2D([0], [0], color=WATER_C, lw=1.8, label=t("fl_lab_surface_short"))],
                   loc="outside lower center", ncol=2, frameon=False, fontsize=9.5)
    return fig


def fig_depth(grid, a, dates, max_depth):
    """Flood depth on newly flooded land · Profondeur sur les terres nouvellement inondées"""
    depth, cls = a["depth"], a["cls"]
    with styled():
        fig, (ax1, ax2) = new_figure(11.5, 5.2, ncols=2, gridspec_kw=dict(width_ratios=[1.15, 1]))
        ext = _base(ax1, grid, a["dem"])
        ax1.imshow(_mask_img(cls == 3, OLD_WATER_C), extent=ext, interpolation="nearest")
        d = depth[np.isfinite(depth)]
        vmax = max(float(np.percentile(d, 98)), 0.5) if len(d) else 1
        im = ax1.imshow(np.ma.masked_invalid(depth), extent=ext, cmap=BLUES, vmin=0, vmax=vmax,
                        interpolation="nearest")
        _finish(ax1, grid, cls == 1, title("fl_ttl_depth_map", **dates))
        ax1.set_ylabel(t("fl_lab_km"))
        fig.colorbar(im, ax=ax1, shrink=0.8, label=t("fl_lab_depth"), extend="max")
        raw = a["depth_raw"][np.isfinite(a["depth_raw"])]
        if len(raw):
            lo = max(float(np.percentile(raw, 1)), -max_depth)
            bins = np.linspace(lo, max(float(np.percentile(raw, 99.5)), 0.5), 60)
            neg, pos = raw[raw < 0], raw[raw >= 0]
            ax2.hist(np.clip(neg, lo, None), bins=bins, color=COL["removed"], edgecolor=COL["bg"], linewidth=0.4)
            ax2.hist(pos, bins=bins, color=WATER_C, edgecolor=COL["bg"], linewidth=0.4)
            for q, lab in ((50, "fl_lab_median"), (90, "fl_lab_p90")):
                v = float(np.percentile(d, q)) if len(d) else 0
                ax2.axvline(v, color=COL["ink"], lw=1.2, ls="-" if q == 50 else (0, (4, 3)))
                ax2.annotate(t(lab, v=f"{v:.1f}"), (v, 0.97 if q == 50 else 0.86), xycoords=("data", "axes fraction"),
                             xytext=(5, 0), textcoords="offset points", va="top", fontsize=9, color=COL["ink"],
                             bbox=dict(boxstyle="square,pad=0.15", fc=COL["bg"], ec="none", alpha=0.85))
        ax2.set_xlabel(t("fl_lab_depth_raw"))
        ax2.set_ylabel(t("fl_lab_cells"))
        ax2.set_title(title("fl_ttl_depth_hist"))
        _legend(fig, [(t("fl_lab_old_water"), OLD_WATER_C), (t("fl_lab_depth_ok"), WATER_C),
                      (t("fl_lab_below_ground"), COL["removed"])], ncol=3)
    return fig
