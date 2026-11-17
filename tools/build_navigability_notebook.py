"""Build the Congo navigability student notebook (English or French, results first, one line of code per step).

The text of the notebook is written here in English and in French. It is shown by small hidden cells, in the language
chosen in the notebook's 'Language' cell: "auto" (the default) takes the language of the computer — on Colab, of the
web browser. Only the title cell is written in both languages, since it is read before anything runs.

Usage: python tools/build_navigability_notebook.py [output.ipynb]
"""
import sys
from pathlib import Path

import nbformat as nbf

items = []            # nbformat cells, or ["text", English, French] for the text shown in the chosen language
HIDE = {"jupyter": {"source_hidden": True}, "cellView": "form", "tags": ["hide-input"]}
NAME = "Congo_Navigability_Student.ipynb"


def text(en, fr, new_cell=False):
    """Text in the chosen language. Text that follows text goes into the same cell, unless new_cell."""
    en, fr = en.strip(), fr.strip()
    assert '"""' not in en + fr and not en.endswith("\\") and not fr.endswith("\\")
    if items and isinstance(items[-1], list) and not new_cell:
        items[-1][1] += "\n\n" + en
        items[-1][2] += "\n\n" + fr
    else:
        items.append(["text", en, fr])


_num = {"part": 0, "sec": 0, "parts": []}


def part(en_title, fr_title, en="", fr=""):
    """A numbered part: 'Part 3 — …' · 'Partie 3 — …'"""
    _num["part"] += 1
    _num["sec"] = 0
    n = _num["part"]
    _num["parts"].append((n, en_title, fr_title))
    text(f"## Part {n} — {en_title}\n\n{en.strip()}", f"## Partie {n} — {fr_title}\n\n{fr.strip()}", new_cell=True)


def section(en_title, fr_title, en="", fr=""):
    """A numbered section inside the current part: '3.2 …'"""
    _num["sec"] += 1
    n = f"{_num['part']}.{_num['sec']}"
    text(f"### {n} {en_title}\n\n{en.strip()}", f"### {n} {fr_title}\n\n{fr.strip()}")


def ask(en, fr):
    """'What do you notice?' questions"""
    assert len(en) == len(fr)
    text("💬 **What do you notice?**\n\n" + "\n".join(f"- {q}" for q in en),
         "💬 **Que remarquez-vous ?**\n\n" + "\n".join(f"- {q}" for q in fr))


def code(src, hidden=False):
    c = nbf.v4.new_code_cell(src.strip())
    if hidden:
        c.metadata.update(HIDE)
    items.append(c)


def text_cell(en, fr):
    c = nbf.v4.new_code_cell(f'#@title\nvg.text(r"""\n{en}\n""", r"""\n{fr}\n""")')
    c.metadata.update(HIDE)
    return c


# ------------------------------------------------------------------------------------------------------------------
items.append(nbf.v4.new_markdown_cell(rf"""
# How navigable is the Congo today? · Le Congo est-il navigable aujourd'hui ?

**Start here:** menu **Run ▸ Run all** (Colab: **Runtime ▸ Run all**). The notebook then appears in the language of
your computer, English or French; to change it, see the *Language* cell below.

**Commencez ici :** menu **Exécuter ▸ Exécuter toutes les cellules** (Colab : **Exécution ▸ Tout exécuter**). Le
notebook s'affiche alors dans la langue de votre ordinateur, français ou anglais ; pour la changer, voir la cellule
*Langue* ci-dessous.

{{CONTENTS}}

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/simreaney/virtualgauge/blob/main/{NAME})
"""))

code(r'''
#@title Setup · Installation { display-mode: "form" }
import glob, importlib, importlib.util, subprocess, sys
from pathlib import Path


def _needs_install():
    spec = importlib.util.find_spec("virtualgauge")            # finds the package without importing it
    return spec is None or not (Path(spec.origin).parent / "geopackage.py").exists()


if _needs_install():                      # install once (Colab / new computer)
    REPO_URL = "https://github.com/simreaney/virtualgauge"
    here = Path.cwd()
    local = [str(here)] if (here / "src" / "virtualgauge" / "geopackage.py").exists() else []   # this repository
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
                           "and run this cell again. · Installation impossible : déposez le fichier "
                           "virtualgauge-*.whl (panneau Fichiers) et relancez cette cellule.")
import virtualgauge as vg
print(f"virtualgauge {vg.__version__} — ready · prêt")
''', hidden=True)

