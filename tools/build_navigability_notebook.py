"""Build the Congo navigability student notebook (English only, results first, one line of code per step).

Usage: python tools/build_navigability_notebook.py [output.ipynb]
"""
import sys
from pathlib import Path

import nbformat as nbf

cells = []
HIDE = {"jupyter": {"source_hidden": True}, "cellView": "form", "tags": ["hide-input"]}
NAME = "Congo_Navigability_Student.ipynb"


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
# How navigable is the Congo today? — student notebook

**Download the SWOT water levels of every river reach in the Congo basin, find the lowest and highest level each reach
has had since July 2023, and map where the rivers stand today between those two.**

**Start here:** menu **Run ▸ Run all** (Colab: **Runtime ▸ Run all**), then read from the top.

The first run downloads the SWOT record of all 4,444 river reaches of the basin from NASA's Hydrocron service — about
10 minutes, no account needed. Later runs re-use the saved files and only download again what is more than three days
old. Without internet the notebook uses the copy shipped with the `virtualgauge` package (downloaded 16 November 2026).
About 60 minutes.

✏️ a line you can change — 🧪 try it — 💬 questions to discuss

{{CONTENTS}}

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/simreaney/virtualgauge/blob/main/{NAME})
"""))

code(r'''
#@title Setup { display-mode: "form" }
import glob, importlib, importlib.util, subprocess, sys
from pathlib import Path


def _needs_install():
    spec = importlib.util.find_spec("virtualgauge")            # finds the package without importing it
    return spec is None or not (Path(spec.origin).parent / "navigation.py").exists()


if _needs_install():                      # install once (Colab / new computer)
    REPO_URL = "https://github.com/simreaney/virtualgauge"
    here = Path.cwd()
    local = [str(here)] if (here / "src" / "virtualgauge" / "navigation.py").exists() else []   # this repository
    wheel = sorted(glob.glob("virtualgauge-*.whl"))
    for source in local + wheel[-1:] + [f"git+{REPO_URL}"]:
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
part("From water level to navigability", """
The Congo and its tributaries carry boats, barges and ferries over thousands of kilometres: from Kinshasa up to
Kisangani (about 1,700 km), up the Kasai to Ilebo, up the Ubangi to Bangui, up the Sangha to Ouesso, and on the Lualaba
above Kisangani. Below Kinshasa the Livingstone Falls block the way to the sea port of Matadi; just above Kisangani the
Boyoma Falls block the way upstream.

What a boat needs is **depth**, above all over the shallowest places — sand bars and rocky sills. When the river is
low, barges must carry less or stop. Nobody measures depth over the whole basin, but the satellite **SWOT** (NASA and
CNES, since July 2023) measures the **height of the water surface** on every river reach wider than about 100 m, two to
four times every 21 days. On a given reach, a higher water surface means more water over the shallows.

So we compare each reach **with itself**: where is its water level today, between the lowest and the highest level
SWOT has recorded there?

> **navigability index = 100 × (latest level − lowest level) ÷ (highest level − lowest level)**

