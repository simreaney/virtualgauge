"""The student interface: one Station per river, one method per step.

L'interface étudiante : une Station par rivière, une méthode par étape.
"""
import functools
from types import SimpleNamespace

import numpy as np
import pandas as pd
import requests

from . import download, settings, store
from .export import export_virtual_gauge
from .i18n import M, fmt_int, fmt_num, say, t
from .local_files import load_gauge
from .maps import site_map
from . import plots
from .processing import build_virtual_station, catch_probability, clean_swot, sampling_summary
from .rating import (bootstrap_rating, fit_rating, pair_with_reference, rating_band, rating_q, residuals_by_month,
                     skill, split_sample)
from .results import Result, reason_label
from .sites import resolve

EXPECTED_ERRORS = (store.OfflineError, store.DownloadError, requests.RequestException, ValueError, KeyError)


def _needs_data(method):
    """Show an explanation instead of an error when the station could not be built."""
    @functools.wraps(method)
    def wrapper(self, *a, **kw):
        if self.error:
            return Result(("h_unavailable", {}), [("msg_unavailable", {"why": self.error})])
        return method(self, *a, **kw)
    return wrapper


def _months(ms):
    return ", ".join(str(m) for m in ms) if ms else "—"


class Station:
    """A virtual station. Build it with `vg.build_station(...)` · Une station virtuelle.

    Steps · Étapes : .map() .raw_points() .cleaning() .slope() .icesat_levels() .swot() .agreement() .levels()
    .reference_discharge() .rating() .residuals_by_month() .split_test() .discharge() .export() .compare_reaches()
    Data · Données : .data (raw tables), .params (settings), .to_dataframe()
    """

    def __init__(self, site, params, data=None, error=None, origin=None):
        self.site, self.params, self.error = site, params, error
        self.data = SimpleNamespace(**(data or {}))
        self.origin = origin or {}
        self.current_rating = None
        self._ref = {}

    # --- overview -----------------------------------------------------------------------------------------
    @property
    def xlim(self):
        times = [self.data.raw.index.min(), self.data.vs.time.min() if len(self.data.vs) else None,
                 self.data.vs.time.max() if len(self.data.vs) else None]
        times = [pd.Timestamp(x).tz_localize(None) if getattr(x, "tzinfo", None) else x
                 for x in times if x is not None and not pd.isna(x)]          # no ICESat-2 points → NaT
        if not times:
            return None
        pad = pd.Timedelta(days=45)
        return (min(times) - pad, max(times) + pad)

    def _card(self):
        if self.error:
            return Result(("h_station", {"site": self.site.short}), [("msg_unavailable", {"why": self.error})])
        d = self.data
        lines = []
        if len(d.vs_ice):
            lines.append(("card_icesat", dict(n_levels=len(d.vs_ice), n_points=fmt_int((d.points.reason == "kept").sum()),
                                             first=f"{d.vs_ice.time.min():%Y-%m-%d}", last=f"{d.vs_ice.time.max():%Y-%m-%d}")))
        obs = d.swot_main[~d.swot_main.reason.str.startswith("0")]
        if len(obs):
            lines.append(("card_swot", dict(reach=self.site.swot_reach, kept=len(d.swot_ok), total=len(obs),
                                           first=f"{obs.time.min():%Y-%m-%d}", last=f"{obs.time.max():%Y-%m-%d}")))
        lines.append(("card_offset", dict(offset=d.offset, n=len(d.pairs))) if len(d.pairs) >= 3 else ("card_no_offset", {}))
        o = self.origin
        if o:
            okey = {"bundled": "origin_bundled", "cache": "origin_cache"}.get(o.get("origin"), "origin_download")
            lines.append(("card_data", dict(origin=M(okey, date=o.get("date") or "?"))))
        lines.append(("card_next", {}))
        return Result(("h_station", {"site": self.site.short}), lines)

    def _repr_html_(self):
        return self._card()._repr_html_()

    def __repr__(self):
        return repr(self._card())

    def to_dataframe(self):
        """Water levels (and discharge, if a rating exists) · Niveaux d'eau (et débits, si une courbe existe)"""
        if self.current_rating:
            return self._flow()
        return self.data.vs.copy()

    # --- steps ----------------------------------------------------------------------------------------------
    @_needs_data
    def map(self, points=True):
        """Step 0: map of the water mask, centre-line and ICESat-2 points · Carte du masque et des points"""
        return site_map(self.site, self.data.geo, points=self.data.raw if points else None)

    @_needs_data
    def raw_points(self):
        raw = self.data.raw
        n_pass = raw.groupby(["rgt", "cycle"]).ngroups if len(raw) else 0
        lines = [("raw_line", dict(n_points=fmt_int(len(raw)), n_pass=n_pass,
                                   first=f"{raw.index.min():%Y-%m-%d}" if len(raw) else "—",
                                   last=f"{raw.index.max():%Y-%m-%d}" if len(raw) else "—")),
                 ("raw_question", {})]
        return Result(("h_raw", {}), lines, figure=lambda: plots.fig_raw(raw, self.site.short, self.xlim),
                      values=dict(points=len(raw), passes=n_pass))

    @_needs_data
    def cleaning(self):
        pts = self.data.points
        counts = pts.reason.value_counts().rename("count").rename_axis("reason").reset_index()
        kept = int((pts.reason == "kept").sum())

        def shown():
            return pd.DataFrame({t("col_reason"): counts.reason.map(reason_label), t("col_count"): counts["count"]})
        return Result(("h_cleaning", {}), [("cleaning_line", dict(kept=fmt_int(kept), total=fmt_int(len(pts))))],
                      figure=lambda: plots.fig_cleaning(pts, self.site.short, self.xlim), table=counts,
                      values=dict(kept=kept, total=len(pts),
                                  reasons={str(r): int(n) for r, n in zip(counts.reason, counts["count"])}),
                      display_table=shown)

    @_needs_data
    def slope(self):
        d = self.data
        if not self.site.slope_correction:
            line = ("slope_off", {})
        elif len(d.slopes):
            line = ("slope_line", dict(cm=d.slope * 100, n=len(d.slopes)))
        else:
            line = ("slope_none", {})
        kept = d.points[d.points.reason == "kept"]
        fig = None
        if len(kept):
            best = kept.pass_id.value_counts().idxmax()
            fig = lambda: plots.fig_profile(d.points, d.slope, best)
        return Result(("h_slope", {}), [line], figure=fig, table=d.slopes.round(3),
                      values=dict(slope_m_per_km=d.slope, n_passes=len(d.slopes)))

    @_needs_data
    def icesat_levels(self):
        v = self.data.vs_ice
        s = sampling_summary(v.time)
        return Result(("h_icesat_levels", {}),
                      [("icesat_line", dict(n=len(v), per_year=s["per_year"], gap=s["median_gap_days"]))],
                      figure=lambda: plots.fig_icesat_levels(v, self.site.short, self.xlim),
                      table=v[["pass_id", "time", "wse_m", "wse_u_m", "n_points"]].round({"wse_m": 3, "wse_u_m": 3}), values=s)

    @_needs_data
    def swot(self):
        m = self.data.swot_main
        obs = m[~m.reason.str.startswith("0")]
        s = sampling_summary(self.data.swot_ok.time)
        n_quality = int(obs.reason.str.match(r"^[123] ").sum())
        n_hyd = int(obs.reason.str.startswith("4 ").sum())
        counts = obs.reason.value_counts().rename("count").rename_axis("reason").reset_index()

        def shown():
            return pd.DataFrame({t("col_reason"): counts.reason.map(reason_label), t("col_count"): counts["count"]})
        lines = [("swot_line", dict(kept=len(self.data.swot_ok), observed=len(obs), per_year=s["per_year"])),
                 ("swot_quality", dict(n=n_quality)), ("swot_hydraulic", dict(n=n_hyd))]
        return Result(("h_swot", {}), lines,
                      figure=lambda: plots.fig_swot(m, self.site.short, self.site.swot_reach, self.xlim),
                      table=counts, display_table=shown,
                      values=dict(kept=len(self.data.swot_ok), observed=len(obs), quality=n_quality, hydraulic=n_hyd))

    @_needs_data
    def agreement(self):
        p = self.data.pairs
        if len(p) == 0:
            return Result(("h_agreement", {}), [("agreement_none", {})])
        line = ("agreement_line", dict(n=len(p), days=self.params.max_days, offset=p.difference_m.median(),
                                       big=p.difference_m.abs().max()))
        lines = [line] + ([] if len(p) >= 3 else [("card_no_offset", {})])
        return Result(("h_agreement", {}), lines, table=p.round({"wse_m": 3, "wse_swot": 3, "difference_m": 3}),
                      values=dict(pairs=len(p), offset_m=self.data.offset))

    @_needs_data
    def levels(self):
        vs = self.data.vs
        n_swot, n_ice = int((vs.source == "SWOT").sum()), int((vs.source == "ICESat-2").sum())
        if len(vs) == 0:
            return Result(("h_levels", {}), [("msg_no_points", {})])
        table = pd.DataFrame({"SWOT": sampling_summary(vs[vs.source == "SWOT"].time),
                              "ICESat-2": sampling_summary(vs[vs.source == "ICESat-2"].time),
                              "all": sampling_summary(vs.time)})
        line = ("levels_line", dict(n_swot=n_swot, n_ice=n_ice, first=f"{vs.time.min():%Y-%m-%d}",
                                    last=f"{vs.time.max():%Y-%m-%d}", lo=vs.wse_m.min(), hi=vs.wse_m.max()))
        return Result(("h_levels", {}), [line], figure=lambda: plots.fig_levels(vs, self.site.short, self.xlim),
                      table=table, values=dict(swot=n_swot, icesat2=n_ice))

    # --- discharge -----------------------------------------------------------------------------------------
    def _reference(self, reference="auto"):
        if reference in self._ref:
            return self._ref[reference]
        q, src = None, None
        gf = self.site.gauge_file
        if reference in ("auto", "gauge") and gf.exists():
            g = load_gauge(gf)
            if g.discharge_m3s.notna().sum() > 30:
                q, src = g.discharge_m3s.dropna(), "gauge"
        if q is None and reference in ("auto", "geoglows") and self.site.geoglows_id:
            q, src = download.geoglows_daily(self.site.geoglows_id), "geoglows"
        self._ref[reference] = (q, src)
        return q, src

    def _bias_warning(self, q, src):
        """Warn when the model's mean flow is far from the published long-term mean · Modèle loin de la mesure"""
        pm = self.site.published_mean_m3s
        if src != "geoglows" or not pm:
            return None
        lo, hi = pm
        ratio = float(q.mean()) / ((lo + hi) / 2)
        if 1 / 1.5 <= ratio <= 1.5:
            return None
        return ("warn_model_bias", dict(model=fmt_int(round(float(q.mean()))), ratio=f"{ratio:.1f}",
                                        at=self.site.published_mean_at, lo=fmt_int(lo), hi=fmt_int(hi), key=self.site.key))

    @staticmethod
    def _src_label(src):
        return M("src_gauge") if src == "gauge" else M("src_geoglows")

    @_needs_data
    def reference_discharge(self, reference="auto"):
        q, src = self._reference(reference)
        if q is None:
            return Result(("h_reference", {}), [("msg_no_reference", dict(key=self.site.key))])
        lines = [("ref_line", dict(src=self._src_label(src), first=f"{q.index.min():%Y-%m-%d}",
                                   last=f"{q.index.max():%Y-%m-%d}"))]
        warnings = []
        if src == "geoglows":
            try:
                auto = download.geoglows_auto_lookup(self.site.lat, self.site.lon)
                lines.append(("ref_auto", dict(rid=auto["river_id"], mean=fmt_num(auto["mean_m3s"]))))
            except EXPECTED_ERRORS:
                pass
            lines.append(("ref_manual", dict(rid=self.site.geoglows_id, mean=fmt_num(q.mean()))))
            warnings.append(("ref_model_warning", {}))
            bias = self._bias_warning(q, src)
            if bias:
                warnings.append(bias)
        start = self.data.vs.time.min() - pd.Timedelta(days=60)
        return Result(("h_reference", {}), lines, warnings=warnings,
                      figure=lambda: plots.fig_reference(q, start, self._src_label(src)),
                      values=dict(source=src, mean_m3s=float(q.mean())))

    @_needs_data
    def rating(self, exclude_months=None, reference="auto", n_boot=None):
        """Fit Q = a·(h − h0)^b to the satellite levels · Ajuster la courbe de tarage.
        exclude_months: months (1–12) to leave out of the fit · mois à exclure de l'ajustement"""
        q, src = self._reference(reference)
        if q is None:
            self.current_rating = None
            return Result(("h_rating", {}), [("msg_no_reference", dict(key=self.site.key))])
        pairs = pair_with_reference(self.data.vs, q)
        dry = int((pairs.Q_ref <= 0).sum())
        pairs = pairs[pairs.Q_ref > 0]                       # a power curve cannot pass through zero flow
        excl = sorted(int(m) for m in (exclude_months or []))
        use, excluded = pairs[~pairs.month.isin(excl)], pairs[pairs.month.isin(excl)]
        if len(use) < 8:
            self.current_rating = None
            return Result(("h_rating", {}), [("msg_few_pairs", dict(n=len(use)))])
        p = fit_rating(use.wse_m, use.Q_ref)
        if not all(np.isfinite([p["a"], p["b"], p["h0"]])):
            self.current_rating = None
            return Result(("h_rating", {}), [("msg_fit_failed", dict(n=len(use)))])
        boot = bootstrap_rating(use.wse_m, use.Q_ref, n_boot=n_boot or self.params.n_boot, seed=self.params.seed)
        sk = skill(use.Q_ref, rating_q(use.wse_m, p))
        if excl:
            p_all = fit_rating(pairs.wse_m, pairs.Q_ref)
            table = pd.DataFrame({"all months": skill(pairs.Q_ref, rating_q(pairs.wse_m, p_all)),
                                  "fit months only": sk}).T
        else:
            table = sk.to_frame("fit").T
        self.current_rating = dict(p=p, src=src, exclude=excl, use=use, excluded=excluded, boot=boot, pairs=pairs, q=q)
        lines = [("rating_line", dict(a=p["a"], h0=p["h0"], b=p["b"], n=p["n"], src=self._src_label(src))),
                 ("rating_skill", dict(nse=sk["NSE"], kge=sk["KGE"]))]
        if len(boot):
            lines.append(("rating_b_band", dict(lo=boot.b.quantile(0.025), hi=boot.b.quantile(0.975))))
        if excl:
            lines.append(("rating_excluded", dict(months=_months(excl))))
        if dry:
            lines.append(("rating_dry", dict(n=dry)))
        warnings = []
        if p["b_at_bound"]:
            warnings.append(("warn_b_bound", {}))
        if p["edge"]:
            warnings.append(("warn_edge", {}))
        rec = self.site.recommended_exclude_months
        if src == "geoglows" and rec and not set(rec) <= set(excl):
            warnings.append(("warn_months", dict(months=rec)))
        bias = self._bias_warning(q, src)
        if bias:
            warnings.append(bias)
        return Result(("h_rating", {}), lines, warnings=warnings,
                      figure=lambda: plots.fig_rating(use, excluded, p, boot), table=table.round(3),
                      values=dict(p, nse=float(sk["NSE"]), kge=float(sk["KGE"]), source=src, exclude_months=excl))

    def _need_rating(self):
        if not self.current_rating:
            return Result(("h_rating", {}), [("msg_rating_first", {})])
        return None

    @_needs_data
    def residuals_by_month(self):
        r = self._need_rating() or None
        if r is not None:
            return r
        cr = self.current_rating
        bm = residuals_by_month(cr["pairs"], cr["p"])
        high = [m for m, v in bm["median"].items() if v > 20]
        low = [m for m, v in bm["median"].items() if v < -20]
        lines = []
        if high:
            lines.append(("resid_high", dict(months=_months(high))))
        if low:
            lines.append(("resid_low", dict(months=_months(low))))
        if not lines:
            lines.append(("resid_none", {}))
        return Result(("h_residuals", {}), lines, figure=lambda: plots.fig_residuals(bm), table=bm.round(0).T,
                      values=dict(high=high, low=low))

    @_needs_data
    def split_test(self, split="2025-01-01"):
        r = self._need_rating()
        if r is not None:
            return r
        res = split_sample(self.current_rating["use"], split)
        if res is None:
            return Result(("h_split", {}), [("split_short", dict(split=split))])
        p = res["rating"]
        lines = [("split_line", dict(n_train=res["n_train"], n_test=res["n_test"], split=split)),
                 ("rating_line", dict(a=p["a"], h0=p["h0"], b=p["b"], n=p["n"],
                                      src=self._src_label(self.current_rating["src"])))]
        warnings = [("warn_b_bound", {})] if p["b_at_bound"] else []
        return Result(("h_split", {}), lines, warnings=warnings, table=res["table"].round(3),
                      values=dict(test_nse=float(res["table"].loc["test", "NSE"]),
                                  test_pbias=float(res["table"].loc["test", "PBIAS %"])))

    def _flow(self):
        cr = self.current_rating
        vs = self.data.vs
        lo, hi = rating_band(vs.wse_m, cr["boot"])
        return vs.assign(Q_m3s=rating_q(vs.wse_m, cr["p"]), Q_lo=lo, Q_hi=hi)

    @_needs_data
    def discharge(self):
        r = self._need_rating()
        if r is not None:
            return r
        cr = self.current_rating
        flow = self._flow()
        q_span = cr["q"][flow.time.min() - pd.Timedelta(days=30):flow.time.max() + pd.Timedelta(days=30)]
        lines = [("discharge_line", dict(n=len(flow), mean=fmt_int(round(flow.Q_m3s.mean())),
                                         lo=fmt_int(round(flow.Q_m3s.min())), hi=fmt_int(round(flow.Q_m3s.max())))),
                 ("discharge_which", dict(src=self._src_label(cr["src"]), months=_months(cr["exclude"])))]
        bias = self._bias_warning(cr["q"], cr["src"])
        return Result(("h_discharge", {}), lines, warnings=[bias] if bias else [],
                      figure=lambda: plots.fig_discharge(flow, q_span, self._src_label(cr["src"]), self.site.short),
                      table=flow[["wse_m", "Q_m3s"]].describe().round(1).T,
                      values=dict(mean_m3s=float(flow.Q_m3s.mean())))

    @_needs_data
    def export(self, download=False):
        """Write outputs/<key>_virtual_gauge.csv (+ metadata) · Écrire le fichier de la station virtuelle"""
        d = self.data
        notes = {"icesat2_minus_swot_offset_m": round(float(d.offset), 3), "slope_m_per_km": round(float(d.slope), 4),
                 "params": vars(self.params)}
        lines = []
        if self.current_rating:
            cr = self.current_rating
            flow = self._flow()
            notes.update({"reference_discharge": cr["src"], "excluded_months": cr["exclude"],
                          "Q_band": "2.5–97.5 % bootstrap of the rating curve only"})
            bias = self._bias_warning(cr["q"], cr["src"])
            if bias:
                from .i18n import _pair
                notes["warning"] = _pair(*bias)[0]
            f, mf = export_virtual_gauge(self.site, flow, cr["p"], extra=notes)
        else:
            f, mf = export_virtual_gauge(self.site, d.vs, None, extra=notes)
            lines.append(("export_levels_only", {}))
        lines += [("export_line", dict(path=str(f))), ("export_line", dict(path=str(mf)))]
        if download:
            try:
                from google.colab import files  # only on Colab
                files.download(str(f))
            except ImportError:
                pass
        return Result(("h_export", {}), lines, values=dict(csv=str(f), metadata=str(mf)))

    # --- comparisons ----------------------------------------------------------------------------------------
    @_needs_data
    def compare_reaches(self):
        series = {}
        for label, rid in (self.site.compare or {}).items():
            if rid == self.site.swot_reach:
                series[label] = self.data.swot_main
            elif rid in self.data.swot:
                series[label] = self.data.swot[rid]
            else:
                series[label] = clean_swot(download.hydrocron_reach(rid), h_range=self.site.h_range,
                                           max_reach_q=self.params.max_reach_q, max_xovr_q=self.params.max_xovr_q)
        lines = []
        for label, d in series.items():
            k = d[d.reason == "kept"]
            if len(k):
                lines.append(("compare_line", dict(label=label, n=len(k), lo=k.wse.min(), hi=k.wse.max())))
        return Result(("h_compare_reaches", {}), lines,
                      figure=lambda: plots.fig_compare_reaches(series, self.site.short) if series else None)

    def removal_counts(self):
        rows = []
        for sat, df in [("ICESat-2", self.data.points), ("SWOT", self.data.swot_main)]:
            vc = df.reason[~df.reason.str.startswith("0")].value_counts()
            for reason, n in vc.items():
                rows.append(dict(satellite=sat, reason=reason, label=f"{sat}: {reason_label(reason)}", count=int(n)))
        return pd.DataFrame(rows)


