"""Language switching: English, French or both · Choix de la langue : anglais, français ou les deux."""
import html as _html
import importlib.util
import os
import re
import subprocess
import sys

from .messages import MESSAGES

_LANG = {"value": os.environ.get("VG_LANG", "both")}
MUTED = "#5b6672"
MONTHS = {"en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                 "November", "December"],
          "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
                 "novembre", "décembre"]}


class M:
    """A message used inside another message, translated in the same language.
    Un message utilisé dans un autre message, traduit dans la même langue."""

    def __init__(self, key, **kw):
        self.key, self.kw = key, kw

    def pair(self):
        return _pair(self.key, self.kw)

    def __str__(self):
        return t(self.key, **self.kw)


class Both:
    """Text already written in each language, used inside a message · Texte déjà écrit dans chaque langue"""

    def __init__(self, en, fr):
        self.en, self.fr = en, fr

    def pair(self):
        return self.en, self.fr

    def __str__(self):
        return self.fr if get_language() == "fr" else self.en


class Day:
    """A date written in the language of each message: "16 November 2026" · "16 novembre 2026" ("1er" in French).
    month=True: "November 2026" · "novembre 2026". A missing date is "—"."""

    def __init__(self, when, month=False):
        self.when, self.month = when, month

    def _text(self, lang):
        d = self.when
        if d is None or d != d:                       # None or NaT
            return "—"
        m = f"{MONTHS[lang][d.month - 1]} {d.year}"
        if self.month:
            return m
        return f"{'1er' if lang == 'fr' and d.day == 1 else d.day} {m}"

    def pair(self):
        return self._text("en"), self._text("fr")

    def __str__(self):
        return self._text("fr" if get_language() == "fr" else "en")


def _language_hints():
    """Where the language of this computer can be read, most reliable first."""
    try:                    # Colab: Python runs on a Google computer, so ask the student's browser instead
        if "google.colab" in sys.modules or importlib.util.find_spec("google.colab"):
            from google.colab import output
            yield output.eval_js("navigator.language || ''", timeout_sec=10)
    except Exception:
        pass
    if sys.platform == "darwin":                  # macOS: the language of menus and windows
        for key in ("AppleLanguages", "AppleLocale"):
            try:
                out = subprocess.run(["defaults", "read", "-g", key], capture_output=True, text=True, timeout=5).stdout
                found = re.search(r"[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)*", out)
                if found:
                    yield found.group(0)
            except Exception:
                pass
    elif sys.platform == "win32":                 # Windows: the language of menus and windows
        try:
            import ctypes
            import locale
            yield locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")
        except Exception:
            pass
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):     # Linux, and terminals everywhere
        yield os.environ.get(var, "").split(":")[0]
    try:
        import locale
        yield locale.getlocale()[0] or ""
    except Exception:
        pass


def detect_language():
    """The language of this computer (on Colab: of the web browser): "fr" for French, otherwise "en".

    La langue de cet ordinateur (sur Colab : du navigateur) : "fr" pour le français, sinon "en".
    """
    forced = os.environ.get("VG_LANG", "").lower()
    if forced in ("en", "fr"):
        return forced
    for hint in _language_hints():
        h = str(hint or "").strip().lower()
        if h and h.split(".")[0] not in ("c", "posix"):
            return "fr" if h.startswith("fr") else "en"           # "fr-CD", "fr_FR.UTF-8", "French_France"
    return "en"


def set_language(lang="both"):
    """Choose the language of figures and messages: "en", "fr", "both", or "auto" (the language of this computer).

    Choisir la langue des figures et des messages : "en", "fr", "both" (les deux) ou "auto" (celle de cet ordinateur).
    """
    lang = str(lang).lower()
    if lang not in ("en", "fr", "both", "auto"):
        raise ValueError('Use "en", "fr", "both" or "auto" · Utilisez "en", "fr", "both" ou "auto"')
    if lang == "auto":
        _LANG["value"] = detect_language()
        say("lang_auto")
        return
    _LANG["value"] = lang


def get_language():
    return _LANG["value"]


def _pair(_key, kw):
    en, fr = MESSAGES[_key]
    kw_en = {k: (v.pair()[0] if hasattr(v, "pair") else v) for k, v in kw.items()}       # M and Day: each language
    kw_fr = {k: (v.pair()[1] if hasattr(v, "pair") else v) for k, v in kw.items()}
    return en.format(**kw_en), fr.format(**kw_fr)


def t(_key, sep=" · ", **kw):
    """Text for a short label. In "both" mode English and French are joined by `sep`."""
    en, fr = _pair(_key, kw)
    lang = get_language()
    if lang == "en" or en == fr:
        return en
    if lang == "fr":
        return fr
    return f"{en}{sep}{fr}"


def title(_key, **kw):
    """Figure title: two lines in "both" mode · Titre de figure : deux lignes en mode « both »."""
    return t(_key, sep="\n", **kw)


def html(_key, **kw):
    """A sentence for HTML output: English, then French in muted italics · Phrase pour l'affichage HTML."""
    en, fr = _pair(_key, kw)
    lang = get_language()
    if lang == "en" or en == fr:
        return _html.escape(en)
    if lang == "fr":
        return _html.escape(fr)
    return f'{_html.escape(en)}<br><i style="color:{MUTED}">{_html.escape(fr)}</i>'


def text(en, fr):
    """Notebook text (Markdown) in the chosen language; "both": English, then French as a quote.

    Texte du notebook (Markdown) dans la langue choisie ; « both » : l'anglais, puis le français en citation.
    """
    lang = get_language()
    if lang == "en":
        s = en.strip()
    elif lang == "fr":
        s = fr.strip()
    else:
        s = en.strip() + "\n\n" + "\n".join(("> " + l) if l.strip() else ">" for l in fr.strip().splitlines())
    try:
        from IPython.display import Markdown
        return Markdown(s)
    except ImportError:
        return s


def say(_key, **kw):
    """Print a message in the chosen language · Afficher un message dans la langue choisie."""
    print(t(_key, sep="\n", **kw))


def fmt_int(n):
    """Thousands with a thin space (clear in both languages) · Milliers séparés par une espace fine."""
    return f"{int(n):,}".replace(",", " ")


def fmt_num(x):
    """Small numbers keep a decimal, large ones get thousands spaces · Petits nombres avec une décimale."""
    x = float(x)
    return f"{x:.1f}" if abs(x) < 10 else fmt_int(round(x))