code(r'''
#@title Language · Langue
language = "auto"  #@param ["auto", "en", "fr"]
vg.set_language(language)   # ✏️ "auto" = this computer's language · la langue de cet ordinateur; "en"; "fr"
''')

text("""
**Download the SWOT water levels of every river reach in the Congo basin, find the lowest and highest level each reach
has had since July 2023, and map where the rivers stand today between those two.**

The first run downloads the SWOT record of all 4,444 river reaches of the basin from NASA's Hydrocron service — about
10 minutes, no account needed. Later runs re-use the saved files and only download again what is more than three days
old. Without internet the notebook uses the copy shipped with the `virtualgauge` package (downloaded 16 November 2026).
About 60 minutes.

✏️ a line you can change — 🧪 try it — 💬 questions to discuss
""", """
**Télécharger les niveaux d'eau SWOT de chaque tronçon de rivière du bassin du Congo, trouver le niveau le plus bas et
le plus haut de chaque tronçon depuis juillet 2023, et cartographier où en sont les rivières aujourd'hui entre les
deux.**

La première exécution télécharge la série SWOT des 4 444 tronçons de rivière du bassin depuis le service Hydrocron de
la NASA — environ 10 minutes, sans compte. Les exécutions suivantes réutilisent les fichiers enregistrés et ne
retéléchargent que ce qui a plus de trois jours. Sans internet, le notebook utilise la copie fournie avec le package
`virtualgauge` (téléchargée le 16 novembre 2026). Durée : environ 60 minutes.

✏️ une ligne que vous pouvez modifier — 🧪 à essayer — 💬 questions à discuter
""")

# ------------------------------------------------------------------------------------------------------------------
part("From water level to navigability", "Du niveau d'eau à la navigabilité", """
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
""", """
Le Congo et ses affluents portent bateaux, barges et bacs sur des milliers de kilomètres : de Kinshasa jusqu'à
Kisangani (environ 1 700 km), sur le Kasaï jusqu'à Ilebo, sur l'Oubangui jusqu'à Bangui, sur la Sangha jusqu'à Ouesso,
et sur le Lualaba en amont de Kisangani. En aval de Kinshasa, les chutes Livingstone barrent la route du port maritime
de Matadi ; juste en amont de Kisangani, les chutes Boyoma barrent la route vers l'amont.

Ce dont un bateau a besoin, c'est de **profondeur**, surtout aux endroits les moins profonds — bancs de sable et seuils
rocheux. Quand la rivière est basse, les barges doivent moins charger, ou s'arrêter. Personne ne mesure la profondeur
sur tout le bassin, mais le satellite **SWOT** (NASA et CNES, depuis juillet 2023) mesure la **hauteur de la surface de
l'eau** sur chaque tronçon de rivière de plus d'environ 100 m de large, deux à quatre fois tous les 21 jours. Sur un
tronçon donné, une surface de l'eau plus haute signifie plus d'eau au-dessus des hauts-fonds.

Nous comparons donc chaque tronçon **avec lui-même** : où en est son niveau d'eau aujourd'hui, entre le niveau le plus
bas et le niveau le plus haut que SWOT y a enregistrés ?

> **indice de navigabilité = 100 × (dernier niveau − niveau le plus bas) ÷ (niveau le plus haut − niveau le plus bas)**

| indice | | |
|---|---|---|
| 0–20 | très mauvaise | la rivière est aussi basse que SWOT l'a jamais vue ici |
| 20–40 | mauvaise | |
| 40–60 | moyenne | |
| 60–80 | bonne | |
| 80–100 | très bonne | la rivière est aussi haute que SWOT l'a jamais vue ici |
""")
ask(["Is high water always better for boats? Think of the current, floating vegetation, flooded ports and bridges.",
     "Why compare each reach with its own record, instead of comparing the water level of different rivers?",
     "The record starts in July 2023. In December 2023 the Congo at Kinshasa rose to its highest level since 1961. "
     "What does that do to the ‘highest level’ of the reaches near Kinshasa — and to their index in later years?",
     "The index says nothing about rapids or waterfalls. Which parts of the Congo are never navigable, whatever the index?"],
    ["Les hautes eaux sont-elles toujours meilleures pour les bateaux ? Pensez au courant, à la végétation flottante, "
     "aux ports inondés et aux ponts.",
     "Pourquoi comparer chaque tronçon avec sa propre série, plutôt que de comparer le niveau d'eau de rivières "
     "différentes ?",
     "La série commence en juillet 2023. En décembre 2023, le Congo à Kinshasa est monté à son plus haut niveau depuis "
     "1961. Qu'est-ce que cela change au « niveau le plus haut » des tronçons proches de Kinshasa — et à leur indice les "
     "années suivantes ?",
     "L'indice ne dit rien des rapides ni des chutes. Quelles parties du Congo ne sont jamais navigables, quel que soit "
     "l'indice ?"])