| index | | |
|---|---|---|
| 0–20 | very poor | the river is as low as SWOT has seen it here |
| 20–40 | poor | |
| 40–60 | fair | |
| 60–80 | good | |
| 80–100 | very good | the river is as high as SWOT has seen it here |
""")
ask(["Is high water always better for boats? Think of the current, floating vegetation, flooded ports and bridges.",
     "Why compare each reach with its own record, instead of comparing the water level of different rivers?",
     "The record starts in July 2023. In December 2023 the Congo at Kinshasa rose to its highest level since 1961. "
     "What does that do to the ‘highest level’ of the reaches near Kinshasa — and to their index in later years?",
     "The index says nothing about rapids or waterfalls. Which parts of the Congo are never navigable, whatever the index?"])

# ------------------------------------------------------------------------------------------------------------------
part("Every SWOT reach in the Congo basin", """
SWOT reports one water level per **reach** — a stretch of river about 10 km long, from the SWORD river database. The
Congo basin has 4,444 of them (narrow streams to the 4 km wide main river), and each has its own record on Hydrocron.
""")
section("Download", """
This one line downloads the SWOT record of every reach, eight at a time, and cleans it. The first time it takes about
10 minutes; a progress line shows how far it has got. If it stops (or you stop it), run the cell again: it continues
where it stopped. The files are saved in the folder `cache/survey_reaches/`, one per reach.
""")
code('congo = vg.river_survey("congo")   # ✏️ update_days=3: download again what is older than this\ncongo')

section("Which reaches does SWOT measure?", """
The colour shows how many good SWOT levels each reach has. Pale grey: no good level at all.
""")
code("congo.coverage()")
ask(["Which rivers have the most levels? Which have none? Is it a matter of width?",
     "Find the stretch of the Congo between Mbandaka and Bumba (around 19–22° E, 1–2° N) with few levels. "
     "The river is very wide there, with many islands and channels. Why might that be hard for SWOT?"])

section("Which levels can we trust?", """
As in the virtual gauge notebook, every level that is removed has a written reason: a poor quality flag, a level far
from all the other levels of its reach, or a **spike** — a level that jumps away from the levels just before and after
it. Rivers rise and fall slowly; a level 2 m away from levels measured a few days earlier is an error, not a flood.
""")
code("congo.cleaning()")
ask(["What share of the SWOT levels is kept?",
     "Why is it important to remove spikes *before* we look for the lowest and the highest level?"])

# ------------------------------------------------------------------------------------------------------------------
part("The lowest and highest recorded levels", """
For each reach: the lowest and the highest good level since July 2023, and the **range** between them. A reach gets a
range only if its record can be trusted: enough good levels, spread over at least a year (so that low and high water
are both in it), and levels that do not jump around from one pass to the next (*too noisy*).
""")
code("congo.ranges()")
ask(["Which rivers have the largest range? Which the smallest? Why might the range of a river change along its course?",
     "Most reaches with no range are narrow. Why is a narrow river harder for SWOT?"])

section("One reach: the Congo at Mbandaka", """
Every good level (blue), the levels removed by the cleaning (grey crosses), the lowest and highest recorded level
(dashed), and the latest level, coloured by its index.
""")
code('congo.reach("13273000011")   # ✏️ any reach ID: click a river on the map in Part 4')
ask(["When was the highest level recorded, and the lowest? Do they match what you know of the Congo's seasons?",
     "Each SWOT level has an error of about 10 cm. How much does that move the index of this reach?"])

section("🧪 A harder reach: the Congo at Bumba")
code('congo.reach("13275700241")')
ask(["Compare this record with Mbandaka. Which do you trust more, and why?",
     "The lowest and highest levels are each one single measurement. What happens to the index of every later date "
     "if one of them is wrong?"])

# ------------------------------------------------------------------------------------------------------------------
part("The navigability of the Congo today", """
Each reach gets an index from its **latest** good level — if that level is at most 30 days old (SWOT passes every few
days to weeks, so ‘today’ really means ‘the last few weeks’). Reaches with no trusted range, or no recent level, are
pale grey.
""")
code("congo.navigability()")
ask(["Where is the water low today, and where is it high? Do rivers north and south of the equator differ?",
     "The Ubangi, the Sangha and the Uele drain the north of the basin; the Kasai and the Lualaba the south. "
     "Their rainy seasons come at different times of year. How does the map show that?",
     "How much of the river length is below 40? Would barges on the main river be loaded fully today?"])

section("Interactive map", """
Zoom in and click a river for its numbers: index, latest level and date, lowest and highest level, and the reach ID
(to use in `congo.reach(...)`). The black dots are river ports. The layer button (top right) changes the background.
""")
code("congo.map()")

# ------------------------------------------------------------------------------------------------------------------
part("Along the river and at the ports", "")
section("From Kindu to the sea", """
The Lualaba and the Congo, reach by reach from Kindu to the Atlantic. Top: the range of each reach (blue) and where its
latest level stands above the lowest. Bottom: the index.
""")
code("congo.profile()")
ask(["Where along the river is the range largest? (Hint: what lies between Kinshasa and the sea?)",
     "Is the index the same all along the river today? Where does it change, and which tributaries join there?"])

section("River ports", """
The index of every SWOT level since July 2023, at the reach nearest each port. The large dot is the latest level.
""")
code("congo.ports()")
ask(["In which months is the water lowest at Bangui? At Ilebo? At Kinshasa?",
     "At Kinshasa, the Congo receives water from both hemispheres. How does that show in its record, compared with "
     "Bangui or Ilebo?",
     "A barge company plans a trip from Kinshasa to Bangui. Which months would you advise, and why?"])

# ------------------------------------------------------------------------------------------------------------------
part("Through time", """
The same index on the first of every month: which share of the river length was at very poor, poor, fair, good or very
good water.
""")
code("congo.history()")
ask(["When was the water lowest across the basin? Is today unusual?",
     "Why is the high water of December 2023 – January 2024 so dark blue, and never again as dark?"])
section("🧪 The map on another date", "Any date since late 2023 — for instance the low water of mid-2025:")
code('congo.navigability("2025-08-01")   # ✏️ a date, "YYYY-MM-DD"')

# ------------------------------------------------------------------------------------------------------------------
part("Change the settings", """
Every setting is a keyword of `congo.with_settings(...)` (or of `vg.river_survey`). The data are already on your
computer, so this is quick. Three tasks:

1. Allow an older ‘latest level’ (`max_age_days=60`). How many more reaches get an index? Is that a fair map of *today*?
2. Remove levels with a lot of **dark water** (`max_dark_frac=0.5`: more than half of the reach gave too little radar
   echo). What happens to the records at Bumba and at Ouesso?
3. Be stricter about noisy reaches (`max_noise_frac=0.1`). Which rivers lose their index?
""")
code('congo.with_settings(max_age_days=60).navigability()   # ✏️')
code('congo.with_settings(max_dark_frac=0.5).ports()   # ✏️')
code('congo.with_settings(max_noise_frac=0.1).navigability()   # ✏️')
md(None, "All the settings, with their default values:")
code("vg.SurveyParams()")

section("🧪 Your own list of reaches", """
Any list of SWOT reach IDs — here every reach within 60 km of Kinshasa and Brazzaville. Reaches already downloaded are
not downloaded again.
""")
code('near = vg.reaches_near(-4.3, 15.3, radius_km=60, n=300).values["reach_ids"]   # ✏️ latitude, longitude\n'
     'pool = vg.river_survey(reach_ids=near, name="Around Kinshasa and Brazzaville")\n'
     'pool.navigability()')

# ------------------------------------------------------------------------------------------------------------------
part("Export and summary", """
Save the table of every reach (CSV: river, lowest and highest level, range, latest level, index) and the rivers with
their index (GeoJSON — open it in QGIS) in the folder `outputs/`.
""")
code("congo.export()")
md(None, "The ten reaches with the lowest water today, as a table you can sort and filter (pandas):")
code('table = congo.to_dataframe()\n'
     'table[table.width_m > 300].sort_values("index")[["reach_id", "river_name", "width_m", "range_m", "now_date", "index"]].head(10)')
md("Summary", """
- SWOT measures the **water level** of every river reach in the basin, not its depth. Comparing each reach with its
  own lowest and highest level turns those heights into a simple **navigability index**.
- The index is only as good as the **record**: three years, with an exceptional flood at the start, and the lowest and
  highest values are each a single measurement — so cleaning the levels first matters.
- **Narrow rivers**, very wide braided ones and **dark water** give noisy records; those reaches get no index.
- ‘Today’ means the **last few weeks**: SWOT passes each reach a few times every 21 days.
- What the index cannot tell: the real depth over sand bars, the draught of the boats, rapids and falls, or whether
  high water is too fast or too high under bridges. Local knowledge and gauge readings complete it.

For water levels and discharge at one place, see `Virtual_River_Gauges_Student.ipynb`; for flood maps,
`SWOT_Flood_Depth_Student.ipynb`.
""", level=2)
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
