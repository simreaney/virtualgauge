// The words of the pages in English and French: STRINGS for every basin, REGION_STRINGS for the words of one. The
// band names and the basin's name come from the data file (written from src/virtualgauge/messages.py), so they read
// the same as in the Python package and the notebook.
//
// Language: ?lang=fr or ?lang=en in the address, else the reader's last choice on this page, else the language of
// the web browser: French if it is French, English otherwise.

export const STRINGS = {
  en: {
    locale: "en-GB",
    titleDated: "{name} navigability, {date}",
    language: "Language",
    side: "Navigability summary",
    h1: "Navigability index",
    lede: "0 = the lowest level SWOT has recorded on the reach since July 2023, 100 = the highest.",
    loading: "Loading the river network…",
    loadFailed: "The river data could not be loaded. Reload the page to try again.",
    selected: "Selected reach",
    clear: "Clear",
    basinToday: "The basin today",
    medianIndex: "median index",
    lowWater: 'of river length at low water <span class="soft">(below 40)</span>',
    highWater: 'at high water <span class="soft">(above 60)</span>',
    shareLabel: "Share of river length in each band",
    shareTitle: "{band}: {pct} of river length",
    colIndex: "Index", colReaches: "Reaches", colLength: "River length",
    ports: "River ports",
    portsHint: "Select a port, or any river on the map, for its levels.",
    download: "Download",
    downloadButton: "GeoPackage for QGIS",
    downloadBusy: "Preparing the file…",
    downloadFailed: "The file could not be made: {error}",
    downloadHint: "Every reach and port with the index shown on the map now, in one file. In QGIS (drag the file into its window) the rivers open coloured by their index.",
    downloadPartial: "Reaches not checked yet ({left}) keep their level of {date}.",
    downloadDone: "Saved {file} ({size}).",
    mb: "{n} MB",
    about: "How to read it",
    formula: "index = 100 × (latest level − lowest level) ÷ (highest level − lowest level)",
    aboutText: "Each reach is compared with its own record of water levels from the SWOT satellite. The index says where the river stands between its lowest and highest recorded level. It is not a depth of water and does not show whether a particular boat can pass.",
    aboutData: "The lowest and highest levels come from every good SWOT level between {first} and {last} ({n} of {total} reaches have a record good enough for an index). Your browser then asks NASA's Hydrocron service for the levels measured since, and judges them with the same quality rules. A reach needs a good level from the last {days} days to be coloured.",
    credits: 'Levels: SWOT L2 HR RiverSP reach product, Version D (NASA/CNES, PO.DAAC), through <a href="https://podaac.github.io/hydrocron/" rel="noopener">Hydrocron</a>. River network: SWORD v17b. Made with <a href="https://github.com/simreaney/virtualgauge" rel="noopener">virtualgauge</a>.',
    basemap: "Background map", plain: "Plain", streets: "Streets", satellite: "Satellite",
    lowEnd: "0 · low water", highEnd: "high water · 100",
    attribution: "Levels: SWOT (NASA/CNES) via Hydrocron · rivers: SWORD · borders: Natural Earth",
    unnamed: "Unnamed river",
    tipIndex: "index <b>{index}</b>",
    noIndex: "no index",
    reachSub: "SWOT reach {id}",
    lowest: "lowest", highest: "highest",
    latest: "Latest level", today: "today", daysAgo1: "1 day ago", daysAgo: "{n} days ago", newTag: "new",
    range: "Range", rangeNote: "between lowest and highest",
    record: "Record", goodLevels: "{n} good SWOT levels",
    width: "Width", about_m: "about {n} m",
    newLowest: "This is the lowest level SWOT has recorded here: {m} below the previous lowest.",
    newHighest: "This is the highest level SWOT has recorded here: {m} above the previous highest.",
    checkingReach: "Checking Hydrocron for a newer level…",
    why: {
      "no SWOT data": "No SWOT data for this reach", "not downloaded": "No SWOT data for this reach",
      "never measured": "SWOT has never measured this reach", "too few good levels": "Too few good levels for an index",
      "record too short": "The record is shorter than a year", "range too small": "The range of levels is too small to trust",
      "too noisy": "The levels are too noisy for an index", "no recent level": "No good level in the last {days} days",
    },
    newer1: "1 reach has a newer level than the snapshot of {date}.",
    newer: "{n} reaches have a newer level than the snapshot of {date}.",
    newerNone: "No level newer than the snapshot of {date} so far.",
    checking: "Checking SWOT for new levels: {done} of {total} reaches",
    checkingNote: "{newer} The largest rivers are checked first.",
    pause: "Pause", resume: "Continue", retry: "Try again", again: "Check again",
    unreachable: "Hydrocron cannot be reached",
    unreachableNote: "The map shows the levels saved on {date}.",
    unreachableNoteSome: "The map shows the levels saved on {date}, updated for {n} reaches.",
    paused: "Paused: {done} of {total} reaches checked",
    failed1: "1 reach could not be checked",
    failed: "{n} reaches could not be checked",
    upToDate: "Up to date: every reach checked at {time}",
  },
  fr: {
    locale: "fr-FR",
    titleDated: "Navigabilité — {name}, {date}",
    language: "Langue",
    side: "Résumé de la navigabilité",
    h1: "Indice de navigabilité",
    lede: "0 = le niveau le plus bas enregistré par SWOT sur le tronçon depuis juillet 2023, 100 = le plus haut.",
    loading: "Chargement du réseau de rivières…",
    loadFailed: "Les données des rivières n'ont pas pu être chargées. Rechargez la page pour réessayer.",
    selected: "Tronçon choisi",
    clear: "Effacer",
    basinToday: "Le bassin aujourd'hui",
    medianIndex: "indice médian",
    lowWater: 'de la longueur des rivières en basses eaux <span class="soft">(sous 40)</span>',
    highWater: 'en hautes eaux <span class="soft">(au-dessus de 60)</span>',
    shareLabel: "Part de la longueur des rivières dans chaque classe",
    shareTitle: "{band} : {pct} de la longueur des rivières",
    colIndex: "Indice", colReaches: "Tronçons", colLength: "Longueur",
    ports: "Ports fluviaux",
    portsHint: "Choisissez un port, ou n'importe quelle rivière sur la carte, pour ses niveaux.",
    download: "Télécharger",
    downloadButton: "GeoPackage pour QGIS",
    downloadBusy: "Préparation du fichier…",
    downloadFailed: "Le fichier n'a pas pu être créé : {error}",
    downloadHint: "Tous les tronçons et les ports, avec l'indice affiché sur la carte maintenant, dans un seul fichier. Dans QGIS (glissez le fichier dans sa fenêtre), les rivières s'ouvrent colorées selon leur indice.",
    downloadPartial: "Les tronçons pas encore vérifiés ({left}) gardent leur niveau du {date}.",
    downloadDone: "Enregistré : {file} ({size}).",
    mb: "{n} Mo",
    about: "Comment le lire",
    formula: "indice = 100 × (dernier niveau − niveau le plus bas) ÷ (niveau le plus haut − niveau le plus bas)",
    aboutText: "Chaque tronçon est comparé à sa propre série de niveaux d'eau du satellite SWOT. L'indice dit où en est la rivière entre son niveau le plus bas et son niveau le plus haut enregistrés. Ce n'est pas une profondeur d'eau, et il ne dit pas si un bateau donné peut passer.",
    aboutData: "Les niveaux le plus bas et le plus haut viennent de tous les niveaux SWOT valides entre le {first} et le {last} ({n} tronçons sur {total} ont une série assez bonne pour un indice). Votre navigateur demande ensuite au service Hydrocron de la NASA les niveaux mesurés depuis, et les juge avec les mêmes règles de qualité. Un tronçon doit avoir un niveau valide des {days} derniers jours pour être coloré.",
    credits: 'Niveaux : produit SWOT L2 HR RiverSP reach, version D (NASA/CNES, PO.DAAC), via <a href="https://podaac.github.io/hydrocron/" rel="noopener">Hydrocron</a>. Réseau de rivières : SWORD v17b. Réalisé avec <a href="https://github.com/simreaney/virtualgauge" rel="noopener">virtualgauge</a>.',
    basemap: "Fond de carte", plain: "Simple", streets: "Rues", satellite: "Satellite",
    lowEnd: "0 · basses eaux", highEnd: "hautes eaux · 100",
    attribution: "Niveaux : SWOT (NASA/CNES) via Hydrocron · rivières : SWORD · frontières : Natural Earth",
    unnamed: "Rivière sans nom",
    tipIndex: "indice <b>{index}</b>",
    noIndex: "pas d'indice",
    reachSub: "Tronçon SWOT {id}",
    lowest: "plus bas", highest: "plus haut",
    latest: "Dernier niveau", today: "aujourd'hui", daysAgo1: "il y a 1 jour", daysAgo: "il y a {n} jours", newTag: "nouveau",
    range: "Amplitude", rangeNote: "entre le plus bas et le plus haut",
    record: "Série", goodLevels: "{n} niveaux SWOT valides",
    width: "Largeur", about_m: "environ {n} m",
    newLowest: "C'est le niveau le plus bas que SWOT ait enregistré ici : {m} sous le précédent plus bas.",
    newHighest: "C'est le niveau le plus haut que SWOT ait enregistré ici : {m} au-dessus du précédent plus haut.",
    checkingReach: "Recherche d'un niveau plus récent sur Hydrocron…",
    why: {
      "no SWOT data": "Pas de données SWOT pour ce tronçon", "not downloaded": "Pas de données SWOT pour ce tronçon",
      "never measured": "SWOT n'a jamais mesuré ce tronçon", "too few good levels": "Trop peu de niveaux valides pour un indice",
      "record too short": "La série fait moins d'un an", "range too small": "L'amplitude des niveaux est trop faible pour être fiable",
      "too noisy": "Les niveaux sont trop bruités pour un indice", "no recent level": "Aucun niveau valide dans les {days} derniers jours",
    },
    newer1: "1 tronçon a un niveau plus récent que l'instantané du {date}.",
    newer: "{n} tronçons ont un niveau plus récent que l'instantané du {date}.",
    newerNone: "Aucun niveau plus récent que l'instantané du {date} pour l'instant.",
    checking: "Recherche de nouveaux niveaux SWOT : {done} tronçons sur {total}",
    checkingNote: "{newer} Les plus grandes rivières sont vérifiées d'abord.",
    pause: "Pause", resume: "Continuer", retry: "Réessayer", again: "Vérifier à nouveau",
    unreachable: "Hydrocron est injoignable",
    unreachableNote: "La carte montre les niveaux enregistrés le {date}.",
    unreachableNoteSome: "La carte montre les niveaux enregistrés le {date}, mis à jour pour {n} tronçons.",
    paused: "En pause : {done} tronçons vérifiés sur {total}",
    failed1: "1 tronçon n'a pas pu être vérifié",
    failed: "{n} tronçons n'ont pas pu être vérifiés",
    upToDate: "À jour : tous les tronçons vérifiés à {time}",
  },
};

