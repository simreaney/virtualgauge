"""Language switching: English, French or both · Choix de la langue : anglais, français ou les deux."""
import html as _html
import os

from .messages import MESSAGES

_LANG = {"value": os.environ.get("VG_LANG", "both")}
MUTED = "#5b6672"


class M:
    """A message used inside another message, translated in the same language.
    Un message utilisé dans un autre message, traduit dans la même langue."""

    def __init__(self, key, **kw):
        self.key, self.kw = key, kw

    def pair(self):
        return _pair(self.key, self.kw)


def set_language(lang="both"):
    """Choose the language of figures and messages: "en", "fr" or "both".

    Choisir la langue des figures et des messages : "en", "fr" ou "both" (les deux).
    """
    lang = str(lang).lower()
    if lang not in ("en", "fr", "both"):
        raise ValueError('Use "en", "fr" or "both" · Utilisez "en", "fr" ou "both"')
    _LANG["value"] = lang


def get_language():
    return _LANG["value"]


def _pair(_key, kw):
    en, fr = MESSAGES[_key]
    kw_en = {k: (v.pair()[0] if isinstance(v, M) else v) for k, v in kw.items()}
    kw_fr = {k: (v.pair()[1] if isinstance(v, M) else v) for k, v in kw.items()}
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
