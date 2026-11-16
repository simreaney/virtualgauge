// Runs the page's index rules (docs/navigability/core.js) on cases from stdin; used by test_navigability_site.py
import { readFileSync } from "node:fs";
import { parseLevels, screen, judge, indexAt } from "../docs/navigability/core.js";

const { params, now, cases } = JSON.parse(readFileSync(0, "utf8"));
const out = cases.map((c) => {
  const levels = judge(c.saved, screen(parseLevels(c.csv), c, params), c, params, c.start);
  const at = indexAt(levels, c.low, c.high, now, params.max_age_days);
  return { kept: levels.filter((l) => l[0] >= c.start), index: at.index, t: at.t ?? null };
});
process.stdout.write(JSON.stringify(out));
