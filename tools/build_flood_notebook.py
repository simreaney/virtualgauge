"""Build the flood-mapping student notebook (English only, results first, one line of code per step).

Usage: python tools/build_flood_notebook.py [output.ipynb]
"""
import sys
from pathlib import Path

import nbformat as nbf

cells = []
HIDE = {"jupyter": {"source_hidden": True}, "cellView": "form", "tags": ["hide-input"]}
NAME = "SWOT_Flood_Depth_Student.ipynb"


def md(title, text, level=2):
    s = f"{'#' * level} {title}\n\n" if title else ""
    cells.append(nbf.v4.new_markdown_cell(s + text.strip()))


_num = {"part": 0, "sec": 0, "parts": []}


def part(title, text):
    """A numbered part: 'Part 3 — …'"""
    _num["part"] += 1
    _num["sec"] = 0
    _num["parts"].append((_num["part"], title))
    md(f"Part {_num['part']} — {title}", text)


def section(title, text=""):
    """A numbered section inside the current part: '3.2 …'"""
    _num["sec"] += 1
    head = f"{_num['part']}.{_num['sec']} {title}"
    if text:
        md(head, text, level=3)
    else:
        cells.append(nbf.v4.new_markdown_cell(f"### {head}"))


def ask(questions):
    """'What do you notice?' questions"""
    md(None, "💬 **What do you notice?**\n\n" + "\n".join(f"- {q}" for q in questions))


def code(src, hidden=False):
    c = nbf.v4.new_code_cell(src.strip())
    if hidden:
        c.metadata.update(HIDE)
    cells.append(c)


# ------------------------------------------------------------------------------------------------------------------
cells.append(nbf.v4.new_markdown_cell(rf"""
# Mapping a flood with SWOT — student notebook

**Draw an area, choose a flood, and see what the SWOT satellite measured before and after it: where the water spread,
how much it rose, and how deep it was.**

**Start here:** menu **Run ▸ Run all** (Colab: **Runtime ▸ Run all**), then read from the top.

Parts 1–4 use real SWOT data for two floods — the **Congo at Kinshasa–Brazzaville** (2023–24) and the
**Okavango Delta** in Botswana (2025) — shipped with the `virtualgauge` package, so they work offline and need no
account. Part 5 maps a flood of your choice: it needs the internet and a free NASA Earthdata login. About 90 minutes.

✏️ a line you can change — 🧪 try it — 💬 questions to discuss

{{CONTENTS}}

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/simreaney/virtualgauge/blob/main/{NAME})
"""))

code(r'''
#@title Setup { display-mode: "form" }
import glob, importlib, importlib.util, subprocess, sys
from importlib.metadata import PackageNotFoundError, version


def _needs_install():
    try:
        major, minor = map(int, version("virtualgauge").split(".")[:2])
    except PackageNotFoundError:
        return True
    extras = ("earthaccess", "xarray", "h5netcdf", "rasterio")
    return (major, minor) < (0, 2) or any(importlib.util.find_spec(m) is None for m in extras)


if _needs_install():                      # install once (Colab / new computer)
    REPO_URL = "https://github.com/simreaney/virtualgauge"
    wheel = sorted(glob.glob("virtualgauge-*.whl"))
    for source in ([f"{wheel[-1]}[flood]", wheel[-1]] if wheel else
                   [f"virtualgauge[flood] @ git+{REPO_URL}", f"git+{REPO_URL}"]):
        print(f"Installing: {source}")
        pip = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", source],
                             capture_output=True, text=True)
        if pip.returncode == 0:
            break
    importlib.invalidate_caches()
    if pip.returncode != 0:
        print((pip.stderr or pip.stdout)[-1500:])
        raise RuntimeError("Could not install virtualgauge. Upload the virtualgauge-*.whl file (Files panel) "
                           "and run this cell again.")
import virtualgauge as vg
vg.set_language("en")
print(f"virtualgauge {vg.__version__} — ready")
''', hidden=True)

