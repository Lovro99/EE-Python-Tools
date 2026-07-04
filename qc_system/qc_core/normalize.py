"""Normalizacija oznaka i vrijednosti prije usporedbe.

Cilj: "RO-1" i "ro 1" su ista oznaka; "15,0 kW" i "15 kW" ista snaga;
"5×2,5" i "5x2.5" isti kabel. Normalizirana vrijednost sluzi SAMO za
usporedbu — u izvjestaju se uvijek prikazuje i sirova vrijednost.
"""

import re

# Atributi koji se tretiraju kao brojevi (sufiks odreduje jedinicu)
_NUMERIC_SUFFIXES = ("_kw", "_w", "_a", "_v", "_m", "_mm2", "_kvar", "_kva", "_pct")

# Jedinice koje se smiju pojaviti uz broj i njihov faktor prema
# kanonskoj jedinici atributa (kanonska = ona iz imena atributa)
_UNIT_FACTORS = {
    "_kw": {"kw": 1.0, "w": 0.001},
    "_w": {"w": 1.0, "kw": 1000.0},
    "_kva": {"kva": 1.0, "va": 0.001},
    "_kvar": {"kvar": 1.0, "var": 0.001},
    "_a": {"a": 1.0, "ma": 0.001},
    "_v": {"v": 1.0, "kv": 1000.0},
    "_m": {"m": 1.0, "km": 1000.0, "mm": 0.001},
    "_mm2": {"mm2": 1.0, "mm²": 1.0},
    "_pct": {"%": 1.0},
}

_NUM_RE = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*([a-zA-Z%²]*)\s*$")


def normalize_tag(raw):
    """Oznaka opreme: velika slova, razmaci/underscori -> crtica."""
    tag = raw.strip().upper()
    tag = re.sub(r"[\s_]+", "-", tag)
    tag = re.sub(r"-{2,}", "-", tag)
    return tag


def _is_numeric_attr(attribute):
    return attribute.lower().endswith(_NUMERIC_SUFFIXES)


def _normalize_number(attribute, raw):
    """Vrati kanonski zapis broja ili None ako se ne da parsirati."""
    m = _NUM_RE.match(raw.replace(" ", " "))
    if not m:
        return None
    num = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    if unit:
        suffix = next(
            (s for s in _UNIT_FACTORS if attribute.lower().endswith(s)), None
        )
        if suffix and unit in _UNIT_FACTORS[suffix]:
            num *= _UNIT_FACTORS[suffix][unit]
        elif suffix:
            return None  # nepoznata jedinica uz broj — ne pogadaj
    # :g mice suvisne nule (15.0 -> 15), zaokruzi da izbjegnes float sum
    return f"{round(num, 6):g}"


def normalize_value(attribute, raw):
    """Normaliziraj vrijednost atributa za usporedbu."""
    s = str(raw).strip()
    if not s:
        return ""
    if _is_numeric_attr(attribute):
        n = _normalize_number(attribute, s)
        if n is not None:
            return n
    # opci tekst / tip kabela / zastita: bez razmaka, x umjesto ×,
    # tocka umjesto zareza, velika slova, ² -> 2
    s = s.replace("×", "x").replace("²", "2").replace(",", ".")
    s = re.sub(r"\s+", "", s)
    return s.upper()
