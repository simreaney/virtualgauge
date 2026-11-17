// A GeoPackage (the SQLite file QGIS and ArcGIS open) written in the browser with sql.js, from the index shown on
// the page: a layer of reaches (lines), a layer of ports (points) and the QGIS style that src/virtualgauge/geopackage.py
// writes, so the file opens like the one from congo.download_geopackage(). No page code here: it also runs under
// node (tests/navigability_gpkg_check.mjs).

const WGS84 = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],'
  + 'AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,'
  + 'AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST],AUTHORITY["EPSG","4326"]]';

const q = (name) => `"${String(name).replace(/"/g, '""')}"`;
const iso = (t) => (t == null ? null : new Date(t * 1000).toISOString());

/** GeoPackage geometry: a small header (with the bounding box for lines), then little-endian WKB. */
function geometry(kind, coords) {
  if (kind === "Point") {
    const b = new DataView(new ArrayBuffer(8 + 21));
    b.setUint8(0, 0x47); b.setUint8(1, 0x50); b.setUint8(2, 0); b.setUint8(3, 0b1);   // "GP", version 0, LE, no box
    b.setInt32(4, 4326, true);
    b.setUint8(8, 1); b.setUint32(9, 1, true); b.setFloat64(13, coords[0], true); b.setFloat64(21, coords[1], true);
    return new Uint8Array(b.buffer);
  }
  const parts = coords;                                               // MultiLineString: [[[x, y], …], …]
  const size = 8 + 32 + 9 + parts.reduce((n, p) => n + 9 + 16 * p.length, 0);
  const b = new DataView(new ArrayBuffer(size));
  const box = bbox(parts.flat());
  b.setUint8(0, 0x47); b.setUint8(1, 0x50); b.setUint8(2, 0); b.setUint8(3, 0b11);    // LE, box [minx maxx miny maxy]
  b.setInt32(4, 4326, true);
  [box[0], box[2], box[1], box[3]].forEach((v, k) => b.setFloat64(8 + 8 * k, v, true));
  let o = 40;
  b.setUint8(o, 1); b.setUint32(o + 1, 5, true); b.setUint32(o + 5, parts.length, true); o += 9;
  for (const p of parts) {
    b.setUint8(o, 1); b.setUint32(o + 1, 2, true); b.setUint32(o + 5, p.length, true); o += 9;
    for (const [x, y] of p) { b.setFloat64(o, x, true); b.setFloat64(o + 8, y, true); o += 16; }
  }
  return new Uint8Array(b.buffer);
}

function bbox(points) {
  let [minx, miny, maxx, maxy] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [x, y] of points) {
    if (x < minx) minx = x; if (x > maxx) maxx = x;
    if (y < miny) miny = y; if (y > maxy) maxy = y;
  }
  return [minx, miny, maxx, maxy];
}

/**
 * The file as bytes. layers: [{name, kind: "MultiLineString" | "Point", description, fields: [[name, type], …],
 * rows: [{geom, values: […]}]}]; styles: [{table, qml}] (QGIS opens a layer with its style).
 */
export function writeGeoPackage(SQL, layers, styles = []) {
  const db = new SQL.Database();
  const now = new Date().toISOString();
  db.exec(`
    PRAGMA application_id = 1196444487;
    PRAGMA user_version = 10200;
    CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY,
      organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT);
    CREATE TABLE gpkg_contents (table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL, identifier TEXT UNIQUE,
      description TEXT DEFAULT '', last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER,
      CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id));
    CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL, column_name TEXT NOT NULL,
      geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL,
      CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name), CONSTRAINT uk_gc_table_name UNIQUE (table_name),
      CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
      CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys (srs_id));`);
  const srs = db.prepare("INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)");
  srs.run(["Undefined cartesian SRS", -1, "NONE", -1, "undefined", "undefined cartesian coordinate reference system"]);
  srs.run(["Undefined geographic SRS", 0, "NONE", 0, "undefined", "undefined geographic coordinate reference system"]);
  srs.run(["WGS 84 geodetic", 4326, "EPSG", 4326, WGS84, "longitude/latitude coordinates in decimal degrees on the WGS 84 spheroid"]);
  srs.free();

  db.exec("BEGIN");
  for (const layer of layers) {
    const cols = layer.fields.map(([name, type]) => `${q(name)} ${type}`).join(", ");
    db.exec(`CREATE TABLE ${q(layer.name)} (fid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, geom ${layer.kind.toUpperCase()}, ${cols})`);
    const ins = db.prepare(`INSERT INTO ${q(layer.name)} (geom, ${layer.fields.map(([n]) => q(n)).join(", ")}) `
                           + `VALUES (${Array(layer.fields.length + 1).fill("?").join(", ")})`);
    const points = [];
    for (const row of layer.rows) {
      const has = row.geom && (layer.kind === "Point" || row.geom.length);
      if (has) points.push(...(layer.kind === "Point" ? [row.geom] : row.geom.flat()));
      ins.run([has ? geometry(layer.kind, row.geom) : null, ...row.values.map((v) => (typeof v === "boolean" ? Number(v) : v ?? null))]);
    }
    ins.free();
    const box = points.length ? bbox(points) : [null, null, null, null];
    db.run("INSERT INTO gpkg_contents (table_name, data_type, identifier, description, last_change, min_x, min_y, max_x, max_y, srs_id) "
           + "VALUES (?, 'features', ?, ?, ?, ?, ?, ?, ?, 4326)", [layer.name, layer.name, layer.description || "", now, ...box]);
    db.run("INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', ?, 4326, 0, 0)", [layer.name, layer.kind.toUpperCase()]);
  }
  if (styles.length) {                                     // the table QGIS itself writes when it saves a style
    db.exec(`CREATE TABLE layer_styles (id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT(256),
      f_table_schema TEXT(256), f_table_name TEXT(256), f_geometry_column TEXT(256), styleName TEXT(30), styleQML TEXT,
      styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT(30), ui TEXT(30), update_time DATETIME)`);
    for (const s of styles) {
      db.run("INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name, f_geometry_column, styleName, "
             + "styleQML, styleSLD, useAsDefault, description, owner, ui, update_time) VALUES ('', '', ?, 'geom', ?, ?, '', 1, "
             + "'virtualgauge', '', '', ?)", [s.table, `${s.table} (virtualgauge)`, s.qml, now]);
    }
    db.run("INSERT INTO gpkg_contents (table_name, data_type, identifier, description, last_change) "
           + "VALUES ('layer_styles', 'attributes', 'layer_styles', '', ?)", [now]);
  }
  db.exec("COMMIT");
  const bytes = db.export();
  db.close();
  return bytes;
}

