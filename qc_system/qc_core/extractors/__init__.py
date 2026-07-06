"""Ekstraktori — prepisuju podatke iz izvornih datoteka u opazanja.

Svaki ekstraktor prima (path, template, field_dict) i vraca listu redaka
spremnih za db.replace_source(). field_dict koriste samo KV ekstraktori
(excel_kv, word_kv) za mapiranje naziva svojstva na kanonsko polje.

Dva nacina rada, ovisno o tipu projekta:
  - tablicni (excel / word / dwg_csv): spajanje po OZNACI opreme/kruga
  - key-value (excel_kv / word_kv): spajanje po KANONSKOM imenu polja
    (za FNE i sl. gdje su podaci na razini projekta)
"""

from .excel_extractor import extract_excel
from .word_extractor import extract_word
from .dwg_csv_extractor import extract_dwg_csv
from .excel_kv_extractor import extract_excel_kv
from .word_kv_extractor import extract_word_kv

# tip predloska -> (funkcija, source_type u bazi)
EXTRACTORS = {
    "excel": (extract_excel, "excel"),
    "word": (extract_word, "word"),
    "dwg_csv": (extract_dwg_csv, "dwg"),
    "excel_kv": (extract_excel_kv, "excel"),
    "word_kv": (extract_word_kv, "word"),
}