// The words that differ from basin to basin. Each page names its basin in <html data-region="…">, which is also the
// name of its data file (data/<region>.json) and its key in src/virtualgauge/navigation.py REGIONS.
export const REGION_STRINGS = {
  congo: {
    en: {
      title: "Congo basin navigability — live from SWOT",
      description: "How navigable are the rivers of the Congo basin today? A navigability index for 4,444 river reaches, updated in your browser from the latest SWOT satellite water levels.",
      eyebrow: "Congo basin · SWOT satellite",
      mapLabel: "Map of the navigability index of the Congo basin",
      otherBasin: 'The same map for the <a href="amazon.html">Amazon basin</a>.',
    },
    fr: {
      title: "Navigabilité du bassin du Congo — en direct depuis SWOT",
      description: "Les rivières du bassin du Congo sont-elles navigables aujourd'hui ? Un indice de navigabilité pour 4 444 tronçons de rivière, mis à jour dans votre navigateur à partir des derniers niveaux d'eau du satellite SWOT.",
      eyebrow: "Bassin du Congo · satellite SWOT",
      mapLabel: "Carte de l'indice de navigabilité du bassin du Congo",
      otherBasin: 'La même carte pour le <a href="amazon.html">bassin de l\'Amazone</a>.',
    },
  },
  amazon: {
    en: {
      title: "Amazon basin navigability — live from SWOT",
      description: "How navigable are the rivers of the Amazon basin today? A navigability index for 16,957 river reaches, updated in your browser from the latest SWOT satellite water levels.",
      eyebrow: "Amazon basin · SWOT satellite",
      mapLabel: "Map of the navigability index of the Amazon basin",
      otherBasin: 'The same map for the <a href="./">Congo basin</a>.',
    },
    fr: {
      title: "Navigabilité du bassin de l'Amazone — en direct depuis SWOT",
      description: "Les rivières du bassin de l'Amazone sont-elles navigables aujourd'hui ? Un indice de navigabilité pour 16 957 tronçons de rivière, mis à jour dans votre navigateur à partir des derniers niveaux d'eau du satellite SWOT.",
      eyebrow: "Bassin de l'Amazone · satellite SWOT",
      mapLabel: "Carte de l'indice de navigabilité du bassin de l'Amazone",
      otherBasin: 'La même carte pour le <a href="./">bassin du Congo</a>.',
    },
  },
};

