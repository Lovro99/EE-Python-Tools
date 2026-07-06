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

_NUM_RE = re.compile(r"^\s*(-?[\d.,]+)\s*([a-zA-Z%²]*)\s*$")


def _parse_hr_number(s):
    """Parsiraj broj u hrvatskom/engleskom zapisu -> float ili None.

      "4.000,00" -> 4000.0   (tocka=tisucice, zarez=decimala)
      "1,093"    -> 1093.0   (tocka nije, zarez=tisucice ako 3 znamenke)
      "15,0"     -> 15.0     (zarez=decimala)
      "13.48"    -> 13.48    (tocka=decimala)
    """
    s = s.strip()
    if not re.fullmatch(r"-?[\d.,]+", s):
        return None
    has_dot, has_comma = "." in s, "," in s
    try:
        if has_dot and has_comma:
            # zadnji separator je decimalni, drugi su tisucice
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif has_comma:
            # "1,093" (3 znamenke iza) = tisucice; "15,0" = decimala
            frac = s.split(",")[-1]
            s = s.replace(",", "") if len(frac) == 3 else s.replace(",", ".")
        return float(s)
    except ValueError:
        return None


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
    m = _NUM_RE.match(raw.replace(u" ", " "))
    if not m:
        return None
    num = _parse_hr_number(m.group(1))
    if num is None:
        return None
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


def normalize_value(attribute, raw, numeric=None):
    """Normaliziraj vrijednost atributa za usporedbu.

    numeric: None  -> tip se pogada iz sufiksa imena (_kw, _a, _mm2, ...)
             True  -> uvijek pokusaj kao broj (KV polja s tip: broj)
             False -> uvijek tekst
    """
    s = str(raw).strip()
    if not s:
        return ""
    want_num = _is_numeric_attr(attribute) if numeric is None else numeric
    if want_num:
        converted = _normalize_number(attribute, s)
        if converted is not None:
            return converted
        m = _NUM_RE.match(s.replace("\xa0", " "))
        if m:
            n = _parse_hr_number(m.group(1))
            if n is not None:
                return f"{round(n, 6):g}"
    # opci tekst / tip kabela / zastita: bez razmaka, x umjesto ×,
    # tocka umjesto zareza, velika slova, ² -> 2
    s = s.replace("×", "x").replace("²", "2").replace(",", ".")
    s = re.sub(r"\s+", "", s)
    return s.upper()
