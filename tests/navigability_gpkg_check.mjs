// Writes the web page's GeoPackage (docs/navigability/gpkg.js) from the page's data, with the index on the day of the
// snapshot; used by test_navigability_site.py.   node tests/navigability_gpkg_check.mjs out.gpkg [en|fr]
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { indexAt, unpack } from "../docs/navigability/core.js";
import { translator } from "../docs/navigability/i18n.js";
import { navigabilityLayers, writeGeoPackage } from "../docs/navigability/gpkg.js";

const [out, lang = "en"] = process.argv.slice(2);
const site = (p) => fileURLToPath(new URL(`../docs/navigability/${p}`, import.meta.url));
const data = JSON.parse(readFileSync(site("data/congo.json"), "utf8"));
const styles = JSON.parse(readFileSync(site("data/qgis.json"), "utf8"));
const initSqlJs = createRequire(import.meta.url)(site("vendor/sql.js/sql-wasm.js"));
const SQL = await initSqlJs({ locateFile: (f) => site(`vendor/sql.js/${f}`) });

const reaches = unpack(data);
for (const r of reaches) {
  r.now = r.why ? { index: null, band: -1, why: r.why }
                : indexAt(r.levels, r.low, r.high, data.as_of_t, data.params.max_age_days);
}
const bytes = writeGeoPackage(SQL, navigabilityLayers(data, reaches, translator(lang), lang),
                              [{ table: "reaches", qml: styles.reaches[lang] }, { table: "ports", qml: styles.ports }]);
writeFileSync(out, bytes);