# ------------------------------------------------------------------------------------------------------------------
part("Every SWOT reach in the Congo basin", "Tous les tronçons SWOT du bassin du Congo", """
SWOT reports one water level per **reach** — a stretch of river about 10 km long, from the SWORD river database. The
Congo basin has 4,444 of them (narrow streams to the 4 km wide main river), and each has its own record on Hydrocron.
""", """
SWOT donne un niveau d'eau par **tronçon** — un morceau de rivière d'environ 10 km, issu de la base de rivières SWORD.
Le bassin du Congo en compte 4 444 (des cours d'eau étroits jusqu'au fleuve principal, large de 4 km), et chacun a sa
propre série sur Hydrocron.
""")
section("Download", "Téléchargement", """
This one line downloads the SWOT record of every reach, eight at a time, and cleans it. The first time it takes about
10 minutes; a progress line shows how far it has got. If it stops (or you stop it), run the cell again: it continues
where it stopped. The files are saved in the folder `cache/survey_reaches/`, one per reach; `update_days=3` sets how
old (in days) a saved file may be before it is downloaded again.
""", """
Cette seule ligne télécharge la série SWOT de chaque tronçon, huit à la fois, et la nettoie. La première fois, cela
prend environ 10 minutes ; une ligne de progression montre où on en est. Si cela s'arrête (ou si vous l'arrêtez),
relancez la cellule : le téléchargement reprend là où il s'est arrêté. Les fichiers sont enregistrés dans le dossier
`cache/survey_reaches/`, un par tronçon ; `update_days=3` fixe l'âge (en jours) au-delà duquel un fichier enregistré est
retéléchargé.
""")
code('congo = vg.river_survey("congo")   # ✏️ update_days=3\ncongo')

section("Which reaches does SWOT measure?", "Quels tronçons SWOT mesure-t-il ?", """
The colour shows how many good SWOT levels each reach has. Pale grey: no good level at all.
""", """
La couleur montre combien de niveaux SWOT valides a chaque tronçon. Gris pâle : aucun niveau valide.
""")
code("congo.coverage()")
ask(["Which rivers have the most levels? Which have none? Is it a matter of width?",
     "Find the stretch of the Congo between Mbandaka and Bumba (around 19–22° E, 1–2° N) with few levels. "
     "The river is very wide there, with many islands and channels. Why might that be hard for SWOT?"],
    ["Quelles rivières ont le plus de niveaux ? Lesquelles n'en ont aucun ? Est-ce une question de largeur ?",
     "Trouvez la partie du Congo entre Mbandaka et Bumba (vers 19–22° E, 1–2° N) qui a peu de niveaux. Le fleuve y est "
     "très large, avec de nombreuses îles et de nombreux chenaux. Pourquoi cela pourrait-il être difficile pour SWOT ?"])

