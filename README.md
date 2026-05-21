# EE-Python-Tools

Python alati za elektroprojektiranje — integracija s AutoCAD-om, Excelom, PDF-om i razvodnim ormarima.

## Struktura

```
EE-Python-Tools/
├── ormari/              # Kalkulator razvodnih ormara (tkinter desktop app)
├── pages/               # Streamlit web stranice (multi-page app)
├── launchers/           # .bat pokretači za svaki alat
├── dwg_props_helper/    # C# helper za čitanje AutoCAD DWG atributa
├── web_app.py           # Streamlit ulazna točka (multi-page)
├── syncProperties.py    # Sinkronizacija DWG properties između crteža
├── syncDwgFast.py       # Brza sinkronizacija DWG (bez GUI)
├── crtanjekabel.py      # Crtanje kabela iz Excela u AutoCAD
├── excelToWord.py       # Export Excel podataka u Word
├── hepaFormFiller.py    # Punjenje HEPA PDF obrazaca
├── pdfFormFiller.py     # Punjenje generičkih PDF obrazaca
├── PrintOrganizer.py    # Organizacija ispisa
├── ExcelPdfPlacer.py    # Postavljanje PDF-ova prema Excelu
├── CabelLength.py       # Proračun duljina kabela
├── search.py            # Pretraga Word dokumenata
└── ...
```

## Pokretanje

Svaki alat ima `.bat` launcher u `launchers/` koji aktivira venv i pokreće skriptu.

### Web app (Streamlit)
```bash
streamlit run web_app.py
```

### Ormari kalkulator
```bash
python ormari/app.py
```

## Ovisnosti

```bash
pip install -r requirements.txt
```

## dwg_props_helper

C# konzolni alat koji `syncProperties.py` koristi za čitanje atributa iz `.dwg` datoteka bez otvorenog AutoCAD-a (via ODA/Teigha). Kompajlirani `.exe` je uključen u repo.
