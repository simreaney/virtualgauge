"""One function per figure. Each returns a matplotlib Figure (no pyplot) · Une fonction par figure."""
import numpy as np
import pandas as pd

from .i18n import fmt_int, t, title
from .rating import rating_band, rating_q
from .style import COL, STATION_COLOURS, dots, new_figure, removed_style, styled


def _y(key, **kw):
    """Y-axis labels: two lines in "both" mode, so they are not cut off · Étiquettes sur deux lignes"""
    return t(key, sep="\n", **kw)


def _years(ax):
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def _gapped(times, y, max_gap_days=60):
    """Insert breaks where observations are far apart, so lines do not hide gaps · Couper la ligne aux lacunes"""
    t = pd.to_datetime(pd.Series(times)).reset_index(drop=True)
    y = pd.Series(np.asarray(y, float))
    tt, yy = [], []
    for i in range(len(t)):
        if i and (t[i] - t[i - 1]) > pd.Timedelta(days=max_gap_days):
            tt.append(t[i - 1] + (t[i] - t[i - 1]) / 2)
            yy.append(np.nan)
        tt.append(t[i])
        yy.append(y[i])
    return tt, yy


def _time_axis(ax, xlim):
    if xlim is not None:
        ax.set_xlim(*xlim)


def fig_raw(raw, short, xlim=None):
    with styled():
        fig, ax = new_figure()
        ax.plot(raw.index, raw.ht_ortho, **dots(COL["ICESat-2"], ms=3))
        ax.set_ylabel(_y("lab_level"))
        ax.set_title(title("ttl_raw", site=short))
        _time_axis(ax, xlim)
    return fig


def fig_cleaning(pts, short, xlim=None):
    with styled():
        fig, ax = new_figure()
        rem, kep = pts[pts.reason != "kept"], pts[pts.reason == "kept"]
        ax.plot(rem.time, rem.ht_ortho, **removed_style(), label=t("lab_removed"))
        ax.plot(kep.time, kep.ht_ortho, **dots(COL["ICESat-2"], ms=3), label=t("lab_kept"))
        ax.set_ylabel(_y("lab_level"))
        ax.legend(loc="upper left")
        ax.set_title(title("ttl_cleaning", site=short))
        _time_axis(ax, xlim)
    return fig


def fig_profile(pts, slope, pass_id):
    with styled():
        fig, ax = new_figure(8.5, 4.2)
        g = pts[pts.pass_id == pass_id]
        k = g[g.reason == "kept"]
        ax.plot(g[g.reason != "kept"].s_km, g[g.reason != "kept"].ht_ortho, **removed_style(), label=t("lab_removed"))
        ax.plot(k.s_km, k.ht_ortho, **dots(COL["ICESat-2"], ms=4), label=t("lab_kept"))
        if len(k):
            xs = np.linspace(g.s_km.min(), g.s_km.max(), 10)
            ax.plot(xs, np.median(k.ht_ortho) + slope * (xs - np.median(k.s_km)), color=COL["ink"], lw=1.2,
                    label=t("lab_median_slope", cm=slope * 100))
        ax.set_xlabel(t("lab_dist"))
        ax.set_ylabel(_y("lab_level"))
        ax.legend()
        ax.set_title(title("ttl_profile", pass_id=pass_id))
    return fig


def fig_icesat_levels(vs_ice, short, xlim=None):
    with styled():
        fig, ax = new_figure()
        ax.errorbar(vs_ice.time, vs_ice.wse_m, yerr=vs_ice.wse_u_m, color=COL["ICESat-2"], elinewidth=1,
                    capsize=0, **dots(COL["ICESat-2"]))
        ax.set_ylabel(_y("lab_level"))
        ax.set_title(title("ttl_icesat_levels", site=short))
        _time_axis(ax, xlim)
    return fig


def fig_swot(main, short, reach, xlim=None):
    with styled():
        fig, ax = new_figure()
        obs = main[~main.reason.str.startswith("0")]
        rem, kep = obs[obs.reason != "kept"], obs[obs.reason == "kept"]
        ax.plot(rem.time, rem.wse, **removed_style(), label=t("lab_removed"))
        ax.errorbar(kep.time, kep.wse, yerr=kep.wse_u, color=COL["SWOT"], elinewidth=1, capsize=0,
                    **dots(COL["SWOT"]), label=t("lab_kept"))
        ax.set_ylabel(_y("lab_level"))
        ax.legend(loc="upper left")
        ax.set_title(title("ttl_swot", site=short, reach=reach))
        _time_axis(ax, xlim)
    return fig