const SAVED = "vg-navigability-lang";

/** "fr" or "en" for a list of preferred languages such as navigator.languages: the first one decides. */
export function fromBrowser(languages) {
  const first = (languages || []).find((l) => l) || "en";
  return String(first).toLowerCase().startsWith("fr") ? "fr" : "en";
}

/** The language of the page: ?lang=…, else the reader's last choice, else the browser's language. */
export function pickLanguage() {
  const asked = new URLSearchParams(location.search).get("lang");
  if (asked === "en" || asked === "fr") return asked;
  try {
    const saved = localStorage.getItem(SAVED);
    if (saved === "en" || saved === "fr") return saved;
  } catch { /* storage blocked: use the browser's language */ }
  return fromBrowser(navigator.languages?.length ? navigator.languages : [navigator.language]);
}

export function saveLanguage(lang) {
  try { localStorage.setItem(SAVED, lang); } catch { /* private window: the choice lasts for this visit */ }
}

/** A function giving the words of `lang` on the page of `region`, with {placeholders} filled in. */
export function translator(lang, region) {
  const both = (l) => ({ ...STRINGS[l], ...REGION_STRINGS[region]?.[l] });
  const words = both(STRINGS[lang] ? lang : "en"), english = both("en");
  return (key, vars = {}) => {
    const path = key.split(".");
    let s = path.reduce((o, k) => (o == null ? o : o[k]), words);
    if (s == null) s = path.reduce((o, k) => (o == null ? o : o[k]), english) ?? key;
    return String(s).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
  };
}
