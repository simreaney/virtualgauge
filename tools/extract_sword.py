import sys, os, time, shutil
sys.path.insert(0, os.path.dirname(__file__))
from httpzip import open_zip
import pyogrio, pandas as pd
out = sys.argv[1]
z = open_zip('https://zenodo.org/api/records/15299138/files/SWORD_v17b_gpkg.zip/content')
for cont in ["af", "oc", "eu", "sa", "na", "as"]:
    slim = f"{out}/{cont}_reaches_slim.parquet"
    if os.path.exists(slim): print(cont, "done already", flush=True); continue
    t = time.time(); name = f"gpkg/{cont}_sword_reaches_v17b.gpkg"; dst = f"{out}/{cont}.gpkg"
    with z.open(name) as src, open(dst, "wb") as f: shutil.copyfileobj(src, f, 8 << 20)
    info = pyogrio.read_info(dst); cols = list(info["fields"])
    print(cont, "fields:", cols, flush=True)
    keep = [c for c in ["reach_id", "x", "y", "width", "river_name", "type", "reach_len", "n_rch_up", "n_rch_dn", "rch_id_up", "rch_id_dn", "facc", "wse"] if c in cols]
    df = pyogrio.read_dataframe(dst, columns=keep, read_geometry=False)
    df["continent"] = cont
    df.to_parquet(slim); os.remove(dst)
    print(cont, len(df), "reaches", round(time.time() - t), "s", flush=True)
print("ALL DONE", flush=True)
