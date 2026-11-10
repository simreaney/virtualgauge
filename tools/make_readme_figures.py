"""Draw the README banner and figures from the bundled data (no internet needed).

Dessiner la bannière et les figures du README à partir des données fournies (sans internet).

    python tools/make_readme_figures.py          # writes docs/images/*.png · écrit docs/images/*.png
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
sys.path.insert(0, str(ROOT / "src"))           # draw with this checkout, not an installed copy
os.environ["VG_OFFLINE"] = "1"

import numpy as np                              # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.figure import Figure            # noqa: E402

import virtualgauge as vg                       # noqa: E402
from virtualgauge.locations import reach_index  # noqa: E402
from virtualgauge.sites import PRESETS          # noqa: E402

DPI = 150

# Banner themes, swapped by GitHub with prefers-color-scheme; backgrounds match GitHub's page
# Thèmes de la bannière (clair / sombre) ; fonds identiques à ceux de GitHub
THEMES = {
    "light": dict(bg="#ffffff", ink="#0b0b0b", ink2="#52514e", muted="#6f6e69",
                  river=("#c5daf3", "#2a78d6", "#0d3f80"), station="#0b0b0b"),
    "dark": dict(bg="#0d1117", ink="#f2f1ec", ink2="#c3c2b7", muted="#9d9c95",
                 river=("#1d3350", "#4b93e6", "#bcd8fb"), station="#f2f1ec"),
}
W, H = 12, 3.0                                   # banner size in inches · taille en pouces
LON0, LON1, LAT0, LAT1 = -160, 182, -45, 72     # Fiji (178.4° E) stays on the right edge · Fidji reste à droite


def _station_dots(ax, x, y, c, z=4):
    ax.scatter(x, y, s=50, color=c["bg"], lw=0, zorder=z)           # ring in the background colour
    ax.scatter(x, y, s=22, color=c["station"], lw=0, zorder=z + 0.1)


def banner(theme):
    c = THEMES[theme]
    idx = reach_index()
    r = idx.assign(x=np.where(idx.lon < LON0, idx.lon + 360, idx.lon))    # every reach · tous les tronçons
    r = r[(r.lat >= LAT0) & (r.lat <= LAT1)].sort_values("width_m")   # wide rivers drawn last, on top
    w = np.clip((np.log10(r.width_m.clip(lower=1)) - 1.5) / 2.3, 0, 1)  # ~30 m → 0, ~6 km → 1 (no width → 0)

    fig = Figure(figsize=(W, H), dpi=DPI)
    fig.patch.set_facecolor(c["bg"])
    map_w = H * (LON1 - LON0) / (LAT1 - LAT0) / W                     # map width as a share of the banner
    ax = fig.add_axes([1 - map_w, 0, map_w, 1])
    ax.set_xlim(LON0, LON1)
    ax.set_ylim(LAT0, LAT1)
    ax.set_aspect("equal")
    ax.axis("off")
    cmap = LinearSegmentedColormap.from_list("river", c["river"])
    ax.scatter(r.x, r.lat, s=0.05 + 2.2 * w ** 2, c=w, cmap=cmap, vmin=0, vmax=1, lw=0, rasterized=True, zorder=1)
    lon = np.array([s.lon + 360 if s.lon < LON0 else s.lon for s in PRESETS.values()])
    _station_dots(ax, lon, [s.lat for s in PRESETS.values()], c, z=2)

    # Text column on the left (axes in inches); a short fade softens the map's empty Pacific edge
    # Colonne de texte à gauche ; un court fondu adoucit le bord du Pacifique
    top = fig.add_axes([0, 0, 1, 1], zorder=3)
    top.set_xlim(0, W)
    top.set_ylim(0, H)
    top.axis("off")
    x0 = (1 - map_w) * W                                              # where the map starts
    xs = np.linspace(0, W, 1200)
    alpha = np.clip(1 - (xs - x0 + 0.15) / 0.9, 0, 1) ** 1.5
    rgba = np.zeros((1, len(xs), 4))
    rgba[..., :3] = [int(c["bg"][i:i + 2], 16) / 255 for i in (1, 3, 5)]
    rgba[..., 3] = alpha
    top.imshow(rgba, extent=(0, W, 0, H), aspect="auto", interpolation="bilinear")

    x = 0.36
    top.text(x, H - 0.44, "virtualgauge", fontsize=34, fontweight="bold", color=c["ink"], va="top")
    top.text(x, H - 1.10, "Virtual river gauges\nfrom satellite altimetry", fontsize=14.5, color=c["ink"],
             va="top", linespacing=1.3)
    top.text(x, H - 1.67, "Stations hydrométriques virtuelles\npar altimétrie satellitaire", fontsize=14.5,
             color=c["ink2"], va="top", linespacing=1.3)

    # Key: what the dots are · légende
    kx, ky = x + 0.06, 0.58
    _station_dots(top, [kx], [ky], c)
    top.scatter(kx + np.array([-0.05, 0, 0.05]), [ky - 0.24] * 3, s=[1.4, 3, 5], color=c["river"][1], lw=0,
                zorder=4)
    top.text(kx + 0.15, ky, f"{len(PRESETS)} ready-made stations · stations prêtes", fontsize=10.5,
             color=c["muted"], va="center")
    top.text(kx + 0.15, ky - 0.24, f"{len(idx):,} SWOT river reaches · tronçons SWOT".replace(",", " "),
             fontsize=10.5, color=c["muted"], va="center")
    fig.savefig(OUT / f"banner_{theme}.png", dpi=DPI, facecolor=c["bg"])


def figures():
    vg.set_language("both")
    congo = vg.build_station("congo_kinshasa")
    congo.levels().save(OUT / "congo_levels.png", dpi=DPI)
    congo.rating(exclude_months=[3, 4, 5, 6]).save(OUT / "congo_rating.png", dpi=DPI)
    congo.discharge().save(OUT / "congo_discharge.png", dpi=DPI)
    vg.compare_stations(["okavango_mohembo", "okavango_seronga", "chobe_kasane", "zambezi_kazungula"]).save(
        OUT / "botswana_levels.png", dpi=DPI)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        banner(theme)
    figures()
    for f in sorted(OUT.glob("*.png")):
        print(f"{f.relative_to(ROOT)}  {f.stat().st_size // 1024} KB")
