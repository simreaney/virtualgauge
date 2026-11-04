"""Interactive exploration with widgets · Exploration interactive avec des widgets."""
from .i18n import get_language, set_language, t
from .rating import residuals_by_month
from .style import to_png
from . import plots


def explore(site="congo_kinshasa"):
    """Change the settings and watch the results update · Modifier les réglages et voir les résultats changer."""
    import ipywidgets as W
    from IPython.display import HTML, Image, clear_output, display
    from .sites import PRESETS
    from .station import build_station

    wide = {"description_width": "initial"}
    dd = W.Dropdown(options=[(s.short, k) for k, s in PRESETS.items()], value=site, description=t("w_site"), style=wide)
    lang = W.ToggleButtons(options=[("EN", "en"), ("FR", "fr"), ("EN+FR", "both")], value=get_language(),
                           description=t("w_language"), style=wide)
    cloud = W.IntSlider(2, 0, 5, description=t("w_cloud"), continuous_update=False, style=wide)
    kmad = W.FloatSlider(3.0, min=1.5, max=8.0, step=0.5, description=t("w_kmad"), continuous_update=False, style=wide)
    slope = W.Checkbox(True, description=t("w_slope"), style=wide)
    reachq = W.IntSlider(1, 0, 3, description=t("w_reachq"), continuous_update=False, style=wide)
    tol = W.FloatSlider(0.3, min=0.1, max=3.0, step=0.1, description=t("w_tol"), continuous_update=False, style=wide)
    neigh = W.Checkbox(True, description=t("w_neigh"), style=wide)
    months = [W.ToggleButton(value=True, description=str(m), layout=W.Layout(width="44px")) for m in range(1, 13)]
    reset = W.Button(description=t("w_reset"))
    info = W.HTML()
    out = W.Output()
    memo = {}
    busy = {"value": False}

    def station():
        key = (dd.value, cloud.value, kmad.value, slope.value, reachq.value, neigh.value, tol.value)
        if key not in memo:
            memo[key] = build_station(dd.value, max_cloud=cloud.value, k_mad=kmad.value, slope_correction=slope.value,
                                      max_reach_q=reachq.value, neighbour_check=neigh.value, tol_m=tol.value)
        return memo[key]

    def defaults_for_site():
        s = PRESETS[dd.value]
        busy["value"] = True
        slope.value = s.slope_correction
        for i, b in enumerate(months):
            b.value = (i + 1) not in (s.recommended_exclude_months or [])
            b.disabled = not s.geoglows_id
        busy["value"] = False

    def update(*_):
        if busy["value"]:
            return
        set_language(lang.value)
        st = station()
        with out:
            clear_output(wait=True)
            if st.error:
                display(st)
                return
            excl = [i + 1 for i, b in enumerate(months) if not b.value]
            cr = None
            if PRESETS[dd.value].geoglows_id or st.site.gauge_file.exists():
                st.rating(exclude_months=excl, n_boot=200)
                cr = st.current_rating
            fig = plots.fig_dashboard(st, cr["p"] if cr else None,
                                      residuals_by_month(cr["pairs"], cr["p"]) if cr else None,
                                      cr["use"] if cr else None, cr["excluded"] if cr else None,
                                      cr["boot"] if cr else None)
            display(Image(to_png(fig)))
        vs = st.data.vs
        rtxt = f" · b = {cr['p']['b']:.2f} · n = {cr['p']['n']} {t('w_boot_note')}" if cr else ""
        info.value = "<b>" + t("w_numbers", n_swot=int((vs.source == "SWOT").sum()),
                               n_ice=int((vs.source == "ICESat-2").sum()), offset=st.data.offset,
                               cm=st.data.slope * 100, rating=rtxt) + "</b>"

    def on_site(_):
        defaults_for_site()
        update()

    def on_reset(_):
        busy["value"] = True
        cloud.value, kmad.value, reachq.value, tol.value, neigh.value = 2, 3.0, 1, 0.3, True
        busy["value"] = False
        defaults_for_site()
        update()

    dd.observe(on_site, names="value")
    for w in [lang, cloud, kmad, slope, reachq, tol, neigh] + months:
        w.observe(update, names="value")
    reset.on_click(on_reset)
    defaults_for_site()
    ui = W.VBox([W.HBox([dd, lang]),
                 W.HBox([W.VBox([cloud, kmad, slope]), W.VBox([reachq, tol, neigh])]),
                 W.HTML(f"<i>{t('w_months')}</i>"), W.HBox(months), reset, info, out])
    update()
    return ui


def explore_locations():
    """Pick a ready-made site or type any SWOT reach ID, then Build · Choisir un site ou taper un identifiant SWOT."""
    import ipywidgets as W
    from IPython.display import clear_output, display
    from .sites import PRESETS
    from .station import build_station

    wide = {"description_width": "initial"}
    dd = W.Dropdown(options=[("—", "")] + [(s.short, k) for k, s in PRESETS.items()], value="",
                    description=t("w_site"), style=wide)
    txt = W.Text(placeholder="13217000081", description=t("w_reach"), style=wide)
    btn = W.Button(description=t("w_build"), button_style="primary")
    out = W.Output()

    def go(_):
        target = txt.value.strip() or dd.value
        if not target:
            return
        with out:
            clear_output()
            print(t("w_busy"))
            st = build_station(target)
            clear_output(wait=True)
            display(st)
            if not st.error:
                display(st.map())
                display(st.levels())

    btn.on_click(go)
    return W.VBox([W.HBox([dd, txt, btn]), out])
