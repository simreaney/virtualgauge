"""Build the student notebook (bilingual, results first, one line of code per step).

Usage: python tools/build_student_notebook.py [output.ipynb]
"""
import sys
from pathlib import Path

import nbformat as nbf

cells = []
HIDE = {"jupyter": {"source_hidden": True}, "cellView": "form", "tags": ["hide-input"]}


def md(title, en, fr, level=2):
    s = f"{'#' * level} {title}\n\n" if title else ""
    s += en.strip() + "\n\n" + "\n".join(("> " + l) if l.strip() else ">" for l in fr.strip().splitlines())
    cells.append(nbf.v4.new_markdown_cell(s))


_num = {"part": 0, "sec": 0, "parts": []}


def part(title_en, title_fr, en, fr):
    """A numbered part: 'Part 3 — …' · Une partie numérotée"""
    _num["part"] += 1
    _num["sec"] = 0
    n = _num["part"]
    _num["parts"].append((n, title_en, title_fr))
    md(f"Part {n} — {title_en} · Partie {n} — {title_fr}", en, fr, level=2)


def section(title_en, title_fr, en="", fr="", level=3):
    """A numbered section inside the current part: '3.2 …' · Une section numérotée"""
    _num["sec"] += 1
    head = f"{_num['part']}.{_num['sec']} {title_en}" + (f" · {title_fr}" if title_fr and title_fr != title_en else "")
    if en:
        md(head, en, fr, level=level)
    else:
        cells.append(nbf.v4.new_markdown_cell(f"{'#' * level} {head}"))


def ask(en, fr):
    """'What do you notice?' questions · Questions « Qu'observez-vous ? »"""
    en_l = "\n".join(f"- {q}" for q in en)
    fr_l = "\n".join(f"- {q}" for q in fr)
    md(None, f"💬 **What do you notice?**\n\n{en_l}", f"💬 **Qu'observez-vous ?**\n\n{fr_l}")


def code(src, hidden=False):
    c = nbf.v4.new_code_cell(src.strip())
    if hidden:
        c.metadata.update(HIDE)
    cells.append(c)


# ------------------------------------------------------------------------------------------------------------------
cells.append(nbf.v4.new_markdown_cell(r"""
# Virtual river gauges from satellites — student notebook
# Stations hydrométriques virtuelles par satellite — notebook étudiant

**Congo (DR Congo) · Rewa (Fiji) · Botswana · and any river in the world** — **Congo (RD Congo) · Rewa (Fidji) · Botswana · et toute rivière du monde**

**Start here · Commencez ici :** menu **Run ▸ Run all** (Colab: **Runtime ▸ Run all**), then read from the top.
Menu **Run ▸ Run all** (Colab : **Exécution ▸ Tout exécuter**), puis lisez depuis le début.

Every result comes from **real** satellite and model data (downloaded 3 November 2026 and shipped with the `virtualgauge` package, so it works offline). About 90 minutes.
Tous les résultats viennent de **vraies** données satellitaires et de modèle (téléchargées le 3 novembre 2026 et fournies avec le package `virtualgauge`, donc utilisables hors ligne). Environ 90 minutes.

✏️ a line you can change · une ligne à modifier — 🧪 try it · à vous — 💬 questions to discuss · questions à discuter

{CONTENTS}

[![Open in Colab · Ouvrir dans Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/simreaney/virtualgauge/blob/main/Virtual_River_Gauges_Student.ipynb)
"""))

code(r'''
#@title Setup · Configuration { display-mode: "form" }
import glob, importlib.util, subprocess, sys
if importlib.util.find_spec("virtualgauge") is None:          # install once (Colab / new computer)
    REPO_URL = "https://github.com/simreaney/virtualgauge"
    wheel = sorted(glob.glob("virtualgauge-*.whl"))
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", wheel[-1] if wheel else f"git+{REPO_URL}"])
import virtualgauge as vg
print(f"virtualgauge {vg.__version__} — ready · prêt")
''', hidden=True)

md(None, "Choose the language of figures and messages: `\"en\"`, `\"fr\"` or `\"both\"`.",
   "Choisissez la langue des figures et des messages : `\"en\"`, `\"fr\"` ou `\"both\"` (les deux).")