def fig_levels(vs, short, xlim=None, ax=None):
    with styled():
        fig = None
        if ax is None:
            fig, ax = new_figure()
        for src in ["SWOT", "ICESat-2"]:
            d = vs[vs.source == src]
            if len(d):
                ax.errorbar(d.time, d.wse_m, yerr=d.wse_u_m, color=COL[src], elinewidth=1, capsize=0,
                            **dots(COL[src]), label=f"{src} ({len(d)})")
        ax.set_ylabel(_y("lab_level"))
        ax.legend(loc="upper left")
        ax.set_title(title("ttl_levels", site=short))
        _time_axis(ax, xlim)
    return fig


def fig_reference(q_ref, start, src_label):
    with styled():
        fig, ax = new_figure(10, 3.6)
        span = q_ref[start:]
        ax.plot(span.index, span.values, color=COL["Q"], lw=1.4)
        ax.set_ylabel(_y("lab_q"))
        ax.set_title(title("ttl_reference", src=src_label))
    return fig


def fig_rating(use, excluded, p, boot, ax=None):
    with styled():
        fig = None
        if ax is None:
            fig, ax = new_figure(8.5, 5.2)
        allh = pd.concat([use.wse_m, excluded.wse_m]) if excluded is not None and len(excluded) else use.wse_m
        hh = np.linspace(allh.min() - 0.3, allh.max() + 0.3, 200)
        if boot is not None and len(boot):
            lo, hi = rating_band(hh, boot)
            ax.fill_between(hh, lo, hi, color=COL["ink2"], alpha=0.12, lw=0, label=t("lab_band"))
        if excluded is not None and len(excluded):
            ax.plot(excluded.wse_m, excluded.Q_ref, **removed_style(), label=t("lab_not_used"))
        for src in ["SWOT", "ICESat-2", "quantiles"]:
            d = use[use.source == src]
            if len(d):
                ax.plot(d.wse_m, d.Q_ref, **dots(COL.get(src, COL["Q"])), label=src)
        ax.plot(hh, rating_q(hh, p), color=COL["ink"], lw=1.6, label=f"Q = a·(h − {p['h0']:.2f})^{p['b']:.2f}")
        ax.set_xlabel(t("lab_level"))
        ax.set_ylabel(_y("lab_q"))
        ax.legend(loc="upper left", fontsize=9)
        ax.set_title(title("ttl_rating"))
    return fig


def fig_residuals(by_month, ax=None):
    with styled():
        fig = None
        if ax is None:
            fig, ax = new_figure(9, 3.6)
        ax.bar(by_month.index, by_month["median"].fillna(0), width=0.6, color=COL["ink2"])
        ax.axhline(0, color=COL["axis"], lw=1)
        ax.set_xticks(range(1, 13))
        ax.set_xlabel(t("lab_month"))
        ax.set_ylabel(_y("lab_median_resid"))
        ax.set_title(title("ttl_residuals"))
    return fig


def fig_discharge(flow, q_span, src_label, short):
    with styled():
        fig, ax = new_figure()
        if q_span is not None and len(q_span):
            ax.plot(q_span.index, q_span.values, color=COL["Q"], lw=1.2, label=t("lab_reference", src=src_label))
        for src in ["SWOT", "ICESat-2"]:
            d = flow[flow.source == src]
            if len(d):
                ax.errorbar(d.time, d.Q_m3s, yerr=[d.Q_m3s - d.Q_lo, d.Q_hi - d.Q_m3s], color=COL[src],
                            elinewidth=1, capsize=0, **dots(COL[src]), label=t("lab_virtual", src=src))
        ax.set_ylabel(_y("lab_q"))
        ax.legend(loc="upper left", fontsize=9)
        ax.set_title(title("ttl_discharge", site=short))
    return fig


