"""The navigability web page (docs/navigability/) judges new SWOT levels in JavaScript. Check that it keeps the same
levels and gives the same index as the package, on the survey shipped with the package (needs node; no internet)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
DAYS = 60                # the levels of the last 60 days of the record are given to the page as 'new'


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_page_rules_match_package():
    import virtualgauge as vg
    import build_navigability_site as site
    from virtualgauge import navigation

    vg.set_language("en")
    survey = vg.river_survey("congo", download=False)
    assert not survey.error
    data = site.build(survey)
    r = data["reaches"]
    lv = survey.levels.assign(s=survey.levels.time.astype("datetime64[s]").astype("int64"))
    end = int(lv.s.max())
    start = (end - DAYS * 86400) // 86400 * 86400
    kept = lv[lv.reason == "kept"]
    old = {rid: g[["s", "wse"]].to_numpy().tolist() for rid, g in kept[kept.s < start].groupby("reach_id")}
    new = lv[lv.s >= start].assign(time_str=lambda d: d.time.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    cols = ["reach_id", "time_str", "wse", "reach_q", "xovr_cal_q", "dark_frac"]
    csv = {rid: g[cols].to_csv(index=False) for rid, g in new.groupby("reach_id")}
    cases, ids = [], []
    for i, rid in enumerate(r["id"]):
        if r["why"][i] == 0:
            ids.append(int(rid))
            cases.append(dict(median=r["median"][i], far=r["far"][i], jump=r["jump"][i], low=r["low"][i], high=r["high"][i],
                              saved=[[int(a), b] for a, b in old.get(int(rid), [])[-site.N_RECENT:]],
                              csv=csv.get(int(rid), ""), start=start))
    job = json.dumps(dict(params=data["params"], now=end, cases=cases))
    res = subprocess.run(["node", str(ROOT / "tests" / "navigability_site_check.mjs")], input=job, capture_output=True,
                         text=True, check=True)
    page = json.loads(res.stdout)

    want = {rid: g.s.tolist() for rid, g in kept[kept.s >= start].groupby("reach_id")}
    same = sum([a for a, _ in p["kept"]] == want.get(rid, []) for rid, p in zip(ids, page))
    # a few levels differ: the page sees only the good levels before the new ones, the package also the removed ones
    assert same / len(ids) > 0.99, f"{len(ids) - same} of {len(ids)} reaches keep other levels"

    now = navigation.index_at(survey.table, survey.levels, pd.Timestamp(end, unit="s"), survey.params)["index"]
    theirs = np.array([np.nan if p["index"] is None else p["index"] for p in page])
    ours = now.reindex(ids).to_numpy()
    assert (np.isnan(theirs) == np.isnan(ours)).mean() > 0.995
    both = ~np.isnan(theirs) & ~np.isnan(ours)
    assert (np.abs(theirs - ours)[both] < 0.5).mean() > 0.995
    print(f"{same}/{len(ids)} reaches keep the same levels; index within 0.5 on "
          f"{(np.abs(theirs - ours)[both] < 0.5).sum()}/{both.sum()}")