code('vg.set_language("both")   # ✏️ "en", "fr" or/ou "both"')

# ------------------------------------------------------------------------------------------------------------------
part("Water levels on the Congo at Kinshasa", "Niveaux d'eau du Congo à Kinshasa",
   """
A **virtual station** is a place where satellites measure the same river again and again. Here we combine two:
**ICESat-2** (a laser, since 2018) and **SWOT** (a radar that maps whole rivers, since 2023). One line builds the station:
""",
   """
Une **station virtuelle** est un endroit où les satellites mesurent la même rivière encore et encore. Nous en
combinons deux : **ICESat-2** (un laser, depuis 2018) et **SWOT** (un radar qui cartographie des rivières entières,
depuis 2023). Une ligne construit la station :
""")
code('congo = vg.build_station("congo_kinshasa")\ncongo')

section("Where is it?", "Où est-elle ?",
   "The white outline is the **water mask** around the river centre-line; orange dots are ICESat-2 laser points. Switch to the satellite image with the layer button.",
   "Le contour blanc est le **masque d'eau** autour de la ligne centrale ; les points orange sont les points laser ICESat-2. Passez à l'image satellite avec le bouton des couches.", level=3)
code("congo.map()")

section("Step 1 — Raw laser points", "Étape 1 — Points laser bruts",
   "Every point is a water height measured by ICESat-2, in metres above the **EGM2008 geoid** (≈ mean sea level), not above your gauge zero.",
   "Chaque point est une hauteur d'eau mesurée par ICESat-2, en mètres au-dessus du **géoïde EGM2008** (≈ niveau moyen des mers), pas au-dessus du zéro de votre échelle.", level=3)
code("congo.raw_points()")
ask(["Most points form a band — the river. What could make the laser see a surface 10–40 m higher?"],
    ["La plupart des points forment une bande — le fleuve. Qu'est-ce qui pourrait faire voir au laser une surface 10 à 40 m plus haut ?"])

section("Step 2 — Cleaning", "Étape 2 — Nettoyage",
   "Points are removed for four reasons: impossible level, not a river, cloudy, or an outlier within its pass. Every removal has a written reason.",
   "Les points sont retirés pour quatre raisons : niveau impossible, pas une rivière, nuageux, ou valeur aberrante dans son passage. Chaque retrait a une raison écrite.", level=3)
code("congo.cleaning()")
ask(["Which filter removes the most points?", "Look at the grey crosses: were any real water levels removed?"],
    ["Quel filtre retire le plus de points ?", "Regardez les croix grises : de vrais niveaux d'eau ont-ils été retirés ?"])

section("Step 3 — The river surface slopes", "Étape 3 — La surface du fleuve est en pente",
   "Each laser pass crosses the reach at a different place. The water surface falls downstream, so the points are corrected to the middle of the reach before taking one level per pass.",
   "Chaque passage laser croise le tronçon à un endroit différent. La surface de l'eau descend vers l'aval : les points sont ramenés au milieu du tronçon avant de prendre un niveau par passage.", level=3)
code("congo.slope()")
ask(["Is a slope of about 8 cm per km plausible for a very large river?", "Why might one pass give a much larger slope than the others? (look at its number of points)"],
    ["Une pente d'environ 8 cm par km est-elle plausible pour un très grand fleuve ?", "Pourquoi un passage donne-t-il une pente bien plus forte que les autres ? (regardez son nombre de points)"])
code("congo.icesat_levels()")

section("Step 4 — SWOT", "Étape 4 — SWOT",
   "SWOT gives one level for the whole ~10 km reach at each pass. We keep good quality flags and check that **water flows downhill**: our reach cannot be higher than the reach upstream at the same moment.",
   "SWOT donne un niveau pour tout le tronçon de ~10 km à chaque passage. On garde les bons indicateurs de qualité et on vérifie que **l'eau descend** : notre tronçon ne peut pas être plus haut que l'amont au même moment.", level=3)
code("congo.swot()")
ask(["How many SWOT levels per year do we get, compared with ICESat-2?", "Why do you think so many observations fail the quality flags?"],
    ["Combien de niveaux SWOT par an obtient-on, comparé à ICESat-2 ?", "Pourquoi, à votre avis, tant d'observations échouent-elles aux indicateurs de qualité ?"])

