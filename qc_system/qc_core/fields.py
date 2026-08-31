"""Rjecnik polja za key-value projekte (FNE i sl.).

Isti podatak zove se malo drukcije u Excelu i Wordu ("Model invertera"
vs "Model  invertera", "Proizvodac invertera" vs typo "Proizodac
invertera"). Rjecnik polja mapira sve te aliase na jedno KANONSKO ime,
pa se vrijednosti mogu usporediti.

Config oblik (dio qc_config.yaml):

    polja:
      - ime: model_invertera
        tip: tekst
        aliasi: ["Model invertera"]
      - ime: dc_snaga_kw
        tip: broj
        aliasi: ["DC snaga elektrane", "DC snaga FNE", "Instalirana snaga DC"]

Alias se usporeduje neosjetljivo na velika/mala slova, visestruke razmake
i zavrsnu interpunkciju — tako "Model  invertera" (dupli razmak) padne na
isto kanonsko polje kao "Model invertera" i njihov nesklad se prijavi.
"""

import re


def _norm_key(text):
    return re.sub(r"\s+", " ", str(text).strip().lower()).strip(" :.")


class FieldDict:
    def __init__(self, polja):
        self._alias_to_field = {}
        self._is_numeric = {}
        for p in polja or []:
            ime = p["ime"]
            self._is_numeric[ime] = (p.get("tip", "tekst") == "broj")
            for alias in [ime] + list(p.get("aliasi", [])):
                self._alias_to_field[_norm_key(alias)] = ime

    def match(self, raw_name):
        """Vrati kanonsko ime polja za dani naziv ili None ako nepoznat."""
        return self._alias_to_field.get(_norm_key(raw_name))

    def is_numeric(self, field):
        return self._is_numeric.get(field, False)

    def __bool__(self):
        return bool(self._alias_to_field)
