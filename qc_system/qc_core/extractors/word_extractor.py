"""Ekstrakcija iz Word tehnickog opisa.

Dva izvora konteksta u .docx datoteci:

1. TABLICE — tablica ciji header sadrzi kljucnu kolonu (npr. "Oznaka")
   tretira se kao tablica krugova; ostale kolone mapiraju se na atribute
   preko sinonima iz predloska.

2. CUSTOM PROPERTIES (File > Info > Properties) — imenovana svojstva
   dokumenta mapiraju se na atribute; oznaka im je "PROJEKT" (podaci na
   razini projekta, npr. instalirana snaga).

Primjer predloska:
    ime: tehnicki_opis
    tip: word
    datoteka: "*opis*.docx"
    tablice:
      kljucna_kolona: ["oznaka", "oznaka kruga", "krug"]
      atributi:
        "snaga": snaga_kw
        "snaga (kw)": snaga_kw
        "kabel": tip_kabela
        "zaštita": zastita
    svojstva:
      "instalirana snaga": inst_snaga_kw
"""

import re
import zipfile
import xml.etree.ElementTree as ET

from docx import Document

from ..normalize import normalize_tag, normalize_value

_CUSTOM_NS = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
_VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"


def _norm_header(text):
    """Header celije: mala slova, bez suvisnih razmaka i interpunkcije."""
    return re.sub(r"\s+", " ", text.strip().lower()).strip(" :.")


def _read_custom_properties(path):
    """python-docx ne podrzava custom properties — citamo XML direktno."""
    props = {}
    with zipfile.ZipFile(path) as zf:
        if "docProps/custom.xml" not in zf.namelist():
            return props
        root = ET.fromstring(zf.read("docProps/custom.xml"))
        for prop in root.findall(f"{{{_CUSTOM_NS}}}property"):
            name = prop.get("name")
            if name is None or len(prop) == 0:
                continue
            value = prop[0].text
            if value is not None:
                props[name] = value
    return props


def _extract_tables(doc, cfg):
    key_names = [_norm_header(k) for k in cfg.get("kljucna_kolona", ["oznaka"])]
    attr_map = {_norm_header(k): v for k, v in cfg.get("atributi", {}).items()}

    rows = []
    for t_idx, table in enumerate(doc.tables, start=1):
        if not table.rows:
            continue
        header = [_norm_header(c.text) for c in table.rows[0].cells]
        try:
            key_col = next(i for i, h in enumerate(header) if h in key_names)
        except StopIteration:
            continue  # nije tablica krugova
        col_attrs = {
            i: attr_map[h] for i, h in enumerate(header)
            if i != key_col and h in attr_map
        }
        if not col_attrs:
            continue
        for r_idx, row in enumerate(table.rows[1:], start=2):
            cells = row.cells
            if key_col >= len(cells):
                continue
            raw_tag = cells[key_col].text.strip()
            if not raw_tag:
                continue
            tag = normalize_tag(raw_tag)
            for c_idx, attribute in col_attrs.items():
                if c_idx >= len(cells):
                    continue
                raw_value = cells[c_idx].text.strip()
                if not raw_value:
                    continue
                rows.append({
                    "tag": tag,
                    "raw_tag": raw_tag,
                    "attribute": attribute,
                    "value": normalize_value(attribute, raw_value),
                    "raw_value": raw_value,
                    "location": f"tablica {t_idx}, red {r_idx}",
                })
    return rows


def _extract_properties(path, cfg):
    prop_map = {k.strip().lower(): v for k, v in cfg.items()}
    rows = []
    for name, value in _read_custom_properties(path).items():
        # podudaranje po podstringu, kao u postojecem scrape_word.py
        matched = next(
            (attr for key, attr in prop_map.items() if key in name.strip().lower()),
            None,
        )
        if matched is None:
            continue
        raw_value = str(value).strip()
        if not raw_value:
            continue
        rows.append({
            "tag": "PROJEKT",
            "raw_tag": "PROJEKT",
            "attribute": matched,
            "value": normalize_value(matched, raw_value),
            "raw_value": raw_value,
            "location": f"svojstvo '{name}'",
        })
    return rows


def extract_word(path, template):
    rows = []
    if template.get("tablice"):
        rows.extend(_extract_tables(Document(path), template["tablice"]))
    if template.get("svojstva"):
        rows.extend(_extract_properties(path, template["svojstva"]))
    return rows