section("Step 5 — Two satellites, one station", "Étape 5 — Deux satellites, une station",
   "When both satellites passed within 3 days, we compare them and shift ICESat-2 onto SWOT.",
   "Quand les deux satellites sont passés à moins de 3 jours d'intervalle, on les compare et on ramène ICESat-2 sur SWOT.", level=3)
code("congo.agreement()")
code("congo.levels()")
ask(["When are the lowest and highest levels of the year?", "Something unusual happened at the end of 2023 — what do you see?", "Is an offset from only 5 pairs reliable?"],
    ["Quand surviennent les niveaux les plus bas et les plus hauts de l'année ?", "Quelque chose d'inhabituel s'est produit fin 2023 — que voyez-vous ?", "Un décalage estimé sur seulement 5 paires est-il fiable ?"])

# ------------------------------------------------------------------------------------------------------------------
part("From level to discharge", "Du niveau au débit",
   """
A **rating curve** turns water level into discharge: **Q = a · (h − h₀)ᵇ**. To fit it we need discharge on the days
the satellites looked. With no open gauge data for these years, we use the **GEOGloWS model** — and we must check it.
""",
   """
Une **courbe de tarage** transforme le niveau en débit : **Q = a · (h − h₀)ᵇ**. Pour l'ajuster, il faut des débits aux
dates des passages. Sans données de station ouvertes pour ces années, on utilise le **modèle GEOGloWS** — et il faut le vérifier.
""")
section("The reference discharge", "Le débit de référence")
code("congo.reference_discharge()")
ask(["The automatic river lookup found a river with about 1 m³/s. Why is that a problem?"],
    ["La recherche automatique a trouvé une rivière d'environ 1 m³/s. Pourquoi est-ce un problème ?"])
section("The rating curve", "La courbe de tarage")
code("congo.rating()")
ask(["What does the warning “b is at its limit” tell you?", "Is NSE = 0.47 good enough for a flow gauge?"],
    ["Que vous dit l'avertissement « b est à sa limite » ?", "Un NSE de 0,47 suffit-il pour une station de débit ?"])
section("Which months fit?", "Quels mois s'ajustent ?")
code("congo.residuals_by_month()")
ask(["Kinshasa's level is controlled by rock rapids just downstream, which do not move. So is this seasonal pattern caused by the river, or by the model?"],
    ["Le niveau à Kinshasa est contrôlé par des rapides rocheux juste en aval, qui ne bougent pas. Cette structure saisonnière vient-elle du fleuve ou du modèle ?"])

md(None, "Leave out the months where the model disagrees with the satellites, and fit again:",
   "Excluez les mois où le modèle contredit les satellites, et ajustez à nouveau :")
code("congo.rating(exclude_months=[3, 4, 5, 6])   # ✏️ try other months · essayez d'autres mois")
section("Test on years not used for fitting", "Test sur des années non utilisées")
code('congo.split_test("2025-01-01")')
ask(["The curve fits the earlier years well. Why is it worse on 2025–2026?", "What do we lose by leaving months out?"],
    ["La courbe s'ajuste bien aux premières années. Pourquoi est-elle moins bonne en 2025–2026 ?", "Que perd-on en excluant des mois ?"])
section("Discharge and export", "Débit et export")
code("congo.discharge()")
ask(["The long-term mean flow measured at Kinshasa since 1903 is about 40,000 m³/s. How does our virtual gauge compare, and why?"],
    ["Le débit moyen mesuré à Kinshasa depuis 1903 est d'environ 40 000 m³/s. Comment notre station virtuelle se compare-t-elle, et pourquoi ?"])
md(None, "Save the result as a CSV file for your agency (folder `outputs/`). On Colab use `congo.export(download=True)`.",
   "Enregistrez le résultat en CSV pour votre service (dossier `outputs/`). Sur Colab, utilisez `congo.export(download=True)`.")
code("congo.export()")

# ------------------------------------------------------------------------------------------------------------------
part("The Rewa, Fiji", "La Rewa, Fidji",
   "The same method on a river 100–400 m wide, with cyclone floods that last hours to days, and a tidal lower course.",
   "La même méthode sur une rivière de 100 à 400 m de large, avec des crues cycloniques de quelques heures à quelques jours, et un cours inférieur soumis à la marée.")