section("Which levels can we trust?", "À quels niveaux peut-on se fier ?", """
As in the virtual gauge notebook, every level that is removed has a written reason: a poor quality flag, a level far
from all the other levels of its reach, or a **spike** — a level that jumps away from the levels just before and after
it. Rivers rise and fall slowly; a level 2 m away from levels measured a few days earlier is an error, not a flood.
""", """
Comme dans le notebook des stations virtuelles, chaque niveau retiré a une raison écrite : un mauvais indicateur de
qualité, un niveau loin de tous les autres niveaux de son tronçon, ou un **pic** — un niveau qui s'écarte des niveaux
juste avant et juste après lui. Les rivières montent et descendent lentement ; un niveau à 2 m des niveaux mesurés
quelques jours plus tôt est une erreur, pas une crue.
""")
code("congo.cleaning()")
ask(["What share of the SWOT levels is kept?",
     "Why is it important to remove spikes *before* we look for the lowest and the highest level?"],
    ["Quelle part des niveaux SWOT est gardée ?",
     "Pourquoi est-il important de retirer les pics *avant* de chercher le niveau le plus bas et le plus haut ?"])

# ------------------------------------------------------------------------------------------------------------------
part("The lowest and highest recorded levels", "Les niveaux les plus bas et les plus hauts enregistrés", """
For each reach: the lowest and the highest good level since July 2023, and the **range** between them. A reach gets a
range only if its record can be trusted: enough good levels, spread over at least a year (so that low and high water
are both in it), and levels that do not jump around from one pass to the next (*too noisy*).
""", """
Pour chaque tronçon : le niveau valide le plus bas et le plus haut depuis juillet 2023, et l'**amplitude** entre les
deux. Un tronçon n'a une amplitude que si sa série est fiable : assez de niveaux valides, répartis sur au moins un an
(pour que les basses et les hautes eaux y soient toutes les deux), et des niveaux qui ne sautent pas d'un passage à
l'autre (*trop bruité*).
""")
code("congo.ranges()")
ask(["Which rivers have the largest range? Which the smallest? Why might the range of a river change along its course?",
     "Most reaches with no range are narrow. Why is a narrow river harder for SWOT?"],
    ["Quelles rivières ont la plus grande amplitude ? Lesquelles la plus petite ? Pourquoi l'amplitude d'une rivière "
     "pourrait-elle changer le long de son cours ?",
     "La plupart des tronçons sans amplitude sont étroits. Pourquoi une rivière étroite est-elle plus difficile pour "
     "SWOT ?"])

section("One reach: the Congo at Mbandaka", "Un tronçon : le Congo à Mbandaka", """
Every good level (blue), the levels removed by the cleaning (grey crosses), the lowest and highest recorded level
(dashed), and the latest level, coloured by its index.
""", """
Chaque niveau valide (en bleu), les niveaux retirés par le nettoyage (croix grises), le niveau le plus bas et le plus
haut enregistrés (tirets), et le dernier niveau, coloré selon son indice.
""")
code('congo.reach("13273000011")   # ✏️ any reach ID (map, Part 4) · tout identifiant de tronçon (carte, partie 4)')
ask(["When was the highest level recorded, and the lowest? Do they match what you know of the Congo's seasons?",
     "Each SWOT level has an error of about 10 cm. How much does that move the index of this reach?"],
    ["Quand le niveau le plus haut a-t-il été enregistré, et le plus bas ? Cela correspond-il à ce que vous savez des "
     "saisons du Congo ?",
     "Chaque niveau SWOT a une erreur d'environ 10 cm. De combien cela déplace-t-il l'indice de ce tronçon ?"])

section("🧪 A harder reach: the Congo at Bumba", "🧪 Un tronçon plus difficile : le Congo à Bumba")
code('congo.reach("13275700241")')
ask(["Compare this record with Mbandaka. Which do you trust more, and why?",
     "The lowest and highest levels are each one single measurement. What happens to the index of every later date "
     "if one of them is wrong?"],
    ["Comparez cette série avec celle de Mbandaka. À laquelle faites-vous le plus confiance, et pourquoi ?",
     "Le niveau le plus bas et le plus haut sont chacun une seule mesure. Qu'arrive-t-il à l'indice de toutes les dates "
     "suivantes si l'un des deux est faux ?"])

