"""A result that shows itself in a notebook: sentences, a figure and a table.

Un résultat qui s'affiche tout seul dans un notebook : phrases, figure et tableau.
"""
import base64

import pandas as pd

from .i18n import html, t
from .messages import MESSAGES
from .style import to_png

_BOX = ("font-family:system-ui,-apple-system,'Segoe UI',sans-serif;line-height:1.45;"
        "border-left:4px solid #2a78d6;padding:4px 0 4px 14px;margin:6px 0 10px 0")


def reason_label(code):
    """Translate a reason code (data never changes language) · Traduire un code de raison"""
    key = f"reason_{code}"
    if key in MESSAGES:
        return t(key)
    if " > " in str(code):
        flag, limit = str(code).split(" ", 1)[1].split(" > ")
        return t("reason_quality", flag=flag, limit=limit)
    return str(code)


class Result:
    """What every step returns · Ce que renvoie chaque étape.

    .table   the numbers as a DataFrame (English column names) · les chiffres (noms de colonnes en anglais)
    .values  key numbers as a dict · chiffres clés
    .figure  the matplotlib figure (drawn in the current language) · la figure
    .save(path) save the figure · enregistrer la figure
    """

    def __init__(self, heading, lines=(), figure=None, table=None, values=None, warnings=(), table_rows=12,
                 display_table=None):
        self.heading = heading            # (key, kwargs)
        self.lines = list(lines)          # [(key, kwargs), ...]
        self._figure = figure             # callable -> Figure, or None
        self.table = table
        self.values = values or {}
        self.warnings = list(warnings)
        self._rows = table_rows
        self._display_table = display_table   # callable -> DataFrame for display (translated labels)

    @property
    def figure(self):
        return self._figure() if self._figure else None

    def save(self, path, dpi=200):
        fig = self.figure
        if fig is not None:
            fig.savefig(path, dpi=dpi)
        return path

    def _repr_html_(self):
        key, kw = self.heading
        parts = [f'<div style="{_BOX}">', f'<div style="font-weight:700;font-size:1.05em">{html(key, **kw)}</div>']
        for k, a in self.lines:
            parts.append(f'<div style="margin-top:4px">{html(k, **a)}</div>')
        for k, a in self.warnings:
            parts.append(f'<div style="margin-top:4px;color:#8a3a12">⚠️ {html(k, **a)}</div>')
        parts.append("</div>")
        fig = self.figure
        if fig is not None:
            b64 = base64.b64encode(to_png(fig)).decode()
            parts.append(f'<img style="max-width:100%" src="data:image/png;base64,{b64}">')
        tab = self._display_table() if self._display_table else self.table
        if isinstance(tab, (pd.DataFrame, pd.Series)) and len(tab):
            tab = tab.to_frame() if isinstance(tab, pd.Series) else tab
            parts.append(tab.head(self._rows).to_html(float_format=lambda x: f"{x:.3g}" if abs(x) < 1e4 else f"{x:,.0f}",
                                                      border=0))
        return "\n".join(parts)

    def __repr__(self):
        key, kw = self.heading
        lines = [t(key, **kw)] + [t(k, **a) for k, a in self.lines] + ["! " + t(k, **a) for k, a in self.warnings]
        return "\n".join(lines)