code('rewa = vg.build_station("rewa_fiji")\nrewa')
section("Levels and slope", "Niveaux et pente")
code("rewa.levels()")
code("rewa.slope()")
ask(["One pass has a negative slope: the water surface rises towards the sea. How can the tide explain that?"],
    ["Un passage a une pente négative : la surface de l'eau monte vers la mer. Comment la marée peut-elle l'expliquer ?"])
section("SWOT and the water-flows-downhill check", "SWOT et le contrôle « l'eau descend »")
code("rewa.swot()")
ask(["Some very high SWOT values were removed because they were higher than the reach upstream. Real floods, or errors?"],
    ["Des valeurs SWOT très hautes ont été retirées car plus hautes que le tronçon amont. Vraies crues ou erreurs ?"])
section("Three reaches, from the tide upstream", "Trois tronçons, de la marée vers l'amont")
code("rewa.compare_reaches()")
ask(["Nausori stays between about 0.2 and 1.7 m all year. Why?", "Where would you put a virtual station to estimate discharge?"],
    ["Nausori reste entre environ 0,2 et 1,7 m toute l'année. Pourquoi ?", "Où placeriez-vous une station virtuelle pour estimer le débit ?"])
section("Will a satellite see the flood?", "Un satellite verra-t-il la crue ?")
code("vg.flood_catch(congo, rewa)")
ask(["What chance does a satellite have of seeing a 1-day cyclone flood? And a 30-day Congo flood?", "What does this mean for flood warning?"],
    ["Quelle chance un satellite a-t-il de voir une crue cyclonique d'un jour ? Et une crue du Congo de 30 jours ?", "Qu'est-ce que cela signifie pour l'alerte aux crues ?"])
section("Why no discharge?", "Pourquoi pas de débit ?")
code("rewa.rating()")
section("Try it: no slope correction", "À vous : sans correction de pente",
        "🧪 Switch the slope correction off for the Rewa and compare the levels with the ones in 3.1.",
        "🧪 Désactivez la correction de pente pour la Rewa et comparez avec les niveaux de 3.1.")
code('vg.build_station("rewa_fiji", slope_correction=False).levels()   # ✏️')

# ------------------------------------------------------------------------------------------------------------------
part("Explore the settings", "Explorer les réglages",
   """
Move the sliders and click the months. Three tasks:
1. Choose the Rewa and set **ICESat-2 max cloud** to 0. How many levels are left?
2. Set the **up/downstream tolerance** to 2 m. Do the impossible "floods" come back?
3. For Kinshasa, add March–June back one month at a time. What happens to *b* and the curve?
""",
   """
Déplacez les curseurs et cliquez sur les mois. Trois tâches :
1. Choisissez la Rewa et mettez **ICESat-2 nuages max** à 0. Combien de niveaux restent-ils ?
2. Mettez la **tolérance amont/aval** à 2 m. Les « crues » impossibles reviennent-elles ?
3. Pour Kinshasa, remettez mars à juin un mois à la fois. Que deviennent *b* et la courbe ?
""")
code("vg.explore()")

# ------------------------------------------------------------------------------------------------------------------
part("Explore more locations", "Explorer d'autres lieux",
     """
On every map below, **click a dot**: the station is built and its graphs appear underneath, in tabs, with the
settings and an export button. No code to copy. Orange dots are stations shipped with the package (instant,
offline); other dots download their data (internet, 20–60 s).
""",
     """
Sur chaque carte ci-dessous, **cliquez sur un point** : la station est construite et ses graphiques s'affichent en
dessous, dans des onglets, avec les réglages et un bouton d'export. Aucun code à copier. Les points orange sont des
stations fournies avec le package (immédiat, hors ligne) ; les autres points téléchargent leurs données (internet,
20 à 60 s).
""")
section("The Congo basin", "Le bassin du Congo",
        "Every dot is a SWOT river reach on the Congo and its large tributaries — a possible virtual station. Darker dots have more good SWOT levels.",
        "Chaque point est un tronçon SWOT du Congo et de ses grands affluents — une station virtuelle possible. Les points foncés ont plus de niveaux SWOT valides.")