# ------------------------------------------------------------------------------------------------------------------
part("The navigability of the Congo today", "La navigabilité du Congo aujourd'hui", """
Each reach gets an index from its **latest** good level — if that level is at most 30 days old (SWOT passes every few
days to weeks, so ‘today’ really means ‘the last few weeks’). Reaches with no trusted range, or no recent level, are
pale grey.
""", """
Chaque tronçon reçoit un indice à partir de son **dernier** niveau valide — si ce niveau a au plus 30 jours (SWOT passe
tous les quelques jours à quelques semaines, donc « aujourd'hui » veut dire en fait « ces dernières semaines »). Les
tronçons sans amplitude fiable, ou sans niveau récent, sont en gris pâle.
""")
code("congo.navigability()")
ask(["Where is the water low today, and where is it high? Do rivers north and south of the equator differ?",
     "The Ubangi, the Sangha and the Uele drain the north of the basin; the Kasai and the Lualaba the south. "
     "Their rainy seasons come at different times of year. How does the map show that?",
     "How much of the river length is below 40? Would barges on the main river be loaded fully today?"],
    ["Où l'eau est-elle basse aujourd'hui, et où est-elle haute ? Les rivières au nord et au sud de l'équateur "
     "diffèrent-elles ?",
     "L'Oubangui, la Sangha et l'Uélé drainent le nord du bassin ; le Kasaï et le Lualaba, le sud. Leurs saisons des "
     "pluies ne tombent pas au même moment de l'année. Comment la carte le montre-t-elle ?",
     "Quelle part de la longueur des rivières est sous 40 ? Les barges du fleuve principal seraient-elles chargées à "
     "plein aujourd'hui ?"])

section("Interactive map", "Carte interactive", """
Zoom in and click a river for its numbers: index, latest level and date, lowest and highest level, and the reach ID
(to use in `congo.reach(...)`). The black dots are river ports. The layer button (top right) changes the background.
""", """
Zoomez et cliquez sur une rivière pour ses chiffres : indice, dernier niveau et sa date, niveau le plus bas et le plus
haut, et l'identifiant du tronçon (à utiliser dans `congo.reach(...)`). Les points noirs sont les ports fluviaux. Le
bouton des couches (en haut à droite) change le fond de carte.
""")
code("congo.map()")

# ------------------------------------------------------------------------------------------------------------------
part("Along the river and at the ports", "Le long du fleuve et aux ports")
section("From Kindu to the sea", "De Kindu à la mer", """
The Lualaba and the Congo, reach by reach from Kindu to the Atlantic. Top: the range of each reach (blue) and where its
latest level stands above the lowest. Bottom: the index.
""", """
Le Lualaba et le Congo, tronçon par tronçon, de Kindu à l'Atlantique. En haut : l'amplitude de chaque tronçon (en bleu)
et la hauteur de son dernier niveau au-dessus du plus bas. En bas : l'indice.
""")
code("congo.profile()")
ask(["Where along the river is the range largest? (Hint: what lies between Kinshasa and the sea?)",
     "Is the index the same all along the river today? Where does it change, and which tributaries join there?"],
    ["Où, le long du fleuve, l'amplitude est-elle la plus grande ? (Piste : qu'y a-t-il entre Kinshasa et la mer ?)",
     "L'indice est-il le même tout le long du fleuve aujourd'hui ? Où change-t-il, et quels affluents s'y jettent ?"])

section("River ports", "Ports fluviaux", """
The index of every SWOT level since July 2023, at the reach nearest each port. The large dot is the latest level.
""", """
L'indice de chaque niveau SWOT depuis juillet 2023, au tronçon le plus proche de chaque port. Le gros point est le
dernier niveau.
""")
code("congo.ports()")
ask(["In which months is the water lowest at Bangui? At Ilebo? At Kinshasa?",
     "At Kinshasa, the Congo receives water from both hemispheres. How does that show in its record, compared with "
     "Bangui or Ilebo?",
     "A barge company plans a trip from Kinshasa to Bangui. Which months would you advise, and why?"],
    ["En quels mois l'eau est-elle la plus basse à Bangui ? À Ilebo ? À Kinshasa ?",
     "À Kinshasa, le Congo reçoit l'eau des deux hémisphères. Comment cela se voit-il dans sa série, comparée à celles "
     "de Bangui ou d'Ilebo ?",
     "Une compagnie de barges prévoit un voyage de Kinshasa à Bangui. Quels mois lui conseilleriez-vous, et pourquoi ?"])

