"""Skeniranje projektne mape: pronadi datoteke po predlošcima i ekstrahiraj."""

import fnmatch
from pathlib import Path

import yaml

from . import db
from .extractors import EXTRACTORS
from .fields import FieldDict


def load_config(config_path):
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not cfg or "predlosci" not in cfg:
        raise ValueError(f"{config_path}: nedostaje kljuc 'predlosci'")
    for t in cfg["predlosci"]:
        for key in ("ime", "tip", "datoteka"):
            if key not in t:
                raise ValueError(f"predlozak bez kljuca '{key}': {t}")
        if t["tip"] not in EXTRACTORS:
            raise ValueError(
                f"predlozak '{t['ime']}': nepoznat tip '{t['tip']}' "
                f"(podrzani: {', '.join(EXTRACTORS)})"
            )
    return cfg


def scan_project(conn, project, project_dir, config):
    """Prodji kroz mapu, upari datoteke s predlošcima i upisi opazanja.

    Vraca listu (datoteka, ime_predloska, broj_opazanja | greska_str).
    """
    project_dir = Path(project_dir)
    field_dict = FieldDict(config.get("polja"))
    results = []
    seen = set()
    for template in config["predlosci"]:
        pattern = template["datoteka"]
        extractor, source_type = EXTRACTORS[template["tip"]]
        for path in sorted(project_dir.rglob("*")):
            if not path.is_file() or path.name.startswith("~$"):
                continue
            if not fnmatch.fnmatch(path.name.lower(), pattern.lower()):
                continue
            if path in seen:
                continue  # prvi predlozak koji upari datoteku "vlasnik" je
            seen.add(path)
            try:
                rows = extractor(str(path), template, field_dict=field_dict)
                n = db.replace_source(conn, project, str(path), source_type, rows)
                results.append((path.name, template["ime"], n))
            except Exception as e:  # jedna losa datoteka ne rusi ostale
                results.append((path.name, template["ime"], f"GRESKA: {e}"))
    return results