/**
 * The page's reaches and ports as GeoPackage layers. reaches: the page's reach objects (with .now, the index on the
 * map); words(key, vars): the page's words in the chosen language; lang: "en" or "fr".
 */
export function navigabilityLayers(data, reaches, words, lang, isNew = () => false) {
  const label = (r) => (r.now.band >= 0 ? data.bands[r.now.band].label[lang]
                                        : words(`why.${r.now.why}`, { days: data.params.max_age_days }));
  const round = (v, nd) => (v == null || !Number.isFinite(v) ? null : Math.round(v * 10 ** nd) / 10 ** nd);
  const segments = (line) => {
    const out = [];
    for (let k = 0; k < line.length; k += 4) out.push([[line[k], line[k + 1]], [line[k + 2], line[k + 3]]]);
    return out;
  };
  const reachRows = reaches.map((r) => {
    const n = r.now, has = n.band >= 0, range = r.low != null && r.high != null ? r.high - r.low : null;
    return {
      geom: segments(r.line),
      values: [Number(r.id), r.river, round(r.lat, 5), round(r.lon, 5), r.width, r.km, r.n, r.low, iso(r.lowT), r.high,
               iso(r.highT), round(range, 3), n.t != null ? n.wse : null, iso(n.t ?? null), round(n.age ?? null, 1),
               has ? round(n.index, 1) : null, n.band, label(r), n.why || "",
               has ? data.bands[n.band].colour : data.no_index_colour, isNew(r)],
    };
  });
  const byId = new Map(reaches.map((r) => [r.id, r]));
  const portRows = data.ports.filter((p) => byId.has(p.reach_id)).map((p) => {
    const r = byId.get(p.reach_id), n = r.now, has = n.band >= 0;
    return { geom: [p.lon, p.lat],
             values: [p.name, p.river, Number(p.reach_id), has ? round(n.index, 1) : null, label(r),
                      n.t != null ? n.wse : null, iso(n.t ?? null), r.low != null && r.high != null ? round(r.high - r.low, 3) : null] };
  });
  return [
    { name: "reaches", kind: "MultiLineString", description: "SWOT river reaches with their navigability index",
      fields: [["reach_id", "INTEGER"], ["river_name", "TEXT"], ["lat", "REAL"], ["lon", "REAL"], ["width_m", "REAL"],
               ["length_km", "REAL"], ["n_good", "INTEGER"], ["low_m", "REAL"], ["low_date", "DATETIME"], ["high_m", "REAL"],
               ["high_date", "DATETIME"], ["range_m", "REAL"], ["now_m", "REAL"], ["now_date", "DATETIME"],
               ["age_days", "REAL"], ["index", "REAL"], ["band", "INTEGER"], ["band_name", "TEXT"], ["why", "TEXT"],
               ["colour", "TEXT"], ["new_level", "BOOLEAN"]],
      rows: reachRows },
    { name: "ports", kind: "Point", description: "River ports and the index of their reach",
      fields: [["name", "TEXT"], ["river", "TEXT"], ["reach_id", "INTEGER"], ["index", "REAL"], ["band_name", "TEXT"],
               ["now_m", "REAL"], ["now_date", "DATETIME"], ["range_m", "REAL"]],
      rows: portRows },
  ];
}
