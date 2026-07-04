# QC sustav — automatska provjera usklađenosti projekta

Deterministička QA/QC provjera podataka elektroprojekta kroz tri medija:
**AutoCAD nacrt** (CSV export atributa blokova), **Excel** (bilanca
snaga) i **Word** (tehnički opis). Sustav prepisuje podatke iz svih
izvora u jednu SQLite bazu *opažanja* i javlja gdje se izvori ne slažu
(npr. snaga na nacrtu 12 kW, a u bilanci 15 kW).

Sustav **ne mijenja** izvorne datoteke i **ne odlučuje** koja je
vrijednost točna — samo pokaže *da* postoji nesklad i *gdje* (datoteka,
ćelija/red/tablica).

## Brzi start

```bash
pip install -r requirements.txt
python qc.py demo          # kreira demo projekt s namjernim greškama i pokrene QC
```

Za stvarni projekt:

```bash
# 1. u AutoCAD-u pokreni CSV export atributa (ExportCSVdata.lsp)
#    i spremi CSV u projektnu mapu
# 2. skeniraj mapu
python qc.py scan "C:/Projekti/FNE_Vrbovec" --projekt FNE_Vrbovec
# 3. izvještaj (konzola + HTML)
python qc.py report --projekt FNE_Vrbovec --html izvjestaj.html
```

Exit kod `report` naredbe je `2` ako postoje greške — pogodno za
automatizaciju (task scheduler, pre-print provjera itd.).

## Kako radi

```
bilanca.xlsx  ──┐  ekstraktori   ┌─────────────┐   usporedba
export_dwg.csv ─┼───────────────▶│    qc.db    │──────────────▶ izvještaj
opis.docx  ─────┘  (qc_config)   │ (opažanja)  │  po oznaci      (HTML)
                                 └─────────────┘
```

Svako *opažanje* = "u izvoru X, za oznaku Y, atribut Z ima vrijednost V".
Usporedba grupira opažanja po (oznaka, atribut):

| Status | Značenje |
|---|---|
| `GRESKA` | izvori imaju različite vrijednosti |
| `UPOZORENJE` | podatak postoji samo u jednom tipu izvora |
| `OK` | svi izvori se slažu |

## Konfiguracija (`qc_config.yaml`)

Kontekst podataka deklarira se **jednom po predlošku** — koji list,
koja kolona, koje zaglavlje tablice znači koji atribut. Zajednički
ključ svih izvora je `oznaka` (oznaka opreme / strujnog kruga, npr.
`RO-1`). Detalji i primjeri su u komentarima same datoteke.

Imena atributa sa sufiksom jedinice (`snaga_kw`, `struja_a`,
`presjek_mm2`, ...) tretiraju se kao brojevi: `15,0 kW` == `15 kW` ==
`15000 W`. Ostalo je tekst uz normalizaciju (`5×2,5` == `5x2.5`,
`ro-1` == `RO-1`).

## Struktura

```
qc_system/
├── qc.py                  # CLI: scan / report / demo
├── qc_config.yaml         # opis predložaka (Excel/Word/DWG-CSV)
├── qc_core/
│   ├── db.py              # SQLite baza opažanja
│   ├── normalize.py       # normalizacija oznaka i vrijednosti
│   ├── compare.py         # usporedba → GRESKA/UPOZORENJE/OK
│   ├── report.py          # konzolni i HTML izvještaj
│   ├── scan.py            # uparivanje datoteka s predlošcima
│   └── extractors/        # excel / word / dwg_csv
└── demo/make_demo.py      # generator demo projekta s greškama
```

## Ograničenja i sljedeći koraci

- DWG se čita **preko CSV exporta** (postojeći LISP alati) — direktno
  čitanje DWG-a nije potrebno ni planirano.
- Slobodan tekst u Wordu (rečenice izvan tablica) se ne provjerava —
  to je posao za AI sloj (faza 2).
- Planirano: watchdog servis (auto-sken pri spremanju datoteke),
  Streamlit QC stranica u postojećem `web_app.py`, AI ekstrakcija
  slobodnog teksta i vizualna provjera shema.
