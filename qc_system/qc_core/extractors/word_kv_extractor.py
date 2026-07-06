"""Ekstrakcija Word custom properties -> kanonska polja projekta.

Cita DOCPROPERTY svojstva (.docx/.docm) i mapira ih na kanonska polja iz
zajednickog rjecnika (fields.py). Time se hvataju zastarjeli/duplirani
ostaci iz sablone: npr. 'Model  invertera' (dupli razmak) s drugom
vrijednoscu od 'Model invertera' zavrsi na istom kanonskom polju i
nesklad se prijavi.

Primjer predloska:
    ime: opis_kv
    tip: word_kv
    datoteka: "*.doc?"      # .docx ili .docm
"""

import zipfile
import xml.etree.ElementTree as ET

from ..normalize import normalize_value

_CUSTOM_NS = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
TAG = "PROJEKT"


def _read_custom_properties(path):
    props = []  # (name, value) — cuvamo redoslijed
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
                props.append((name, value))
    return props


def extract_word_kv(path, template, field_dict=None):
    if not field_dict:
        raise ValueError(
            f"predlozak '{template['ime']}' (word_kv) zahtijeva "
            f"'polja:' rjecnik u configu"
        )
    rows = []
    for name, value in _read_custom_properties(path):
        field = field_dict.match(name)
        if field is None:
            continue
        raw_value = str(value).strip()
        if not raw_value:
            continue
        rows.append({
            "tag": TAG,
            "raw_tag": TAG,
            "attribute": field,
            "value": normalize_value(
                field, raw_value, numeric=field_dict.is_numeric(field)
            ),
            "raw_value": raw_value,
            "location": f"svojstvo '{name}'",
        })
    return rows
