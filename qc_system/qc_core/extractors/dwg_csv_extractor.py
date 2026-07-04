"""Ekstrakcija iz CSV exporta atributa blokova iz AutoCAD-a.

Nacrti se ne citaju direktno — koristi se postojeci LISP export
(ExportCSVdata.lsp / ExportLayoutsToExcel.lsp) koji atribute blokova
ispise u CSV. Predlozak mapira imena CSV kolona na atribute:

    ime: dwg_export
    tip: dwg_csv
    datoteka: "*dwg*.csv"
    separator: ";"           # default ";", moze i ","
    kolone:
      CIRCUIT_LABEL: oznaka
      SNAGA: snaga_kw
      KABEL: tip_kabela
      ZASTITA: zastita
"""

import csv

from ..normalize import normalize_tag, normalize_value


def extract_dwg_csv(path, template):
    sep = template.get("separator", ";")
    col_map = {k.strip().upper(): v for k, v in template["kolone"].items()}
    key_header = next(
        (k for k, attr in col_map.items() if attr == "oznaka"), None
    )
    if key_header is None:
        raise ValueError(f"predlozak '{template['ime']}': nema kolone 'oznaka'")

    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=sep)
        if reader.fieldnames is None:
            return rows
        headers = {h.strip().upper(): h for h in reader.fieldnames}
        if key_header not in headers:
            raise ValueError(
                f"{path}: nema kolone '{key_header}' "
                f"(nadene: {', '.join(headers)})"
            )
        for line_no, row in enumerate(reader, start=2):
            raw_tag = (row.get(headers[key_header]) or "").strip()
            if not raw_tag:
                continue
            tag = normalize_tag(raw_tag)
            for header_up, attribute in col_map.items():
                if attribute == "oznaka" or header_up not in headers:
                    continue
                raw_value = (row.get(headers[header_up]) or "").strip()
                if not raw_value:
                    continue
                rows.append({
                    "tag": tag,
                    "raw_tag": raw_tag,
                    "attribute": attribute,
                    "value": normalize_value(attribute, raw_value),
                    "raw_value": raw_value,
                    "location": f"red {line_no}, kolona {headers[header_up]}",
                })
    return rows