# ------------------------------------------------------------------------------------------------------------------
part("Through time", "Au fil du temps", """
The same index on the first of every month: which share of the river length was at very poor, poor, fair, good or very
good water.
""", """
Le même indice le premier de chaque mois : quelle part de la longueur des rivières était en navigabilité très mauvaise,
mauvaise, moyenne, bonne ou très bonne.
""")
code("congo.history()")
ask(["When was the water lowest across the basin? Is today unusual?",
     "Why is the high water of December 2023 – January 2024 so dark blue, and never again as dark?"],
    ["Quand l'eau était-elle la plus basse sur l'ensemble du bassin ? La situation d'aujourd'hui est-elle inhabituelle ?",
     "Pourquoi les hautes eaux de décembre 2023 – janvier 2024 sont-elles si bleu foncé, et plus jamais aussi foncées "
     "ensuite ?"])
section("🧪 The map on another date", "🧪 La carte à une autre date",
        "Any date since late 2023 — for instance the low water of mid-2025:",
        "N'importe quelle date depuis fin 2023 — par exemple les basses eaux de la mi-2025 :")
code('congo.navigability("2025-08-01")   # ✏️ "YYYY-MM-DD"')

# ------------------------------------------------------------------------------------------------------------------
part("Change the settings", "Changer les réglages", """
Every setting is a keyword of `congo.with_settings(...)` (or of `vg.river_survey`). The data are already downloaded, so
this is quick. Three tasks:

1. Allow an older ‘latest level’ (`max_age_days=60`). How many more reaches get an index? Is that a fair map of *today*?
2. Remove levels with a lot of **dark water** (`max_dark_frac=0.5`: more than half of the reach gave too little radar
   echo). What happens to the records at Bumba and at Ouesso?
3. Be stricter about noisy reaches (`max_noise_frac=0.1`). Which rivers lose their index?
""", """
Chaque réglage est un mot-clé de `congo.with_settings(...)` (ou de `vg.river_survey`). Les données sont déjà
téléchargées, donc c'est rapide. Trois tâches :

1. Acceptez un « dernier niveau » plus ancien (`max_age_days=60`). Combien de tronçons de plus reçoivent un indice ?
   Est-ce une carte juste d'*aujourd'hui* ?
2. Retirez les niveaux avec beaucoup d'**eau sombre** (`max_dark_frac=0.5` : plus de la moitié du tronçon a donné trop
   peu d'écho radar). Qu'arrive-t-il aux séries de Bumba et d'Ouesso ?
3. Soyez plus strict avec les tronçons bruités (`max_noise_frac=0.1`). Quelles rivières perdent leur indice ?
""")
code('congo.with_settings(max_age_days=60).navigability()   # ✏️')
code('congo.with_settings(max_dark_frac=0.5).ports()   # ✏️')
code('congo.with_settings(max_noise_frac=0.1).navigability()   # ✏️')
text("All the settings, with their default values:", "Tous les réglages, avec leurs valeurs par défaut :")
code("vg.SurveyParams()")

section("🧪 Your own list of reaches", "🧪 Votre propre liste de tronçons", """
Any list of SWOT reach IDs — here every reach within 60 km of Kinshasa and Brazzaville. Reaches already downloaded are
not downloaded again.
""", """
N'importe quelle liste d'identifiants de tronçons SWOT — ici tous les tronçons à moins de 60 km de Kinshasa et de
Brazzaville. Les tronçons déjà téléchargés ne sont pas retéléchargés.
""")
code('near = vg.reaches_near(-4.3, 15.3, radius_km=60, n=300).values["reach_ids"]   # ✏️ latitude, longitude\n'
     'pool = vg.river_survey(reach_ids=near, name="Kinshasa – Brazzaville")\n'
     'pool.navigability()')

