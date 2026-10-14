# EE-Python-Tools

Python alati za elektroprojektiranje — integracija s AutoCAD-om, Excelom, PDF-om i razvodnim ormarima.

## Struktura

```
EE-Python-Tools/
├── launcher.py              # EE Alati – centralni launcher (jedini prečac)
├── launcher_git.py          # git sinkronizacija, grane, verzije (za launcher i deploy)
├── ee_verzija.py            # verzija u naslovu prozora alata
├── tools.json               # popis alata: opisi, upute, verzije
├── requirements.txt         # Python paketi za sve alate
├── Instaliraj EE Alati.bat  # instalacija + prečac (pokreće setup.ps1)
├── deploy.ps1               # objava stabilne verzije kolegama (network share)
├── ormari/                  # Kalkulator razvodnih ormara (tkinter desktop app)
├── qc_system/               # QC provjera usklađenosti DWG/Excel/Word (CLI)
├── mcp_autocad/             # MCP server – Claude <-> AutoCAD integracija via COM
├── dwg_props_helper/        # C# helper za čitanje AutoCAD DWG atributa
└── *.py                     # alati (syncProperties.py, crtanjekabel.py, …)
```

## EE Alati — svi alati na jednom mjestu

Jedan prečac **EE Alati** → popis svih alata po kategorijama, s verzijom i
datumom zadnje promjene (★ = mijenjano u zadnjih 7 dana). Kad zadržiš miš
iznad retka ~1 s, tooltip prikaže opis, upute i što je zadnje mijenjano.
Alat se pokreće dvoklikom, Enterom ili gumbom **Pokreni**. Svaki alat radi
kao zaseban program, bez ikakvih ograničenja, a verzija mu piše u naslovu
prozora.

### Instalacija (jednom)

**Tvoje računalo (razvoj):**

1. Instaliraj [Git](https://git-scm.com/download/win) i
   [Python 3](https://www.python.org/downloads/) (označi *Add to PATH*).
2. Kloniraj repo, npr. u `C:\Users\<ti>\EE-Python-Tools`:
   ```
   git clone https://github.com/Lovro99/EE-Python-Tools.git
   ```
3. Dvoklik na **`Instaliraj EE Alati.bat`** u toj mapi. Napravi `.venv`,
   instalira pakete, napravi prečac *EE Alati* (Desktop + Start meni) i ponudi
   brisanje starih prečaca na pojedinačne alate.

**Kolege (stabilna verzija):** dvoklik na `Instaliraj EE Alati.bat` **na
network shareu** (`\\192.168.30.150\Projekti\LUKA SOFTWARE\Aplikacije\AutoLisp\python`).
Skripta sama prepozna share: paketi idu u `%LOCALAPPDATA%\EE-Alati\venv`, a
prečac pokreće launcher sa sharea.

### Svakodnevni rad

```
Claude napravi promjenu na grani  →  launcher javi „Nova grana za testiranje”
→ u izborniku Verzija odabereš tu granu  →  isprobaš alat
→ merge u master  →  launcher javi „Dostupna je nova verzija”  →  ⟳ Ažuriraj
→ „Objavi kolegama”  (kad je provjereno)
```

- **Obavijesti:** launcher svakih 5 min provjeri GitHub. Ništa ne mijenja sam —
  samo pokaže plavu traku; ažurira se tek kad klikneš **⟳ Ažuriraj**.
- **Lokalne izmjene se nikad ne brišu.** Ako bi ažuriranje pregazilo neku
  izmijenjenu datoteku, launcher odbije i kaže koju.
- **Testne grane:** izbornik **Verzija** pokreće alate s odabrane grane iz
  zasebne kopije (`.grane/`), a `master` ostaje netaknut. Narančasta traka
  podsjeća da si na testnoj grani. Kopije mergeanih/obrisanih grana brišu se
  same.
- **Paketi:** kad se `requirements.txt` promijeni, launcher sam doinstalira
  pakete u venv.
- **Objavi kolegama** (= `deploy.ps1`): na share uvijek ide `origin/master` s
  GitHuba — nikad testna grana ni lokalne izmjene — i uz njega `VERSION.json`
  koji launcher kod kolega prikazuje. Kolegama launcher javi kad je objavljena
  nova verzija. Pregled bez promjena: `.\deploy.ps1 -WhatIf`.

### Dodavanje / izmjena alata

Sve je u **`tools.json`** (bez diranja launchera):

```json
{
  "ime": "Moj Alat",
  "skripta": "mojAlat.py",
  "verzija": "1.0",
  "kategorija": "Excel / Word",
  "opis": "Kratki opis u popisu",
  "dugi_opis": "Duži opis u tooltipu na hover",
  "upute": "1. Prvi korak\n2. Drugi korak",
  "ikona": "🔧",
  "konzola": false
}
```

- `"konzola": true` za alate koji trebaju konzolni prozor (`input()`/`print`).
- Umjesto `"skripta"` može `"modul"` (npr. `"ormari.app"`); `"skripta"` može
  biti i apsolutna putanja za alat izvan repoa (npr. Batch Layouti).
- Kad mijenjaš alat, povećaj mu `"verzija"`.
- Za verziju u naslovu prozora: `from ee_verzija import naslov` i
  `root.title(naslov("Moj Alat"))`.
- Novi Python paket → dodaj ga u `requirements.txt`.

### Web app (Streamlit)

`web_app.py` + `pages/` nisu dio launchera; pokretanje: `streamlit run web_app.py`.

## mcp_autocad

MCP server koji spaja Claude Code s AutoCAD-om putem COM sučelja (`pywin32`).  
Pokretanje: `python mcp_autocad/server.py`  
Konfiguracija u Claude Code `settings.json` pod `mcpServers`.

## dwg_props_helper

C# konzolni alat koji `syncProperties.py` koristi za čitanje atributa iz `.dwg` datoteka bez otvorenog AutoCAD-a (via ODA/Teigha). Kompajlirani `.exe` je uključen u repo.
