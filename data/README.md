# data/ — optional input files · fichiers d'entrée facultatifs

The notebook runs without any file here. Add files to unlock the optional steps.
Le notebook fonctionne sans aucun fichier ici. Ajoutez des fichiers pour activer les étapes facultatives.

## 1. Your gauge data · Vos données de station

File name: the `gauge_file` setting of the site, e.g. `gauge_congo_kinshasa.csv`, `gauge_rewa_fiji.csv`, `gauge_my_river.csv`.
Nom du fichier : le paramètre `gauge_file` du site, par ex. `gauge_congo_kinshasa.csv`, `gauge_rewa_fiji.csv`, `gauge_my_river.csv`.

Format: CSV, comma-separated, one row per day (several rows on the same day are averaged). Leave a cell empty if a value is missing.
Format : CSV séparé par des virgules, une ligne par jour (plusieurs lignes le même jour sont moyennées). Laissez une case vide si une valeur manque.

```
date,stage_m,discharge_m3s
2024-01-03,6.12,61200
2024-01-04,6.15,
2024-01-05,,61900
```

| Column · Colonne | Meaning · Signification |
|---|---|
| `date` | YYYY-MM-DD (UTC day · jour UTC) |
| `stage_m` | gauge reading in metres above the gauge zero · lecture d'échelle en mètres au-dessus du zéro |
| `discharge_m3s` | discharge in m³/s (from gauging or your existing rating) · débit en m³/s (jaugeage ou courbe existante) |

The notebook estimates the offset between the gauge zero and the EGM2008 geoid itself.
Le notebook estime lui-même le décalage entre le zéro de l'échelle et le géoïde EGM2008.

## 2. GRDC daily discharge · Débits journaliers GRDC

For the Congo at Kinshasa (GRDC station 1147010, daily data to 2010):
Pour le Congo à Kinshasa (station GRDC 1147010, données journalières jusqu'en 2010) :

1. Go to · Allez sur https://portal.grdc.bafg.de
2. Select station 1147010, daily data, and submit the request form (free). The download link arrives by e-mail.
   Sélectionnez la station 1147010, données journalières, et envoyez le formulaire (gratuit). Le lien arrive par courriel.
3. Save the daily text file here as `grdc_1147010.txt`.
   Enregistrez le fichier texte journalier ici sous `grdc_1147010.txt`.

GRDC data may not be redistributed: each user must request their own copy.
Les données GRDC ne peuvent pas être rediffusées : chaque utilisateur doit demander sa propre copie.
