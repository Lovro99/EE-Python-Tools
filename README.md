# EE-Python-Tools

Python alati za elektroprojektiranje — integracija s AutoCAD-om, Excelom, PDF-om i razvodnim ormarima.

## Struktura

```
EE-Python-Tools/
├── ormari/              # Kalkulator razvodnih ormara (tkinter desktop app)
├── pages/               # Streamlit web stranice (multi-page app)
├── launchers/           # .bat pokretači za svaki alat
├── mcp_autocad/         # MCP server – Claude <-> AutoCAD integracija via COM
├── dwg_props_helper/    # C# helper za čitanje AutoCAD DWG atributa
├── launcher.py          # EE Alati – centralni launcher (tkinter)
├── tools.json           # Popis alata s opisima i uputama za launcher
├── deploy.ps1           # Deploy skriptu – kopira alate na server
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

### EE Alati — centralni launcher

Jedno mjesto za sve alate: popis s imenom, kratkim opisom i kategorijama.
Kad zadržiš miš iznad retka ~1 s, tooltip prikaže duži opis i upute za
korištenje. Alat se pokreće dvoklikom, Enterom ili gumbom **Pokreni**.

```bash
pythonw launcher.py
```

ili preko `launchers/EE Alati.bat` — tu .bat (ili prečac na nju) pinnaj na
toolbar/taskbar pa je cijeli popis alata na jednom kliku.

Popis alata, opisi i upute uređuju se u **`tools.json`** (bez diranja koda).
Novi alat = novi unos u `tools.json`:

```json
{
  "ime": "Moj Alat",
  "skripta": "mojAlat.py",
  "kategorija": "Excel / Word",
  "opis": "Kratki opis u popisu",
  "dugi_opis": "Duži opis u tooltipu na hover",
  "upute": "1. Prvi korak\n2. Drugi korak",
  "ikona": "🔧",
  "konzola": false
}
```

Polje `"konzola": true` postavi za alate koji trebaju konzolni prozor
(`input()`/`print`); umjesto `"skripta"` može ići `"modul"` (npr.
`"ormari.app"`).

### Pojedinačni launcheri

Svaki alat ima i `.bat` launcher u `launchers/` koji aktivira venv i pokreće skriptu.

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

## Deploy na server

Alati su dostupni kolegama putem network share-a (`\\192.168.30.150\...`). Kad si zadovoljan lokalnim testiranjem, pokreni:

```powershell
.\deploy.ps1
```

Za preview bez promjena:
```powershell
.\deploy.ps1 -WhatIf
```

Workflow:
```
lokalno testiraš  →  .\deploy.ps1  →  git commit + push
```

## mcp_autocad

MCP server koji spaja Claude Code s AutoCAD-om putem COM sučelja (`pywin32`).  
Pokretanje: `python mcp_autocad/server.py`  
Konfiguracija u Claude Code `settings.json` pod `mcpServers`.

## dwg_props_helper

C# konzolni alat koji `syncProperties.py` koristi za čitanje atributa iz `.dwg` datoteka bez otvorenog AutoCAD-a (via ODA/Teigha). Kompajlirani `.exe` je uključen u repo.