# ------------------------------------------------------------------------------------------------------------------
part("Export and summary", "Export et résumé", """
Save in the folder `outputs/`: the table of every reach (CSV: river, lowest and highest level, range, latest level,
index), and the rivers with their index as a **GeoPackage** (`.gpkg`: one file with the rivers and the ports — open it
in QGIS and the rivers appear already coloured by their index) and as GeoJSON.
""", """
Enregistrez dans le dossier `outputs/` : le tableau de tous les tronçons (CSV : rivière, niveau le plus bas et le plus
haut, amplitude, dernier niveau, indice), et les rivières avec leur indice en **GeoPackage** (`.gpkg` : un seul fichier
avec les rivières et les ports — ouvrez-le dans QGIS et les rivières apparaissent déjà colorées selon leur indice) et
en GeoJSON.
""")
code("congo.export()")
section("Download the GeoPackage", "Télécharger le GeoPackage", """
On **Colab** the notebook runs on a Google computer, so the files in `outputs/` are not on yours: this line makes your
browser download the GeoPackage (look in your *Downloads* folder). On your own computer the file is already in
`outputs/`; the line shows where, with a link. `levels=True` also puts in every SWOT level (a table of about 480,000
rows, 30 MB more).
""", """
Sur **Colab**, le notebook tourne sur un ordinateur de Google : les fichiers de `outputs/` ne sont donc pas sur le
vôtre. Cette ligne fait télécharger le GeoPackage par votre navigateur (regardez dans votre dossier *Téléchargements*).
Sur votre propre ordinateur, le fichier est déjà dans `outputs/` ; la ligne indique où, avec un lien. `levels=True`
y ajoute tous les niveaux SWOT (un tableau d'environ 480 000 lignes, 30 Mo de plus).
""")
code("congo.download_geopackage()   # ✏️ levels=True")
text("The ten reaches with the lowest water today, as a table you can sort and filter (pandas):",
     "Les dix tronçons aux eaux les plus basses aujourd'hui, dans un tableau que vous pouvez trier et filtrer (pandas) :")
code('table = congo.to_dataframe()\n'
     'table[table.width_m > 300].sort_values("index")[["reach_id", "river_name", "width_m", "range_m", "now_date", "index"]].head(10)')
text(new_cell=True, en="""
## Summary

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
""", fr="""
## Résumé

- SWOT mesure le **niveau d'eau** de chaque tronçon de rivière du bassin, pas sa profondeur. Comparer chaque tronçon
  avec son propre niveau le plus bas et le plus haut transforme ces hauteurs en un **indice de navigabilité** simple.
- L'indice ne vaut que ce que vaut la **série** : trois ans, avec une crue exceptionnelle au début, et le niveau le plus
  bas et le plus haut sont chacun une seule mesure — d'où l'importance de nettoyer d'abord les niveaux.
- Les **rivières étroites**, les rivières très larges à chenaux multiples et l'**eau sombre** donnent des séries
  bruitées ; ces tronçons n'ont pas d'indice.
- « Aujourd'hui » veut dire **ces dernières semaines** : SWOT passe sur chaque tronçon quelques fois tous les 21 jours.
- Ce que l'indice ne peut pas dire : la vraie profondeur au-dessus des bancs de sable, le tirant d'eau des bateaux, les
  rapides et les chutes, ou si les hautes eaux sont trop rapides ou trop hautes sous les ponts. Les connaissances
  locales et les relevés des échelles limnimétriques le complètent.

Pour les niveaux d'eau et le débit en un lieu, voir `Virtual_River_Gauges_Student.ipynb` ; pour les cartes de crue,
`SWOT_Flood_Depth_Student.ipynb` (en anglais).
""")
code("vg.credits()")

contents = ("**Contents** — " + " · ".join(f"{n} {en}" for n, en, _ in _num["parts"]) + "\n\n"
            + "**Sommaire** — " + " · ".join(f"{n} {fr}" for n, _, fr in _num["parts"]))
cells = [text_cell(i[1], i[2]) if isinstance(i, list) else i for i in items]
cells[0].source = cells[0].source.replace("{CONTENTS}", contents)
nb = nbf.v4.new_notebook()
nb.cells = cells
nb.metadata = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
               "language_info": {"name": "python"}, "colab": {"provenance": []}}
nbf.validate(nb)
out = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1] / NAME)
nbf.write(nb, out)
print("wrote", out, "with", len(cells), "cells,", sum(c.cell_type == "code" for c in cells), "code cells,",
      sum(isinstance(i, list) for i in items), "of them text in the chosen language")
