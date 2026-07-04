"""Ekstraktori — prepisuju podatke iz izvornih datoteka u opazanja.

Svaki ekstraktor prima svoj dio konfiguracije (predlozak iz
qc_config.yaml) i vraca listu redaka spremnih za db.replace_source().
"""

from .excel_extractor import extract_excel
from .word_extractor import extract_word
from .dwg_csv_extractor import extract_dwg_csv

# tip predloska -> (funkcija, source_type u bazi)
EXTRACTORS = {
    "excel": (extract_excel, "excel"),
    "word": (extract_word, "word"),
    "dwg_csv": (extract_dwg_csv, "dwg"),
}
