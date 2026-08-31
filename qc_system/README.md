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

## Dva tipa projekta

Sustav podržava dva načina spajanja podataka — biraš ga tipom predloška
u konfiguraciji:

| Način | Ključ spajanja | Tipovi predložaka | Primjer projekta |
|---|---|---|---|
| **tablični** | oznaka opreme/kruga (`RO-1`) | `excel`, `word`, `dwg_csv` | razdjelne ploče, instalacije |
| **key-value** | naziv polja (`Model invertera`) | `excel_kv`, `word_kv` | FNE — Excel „Podaci" ↔ Word properties ↔ DWG title-block |

Za FNE projekte koristi `qc_config_fne.yaml`:

```bash
python qc.py scan "C:/Projekti/FNE_Kadijevic" --projekt FNE_Kadijevic --config qc_config_fne.yaml
python qc.py report --projekt FNE_Kadijevic --html izvjestaj.html
```

Key-value način hvata tipičnu FNE grešku — **zastarjele/duplirane
vrijednosti iz šablone**: npr. Word svojstvo `Model  invertera` (dupli
razmak) ili `Izlazna struja invertera ` (razmak na kraju) s vrijednošću
zaostalom od prošlog projekta koja se ne slaže s Excelom. Rječnik
`polja:` mapira sve nazivne varijante (uklj. tipfelere kao
`Proizođač` bez „v") na jedno kanonsko polje pa se vrijednosti mogu
usporediti.

## Konfiguracija

Kontekst podataka deklarira se **jednom po predlošku** — koji list,
koja kolona/zaglavlje/svojstvo znači koji podatak. Detalji i primjeri
su u komentarima datoteka `qc_config.yaml` (tablični) i
`qc_config_fne.yaml` (key-value + rječnik polja).

Imena atributa sa sufiksom jedinice (`snaga_kw`, `struja_a`,
`presjek_mm2`, ...) tretiraju se kao brojevi: `15,0 kW` == `15 kW` ==
`15000 W`. Ostalo je tekst uz normalizaciju (`5×2,5` == `5x2.5`,
`ro-1` == `RO-1`).

## Struktura

```
qc_system/
├── qc.py                  # CLI: scan / report / demo
├── qc_config.yaml         # tablični predlošci (Excel/Word/DWG-CSV)
├── qc_config_fne.yaml     # key-value predlošci + rječnik polja (FNE)
├── qc_core/
│   ├── db.py              # SQLite baza opažanja
│   ├── normalize.py       # normalizacija (uklj. HR broj: "4.000,00"==4000)
│   ├── fields.py          # rječnik polja (kanonsko ime + aliasi) za KV
│   ├── compare.py         # usporedba → GRESKA/UPOZORENJE/OK
│   ├── report.py          # konzolni i HTML izvještaj
│   ├── scan.py            # uparivanje datoteka s predlošcima
│   └── extractors/        # excel / word / dwg_csv / excel_kv / word_kv
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
