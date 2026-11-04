# Virtual river gauges from satellite altimetry · Stations hydrométriques virtuelles par altimétrie satellitaire

[![Open in Colab · Ouvrir dans Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/simreaney/virtualgauge/blob/main/Virtual_River_Gauges_Student.ipynb)

Bilingual (English / French) teaching material for hydrologists in national services: build virtual river gauges from real ICESat-2 and SWOT satellite data, with worked examples on the **Congo at Kinshasa–Brazzaville (DR Congo)** and the **Rewa River (Fiji)**, six more Congo-basin stations, nine stations in **Botswana**, ready-made examples on every continent, and any river in the world.

Matériel pédagogique bilingue (anglais / français) pour les hydrologues des services nationaux : construire des stations hydrométriques virtuelles à partir de vraies données ICESat-2 et SWOT, avec des exemples sur le **Congo à Kinshasa–Brazzaville (RD Congo)** et la **rivière Rewa (Fidji)**, six autres stations du bassin du Congo, neuf stations au **Botswana**, des exemples prêts sur tous les continents, et toute rivière du monde.

## Two notebooks · Deux notebooks

| Notebook | For · Pour |
|---|---|
| `Virtual_River_Gauges_Student.ipynb` | **Students** — results first, one line of code per step, questions to discuss, widgets, maps of the Congo, Botswana and the world. Uses the `virtualgauge` package. · **Étudiants** — résultats d'abord, une ligne de code par étape, questions, widgets, cartes. |
| `Virtual_River_Gauges_DRC_Fiji.ipynb` | **Trainers / advanced** — the full method with all the code. · **Formateurs / avancés** — la méthode complète avec tout le code. |

## The `virtualgauge` package · Le package `virtualgauge`

```python
import virtualgauge as vg
vg.set_language("both")                      # "en", "fr" or "both"
congo = vg.build_station("congo_kinshasa")   # or any 11-digit SWOT reach ID · ou tout identifiant SWOT
congo.levels()
congo.rating(exclude_months=[3, 4, 5, 6])
congo.discharge()
congo.export()
vg.explore()                                 # sliders · curseurs
vg.explore_map()                             # click a dot → graphs · cliquez sur un point → graphiques
vg.explore_map("botswana")                   # Botswana and its border rivers · le Botswana
vg.explore_map("world")                      # zoom in: every reach in view · zoomez : chaque tronçon de la vue
vg.explore_map(lat=-17.96, lon=178.43, radius_km=150)   # any region · toute région
vg.sites(region="botswana")                  # ready-made stations · stations prêtes
```

It ships the real data (downloaded 3–4 November 2026) for 31 stations — the Congo basin, Botswana, Fiji and fourteen rivers on other continents, including the Karnali (Nepal) and the Cimanuk (West Java) — and an index of all 248,673 SWOT river reaches, so the student notebook works **offline**. Other reaches are downloaded on demand (no account needed). Ready-made stations: `vg.sites()`.

Il contient les vraies données (téléchargées les 3 et 4 novembre 2026) de 31 stations — bassin du Congo, Botswana, Fidji et quatorze fleuves d'autres continents, dont la Karnali (Népal) et la Cimanuk (Java occidental) — et l'index des 248 673 tronçons SWOT du monde : le notebook étudiant fonctionne **hors ligne**. Les autres tronçons sont téléchargés à la demande (sans compte).

## Install · Installation

**Your computer · Votre ordinateur**

```bash
pip install -e .              # the package (from this folder) · le package
jupyter lab Virtual_River_Gauges_Student.ipynb
```

**Google Colab:** click the *Open in Colab* badge above, then *Runtime ▸ Run all*. The hidden setup cell installs the package from GitHub (`pip install git+https://github.com/simreaney/virtualgauge`). If Colab cannot install from GitHub, download `virtualgauge-0.1.0-py3-none-any.whl` from the [Releases page](https://github.com/simreaney/virtualgauge/releases) and upload it to Colab together with the notebook.
**Google Colab :** cliquez sur le badge *Open in Colab* ci-dessus, puis *Exécution ▸ Tout exécuter*. La cellule cachée installe le package depuis GitHub. Si Colab ne peut pas installer depuis GitHub, téléchargez le fichier `.whl` depuis la page [Releases](https://github.com/simreaney/virtualgauge/releases) et téléversez-le dans Colab avec le notebook.

**Anywhere else · Ailleurs :** `pip install git+https://github.com/simreaney/virtualgauge`

The trainer notebook only needs `pip install -r requirements.txt` · Le notebook formateur demande seulement `pip install -r requirements.txt`.

## Folder · Dossier

| Path · Chemin | What · Quoi |
|---|---|
| `src/virtualgauge/` | The package; `messages.py` holds every English/French text (for the francophone review) · tous les textes EN/FR |
| `src/virtualgauge/data/` | Bundled real data + `MANIFEST.json` (checksums, sources, dates) · données fournies |
| `tests/` | `pytest` — offline checks, including exact agreement with the trainer notebook · contrôles hors ligne |
| `tools/` | Rebuild the student notebook, the bundled data, the location data; `check_wheel.sh` · outils |
| `cache/`, `outputs/`, `data/` | Downloads, results, your own gauge files (see `data/README.md`) · téléchargements, résultats, vos fichiers |

## Data and credits · Données et remerciements

| Source | Access · Accès | Credit · Crédit |
|---|---|---|
| ICESat-2 ATL13 v007 (NASA/NSIDC) via SlideRule Earth | no login · sans identifiant | doi:10.5067/ATLAS/ATL13.007; SlideRule Earth (University of Washington / NASA) |
| SWOT L2 HR RiverSP, Version D (NASA/CNES, PO.DAAC) via Hydrocron | no login · sans identifiant | NASA/CNES, PO.DAAC |
| SWORD v17b river database (reach index) | bundled · fourni | Altenau et al. (2021), CC BY 4.0, doi:10.5281/zenodo.15299138 |
| GEOGloWS v2 retrospective streamflow (ECMWF) | no login · sans identifiant | GEOGloWS ECMWF Streamflow Model v2 |
| Botswana border (map outline) · frontière du Botswana | bundled · fourni | Natural Earth 1:50m, public domain · domaine public |
| GRDC (optional · facultatif) | free registration · inscription gratuite | Global Runoff Data Centre, Koblenz — no redistribution · pas de rediffusion |
| DAHITI (optional · facultatif) | free API key · clé API gratuite | DGFI-TUM, CC BY 4.0 |

## Status · État

- Tested 2026-11-04: 28 offline tests pass on Python 3.13 (pandas 3) and on a Colab-like Python 3.12 (pandas 2.2, numpy 1.26, geopandas 1.0, ipywidgets 7.7); the student notebook runs offline from the installed wheel in both. The package reproduces the trainer notebook's results exactly.
  Testé le 2026-11-04 : 28 tests hors ligne réussis sous Python 3.13 et sous un Python 3.12 proche de Colab ; le notebook étudiant s'exécute hors ligne depuis le wheel installé. Le package reproduit exactement les résultats du notebook formateur.
- Not yet checked on real Google Colab, nor in VS Code's handling of the hidden setup cell. · Pas encore vérifié sur Colab ni dans VS Code.
- Where GEOGloWS is far from the flow measured nearby (Okavango at Mohembo 2.3×, Zambezi 3.8×, Niger 3×, White Nile 8×) the package warns in the Discharge tab; Botswana's own gauge records would make those curves usable. · Quand GEOGloWS s'écarte fortement du débit mesuré, le package le signale.
- The optional DAHITI and GRDC functions are untested without a real key or file. · Les fonctions DAHITI et GRDC ne sont pas testées sans vraie clé ou fichier.
- The French text should be reviewed by a francophone hydrologist (`src/virtualgauge/messages.py` and the notebooks). · Le texte français doit être relu par un hydrologue francophone.

## Licence

The code and notebooks are free software under the **GNU General Public License v3.0 or later** (see `LICENSE`). The bundled data keep their own terms (see *Data and credits* above).

Le code et les notebooks sont des logiciels libres sous **licence publique générale GNU v3.0 ou ultérieure** (voir `LICENSE`). Les données fournies gardent leurs propres conditions (voir *Données et remerciements*).