code("vg.explore_map()")
ask(["Click the orange pins from Kindu down to Kinshasa. How does the range of water levels change downstream?",
     "Open the Discharge tab for the Ubangi at Bangui. Which reference is used, and how well does the curve fit?",
     "In the Settings tab, switch the water-flows-downhill check off. What changes?"],
    ["Cliquez sur les épingles orange de Kindu jusqu'à Kinshasa. Comment l'amplitude des niveaux change-t-elle vers l'aval ?",
     "Ouvrez l'onglet Débit pour l'Oubangui à Bangui. Quelle référence est utilisée, et la courbe est-elle bien ajustée ?",
     "Dans l'onglet Réglages, désactivez le contrôle amont/aval. Qu'est-ce qui change ?"])
section("Down the river", "Le long du fleuve",
   "Water levels at seven stations, from the upper Congo (Lualaba at Kindu) to Kinshasa. Each panel shows the level minus its median.",
   "Les niveaux de sept stations, du haut Congo (Lualaba à Kindu) jusqu'à Kinshasa. Chaque panneau montre le niveau moins sa médiane.")
code('vg.compare_stations(["lualaba_kindu", "congo_kisangani", "congo_mbandaka", "ubangi_bangui",\n                     "sangha_ouesso", "kasai_kwamouth", "congo_kinshasa"])')
ask(["Which rivers peak in October–December, and which in April–May?", "Kinshasa has two high-water seasons each year. Which tributaries explain each one?", "Which river has the biggest seasonal range?"],
    ["Quelles rivières culminent en octobre–décembre, et lesquelles en avril–mai ?", "Kinshasa a deux saisons de hautes eaux par an. Quels affluents expliquent chacune ?", "Quelle rivière a la plus grande amplitude saisonnière ?"])

section("Botswana", "Botswana",
   """
Botswana's large rivers are mostly on its borders — the Chobe, the Zambezi, the Shashe and the Limpopo — except the
Okavango, which flows in from Angola and Namibia and spreads out into its delta. Nine ready-made stations (orange) on
these five rivers work offline. The white dashed line is the border; dots up to 25 km outside it are included, so the
border rivers appear. Smaller rivers such as the Boteti and the Thamalakane at Maun are not in SWOT's river database.
""",
   """
Les grands fleuves du Botswana sont surtout à ses frontières — le Chobe, le Zambèze, la Shashe et le Limpopo — sauf
l'Okavango, qui arrive de l'Angola et de la Namibie et s'étale dans son delta. Neuf stations prêtes (orange) sur ces
cinq fleuves fonctionnent hors ligne. La ligne blanche en tirets est la frontière ; les points jusqu'à 25 km au-delà
sont inclus, pour montrer les fleuves frontaliers. Les petites rivières comme la Boteti et la Thamalakane à Maun ne
figurent pas dans la base de rivières de SWOT.
""")
code('vg.explore_map("botswana")')
ask(["Open the Okavango at Mohembo, then its Discharge tab. How does the model's mean flow compare with the mean measured at Mohembo? What would you tell a water manager who used these discharges?",
     "The Chobe at Kasane has no Discharge curve. Read the explanation, then compare its Levels tab with the Zambezi at Kazungula, 10 km away.",
     "Most Botswana dots are dark, even on narrow rivers. Does many SWOT levels always mean good levels? (Look at the Limpopo.)"],
    ["Ouvrez l'Okavango à Mohembo, puis son onglet Débit. Comment le débit moyen du modèle se compare-t-il à la moyenne mesurée à Mohembo ? Que diriez-vous à un gestionnaire de l'eau qui utiliserait ces débits ?",
     "Le Chobe à Kasane n'a pas de courbe de débit. Lisez l'explication, puis comparez son onglet Niveaux avec le Zambèze à Kazungula, à 10 km.",
     "La plupart des points du Botswana sont foncés, même sur des rivières étroites. Beaucoup de niveaux SWOT veut-il toujours dire de bons niveaux ? (Regardez le Limpopo.)"])