# ------------------------------------------------------------------------------------------------------------------
part("How SWOT sees a flood", """
**SWOT** (Surface Water and Ocean Topography, NASA and CNES, launched December 2022) is a radar satellite that maps the
**height of water surfaces** in two dimensions. Four facts matter for flood mapping:

1. **Two swaths with a gap.** SWOT sees two strips, each 50 km wide, either side of its ground track. The 20 km strip
   straight under the satellite is **not seen**.
2. **Every 21 days.** Each track repeats every 21 days. With neighbouring tracks, most places are seen two to four
   times in 21 days (more often far from the equator).
3. **100 m cells.** We use the SWOT *raster* product: for every 100 m cell, how much of it is water (the
   *water fraction*) and the **water surface elevation** (WSE).
4. **Heights, not depths.** SWOT measures the water surface in metres above the **EGM2008 geoid** (≈ mean sea level).
   It cannot see the ground under the water.

So we compare a SWOT pass **before** the flood with a pass **after** (or during) it, and for the depth we need the
height of the ground from a **digital elevation model (DEM)**:

> **flood depth = water surface (SWOT, after) − ground (DEM)**
""")
ask(["A flood lasts 5 days. SWOT sees your area about once a week. Will it always see the flood?",
     "Why can SWOT not tell us the depth of a river that was already there before the flood — only how much it rose?",
     "The DEM and SWOT must use the same zero for heights. What happens to the depth if one is 2 m higher than the other?"])

# ------------------------------------------------------------------------------------------------------------------
part("The Congo at Kinshasa–Brazzaville, December 2023 – January 2024", """
At the end of 2023 the Congo rose to its highest level at Kinshasa–Brazzaville since 1961, and flooded low-lying parts
of both cities and the islands of the Malebo Pool. (In the virtual gauge notebook: *"something unusual happened at the
end of 2023"*.)
""")
section("The area", "One line defines the area — here a ready-made polygon around the Malebo Pool.")
code('kin = vg.flood_area("kinshasa_2024")\nkin')
md(None, "The white outline on the satellite image. Kinshasa is on the south bank, Brazzaville on the north bank. "
         "The pin is the SWOT river reach used as a virtual gauge in the other notebook.")
code("kin.map()")

section("When did SWOT look?", """
SWOT passes over the area, found in NASA's catalogue (no login needed). Top: the water level of the Congo measured by
SWOT at Kinshasa. Bottom: each pass, and how much of the area it saw.
""")
code("kin.passes()")
ask(["Two tracks pass over the area (111 and 570). Why do they see different shares of it?",
     "We compare pass 003_570 (21 September 2023, low water) with 008_570 (3 January 2024, near the peak). Why choose two passes on the same track?",
     "Could we have used 009_111 (8 January 2024) as the ‘after’ pass? What would we gain and what would we lose?"])

section("Before and after", """
A 100 m cell counts as **water** when at least half of it is water. Only the part of the area seen by **both** passes
can be compared.
""")
code('flood = vg.flood_event("kinshasa_2024")\nflood')
code("flood.extent()")
ask(["Where did the new flood water spread: into the cities, onto the islands, or along the river banks?",
     "What is the hatched strip, and how does it change the totals?",
     "Is there any ‘water gone’? What could make water disappear between low water and a flood peak?"])

section("Which water levels can we trust?", """
Each water cell has a SWOT water level with quality information. As in the virtual gauge notebook, every level that is
removed has a written reason: a bad quality flag, **dark water** (too little radar echo, e.g. very calm water or heavy
rain), **layover** (tall or steep things — buildings, banks, hills — that send the echo back early), ice, or a level that
differs from its neighbours.
""")
code("flood.cleaning()")
ask(["Where are most removed levels: in open water, at the water's edge, or in the city? Why?",
     "Which reason removes the most levels before the flood, and after it?"])