def build_station(site, verbose=False, **settings_):
    """Build a virtual station · Construire une station virtuelle.

    site : a ready-made key (see vg.sites()), an 11-digit SWOT reach ID, or a vg.Site
           une clé prête (voir vg.sites()), un identifiant SWOT à 11 chiffres, ou un vg.Site
    other keywords change settings, e.g. slope_correction=False, max_cloud=5, tol_m=1.0
    """
    try:
        if isinstance(site, str) and site.strip().isdigit() and not settings.offline():
            info = f"swot_reach_{site.strip()}_info.csv"
            if not ((settings.cache_dir() / info).exists() or store.bundled_path(info)):
                say("msg_online_needed")
        s, params = resolve(site, **settings_)
    except EXPECTED_ERRORS as e:
        from .sites import Site
        s = Site(key=str(site), name=str(site), lat=0, lon=0, swot_reach=str(site))
        return Station(s, None, error=getattr(e, "msg", None) or str(e))
    if verbose:
        say("msg_building", site=s.short)
    loaders = dict(reach_line=download.reach_line, fetch_atl13=download.fetch_atl13,
                   hydrocron_reach=download.hydrocron_reach)
    try:
        data = build_virtual_station(s, params, loaders)
    except EXPECTED_ERRORS as e:
        return Station(s, params, error=getattr(e, "msg", None) or str(e))
    origin = store.ORIGINS.get(f"atl13_{s.key}.parquet", {})
    return Station(s, params, data, origin=origin)


def flood_catch(*stations):
    """How many floods of each length would the satellites see? · Combien de crues de chaque durée ?"""
    cols, chart = {}, {}
    for st in stations:
        if st.error or len(st.data.vs) == 0:
            continue
        vs = st.data.vs
        swot = vs[vs.source == "SWOT"]
        start = swot.time.min() if len(swot) else vs.time.min()
        end = vs.time.max()
        if len(swot):
            cols[f"{st.site.short}: SWOT"] = catch_probability(swot.time, start, end)
        cols[f"{st.site.short}: SWOT + ICESat-2"] = catch_probability(vs.time, start, end)
        chart[st.site.short] = cols[f"{st.site.short}: SWOT + ICESat-2"]
    table = pd.DataFrame(cols)
    chart = pd.DataFrame(chart)
    shown = (table * 100).round(0)
    shown.index = [f"{d} d · j" for d in shown.index]
    return Result(("h_flood_catch", {}), [("catch_line", {})],
                  figure=(lambda: plots.fig_flood_catch(chart)) if len(chart.columns) else None,
                  table=table, display_table=lambda: shown.T,
                  values={c: dict(table[c]) for c in table.columns})