section("The Okavango, the Chobe and the Zambezi", "L'Okavango, le Chobe et le Zambèze",
   "The Okavango as it enters Botswana (Mohembo), at the end of the Panhandle (Seronga) and where the Delta opens out (Gunotsoga); the Zambezi and the Chobe where they meet at Kazungula.",
   "L'Okavango à son entrée au Botswana (Mohembo), au bout du Panhandle (Seronga) et à l'ouverture du Delta (Gunotsoga) ; le Zambèze et le Chobe à leur rencontre à Kazungula.")
code('vg.compare_stations(["okavango_mohembo", "okavango_seronga", "okavango_gunotsoga", "zambezi_kazungula",\n                     "chobe_kasane"])')
ask(["Which year had almost no flood on the Zambezi and the Chobe? What happened in southern Africa that year?",
     "The Okavango's yearly rise shrinks from about 2.4 m at Mohembo to 1.9 m at Seronga and 0.6 m at Gunotsoga, and peaks a month later. Where does the water go?",
     "The Chobe stays flat while the Zambezi is low, then rises with it. What does that mean for a rating curve at Kasane?"],
    ["Quelle année le Zambèze et le Chobe n'ont-ils presque pas eu de crue ? Que s'est-il passé en Afrique australe cette année-là ?",
     "La montée annuelle de l'Okavango passe d'environ 2,4 m à Mohembo à 1,9 m à Seronga et 0,6 m à Gunotsoga, et culmine un mois plus tard. Où va l'eau ?",
     "Le Chobe reste plat quand le Zambèze est bas, puis monte avec lui. Qu'est-ce que cela implique pour une courbe de tarage à Kasane ?"])
section("Down the Limpopo", "Le long du Limpopo",
   "The Limpopo is Botswana's border with South Africa and flows only part of the year. From Martin's Drift down to Pont Drift, with the Shashe — on the border with Zimbabwe — which joins it just below the Pont Drift station.",
   "Le Limpopo forme la frontière du Botswana avec l'Afrique du Sud et ne coule qu'une partie de l'année. De Martin's Drift jusqu'à Pont Drift, avec la Shashe — à la frontière du Zimbabwe — qui le rejoint juste en aval de la station de Pont Drift.")
code('vg.compare_stations(["limpopo_martinsdrift", "limpopo_zanzibar", "shashe_tuli", "limpopo_pontdrift"])')
ask(["The Limpopo stations rise in January; the Okavango in 5.4 peaks in April–May. Why are the seasons so different on two rivers of the same country?",
     "Which panels look like a river rising and falling, and which look like noise? Compare Zanzibar with Pont Drift.",
     "Open the Agreement tab for the Shashe and for Pont Drift on the map in 5.3: the two satellites differ by about 4 m and 2 m. What could each one be measuring when the sand bed is almost dry?"],
    ["Les stations du Limpopo montent en janvier ; l'Okavango en 5.4 culmine en avril–mai. Pourquoi les saisons sont-elles si différentes sur deux fleuves du même pays ?",
     "Quels panneaux ressemblent à une rivière qui monte et descend, et lesquels à du bruit ? Comparez Zanzibar et Pont Drift.",
     "Ouvrez l'onglet Accord de la Shashe et de Pont Drift sur la carte de 5.3 : les deux satellites diffèrent d'environ 4 m et 2 m. Que pourrait mesurer chacun quand le lit de sable est presque à sec ?"])