section("How much did the water rise?", """
Where there was water on both dates, the difference between the two SWOT levels is the **rise**. The dashed line is the
SWOT river level at the Kinshasa reach over the same dates — an independent check.
""")
code("flood.water_levels()")
ask(["Does the median rise agree with the river reach?",
     "Is the rise the same everywhere in the Pool? What could make it differ from place to place?"])

section("The ground", """
The ground is the **Copernicus GLO-30 DEM**, made from TanDEM-X radar images taken between 2011 and 2015, averaged from
30 m to our 100 m cells. Its heights are also above the EGM2008 geoid, so they can be subtracted from SWOT's.
""")
code("flood.ground()")
ask(["The ground under new flood water should be below the water surface. Is it, everywhere?",
     "Where could the DEM ‘ground’ be too high? (Think of what a radar sees over a city or a forest.)"])

section("Flood depth", """
SWOT levels are noisy from cell to cell (about ±10–30 cm), so by default the water surface is **averaged within
500 m** before the ground is subtracted.
""")
code("flood.depth()")
md(None, "🧪 Now use each cell's own SWOT level, with no averaging — and try other distances:")
code("flood.depth(smooth_m=0)   # ✏️ try 0, 250, 1000")
ask(["How do the median depth and the share of new flood water with a depth change without averaging? Why?",
     "What would trees or buildings in the DEM do to the depth?",
     "The volume is a rough number. Which errors push it up, and which push it down?"])

section("Summary, map and export")
code("flood.summary()")
md(None, "Use the layer button (top right) to switch between water before, after, what changed, and depth.")
code("flood.map()")
md(None, "Save the summary (CSV), the area (GeoJSON) and the maps (a GeoTIFF with class, depth, rise, water levels and "
         "ground — open it in QGIS) in the folder `outputs/`. On Colab use `flood.export(download=True)`.")
code("flood.export()")

# ------------------------------------------------------------------------------------------------------------------
part("The Okavango Delta, 2025", """
Every year, rain that falls on the Angolan highlands from November to March reaches Botswana as a slow flood. It enters
at Mohembo, flows down the Panhandle, and spreads into the Delta, where the flooded area is largest between May and
August. Here we compare low water (30 November 2024) with high water (27 June 2025) at the top of the Delta, near
Seronga — the same steps, on a very different landscape.
""")
code('oka = vg.flood_area("okavango_2025")\noka.passes()')
ask(["SWOT saw this area on track 514 every 21 days — except in May 2025. Look at the river level: what did we miss?",
     "Track 514 sees all of the area, the other two tracks less than half. Why might that be?"])
code('delta = vg.flood_event("okavango_2025")\ndelta.extent()')
ask(["How does the new flood water spread here, compared with Kinshasa?",
     "Much of the Delta is covered by reeds and papyrus. Can a radar see water under vegetation?"])
code("delta.cleaning()")
code("delta.depth()")
ask(["The Delta is very flat. If the DEM is 1 m too high or too low, what happens to the flooded depth — and to the volume?",
     "Compare the median depth and the share of ‘water below the ground’ with Kinshasa. Which result do you trust more, and why?"])
code("delta.summary()")

# ------------------------------------------------------------------------------------------------------------------
part("Change the settings", """
Every setting is a keyword of `vg.flood_event`. The data are already on your computer, so this is quick. Three tasks:

1. Make a cell count as water when only 30% of it is water (`min_water_frac=0.3`). How much does the flooded area change?
2. Keep degraded SWOT levels too (`max_wse_qual=2`). Which removed levels come back, and does the depth change?
3. For the Okavango, average the water surface over 1 km (`smooth_m=1000`). What happens to the depth map?
""")
code('vg.flood_event("kinshasa_2024", min_water_frac=0.3).extent()   # ✏️ 0.3 … 0.8')
code('vg.flood_event("kinshasa_2024", max_wse_qual=2).cleaning()   # ✏️ 0, 1, 2 or 3')
code('vg.flood_event("okavango_2025", smooth_m=1000).depth()   # ✏️')
md(None, "All the settings, with their default values:")
code("vg.FloodParams()")