def fig_compare_reaches(series, site_short):
    """series: {label: cleaned SWOT DataFrame} — same vertical scale · même échelle verticale"""
    with styled():
        n = len(series)
        fig, axes = new_figure(4.3 * n, 4.4, 1, n, sharey=True)
        axes = np.atleast_1d(axes)
        for ax, (label, d) in zip(axes, series.items()):
            k = d[d.reason == "kept"]
            ax.plot(k.time, k.wse, **dots(COL["SWOT"], ms=5))
            ax.set_title(label, fontsize=10.5)
            _years(ax)
        axes[0].set_ylabel(_y("lab_level"))
        fig.suptitle(title("ttl_compare_reaches", site=site_short), x=0.01, ha="left", fontweight="bold")
    return fig


def fig_flood_catch(table):
    """table: index = duration (days), columns = station labels, values = share (0–1)"""
    with styled():
        fig, ax = new_figure(8.5, 4.2)
        for i, col in enumerate(table.columns):
            ax.plot(table.index, 100 * table[col], color=STATION_COLOURS[i % len(STATION_COLOURS)], lw=2,
                    marker="o", ms=6, mec=COL["bg"], label=col)
        ax.set_xscale("log")
        ax.set_xticks(list(table.index))
        ax.set_xticklabels([str(d) for d in table.index])
        ax.set_ylim(0, 102)
        ax.set_xlabel(t("lab_duration"))
        ax.set_ylabel(_y("lab_catch"))
        ax.legend(loc="upper left")
        ax.set_title(title("ttl_flood_catch"))
    return fig


def fig_compare_stations(levels):
    """levels: {label: combined levels} → level minus median, one panel each · un panneau par station"""
    with styled():
        n = len(levels)
        fig, axes = new_figure(10, 1.9 * n + 0.6, n, 1, sharex=True, sharey=True)
        axes = np.atleast_1d(axes)
        colour = STATION_COLOURS[0]          # one colour: the panel title names the station
        for ax, (label, vs) in zip(axes, levels.items()):
            if len(vs):
                a = (vs.wse_m - vs.wse_m.median()).to_numpy(float)
                ax.plot(*_gapped(vs.time, a), color=colour, lw=0.8, alpha=0.5)   # no line across long gaps
                ax.plot(vs.time, a, **dots(colour, ms=4))
            ax.set_title(label, fontsize=10.5)
        axes[len(axes) // 2].set_ylabel(_y("lab_anomaly"))
        fig.suptitle(title("ttl_compare_stations"), x=0.01, ha="left", fontweight="bold")
    return fig


def fig_dashboard(st, rating=None, by_month=None, use=None, excluded=None, boot=None):
    """2×2 summary for the explore widget · Résumé 2×2 pour le widget d'exploration"""
    with styled():
        fig, axes = new_figure(12, 7.6, 2, 2)
        fig_levels(st.data.vs, st.site.short, xlim=st.xlim, ax=axes[0, 0])
        ax = axes[0, 1]
        if rating is not None:
            fig_rating(use, excluded, rating, boot, ax=ax)
            ax.legend(loc="upper left", fontsize=8)          # half-width panel: smaller legend
        else:
            ax.axis("off")
            ax.text(0.02, 0.6, t("msg_no_rating_short", sep="\n"), transform=ax.transAxes, fontsize=11, va="top")
        ax = axes[1, 0]
        if by_month is not None:
            fig_residuals(by_month, ax=ax)
        else:
            ax.axis("off")
        ax = axes[1, 1]
        counts = st.removal_counts()
        ax.barh(range(len(counts)), counts["count"], height=0.42,
                color=[COL["ICESat-2"] if s == "ICESat-2" else COL["SWOT"] for s in counts["satellite"]])
        ax.set_yticks([])                                    # labels above the bars, so the panel keeps its width
        for i, (lab, n) in enumerate(zip(counts["label"], counts["count"])):
            ax.text(0.005, i - 0.27, f"{lab}: {fmt_int(n)}", transform=ax.get_yaxis_transform(),
                    fontsize=8.5, va="bottom", ha="left")
        ax.set_ylim(len(counts) - 0.5, -0.95)
        ax.set_xscale("symlog")
        ax.set_title(title("ttl_counts"))
    return fig