section("Any river in the world", "N'importe quelle rivière du monde",
        """
The map starts with the world's largest rivers. **Zoom in anywhere** and every SWOT reach in the view appears — up to
3,000 at a time, widest first; the line under the map says whether all of them are shown. So every possible location
in the world can be found and clicked. Orange dots are ready-made examples on every continent — from the Niger and
the Amazon to the Karnali in Nepal, the Cimanuk in West Java and the Mississippi; they open instantly, offline.
""",
        """
La carte commence par les plus grands fleuves du monde. **Zoomez n'importe où** et chaque tronçon SWOT de la vue
apparaît — 3 000 au plus à la fois, les plus larges d'abord ; la ligne sous la carte indique s'ils sont tous affichés.
On peut donc trouver et cliquer n'importe quel lieu possible dans le monde. Les points orange sont des exemples prêts
sur tous les continents — du Niger et de l'Amazone à la Karnali au Népal, à la Cimanuk à Java occidental et au
Mississippi ; ils s'ouvrent tout de suite, hors ligne.
""")
code('vg.explore_map("world")')
ask(["Zoom in on your own country. Which rivers have SWOT reaches? Click one near a gauge you know (internet needed).",
     "Open two examples on different continents. Which has the biggest seasonal range, and in which months does each peak?",
     "Which example does SWOT see most often (Levels tab)? Why might rivers far from the equator be seen more often?",
     "For an example with a Discharge tab, is the curve good enough to replace a ground gauge? What would you check first?",
     "Open the Karnali (Nepal) and the Cimanuk (West Java). When is each river highest, and why? Why does the Cimanuk stay near 24 m in the dry season — and what happened at the end of 2023?"],
    ["Zoomez sur votre propre pays. Quelles rivières ont des tronçons SWOT ? Cliquez sur l'un d'eux près d'une station que vous connaissez (internet nécessaire).",
     "Ouvrez deux exemples sur des continents différents. Lequel a la plus grande amplitude saisonnière, et en quels mois chacun culmine-t-il ?",
     "Quel exemple SWOT voit-il le plus souvent (onglet Niveaux) ? Pourquoi les rivières loin de l'équateur seraient-elles vues plus souvent ?",
     "Pour un exemple avec un onglet Débit, la courbe suffit-elle pour remplacer une station au sol ? Que vérifieriez-vous d'abord ?",
     "Ouvrez la Karnali (Népal) et la Cimanuk (Java occidental). Quand chaque rivière est-elle au plus haut, et pourquoi ? Pourquoi la Cimanuk reste-t-elle vers 24 m en saison sèche — et que s'est-il passé fin 2023 ?"])

section("Straight to your region", "Directement à votre région",
        "To jump straight to a region, give a point and a radius — here the Rewa in Fiji. Change the numbers to your own river, then click a dot. This map also reloads the reaches when you pan or zoom.",
        "Pour aller directement à une région, donnez un point et un rayon — ici la Rewa aux Fidji. Mettez les nombres de votre propre rivière, puis cliquez sur un point. Cette carte recharge aussi les tronçons quand vous vous déplacez ou zoomez.")
code("vg.explore_map(lat=-17.96, lon=178.43, radius_km=150)   # ✏️ your region · votre région")

# ------------------------------------------------------------------------------------------------------------------
part("Summary", "Résumé",
   """
- Satellites give water levels above the **EGM2008 geoid**; your gauge reads from its own zero.
- **Cleaning** makes the station: a narrow water mask, slope correction, and the "water flows downhill" check.
- A rating curve is only as good as its **reference discharge** — and satellite levels can expose a biased model.
- Large, slow rivers suit altimetry; small, flashy, tidal rivers still need ground gauges.

For the full method and code, see the trainer notebook `Virtual_River_Gauges_DRC_Fiji.ipynb`.
""",
   """
- Les satellites donnent des niveaux au-dessus du **géoïde EGM2008** ; votre échelle lit depuis son propre zéro.
- Le **nettoyage** fait la station : masque d'eau étroit, correction de pente, et contrôle « l'eau descend ».
- Une courbe de tarage ne vaut que son **débit de référence** — et les niveaux satellitaires peuvent révéler un modèle biaisé.
- Les grands fleuves lents se prêtent à l'altimétrie ; les petites rivières rapides et à marée ont toujours besoin de stations au sol.

Pour la méthode complète et le code, voir le notebook formateur `Virtual_River_Gauges_DRC_Fiji.ipynb`.
""")
code("vg.credits()")

contents = ("**Contents · Sommaire** — " + " · ".join(f"{n} {en}" for n, en, _ in _num["parts"]) + "  \n"
            + "*" + " · ".join(f"{n} {fr}" for n, _, fr in _num["parts"]) + "*")
cells[0].source = cells[0].source.replace("{CONTENTS}", contents)
nb = nbf.v4.new_notebook()
nb.cells = cells
nb.metadata = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
               "language_info": {"name": "python"}, "colab": {"provenance": []}}
nbf.validate(nb)
out = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1] / "Virtual_River_Gauges_Student.ipynb")
nbf.write(nb, out)
print("wrote", out, "with", len(cells), "cells,", sum(c.cell_type == "code" for c in cells), "code cells")