# ------------------------------------------------------------------------------------------------------------------
part("Your own flood", """
Now any flood that SWOT has seen since July 2023. Finding SWOT passes needs only the internet; downloading the SWOT
maps needs a free **NASA Earthdata** account (each pass is a 20–70 MB file, cut down to your area and saved).
""")
section("Log in to NASA Earthdata", """
1. If you have no account, register (free, 2 minutes): <https://urs.earthdata.nasa.gov/users/new>
2. Run the cell below, type your username and password, and click **Log in**. Tick *Remember me* to skip this next time.
""")
code("vg.earthdata_login()")

section("Draw your area and map the flood", """
1. Move the map to your flood, then draw a polygon or rectangle (tools at the top left). Keep it under about
   50 km × 50 km.
2. Set the flood date and click **Find SWOT passes**.
3. Choose a *before* and an *after* pass — on the same track if you can — and click **Map the flood**.

The map starts on the Kinshasa example, so you can try the buttons straight away (no login needed for the example).
""")
code('vg.flood_explorer("kinshasa_2024")   # ✏️ or vg.flood_explorer(lat=-19.0, lon=23.0, zoom=8)')
ask(["Which flood did you choose? Did SWOT see it before and after, from the same track?",
     "How much of your area did both passes see? Would a different pair of passes be better?"])

section("The same, with code", """
Each line can be changed. Give your polygon as **(longitude, latitude)** points — the explorer shows this line for the
area you drew. The example below looks at the Kinshasa flood again, from the *other* track (111): compare it with Part 2.
""")
code('area = vg.flood_area(polygon=[(15.25, -4.40), (15.60, -4.40), (15.60, -4.05), (15.25, -4.05)])   # ✏️ (lon, lat)\n'
     'area.passes("2023-08-15", "2024-02-15")   # ✏️ the period to search')
code('mine = vg.flood_event(area, before="2023-09-04", after="2024-01-08")   # ✏️ dates, or passes like "003_111"\nmine')
code("mine.depth()")
code("mine.summary()")
ask(["Does track 111 give the same newly flooded area and depth as track 570 in Part 2? Why might they differ?"])

# ------------------------------------------------------------------------------------------------------------------
part("Summary", """
- SWOT measures the **height of the water surface**, in 2D, every 100 m. The **depth** needs a ground model (DEM), and
  every error in the DEM — trees, buildings, its age — goes straight into the depth.
- Compare passes on the **same track** when you can, and check how much of your area each pass saw (the 20 km gap
  under the satellite, the swath edges).
- SWOT sees a place two to four times in 21 days: it suits **large, slow floods** like the Congo and the Okavango, and
  will often miss short, flashy ones.
- **Cities** (layover), **vegetation** over water and **dark water** reduce what SWOT can measure. The cleaning step
  shows where.
- Better ground, better depth: a bare-earth DEM (trees and buildings removed, such as FABDEM) or a local survey.

For water levels at a point and discharge, see the virtual gauge notebook `Virtual_River_Gauges_Student.ipynb`.
""")
code("vg.credits()")

contents = "**Contents** — " + " · ".join(f"{n} {title}" for n, title in _num["parts"])
cells[0].source = cells[0].source.replace("{CONTENTS}", contents)
nb = nbf.v4.new_notebook()
nb.cells = cells
nb.metadata = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
               "language_info": {"name": "python"}, "colab": {"provenance": []}}
nbf.validate(nb)
out = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1] / NAME)
nbf.write(nb, out)
print("wrote", out, "with", len(cells), "cells,", sum(c.cell_type == "code" for c in cells), "code cells")
