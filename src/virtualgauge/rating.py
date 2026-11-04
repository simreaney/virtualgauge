"""Step 7: rating curve Q = a·(h − h0)^b · Étape 7 : courbe de tarage.

Copied from the trainer notebook (Step 7 cells). Helpers `pair_with_reference`, `residuals_by_month` and
`split_sample` collect code that the trainer wrote inline in its cells.
"""
import numpy as np
import pandas as pd


def fit_rating(h, q, b_bounds=(1.0, 3.5), h0_search_m=25.0, n_grid=2000):
    """Fit Q = a·(h − h0)^b: try many h0 values, fit a straight line in log space for each, keep the best.
    Ajuster Q = a·(h − h0)^b : essayer de nombreux h0, ajuster une droite en log pour chacun, garder le meilleur."""
    h, q = np.asarray(h, float), np.asarray(q, float)
    y = np.log(q)
    h0 = np.linspace(h.min() - h0_search_m, h.min() - 0.05, n_grid)
    X = np.log(h[None, :] - h0[:, None])
    xm, ym = X.mean(1, keepdims=True), y.mean()
    b = np.clip(((X - xm) * (y - ym)).sum(1) / ((X - xm) ** 2).sum(1), *b_bounds)
    loga = ym - b * xm[:, 0]
    sse = ((loga[:, None] + b[:, None] * X - y) ** 2).sum(1)
    i = int(np.argmin(sse))
    return dict(a=float(np.exp(loga[i])), h0=float(h0[i]), b=float(b[i]), n=len(h),
                edge=bool(i in (0, n_grid - 1)), b_at_bound=bool(b[i] in b_bounds))


def rating_q(h, p):
    """Discharge from level with rating parameters p · Débit à partir du niveau"""
    h = np.asarray(h, float)
    return np.where(h > p["h0"], p["a"] * np.clip(h - p["h0"], 0, None) ** p["b"], 0.0)


def bootstrap_rating(h, q, n_boot=500, seed=1, **kw):
    """Refit the curve on resampled pairs to see how uncertain it is · Réajuster sur des tirages pour l'incertitude"""
    rng = np.random.default_rng(seed)
    h, q = np.asarray(h, float), np.asarray(q, float)
    out = []
    for _ in range(n_boot):
        i = rng.integers(0, len(h), len(h))
        if np.unique(h[i]).size >= 5:
            out.append(fit_rating(h[i], q[i], **kw))
    return pd.DataFrame(out)


def rating_band(h, boot, lo=2.5, hi=97.5):
    Q = np.array([rating_q(h, p) for p in boot.to_dict("records")])
    return np.percentile(Q, lo, axis=0), np.percentile(Q, hi, axis=0)


def skill(obs, sim):
    """Agreement statistics · Statistiques d'accord (r, NSE, KGE, RMSE, PBIAS)"""
    obs, sim = np.asarray(obs, float), np.asarray(sim, float)
    r = np.corrcoef(obs, sim)[0, 1]
    nse = 1 - np.sum((sim - obs) ** 2) / np.sum((obs - obs.mean()) ** 2)
    kge = 1 - np.sqrt((r - 1) ** 2 + (sim.std() / obs.std() - 1) ** 2 + (sim.mean() / obs.mean() - 1) ** 2)
    return pd.Series({"n": len(obs), "r": r, "NSE": nse, "KGE": kge,
                      "RMSE": np.sqrt(np.mean((sim - obs) ** 2)), "PBIAS %": 100 * np.sum(sim - obs) / np.sum(obs)})


def quantile_pairs(levels, q_series, probs=np.linspace(0.05, 0.95, 19)):
    """Pair level and discharge quantiles · Associer les quantiles de niveau et de débit"""
    return pd.DataFrame({"wse_m": np.quantile(levels, probs), "Q_ref": np.quantile(q_series.dropna(), probs),
                         "source": "quantiles"})


def pair_with_reference(vs, q_ref):
    """Reference discharge on each satellite day (trainer Step 7) · Débit de référence pour chaque date satellitaire"""
    p = vs.assign(Q_ref=vs.time.dt.normalize().map(q_ref)).dropna(subset=["Q_ref"]).reset_index(drop=True)
    p["month"] = p.time.dt.month
    return p


def residuals_by_month(pairs_q, p):
    """Median (reference − curve) / curve in %, by month · Résidu médian par mois (%)"""
    pred = rating_q(pairs_q.wse_m, p)
    res = 100 * (pairs_q.Q_ref - pred) / pred
    return (pairs_q.assign(residual_pct=res).groupby("month").residual_pct.agg(["median", "count"])
            .reindex(range(1, 13)))


def split_sample(use, split, **kw):
    """Fit before `split`, test after (trainer Step 7) · Calage avant `split`, test après"""
    split = pd.Timestamp(split)
    train, test = use[use.time < split], use[use.time >= split]
    if len(train) < 10 or len(test) < 5:
        return None
    p = fit_rating(train.wse_m, train.Q_ref, **kw)
    table = pd.DataFrame({"train": skill(train.Q_ref, rating_q(train.wse_m, p)),
                          "test": skill(test.Q_ref, rating_q(test.wse_m, p))}).T
    return dict(rating=p, table=table, n_train=len(train), n_test=len(test))
